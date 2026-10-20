"""
One question on one KU at one tier, written when a student's check needs it (plan/slide-uploads-plan.md V4) and
checked by the critic, the same way a bank's three are (bank_writing.py). It is saved by the server and reused by any
later student with the same slides who has not seen it, so the prompt names the questions already written on the KU
and asks for a different one.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel
from syllabyte_common.learner import Item, ItemTier
from syllabyte_common.llm import structured, text_block
from syllabyte_common.models import KnowledgeUnit, RunManifest, SlideRef

from assessment_agent.bank import TIER_BLOOM, TIERS, BankMCQ
from assessment_agent.bank_writing import BANK_SYSTEM, STAY_IN_SLIDES, TIER_TASKS, WRONG_OPTIONS
from assessment_agent.item_writing import generate_with_critic, mcq_text


class QuestionGen(BaseModel):
    question: BankMCQ
    slides: list[int]


def question_prompt(ku: KnowledgeUnit, prereq_titles: list[str], tier: ItemTier, slide_text: str, avoid: list[str], extra: str = "") -> str:
    prereq = "; ".join(prereq_titles) if prereq_titles else "none"
    written = "\n".join(f"- {s}" for s in avoid) if avoid else "(none yet)"
    return f"""Knowledge unit: {ku.title}
Summary: {ku.summary}
Bloom level the course analysis gave this unit: {ku.bloom_level}
It builds on: {prereq}

Write ONE question about this knowledge unit for a check of what a student already knows, at the {tier} tier ({TIER_BLOOM[tier]}):
{TIER_TASKS[tier]}

Questions already written on this unit (at any tier). Yours must ask about something else or in another way, and must not reuse their wording or options:
{written}

{STAY_IN_SLIDES}

{WRONG_OPTIONS}

Set `slides` to the slide numbers that support the question.

Slides (text and images follow):
{slide_text}{extra}"""


def write_question(
    ku: KnowledgeUnit,
    prereq_titles: list[str],
    tier: ItemTier,
    material: tuple[str, list[dict]],
    *,
    avoid: list[str],
    model: str,
    critic_model: str,
    manifest: RunManifest,
    log: Callable[[str], None] = print,
) -> tuple[QuestionGen, list[dict]]:
    """The question and the critic's remaining flags. `material`: the KU's slides as text and image blocks."""
    qid = f"{ku.id}-{tier}"

    def ask(extra: str) -> QuestionGen:
        return structured(
            schema=QuestionGen, content=[text_block(question_prompt(ku, prereq_titles, tier, material[0], avoid, extra)), *material[1]],
            system=BANK_SYSTEM, stage="question", ku_id=ku.id, model=model, max_tokens=3000, manifest=manifest,
        )

    def make(extra: str) -> QuestionGen:
        g = ask(extra)
        if not g.question.stem.strip().endswith("?"):
            log(f"  {qid}: the stem is not a question — asking again once")
            g = ask(extra + "\n\nYour previous attempt had a problem. Fix it:\n- the stem must end with a question that tells the student what to do")
        return g

    gen, flags = generate_with_critic(
        make=make, describe=lambda g: mcq_text(qid, g.question), ids_of=lambda g: [qid], material=material,
        stage=f"question_{qid}", model=critic_model, manifest=manifest, log=log,
    )
    if not gen.question.stem.strip().endswith("?"):
        flags.append({"id": qid, "issue": "the stem must end with a question that tells the student what to do"})
    return gen, flags


def question_item(item_id: str, ku_id: str, tier: ItemTier, gen: QuestionGen, *, beta: float, target_index: int, deck_name: str) -> Item:
    """The saved question: difficulty from the KU's tier, the keyed answer moved to `target_index` so answers spread
    over A/B/C across a course (as `balance_positions` does for a bank)."""
    m = gen.question
    options, c = list(m.options), m.correct_index
    t = target_index % len(options)
    options[c], options[t] = options[t], options[c]
    return Item(
        id=item_id, ku_id=ku_id, topic_id="", context="assessment", stem=m.stem, options=options, correct_index=t,
        allows_not_sure=True, explanation=m.explanation, hint=m.hint, difficulty_prior=beta, discrimination=1.0, tier=tier,
        source_refs=[SlideRef(deck_name=deck_name, slide_number=n) for n in gen.slides],
    )


__all__ = ["TIERS", "QuestionGen", "question_item", "question_prompt", "write_question"]
