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

import sys
from pathlib import Path
from typing import Literal

from script_generation_agent.prompts import (
    DIALOGUE_MAX_WORDS,
    DIALOGUE_MIN_WORDS,
    SCRIPT_SYSTEM_PROMPT,
    build_script_prompt,
    dialogue_system_prompt,
    draw_fix_system_prompt,
    draw_segment_system_prompt,
    level_system_prompt,
    templates_brief,
)
from script_generation_agent.slang import MIN_SLANG, find_slang, lexicon_for_prompt, max_slang
from syllabyte_common.llm import DEFAULT_MODEL, image_block, structured, text_block
from pydantic import BaseModel

from syllabyte_common.models import (
    CourseCorpus,
    DialogueScript,
    KnowledgeUnit,
    RunManifest,
    Script,
    Slide,
    TemplatedDialogueScript,
)

Style = Literal["monologue", "dialogue"]
# How segments are drawn: LLM-written Manim code from each line's `visual` sentence, or the visual template
# library from each line's `draw` calls (plan/visual-template-library-plan.md; dialogue only for now).
Visuals = Literal["codegen", "templates"]

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


def validate_script(script: Script, *, min_words: int = MIN_WORDS, max_words: int = MAX_WORDS) -> list[str]:
    """Code-side checks. Returns a list of problems (empty = valid)."""
    problems: list[str] = []

    wc = script.word_count
    if not (min_words <= wc <= max_words):
        problems.append(f"word_count={wc}, expected {min_words}-{max_words}")

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


MAX_TURN_BEATS = 3
NO_SLANG_STEPS = ("objective", "check")


def validate_dialogue(script: DialogueScript) -> list[str]:
    """validate_script's checks plus the dialogue's tutoring-frame and slang rules
    (research_notes/dialogue-framework.md). Problems name segments and beats the way the prompt does."""
    problems = validate_script(script, min_words=DIALOGUE_MIN_WORDS, max_words=DIALOGUE_MAX_WORDS)
    if len(script.segments) != 5:
        return problems
    prepare, initiate, deliver1, deliver2, end = script.segments
    names = ["prepare", "initiate", "first deliver", "second deliver", "end"]
    beats = [(name, j, b) for name, seg in zip(names, script.segments) for j, b in enumerate(seg.beats, 1)]

    if prepare.beats[0].speaker != "peer":
        problems.append("the prepare segment must open with the peer's hook (speaker \"peer\")")
    if not any(b.speaker == "explainer" and b.step == "objective" for b in initiate.beats):
        problems.append("the initiate segment needs the explainer's objective line (step \"objective\")")

    # Every wrong answer is the peer's, and the explainer's very next line corrects it.
    for k, (name, j, b) in enumerate(beats):
        if not b.misconception:
            continue
        if b.speaker != "peer" or b.step != "answer":
            problems.append(f"{name} beat {j}: only the peer's answer (step \"answer\") can be a misconception")
        if name == "prepare":
            continue  # the hook's wrong intuition is corrected in a deliver segment
        # The correction comes next. One "predict" line may sit between (the viewer guesses before the reveal).
        k2 = k + 2 if k + 1 < len(beats) and beats[k + 1][2].step == "predict" else k + 1
        nxt = beats[k2][2] if k2 < len(beats) else None
        if nxt is None or nxt.speaker != "explainer" or nxt.step != "feedback":
            seg_beats = next(seg.beats for n, seg in zip(names, script.segments) if n == name)
            sequence = " -> ".join(
                f"{b2.speaker} {b2.step}{'*' if b2.misconception else ''}" for b2 in seg_beats
            )
            problems.append(
                f"{name} beat {j} is a misconception, so the next beat (or the one after a predict line) must be "
                f"the explainer's feedback (step \"feedback\") explaining why it is wrong; that segment's beats "
                f"are: {sequence}"
            )
    if not any(b.misconception for b in deliver1.beats):
        problems.append("the first deliver segment needs the peer's misconception (misconception true) and its correction")

    predicts = [(name, j, seg) for name, seg in (("first deliver", deliver1), ("second deliver", deliver2))
                for j, b in enumerate(seg.beats, 1) if b.step == "predict"]
    if len(predicts) != 1:
        problems.append(f"the deliver segments need exactly one \"predict\" line, found {len(predicts)}")
    elif predicts[0][1] == len(predicts[0][2].beats):
        problems.append(f"{predicts[0][0]}: the predict line must come before the beat that shows the answer")
    if any(b.step == "predict" for seg in (prepare, initiate, end) for b in seg.beats):
        problems.append("predict lines belong in the deliver segments")

    if not any(b.speaker == "peer" and b.step == "question" for b in deliver2.beats):
        problems.append("in the second deliver segment the peer asks at least one question (step \"question\")")
    for name, seg in (("first deliver", deliver1), ("second deliver", deliver2)):
        if {b.speaker for b in seg.beats} != {"explainer", "peer"}:
            problems.append(f"both characters must speak in the {name} segment")

    peer_check = [j for j, b in enumerate(end.beats) if b.speaker == "peer" and b.step == "check"]
    if not peer_check:
        problems.append("the end segment needs the peer restating the idea (speaker \"peer\", step \"check\")")
    elif not any(b.speaker == "explainer" for b in end.beats[peer_check[0] + 1:]):
        problems.append("in the end segment the explainer confirms the peer's restatement, after it")

    run = 1
    for k in range(1, len(beats)):
        run = run + 1 if beats[k][2].speaker == beats[k - 1][2].speaker else 1
        if run == MAX_TURN_BEATS + 1:
            name, j, b = beats[k]
            problems.append(f"{name} beat {j}: the {b.speaker} speaks more than {MAX_TURN_BEATS} beats in a row")

    slang = [(name, j, b, find_slang(b.narration)) for name, j, b in beats]
    used = sum(len(found) for *_, found in slang)
    cap = max_slang(len(beats))
    if used > cap:
        problems.append(f"{used} slang phrases for {len(beats)} beats; use at most {cap}")
    if used < MIN_SLANG:
        problems.append(f"only {used} slang phrase(s) from the list; use {MIN_SLANG}-{cap}")
    for name, j, b, found in slang:
        if found and b.step in NO_SLANG_STEPS:
            problems.append(f"{name} beat {j} is a \"{b.step}\" line, which takes no slang (found {found})")
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
    style: Style = "monologue",
    visuals: Visuals = "codegen",
) -> Script:
    """Writes the 5-segment script for `ku`. With `level` (1-3) the script is written for one student's level on this
    KU (plan/per-student-video-plan.md V1): the level shapes the language, the objective and the second deliver
    segment, and a script the code-side checks reject is rewritten once with the problems fed back. With
    style="dialogue" (which needs a level) it is a DialogueScript spoken by the cast's two characters; with
    visuals="templates" as well, each line also carries the template calls that draw it (see fix_draws)."""
    text_context, image_blocks = gather_source_material(corpus, ku)
    if not text_context:
        raise ScriptValidationError(
            f"KU {ku.id} cites slides that don't resolve in the corpus: {ku.source_refs}"
        )

    schema: type[Script] = Script
    check = validate_script
    if style == "dialogue":
        if level is None:
            raise ValueError("dialogue scripts are written for a level")
        from syllabyte_common.cast import load_cast

        cast = load_cast()
        system = dialogue_system_prompt(
            level, prereq_titles, explainer=cast.explainer.name, peer=cast.peer.name, lexicon=lexicon_for_prompt(),
        )
        schema, check = DialogueScript, validate_dialogue
        stage = f"write_dialogue_l{level}"
        if visuals == "templates":
            # The writer only learns what the templates can draw; the calls are filled in per segment after
            # (add_draws), in parallel, which is much faster than one call planning every call of every line.
            system += templates_brief()
    elif visuals == "templates":
        raise ValueError("template visuals are only built for dialogue scripts so far")
    else:
        system = SCRIPT_SYSTEM_PROMPT if level is None else level_system_prompt(level, prereq_titles)
        stage = "write_script" if level is None else f"write_script_l{level}"
    # The dialogue has more rules to meet, so one more rewrite.
    attempts = 1 if level is None else 3 if style == "dialogue" else 2
    problems: list[str] = []
    feedback = ""
    for _ in range(attempts):
        prompt = build_script_prompt(ku, text_context)
        if extra_instruction:
            prompt += f"\n\nRevision instructions from a previous review round:\n{extra_instruction}"
        if feedback:
            prompt += f"\n\n{feedback}"

        script = structured(
            schema=schema,
            content=[text_block(prompt), *image_blocks],
            system=system,
            stage=stage,
            ku_id=ku.id,
            model=model,
            # A dialogue has more beats, each with speaker/step fields: 8000 cut some off.
            max_tokens=16000 if style == "dialogue" else 8000,
            manifest=manifest,
        )

        problems = check(script)
        if not problems:
            if visuals == "templates":
                script = add_draws(script, ku_id=ku.id, model=model, manifest=manifest)
                fix_draws(script, ku_id=ku.id, model=model, manifest=manifest)
            return script
        print(f"[write_script] {ku.id}: attempt rejected: {'; '.join(problems)}", file=sys.stderr, flush=True)
        feedback = "Your previous attempt was rejected by the automatic checker: " + "; ".join(problems) + ". Fix these."

    raise ScriptValidationError(f"KU {ku.id}: {'; '.join(problems)}")


# --------------------------------------------------------------------------
# Template calls (visuals="templates")
# --------------------------------------------------------------------------


class _BeatDraw(BaseModel):
    draw: list[str]
    visual: str  # what the calls show, replacing the writer's sentence


class _Draws(BaseModel):
    beats: list[_BeatDraw]


def _script_listing(script: Script) -> str:
    out = []
    for i, seg in enumerate(script.segments):
        out.append(f"Segment {i} ({seg.phase}):")
        out += [f"  beat {k}: [{getattr(b, 'speaker', '')}] {b.narration}\n    visual: {b.visual}"
                for k, b in enumerate(seg.beats, 1)]
    return "\n".join(out)


def add_draws(script: DialogueScript, *, ku_id: str, model: str = DEFAULT_MODEL,
              manifest: RunManifest | None = None, frame: str = "dialogue",
              feedback: dict[int, list[str]] | None = None) -> TemplatedDialogueScript:
    """The script with each line's template calls, and its `visual` sentence rewritten to say what they show:
    one call per segment, all at once. A segment whose call fails gets no calls (it is drawn by LLM code);
    fix_draws then checks every segment's calls. With `feedback` (segment index -> a reviewer's issues), only
    those segments are drawn again, the others keep their calls."""
    from concurrent.futures import ThreadPoolExecutor

    head = ("Colour key: " + ", ".join(f"{t.term} = {t.colour}" for t in script.colour_key)
            + "\n\nThe whole script:\n" + _script_listing(script))
    system = draw_segment_system_prompt(frame)

    def draw(i: int) -> list[_BeatDraw] | None:
        seg = script.segments[i]
        n = len(seg.beats)
        if feedback is not None and i not in feedback:
            return None  # keep this segment as it is
        ask = f"Draw segment {i} ({seg.phase}): {n} beats, so {n} entries."
        if feedback and i in feedback:
            current = "\n".join(f"  beat {k}: {getattr(b, 'draw', [])}" for k, b in enumerate(seg.beats, 1))
            ask += (f"\nIts current calls:\n{current}\nA reviewer found these problems with its pictures; fix "
                    "them:\n" + "\n".join(f"  - {p}" for p in feedback[i]))
        try:
            out = structured(schema=_Draws, content=[text_block(f"{head}\n\n{ask}")], system=system,
                             stage="draw_segment", ku_id=ku_id, model=model, max_tokens=8000, manifest=manifest)
        except Exception as e:
            print(f"[write_script] {ku_id}: drawing segment {i} failed: {e}", file=sys.stderr, flush=True)
            return [_BeatDraw(draw=[], visual=b.visual) for b in seg.beats]
        return (out.beats + [_BeatDraw(draw=[], visual=b.visual) for b in seg.beats[len(out.beats):]])[:n]

    with ThreadPoolExecutor(max_workers=len(script.segments)) as pool:
        drawn = list(pool.map(draw, range(len(script.segments))))
    data = script.model_dump(mode="json") | {"visuals": "templates"}
    for seg, seg_drawn in zip(data["segments"], drawn):
        for beat, d in zip(seg["beats"], seg_drawn or []):
            beat["draw"] = d.draw
            if d.draw:  # a segment left to the animator keeps the writer's sentences
                beat["visual"] = d.visual
        for beat in seg["beats"]:
            beat.setdefault("draw", [])
    return TemplatedDialogueScript.model_validate(data)


class _SegmentDraws(BaseModel):
    segment_index: int
    beats: list[_BeatDraw]


class _DrawFixes(BaseModel):
    segments: list[_SegmentDraws]


def draw_problems(script: Script) -> dict[int, list[str]]:
    """Segment index -> what animation_agent.visuals.calls.check_segment found in its calls (segments without
    calls, which are drawn by LLM code, are skipped)."""
    from animation_agent.visuals.calls import check_segment, segment_draws

    out = {}
    for i, seg in enumerate(script.segments):
        draws = segment_draws(seg)
        if draws is not None and (problems := check_segment(draws)):
            out[i] = problems
    return out


def fix_draws(script: Script, *, ku_id: str, model: str = DEFAULT_MODEL, manifest: RunManifest | None = None,
              frame: str = "dialogue") -> dict[int, list[str]]:
    """Checks the script's template calls and, if some segments have problems, asks for corrected calls for just
    those segments, once (a small call: far cheaper than rewriting the script, whose lines already passed). A
    segment still wrong after that has its calls removed, so it is drawn by LLM code from its `visual` text.
    Edits `script` in place and returns the problems left in the segments it emptied."""
    problems = draw_problems(script)
    if not problems:
        return {}
    print(f"[write_script] {ku_id}: fixing template calls in segments {sorted(problems)}: "
          f"{'; '.join(p for ps in problems.values() for p in ps)[:600]}", file=sys.stderr, flush=True)
    listing = []
    for i, ps in problems.items():
        seg = script.segments[i]
        beats = "\n".join(
            f"    beat {k}: [{getattr(b, 'speaker', '')}] {b.narration}\n      visual: {b.visual}\n      draw: {b.draw}"
            for k, b in enumerate(seg.beats, 1)
        )
        listing.append(f"Segment {i} ({seg.phase}), {len(seg.beats)} beats:\n{beats}\n  Problems:\n"
                       + "\n".join(f"    - {p}" for p in ps))
    try:
        fixes = structured(
            schema=_DrawFixes,
            content=[text_block("Colour key: " + ", ".join(f"{t.term} = {t.colour}" for t in script.colour_key)
                                + "\n\n" + "\n\n".join(listing))],
            system=draw_fix_system_prompt(frame), stage="fix_draws", ku_id=ku_id, model=model, max_tokens=6000,
            manifest=manifest,
        )
        for fix in fixes.segments:
            seg = script.segments[fix.segment_index] if fix.segment_index in problems else None
            if seg is not None and len(fix.beats) == len(seg.beats):
                for beat, d in zip(seg.beats, fix.beats):
                    beat.draw, beat.visual = d.draw, d.visual
    except Exception as e:  # the fix is best-effort: the segments fall back to LLM code below
        print(f"[write_script] {ku_id}: fixing template calls failed: {e}", file=sys.stderr, flush=True)
    left = draw_problems(script)
    for i in left:
        for beat in script.segments[i].beats:
            beat.draw = []
    if left:
        print(f"[write_script] {ku_id}: segments {sorted(left)} will be drawn by LLM code: "
              f"{'; '.join(p for ps in left.values() for p in ps)[:600]}", file=sys.stderr, flush=True)
    return left
