"""
Writing multiple-choice items with an LLM, and the critic pass that checks them against the slides. Shared by the
dev course's fixture scripts (scripts/build_ui_fixtures.py, scripts/build_item_bank.py) and the upload worker
(plan/slide-uploads-plan.md), which writes each uploaded deck's item bank.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel
from syllabyte_common.learner import MCQ
from syllabyte_common.llm import image_block, structured, text_block
from syllabyte_common.models import RunManifest, Slide

ITEM_SYSTEM = """You write short multiple-choice questions for a university course's micro-learning app. Students see one question at a time on a phone.

Rules:
- Ground every question ONLY in the supplied slides and narration. Never use outside facts.
- Exactly 3 options. Exactly one is correct. The two wrong options must be plausible (a common misconception) but clearly wrong given the material. Never use "all of the above" or "none of the above".
- The stem is concise and self-contained; include the data and assumptions needed to answer. Do not say "according to the slide" or "in the video".
- Vary which option is correct (correct_index 0, 1 and 2 should all appear across a batch).
- explanation: one or two plain sentences saying why the right option is right.
- hint: a nudge toward the idea that does not reveal the answer, or null.
- difficulty_prior: your estimate on a logit scale, -2 (very easy) to 2 (hard); 0 is medium.
- Preserve standard CS and mathematical notation: variables, Greek letters, quantifiers, equations, subscripts and complexity notation are allowed. Use readable Unicode or unambiguous plain text, e.g. x², λ, ∀x, O(n log n), (a + b)/c. Do not emit LaTeX commands or dollar-delimited math: the app displays text notation.
- Format code with single backticks for inline code or fenced triple-backtick blocks with a language name and newlines for multiline code. Preserve indentation. Never execute code. State the language/version or pseudocode conventions when the answer depends on them.
- Define problem-specific symbols, domains, dimensions, units and assumptions when needed, without defining the concept the question tests. Supply a matrix, graph edge list or data table as a small fenced text block when needed; never refer to an absent diagram.
- Keep options concise and comparable in specificity; formulas and code may differ in length without giving away the answer."""


class Verdict(BaseModel):
    id: str
    ok: bool
    issue: str = ""


class Verdicts(BaseModel):
    verdicts: list[Verdict]


CRITIC_SYSTEM = """You check quiz items and factual claims against course material. Be strict but fair.
For every item verify: (1) the keyed answer is correct according to the material; (2) no other option is also defensible; (3) the wrong options are not secretly correct; (4) the stem is self-contained and unambiguous.
For every claim verify it is a statement the cited narration actually makes and the slides support, with no added facts.
For CS and math, verify calculations, signs, units, domains, matrix dimensions, quantifier scope, boundary cases, and code semantics as applicable. Ensure exactly one option is correct: reject equivalent formulas or answers differing only by formatting. Do not reject an option just because its formula is longer or it uses a necessary quantifier/negation. Flag a wording cue only when it actually reveals the answer. Reject undefined problem-specific symbols or ambiguous code behavior, but allow standard notation for the knowledge being tested.
Return one verdict per id. Set ok=false only for a real problem and say what it is in one sentence."""


def slides_material(slides: list[Slide]) -> tuple[str, list[dict]]:
    """The slides' text, labelled by number, and their images as content blocks (each slide once)."""
    parts, images, seen = [], [], set()
    for slide in slides:
        if slide.slide_number in seen:
            continue
        seen.add(slide.slide_number)
        parts.append(f"[slide {slide.slide_number}]\n{slide.text}")
        if slide.image_path and Path(slide.image_path).exists():
            images.append(image_block(slide.image_path))
    return "\n\n".join(parts), images


def critic_pass(
    items_text: str, material_text: str, images: list[dict], ids: list[str], *, stage: str, model: str, manifest: RunManifest, checks: str = "",
) -> list[Verdict]:
    """`checks`: more for the critic to verify on these items, after its usual ones."""
    prompt = (
        f"Course material (slides):\n{material_text}\n\nItems and claims to check "
        f"(ids: {', '.join(ids)}):\n{items_text}"
    )
    result = structured(
        schema=Verdicts, content=[text_block(prompt), *images], system=CRITIC_SYSTEM + (f"\n{checks}" if checks else ""),
        stage=stage, model=model, max_tokens=4000, manifest=manifest,
    )
    return result.verdicts


def mcq_text(id_: str, m: MCQ) -> str:
    opts = "\n".join(f"   {'ABC'[i]}. {o}{'  <-- keyed' if i == m.correct_index else ''}" for i, o in enumerate(m.options))
    hint = getattr(m, "hint", None)
    return f"[{id_}] {m.stem}\n{opts}\n   explanation: {m.explanation}" + (f"\n   hint: {hint}" if hint else "")


def generate_with_critic(
    *, make, describe, ids_of, material: tuple[str, list[dict]], stage: str, model: str, manifest: RunManifest,
    log: Callable[[str], None] = print, critic_checks: str = "", require_all_verdicts: bool = False,
):
    """make(extra) -> generated; describe(gen) -> text for the critic; ids_of(gen) -> ids; critic_checks: see
    `critic_pass`. Returns (gen, remaining_flags)."""
    def review(gen, suffix):
        ids = ids_of(gen)
        verdicts = critic_pass(describe(gen), material[0], material[1], ids, stage=f"{stage}_{suffix}", model=model, manifest=manifest, checks=critic_checks)
        bad = [v for v in verdicts if not v.ok]
        if require_all_verdicts:
            for id_ in ids:
                if sum(v.id == id_ for v in verdicts) != 1:
                    bad.append(Verdict(id=id_, ok=False, issue="The reviewer must return exactly one verdict for this question."))
            if any(v.id not in ids for v in verdicts):
                bad.append(Verdict(id=ids[0], ok=False, issue="The review contains an unknown question ID."))
        return bad

    gen = make("")
    bad = review(gen, "critic")
    if bad:
        log(f"  {stage}: critic objected to {[v.id for v in bad]} — regenerating once")
        feedback = "\n\nA reviewer found problems in your previous attempt. Fix them:\n" + "\n".join(f"- {v.id}: {v.issue}" for v in bad)
        gen = make(feedback)
        bad = review(gen, "critic2")
    return gen, [{"id": v.id, "issue": v.issue} for v in bad]
