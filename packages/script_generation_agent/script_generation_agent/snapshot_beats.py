"""
Snapshot-led beats: every point a step of the picture (plan/snapshot-led-beats-plan.md).

Before this, two plans were made apart and met only by luck: the beat plan, fixed by code (storyboard.skeleton: 17
beats at level 2), and the picture program, whose snapshots the planner then handed out to the beats. With fewer
steps in the program than points in the plan, most points got no picture change, and the critic's main complaint
in runs/va1-va3 was a still picture under a line bringing in something new. Rounds of checks did not move visual
alignment past noise (4.0-4.8).

So the beats are built from the picture instead:
  1. The planner writes only the program (and the title, colour key, slide example), each snapshot tagged with the
     part of the video it belongs to: snap(caption, name=..., part='deliver_1'), and wrong=True for the wrong idea.
  2. Code runs it and checks the snapshot count of each part against a band (BANDS); a program outside it, or one
     that fails or doesn't fit, is sent back once with what is wrong.
  3. Code builds each part's beats: the tutoring roles stay (the hook, the wrong idea and its feedback, the predict
     line and its answer, the restatement), and the part's build beats are as many as its snapshots, one each, in
     order. Code writes every p.show(snap=...) call, so a line can't be out of step with its picture or jump ahead.
  4. The writer writes the lines as before, each point-making line now with exactly one change to say.

A program that still fails after the redraw returns None, and the storyboard is planned the way it was before.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from pydantic import Field, create_model

from script_generation_agent.storyboard import BeatPlan, SegmentPlan, _budget, _colour_key
from syllabyte_common.llm import structured, text_block
from syllabyte_common.models import SlideRef, TemplatedDialogueScript, TermColour

PARTS = ("prepare", "initiate", "deliver_1", "deliver_2", "end")
PHASES = {"prepare": "prepare", "initiate": "initiate", "deliver_1": "deliver", "deliver_2": "deliver", "end": "end"}
# snapshots per part: one line each, so 14-18 lines in all (about 225 words, a 70-100 s video)
BANDS = {"prepare": (1, 2), "initiate": (1, 2), "deliver_1": (3, 6), "deliver_2": (3, 6), "end": (0, 1)}
MAX_DELIVER = 10  # the two deliver parts together
PICTURE = "p"
MAX_PROGRAMS = 3  # the first, a redraw, and one more only for a program that still can't run or fit


def beats_mode() -> str:
    """How a grammar storyboard's beats are made: "snapshots" (built from the program's snapshots, the default on
    this branch) or "planned" (the fixed skeleton, its snapshots handed out by the planner: SYLLABYTE_BEATS=planned)."""
    return "planned" if os.environ.get("SYLLABYTE_BEATS", "").strip().lower() == "planned" else "snapshots"


# --------------------------------------------------------------------------
# Each part's tutoring roles
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    """One line of a part. `takes` says which snapshot it shows: "snap" the next one, "may" the next one when the
    part has one to spare, "wrong" the next one if it is the wrong idea's, "hold" none (the picture stays)."""

    speaker: str
    step: str
    does: str
    takes: str = "snap"
    misconception: bool = False
    move: str = ""  # the learning moment its casual phrase marks (slang.MOVES); "" for no casual phrase


BUILD = "Takes the next step: says what the picture now shows, with its values."
LAST_BUILD = "Completes the idea: states the key fact the picture now shows."


def roles(level: int, has_prereqs: bool = False) -> dict[str, tuple[list[Slot], list[Slot]]]:
    """Each part's lines before its build lines (lead) and after them (tail), as storyboard.skeleton's tutoring
    frame has them; the build lines between are one per snapshot left."""
    teaser = ("recaps the earlier idea this one builds on, in one plain sentence" if has_prereqs
              else "hints at the surprising answer without giving it away")
    second = {
        1: ([Slot("explainer", "build", "Sets up the full worked example from the slides, naming its numbers."),
             Slot("peer", "question", "Asks how to do the first step.", "hold", move="followup"),
             Slot("explainer", "build", "Does the first step, naming each quantity as it is used.")],
            [Slot("explainer", "predict", "To the viewer: pause and guess the result of the last step.", "hold"),
             Slot("peer", "build", "Gives the result: the answer to the predict line.", move="result")]),
        2: ([Slot("explainer", "build", "Sets up one worked example from the slides, naming its numbers."),
             Slot("peer", "question", "Asks why a key step works.", "hold", move="followup"),
             Slot("explainer", "feedback", "Gives the reason that step works.")],
            [Slot("explainer", "predict", "To the viewer: pause and guess the result of the next step.", "hold"),
             Slot("peer", "build", "Gives the result: the answer to the predict line.", move="result")]),
        3: ([Slot("peer", "question", "Asks ONE 'what if': changes a condition from the slides.", move="followup"),
             Slot("peer", "answer", "A first guess at what happens, and it is wrong.", "wrong", misconception=True),
             Slot("explainer", "predict", "To the viewer: pause and guess what really happens.", "hold"),
             Slot("explainer", "feedback", "Says what really happens and why, refining the guess.")],
            [Slot("explainer", "build", "States the conclusion: how the idea changes under that condition.", "may")]),
    }[level]
    return {
        "prepare": ([Slot("peer", "question", "The hook: a puzzled, deep question about the idea (why, how, what "
                                              "if).", move="hook"),
                     Slot("explainer", "build", f"Answers the hook briefly: {teaser}.", "may")], []),
        "initiate": ([Slot("peer", "question", "Asks what this is for, or why it matters.", "may"),
                      Slot("explainer", "objective", "States what the viewer will be able to do after the video.")],
                     []),
        "deliver_1": ([Slot("explainer", "question", "Asks a question that invites the common wrong idea."),
                       Slot("peer", "answer", "Gives that wrong idea, confidently: a misconception a student of this "
                                              "course really has.", "wrong", misconception=True, move="commit"),
                       Slot("explainer", "feedback", "Says why it is wrong (the reason) and what holds instead.")],
                      []),
        "deliver_2": second,
        "end": ([Slot("peer", "check", "Restates the one big idea in their own words.", "may"),
                 Slot("explainer", "check", "Confirms or sharpens it in one line.", "hold")], []),
    }


# --------------------------------------------------------------------------
# The snapshots, by part, and the band
# --------------------------------------------------------------------------


def by_part(snaps: list[dict]) -> tuple[dict[str, list[dict]], list[str]]:
    """The snapshots of each part, in order, and what code had to decide: a snapshot with no part, or with a part
    earlier than one already reached, belongs to the part running at that point (the first to prepare)."""
    out: dict[str, list[dict]] = {p: [] for p in PARTS}
    log, at = [], 0
    for s in snaps:
        part = s.get("part")
        if part in PARTS and PARTS.index(part) >= at:
            at = PARTS.index(part)
        else:
            log.append(f"snapshot {s['name']!r} ({part or 'no part'}) put in {PARTS[at]}")
        out[PARTS[at]].append(s)
    return out, log


def band_problems(snaps: list[dict], level: int) -> list[str]:
    """What is wrong with the program's snapshots as the video's steps, in words for the planner; [] when none."""
    problems = []
    untagged = [s["name"] for s in snaps if s.get("part") not in PARTS]
    if untagged:
        problems.append(f"snapshots {', '.join(map(repr, untagged[:6]))} name no part: give every snap() its part "
                        f"({', '.join(PARTS)})")
    order = [PARTS.index(s["part"]) for s in snaps if s.get("part") in PARTS]
    if any(b < a for a, b in zip(order, order[1:])):
        problems.append("the snapshots' parts are out of order: the program snaps prepare's first, then "
                        "initiate's, deliver_1's, deliver_2's and end's")
    parts, _ = by_part(snaps)
    counts = {p: len(parts[p]) for p in PARTS}
    for p, (lo, hi) in BANDS.items():
        if not lo <= counts[p] <= hi:
            problems.append(f"{p} has {counts[p]} snapshots; it needs {lo}-{hi}")
    if (n := counts["deliver_1"] + counts["deliver_2"]) > MAX_DELIVER:
        problems.append(f"the two deliver parts have {n} snapshots together; at most {MAX_DELIVER}, so the video "
                        "stays under 100 seconds (merge two small steps into one)")
    d1 = parts["deliver_1"]
    if len(d1) >= 2 and not d1[1].get("wrong"):
        problems.append("deliver_1's second snapshot is the wrong idea's state (wrong=True): the peer's "
                        "misconception, drawn")
    wrong_ok = {("deliver_1", 1)} | ({("deliver_2", 1)} if level == 3 else set())
    stray = [s["name"] for p in PARTS for k, s in enumerate(parts[p]) if s.get("wrong") and (p, k) not in wrong_ok]
    if stray:
        problems.append(f"wrong=True marks only the wrong idea (deliver_1's second snapshot"
                        f"{', or deliver_2s second' if level == 3 else ''}), not {', '.join(map(repr, stray))}")
    return problems


def _clamp(snaps: list[dict], hi: int) -> list[dict]:
    """At most `hi` snapshots, keeping the first ones and the last (the part's result); the ones between that go
    are passed over (the next show animates from the one before)."""
    return snaps if len(snaps) <= hi else snaps[:hi - 1] + snaps[-1:]


# --------------------------------------------------------------------------
# The beats
# --------------------------------------------------------------------------


def _part_beats(snaps: list[dict], lead: list[Slot], tail: list[Slot], last_does: str) -> list[tuple[Slot, str | None]]:
    """The part's lines, each with the name of the snapshot it shows (None: the picture stays)."""
    queue = list(snaps)
    tail_need = sum(1 for s in tail if s.takes == "snap")
    out: list[tuple[Slot, str | None]] = []
    for k, slot in enumerate(lead):
        later = sum(1 for s in lead[k + 1:] if s.takes == "snap") + tail_need
        take = (slot.takes == "snap" and len(queue) > tail_need
                or slot.takes == "may" and len(queue) > later
                or slot.takes == "wrong" and bool(queue) and bool(queue[0].get("wrong")) and len(queue) > later)
        out.append((slot, queue.pop(0)["name"] if take else None))
    # the tail's snapshots come off the end: a "snap" always, a "may" when one is left past the build lines' turn
    ends: list[str | None] = []
    for slot in reversed(tail):
        take = slot.takes == "snap" and queue or slot.takes == "may" and len(queue) > 0
        ends.insert(0, queue.pop()["name"] if take else None)
    # the build lines between, one per snapshot left, taking turns so the last hands over to the tail's first
    last = ("peer" if tail[0].speaker == "explainer" else "explainer") if tail else "explainer"
    other = {"peer": "explainer", "explainer": "peer"}
    speakers = []
    for _ in queue:
        speakers.insert(0, last if not speakers else other[speakers[0]])
    for j, (s, speaker) in enumerate(zip(queue, speakers)):
        does = last_does if j == len(queue) - 1 and not tail and speaker == "explainer" else BUILD
        out.append((Slot(speaker, "build", does), s["name"]))
    out += list(zip(tail, ends))
    return out


def build_beats(snaps: list[dict], level: int, has_prereqs: bool = False,
                ) -> tuple[list[SegmentPlan], list[list[str | None]], list[str]]:
    """The beat plan built from the snapshots (word ranges budgeted as storyboard.skeleton's), the snapshot each
    beat shows, and what code decided on the way (a part's snapshots placed or passed over)."""
    parts, log = by_part(snaps)
    if not parts["prepare"]:  # the picture opens on the program's first snapshot, under the hook
        first = next(p for p in PARTS if parts[p])
        parts["prepare"] = [parts[first].pop(0)]
        log.append(f"snapshot {parts['prepare'][0]['name']!r} put in prepare: the video opens on it")
    for p, (_lo, hi) in BANDS.items():
        if len(parts[p]) > hi:
            log.append(f"{p}: {len(parts[p]) - hi} of its {len(parts[p])} snapshots passed over")
            parts[p] = _clamp(parts[p], hi)
    while len(parts["deliver_1"]) + len(parts["deliver_2"]) > MAX_DELIVER:
        p = max(("deliver_2", "deliver_1"), key=lambda q: len(parts[q]))
        log.append(f"{p}: a snapshot passed over to keep the video short")
        parts[p] = _clamp(parts[p], len(parts[p]) - 1)
    plan, shown = [], []
    for p, (lead, tail) in roles(level, has_prereqs).items():
        beats = _part_beats(parts[p], lead, tail, LAST_BUILD)
        plan.append(SegmentPlan(PHASES[p], p, [BeatPlan(s.speaker, s.step, s.does, misconception=s.misconception,
                                                        slang=bool(s.move), move=s.move) for s, _ in beats]))
        shown.append([name for _, name in beats])
    return _budget(plan), shown, log


def picture_call(program: list[str]) -> str:
    """The call that creates the Picture with the whole program (each line in double quotes, its strings single)."""
    lines = [line.replace('"', "'") if "'" not in line else line for line in program]
    return f"{PICTURE} = Picture(program=[" + ", ".join(f'"{line}"' for line in lines) + "])"


def calls_for(program: list[str], shown: list[list[str | None]], first: str) -> list[list[list[str]]]:
    """Each beat's calls: the first beat creates the Picture (it opens on the program's first snapshot, `first`),
    and every beat that shows a snapshot shows it by name."""
    out, made = [], False
    for names in shown:
        seg = []
        for name in names:
            calls = []
            if not made:
                calls.append(picture_call(program))
                made = True
                if name == first:
                    name = None
            if name is not None:
                calls.append(f"{PICTURE}.show(snap='{name}')")
            seg.append(calls)
        out.append(seg)
    return out


# --------------------------------------------------------------------------
# The planner: the program, and only the program
# --------------------------------------------------------------------------


_PROGRAM_TASK = """\
You write the picture program for the whole video. Code runs it and builds the video from its snapshots: each \
snapshot gets one line, in the program's order, and is on screen while that line is spoken. So the snapshots are \
the video's steps: plan them as the lesson. {explainer} explains; {peer} is a classmate learning it, sometimes \
wrong. The video has five parts, and every snap() names its part (snap('caption', name='...', part='...')):
  - prepare (1-2 snapshots): the first is the opening picture, under {peer}'s hook (a puzzling question about the \
idea, never its answer); a second goes with {explainer}'s short reply to it.
  - initiate (1-2): what the video will work on: the setup, never the result. With two, the first goes with \
{peer} asking what this is for, the second with {explainer}'s objective.
  - deliver_1 (3-6): the first sets up a question that invites the common wrong idea; the second is that wrong \
idea drawn as a state, snap(..., wrong=True) (a wrong value marked red, the wrong order, a red line); the third \
shows what holds instead; each one after takes the next step toward the key fact.
  - deliver_2 (3-6): {second}
  - end (0-1): the one big idea, with everything it needs on screen.
At most {max_deliver} snapshots across the two deliver parts, so the video stays 70-100 seconds. The question \
lines, the predict line and the last line keep the picture as it is: they need no snapshot of their own.
Plan the whole video before the first line of the program:
  - Pick the example from the slides (its real numbers, its real size when it fits) and the diagram that shows \
the idea; draw it from the first snapshot and keep acting on it.
  - List every part and quantity the lines will talk about, and give each a place in the picture, labelled, where \
it first comes up. A formula the lines work through is a formula view, each of its steps a snapshot.
  - One change per snapshot, the change its line will say: a snapshot that changes nothing leaves its line \
nothing to point at, and one that changes three things gets one line for all three.
  - More steps, not a bigger drawing: most snapshots change what is already there (mark a node, light a cell \
or a code line, write a value, highlight a term), so the drawing stays inside "What fits" below (about 7 \
messages, 4 frames, one timeline alone). Every wrong=True stays when you rewrite the program.
  - Give the video a `title` and a `colour_key` (the 2-4 things the pictures show again and again, each with its \
own colour, named in one or two words as the characters will say them), and style those things in the program \
with the matching style word (YELLOW is current, TEAL visited, GREEN found, ORANGE compare, RED red, BLUE blue).
  - `source_refs`: the slides the video uses.

"""

_SECOND = {
    1: "the full worked example from the slides: the first snapshot sets it up with its numbers, the second does "
       "its first step, then one per step; the last is its result, which the viewer is asked to predict first.",
    2: "one worked example from the slides: the first snapshot sets it up with its numbers, the second shows the "
       "key step whose reason the lines give, then one per step; the last is its result, which the viewer is asked "
       "to predict first.",
    3: "one 'what if' that changes a condition from the slides: the first snapshot shows the change; the second "
       "may be a first wrong guess at what happens (wrong=True); then what really happens, one step each; the last "
       "is the conclusion.",
}


def picture_area(ku) -> str | None:
    """The area whose picture brief a topic gets (scene/brief.py), from its title and summary; None (the whole
    brief) when no area leads, or with SYLLABYTE_BRIEF=full."""
    from animation_agent.scene.brief import area_of

    if os.environ.get("SYLLABYTE_BRIEF") == "full":
        return None
    return area_of(f"{ku.title}. {getattr(ku, 'summary', '') or ''}")


def program_system_prompt(level: int, prereq_titles: list[str] | None, *, explainer: str, peer: str,
                          area: str | None = None) -> str:
    from animation_agent.scene.brief import brief

    from script_generation_agent.prompts import LEVEL_BRIEF, SHARED_RUBRIC
    from script_generation_agent.storyboard_plan import _PLAN_INTRO

    prereqs = "; ".join(f"“{t}”" for t in prereq_titles or [])
    prereq_line = (f"This idea builds on {prereqs}: {explainer} recaps it in one plain sentence early on (the "
                   "prepare part)." if prereqs else "This idea builds on nothing earlier in the course: no recap.")
    return (
        _PLAN_INTRO
        + _PROGRAM_TASK.format(explainer=explainer, peer=peer, second=_SECOND[level], max_deliver=MAX_DELIVER)
        + "The viewer's level\n" + LEVEL_BRIEF[level].format(prereq_line=prereq_line) + "\n"
        + brief(area)
        + SHARED_RUBRIC + "\n"
    )


def program_model():
    from script_generation_agent.fidelity import SlideExample

    return create_model(
        "PictureProgram",
        title=(str, ...),
        colour_key=(list[TermColour], ...),
        slide_example=(SlideExample, Field(description=(
            "the slides' own worked example that the picture draws, copied exactly; write it before the program"))),
        program=(list[str], Field(description=(
            "the picture program, one string per line, indentation kept; its strings in single quotes, TeX in raw "
            "strings; every snap() names its part"))),
        source_refs=(list[SlideRef], Field(description="the slides the video uses")),
    )


def program_problems(program: list[str], level: int) -> tuple[list[dict], list[str]]:
    """The program's snapshots, and why it can't be drawn as the video's steps ([] when it can). A program that
    can't run or doesn't fit has no snapshots."""
    from animation_agent.visuals.specs import PictureParams, _picture_problem, picture_snapshots, picture_source

    try:
        program = PictureParams(program=program).program
    except Exception as e:  # pydantic's message names the problem
        return [], [str(e).split("\n", 2)[-1].strip()[:400]]
    if (problem := _picture_problem(picture_source(program), "full")) is not None:
        return [], [problem]
    snaps = picture_snapshots(program)
    return snaps, band_problems(snaps, level) + dropped_labels(snaps)


def dropped_labels(snaps: list[dict]) -> list[str]:
    """The labels the layout had to leave out, as a problem the planner can fix with shorter text. They used to be
    left out silently: in runs/bench1-2 a race condition's timeline blocks ('load 5', 'store 6', each block 0.55
    units wide) lost every label, and the critic could not read the interleaving."""
    from animation_agent.scene.api import PictureError
    from animation_agent.scene.layout import plan_groups
    from animation_agent.visuals.specs import _dialogue_area

    try:
        groups = plan_groups(snaps, *_dialogue_area("full"))
    except PictureError:
        return []
    out: list[str] = []
    for _ids, lay in groups:
        for view in lay.math.values():
            for text in getattr(view, "dropped", None) or []:
                if str(text) not in out and str(text) not in AXIS_NAMES:
                    out.append(str(text))
    if not out:
        return []
    shown = ", ".join(repr(t) for t in out[:6])
    return [f"these labels don't fit where they go and are left out of the picture: {shown}. Keep the numbers "
            "the captions rely on: shorten them (a symbol or an abbreviation), label fewer things on that view, or "
            "give it more room (hide a view it shares the frame with)"]


AXIS_NAMES = {"x", "y", "z"}  # a crowded 3D axis drops its own name; nothing the planner can change


def _feedback(program: list[str], problems: list[str], drawn: bool) -> str:
    # In runs/va4, 3 of 4 first programs didn't fit or didn't run (9 messages in a sequence, a timeline beside a
    # table, a frame title too long): more snapshots tempt a bigger drawing, and a redraw that cut snapshots to fit
    # would lose the steps. Keep the example and steps; change the simultaneous views for fit failures,
    # and fix runtime errors directly rather than telling the planner to shrink an unrelated drawing.
    layout_failure = any("fit" in p or "views on screen" in p for p in problems)
    keep = ("" if drawn else
            " Keep the slide's worked example and every snapshot, its part and its wrong=True. "
            + ("Change which views are visible: v.hide() keeps its state, v.show() restores it. Hide a view "
               "before creating its replacement. Show the diagram and supporting working in separate steps "
               "when needed; do not repeat the refused combination. Code handles sizing and placement."
               if layout_failure else "Fix the program error without removing the teaching steps."))
    return ("\n\nYour previous program:\n" + "\n".join(program)
            + "\n\nThe automatic checker refused it:\n" + "\n".join(f"  - {p}" for p in problems)
            + "\nWrite it again with these fixed, changing only what you must." + keep)


def plan_by_snapshots(ku, *, head: str, image_blocks: list, text_context: str, level: int,
                      prereq_titles: list[str] | None, explainer: str, peer: str, model: str, manifest=None,
                      stage: str = "storyboard_program"):
    """The planned picture and the beats built from it, as (script whose lines are the snapshots' captions, the
    calls per segment and beat, the beat plan), or None when the program can't be drawn after one redraw."""
    from script_generation_agent.fidelity import example_problem
    from script_generation_agent.storyboard import STORYBOARD_EFFORT, _log

    area = picture_area(ku)
    print(f"[storyboard] {ku.id}: picture brief for {area or 'every area'}", file=sys.stderr, flush=True)
    system = program_system_prompt(level, prereq_titles, explainer=explainer, peer=peer, area=area)
    prompt = head + "Write the picture program for this Knowledge Unit now: the whole video's steps, each tagged."
    feedback, board, snaps, problems = "", None, [], []
    for attempt in range(MAX_PROGRAMS):
        board = structured(schema=program_model(), content=[text_block(prompt + feedback), *image_blocks],
                           system=system, stage=f"{stage}_l{level}", ku_id=ku.id, model=model,
                           effort=STORYBOARD_EFFORT, max_tokens=10000, manifest=manifest)
        if dump := os.environ.get("SYLLABYTE_PLAN_DUMP"):
            from pathlib import Path

            Path(dump).mkdir(parents=True, exist_ok=True)
            (Path(dump) / f"{ku.id}-program{attempt}.json").write_text(board.model_dump_json(indent=1))
        snaps, problems = program_problems(board.program, level)
        if snaps:
            plan, shown, _ = build_beats(snaps, level, bool(prereq_titles))
            segments = calls_for(board.program, shown, snaps[0]["name"])
            if (stray := example_problem(board.slide_example, segments, text_context)) is not None:
                problems.append(stray.message)
        counts = ", ".join(f"{p} {n}" for p, n in _counts(snaps).items()) if snaps else "no snapshots"
        _log(ku.id, [f"program {attempt + 1}: {len(board.program)} lines; snapshots {counts}"])
        if not problems or attempt + 1 == MAX_PROGRAMS or (snaps and attempt >= 1):
            break  # a program that runs and fits gets one redraw; one that can't be drawn, two
        _log(ku.id, [f"the program is written again: {'; '.join(problems)[:500]}"])
        feedback = _feedback(board.program, problems, bool(snaps))
    if not snaps:
        print(f"[storyboard] {ku.id}: the program can't be drawn ({'; '.join(problems)[:300]}); planning the "
              "beats as before", file=sys.stderr, flush=True)
        return None
    if problems:
        _log(ku.id, [f"built with the program as it is: {'; '.join(problems)[:300]}"])
    plan, shown, decided = build_beats(snaps, level, bool(prereq_titles))
    _log(ku.id, decided)
    program = board.program
    segments = calls_for(program, shown, snaps[0]["name"])
    captions = {s["name"]: s["caption"].strip() for s in snaps}
    refs = [r.model_dump() for r in board.source_refs] or [r.model_dump() for r in ku.source_refs[:1]]
    data = {
        "ku_id": ku.id, "title": board.title, "style": "dialogue", "visuals": "templates",
        "colour_key": [t.model_dump() for t in _colour_key(board.colour_key)],
        "segments": [{
            "phase": sp.phase, "source_refs": refs, "drawn": "templates",
            "beats": [{"narration": (captions.get(name) if name else None) or b.does, "speaker": b.speaker,
                       "step": b.step, "misconception": b.misconception, "draw": calls,
                       "visual": "(drawn from its calls)"}
                      for b, name, calls in zip(sp.beats, names, seg)],
        } for sp, names, seg in zip(plan, shown, segments)],
    }
    _log(ku.id, ["beats from snapshots: " + ", ".join(f"{sp.key} {len(sp.beats)}" for sp in plan)
                 + f" ({sum(len(sp.beats) for sp in plan)} lines)"])
    return TemplatedDialogueScript.model_validate(data), segments, plan


def _counts(snaps: list[dict]) -> dict[str, int]:
    parts, _ = by_part(snaps)
    return {p: len(parts[p]) for p in PARTS}


__all__ = ["BANDS", "PARTS", "band_problems", "beats_mode", "build_beats", "by_part", "calls_for", "picture_call",
           "plan_by_snapshots", "program_problems", "program_system_prompt", "roles"]
