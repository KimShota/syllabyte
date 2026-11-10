"""
Fixing a script's template calls in code, so a storyboard needs no LLM repair for mechanical mistakes.

Across the template pilots, most rejected calls were bookkeeping a model is bad at (runs/template-videos-*):
areas that were too small or overlapped, objects not re-created in a new segment, notes a few characters too
long, too many calls in a beat, zero vectors, a vector off the grid. normalize_script:

  1. lays out every object itself: the writer never picks an area. Each object keeps one area for its whole
     life, chosen so that everything on screen at the same time fits (a diagram gets the most room);
  2. then simulates the script (calls.simulate_script) and, for each problem it knows how to fix, edits the
     calls and simulates again: it drops a note that is too long, repeats the line or is the beat's only picture,
     a zero vector, a guess hidden under a real vector, or a call on an object that doesn't exist, and it widens
     a grid whose vector falls off it.

What is left (a formula too long to read, an index outside the list, ...) is returned for a fix call.
No Manim import.
"""

from __future__ import annotations

from dataclasses import dataclass

from animation_agent.visuals.calls import (
    Call,
    CallError,
    Problem,
    parse_call,
    reveal_flags,
    simulate_script,
)
from animation_agent.visuals.specs import AREAS, REGISTRY, areas_overlap

MAX_EXTENT = 5  # LinearMap2D's largest grid
MAX_PASSES = 40  # one fix per pass, then simulate again (cheap: no Manim)


# --------------------------------------------------------------------------
# Writing calls back out
# --------------------------------------------------------------------------


def _literal(value) -> str:
    """A Python literal that calls.parse_call reads back as `value` (it reads every string as a raw string, so
    a string is written between quotes it doesn't contain, without escaping its backslashes)."""
    if isinstance(value, str):
        for q in ('"', "'"):
            if q not in value and not value.endswith("\\"):
                return f"{q}{value}{q}"
        raise ValueError(f"can't write {value!r} as a call argument")
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_literal(k)}: {_literal(v)}" for k, v in value.items()) + "}"
    raise ValueError(f"can't write {value!r} as a call argument")


def format_call(call: Call) -> str:
    args = ", ".join(f"{k}={_literal(v)}" for k, v in call.args.items())
    if call.action is None:
        return f"{call.target} = {call.template}({args})"
    return f"{call.target}.{call.action}({args})"


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


@dataclass
class _Object:
    template: str
    start: int  # global beat index of its creation
    end: int  # last global beat it is on screen
    where: tuple[int, int, int]  # (segment, beat, call) of its creation
    area: str | None = None

    @property
    def is_diagram(self) -> bool:
        return REGISTRY[self.template].min_rows >= 3


# Preferred areas, best first: a diagram wants room, a formula or note sits above it.
_DIAGRAM_ALONE = ["full"]
_DIAGRAM_SHARED = ["bottom_two_thirds", "bottom_half", "top_two_thirds", "top_half"]
_SMALL_ALONE = {"EquationSteps": ["full", "top_two_thirds", "top_half"], "Note": ["top_third", "middle_third"]}
_SMALL_SHARED = ["top_third", "top_half", "bottom_third", "middle_third", "bottom_half"]


def _objects(segments: list[list[list[str]] | None]) -> list[_Object]:
    """Every object the calls create, with the beats it is on screen (objects carry over between segments)."""
    objects: list[_Object] = []
    live: dict[str, _Object] = {}
    templates: dict[str, str] = {}
    g = 0
    for s, draws in enumerate(segments):
        for b, calls in enumerate(draws or []):
            for c, text in enumerate(calls):
                try:
                    call = parse_call(text, templates)
                except CallError:
                    continue
                if call.action is None:
                    if call.target in live:
                        live.pop(call.target).end = g
                    obj = _Object(call.template, g, -1, (s, b, c))
                    objects.append(obj)
                    live[call.target] = obj
                    templates[call.target] = call.template
                elif call.action == "remove" and call.target in live:
                    live.pop(call.target).end = g
            g += 1
    for obj in live.values():
        obj.end = g
    return objects


def _lay_out(objects: list[_Object]) -> None:
    # Diagrams first, so a note never takes the room a later diagram needs.
    for obj in sorted(objects, key=lambda o: (not o.is_diagram, o.start)):
        together = [o for o in objects if o is not obj and o.start <= obj.end and obj.start <= o.end]
        if obj.is_diagram and any(o.is_diagram for o in together):
            choices = ["bottom_half", "top_half"]  # two diagrams at once: half the frame each
        elif obj.is_diagram:
            choices = _DIAGRAM_SHARED if together else _DIAGRAM_ALONE + _DIAGRAM_SHARED
        else:
            alone = _SMALL_ALONE.get(obj.template, ["top_third"])
            choices = _SMALL_SHARED if together else alone + _SMALL_SHARED
        spec = REGISTRY[obj.template]
        taken = [o.area for o in together if o.area is not None]
        for area in choices:
            first, last = AREAS[area]
            if last - first + 1 >= spec.min_rows and not any(areas_overlap(area, t) for t in taken):
                obj.area = area
                break


def lay_out(segments: list[list[list[str]] | None]) -> list[list[list[str]] | None]:
    """The calls with every object's area chosen by code (any area the writer gave is replaced) and `move` calls
    dropped (an object keeps its area). An object that can't be placed keeps the writer's area."""
    objects = _objects(segments)
    _lay_out(objects)
    placed = {o.where: o.area for o in objects if o.area is not None}
    out: list[list[list[str]] | None] = []
    templates: dict[str, str] = {}
    for s, draws in enumerate(segments):
        if draws is None:
            out.append(None)
            continue
        seg = []
        for b, calls in enumerate(draws):
            beat = []
            for c, text in enumerate(calls):
                try:
                    call = parse_call(text, templates)
                except CallError:
                    beat.append(text)
                    continue
                if call.action is None:
                    templates[call.target] = call.template
                    if (s, b, c) in placed:
                        call.args = {k: v for k, v in call.args.items() if k != "area"} | {"area": placed[(s, b, c)]}
                        text = format_call(call)
                elif call.action == "move":
                    continue
                beat.append(text)
            seg.append(beat)
        out.append(seg)
    return out


# --------------------------------------------------------------------------
# Fixing what the simulation finds
# --------------------------------------------------------------------------

# Problems fixed by dropping the call: what it adds is a note, a highlight the line doesn't name, or nothing the
# viewer could see.
_DROP = {"echo", "zero_vector", "hidden_ghost", "not_created", "unmentioned"}


@dataclass
class Fixed:
    segments: list[list[list[str]] | None]
    left: list[Problem]  # problems code couldn't fix
    log: list[str]  # what was changed, for the run log


def _is_note(text: str) -> bool:
    from animation_agent.visuals.calls import _call_name

    _, name = _call_name(text)
    return name in ("Note", "note", "say")


def _creation_of(segments, s: int, b: int, name: str) -> tuple[int, int, int] | None:
    """Where the object called `name` that is on screen at (segment s, beat b) was created."""
    found = None
    for si, draws in enumerate(segments[: s + 1]):
        for bi, calls in enumerate(draws or []):
            if si == s and bi > b:
                break
            for ci, text in enumerate(calls):
                if text.split("=")[0].strip() == name and "(" in text.split("=", 1)[-1]:
                    found = (si, bi, ci)
    return found


def _widen(segments, s: int, b: int, c: int) -> str | None:
    """Gives the grid the call at (s, b, c) acts on (or creates) one more unit of extent; None if it can't grow."""
    text = segments[s][b][c]
    name = text.split("=")[0].strip() if "=" in text.split("(")[0] else text.split(".")[0].strip()
    where = _creation_of(segments, s, b, name)
    if where is None:
        return None
    cs, cb, cc = where
    call = parse_call(segments[cs][cb][cc], {})
    extent = int(call.args.get("extent", 3))
    if extent >= MAX_EXTENT:
        return None
    call.args["extent"] = extent + 1
    segments[cs][cb][cc] = format_call(call)
    return f"widened {name}'s grid to {extent + 1}"


def _drop_title(text: str) -> str | None:
    try:
        call = parse_call(text, {})
    except CallError:
        return None
    if call.action is None and "title" in call.args:
        call.args.pop("title")
        return format_call(call)
    return None


def normalize_script(segments: list[list[list[str]] | None], lines: list[list[str]] | None = None,
                     allowed: set[str] | None = None, keep_text: set[tuple[int, int]] | frozenset = frozenset(),
                     keep_echo: bool = False) -> Fixed:
    """The calls laid out by code, with every problem it can fix fixed (module docstring). `lines` are each
    beat's narration, for the checks against the words; `allowed`, the templates the KU's picture plan chose.
    A text-only beat in `keep_text` ((segment, 1-based beat)) is left for the fix call to draw, not cleared. With
    `keep_echo` a note isn't dropped for repeating its line: the lines are only the planner's points
    (storyboard_plan), and the real lines are checked for echoes once written."""
    segs = segments
    log: list[str] = []
    for _ in range(MAX_PASSES):
        segs = lay_out(segs)  # again after every fix: a dropped note frees room
        problems = simulate_script(segs, lines, allowed=allowed).problems
        changed = False
        # Highest call first within a beat, so dropping a call doesn't shift the next one's index.
        for p in sorted(problems, key=lambda p: (p.segment, p.beat, -(p.call if p.call is not None else -1))):
            calls = segs[p.segment][p.beat - 1]
            if p.kind in _DROP and not (keep_echo and p.kind == "echo") and p.call is not None and p.call < len(calls):
                log.append(f"segment {p.segment} beat {p.beat}: dropped `{calls.pop(p.call)}` ({p.kind})")
                changed = True
            elif p.kind == "text_only" and calls and (p.segment, p.beat) not in keep_text:
                log.append(f"segment {p.segment} beat {p.beat}: dropped its text-only calls {calls}")
                calls.clear()
                changed = True
            elif p.kind == "too_long" and p.call is not None and p.call < len(calls):
                text = calls[p.call]
                if (fixed := _drop_title(text)) is not None and "title" in p.message.split("`: ")[-1]:
                    calls[p.call] = fixed
                    log.append(f"segment {p.segment} beat {p.beat}: dropped a title too long to read")
                    changed = True
                elif _is_note(text):
                    log.append(f"segment {p.segment} beat {p.beat}: dropped `{calls.pop(p.call)}` (too long)")
                    changed = True
            elif p.kind == "off_grid" and p.call is not None and p.call < len(calls):
                if (what := _widen(segs, p.segment, p.beat - 1, p.call)) is not None:
                    log.append(f"segment {p.segment} beat {p.beat}: {what}")
                    changed = True
            if changed:
                break  # simulate again: one fix can clear (or change) the problems after it
        if not changed:
            return Fixed(segs, problems, log)
    segs = lay_out(segs)
    return Fixed(segs, simulate_script(segs, lines, allowed=allowed).problems, log)


# --------------------------------------------------------------------------
# A question or predict line doesn't show its own answer
# --------------------------------------------------------------------------

# The course test's most common picture issue (51 of 299, in 31 of 42 videos): the picture gave the answer away
# during the line that asks for it, e.g. a scan reaching the target while the line says "pause: how many checks?".
ASKING_STEPS = ("question", "predict")


def hold_reveals(segments: list[list[list[str]] | None], steps: list[list[tuple[str, bool]]],
                 lines: list[list[str]] | None = None) -> tuple[list[list[list[str]] | None], list[str]]:
    """Moves every call that shows a result (ActionSpec.reveals) out of a question or predict line, to the front of
    the next line in its segment that answers (not a question, not the peer's wrong idea); with no such line, the
    call is dropped. `steps` gives each beat's (step, is the wrong idea), per segment. With `lines`, a move that
    would leave a line comparing a merge's values the picture doesn't (wrong_front) is not made: there the call
    sets up the question rather than answering it ("the result holds one; now, five or two?"). Returns the calls
    and a log."""
    flags = reveal_flags(segments)
    out = [None if d is None else [list(b) for b in d] for d in segments]
    log: list[str] = []
    for s, draws in enumerate(out):
        if draws is None:
            continue
        for b, calls in enumerate(draws):
            if b >= len(steps[s]) or steps[s][b][0] not in ASKING_STEPS:
                continue
            held = [c for c, f in zip(calls, flags[s][b]) if f]
            if not held:
                continue
            before = [list(beat) for beat in draws]
            draws[b] = [c for c, f in zip(calls, flags[s][b]) if not f]
            answer = next((k for k in range(b + 1, len(draws))
                           if steps[s][k][0] not in ASKING_STEPS and not steps[s][k][1]), None)
            if answer is None:
                log.append(f"segment {s} beat {b + 1} ({steps[s][b][0]}): dropped {held}, which would show the answer")
                continue
            draws[answer] = held + draws[answer]
            if lines is not None and _out_of_step(out, lines, s) > _out_of_step(
                    [*out[:s], before, *out[s + 1:]], lines, s):
                draws[:] = before  # in place: the loop is walking this segment
                log.append(f"segment {s} beat {b + 1} ({steps[s][b][0]}): kept {held}, which sets up the question "
                           "the line asks")
                continue
            flags[s][answer] = [True] * len(held) + flags[s][answer]
            log.append(f"segment {s} beat {b + 1} ({steps[s][b][0]}): moved {held} to beat {answer + 1}, the line "
                       "that answers")
    return out, log


def _out_of_step(segments, lines, s: int) -> int:
    """How many lines of segment `s` compare a merge's values that its picture doesn't."""
    return sum(1 for p in simulate_script(segments, lines).problems if p.segment == s and p.kind == "wrong_front")


# --------------------------------------------------------------------------
# A line that makes a point changes the picture
# --------------------------------------------------------------------------
# Static pictures (plan/one-shot-storyboard-plan.md, "Static pictures"): of the 100 drawn beats with no picture
# change in the course tests, about 57 were emptied by code (a note-only beat cleared as text_only), and the critic's
# complaints fell on objective, explaining and recap lines. A question, a predict line or the wrong idea may keep
# the picture: the viewer is thinking, and the critic agrees ("the predict line is fine to leave still").

def point_beats(steps: list[list[tuple[str, bool]]]) -> set[tuple[int, int]]:
    """(segment, 1-based beat) of every line that makes a point: not a question, a predict line or the wrong idea."""
    return {(s, b + 1) for s, seg in enumerate(steps) for b, (step, wrong) in enumerate(seg)
            if step not in ASKING_STEPS and not wrong}


def still_beats(segments: list[list[list[str]] | None], steps: list[list[tuple[str, bool]]],
                text_too: bool = True) -> list[tuple[int, int]]:
    """The point-making beats whose calls don't change the diagram: none at all, or (with `text_too`) only text."""
    from animation_agent.visuals.calls import _only_text

    out = []
    for s, b in sorted(point_beats(steps)):
        draws = segments[s] if s < len(segments) else None
        if draws is None or b > len(draws):
            continue
        calls = draws[b - 1]
        if not calls or (text_too and all(_only_text(c) for c in calls)):
            out.append((s, b))
    return out


def fill_still(segments: list[list[list[str]] | None], steps: list[list[tuple[str, bool]]],
               lines: list[list[str]]) -> tuple[list[list[list[str]] | None], list[str]]:
    """In code, no LLM: a still point-making beat whose line says values of a list on screen highlights them."""
    from animation_agent.visuals.calls import live_after, named_cells

    out = [None if d is None else [list(b) for b in d] for d in segments]
    log = []
    for s, b in still_beats(out, steps):
        call = named_cells(live_after([*out[:s], out[s][:b - 1]]), lines[s][b - 1])
        if call is not None:
            out[s][b - 1].append(call)
            log.append(f"segment {s} beat {b}: the picture was still; added `{call}`, the cells the line names")
    return out, log


def still_problems(segments: list[list[list[str]] | None], steps: list[list[tuple[str, bool]]]) -> list[Problem]:
    """A problem for the fix call per point-making beat that draws nothing (text-only ones are text_only)."""
    return [Problem(s, b, None, "still",
                    f"beat {b}: the line makes a point, but the picture doesn't change; add a call that shows it in "
                    "the diagram (highlight or point at what it names, take a step, ghost a value, write the "
                    "formula), not only a note")
            for s, b in still_beats(segments, steps, text_too=False)]
