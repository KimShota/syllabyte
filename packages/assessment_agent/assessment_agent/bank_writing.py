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

_STEM_RULE = "- The stem is one sentence, under 28 words, and self-contained."
assert _STEM_RULE in ITEM_SYSTEM, "item_writing.ITEM_SYSTEM changed; update the stem rule here"
_NEW_STEM_RULE = (
    f"- The stem is self-contained and at most {MAX_STEM_WORDS} words: students read it on a phone. If it sets up a "
    "situation or states a claim, the question comes after it, and it always ends with a question mark."
)
BANK_SYSTEM = "\n".join(
    l.replace(_STEM_RULE, _NEW_STEM_RULE)  # keeps what follows on the line: "Do not say 'according to the slide'…"
    for l in ITEM_SYSTEM.splitlines()
    # a pre-check has no notation at all (STAY_IN_SLIDES), so the rule on how to write it is dropped
    if not l.startswith(("- difficulty_prior", "- Write math"))
)


TIER_TASKS = {
    "basic": "- basic: one fact or definition from the slides, asked about the idea rather than the slides' name or symbol for it, so a student who learned it elsewhere can answer.",
    "applied": "- applied: handle a new case in the slides' own setting: classify it, compute with it, or read it. It must need more than the basic question's lookup, and must not be the same lookup with another value.",
    "advanced": '- advanced: judge a claim or design, spot what is wrong with an argument, or predict what changes when a condition changes. Vary the shape across units; do not always open with "A colleague claims".',
}
STAY_IN_SLIDES = (
    "The student takes this check BEFORE the lecture and has never seen these slides. Test the ideas the slides teach, "
    "never the slides themselves: the stem, the options, the explanation and the hint must all make sense to someone who "
    "has not seen them. Never refer to a slide, diagram, figure, panel, chart, plot, table or image, and never name an "
    "example, dataset or story the way the slides do (\"the house example\", \"the robot\"). When a question needs a "
    "case, describe it fully in the stem, briefly: retell the slides' own case, or use a short new case in the same "
    "setting, so long as answering it needs only the idea the slides teach and nothing from another domain. Where the "
    "slides state a number, rule or definition, use it exactly as stated, in words. Write for a general reader: no "
    "specialist notation anywhere, not even with an explanation: no letters standing for quantities or parts of a "
    "definition (T, P and E; f; x and y), no Greek letters, subscripts, formulas or equations (Y1 - Y0, theta). Say the "
    "idea in plain words instead. Name a person's definition or a technical term only where the question still makes "
    "sense to someone who has never heard the name. Test one idea per question: the right option makes one point, not two joined together, and every wrong option "
    "is wrong as a whole, not partly true."
)
WRONG_OPTIONS = "Wrong options: each must be a plausible misconception about this idea. Never make a wrong option restate the claim the question asks the student to evaluate, never make it a true statement, and never make it merely the negation of the right answer."
SAME_LENGTH_OPTIONS = (
    "Options: the three must be about the same length and equally specific, so the right one cannot be spotted by its "
    "wording. The right option must not be the longest, the only hedged or qualified one, or the only one that explains "
    "itself; if it needs a clause, give the wrong ones a clause too. Do not give the wrong options away with absolute "
    "words (always, never, only, guaranteed, nothing, none, cannot) while the right one is measured: a student who "
    "knows how tests work rules those out without knowing the idea. Use such a word only where the idea itself is "
    "absolute, and then in the right option as readily as in a wrong one."
)
EXPLANATION_AND_HINT = (
    "The explanation and the hint are each one or two complete sentences in plain words, ending in a full stop or a "
    "question mark, with nothing after it. The hint points toward the idea without giving away the answer."
)
# what the critic adds for a pre-check question, on top of its usual checks of the key and the wrong options
PRECHECK_CRITIC_CHECKS = (
    "These are pre-lecture questions, so also check: (5) someone who has never seen the slides can understand the stem "
    "and options (no reference to a slide, figure, diagram, plot or table, and no example named the way the slides name "
    "it); (6) the keyed option does not stand out by being longer, more detailed or more hedged than the others, and the "
    "wrong options are not marked out by absolute words (always, never, only, guaranteed, nothing) that the key avoids; "
    f"(7) the stem is at most {MAX_STEM_WORDS} words; (8) the question tests one idea: the key does not bundle two "
    "points, and no wrong option is partly true; (9) a general reader could follow it without the slides: no specialist "
    "notation at all (letters standing for quantities, Greek letters, subscripts, formulas), and no term or name a "
    "newcomer could not know; (10) the explanation and the hint are clean, complete sentences with no stray "
    "characters, and the hint does not give the answer away."
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
) -> tuple[KuBankGen, list[dict]]:
    """The KU's three items and the critic's remaining flags. `material`: the KU's slides as text and image blocks."""

    def ask(extra: str) -> KuBankGen:
        return structured(
            schema=KuBankGen, content=[text_block(bank_prompt(ku, prereq_titles, material[0], extra)), *material[1]],
            system=BANK_SYSTEM, stage="item_bank", ku_id=ku.id, model=model, max_tokens=6000, manifest=manifest,
        )

    def make(extra: str) -> KuBankGen:
        g = ask(extra)
        problems = stem_problems(g)
        if problems:
            log(f"  {ku.id}: {problems} — asking again once")
            g = ask(extra + "\n\nYour previous attempt had problems. Fix them:\n" + "\n".join(f"- {p}" for p in problems))
        return g

    def describe(g: KuBankGen) -> str:
        return "\n".join(mcq_text(f"as-{ku.id}-{t}", getattr(g, t)) for t in TIERS)

    gen, flags = generate_with_critic(
        make=make, describe=describe, ids_of=lambda g: [f"as-{ku.id}-{t}" for t in TIERS], material=material,
        stage=f"bank_{ku.id}", model=critic_model, manifest=manifest, log=log, critic_checks=PRECHECK_CRITIC_CHECKS,
    )
    # anything the retry did not fix stays visible on the review sheet
    flags += [{"id": f"as-{ku.id}-{p.split(':')[0]}", "issue": p.split(': ', 1)[1]} for p in stem_problems(gen)]
    return gen, flags
