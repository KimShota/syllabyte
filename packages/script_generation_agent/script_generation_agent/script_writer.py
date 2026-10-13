"""
Script writing — Component 3 (Script Generation Agent), Week-1 scope.

Gathers the specific slides a Knowledge Unit cites (text + rendered PNG, if
available) as the ONLY grounding material, then calls Claude for a
structured Script. Hard, code-side checks run before the LLM critic ever
sees the output — cheap, deterministic checks catch cheap, deterministic
mistakes (wrong word count, missing refs, overlong beats) without
spending an extra LLM call.
"""

from __future__ import annotations

from pathlib import Path

from script_generation_agent.prompts import SCRIPT_SYSTEM_PROMPT, build_script_prompt, level_system_prompt
from syllabyte_common.llm import DEFAULT_MODEL, image_block, structured, text_block
from syllabyte_common.models import CourseCorpus, KnowledgeUnit, RunManifest, Script, Slide

MIN_WORDS = 150
MAX_WORDS = 220
# The prompt asks for <=25; the slack avoids rejecting a whole script (and
# crashing the run) over one slightly long sentence.
MAX_BEAT_WORDS = 32


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


MAX_KEY_TERMS = 4


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

    colours = [t.colour for t in script.colour_key]
    terms = [t.term.strip().lower() for t in script.colour_key]
    if len(script.colour_key) > MAX_KEY_TERMS:
        problems.append(f"colour_key has {len(script.colour_key)} terms, max {MAX_KEY_TERMS}")
    if len(set(colours)) != len(colours):
        problems.append(f"colour_key gives two terms the same colour: {colours}")
    if len(set(terms)) != len(terms):
        problems.append(f"colour_key lists a term twice: {terms}")

    for i, seg in enumerate(script.segments):
        if not seg.source_refs:
            problems.append(f"segment {i} ({seg.phase}) has no source_refs")
        # `beats` (>=1 entry) is already enforced by Segment's Pydantic
        # min_length; check each beat is one short sentence with a visual.
        for j, beat in enumerate(seg.beats, 1):
            words = len(beat.narration.split())
            if words > MAX_BEAT_WORDS:
                problems.append(
                    f"segment {i} ({seg.phase}) beat {j} has {words} words, "
                    f"max {MAX_BEAT_WORDS} (one sentence per beat)"
                )
            if not beat.visual.strip():
                problems.append(f"segment {i} ({seg.phase}) beat {j} has no visual")

    return problems


def write_script(
    ku: KnowledgeUnit,
    corpus: CourseCorpus,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
    extra_instruction: str = "",
    level: int | None = None,
    prereq_titles: list[str] | None = None,
) -> Script:
    """Writes the 5-segment script for `ku`. With `level` (1-3) the script is written for one student's level on this
    KU (plan/per-student-video-plan.md V1): the level shapes the language, the objective and the second deliver
    segment, and a script the code-side checks reject is rewritten once with the problems fed back."""
    text_context, image_blocks = gather_source_material(corpus, ku)
    if not text_context:
        raise ScriptValidationError(
            f"KU {ku.id} cites slides that don't resolve in the corpus: {ku.source_refs}"
        )

    system = SCRIPT_SYSTEM_PROMPT if level is None else level_system_prompt(level, prereq_titles)
    stage = "write_script" if level is None else f"write_script_l{level}"
    attempts = 1 if level is None else 2
    problems: list[str] = []
    feedback = ""
    for _ in range(attempts):
        prompt = build_script_prompt(ku, text_context)
        if extra_instruction:
            prompt += f"\n\nRevision instructions from a previous review round:\n{extra_instruction}"
        if feedback:
            prompt += f"\n\n{feedback}"

        script = structured(
            schema=Script,
            content=[text_block(prompt), *image_blocks],
            system=system,
            stage=stage,
            ku_id=ku.id,
            model=model,
            max_tokens=8000,
            manifest=manifest,
        )

        problems = validate_script(script)
        if not problems:
            return script
        feedback = "Your previous attempt was rejected by the automatic checker: " + "; ".join(problems) + ". Fix these."

    raise ScriptValidationError(f"KU {ku.id}: {'; '.join(problems)}")
