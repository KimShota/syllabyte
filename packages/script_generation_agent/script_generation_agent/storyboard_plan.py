"""
Plan, then write: the storyboard in two calls, the pictures first and the lines to them.

In one call the writer decided the picture and wrote the lines at once, and what the critic marked down most was
its plan of the picture: parts the lines name never drawn (the reward and the next state of a loop, r and theta of
a polar point), a trajectory drawn as a 3-box loop and then mostly cleared, every bar lit during a question
(runs/general-3, runs/modules-1). Educational-video work that plans before it writes (Code2Video: planner, coder,
critic) reports large gains over writing directly, and so did our own bisection run once code planned its steps
(visual alignment 3 -> 5). So:

  1. The planner (one call) sees the KU, its slides, the beat plan (who speaks and what each line does, not its
     words), the drawing rules, the kind's module and the template cards. For every beat it writes the template
     calls and, in a few words, the point its line will make. It owns the title and the colour key.
  2. Code settles that picture as it will render: the traced example's steps, the reveals held back, normalize,
     one fix call, broken calls dropped (storyboard.settle_picture, with the points standing in for the lines).
     Then it computes what each beat's picture shows, in words.
  3. The writer (one call) sees the dialogue rules, the casual phrases, each beat's word range, and under each
     beat what its picture shows and the planner's point, and writes only the lines. A draft the dialogue checks
     reject is written once more with their findings.
  4. As before: the lines are matched to the picture (match_lines), the voices start, and each beat's visual is
     written from its calls.

The default since 2026-11-07 (write_storyboard; SYLLABYTE_STORYBOARD=one_call for the one call): on 12 KUs it
scored level or better (coherence 5.67 -> 6.25, visual alignment 4.58 -> 4.83), on seven data-structure KUs clearly
better (visual alignment 4.14 -> 5.00, five up and none down; Dijkstra's lines now say the computed distances).
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field, create_model

from script_generation_agent.prompts import (
    _DIALOGUE_INTRO,
    _DIALOGUE_LEVEL_RULES,
    _STORYBOARD_DRAWING,
    _STORYBOARD_SLANG,
    LEVEL_BRIEF,
    SHARED_RUBRIC,
    build_script_prompt,
    picture_brief,
)
from syllabyte_common.llm import structured, text_block
from syllabyte_common.models import KnowledgeUnit, SlideRef, TemplatedDialogueScript, TermColour

PLAN_STAGE = "storyboard_plan"
WRITE_STAGE = "storyboard_write"

# --------------------------------------------------------------------------
# The planner
# --------------------------------------------------------------------------

_PLAN_INTRO = """\
You are the picture planner of SyllaByte, which makes 70-100 second educational dialogue videos (vertical, \
9:16) in computer science and mathematics, grounded ONLY in the professor's own slides. You plan what the viewer \
sees; a second writer then writes the two characters' lines to say what your pictures show. So the pictures carry \
the lesson: a part of the idea you don't draw can't be pointed at, and a picture that changes with nothing to say \
about it is noise.

"""

_PLAN_TASK = """\
The tutoring plan is fixed: each beat in the schema is one line, named for its speaker and its step (e.g. \
b3_explainer_feedback), and its description says what that line does. {explainer} explains; {peer} is a classmate \
learning it, sometimes wrong. For every beat, in order, write:
  - `draw`: the template calls that draw what the viewer sees during that line;
  - `point`: in at most 15 plain words, what the line will say about that picture (the writer turns it into the \
character's words). Name the values and parts as the picture shows them.
Plan the whole video before the first call:
  - Pick the example from the slides (its real numbers, its real size when it fits) and the one diagram that \
shows the idea; create it in the first beat and keep acting on it.
  - List every part and quantity the lines will talk about, and give each a place in the picture, labelled, where \
it first comes up (a box, an edge label, a named point, a bar, a cell, a formula).
  - Give each beat's picture its beat's job: a question or predict line holds the picture or points at the \
candidates, never the answer; the wrong idea draws the wrong picture; the feedback line shows what holds instead; \
build lines take the next step; the end lines show the one big idea.
  - Give the video a `title` and a `colour_key` (the 2-4 things the pictures show again and again, each with its \
own colour, named in one or two words as the characters will say them). Use those colours in the calls.
  - Every segment cites the slides it uses (`source_refs`).

"""

_PLAN_EXAMPLE_NOTE = """\
An example of a finished plan at this viewer's level, on a different idea, to show the format and the bar (its \
points are the lines the writer then wrote): every picture moves with its line, and no picture shows an answer \
before its line.
"""


def planner_system_prompt(level: int, prereq_titles: list[str] | None, *, explainer: str, peer: str,
                          templates: list[str] | None, family: str | None, example: str) -> str:
    from animation_agent.visuals.specs import template_cards
    from script_generation_agent.storyboard_modules import module_for, module_rules

    module = module_for(family)
    prereqs = "; ".join(f"“{t}”" for t in prereq_titles or [])
    prereq_line = (f"This idea builds on {prereqs}: the plan has a line where {explainer} recaps it in one plain "
                   "sentence." if prereqs else "This idea builds on nothing earlier in the course: no recap.")
    return (
        _PLAN_INTRO
        + _PLAN_TASK.format(explainer=explainer, peer=peer)
        + "The viewer's level\n" + LEVEL_BRIEF[level].format(prereq_line=prereq_line) + "\n"
        + _STORYBOARD_DRAWING.replace("{picture}", picture_brief(family, templates or [])
                                      + (module_rules(module) if module is not None else ""))
                             .replace("{cards}", template_cards(templates, auto_layout=True))
        + SHARED_RUBRIC + "\n"
        + _PLAN_EXAMPLE_NOTE
        + ("Its templates may not be yours: draw only with the templates listed above.\n" if templates else "")
        + example
    )


class PlanBeat(BaseModel):
    draw: list[str] = Field(description="the template calls that draw this line's picture")
    point: str = Field(description="what the line will say about it, at most 15 plain words")


def _describe_plan(beat) -> str:
    who = "The explainer" if beat.speaker == "explainer" else "The peer"
    out = f"{who}, step {beat.step}: {beat.does}"
    if beat.misconception:
        out += " The wrong idea: draw it as a ghost or a wrong step."
    return out


def plan_model(plan) -> type[BaseModel]:
    """One required field per planned beat, in order (as storyboard.storyboard_model), each a picture and a
    point."""
    segments = {}
    for seg in plan:
        fields: dict = {"source_refs": (list[SlideRef], Field(description="the slides this segment uses"))}
        for k, beat in enumerate(seg.beats, 1):
            fields[beat.key(k)] = (PlanBeat, Field(description=_describe_plan(beat)))
        fields["sketches"] = (list[str], Field(
            description="[] unless no template can draw this segment: then one sentence per beat for an animator"))
        segments[seg.key] = (create_model(f"Plan_{seg.key}", **fields), Field(description=seg.phase))
    return create_model("PicturePlanBoard", title=(str, ...), colour_key=(list[TermColour], ...), **segments)


def plan_to_script(board: BaseModel, plan, ku: KnowledgeUnit) -> TemplatedDialogueScript:
    """The planned picture as a script whose lines are the planner's points (until the writer writes them)."""
    from script_generation_agent.storyboard import _colour_key

    segments = []
    for seg in plan:
        filled = getattr(board, seg.key)
        beats = [getattr(filled, b.key(k)) for k, b in enumerate(seg.beats, 1)]
        sketches = list(filled.sketches)
        code = bool(sketches) and not any(pb.draw for pb in beats)
        segments.append({
            "phase": seg.phase,
            "source_refs": [r.model_dump() for r in filled.source_refs] or [r.model_dump() for r in ku.source_refs[:1]],
            "drawn": "code" if code else "templates",
            "beats": [{
                "narration": pb.point.strip() or "-", "speaker": b.speaker, "step": b.step,
                "misconception": b.misconception, "draw": [] if code else list(pb.draw),
                "visual": (sketches[k] if k < len(sketches) else pb.point) if code else "(drawn from its calls)",
            } for k, (b, pb) in enumerate(zip(seg.beats, beats))],
        })
    return TemplatedDialogueScript.model_validate({
        "ku_id": ku.id, "title": board.title, "style": "dialogue", "visuals": "templates",
        "colour_key": [t.model_dump() for t in _colour_key(board.colour_key)], "segments": segments,
    })


# --------------------------------------------------------------------------
# The writer
# --------------------------------------------------------------------------

_WRITE_TASK = """\
You write the lines of one short dialogue video whose pictures are planned and drawn already. Under each beat is \
what its picture shows while the line is spoken (computed from the animation itself, so it is always right) and \
the point the planner meant the line to make. Write every line so it says what its picture shows at that moment, \
in the character's voice.

The beat plan is fixed. Each beat in the schema is named for its speaker and its tutoring step (e.g. \
b3_explainer_feedback), and its description says what the line does, how many words it has, and whether it \
carries a casual phrase. Fill in every beat in that order.
  - {explainer} (the explainer) knows the material and teaches it. {peer} (the peer) is a classmate learning it, \
like the viewer: curious, a bit sceptical, sometimes wrong, never laughed at. They use each other's names now \
and then.
  - Say the values and parts as the picture shows them (the middle value, the box, the bar, the cell), in words; \
never describe the screen ("the picture shows", "on screen").
  - A question or predict line asks without giving the answer: its picture holds it back on purpose. A beat \
marked "wrong idea" says the misconception with confidence; the next feedback line says why it is wrong and \
what holds instead.
  - "The picture stays as it is" means the line can talk about the picture before it.
  - Each line says its point once, and right: never a line that corrects itself. Keep to each beat's word range: \
the whole script must come to {min_words}-{max_words} words.
  - Every segment cites the slides its lines come from (`source_refs`).

"""

_WRITE_EXAMPLE_NOTE = """\
An example at this viewer's level, on a different idea: each beat's picture as the writer saw it, then the line \
written for it.
"""


def writer_system_prompt(level: int, prereq_titles: list[str] | None, *, explainer: str, peer: str, lexicon: str,
                         example: str) -> str:
    from script_generation_agent.storyboard import DIALOGUE_MAX_WORDS, DIALOGUE_MIN_WORDS

    prereqs = "; ".join(f"“{t}”" for t in prereq_titles or [])
    prereq_line = (f"This idea builds on {prereqs}: the plan has a line where {explainer} recaps it in one plain "
                   "sentence." if prereqs else "This idea builds on nothing earlier in the course: no recap.")
    rules = _DIALOGUE_LEVEL_RULES.replace("Give the video a `colour_key`",
                                          "The pictures already have a `colour_key` (given with the beats)")
    return (
        _DIALOGUE_INTRO
        + _WRITE_TASK.format(explainer=explainer, peer=peer, min_words=DIALOGUE_MIN_WORDS,
                             max_words=DIALOGUE_MAX_WORDS)
        + "The viewer's level\n" + LEVEL_BRIEF[level].format(prereq_line=prereq_line) + "\n"
        + rules
        + _STORYBOARD_SLANG.format(lexicon=lexicon)
        + SHARED_RUBRIC + "\n"
        + _WRITE_EXAMPLE_NOTE
        + example
    )


class LineBeat(BaseModel):
    narration: str = Field(description="the line, said while its picture plays")


def lines_model(plan) -> type[BaseModel]:
    from script_generation_agent.storyboard import _describe

    segments = {}
    for seg in plan:
        fields: dict = {"source_refs": (list[SlideRef], Field(description="the slides this segment's lines use"))}
        for k, beat in enumerate(seg.beats, 1):
            fields[beat.key(k)] = (LineBeat, Field(description=_describe(beat)))
        segments[seg.key] = (create_model(f"Lines_{seg.key}", **fields), Field(description=seg.phase))
    return create_model("Lines", **segments)


def beats_listing(script: TemplatedDialogueScript, plan, said: list[list[str]]) -> str:
    """The planned beats as the writer reads them: each beat's picture (computed) and the planner's point."""
    out = [f"title: {script.title}",
           "colour_key: " + ", ".join(f"{t.term} = {t.colour}" for t in script.colour_key), ""]
    for seg, sp, seg_said in zip(script.segments, plan, said):
        out.append(f"{sp.key}:")
        for k, (beat, bp) in enumerate(zip(seg.beats, sp.beats), 1):
            picture = seg_said[k - 1] if seg.drawn_by == "templates" and k - 1 < len(seg_said) else beat.visual
            out.append(f"  {bp.key(k)}:\n    picture: {picture}\n    point: {beat.narration}")
    return "\n".join(out)


def _with_lines(script: TemplatedDialogueScript, board: BaseModel, plan) -> TemplatedDialogueScript:
    data = script.model_dump(mode="json")
    for seg, sp in zip(data["segments"], plan):
        filled = getattr(board, sp.key)
        if filled.source_refs:
            seg["source_refs"] = [r.model_dump() for r in filled.source_refs]
        for k, (beat, bp) in enumerate(zip(seg["beats"], sp.beats), 1):
            beat["narration"] = getattr(filled, bp.key(k)).narration.strip()
    return TemplatedDialogueScript.model_validate(data)


# --------------------------------------------------------------------------
# The examples, in each call's form
# --------------------------------------------------------------------------


def _example_data(level: int, family: str | None) -> tuple[str, dict]:
    from script_generation_agent.storyboard_example import EXAMPLES
    from script_generation_agent.storyboard_modules import module_for

    module = module_for(family)
    if level == 2 and module is not None and module.example is not None:
        return module.ku, module.example
    return EXAMPLES[level]


def planner_example(level: int, family: str | None, *, explainer: str, peer: str) -> str:
    from script_generation_agent.storyboard_example import SEGMENT_KEYS

    ku, ex = _example_data(level, family)
    lines = [f"Knowledge Unit: {ku}", f"title: {ex['title']}",
             "colour_key: " + ", ".join(f"{t['term']} = {t['colour']}" for t in ex["colour_key"])]
    for key in SEGMENT_KEYS:
        lines.append(f"{key}:")
        for field, draw, narration in ex[key]:
            lines += [f"  {field}:", f"    draw: {draw}",
                      f"    point: {narration.format(explainer=explainer, peer=peer)}"]
    return "\n".join(lines) + "\n"


def write_example(level: int, family: str | None, *, explainer: str, peer: str) -> str:
    from animation_agent.visuals.calls import describe_script

    from script_generation_agent.storyboard_example import SEGMENT_KEYS

    ku, ex = _example_data(level, family)
    said = describe_script([[list(draw) for _, draw, _ in ex[key]] for key in SEGMENT_KEYS])
    lines = [f"Knowledge Unit: {ku}"]
    for key, seg_said in zip(SEGMENT_KEYS, said):
        lines.append(f"{key}:")
        for (field, _, narration), picture in zip(ex[key], seg_said):
            lines += [f"  {field}:", f"    picture: {picture}",
                      f"    line: {narration.format(explainer=explainer, peer=peer)}"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# The whole step
# --------------------------------------------------------------------------


MIN_PICTURE_BEATS = 5  # a Picture that changes on fewer beats than this is a still with a caption


def _thin_picture(segments):
    """A problem when the plan makes a Picture but shows it changing on only a few of its beats, or None. In
    runs/picture-p4 several videos showed their Picture on one or two lines (an MLE's likelihood curve in one
    segment only) and spent the rest on formulas; the critic marked them down for a still picture."""
    from types import SimpleNamespace

    names = set()
    beats = changing = 0
    for draws in segments:
        for calls in draws or []:
            beats += 1
            for c in calls:
                if m := re.match(r"\s*(\w+)\s*=\s*Picture\(", c):
                    names.add(m.group(1))
            if any(re.match(rf"\s*{re.escape(n)}\.(show|step)\(", c) for n in names for c in calls):
                changing += 1
    if not names or beats < 2 * MIN_PICTURE_BEATS or changing >= MIN_PICTURE_BEATS:
        return None
    return SimpleNamespace(segment=0, beat=1, call=None, kind="other", message=(
        f"the Picture changes on only {changing} of the video's {beats} beats, so for most of the video it is a "
        "still; snap a state for each point the lines make (10-25 snapshots) and show one on most beats, from the "
        "first segment to the last (create the Picture in the video's first beat; a formula can sit beside it)"))


def script_segments_of(script):
    from animation_agent.visuals.calls import script_segments

    return script_segments(script)


def _picture_calls(segments) -> str:
    """How many calls of each kind the segments make on a Picture, for the log (a step dropped on the way shows)."""
    import re

    counts = {"Picture": 0, "show": 0, "step": 0, "other": 0}
    for draws in segments:
        for calls in draws or []:
            for c in calls:
                if "Picture(" in c:
                    counts["Picture"] += 1
                elif m := re.match(r"\s*\w+\.(show|step)\(", c):
                    counts[m.group(1)] += 1
                else:
                    counts["other"] += 1
    return ", ".join(f"{k} {v}" for k, v in counts.items())


def write_storyboard_planned(
    ku: KnowledgeUnit,
    corpus,
    *,
    level: int,
    prereq_titles: list[str] | None = None,
    model: str,
    manifest=None,
    on_lines_ready: Callable | None = None,
    writer_model: str,
    picture=None,
    example=None,
) -> TemplatedDialogueScript:
    """storyboard.write_storyboard in two calls: the picture planned, settled and described, then the lines
    written to it (module docstring). Same arguments; `example` is the traced worked example (or None)."""
    from animation_agent.visuals.calls import describe_script
    from animation_agent.visuals.trace import trace_brief

    from script_generation_agent.picture_plan import plan_picture
    from script_generation_agent.script_writer import ScriptValidationError, gather_source_material, validate_dialogue
    from script_generation_agent.slang import lexicon_for_prompt
    from script_generation_agent.storyboard import (
        _CREATES,
        _PLAN,
        STORYBOARD_EFFORT,
        _log,
        _over_limit,
        _redo_feedback,
        _traced,
        align_lines,
        drop_echoes,
        fix_slang,
        match_lines,
        settle_picture,
        skeleton,
        with_pictures,
    )
    from syllabyte_common.cast import load_cast

    text_context, image_blocks = gather_source_material(corpus, ku)
    if not text_context:
        raise ScriptValidationError(f"KU {ku.id} cites slides that don't resolve in the corpus: {ku.source_refs}")
    cast = load_cast()
    explainer, peer = cast.explainer.name, cast.peer.name
    if os.environ.get("SYLLABYTE_PICTURES") == "grammar":  # a program draws the picture (scene grammar, P1)
        from script_generation_agent.picture_plan import GRAMMAR_PLAN

        picture, example = GRAMMAR_PLAN, None
    picture = picture or plan_picture(ku, model=model, manifest=manifest)
    plan = skeleton(level, bool(prereq_titles))
    allowed = set(picture.templates)
    if example is _PLAN:  # the traced worked example, planned as in one call
        from script_generation_agent.picture_plan import plan_example as plan_traced

        example = plan_traced(ku, picture, text_context, model=model, manifest=manifest, images=image_blocks)
    ku_prompt = build_script_prompt(ku, text_context)
    head = ku_prompt.replace("Write the 5-segment CLT-bLM script for this Knowledge Unit now.", "")

    # 1. The picture, planned (once more if it strays from the traced example or a creation call is refused).
    system = planner_system_prompt(level, prereq_titles, explainer=explainer, peer=peer,
                                   templates=picture.templates, family=picture.family,
                                   example=planner_example(level, picture.family, explainer=explainer, peer=peer))
    prompt = head + "Plan the pictures for this Knowledge Unit now: every beat's calls, then its point."
    if example is not None:
        prompt += trace_brief(example)
    feedback = ""
    for attempt in range(2):
        board = structured(schema=plan_model(plan), content=[text_block(prompt + feedback), *image_blocks],
                           system=system, stage=f"{PLAN_STAGE}_l{level}", ku_id=ku.id, model=writer_model,
                           effort=STORYBOARD_EFFORT, max_tokens=12000, manifest=manifest)
        if dump := os.environ.get("SYLLABYTE_PLAN_DUMP"):  # every planned board, to trace what later steps change
            Path(dump).mkdir(parents=True, exist_ok=True)
            (Path(dump) / f"{ku.id}-plan{attempt}.json").write_text(board.model_dump_json(indent=1))
        script = plan_to_script(board, plan, ku)
        _log(ku.id, [f"planned: {_picture_calls(script_segments_of(script))}"])
        script, off_trace = _traced(script, example, ku.id)
        refused = []
        if attempt == 0:
            from animation_agent.visuals.calls import check_script, script_segments

            segs = script_segments(script)
            refused = [p for p in check_script(segs, None, allowed)
                       if p.kind in ("other", "wrong_template") and p.call is not None
                       and _CREATES.match(segs[p.segment][p.beat - 1][p.call])]
            if (thin := _thin_picture(segs)) is not None:
                refused.append(thin)
        if not (off_trace or refused):
            break
        _log(ku.id, [f"the plan is drawn again: {'; '.join(p.message for p in off_trace + refused)[:400]}"])
        feedback = _redo_feedback(off_trace + refused)

    # 2. Settled as it will render, and described.
    segments = settle_picture(script, ku_id=ku.id, model=model, manifest=manifest, system=system, allowed=allowed,
                              main=picture.main, trace=example, keep_echo=True)
    said = describe_script(segments)
    _log(ku.id, [f"settled: {_picture_calls(segments)}"])

    # 3. The lines, written to the pictures.
    wsystem = writer_system_prompt(level, prereq_titles, explainer=explainer, peer=peer, lexicon=lexicon_for_prompt(),
                                   example=write_example(level, picture.family, explainer=explainer, peer=peer))
    listing = beats_listing(script, plan, said)
    wprompt = head + "The pictures, beat by beat:\n" + listing + "\n\nWrite every beat's line now."
    feedback, problems, best = "", [], None
    for attempt in range(2):
        lines = structured(schema=lines_model(plan), content=[text_block(wprompt + feedback), *image_blocks],
                           system=wsystem, stage=f"{WRITE_STAGE}_l{level}", ku_id=ku.id, model=writer_model,
                           max_tokens=6000, manifest=manifest)
        written = _with_lines(script, lines, plan)
        _log(ku.id, fix_slang(written, plan, (explainer, peer)))
        found = validate_dialogue(written)
        problems = [p for p in found if not _over_limit(p, written)]
        if len(problems) < len(found):
            _log(ku.id, [f"kept at {written.word_count} words, over the limit"])
        if not problems:
            best = written
            break
        _log(ku.id, [f"lines rejected: {'; '.join(problems)}"])
        feedback = ("\n\nYour previous lines were rejected by the automatic checker: " + "; ".join(problems)
                    + ". Fix these.")
    if best is None:
        raise ScriptValidationError(f"KU {ku.id}: {'; '.join(problems)}")

    # 4. As in one call: matched to the picture, the voices start, the visuals written. A note that repeats the
    # line it was planned for goes (it was kept while the lines were only points).
    segments = drop_echoes(segments, [[b.narration for b in seg.beats] for seg in best.segments], ku.id)
    segments, notes = align_lines(best, segments, example, ku.id)
    script = match_lines(best, ku_id=ku.id, model=model, manifest=manifest, allowed=allowed, segments=segments,
                         accept=lambda s: not [p for p in validate_dialogue(s) if not _over_limit(p, s)], notes=notes)
    _log(ku.id, [f"final: {_picture_calls(segments)}"])
    if on_lines_ready is not None:
        on_lines_ready(script)
    print(f"[storyboard] {ku.id}: planned, then written", file=sys.stderr, flush=True)
    return with_pictures(script, segments, ku_id=ku.id, allowed=allowed)


__all__ = ["PLAN_STAGE", "WRITE_STAGE", "planner_example", "plan_model", "planner_system_prompt", "lines_model",
           "write_example", "write_storyboard_planned", "writer_system_prompt"]
