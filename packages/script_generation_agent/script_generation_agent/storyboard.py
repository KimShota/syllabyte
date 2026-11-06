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
from script_generation_agent.picture_plan import PicturePlan, plan_picture
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


def _fix_calls(script, segments, problems, *, ku_id: str, model: str, manifest, system: str):
    """One call that corrects the calls of the segments with problems code couldn't fix."""
    bad = sorted({p.segment for p in problems})
    listing = (_calls_listing(script, segments) + "\n\nProblems an automatic checker found (what is on screen carries "
               "over between segments; code places every object, so give no areas):\n"
               + "\n".join(f"  - segment {p.segment}: {p.message}" for p in problems)
               + f"\n\nThe lines are final (their voices are recorded), so make the pictures match them. Return "
                 f"corrected `draw` lists for segments {bad} only, one entry per beat, changing only what you must.")
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
        problems = [p for p in simulate_script(segments, lines, allowed=allowed).problems if p.call is not None
                    or p.kind == "too_many_calls"]
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


def finish(script: TemplatedDialogueScript, *, ku_id: str, model: str = DEFAULT_MODEL,
           manifest: RunManifest | None = None, system: str = "", allowed: set[str] | None = None,
           main: str | None = None) -> TemplatedDialogueScript:
    """The storyboard's calls made safe to render and its visual sentences written: code fixes (a result shown
    during a question or predict line moves to the line that answers; normalize), one fix call for what code
    can't fix (including a template the picture plan didn't choose, `allowed`, or its main template, `main`, never
    drawn), then code drops whatever is still rejected. Each drawn beat's `visual` is then what its calls show."""
    from animation_agent.visuals.calls import describe_script, script_segments
    from animation_agent.visuals.normalize import hold_reveals, normalize_script

    segments = script_segments(script)
    lines = [[b.narration for b in seg.beats] for seg in script.segments]
    steps = [[(getattr(b, "step", ""), bool(getattr(b, "misconception", False))) for b in seg.beats]
             for seg in script.segments]

    def held(segs):
        segs, moved = hold_reveals(segs, steps, lines)
        for line in moved:
            print(f"[storyboard] {ku_id}: {line}", file=sys.stderr, flush=True)
        return segs

    fixed = normalize_script(held(segments), lines, allowed)
    for line in fixed.log:
        print(f"[storyboard] {ku_id}: {line}", file=sys.stderr, flush=True)
    segments = fixed.segments
    # Only problems that break or contradict the picture are worth a call; a segment showing only notes or a
    # count the words don't match is left to the critic.
    worth = [p for p in fixed.left if p.kind not in ("notes_only", "count")] + _missing_main(segments, main)
    if worth:
        segments = _fix_calls(script, segments, worth, ku_id=ku_id, model=model, manifest=manifest, system=system)
        segments = normalize_script(held(segments), lines, allowed).segments
    segments = _drop_broken(segments, lines, allowed)
    said = describe_script(segments)
    data = script.model_dump(mode="json")
    for seg, draws, seg_said in zip(data["segments"], segments, said):
        if draws is None:
            continue
        for beat, d, v in zip(seg["beats"], draws, seg_said):
            beat["draw"], beat["visual"] = d, v
    return TemplatedDialogueScript.model_validate(data)


# --------------------------------------------------------------------------
# The whole step
# --------------------------------------------------------------------------


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
) -> TemplatedDialogueScript:
    """A dialogue script with its template calls, from one storyboard call (on `writer_model`; `model` makes
    the fix call and, when `picture` isn't given, the picture plan that picks the templates). `on_lines_ready` gets
    the script as soon as its lines are final (before the calls are checked), so the voices can start."""
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
        found = validate_dialogue(script)
        problems = [p for p in found if not _over_limit(p, script)]
        if len(problems) < len(found):
            print(f"[storyboard] {ku.id}: kept at {script.word_count} words, over the {DIALOGUE_MAX_WORDS}-word "
                  "limit", file=sys.stderr, flush=True)
        if not problems:
            redo = _redo_problems(script, set(picture.templates)) if attempt == 0 else []
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
    if on_lines_ready is not None:
        on_lines_ready(script)
    return finish(script, ku_id=ku.id, model=model, manifest=manifest, system=system,
                  allowed=set(picture.templates), main=picture.main)


__all__ = ["BeatPlan", "SegmentPlan", "assemble", "finish", "fix_slang", "skeleton", "storyboard_model",
           "write_storyboard", "DIALOGUE_MAX_WORDS", "DIALOGUE_MIN_WORDS"]
