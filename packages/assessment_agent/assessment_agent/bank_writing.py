"""
Writing one KU's three bank items (plan/per-ku-profiling-plan.md D4) with an LLM, checked by the critic. Used by
scripts/build_item_bank.py for the dev course and by the upload worker for each uploaded deck
(plan/slide-uploads-plan.md); assessment_agent/bank.py turns the result into `Item`s.
"""

from __future__ import annotations

from collections.abc import Callable

from syllabyte_common.llm import structured, text_block
from syllabyte_common.models import KnowledgeUnit, RunManifest

from assessment_agent.bank import TIER_BLOOM, TIERS, KuBankGen, stem_problems
from assessment_agent.item_writing import ITEM_SYSTEM, generate_with_critic, mcq_text

_STEM_RULE = "- The stem is one sentence, under 28 words, and self-contained."
assert _STEM_RULE in ITEM_SYSTEM, "item_writing.ITEM_SYSTEM changed; update the stem rule here"
_NEW_STEM_RULE = (
    "- The stem is self-contained and under 40 words. If it sets up a situation or states a claim, the question comes "
    "after it, and it always ends with a question mark."
)
BANK_SYSTEM = "\n".join(
    l.replace(_STEM_RULE, _NEW_STEM_RULE)  # keeps what follows on the line: "Do not say 'according to the slide'…"
    for l in ITEM_SYSTEM.splitlines()
    if not l.startswith("- difficulty_prior")
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

- basic: one fact, definition or label from the slides.
- applied: handle a new case in the slides' own setting: classify it, compute with it, or read it. It must need more than the basic question's lookup, and must not be the same lookup with another value.
- advanced: judge a claim or design, spot what is wrong with an argument, or predict what changes when a condition changes. Vary the shape across units; do not always open with "A colleague claims".
The three tiers must call for different kinds of thinking, not just different wording, and must be independent: answering one must not give away another, and none may reuse another's wording or options.

Stay inside the slides. Every question, including the advanced one, must be answerable from the slides below alone. Use the slides' own example, people, data and notation; you may change the numbers or ask about another case in that same setting, but never bring in an analogy, example or fact from another domain. Where the slides state a number or a rule, use it exactly as stated. In the explanation and hint, describe a chart or table only as far as its text or image shows.

Wrong options: each must be a plausible misconception about this idea. Never make a wrong option restate the claim the question asks the student to evaluate, never make it a true statement, and never make it merely the negation of the right answer.

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
        stage=f"bank_{ku.id}", model=critic_model, manifest=manifest, log=log,
    )
    # anything the retry did not fix stays visible on the review sheet
    flags += [{"id": f"as-{ku.id}-{p.split(':')[0]}", "issue": p.split(': ', 1)[1]} for p in stem_problems(gen)]
    return gen, flags
