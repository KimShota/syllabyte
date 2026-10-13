"""
Level-aware script writing (plan/per-student-video-plan.md V1).

A video is four segments every viewer sees (hook, objective, core idea, recap: the BASE) plus ONE worked-example
segment that depends on the viewer's level for that KU. The base is written once per KU; the example is written per
level against it, and `compose` slots the example between the core idea and the recap to give the usual 5-segment
`Script`. Because the base is one object, the shared segments are identical across levels by construction, so the
animations made for them are reused across levels and across students (the renderer caches by segment content).

    Level 1  a recap of what the idea builds on, then a full step-by-step worked example
    Level 2  one worked example, key steps only
    Level 3  no example: a "what if" question and the reasoning through it

The code-side checks run before any critic call, and a rejected piece is retried once with the specific problems
fed back, so a cheap deterministic mistake costs one more call, not a failed video.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel
from syllabyte_common.llm import DEFAULT_MODEL, structured, text_block
from syllabyte_common.models import CourseCorpus, CritiqueResult, KnowledgeUnit, RunManifest, Script, Segment

from script_generation_agent.critic import CRITIQUE_THRESHOLD, MAX_ROUNDS, critique
from script_generation_agent.prompts import (
    BASE_SYSTEM_PROMPT,
    BASE_WORDS,
    EXAMPLE_WORDS,
    build_base_prompt,
    build_example_prompt,
    example_system_prompt,
)
from script_generation_agent.script_writer import (
    MAX_BEAT_WORDS,
    ScriptValidationError,
    gather_source_material,
    validate_script,
)

Level = Literal[1, 2, 3]
LEVELS: tuple[Level, ...] = (1, 2, 3)
BASE_PHASES = ["prepare", "initiate", "deliver", "end"]
# Where the example goes in the composed script: after the core idea (index 2), before the recap.
EXAMPLE_INDEX = 3
# The prompts give a range; the checker accepts a little outside it so one slightly long sentence does not reject a script.
WORD_SLACK = 0.12


class BaseScript(BaseModel):
    """The four segments every viewer sees: prepare, initiate, deliver (the core idea), end (the recap)."""

    ku_id: str
    title: str
    segments: list[Segment]

    @property
    def word_count(self) -> int:
        return sum(len(s.narration.split()) for s in self.segments)


def _bounds(rng: tuple[int, int]) -> tuple[int, int]:
    lo, hi = rng
    return int(lo * (1 - WORD_SLACK)), round(hi * (1 + WORD_SLACK))


def _segment_problems(seg: Segment, label: str) -> list[str]:
    problems: list[str] = []
    if not seg.source_refs:
        problems.append(f"{label} has no source_refs")
    for j, beat in enumerate(seg.beats, 1):
        words = len(beat.narration.split())
        if words > MAX_BEAT_WORDS:
            problems.append(f"{label} beat {j} has {words} words, max {MAX_BEAT_WORDS} (one sentence per beat)")
        if not beat.visual.strip():
            problems.append(f"{label} beat {j} has no visual")
    return problems


def validate_base(base: BaseScript) -> list[str]:
    problems: list[str] = []
    phases = [s.phase for s in base.segments]
    if phases != BASE_PHASES:
        problems.append(f"phase order {phases} != expected {BASE_PHASES}")
    lo, hi = _bounds(BASE_WORDS)
    if not lo <= base.word_count <= hi:
        problems.append(f"base word_count={base.word_count}, expected {BASE_WORDS[0]}-{BASE_WORDS[1]}")
    for i, seg in enumerate(base.segments):
        problems += _segment_problems(seg, f"segment {i} ({seg.phase})")
    return problems


def validate_example(seg: Segment, level: Level) -> list[str]:
    problems: list[str] = []
    if seg.phase != "deliver":
        problems.append(f"the example segment must have phase 'deliver', got '{seg.phase}'")
    if not 3 <= len(seg.beats) <= 5:
        problems.append(f"the example segment has {len(seg.beats)} beats, expected 3 to 5")
    lo, hi = _bounds(EXAMPLE_WORDS[level])
    words = len(seg.narration.split())
    if not lo <= words <= hi:
        problems.append(f"the example segment has {words} words, expected {EXAMPLE_WORDS[level][0]}-{EXAMPLE_WORDS[level][1]}")
    return problems + _segment_problems(seg, "the example segment")


def compose(base: BaseScript, example: Segment) -> Script:
    """The usual 5-segment script: prepare, initiate, deliver (core idea), deliver (the example), end."""
    segs = list(base.segments)
    return Script(ku_id=base.ku_id, title=base.title, segments=[*segs[:EXAMPLE_INDEX], example, *segs[EXAMPLE_INDEX:]])


def _with_retry(make: Callable[[str], object], validate: Callable[[object], list[str]], what: str, attempts: int = 2):
    """make(extra_instruction) -> object; retry once with the checker's complaints fed back."""
    extra = ""
    problems: list[str] = []
    for _ in range(attempts):
        obj = make(extra)
        problems = validate(obj)
        if not problems:
            return obj
        extra = "Your previous attempt was rejected: " + "; ".join(problems) + ". Fix these in the new version."
    raise ScriptValidationError(f"{what}: {'; '.join(problems)}")


def write_base_script(
    ku: KnowledgeUnit, corpus: CourseCorpus, *, model: str = DEFAULT_MODEL, manifest: RunManifest | None = None,
    extra_instruction: str = "",
) -> BaseScript:
    text_context, image_blocks = gather_source_material(corpus, ku)
    if not text_context:
        raise ScriptValidationError(f"KU {ku.id} cites slides that don't resolve in the corpus: {ku.source_refs}")

    def make(extra: str) -> BaseScript:
        prompt = build_base_prompt(ku, text_context)
        if extra or extra_instruction:
            prompt += f"\n\nRevision instructions:\n{extra or extra_instruction}"
        return structured(
            schema=BaseScript, content=[text_block(prompt), *image_blocks], system=BASE_SYSTEM_PROMPT,
            stage="write_base_script", ku_id=ku.id, model=model, max_tokens=8000, manifest=manifest,
        )

    return _with_retry(make, validate_base, f"KU {ku.id} base script")  # type: ignore[return-value]


def write_example(
    ku: KnowledgeUnit, base: BaseScript, level: Level, corpus: CourseCorpus, *, prereq_titles: list[str] | None = None,
    model: str = DEFAULT_MODEL, manifest: RunManifest | None = None, extra_instruction: str = "",
) -> Segment:
    text_context, image_blocks = gather_source_material(corpus, ku)
    base_json = base.model_dump_json(indent=2)

    def make(extra: str) -> Segment:
        prompt = build_example_prompt(ku, base_json, text_context, level, prereq_titles or [])
        if extra or extra_instruction:
            prompt += f"\n\nRevision instructions:\n{extra or extra_instruction}"
        return structured(
            schema=Segment, content=[text_block(prompt), *image_blocks], system=example_system_prompt(level),
            stage=f"write_example_l{level}", ku_id=ku.id, model=model, max_tokens=4000, manifest=manifest,
        )

    return _with_retry(make, lambda seg: validate_example(seg, level), f"KU {ku.id} level {level} example")  # type: ignore[arg-type,return-value]


def write_leveled_script(
    ku: KnowledgeUnit, corpus: CourseCorpus, level: Level, *, base: BaseScript | None = None,
    prereq_titles: list[str] | None = None, model: str = DEFAULT_MODEL, manifest: RunManifest | None = None,
    skip_critic: bool = False,
) -> tuple[Script, BaseScript, CritiqueResult]:
    """The script for `ku` at `level`, plus the base it was built on (pass it back in for the other levels).

    The critic scores the composed script; if it falls below threshold only the example is rewritten, since the base
    is shared and was already accepted.
    """
    base = base or write_base_script(ku, corpus, model=model, manifest=manifest)
    result = CritiqueResult(ku_id=ku.id)
    extra = ""
    script: Script | None = None
    for round_num in range(1, MAX_ROUNDS + 1):
        example = write_example(ku, base, level, corpus, prereq_titles=prereq_titles, model=model, manifest=manifest, extra_instruction=extra)
        script = compose(base, example)
        problems = validate_script(script)
        if problems:
            raise ScriptValidationError(f"KU {ku.id} level {level}: {'; '.join(problems)}")
        if skip_critic:
            result.passed = True
            return script, base, result
        score = critique(script, corpus, ku, model=model, manifest=manifest)
        result.rounds.append(score)
        if score.min_score >= CRITIQUE_THRESHOLD:
            result.passed = True
            return script, base, result
        extra = "The previous version scored below threshold. Issues found:\n" + "\n".join(f"- {i}" for i in score.issues) + "\nFix these in the example segment."
    assert script is not None
    return script, base, result


if __name__ == "__main__":
    import argparse
    import time
    from pathlib import Path

    from syllabyte_common.llm import PRICE_PER_MTOK
    from syllabyte_common.models import KUList

    parser = argparse.ArgumentParser(description="Write one KU's script at several levels (spends LLM credits).")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--kus", required=True)
    parser.add_argument("--ku-id", required=True)
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--skip-critic", action="store_true")
    args = parser.parse_args()

    corpus = CourseCorpus.model_validate_json(Path(args.corpus).read_text())
    kus = KUList.model_validate_json(Path(args.kus).read_text()).knowledge_units
    ku = next(k for k in kus if k.id == args.ku_id)
    titles = [k.title for k in kus if k.id in ku.prerequisites]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest = RunManifest(run_id="leveled-cli")
    base: BaseScript | None = None
    for level in args.levels:
        t0 = time.monotonic()
        script, base, crit = write_leveled_script(ku, corpus, level, base=base, prereq_titles=titles, model=args.model, manifest=manifest, skip_critic=args.skip_critic)  # type: ignore[arg-type]
        (out / "base.json").write_text(base.model_dump_json(indent=2))
        (out / f"script.L{level}.json").write_text(script.model_dump_json(indent=2))
        (out / f"critique.L{level}.json").write_text(crit.model_dump_json(indent=2))
        print(f"level {level}: {script.word_count} words, passed={crit.passed}, {time.monotonic() - t0:.0f}s")
    print(f"LLM cost ≈ ${manifest.total_cost_usd(PRICE_PER_MTOK):.2f}")
