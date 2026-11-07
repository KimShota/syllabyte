"""
A dialogue video's script and pictures in one call: the storyboard (plan/one-shot-storyboard-plan.md).

The template pilots needed repairs because the writer had to keep track of things code can guarantee
(runs/template-videos-2..8: 12 rewrites for slang counts, word counts and speaker runs; 33 fix calls on draw
calls), because the lines were written before the pictures and the pictures fitted to them afterwards, and
because the writer never saw how it would be scored. So here:

  - code builds the beat plan (skeleton): who speaks each line, its tutoring step, where the misconception, its
    correction and the predict line go, a word range per line and the lines that carry a casual phrase. It meets
    validate_dialogue by construction;
  - one structured call fills every beat with its picture (template calls) and then its line, with the plan in
    the schema itself (one required field per beat, named for its speaker and step), the critic's rubric, and a
    worked example;
  - code fixes what is left that it can (slang slots, the colour key, source refs, and the calls through
    animation_agent.visuals.normalize), and only what it can't goes to one small fix call.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, create_model

from script_generation_agent.prompts import (
    DIALOGUE_MAX_WORDS,
    DIALOGUE_MIN_WORDS,
    build_script_prompt,
    storyboard_system_prompt,
)
from script_generation_agent.picture_plan import PicturePlan, plan_example, plan_picture
from script_generation_agent.slang import MIN_SLANG, find_slang, lexicon_for_prompt, max_slang
from syllabyte_common.llm import DEFAULT_MODEL, structured, text_block
from syllabyte_common.models import (
    CourseCorpus,
    KnowledgeUnit,
    RunManifest,
    SlideRef,
    TemplatedDialogueScript,
    TermColour,
)

# The one call that writes the whole video: Sonnet at medium effort (2026-11-05). Opus 5.5 was tried and set
# aside for now: at medium it took 39-43 s (videos of 72-81 s, runs/storyboard-opus-1), and at low it was about as
# fast as Sonnet at medium (45-56 s, runs/storyboard-opus-2) with no better critic scores in two videos. Every
# other call runs on llm.DEFAULT_MODEL (Sonnet) at llm.DEFAULT_EFFORT (low), including the fix call.
STORYBOARD_MODEL = DEFAULT_MODEL
STORYBOARD_EFFORT = "medium"

# Words per line by step, before the plan is scaled to fit the script's word limits.
STEP_WORDS = {
    "question": (7, 12), "answer": (7, 12), "feedback": (12, 18), "build": (10, 15), "predict": (6, 11),
    "objective": (10, 18), "check": (10, 16),
}
NO_SLANG_STEPS = ("objective", "check")


@dataclass(frozen=True)
class BeatPlan:
    speaker: str  # "explainer" | "peer"
    step: str
    does: str  # what the line does, for the writer
    misconception: bool = False
    slang: bool = False
    words: tuple[int, int] = (0, 0)

    def key(self, k: int) -> str:
        return f"b{k}_{self.speaker}_{self.step}" + ("_wrong_idea" if self.misconception else "")


@dataclass
class SegmentPlan:
    phase: str
    key: str  # the storyboard's field for this segment
    beats: list[BeatPlan] = field(default_factory=list)


def _b(speaker: str, step: str, does: str, **kw) -> BeatPlan:
    return BeatPlan(speaker, step, does, **kw)


def skeleton(level: int, has_prereqs: bool = False) -> list[SegmentPlan]:
    """The beat plan for a dialogue at `level` (1-3), the tutoring frame of prompts._DIALOGUE_FRAME made concrete."""
    teaser = ("recaps the earlier idea this one builds on, in one plain sentence" if has_prereqs
              else "hints at the surprising answer without giving it away")
    plan = [
        SegmentPlan("prepare", "prepare", [
            _b("peer", "question", "The hook: a puzzled, deep question about the idea (why, how, what if).", slang=True),
            _b("explainer", "build", f"Answers the hook briefly: {teaser}."),
        ]),
        SegmentPlan("initiate", "initiate", [
            _b("peer", "question", "Asks what this is for, or why it matters."),
            _b("explainer", "objective", "States what the viewer will be able to do after the video."),
        ]),
        SegmentPlan("deliver", "deliver_1", [
            _b("explainer", "question", "Asks a question that invites the common wrong idea."),
            _b("peer", "answer", "Gives that wrong idea, confidently: a misconception a student of this course "
                                 "really has.", misconception=True, slang=True),
            _b("explainer", "feedback", "Says why it is wrong (the reason) and what holds instead."),
            _b("peer", "build", "Takes the next step toward the right idea."),
            _b("explainer", "build", "Completes the idea: states the key fact."),
        ]),
    ]
    second = {
        1: [
            _b("explainer", "build", "Sets up the full worked example from the slides, naming its numbers."),
            _b("peer", "question", "Asks how to do the first step.", slang=True),
            _b("explainer", "build", "Does the first step, naming each quantity as it is used."),
            _b("peer", "question", "Asks why a later step works."),
            _b("explainer", "feedback", "Gives the reason that step works."),
            _b("explainer", "predict", "To the viewer: pause and guess the result of the last step."),
            _b("peer", "build", "Gives the result: the answer to the predict line."),
        ],
        2: [
            _b("explainer", "build", "Sets up one worked example from the slides, naming its numbers."),
            _b("peer", "question", "Asks why a key step works.", slang=True),
            _b("explainer", "feedback", "Gives the reason that step works."),
            _b("explainer", "predict", "To the viewer: pause and guess the result of the next step."),
            _b("peer", "build", "Gives the result: the answer to the predict line."),
            _b("explainer", "build", "Confirms it and ties it back to the idea."),
        ],
        3: [
            _b("peer", "question", "Asks ONE 'what if': changes a condition from the slides.", slang=True),
            _b("peer", "answer", "A first guess at what happens, and it is wrong.", misconception=True),
            _b("explainer", "predict", "To the viewer: pause and guess what really happens."),
            _b("explainer", "feedback", "Says what really happens and why, refining the guess."),
            _b("peer", "build", "Reasons it through one step further."),
            _b("explainer", "build", "States the conclusion: how the idea changes under that condition."),
        ],
    }[level]
    plan.append(SegmentPlan("deliver", "deliver_2", second))
    plan.append(SegmentPlan("end", "end", [
        _b("peer", "check", "Restates the one big idea in their own words."),
        _b("explainer", "check", "Confirms or sharpens it in one line."),
    ]))
    return _budget(plan)


SLANG_WORDS = 2  # a casual phrase ("not gonna lie") takes words of its own


def _budget(plan: list[SegmentPlan]) -> list[SegmentPlan]:
    """Each line's word range from its step (a little longer where it carries a casual phrase), scaled so the
    ranges sum to about 225 words: room under the 250-word limit for writers who run long, without squeezing
    lines below natural speech (tests check the worked examples keep to these ranges)."""
    def base(b: BeatPlan) -> tuple[int, int]:
        lo, hi = STEP_WORDS[b.step]
        return (lo, hi + SLANG_WORDS) if b.slang else (lo, hi)

    beats = [b for seg in plan for b in seg.beats]
    lo_total = sum(base(b)[0] for b in beats)
    hi_total = sum(base(b)[1] for b in beats)
    lo_f = max(1.0, (DIALOGUE_MIN_WORDS + 5) / lo_total)
    hi_f = min(1.0, (DIALOGUE_MAX_WORDS - 25) / hi_total)
    for seg in plan:
        seg.beats = [BeatPlan(b.speaker, b.step, b.does, b.misconception, b.slang,
                              (round(base(b)[0] * lo_f), max(round(base(b)[0] * lo_f) + 2, int(base(b)[1] * hi_f))))
                     for b in seg.beats]
    return plan


# --------------------------------------------------------------------------
# The schema the one call fills in: the plan, as required fields
# --------------------------------------------------------------------------


class StoryBeat(BaseModel):
    draw: list[str] = Field(description="the template calls that draw this line's picture (decide these first)")
    narration: str = Field(description="the line, spoken while that picture plays")


def _describe(beat: BeatPlan) -> str:
    who = "The explainer" if beat.speaker == "explainer" else "The peer"
    out = f"{who}, step {beat.step}: {beat.does} {beat.words[0]}-{beat.words[1]} words."
    if beat.misconception:
        out += " The wrong idea: draw it as a ghost or a wrong step."
    if beat.slang:
        out += " Casual phrase here."
    elif beat.step in NO_SLANG_STEPS:
        out += " No casual phrase."
    return out


def storyboard_model(plan: list[SegmentPlan]) -> type[BaseModel]:
    """A Pydantic model with one required field per planned beat, in order, so the structured output can't skip,
    add or reorder beats."""
    segments = {}
    for seg in plan:
        fields: dict = {"source_refs": (list[SlideRef], Field(description="the slides this segment's lines use"))}
        for k, beat in enumerate(seg.beats, 1):
            fields[beat.key(k)] = (StoryBeat, Field(description=_describe(beat)))
        fields["sketches"] = (list[str], Field(
            description="[] unless no template can draw this segment: then one sentence per beat for an animator"))
        segments[seg.key] = (create_model(f"Storyboard_{seg.key}", **fields), Field(description=seg.phase))
    return create_model("Storyboard", title=(str, ...), colour_key=(list[TermColour], ...), **segments)


# --------------------------------------------------------------------------
# From a filled storyboard to a script
# --------------------------------------------------------------------------


def assemble(board: BaseModel, plan: list[SegmentPlan], ku: KnowledgeUnit) -> TemplatedDialogueScript:
    """The script the storyboard describes. Visual sentences are placeholders until finish() describes the calls."""
    segments = []
    for seg in plan:
        filled = getattr(board, seg.key)
        beats = [getattr(filled, b.key(k)) for k, b in enumerate(seg.beats, 1)]
        sketches = list(filled.sketches)
        code = bool(sketches) and not any(sb.draw for sb in beats)
        segments.append({
            "phase": seg.phase,
            "source_refs": [r.model_dump() for r in filled.source_refs] or [r.model_dump() for r in ku.source_refs[:1]],
            "drawn": "code" if code else "templates",
            "beats": [{
                "narration": sb.narration.strip(), "speaker": b.speaker, "step": b.step,
                "misconception": b.misconception, "draw": [] if code else list(sb.draw),
                # A drawn beat's sentence is written from its calls in finish(); until then, a placeholder.
                "visual": (sketches[k] if k < len(sketches) else sb.narration) if code else "(drawn from its calls)",
            } for k, (b, sb) in enumerate(zip(seg.beats, beats))],
        })
    return TemplatedDialogueScript.model_validate({
        "ku_id": ku.id, "title": board.title, "style": "dialogue", "visuals": "templates",
        "colour_key": [t.model_dump() for t in _colour_key(board.colour_key)], "segments": segments,
    })


def _colour_key(terms: list[TermColour]) -> list[TermColour]:
    """At most 4 terms, each term and each colour once (validate_script's rules), keeping the first of each."""
    out, colours, names = [], set(), set()
    for t in terms:
        name = t.term.strip().lower()
        if t.colour in colours or name in names:
            continue
        out.append(t)
        colours.add(t.colour)
        names.add(name)
    return out[:4]


OPENERS = ["Lowkey", "Not gonna lie", "For real", "No cap"]


def fix_slang(script: TemplatedDialogueScript, plan: list[SegmentPlan], names: tuple[str, ...] = ()) -> list[str]:
    """Puts the casual phrases where the plan says, in code: a slot without one gets an opener, a line that may
    not have one loses it, and none goes past the cap. `names` (the cast's) keep their capital after an opener.
    Returns what changed."""
    from script_generation_agent.slang import _pattern

    log = []
    beats = [(b, p) for seg, sp in zip(script.segments, plan) for b, p in zip(seg.beats, sp.beats)]
    openers = iter(OPENERS * 3)
    used = sum(len(find_slang(b.narration)) for b, p in beats if p.slang)
    for beat, p in beats:
        found = find_slang(beat.narration)
        if p.slang and not found and used < MIN_SLANG:  # only up to the minimum: every phrase adds words
            used += 1
            line = beat.narration
            first = line.split(" ", 1)[0].strip(",.!?;:")
            keep = first in ("I", "I'm", "I'd", "I’m", "I’d") or first in names or first.startswith(("I'", "I’"))
            rest = line if keep else line[:1].lower() + line[1:]
            beat.narration = f"{next(openers)}, {rest}"
            log.append(f"added a casual phrase: {beat.narration!r}")
        elif found and p.step in NO_SLANG_STEPS:
            # Elsewhere a phrase off its slot is allowed (validate_dialogue only bans these steps); removing it
            # can break the sentence, so this is the only place code takes one out.
            for phrase in found:
                if (stripped := _strip(beat.narration, _pattern(phrase))) is not None:
                    beat.narration = stripped
                    log.append(f"removed {phrase!r} from a {p.step} line")
    cap = max_slang(len(beats))
    used = sum(len(find_slang(b.narration)) for b, _ in beats)
    for beat, p in reversed(beats):
        if used <= cap:
            break
        if not p.slang and (found := find_slang(beat.narration)):
            if (stripped := _strip(beat.narration, _pattern(found[0]))) is not None:
                beat.narration = stripped
                used -= 1
                log.append(f"removed {found[0]!r}: over the cap")
    return log


def _strip(line: str, pattern) -> str | None:
    """The line without the phrase, or None when taking it out would leave a broken sentence: the phrase works as
    an opener ("No cap, it ...") or a closer ("..., no cap.") but not as a clause of its own ("Wait, for real? But
    ..." would become "Wait, ? But ...")."""
    import re

    m = pattern.search(line)
    if m is None:
        return line
    after = line[m.end():].lstrip()
    if after[:1] in ("?", "!") and after[1:].strip():
        return None
    out = re.sub(r"\s+", " ", line[:m.start()] + line[m.end():]).strip()
    out = re.sub(r"^[,;:—\-\s]+", "", out)  # it was an opener
    out = re.sub(r",\s*([.!?])", r"\1", out)  # it was a closer
    out = re.sub(r"\s+([,.!?;:])", r"\1", out)
    if len(out.split()) < 4 or re.search(r"[,;:]\s*[,.!?;:]|[,;:]$", out) or not out[:1].isalnum():
        return None
    return out[:1].upper() + out[1:]


# --------------------------------------------------------------------------
# The calls: code fixes, then one fix call for what is left
# --------------------------------------------------------------------------


class _BeatDraw(BaseModel):
    draw: list[str]


class _SegmentFix(BaseModel):
    segment_index: int
    beats: list[_BeatDraw]


class _Fixes(BaseModel):
    segments: list[_SegmentFix]


def _calls_listing(script: TemplatedDialogueScript, segments) -> str:
    out = []
    for i, (seg, draws) in enumerate(zip(script.segments, segments)):
        if draws is None:
            out.append(f"Segment {i} ({seg.phase}): drawn by an animator, not by templates")
            continue
        out.append(f"Segment {i} ({seg.phase}):")
        out += [f"  beat {k}: [{b.speaker}] {b.narration}\n    draw: {d}"
                for k, (b, d) in enumerate(zip(seg.beats, draws), 1)]
    return "\n".join(out)


def _fix_calls(script, segments, problems, *, ku_id: str, model: str, manifest, system: str, note: str = ""):
    """One call that corrects the calls of the segments with problems code couldn't fix."""
    bad = sorted({p.segment for p in problems})
    listing = (_calls_listing(script, segments) + "\n\nProblems an automatic checker found (what is on screen carries "
               "over between segments; code places every object, so give no areas):\n"
               + "\n".join(f"  - segment {p.segment}: {p.message}" for p in problems)
               + f"\n\nThe lines stay as they are, so make the pictures match them. Return "
                 f"corrected `draw` lists for segments {bad} only, one entry per beat, changing only what you must."
                 + note)
    print(f"[storyboard] {ku_id}: fixing calls in segments {bad}: {'; '.join(p.message for p in problems)[:500]}",
          file=sys.stderr, flush=True)
    try:
        fixes = structured(schema=_Fixes, content=[text_block(listing)], system=system, stage="storyboard_fix",
                           ku_id=ku_id, model=model, max_tokens=8000, manifest=manifest)
    except Exception as e:  # best effort: the code fallback below still makes the calls safe to render
        print(f"[storyboard] {ku_id}: the fix call failed: {e}", file=sys.stderr, flush=True)
        return segments
    out = [None if d is None else [list(b) for b in d] for d in segments]
    for fix in fixes.segments:
        i = fix.segment_index
        if i in bad and out[i] is not None and len(fix.beats) == len(out[i]):
            out[i] = [list(b.draw) for b in fix.beats]
    return out


def _drop_broken(segments, lines, allowed=None):
    """Last resort, in code: drop every call the checker still rejects, so what renders is always valid."""
    from animation_agent.visuals.calls import MAX_CALLS_PER_BEAT, simulate_script

    for _ in range(80):
        # A change the line doesn't say stays (only logged): dropping a step would change every state after it.
        problems = [p for p in simulate_script(segments, lines, allowed=allowed).problems
                    if (p.call is not None and p.kind != "unsaid_change") or p.kind == "too_many_calls"]
        if not problems:
            break
        p = problems[0]
        calls = segments[p.segment][p.beat - 1]
        if p.call is not None and p.call < len(calls):
            print(f"[storyboard] dropped `{calls.pop(p.call)}`: {p.message[-160:]}", file=sys.stderr, flush=True)
        else:
            del calls[MAX_CALLS_PER_BEAT:]
    return segments


def _missing_main(segments, main: str | None):
    """A problem when the template that draws the KU's main picture is never created."""
    from animation_agent.visuals.calls import Problem, _call_name

    if main is None:
        return []
    for draws in segments:
        for calls in draws or []:
            if any(_call_name(text)[1] == main for text in calls):
                return []
    return [Problem(0, 1, None, "missing_picture",
                    f"no segment draws {main}, and this idea's main picture is drawn with it: create it where the "
                    "idea is first shown (by the deliver segment at the latest) and keep acting on it")]


def settle_picture(script: TemplatedDialogueScript, *, ku_id: str, model: str = DEFAULT_MODEL,
                   manifest: RunManifest | None = None, system: str = "", allowed: set[str] | None = None,
                   main: str | None = None, trace=None) -> list:
    """The storyboard's calls made safe to render, per segment and beat: code fixes (a result shown during a
    question or predict line moves to the line that answers; normalize), one fix call for what code can't fix
    (including a template the picture plan didn't choose, `allowed`, or its main template, `main`, never drawn),
    then code drops whatever is still rejected. Before and after the fix call, highlights are made to say what
    they show (visuals/highlights.py: green only on sorted or found cells, no answer shown during its question,
    key colours, ghosts only for the wrong idea). The fix call can't change the worked example's steps (`trace`,
    animation_agent.visuals.trace): code puts them back as they were. This is the picture as it renders: nothing changes it after, so
    the lines can be matched to it (match_lines) before the voices start."""
    from animation_agent.visuals.calls import script_segments
    from animation_agent.visuals.normalize import (
        fill_still,
        hold_reveals,
        normalize_script,
        point_beats,
        still_problems,
    )
    from animation_agent.visuals.highlights import fix_highlights
    from animation_agent.visuals.trace import FIX_NOTE, STEP_ACTIONS, example_name, keep_steps

    segments = script_segments(script)
    lines = [[b.narration for b in seg.beats] for seg in script.segments]
    steps = [[(getattr(b, "step", ""), bool(getattr(b, "misconception", False))) for b in seg.beats]
             for seg in script.segments]

    def held(segs):
        segs, moved = hold_reveals(segs, steps, lines)
        _log(ku_id, moved)
        return segs

    key = {t.term: t.colour for t in script.colour_key}

    def highlighted(segs):
        segs, changed = fix_highlights(segs, steps, lines, key)
        _log(ku_id, changed)
        return segs

    # A line that makes a point changes the picture: code highlights the cells it names where it can, and a
    # note-only beat there goes to the fix call (to be drawn) instead of being cleared.
    segments, filled = fill_still(highlighted(held(segments)), steps, lines)
    _log(ku_id, filled)
    fixed = normalize_script(segments, lines, allowed, keep_text=point_beats(steps))
    _log(ku_id, fixed.log)
    segments = fixed.segments
    # Only problems that break or contradict the picture are worth a call; a segment showing only notes or a
    # count the words don't match is left to the critic.
    worth = ([p for p in fixed.left if p.kind not in ("notes_only", "count")] + _missing_main(segments, main)
             + still_problems(segments, steps))
    if worth:
        note = ""
        if trace is not None and (name := example_name(segments, trace)):
            note = FIX_NOTE.format(name=name, actions=", ".join(sorted(STEP_ACTIONS[trace.template])))
        before = segments
        segments = _fix_calls(script, segments, worth, ku_id=ku_id, model=model, manifest=manifest, system=system,
                              note=note)
        if trace is not None:
            segments, kept = keep_steps(before, segments, trace)
            _log(ku_id, kept)
        segments = normalize_script(highlighted(held(segments)), lines, allowed).segments
    return _drop_broken(segments, lines, allowed)


def _log(ku_id: str, entries) -> None:
    for line in entries:
        print(f"[storyboard] {ku_id}: {line}", file=sys.stderr, flush=True)


# What a line can say that its picture contradicts: the measure of how well the two match, logged for every video
# once its lines are final (scratchpad compare scripts read it back from work.log).
MISMATCH_KINDS = ("unshown_number", "wrong_front", "unsaid_change")


def mismatches(script: TemplatedDialogueScript, segments=None, allowed: set[str] | None = None) -> list:
    """The checker's problems between the lines and the picture (MISMATCH_KINDS)."""
    from animation_agent.visuals.calls import check_script, script_segments

    lines = [[b.narration for b in seg.beats] for seg in script.segments]
    segments = script_segments(script) if segments is None else segments
    return [p for p in check_script(segments, lines, allowed) if p.kind in MISMATCH_KINDS]


def _two_steps(segments) -> list[tuple[int, int]]:
    """(segment, 1-based beat) of each beat showing two or more results (a bisection check with its discard is
    one)."""
    from animation_agent.visuals.calls import _call_name, reveal_flags

    out = []
    for s, (draws, flags) in enumerate(zip(segments, reveal_flags(segments))):
        for b, (calls, f) in enumerate(zip(draws or [], flags or []), 1):
            names = [_call_name(c)[1] for c, hit in zip(calls, f) if hit]
            if len([n for n in names if n != "bisect_check"]) >= 2:
                out.append((s, b))
    return out


def with_pictures(script: TemplatedDialogueScript, segments, *, ku_id: str = "",
                  allowed: set[str] | None = None) -> TemplatedDialogueScript:
    """The script with these calls, and each drawn beat's `visual` written from them (what its calls show)."""
    from animation_agent.visuals.calls import describe_script
    from animation_agent.visuals.normalize import still_beats

    steps = [[(getattr(b, "step", ""), bool(getattr(b, "misconception", False))) for b in seg.beats]
             for seg in script.segments]
    left = mismatches(script, segments, allowed)
    _log(ku_id, [f"lines vs picture: {len(left)} mismatches"
                 + (" (" + "; ".join(f"segment {p.segment} beat {p.beat} {p.kind}" for p in left) + ")"
                    if left else "")])
    if crowded := _two_steps(segments):
        _log(ku_id, ["lines showing two steps: " + ", ".join(f"segment {i} beat {k}" for i, k in crowded)])
    if muddled := [(i, k) for i, seg in enumerate(script.segments) for k, b in enumerate(seg.beats, 1)
                   if self_corrects(b.narration)]:
        _log(ku_id, ["lines that correct themselves: " + ", ".join(f"segment {i} beat {k}" for i, k in muddled)])
    if still := still_beats(segments, steps):
        _log(ku_id, [f"still picture on {len(still)} point-making lines: "
                     + ", ".join(f"segment {s} beat {b}" for s, b in still)])
    said = describe_script(segments)
    data = script.model_dump(mode="json")
    for seg, draws, seg_said in zip(data["segments"], segments, said):
        if draws is None:
            continue
        for beat, d, v in zip(seg["beats"], draws, seg_said):
            beat["draw"], beat["visual"] = d, v
    return TemplatedDialogueScript.model_validate(data)


def finish(script: TemplatedDialogueScript, *, ku_id: str, model: str = DEFAULT_MODEL,
           manifest: RunManifest | None = None, system: str = "", allowed: set[str] | None = None,
           main: str | None = None) -> TemplatedDialogueScript:
    """settle_picture, then with_pictures: the calls made safe and each drawn beat's `visual` written from them
    (the lines as they are; write_storyboard matches them to the settled picture in between)."""
    segments = settle_picture(script, ku_id=ku_id, model=model, manifest=manifest, system=system,
                              allowed=allowed, main=main)
    return with_pictures(script, segments, ku_id=ku_id, allowed=allowed)


# --------------------------------------------------------------------------
# The whole step
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# The lines say what the pictures show
# --------------------------------------------------------------------------
# The writer narrates its own run of an algorithm, and its run can be wrong where the picture's is computed: in
# runs/state-fix-1 bisection on 1, 3, 4, 7, 9, 11, 13, 15 for 11 compared 7, then 11, while the lines said "the
# middle value is nine", then "the middle is thirteen, so we discard the right part". Lines like that name values on
# screen and the right words, so no rule catches them. So before the voices start, one call reads each line beside
# the sentence code computes from its picture (as code will draw it), and rewrites only the lines that contradict
# it; each rewrite is kept only if the script still passes the dialogue checks.

LINES_SYSTEM = """You check a short teaching video's lines against its pictures. Two characters talk; under each \
line is a sentence saying what the picture does during it. Those sentences are computed from the animation itself, \
so they are always right. The lines were written before the animation ran, so a line may be wrong about it.

Rewrite a line when it is marked as correcting itself ("the last four... wait, I mean the last three"): say \
the right thing once. Otherwise rewrite a line only when it contradicts its picture or the pictures before it: it names a different value, middle, \
front, order, count, swap or result than the picture shows, or describes a step the picture doesn't take, or skips \
one it does. "The picture stays as it is" means the line can still talk about the picture before it. Leave every \
other line exactly as it is.

When you rewrite a line:
  - keep its speaker's voice, its job and its length (within a few words). A question stays a question. A predict \
line still asks without giving the answer (its picture's result shows in the next line on purpose). The peer's \
wrong idea stays wrong: it is the misconception the next line corrects, and its picture is a ghost of that idea;
  - keep any opener or slang it has, and add none;
  - write numbers as words, as the lines do;
  - never correct yourself mid-line, and narrate at most one step of the picture;
  - talk about the idea, not the screen ("the middle is seven", never "the picture shows seven");
  - if later lines build on the wrong fact, rewrite them too, so the story stays consistent.
Return only the lines you rewrite, or none if every line fits its picture."""


# A line that corrects itself is hard to follow by ear: in runs/trace-fix-2 the writer's predict line asked about
# "the last three cells, 5, 9 and 3... I mean 5, 9 and 8", and the line call, asked only to fix contradictions,
# made it "the last four cells, 5, 9, 8... wait, I mean the last three". "Wait" alone is a casual opener ("Wait, so
# why...?"), so it counts only after a trailing "...", or before "I mean"/"no"/"actually".
_SELF_CORRECTION = re.compile(r"\bI mean\b|\.\.\.\s*(?:wait|no|sorry|actually|oops)\b|\bscratch that\b"
                              r"|\b(?:wait|sorry|oops),?\s+(?:no|actually)\b", re.IGNORECASE)


def self_corrects(line: str) -> bool:
    return bool(_SELF_CORRECTION.search(line))


class _LineFix(BaseModel):
    segment_index: int
    beat: int = Field(description="1-based, within the segment")
    line: str = Field(description="the rewritten line")


class _LineFixes(BaseModel):
    fixes: list[_LineFix]


def _picture_sentences(script: TemplatedDialogueScript, allowed: set[str] | None) -> list[list[str]]:
    """What each beat's picture shows, as code will draw it (reveals held back, still lines filled, problems code
    can fix fixed), before the fix call."""
    from animation_agent.visuals.calls import describe_script, script_segments
    from animation_agent.visuals.normalize import fill_still, hold_reveals, normalize_script, point_beats

    lines = [[b.narration for b in seg.beats] for seg in script.segments]
    steps = [[(b.step, b.misconception) for b in seg.beats] for seg in script.segments]
    segments, _ = hold_reveals(script_segments(script), steps, lines)
    segments, _ = fill_still(segments, steps, lines)
    segments = normalize_script(segments, lines, allowed, keep_text=point_beats(steps)).segments
    return describe_script(segments)


def match_lines(script: TemplatedDialogueScript, *, ku_id: str, model: str = DEFAULT_MODEL,
                manifest: RunManifest | None = None, allowed: set[str] | None = None,
                accept: Callable[[TemplatedDialogueScript], bool] = lambda s: True,
                segments=None) -> TemplatedDialogueScript:
    """The script with each line that contradicts its picture rewritten (one call). The picture is `segments`
    (settle_picture's calls, as they render), or else what code alone would draw from the script's calls. A
    rewrite is kept only if `accept` still passes the script and the line stays about as long."""
    from animation_agent.visuals.calls import describe_script

    said = _picture_sentences(script, allowed) if segments is None else describe_script(segments)
    listing = []
    for i, (seg, seg_said) in enumerate(zip(script.segments, said)):
        if seg.drawn_by != "templates":
            continue
        listing.append(f"Segment {i} ({seg.phase}):")
        for k, (b, picture) in enumerate(zip(seg.beats, seg_said), 1):
            role = b.step + (", the wrong idea" if b.misconception else "")
            mark = " (corrects itself: rewrite it)" if self_corrects(b.narration) else ""
            listing.append(f"  beat {k} [{b.speaker}, {role}]{mark}: {b.narration}\n    picture: {picture}")
    if not listing:
        return script
    try:
        fixes = structured(schema=_LineFixes, content=[text_block("\n".join(listing))], system=LINES_SYSTEM,
                           stage="storyboard_lines", ku_id=ku_id, model=model, max_tokens=4000, manifest=manifest)
    except Exception as e:  # best effort: the lines as written still pass every check
        print(f"[storyboard] {ku_id}: the line-matching call failed: {e}", file=sys.stderr, flush=True)
        return script
    for fix in fixes.fixes:
        i, k, new = fix.segment_index, fix.beat - 1, " ".join(fix.line.split())
        if not (0 <= i < len(script.segments) and 0 <= k < len(script.segments[i].beats)):
            continue
        old = script.segments[i].beats[k].narration
        n_old, n_new = len(old.split()), len(new.split())
        if new == old or not (0.7 * n_old - 2 <= n_new <= 1.3 * n_old + 2) or self_corrects(new):
            continue
        data = script.model_dump(mode="json")
        data["segments"][i]["beats"][k]["narration"] = new
        candidate = TemplatedDialogueScript.model_validate(data)
        if accept(candidate):
            script = candidate
            print(f"[storyboard] {ku_id}: segment {i} beat {k + 1}: matched the line to its picture: "
                  f"{old!r} -> {new!r}", file=sys.stderr, flush=True)
        else:
            print(f"[storyboard] {ku_id}: segment {i} beat {k + 1}: kept the line (the rewrite fails the dialogue "
                  f"checks): {new!r}", file=sys.stderr, flush=True)
    return script


# Where the lines and the picture disagree, only a new storyboard helps: the lines are final once they pass (the
# voices start), and the fix call can change only the calls. In runs/course-test-2 the merge-step video's slide
# example (ten two-digit numbers) didn't fit MergeSort; the fix call swapped in smaller numbers, and every line
# still said the slide's. So a first draft with a line naming numbers that aren't on screen, a line comparing a
# merge's values the picture doesn't, or a rejected creation call (the fix call would change what it draws) is
# written once more, with those problems.
_REDO_KINDS = ("unshown_number", "wrong_front")
_CREATES = re.compile(r"\s*\w+\s*=\s*[A-Z]\w*\(")


def _redo_problems(script, allowed: set[str] | None) -> list:
    from animation_agent.visuals.calls import check_script, script_segments

    segments = script_segments(script)
    lines = [[b.narration for b in seg.beats] for seg in script.segments]
    out = []
    for p in check_script(segments, lines, allowed):
        call = segments[p.segment][p.beat - 1][p.call] if p.call is not None else ""
        if p.kind in _REDO_KINDS or (p.kind in ("other", "wrong_template") and _CREATES.match(call)):
            out.append(p)
    return out


def _redo_feedback(problems) -> str:
    return ("\n\nIn your previous storyboard the lines and the pictures disagree (an automatic checker found these):\n"
            + "\n".join(f"  - segment {p.segment}, {p.message}" for p in problems)
            + "\nWrite it again with the lines and the pictures together: every number a line names is on screen, "
              "every comparison a line makes is the one the picture makes at that moment, and every template gets "
              "values it accepts. If the slide's example doesn't fit a template, use a smaller example and say its "
              "numbers in the lines.")


# A storyboard over the word limit is kept, only logged: a longer video beats a 13 s rewrite, and in the
# 48-video course test (runs/course-test-1) 24 first drafts ran 264-319 words, 3 of them still over after the
# rewrite, so those KUs got no video at all. Too short still gets a rewrite.
def _over_limit(problem: str, script) -> bool:
    return problem.startswith("word_count=") and script.word_count > DIALOGUE_MAX_WORDS


_PLAN = object()  # write_storyboard(example=...) not given: plan one


def _traced(script: TemplatedDialogueScript, trace, ku_id: str):
    """The script with the worked example's next_step calls expanded into its computed steps, and the problems
    where the draft strayed from them (as checker problems, for the redo)."""
    from animation_agent.visuals.calls import Problem, script_segments
    from animation_agent.visuals.trace import apply_trace

    if trace is None:
        return script, []
    segments, log, strays = apply_trace(script_segments(script), trace)
    _log(ku_id, log + [f"off the worked example: {m}" for _, _, m in strays])
    data = script.model_dump(mode="json")
    for seg, draws in zip(data["segments"], segments):
        if draws is not None:
            for beat, d in zip(seg["beats"], draws):
                beat["draw"] = d
    return (TemplatedDialogueScript.model_validate(data),
            [Problem(s, b, None, "off_trace", m) for s, b, m in strays])


def _example(explainer: str, peer: str, level: int) -> str:
    from script_generation_agent.storyboard_example import render_example

    return render_example(explainer=explainer, peer=peer, level=level)


def write_storyboard(
    ku: KnowledgeUnit,
    corpus: CourseCorpus,
    *,
    level: int,
    prereq_titles: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
    on_lines_ready: Callable | None = None,
    writer_model: str = STORYBOARD_MODEL,
    picture: PicturePlan | None = None,
    example=_PLAN,
) -> TemplatedDialogueScript:
    """A dialogue script with its template calls, from one storyboard call (on `writer_model`; `model` makes
    the fix call and, when `picture` isn't given, the picture plan that picks the templates). For a KU that steps
    through an algorithm, `example` is its traced worked example (animation_agent.visuals.trace.Trace), planned
    with one short call unless given (None: no trace). `on_lines_ready` gets
    the script once its lines are final: after the picture is settled and the lines matched to it, so a fix to
    the picture can't leave a recorded line contradicting it."""
    from script_generation_agent.script_writer import ScriptValidationError, gather_source_material, validate_dialogue
    from syllabyte_common.cast import load_cast

    text_context, image_blocks = gather_source_material(corpus, ku)
    if not text_context:
        raise ScriptValidationError(f"KU {ku.id} cites slides that don't resolve in the corpus: {ku.source_refs}")
    cast = load_cast()
    picture = picture or plan_picture(ku, model=model, manifest=manifest)
    plan = skeleton(level, bool(prereq_titles))
    system = storyboard_system_prompt(level, prereq_titles, explainer=cast.explainer.name, peer=cast.peer.name,
                                      lexicon=lexicon_for_prompt(), example=_example(cast.explainer.name,
                                                                                     cast.peer.name, level),
                                      templates=picture.templates, family=picture.family)
    prompt = build_script_prompt(ku, text_context).replace(
        "Write the 5-segment CLT-bLM script for this Knowledge Unit now.",
        "Fill in the storyboard for this Knowledge Unit now: every beat's picture, then its line.")
    schema = storyboard_model(plan)
    trace = plan_example(ku, picture, text_context, model=model, manifest=manifest) if example is _PLAN else example
    if trace is not None:
        from animation_agent.visuals.trace import trace_brief

        prompt += trace_brief(trace)

    problems: list[str] = []
    feedback = ""
    first = None  # a first draft whose only problem is between its lines and its picture
    for attempt in range(2):  # the plan makes a rejected script rare; one retry with the checker's findings
        board = structured(schema=schema, content=[text_block(prompt + feedback), *image_blocks], system=system,
                           stage=f"storyboard_l{level}", ku_id=ku.id, model=writer_model,
                           effort=STORYBOARD_EFFORT,
                           max_tokens=16000, manifest=manifest)
        script = assemble(board, plan, ku)
        for line in fix_slang(script, plan, (cast.explainer.name, cast.peer.name)):
            print(f"[storyboard] {ku.id}: {line}", file=sys.stderr, flush=True)
        script, off_trace = _traced(script, trace, ku.id)
        found = validate_dialogue(script)
        problems = [p for p in found if not _over_limit(p, script)]
        if len(problems) < len(found):
            print(f"[storyboard] {ku.id}: kept at {script.word_count} words, over the {DIALOGUE_MAX_WORDS}-word "
                  "limit", file=sys.stderr, flush=True)
        if not problems:
            redo = off_trace + _redo_problems(script, set(picture.templates)) if attempt == 0 else []
            if not redo:
                break
            first = script
            print(f"[storyboard] {ku.id}: lines and picture disagree, writing it again: "
                  f"{'; '.join(p.message for p in redo)[:500]}", file=sys.stderr, flush=True)
            feedback = _redo_feedback(redo)
            continue
        print(f"[storyboard] {ku.id}: rejected: {'; '.join(problems)}", file=sys.stderr, flush=True)
        if first is not None:
            print(f"[storyboard] {ku.id}: keeping the first draft", file=sys.stderr, flush=True)
            script = first
            break
        feedback = ("\n\nYour previous storyboard was rejected by the automatic checker: " + "; ".join(problems)
                    + ". Fix these.")
    else:
        raise ScriptValidationError(f"KU {ku.id}: {'; '.join(problems)}")
    # The picture first, settled as it will render; then the lines matched to it; nothing changes either after.
    allowed = set(picture.templates)
    segments = settle_picture(script, ku_id=ku.id, model=model, manifest=manifest, system=system, allowed=allowed,
                              main=picture.main, trace=trace)
    script = match_lines(script, ku_id=ku.id, model=model, manifest=manifest, allowed=allowed, segments=segments,
                         accept=lambda s: not [p for p in validate_dialogue(s) if not _over_limit(p, s)])
    if on_lines_ready is not None:
        on_lines_ready(script)
    return with_pictures(script, segments, ku_id=ku.id, allowed=allowed)


__all__ = ["BeatPlan", "SegmentPlan", "assemble", "finish", "fix_slang", "match_lines", "mismatches",
           "settle_picture", "skeleton", "with_pictures",
           "storyboard_model", "write_storyboard", "DIALOGUE_MAX_WORDS", "DIALOGUE_MIN_WORDS"]
