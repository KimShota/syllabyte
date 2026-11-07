"""
Highlights that say what they show: code rules for the colours and cells a writer highlights. No Manim import.

The computed steps make the list right, but the highlights around them are the writer's, and in runs/trace-fix-1
and runs/trace-fix-2 they were most of what the critic still marked down in the selection-sort video:
  - an unsorted 5, 2, 8 turned GREEN under the objective (twice), though green is what a sorted or found cell
    looks like, so it showed an unsorted prefix as sorted;
  - a predict line ("which is the minimum of 5, 9 and 8?") highlighting 5, its answer, before the answer;
  - colours outside the video's colour key (yellow, teal);
  - a red "wrong idea" ghost drawn around a peer's correct answer.
So, on a list (ArrayBars):
  - a GREEN highlight may colour only cells that are sorted or found (specs.green_cells); one that colours any
    other cell is dropped (unless the list was changed by hand with swap or set_value: code can't tell then);
  - a question or predict line may not highlight the cell its answer step lands on (the next step
    on that list in the segment: selection's minimum, insertion's place, bisection's middle or discarded half, a
    scan or found that hits, in this segment or a later one): that call is dropped, and the step shows it on the
    line that answers;
  - a highlight of one or two cells whose colour isn't in the colour key takes the colour of the one key term
    its line names, if it names exactly one (never green on cells that aren't sorted or found);
  - a ghost (a wrong idea) outside the wrong-idea line becomes a highlight of the same cells.
"""

from __future__ import annotations

import ast
import copy
import re

from animation_agent.visuals.calls import _check, _Live, parse_call
from animation_agent.visuals.specs import REGISTRY, green_cells

ASKING_STEPS = ("question", "predict")
_STEPS = {"selection_step", "insertion_step", "bisect_check", "bisect_discard", "bisect_step", "scan", "found"}
NEUTRAL = "TEAL"  # a highlight that names no key term: the examples' colour for "look here"


def _indices(call) -> list[int]:
    if "indices" in call.args:
        return list(call.args["indices"])
    if "index" in call.args:
        return [call.args["index"]]
    return []


def _answer_cells(state: dict, action: str, args: dict) -> set[int]:
    """The cells the step reveals as its result, on a copy of the list's state."""
    spec = REGISTRY["ArrayBars"].all_actions()[action]
    st = copy.deepcopy(state)
    try:
        a = spec.args.model_validate(args)
        if spec.check and spec.check(st, a):
            return set()
    except Exception:  # noqa: BLE001 - a broken step reveals nothing; the checker reports it
        return set()
    if action in ("selection_step", "insertion_step"):
        ev = st["last_sort"][-1]
        if action == "selection_step":
            return {ev["min"]}
        return {ev["to"]} if ev["to"] != ev["from"] else set()  # a value that stays isn't the answer
    if action in ("bisect_check",):
        lo, hi = st["bisect"]["range"]
        return {(lo + hi) // 2}
    if action in ("bisect_discard", "bisect_step"):
        mid, lo, hi, found = st["bisect"]["last"]
        if found:
            return {mid}
        v, t = st["values"], st["bisect"]["target"]
        return set(range(lo, mid + 1)) if v[mid] < t else set(range(mid, hi + 1))
    if action in ("scan", "found"):
        return set(st.get("found", set())) - set(state.get("found", set()))
    return set()


def _next_step(segments: list[list[list[str]] | None], s: int, b: int, name: str, live: dict,
               ) -> tuple[str, dict] | None:
    """The first step on `name` after beat `b` (0-based) of segment `s`, in it or a later one (the list stays on
    screen): (action, args)."""
    later = [calls for draws in segments[s + 1:] if draws is not None for calls in draws]
    for calls in segments[s][b + 1:] + later:
        for text in calls:
            try:
                call = parse_call(text, {n: o.template for n, o in live.items()})
            except Exception:  # noqa: BLE001
                continue
            if call.target == name and call.action in _STEPS:
                return call.action, call.args
            if call.target == name and call.action is None:
                return None  # created again: what came before is gone
    return None


def _with_colour(text: str, colour: str) -> str:
    """The call with its colour= argument set to `colour`."""
    tree = ast.parse(text.strip())
    call = tree.body[0].value
    call.keywords = [kw for kw in call.keywords if kw.arg != "colour"] + [ast.keyword("colour", ast.Constant(colour))]
    return ast.unparse(tree).replace("'", '"')


def _key_colour(line: str, key: dict[str, str]) -> str | None:
    """The colour of the one key term the line names, if it names exactly one."""
    named = {colour for term, colour in key.items()
             if re.search(r"\b" + re.escape(term.lower()) + r"\b", line.lower())}
    return named.pop() if len(named) == 1 else None


def fix_highlights(segments: list[list[list[str]] | None], steps: list[list[tuple[str, bool]]],
                   lines: list[list[str]], key: dict[str, str] | None = None,
                   ) -> tuple[list[list[list[str]] | None], list[str]]:
    """The calls with the rules above applied to every list. `steps` gives each beat's (step, is the wrong idea);
    `key` maps the colour key's terms to their colours. Returns the calls and a log."""
    key = key or {}
    key_colours = set(key.values())
    out: list[list[list[str]] | None] = []
    log: list[str] = []
    live: dict[str, _Live] = {}
    for s, draws in enumerate(segments):
        if draws is None:
            out.append(None)
            continue
        seg: list[list[str]] = []
        for b, calls in enumerate(draws):
            step, wrong = steps[s][b] if s < len(steps) and b < len(steps[s]) else ("", False)
            line = lines[s][b] if s < len(lines) and b < len(lines[s]) else ""
            beat = []
            for text in calls:
                new = text
                try:
                    call = parse_call(text, {n: o.template for n, o in live.items()})
                except Exception:  # noqa: BLE001 - the checker reports it
                    call = None
                if call is not None and call.template == "ArrayBars" and call.action in ("highlight", "ghost",
                                                                                           "point"):
                    state = live[call.target].state
                    cells = _indices(call)
                    where = f"segment {s} beat {b + 1}"
                    if call.action == "ghost" and not wrong:
                        colour = _key_colour(line, key) or NEUTRAL
                        new = f'{call.target}.highlight(indices={cells}, colour="{colour}")'
                        log.append(f"{where}: `{text}` drew a wrong idea on a line that isn't one; "
                                   f"highlighted the cells instead")
                        call = parse_call(new, {n: o.template for n, o in live.items()})
                    if call.action == "highlight":
                        colour = call.args.get("colour", "YELLOW")
                        # A key term names one role (the minimum, the target, the middle), so only a highlight
                        # of a cell or two takes its colour; a wider one is left as it is.
                        legit_green = state.get("edited") or set(cells) <= green_cells(state)
                        if (key_colours and colour not in key_colours and len(cells) <= 2
                                and (better := _key_colour(line, key)) and better != colour
                                and (better != "GREEN" or legit_green)):
                            log.append(f"{where}: `{text}` used {colour}, not in the colour key; recoloured "
                                       f"{better}, the colour of the term the line names")
                            new, colour = _with_colour(new, better), better
                        # A list changed by hand (swap, set_value) may have cells in place that code can't know.
                        if colour == "GREEN" and not legit_green:
                            log.append(f"{where}: dropped `{text}`: green means sorted or found, and "
                                       f"{sorted(set(cells) - green_cells(state))} aren't")
                            continue
                    if step in ASKING_STEPS and not wrong and cells and call.action == "highlight":
                        nxt = _next_step(segments, s, b, call.target, live)
                        answer = _answer_cells(state, *nxt) if nxt else set()
                        if answer and set(cells) <= answer:
                            log.append(f"{where} ({step}): dropped `{text}`, which shows the answer before the "
                                       "line that gives it")
                            continue
                try:
                    _check(parse_call(new, {n: o.template for n, o in live.items()}), live)
                except Exception:  # noqa: BLE001
                    pass
                beat.append(new)
            seg.append(beat)
        out.append(seg)
    return out, log


__all__ = ["fix_highlights"]
