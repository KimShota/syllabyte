"""
Writing one KU's three bank items (plan/per-ku-profiling-plan.md D4) with an LLM, checked by the critic. Used by
scripts/build_item_bank.py for the dev course and by the upload worker for each uploaded deck
(plan/slide-uploads-plan.md); assessment_agent/bank.py turns the result into `Item`s.
"""

from __future__ import annotations

from collections.abc import Callable

from syllabyte_common.llm import structured, text_block
from syllabyte_common.models import KnowledgeUnit, RunManifest

from assessment_agent.bank import MAX_STEM_WORDS, TIER_BLOOM, TIERS, KuBankGen, stem_problems
from assessment_agent.item_writing import ITEM_SYSTEM, generate_with_critic, mcq_text
from assessment_agent.precheck_quality import precheck_bank_problems, require_approved

_STEM_RULE = "- The stem is concise and self-contained; include the data and assumptions needed to answer."
assert _STEM_RULE in ITEM_SYSTEM, "item_writing.ITEM_SYSTEM changed; update the stem rule here"
_NEW_STEM_RULE = (
    f"- The stem is self-contained and at most {MAX_STEM_WORDS} words of prose, excluding fenced code/data: students read it on a phone. Use only as much setup as the task needs. If it sets up a "
    "situation or states a claim, the question comes after it, and it always ends with a question mark."
)
BANK_SYSTEM = "\n".join(
    l.replace(_STEM_RULE, _NEW_STEM_RULE)  # keeps what follows on the line: "Do not say 'according to the slide'…"
    for l in ITEM_SYSTEM.splitlines()
    if not l.startswith(("- difficulty_prior", "- hint:"))
) + "\n- Set hint=null. Pre-checks measure prior understanding; do not provide hints or teach the answer in the stem."


TIER_TASKS = {
    "basic": "- basic: recognize one fact, definition or simple example of the idea, so a student who learned it elsewhere can answer. Do not require a multi-step calculation or diagnose a design failure at this tier.",
    "applied": "- applied: handle a new case in the slides' own setting: classify it, compute with it, or read it. It must need more than the basic question's lookup, and must not be the same lookup with another value.",
    "advanced": '- advanced: judge a claim or design, spot what is wrong with an argument, or predict what changes when a condition changes. Vary the shape across units; do not always open with "A colleague claims".',
}
STAY_IN_SLIDES = (
    "The student takes this check BEFORE the lecture and has never seen these slides. Test the ideas the slides teach, "
    "never the slides themselves: the stem, the options, the explanation and the hint must all make sense to someone who "
    "has not seen them. Never rely on a slide or an absent diagram, figure, panel, chart, plot, table or image, and never name an "
    "example, dataset or story the way the slides do (\"the house example\", \"the robot\"). When a question needs a "
    "case, describe it fully in the stem, briefly: retell the slides' own case, or use a short new case in the same "
    "setting, so long as answering it needs only the idea the slides teach and nothing from another domain. Where the "
    "slides state a number, rule or definition, preserve its meaning and notation. Standard CS and mathematical "
    "notation is allowed, including variables, Greek letters, equations, quantifiers and code. Define problem-specific "
    "symbols and supply necessary domains, dimensions and assumptions without teaching the answer. Avoid private "
    "course labels or names of people unless needed to identify the concept. "
    "Standard topic terms such as stack or queue can be the knowledge being tested; leave their definitions for the "
    "post-check explanation. Test one idea per question: the right option makes one point, not two joined together, and every wrong option "
    "is wrong as a whole, not partly true. Do not state, define or explain the target rule in the stem when knowing "
    "that rule is what the question tests. Supply the scenario and necessary data, but leave the reasoning to the student. "
    "Use standard technical terms when their meaning is the knowledge being tested; do not explain them in a way that "
    "reveals which option is correct. Favor transferable understanding of the topic over recalling slide wording or trivia."
)
WRONG_OPTIONS = "Wrong options: each must be a plausible misconception about this idea. Never make a wrong option restate the claim the question asks the student to evaluate, never make it a true statement, and a negation is appropriate when distinguishing a proposition from its negation is the skill being tested."
SAME_LENGTH_OPTIONS = (
    "Options: keep them comparable in specificity and avoid wording that reveals the answer. "
    "Do not pad mathematical expressions or code to equalize their character counts. Quantifiers and absolute words "
    "such as always, never, only and none are allowed when their truth is the concept being tested. "
    "Do not give the wrong options away with irrelevant absolutes or give only the key an explanatory clause. "
    "All three answers must be semantically distinct: check algebraic equivalence and code behavior, not just wording."
)
EXPLANATION_AND_HINT = (
    "Set hint=null: diagnostic pre-checks have no hints. The explanation is one or two complete sentences in plain "
    "words, ending in a full stop or question mark, with nothing after it. It is feedback for after the check, never information for the stem."
)
# what the critic adds for a pre-check question, on top of its usual checks of the key and the wrong options
PRECHECK_CRITIC_CHECKS = (
    "These are pre-lecture questions, so also check: (5) someone who has never seen the slides can understand the stem "
    "and options (no dependence on a slide or an absent figure, diagram, plot or table, and no example named the way the slides name "
    "it); (6) the keyed option does not stand out by being longer, more detailed or more hedged than the others, and the "
    "wrong options are not marked out by irrelevant qualifiers. Different formula lengths and necessary quantifiers "
    "are not giveaways; "
    f"(7) the stem is at most {MAX_STEM_WORDS} words of prose, excluding fenced code/data, and includes all needed context; "
    "(8) the question tests one idea: the key does not bundle two points, and no wrong option is partly true; "
    "(9) standard CS and mathematical notation is allowed. Verify the meaning, domains, dimensions, quantifiers and "
    "code semantics, and ensure problem-specific symbols are defined. Standard technical terms may name the "
    "knowledge being tested: do not require the stem to define those terms; "
    "(10) the explanation consists of clean, complete sentences with no stray "
    "characters, and hint is null; (11) the stem does not teach, define or repeat the target rule or give the correct "
    "option away through a wording match; it tests the student's existing understanding; (12) the task matches its "
    "stated tier: basic is recognition/understanding, applied uses a concrete case, advanced judges or predicts; "
    "(13) questions test ideas from this knowledge unit, not incidental slide trivia, and one question does not "
    "reveal the answer to another in the bank. Reject a question for a genuine cue or tier mismatch."
)


def bank_prompt(ku: KnowledgeUnit, prereq_titles: list[str], slide_text: str, extra: str = "") -> str:
    prereq = "; ".join(prereq_titles) if prereq_titles else "none"
    tiers = "\n".join(f"- {t} ({TIER_BLOOM[t]})" for t in TIERS)
    return f"""Knowledge unit: {ku.title}
Summary: {ku.summary}
Bloom level the course analysis gave this unit: {ku.bloom_level}
It builds on: {prereq}

Write THREE questions about this knowledge unit for a pre-test of what a student already knows, one per tier:
{tiers}

{TIER_TASKS["basic"]}
{TIER_TASKS["applied"]}
{TIER_TASKS["advanced"]}
The three tiers must call for different kinds of thinking, not just different wording, and must be independent: answering one must not give away another, and none may reuse another's wording or options.

{STAY_IN_SLIDES}

{WRONG_OPTIONS}

{SAME_LENGTH_OPTIONS}

{EXPLANATION_AND_HINT}

Set `slides` to the slide numbers that support the questions (one list for all three).
Set `ku_difficulty` from -2 (very easy) to 2 (hard): how hard is this CONCEPT for a student meeting it for the first time. Rate the concept, not your questions; the three tiers are spread apart automatically.

Slides (text and images follow):
{slide_text}{extra}"""


def write_ku_bank(
    ku: KnowledgeUnit,
    prereq_titles: list[str],
    material: tuple[str, list[dict]],
    *,
    model: str,
    critic_model: str,
    manifest: RunManifest,
    log: Callable[[str], None] = print,
    strict: bool = False,
    avoid: list[str] | None = None,
) -> tuple[KuBankGen, list[dict]]:
    """The KU's three items and the critic's remaining flags. `material`: the KU's slides as text and image blocks."""

    def ask(extra: str) -> KuBankGen:
        previous = "\nAlready saved questions; ask independently and avoid repeating their stems:\n" + "\n".join(avoid) if avoid else ""
        return structured(
            schema=KuBankGen, content=[text_block(bank_prompt(ku, prereq_titles, material[0], previous + extra)), *material[1]],
            system=BANK_SYSTEM, stage="item_bank", ku_id=ku.id, model=model, max_tokens=6000, manifest=manifest,
        )

    def make(extra: str) -> KuBankGen:
        g = ask(extra)
        problems = precheck_bank_problems(g) if strict else stem_problems(g)
        if problems:
            log(f"  {ku.id}: {problems} — asking again once")
            g = ask(extra + "\n\nYour previous attempt had problems. Fix them:\n" + "\n".join(f"- {p}" for p in problems))
        return g

    def describe(g: KuBankGen) -> str:
        return "\n".join(f"Tier: {t} ({TIER_BLOOM[t]})\n" + mcq_text(f"as-{ku.id}-{t}", getattr(g, t)) for t in TIERS)

    gen, flags = generate_with_critic(
        make=make, describe=describe, ids_of=lambda g: [f"as-{ku.id}-{t}" for t in TIERS], material=material,
        stage=f"bank_{ku.id}", model=critic_model, manifest=manifest, log=log, critic_checks=PRECHECK_CRITIC_CHECKS, require_all_verdicts=strict,
    )
    # anything the retry did not fix stays visible on the review sheet
    problems = precheck_bank_problems(gen) if strict else stem_problems(gen)
    flags += [{"id": f"as-{ku.id}-{p.split(':')[0]}", "issue": p.split(': ', 1)[1]} for p in problems]
    if strict:
        require_approved(flags)
    return gen, flags
