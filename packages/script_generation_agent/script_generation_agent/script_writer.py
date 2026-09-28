"""
Script writing — Component 3 (Script Generation Agent), Week-1 scope.

Gathers the specific slides a Knowledge Unit cites (text + rendered PNG, if
available) as the ONLY grounding material, then calls Claude for a
structured Script. Hard, code-side checks run before the LLM critic ever
sees the output — cheap, deterministic checks catch cheap, deterministic
mistakes (wrong word count, missing refs, invalid visual kind) without
spending an extra LLM call.
"""

from __future__ import annotations

from pathlib import Path

from script_generation_agent.prompts import (
    ALLOWED_VISUAL_KINDS,
    SCRIPT_SYSTEM_PROMPT,
    build_script_prompt,
)
from syllabyte_common.llm import DEFAULT_MODEL, image_block, structured, text_block
from syllabyte_common.models import CourseCorpus, KnowledgeUnit, RunManifest, Script, Slide

MIN_WORDS = 150
MAX_WORDS = 220


class ScriptValidationError(Exception):
    pass


def gather_source_material(corpus: CourseCorpus, ku: KnowledgeUnit) -> tuple[str, list[dict]]:
    """Returns (text_context, image_blocks) for every slide the KU cites."""
    text_parts: list[str] = []
    image_blocks: list[dict] = []
    seen: set[tuple[str, int]] = set()

    for ref in ku.source_refs:
        key = (ref.deck_name, ref.slide_number)
        if key in seen:
            continue
        seen.add(key)
        slide: Slide | None = corpus.slide_by_ref(ref.deck_name, ref.slide_number)
        if slide is None:
            continue
        text_parts.append(
            f"[{ref.deck_name} — slide {ref.slide_number}]\n{slide.text}"
            + (f"\n(notes: {slide.notes})" if slide.notes else "")
        )
        if slide.image_path and Path(slide.image_path).exists():
            image_blocks.append(image_block(slide.image_path))

    return "\n\n".join(text_parts), image_blocks


def validate_script(script: Script) -> list[str]:
    """Code-side checks. Returns a list of problems (empty = valid)."""
    problems: list[str] = []

    wc = script.word_count
    if not (MIN_WORDS <= wc <= MAX_WORDS):
        problems.append(f"word_count={wc}, expected {MIN_WORDS}-{MAX_WORDS}")

    if len(script.segments) != 5:
        problems.append(f"expected 5 segments, got {len(script.segments)}")

    expected_phases = ["prepare", "initiate", "deliver", "deliver", "end"]
    actual_phases = [s.phase for s in script.segments]
    if actual_phases != expected_phases:
        problems.append(f"phase order {actual_phases} != expected {expected_phases}")

    for i, seg in enumerate(script.segments):
        if not seg.source_refs:
            problems.append(f"segment {i} ({seg.phase}) has no source_refs")
        if seg.visual.kind not in ALLOWED_VISUAL_KINDS:
            problems.append(f"segment {i} has invalid visual.kind={seg.visual.kind!r}")
        if seg.visual.kind in ("diagram", "compare", "code") and not seg.visual.animation_steps:
            problems.append(
                f"segment {i} has visual.kind={seg.visual.kind!r} but no "
                "visual.animation_steps (required — see system prompt)"
            )

    return problems


def write_script(
    ku: KnowledgeUnit,
    corpus: CourseCorpus,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
    extra_instruction: str = "",
) -> Script:
    text_context, image_blocks = gather_source_material(corpus, ku)
    if not text_context:
        raise ScriptValidationError(
            f"KU {ku.id} cites slides that don't resolve in the corpus: {ku.source_refs}"
        )

    prompt = build_script_prompt(ku, text_context)
    if extra_instruction:
        prompt += f"\n\nRevision instructions from a previous review round:\n{extra_instruction}"

    content = [text_block(prompt), *image_blocks]

    script = structured(
        schema=Script,
        content=content,
        system=SCRIPT_SYSTEM_PROMPT,
        stage="write_script",
        ku_id=ku.id,
        model=model,
        max_tokens=8000,
        manifest=manifest,
    )

    problems = validate_script(script)
    if problems:
        raise ScriptValidationError(f"KU {ku.id}: {'; '.join(problems)}")

    return script
