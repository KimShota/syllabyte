"""
What each visual template takes and can do, without importing Manim.

The script writer's prompt is built from these (`template_cards`), and calls.py checks a script's calls against
them before anything renders. The drawing classes (array_bars.py, ...) implement the same names: every action
here is a method there with the same arguments (tests/test_visual_templates.py checks this).

Logic a drawing has to get right, like which half bisection discards, lives here as plain functions, so the
checker and the drawing compute the same thing.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Bump when a template draws differently (or the call language changes): it is part of the cache key of every
# video drawn with templates (syllabyte_common.video_jobs.video_key), so those videos are made again.
TEMPLATES_VERSION = "6"  # 6: MergeSort, Graph, FunctionPlot, computed sorts, picture plans, reveals held (5: overlapping formula pieces, doubled backslashes, a failed action skipped; 4: ghost outlines clear of notes; 3: storyboards)

# --------------------------------------------------------------------------
# Shared vocabulary
# --------------------------------------------------------------------------

# Where a template sits: bands of the six grid rows (layout.GRID_ROWS), the full width of the frame.
AREAS: dict[str, tuple[int, int]] = {
    "full": (0, 5),
    "top_half": (0, 2),
    "bottom_half": (3, 5),
    "top_third": (0, 1),
    "middle_third": (2, 3),
    "bottom_third": (4, 5),
    "top_two_thirds": (0, 3),
    "bottom_two_thirds": (2, 5),
}
Area = Literal[
    "full", "top_half", "bottom_half", "top_third", "middle_third", "bottom_third",
    "top_two_thirds", "bottom_two_thirds",
]

# The script's colour-key colours, plus white and grey.
Colour = Literal["BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PURPLE", "TEAL", "PINK", "GOLD", "WHITE", "GREY"]


def areas_overlap(a: str, b: str) -> bool:
    (a0, a1), (b0, b1) = AREAS[a], AREAS[b]
    return a0 <= b1 and b0 <= a1


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(_Args):
    pass


class MoveArgs(_Args):
    area: Area


def _short(limit: int):
    def check(value: str | None) -> str | None:
        if value is not None and len(value) > limit:
            raise ValueError(f"is {len(value)} characters; at most {limit} fit on screen")
        return value
    return check


# How many symbols a formula may show across the frame at a readable size (TeX font 40 in 4 units).
MAX_TEX_SYMBOLS = 22


def tex_symbols(tex: str) -> int:
    """Roughly how many symbols a TeX formula shows: a command like \\lambda counts as one, layout commands and
    braces as none."""
    import re

    s = re.sub(r"\\(begin|end)\{[a-z*]+\}", "", tex)
    s = re.sub(r"\\(left|right|,|;|!|quad|qquad|cdot|mathrm|text|operatorname)\b", "", s)
    s = re.sub(r"\\[A-Za-z]+", "x", s)
    return len(re.sub(r"[\s{}^_&\\]", "", s))


def _readable_tex(tex: str | None) -> str | None:
    if tex is not None and (n := tex_symbols(tex)) > MAX_TEX_SYMBOLS:
        raise ValueError(f"shows about {n} symbols; at most {MAX_TEX_SYMBOLS} stay readable. Split it over two "
                         "lines (then) or shorten it")
    return tex


@dataclass
class ActionSpec:
    doc: str
    args: type[BaseModel] = NoArgs
    # Checks the call against what the object holds at that point (e.g. an index is inside the list) and updates
    # that state. Returns a problem, or None.
    check: Callable[[dict, BaseModel], str | None] | None = None
    # What the call shows, in words, from the object's state after `check` ran: the line's `visual` sentence is
    # built from these, so it says exactly what is drawn (calls.describe_segment). None: the doc's first sentence.
    says: Callable[[dict, BaseModel], str] | None = None
    # Whether the call shows a result (a match found, a half ruled out, a sort step, a transform). A question or
    # predict line must not show its own answer, so code moves such a call to the line that answers
    # (normalize.hold_reveals). A callable decides from the state before the call, e.g. a scan reveals only when
    # it reaches the target.
    reveals: bool | Callable[[dict, BaseModel], bool] = False


@dataclass
class TemplateSpec:
    name: str
    family: str
    purpose: str
    params: type[BaseModel]
    actions: dict[str, ActionSpec]
    example: list[list[str]]  # one segment's beats, each a list of calls
    init_state: Callable[[BaseModel], dict] = lambda params: {}
    min_rows: int = 1  # grid rows (of 6) its area must span to stay legible
    common_actions: dict[str, ActionSpec] = field(default_factory=lambda: dict(COMMON_ACTIONS))
    noun: str = "picture"  # what the object is called in a visual sentence ("the list", "the grid")
    describe: Callable[[BaseModel], str] | None = None  # what creating it shows, in words

    def all_actions(self) -> dict[str, ActionSpec]:
        return {**self.actions, **self.common_actions}


COMMON_ACTIONS = {
    "remove": ActionSpec("Fade it out. Its name can't be used again in this segment.",
                         says=lambda s, a: f"the {s['_noun']} fades out"),
    "move": ActionSpec("Slide it, shrinking or growing to fit, into another area.", MoveArgs,
                       says=lambda s, a: f"the {s['_noun']} slides into the {_area_words(a.area)}"),
}


def _area_words(area: str) -> str:
    return "whole frame" if area == "full" else area.replace("_", " ")


def _num(x) -> str:
    """A number as a visual sentence writes it: 3 not 3.0, two decimals at most."""
    return f"{round(float(x), 2):g}" if isinstance(x, int | float) else str(x)


def _matrix_words(m: list[list[float]]) -> str:
    return "[[" + "], [".join(", ".join(_num(x) for x in row) for row in m) + "]]"


# --------------------------------------------------------------------------
# ArrayBars: a list or array as cells (or bars), with pointers
# --------------------------------------------------------------------------

Value = int | float | str
MAX_CELLS = 10


def bisect_next(values: list[float], lo: int, hi: int, target: float) -> tuple[int, int, int, bool]:
    """One bisection step on values[lo..hi]: (mid, new_lo, new_hi, found)."""
    mid = (lo + hi) // 2
    if values[mid] == target:
        return mid, lo, hi, True
    if values[mid] < target:
        return mid, mid + 1, hi, False
    return mid, lo, mid - 1, False


class ArrayParams(_Args):
    values: list[Value] = Field(description="the entries, left to right (1-10 of them)")
    style: Literal["cells", "bars"] = Field(
        "cells", description='"cells": boxes with the value inside; "bars": heights from the values (for sorting)',
    )
    show_indices: bool = Field(True, description="index numbers under the cells")
    colour: Colour = "BLUE"
    title: str | None = Field(None, description="a short label above, e.g. \"sorted list\" (at most 24 characters)")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    @model_validator(mode="after")
    def _fits(self) -> ArrayParams:
        n = len(self.values)
        if not 1 <= n <= MAX_CELLS:
            raise ValueError(f"values has {n} entries; use 1-{MAX_CELLS}")
        longest = max(len(_fmt(v)) for v in self.values)
        limit = 3 if n <= 7 else 2
        if longest > limit:
            raise ValueError(f"with {n} cells each value can be at most {limit} characters wide (found {longest})")
        if self.style == "bars" and not all(isinstance(v, int | float) and v >= 0 for v in self.values):
            raise ValueError('style "bars" needs non-negative numbers')
        return self


def _fmt(value: Value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class IndicesArgs(_Args):
    indices: list[int]
    colour: Colour = "YELLOW"


class RangeArgs(_Args):
    start: int = Field(description="first index, inclusive")
    end: int = Field(description="last index, inclusive")


class PointArgs(_Args):
    name: str = Field(description='pointer label, e.g. "lo", "mid", "i" (at most 4 characters)')
    index: int

    _name = field_validator("name")(_short(4))


class NameArgs(_Args):
    name: str


class PairArgs(_Args):
    i: int
    j: int


class SetValueArgs(_Args):
    index: int
    value: Value


class NoteArgs(_Args):
    text: str = Field(description="at most 26 characters")
    colour: Colour = "WHITE"

    _text = field_validator("text")(_short(26))


class CounterArgs(_Args):
    label: str = Field(description='e.g. "checks" (at most 12 characters)')
    value: int

    _label = field_validator("label")(_short(12))


class ScanArgs(_Args):
    index: int
    target: Value | None = Field(None, description="the value searched for; the cell turns green if it matches")


class TargetArgs(_Args):
    target: float


class IndexArgs(_Args):
    index: int


class GhostArgs(_Args):
    indices: list[int]
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _describe_array(p: ArrayParams) -> str:
    kind = "cells" if p.style == "cells" else "bars"
    out = f"a row of {len(p.values)} {p.colour.lower()} {kind}: {', '.join(_fmt(v) for v in p.values)}"
    return out + (f', titled "{p.title}"' if p.title else "")


def _cells(state: dict, indices) -> str:
    """Cells by the values they hold, not by index: the narration counts cells from one ("cells one through
    four") while the calls index from zero, so naming values can't contradict either."""
    indices = list(indices)
    values = ", ".join(_fmt(state["values"][i]) for i in indices)
    return f"the cell holding {values}" if len(indices) == 1 else f"the cells holding {values}"


def _span(state: dict, first: int, last: int) -> str:
    return _cells(state, range(first, last + 1))


def _verb(indices, verb: str) -> str:
    return verb + "s" if len(list(indices)) == 1 else verb


def _said_bisect_check(state: dict, a) -> str:
    b = state["bisect"]
    lo, hi = b["range"]
    mid = (lo + hi) // 2
    v = state["values"]
    return (f"lo, mid, hi point at the cells holding {_fmt(v[lo])}, {_fmt(v[mid])}, {_fmt(v[hi])}; the middle "
            f"value {_fmt(v[mid])} is compared with the target {_fmt(b['target'])}")


def _said_bisect_discard(state: dict, a) -> str:
    b = state["bisect"]
    mid, lo0, hi0, found = b["last"]
    value, target = state["values"][mid], b["target"]
    if found:
        return f"{_fmt(value)} is the target: its cell turns green, found"
    if value < target:
        out = f"{_fmt(value)} < {_fmt(target)}, so {_span(state, lo0, mid)} grey out"
    else:
        out = f"{_fmt(value)} > {_fmt(target)}, so {_span(state, mid, hi0)} grey out"
    if b["lo"] > b["hi"]:
        return out + "; nothing is left in play: the target isn't in the list"
    return out + f"; {_span(state, b['lo'], b['hi'])} stay in play"


def _said_scan(state: dict, a) -> str:
    out = f"pointer i moves to {_cells(state, [a.index])} and the checks counter goes up by one"
    if a.target is not None and state["values"][a.index] == a.target:
        out += "; it matches the target and turns green"
    return out


def _array_state(p: ArrayParams) -> dict:
    return {"values": list(p.values), "pointers": set(), "bisect": None}


def _in_range(state: dict, *indices: int) -> str | None:
    n = len(state["values"])
    bad = [i for i in indices if not 0 <= i < n]
    return f"index {bad[0]} is outside the list (0-{n - 1})" if bad else None


def _numeric_sorted(state: dict) -> str | None:
    values = state["values"]
    if not all(isinstance(v, int | float) for v in values):
        return "bisection needs numeric values"
    if values != sorted(values):
        return "bisection needs the values sorted"
    return None


def _check_bisect_check(state: dict, a: TargetArgs) -> str | None:
    if problem := _numeric_sorted(state):
        return problem
    b = state["bisect"]
    if b is None or b["target"] != a.target or b["done"]:  # after a search ends, a check starts a new one
        b = state["bisect"] = {"lo": 0, "hi": len(state["values"]) - 1, "target": a.target, "checked": False,
                               "done": False}
    if b["checked"]:
        return "bisect_check twice in a row: call bisect_discard first"
    b["checked"] = True
    b["range"] = (b["lo"], b["hi"])
    state["pointers"] |= {"lo", "mid", "hi"}
    return None


def _check_bisect_discard(state: dict, a: NoArgs) -> str | None:
    b = state["bisect"]
    if b is None or not b["checked"]:
        return "bisect_discard needs a bisect_check before it"
    lo0, hi0 = b["lo"], b["hi"]
    mid, b["lo"], b["hi"], found = bisect_next(state["values"], lo0, hi0, b["target"])
    b["last"] = (mid, lo0, hi0, found)
    b["checked"] = False
    b["done"] = found or b["lo"] > b["hi"]
    return None


def _check_bisect_step(state: dict, a: TargetArgs) -> str | None:
    return _check_bisect_check(state, a) or _check_bisect_discard(state, NoArgs())


def _check_point(state: dict, a: PointArgs) -> str | None:
    state["pointers"].add(a.name)
    return _in_range(state, a.index)


def _check_unpoint(state: dict, a: NameArgs) -> str | None:
    if a.name not in state["pointers"]:
        return f'there is no pointer "{a.name}"'
    state["pointers"].discard(a.name)
    return None


def _check_set_value(state: dict, a: SetValueArgs) -> str | None:
    if problem := _in_range(state, a.index):
        return problem
    state["values"][a.index] = a.value
    return None


def _check_swap(state: dict, a: PairArgs) -> str | None:
    if problem := _in_range(state, a.i, a.j):
        return problem
    v = state["values"]
    v[a.i], v[a.j] = v[a.j], v[a.i]
    return None


def _check_scan(state: dict, a: ScanArgs) -> str | None:
    state["pointers"].add("i")
    return _in_range(state, a.index)


# ---- Sorts, computed --------------------------------------------------------
# The course test (runs/course-test-1) had the writer run sorts by hand with swap and set_value, and it lost track:
# selection sort swapped the wrong cells, bubble sort called a pass done with 5 before 2. These steps are computed
# instead, like bisection, so the row is always what the sort really does. sort_step is shared by the checker and
# the drawing (array_bars.py).

SORTS = ("bubble", "selection", "insertion")


def new_sort(kind: str, n: int) -> dict:
    progress = {"bubble": {"j": 0, "end": n - 1, "swapped": False, "pass": 1},
                "selection": {"k": 0}, "insertion": {"i": 1}}[kind]
    return {"kind": kind, "done": n < 2, "comparisons": 0, **progress}


def sort_step(values: list, st: dict) -> dict:
    """One step of the sort `st` describes, on `values` (both changed in place). What happened:
      bubble: compared (j, j + 1), the two values, swapped, placed (indices now final), pass_done;
      selection: min (where the smallest of the unsorted part was), into (where it goes), swapped, placed;
      insertion: from, to (where the value moved), the value;
    and for all: comparisons (this step's), done."""
    n = len(values)
    kind = st["kind"]
    if kind == "bubble":
        j = st["j"]
        a, b = values[j], values[j + 1]
        ev = {"compared": (j, j + 1), "values": (a, b), "swapped": a > b, "placed": [], "pass_done": False,
              "comparisons": 1}
        if a > b:
            values[j], values[j + 1] = b, a
            st["swapped"] = True
        st["j"] += 1
        if st["j"] >= st["end"]:  # the pass reached the end: the largest unsorted value is in place
            ev["pass_done"] = True
            ev["placed"] = [st["end"]]
            if not st["swapped"] or st["end"] == 1:  # no swap in a whole pass, or one cell left: sorted
                ev["placed"] = list(range(st["end"] + 1))
                st["done"] = True
            else:
                st["end"] -= 1
                st["j"], st["swapped"] = 0, False
                st["pass"] += 1
    elif kind == "selection":
        k = st["k"]
        m = min(range(k, n), key=lambda i: (values[i], i))
        ev = {"min": m, "into": k, "value": values[m], "swapped": m != k, "placed": [k], "comparisons": n - 1 - k}
        values[k], values[m] = values[m], values[k]
        st["k"] += 1
        if st["k"] >= n - 1:
            ev["placed"] = [k, n - 1]
            st["done"] = True
    else:
        i = st["i"]
        value, p, comps = values[i], i, 0
        while p > 0:
            comps += 1
            if values[p - 1] > value:
                p -= 1
            else:
                break
        values.insert(p, values.pop(i))
        ev = {"from": i, "to": p, "value": value, "comparisons": comps}
        st["i"] += 1
        st["done"] = st["i"] >= n
    st["comparisons"] += ev["comparisons"]
    ev["done"] = st["done"]
    return ev


def _row(state: dict) -> str:
    return ", ".join(_fmt(v) for v in state["values"])


def sort_events(values: list, sort: dict | None, kind: str, whole_pass: bool = False) -> tuple[dict, list[dict]]:
    """The sort's progress (a new one if `kind` differs) and the steps one call makes: one step, or with
    `whole_pass` a bubble pass to its end. Shared by the checker and the drawing."""
    if sort is None or sort["kind"] != kind:
        sort = new_sort(kind, len(values))
    events = []
    while not sort["done"]:
        events.append(sort_step(values, sort))
        if not whole_pass or events[-1]["pass_done"]:
            break
    return sort, events


def _check_sort(kind: str, whole_pass: bool = False):
    def check(state: dict, a) -> str | None:
        if not all(isinstance(v, int | float) for v in state["values"]):
            return f"{kind} sort needs numeric values"
        s = state.get("sort")
        if s is not None and s["kind"] == kind and s["done"]:
            return f"the list is sorted: {kind} sort has finished (create the list again to sort another)"
        state["sort"], state["last_sort"] = sort_events(state["values"], s, kind, whole_pass)
        return None
    return check


def _said_bubble(ev: dict) -> str:
    (i, j), (a, b) = ev["compared"], ev["values"]
    out = (f"{_fmt(a)} and {_fmt(b)} are compared: {_fmt(a)} > {_fmt(b)}, so they swap" if ev["swapped"]
           else f"{_fmt(a)} and {_fmt(b)} are compared: already in order, no swap")
    return out


def _said_sort(state: dict, a) -> str:
    events = state["last_sort"]
    kind = state["sort"]["kind"]
    if kind == "bubble":
        if len(events) == 1:
            out = _said_bubble(events[0])
        else:
            swaps = sum(e["swapped"] for e in events)
            out = f"a whole pass of {len(events)} comparisons and {swaps} swap{'s' if swaps != 1 else ''}"
        last = events[-1]
        out += f"; the row reads {_row(state)}"
        if last["done"]:
            out += "; every cell turns green: sorted"
        elif last["pass_done"]:
            out += f"; {_fmt(state['values'][last['placed'][0]])} turns green at the end: in place"
    elif kind == "selection":
        ev = events[-1]
        out = (f"the smallest unsorted value, {_fmt(ev['value'])}, is found"
               + (" and swaps to the front of the unsorted part" if ev["swapped"] else ", already at the front"))
        out += f"; the row reads {_row(state)}; the first {ev['into'] + 1} cell{'s are' if ev['into'] else ' is'} sorted"
        if ev["done"]:
            out += "; every cell is green: sorted"
    else:
        ev = events[-1]
        moved = ev["from"] - ev["to"]
        out = (f"{_fmt(ev['value'])} moves left past {moved} larger value{'s' if moved != 1 else ''}" if moved
               else f"{_fmt(ev['value'])} stays: its left neighbour is smaller")
        out += f" ({ev['comparisons']} comparison{'s' if ev['comparisons'] != 1 else ''}); the row reads {_row(state)}"
        out += "; sorted" if ev["done"] else f"; the first {ev['from'] + 1} cells are in order"
    return out + f"; comparisons: {state['sort']['comparisons']}"


def _scan_reveals(state: dict, a: ScanArgs) -> bool:
    return a.target is not None and 0 <= a.index < len(state["values"]) and state["values"][a.index] == a.target


ARRAY_BARS = TemplateSpec(
    name="ArrayBars",
    family="array_bars",
    purpose="A list/array as cells or bars: searching, sorting, pointers, halves, swaps. To show a sort, use "
            "bubble_step, bubble_pass, selection_step or insertion_step: code makes the comparisons and swaps, so "
            "the row is always right (swap and set_value are for a single change the line talks about). Needs at "
            "least half the frame.",
    params=ArrayParams,
    min_rows=3,
    init_state=_array_state,
    noun="list",
    describe=_describe_array,
    actions={
        "highlight": ActionSpec("Colour these cells.", IndicesArgs, lambda s, a: _in_range(s, *a.indices),
                                lambda s, a: f"{_cells(s, a.indices)} {_verb(a.indices, 'turn')} {a.colour.lower()}"),
        "clear": ActionSpec("Remove highlights, ghosts and the note (greyed cells stay grey).",
                            says=lambda s, a: "the list's highlights, ghosts and note clear"),
        "grey_out": ActionSpec("Grey out cells start..end: ruled out.", RangeArgs,
                               lambda s, a: _in_range(s, a.start, a.end),
                               lambda s, a: f"{_span(s, a.start, a.end)} grey out: ruled out"),
        "restore": ActionSpec("Un-grey every cell.", says=lambda s, a: "every cell is back in play"),
        "point": ActionSpec("Show (or move) a named pointer under a cell.", PointArgs, _check_point,
                            lambda s, a: f'pointer "{a.name}" under {_cells(s, [a.index])}'),
        "unpoint": ActionSpec("Remove a pointer.", NameArgs, _check_unpoint,
                              lambda s, a: f'pointer "{a.name}" disappears'),
        "compare": ActionSpec('Highlight two cells and note the comparison, e.g. "4 < 7".', PairArgs,
                              lambda s, a: _in_range(s, a.i, a.j),
                              lambda s, a: f"{_cells(s, [a.i, a.j])} light up and are compared"),
        "swap": ActionSpec("Swap two cells (they move past each other).", PairArgs, _check_swap,
                           lambda s, a: f"{_cells(s, [a.j, a.i])} swap places; the row now reads "
                                        f"{', '.join(_fmt(v) for v in s['values'])}", reveals=True),
        "set_value": ActionSpec("Change one cell's value.", SetValueArgs, _check_set_value,
                                lambda s, a: f"a cell changes to {_fmt(a.value)}; the row now reads "
                                             f"{', '.join(_fmt(v) for v in s['values'])}", reveals=True),
        "bubble_step": ActionSpec(
            "Bubble sort, one comparison (computed): compare the next adjacent pair and swap it if it is out of "
            "order. When a pass reaches the end, the largest unsorted value turns green: in place. A comparisons "
            "counter keeps count.", NoArgs, _check_sort("bubble"), _said_sort, reveals=True),
        "bubble_pass": ActionSpec("Bubble sort, the rest of the current pass in one line (computed).", NoArgs,
                                  _check_sort("bubble", whole_pass=True), _said_sort, reveals=True),
        "selection_step": ActionSpec(
            "Selection sort, one step (computed): find the smallest value of the unsorted part and swap it to the "
            "front of that part, which turns green: sorted.", NoArgs, _check_sort("selection"), _said_sort,
            reveals=True),
        "insertion_step": ActionSpec(
            "Insertion sort, one step (computed): the next value moves left past every larger value and stops "
            "after the first smaller one.", NoArgs, _check_sort("insertion"), _said_sort, reveals=True),
        "note": ActionSpec("A short line of text above the list.", NoteArgs,
                           says=lambda s, a: f'note above the list: "{a.text}"'),
        "counter": ActionSpec('Show or update a counter, e.g. checks: 3.', CounterArgs,
                              says=lambda s, a: f"counter {a.label}: {a.value}"),
        "scan": ActionSpec("Linear search: pointer i moves to this cell, the checks counter goes up by one.",
                           ScanArgs, _check_scan, _said_scan, reveals=_scan_reveals),
        "bisect_check": ActionSpec(
            "Bisection: show lo, mid, hi on the part still in play and compare the middle value with the target. "
            "The first call (or the first after a search ended) starts a search over the whole list. Values must "
            "be sorted numbers.",
            TargetArgs, _check_bisect_check, _said_bisect_check, reveals=True,
        ),
        "bisect_discard": ActionSpec(
            "Bisection: grey out the half that can't hold the target (or mark mid green if it is the target).",
            NoArgs, _check_bisect_discard, _said_bisect_discard, reveals=True,
        ),
        "bisect_step": ActionSpec("bisect_check and bisect_discard in one line.", TargetArgs, _check_bisect_step,
                                  lambda s, a: f"{_said_bisect_check(s, a)}; {_said_bisect_discard(s, a)}",
                                  reveals=True),
        "found": ActionSpec("Mark this cell green: found.", IndexArgs, lambda s, a: _in_range(s, a.index),
                            lambda s, a: f"{_cells(s, [a.index])} turns green: found", reveals=True),
        "ghost": ActionSpec("A wrong idea: dashed red outline around these cells, with the idea noted in red.",
                            GhostArgs, lambda s, a: _in_range(s, *a.indices),
                            lambda s, a: f"a wrong idea: a red dashed outline around {_cells(s, a.indices)}, "
                                         f'noted "{a.text}"'),
    },
    example=[
        ['arr = ArrayBars(values=[1, 3, 4, 7, 9, 11, 15], title="sorted list", area="bottom_two_thirds")'],
        ["arr.ghost(indices=[0, 1, 2], text=\"check every one?\")"],
        ["arr.clear()", "arr.bisect_check(target=9)"],
        ["arr.bisect_discard()"],
        ["arr.bisect_step(target=9)"],
    ],
)


# --------------------------------------------------------------------------
# MergeSort: a list split into halves level by level, and sorted runs merged front by front
# --------------------------------------------------------------------------
# The course test's merge videos drew only one of the two lists (ArrayBars holds one row), so the merge itself was
# never on screen. Here the split tree and every merge step are computed (ms_split, ms_merge_step), shared by the
# checker and the drawing (merge_sort.py).

MS_MAX_SPLIT = 8
MS_MAX_RUNS = 10
MS_GAP = 0.25  # the gap between runs, per level of the split tree, in cell widths


class MergeParams(_Args):
    values: list[int | float] | None = Field(None, description="a list to sort, 2-8 numbers; split it with split")
    runs: list[list[int | float]] | None = Field(
        None, description="or two sorted lists to merge, e.g. [[1, 5, 9], [2, 3, 7]] (2-10 numbers in all)")
    colour: Colour = "BLUE"
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    @model_validator(mode="after")
    def _fits(self) -> MergeParams:
        if (self.values is None) == (self.runs is None):
            raise ValueError("give exactly one of values (a list to sort) or runs (two sorted lists to merge)")
        if self.runs is not None:
            if len(self.runs) != 2 or not all(self.runs):
                raise ValueError("runs needs exactly two non-empty lists")
            if any(r != sorted(r) for r in self.runs):
                raise ValueError("each of the two runs must be sorted: merging takes sorted lists")
            values, limit = self.runs[0] + self.runs[1], MS_MAX_RUNS
        else:
            values, limit = self.values, MS_MAX_SPLIT
        if not 2 <= len(values) <= limit:
            raise ValueError(f"{len(values)} numbers; use 2-{limit}")
        widths = [len(_fmt(v)) for v in values]
        if max(widths) > 2:
            raise ValueError("each value can be at most 2 characters wide")
        if max(widths) == 2 and len(values) > 7:
            raise ValueError("with two-digit values, at most 7 numbers fit; use fewer or one-digit values")
        return self


def _ms_leaf(lo: int, hi: int, sorted_: bool) -> dict:
    return {"lo": lo, "hi": hi, "kids": None, "sorted": sorted_, "merged": False}


def ms_new(values: list | None, runs: list[list] | None) -> dict:
    """The state of a MergeSort object: its row of values, the split tree over it, the merge in progress."""
    if runs is not None:
        vals = list(runs[0]) + list(runs[1])
        n0 = len(runs[0])
        root = {"lo": 0, "hi": len(vals), "kids": [_ms_leaf(0, n0, True), _ms_leaf(n0, len(vals), True)],
                "sorted": False, "merged": False}
    else:
        vals = list(values or [])
        root = _ms_leaf(0, len(vals), len(vals) < 2)
    return {"values": vals, "tree": root, "merge": None, "comparisons": 0, "splittable": runs is None}


def ms_leaves(node: dict) -> list[dict]:
    return [node] if node["kids"] is None else [leaf for k in node["kids"] for leaf in ms_leaves(k)]


def _ms_post(node: dict):
    for k in node["kids"] or []:
        yield from _ms_post(k)
    yield node


def ms_gaps(tree: dict) -> list[int]:
    """Gap units before each slot (0 for the first and inside a run): runs split at a higher level sit further
    apart, so the split tree reads from the gaps."""
    gaps = [0] * (tree["hi"] - tree["lo"])

    def height(node: dict) -> int:
        return 1 + max(height(k) for k in node["kids"]) if node["kids"] else 0

    top = height(tree)

    def walk(node: dict, d: int) -> None:
        if node["kids"]:
            gaps[node["kids"][1]["lo"]] = top - d
            for k in node["kids"]:
                walk(k, d + 1)

    walk(tree, 0)
    return gaps


def ms_full_gap_units(state: dict) -> int:
    """The most gap units the row will ever have (fully split), so cells are sized once for the object's life."""
    import copy

    st = copy.deepcopy(state)
    while st["splittable"] and ms_split(st) is None:
        pass
    return sum(ms_gaps(st["tree"]))


def ms_split(st: dict) -> str | None:
    """Splits every run that can split into halves (the first half has len // 2 values, as L[:len(L) // 2])."""
    if not st["splittable"]:
        return "these are two lists to merge, not one to split"
    if st["merge"] is not None:
        return "finish the merge in progress first (merge)"
    changed = False
    for leaf in ms_leaves(st["tree"]):
        size = leaf["hi"] - leaf["lo"]
        if size > 1 and not leaf["merged"]:
            mid = leaf["lo"] + size // 2
            leaf["kids"] = [_ms_leaf(leaf["lo"], mid, mid - leaf["lo"] == 1), _ms_leaf(mid, leaf["hi"], leaf["hi"] - mid == 1)]
            changed = True
    return None if changed else "every run is split down to one value (or already merged): merge now"


def _ms_ready(st: dict) -> list[dict]:
    """Nodes whose two runs are both leaves: what can merge now, leftmost and deepest first."""
    return [n for n in _ms_post(st["tree"]) if n["kids"] and all(k["kids"] is None for k in n["kids"])]


def ms_merge_step(st: dict, among: list[dict] | None = None) -> dict | str:
    """One merge step: compare the two runs' fronts and move the smaller into the merged list, or, once a run is
    used up, copy the rest of the other. A new merge starts on the leftmost, deepest ready pair (of `among`, if
    given). Returns what happened (or a problem): compared (the two slots) or None, took (slots moved, in order),
    out (the merged list so far), lo/hi (the node), done."""
    v = st["values"]
    m = st["merge"]
    if m is None:
        ready = _ms_ready(st)
        if among is not None:
            ready = [n for n in ready if any(n is t for t in among)] or ready
        if not ready:
            return ("nothing to merge: the list is one sorted run" if st["tree"]["sorted"]
                    else "nothing to merge yet: split the list first")
        node = ready[0]
        left, right = node["kids"]
        for run in (left, right):
            if not run["sorted"]:
                return (f"split further first: {', '.join(_fmt(x) for x in v[run['lo']:run['hi']])} isn't sorted, "
                        "and merging takes two sorted runs")
        m = st["merge"] = {"node": node, "i": left["lo"], "j": right["lo"], "out": []}
    node = m["node"]
    left, right = node["kids"]
    has_l, has_r = m["i"] < left["hi"], m["j"] < right["hi"]
    ev: dict = {"lo": node["lo"], "hi": node["hi"], "compared": None}
    if has_l and has_r:
        a, b = v[m["i"]], v[m["j"]]
        st["comparisons"] += 1
        ev["compared"], ev["pair"] = (m["i"], m["j"]), (a, b)
        side = "i" if a <= b else "j"
        ev["took"] = [m[side]]
        m["out"].append(v[m[side]])
        m[side] += 1
    else:
        side, end = ("i", left["hi"]) if has_l else ("j", right["hi"])
        ev["took"] = list(range(m[side], end))
        ev["rest"] = True
        m["out"] += [v[k] for k in ev["took"]]
        m[side] = end
    ev["out"] = list(m["out"])
    ev["done"] = m["i"] >= left["hi"] and m["j"] >= right["hi"]
    if ev["done"]:
        v[node["lo"]:node["hi"]] = m["out"]
        node["kids"], node["sorted"], node["merged"] = None, True, True
        st["merge"] = None
    return ev


def ms_merge(st: dict, whole_level: bool = False) -> list[dict] | str:
    """The steps of one whole merge (the one in progress, or the next), or with `whole_level` of every merge that
    is ready now."""
    targets: list[dict] | None = None
    if whole_level:  # the merges ready now (a parent that becomes ready on the way waits for the next call)
        targets = [st["merge"]["node"]] if st["merge"] else []
        targets += [n for n in _ms_ready(st) if not any(n is t for t in targets)]
    events: list[dict] = []
    while sum(e["done"] for e in events) < (len(targets) if targets else 1):
        ev = ms_merge_step(st, targets)
        if isinstance(ev, str):
            return events or ev
        events.append(ev)
    return events


def _runs_words(st: dict) -> str:
    v = st["values"]
    return " | ".join(", ".join(_fmt(x) for x in v[leaf["lo"]:leaf["hi"]]) for leaf in ms_leaves(st["tree"]))


def _describe_merge(p: MergeParams) -> str:
    if p.runs is not None:
        lists = " and ".join(", ".join(_fmt(x) for x in r) for r in p.runs)
        out = f"two sorted lists side by side, {lists}, with room below for the merged list"
    else:
        out = f"a list {', '.join(_fmt(x) for x in p.values)} as one run of cells"
    return out + (f', titled "{p.title}"' if p.title else "")


def _check_ms_split(state: dict, a) -> str | None:
    return ms_split(state["ms"])


def _check_ms_merge(kind: str):
    def check(state: dict, a) -> str | None:
        st = state["ms"]
        out = [ms_merge_step(st)] if kind == "step" else ms_merge(st, whole_level=kind == "level")
        if isinstance(out, str):
            return out
        if isinstance(out[0], str):
            return out[0]
        state["last_merge"] = out
        return None
    return check


def _said_merge_event(st_values_before: list, ev: dict) -> str:
    if ev["compared"] is not None:
        a, b = ev["pair"]
        small = min(a, b) if a != b else a
        out = f"fronts {_fmt(a)} and {_fmt(b)} are compared: {_fmt(small)} is smaller and moves down"
        if a == b:
            out = f"fronts {_fmt(a)} and {_fmt(b)} are compared: equal, the left one moves down"
    else:
        vals = ", ".join(_fmt(st_values_before[k]) for k in ev["took"])
        out = f"one run is used up, so the rest of the other, {vals}, copies down"
    out += f"; the merged list reads {', '.join(_fmt(x) for x in ev['out'])}"
    if ev["done"]:
        out += " and moves up into place as one sorted run"
    return out


def _said_ms(state: dict, a) -> str:
    events = state["last_merge"]
    st = state["ms"]
    if len(events) == 1:
        out = _said_merge_event(state["values_before"], events[0])
    else:
        done = [e for e in events if e["done"]]
        merged = "; ".join(", ".join(_fmt(x) for x in e["out"]) for e in done)
        out = f"{len(done)} merge{'s' if len(done) != 1 else ''} run front by front into {merged}"
    return out + f"; the row reads {_runs_words(st)}; comparisons: {st['comparisons']}"


def _ms_state(p: MergeParams) -> dict:
    st = ms_new(p.values, p.runs)
    return {"ms": st, "values": st["values"], "values_before": list(st["values"])}


def _ms_wrap(check):
    """Keeps a copy of the row before the call, for the sentence (which names the values a step moved)."""
    def wrapped(state: dict, a) -> str | None:
        state["values_before"] = list(state["ms"]["values"])
        return check(state, a)
    return wrapped


class MsIndicesArgs(_Args):
    indices: list[int] = Field(description="positions in the row, from 0")
    colour: Colour = "YELLOW"


class MsGhostArgs(_Args):
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _ms_in_range(state: dict, a) -> str | None:
    n = len(state["ms"]["values"])
    bad = [i for i in a.indices if not 0 <= i < n]
    return f"index {bad[0]} is outside the row (0-{n - 1})" if bad else None


MERGE_SORT = TemplateSpec(
    name="MergeSort",
    family="merge_sort",
    purpose="Merge sort and merging, computed: a list split in halves level by level (split), and two sorted runs "
            "merged front by front into a list below them (merge_step, merge, merge_level). The comparisons are "
            "counted. Give `runs` to merge two sorted lists, or `values` to sort one. Needs at least half the frame.",
    params=MergeParams,
    min_rows=3,
    init_state=_ms_state,
    noun="runs",
    describe=_describe_merge,
    actions={
        "split": ActionSpec("Every run splits into two halves (one level of the split).", NoArgs,
                            _check_ms_split, lambda s, a: f"each run splits in half: {_runs_words(s['ms'])}"),
        "merge_step": ActionSpec(
            "One merge step: compare the fronts of the two runs being merged and move the smaller down into the "
            "merged list (when one run is used up, the rest of the other copies down). The first step starts the "
            "next merge: the leftmost, deepest pair of sorted runs.",
            NoArgs, _ms_wrap(_check_ms_merge("step")), _said_ms, reveals=True),
        "merge": ActionSpec("A whole merge in one line: the steps of the merge in progress (or the next one).", NoArgs,
                            _ms_wrap(_check_ms_merge("whole")), _said_ms, reveals=True),
        "merge_level": ActionSpec("Every pair of runs that is ready merges, one after another.", NoArgs,
                                  _ms_wrap(_check_ms_merge("level")), _said_ms, reveals=True),
        "highlight": ActionSpec("Colour these cells of the top row.", MsIndicesArgs, _ms_in_range,
                                lambda s, a: "the cells holding "
                                             + ", ".join(_fmt(s["ms"]["values"][i]) for i in a.indices)
                                             + f" turn {a.colour.lower()}"),
        "ghost": ActionSpec("A wrong idea: a red dashed outline around the row, with the idea noted in red.",
                            MsGhostArgs, says=lambda s, a: f'a wrong idea: a red dashed outline, noted "{a.text}"'),
        "note": ActionSpec("A short line of text above the runs.", NoteArgs,
                           says=lambda s, a: f'note above the runs: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, the ghost and the note.",
                            says=lambda s, a: "the highlights, ghost and note clear"),
    },
    example=[
        ['ms = MergeSort(values=[5, 2, 4, 7, 1, 3, 8, 6], title="merge sort")'],
        ["ms.split()", "ms.split()"],
        ["ms.split()"],
        ["ms.merge_step()", "ms.merge_step()"],
        ["ms.merge_level()"],
        ["ms.merge_level()"],
        ["ms.merge()"],
    ],
)


# --------------------------------------------------------------------------
# FunctionPlot: axes with curves, points, tangents, areas and maxima
# --------------------------------------------------------------------------
# For the course test's function pictures that had no template: the MLE video showed only formulas ("no curves, no
# max point on a graph"), growth curves were formulas, XOR's points were vectors on a linear-map grid. Values such
# as a tangent's slope, a maximum or an area are computed from the function, so they are always right.

FN_NAMES = {"sin", "cos", "tan", "exp", "log", "ln", "log2", "log10", "sqrt", "abs"}
FN_VARS = {"x", "n", "t"}
FN_CONSTS = {"pi", "e"}
MAX_CURVES = 4
MAX_POINTS = 12
PLOT_SAMPLES = 161


def parse_fn(expr: str):
    """A function of one variable (x, n or t) from a formula like "x**2 - 1", "n*log2(n)" or "exp(-x^2/2)", as a
    numpy function. Only numbers, the variable, + - * / ** (or ^), and FN_NAMES are allowed: it is parsed, never
    executed as code. Raises ValueError with what to fix."""
    import ast as _ast

    import numpy as np

    source = expr.replace("^", "**").strip()
    try:
        tree = _ast.parse(source, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"{expr!r} is not a formula (write products with *, e.g. 2*x)") from e
    allowed = (_ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Constant, _ast.Name, _ast.Call, _ast.Load,
               _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.Pow, _ast.USub, _ast.UAdd)
    for node in _ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"{expr!r}: only numbers, the variable x (or n, t), + - * / ** and "
                             f"{', '.join(sorted(FN_NAMES))} are allowed")
        if isinstance(node, _ast.Constant) and not isinstance(node.value, int | float):
            raise ValueError(f"{expr!r}: only numbers are allowed as constants")
        if isinstance(node, _ast.Name) and node.id not in FN_VARS | FN_CONSTS | FN_NAMES:
            raise ValueError(f"{expr!r}: unknown name {node.id!r}; use x (or n, t) and {', '.join(sorted(FN_NAMES))}")
        if isinstance(node, _ast.Call) and (not isinstance(node.func, _ast.Name) or node.func.id not in FN_NAMES
                                            or len(node.args) != 1 or node.keywords):
            raise ValueError(f"{expr!r}: a function takes one argument: {', '.join(sorted(FN_NAMES))}")
    names = {"sin": np.sin, "cos": np.cos, "tan": np.tan, "exp": np.exp, "log": np.log, "ln": np.log,
             "log2": np.log2, "log10": np.log10, "sqrt": np.sqrt, "abs": np.abs, "pi": np.pi, "e": np.e}
    code = compile(tree, "<fn>", "eval")

    def f(x):
        with np.errstate(all="ignore"):
            out = eval(code, {"__builtins__": {}}, {**names, "x": x, "n": x, "t": x})  # noqa: S307 - checked AST
        return np.broadcast_to(np.asarray(out, dtype=float), np.shape(x)).astype(float)

    return f


def fn_samples(fn, lo: float, hi: float, k: int = PLOT_SAMPLES):
    import numpy as np

    xs = np.linspace(lo, hi, k)
    return xs, fn(xs)


def _range_pair(v: list[float]) -> list[float]:
    if len(v) != 2 or not v[0] < v[1]:
        raise ValueError("give [low, high] with low < high")
    return v


class CurveSpec(_Args):
    name: str = Field(description=r'its label in TeX, e.g. "f", "n^2", "\log L" (at most 12 characters)')
    fn: str = Field(description='a formula in x (or n, t), e.g. "x**2", "n*log2(n)", "exp(-(x-2)**2/2)"')
    colour: Colour = "BLUE"

    _name = field_validator("name")(_short(12))


class PlotParams(_Args):
    x_range: list[float] = Field(description="[low, high]")
    y_range: list[float] | None = Field(None, description="[low, high]; left out, it fits the curves")
    x_label: str = Field("x", description="at most 8 characters")
    y_label: str = Field("y", description="at most 8 characters")
    curves: list[CurveSpec] = Field(default_factory=list, description="0-3 curves drawn at the start")
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _x = field_validator("x_range")(_range_pair)
    _x_label = field_validator("x_label")(_short(8))
    _y_label = field_validator("y_label")(_short(8))
    _title = field_validator("title")(_short(24))

    @field_validator("y_range")
    @classmethod
    def _y(cls, v):
        return None if v is None else _range_pair(v)

    @model_validator(mode="after")
    def _curves(self) -> PlotParams:
        if len(self.curves) > 3:
            raise ValueError("at most 3 curves at the start")
        if len({c.name for c in self.curves}) != len(self.curves):
            raise ValueError("curve names must differ")
        for c in self.curves:
            parse_fn(c.fn)
        if self.y_range is None and not self.curves:
            raise ValueError("give y_range when no curve is drawn at the start")
        return self


def plot_y_range(p: PlotParams) -> tuple[float, float]:
    """The y range: as given, or the initial curves' values over x_range with a margin."""
    import numpy as np

    if p.y_range is not None:
        return float(p.y_range[0]), float(p.y_range[1])
    ys = np.concatenate([fn_samples(parse_fn(c.fn), *p.x_range)[1] for c in p.curves])
    ys = ys[np.isfinite(ys)]
    if ys.size == 0:
        return -1.0, 1.0
    lo, hi = float(ys.min()), float(ys.max())
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    pad = 0.08 * (hi - lo)
    lo = 0.0 if 0 <= lo < 0.3 * (hi - lo) else lo - pad  # a curve starting near 0 keeps 0 as the floor
    return lo, hi + pad


class PlotArgs(CurveSpec):
    pass


class CurveNameArgs(_Args):
    curve: str = Field(description="a curve's name")


class CurveXArgs(_Args):
    curve: str = Field(description="a curve's name")
    x: float
    label: str | None = Field(None, description=r'optional TeX label, e.g. "x_0" (at most 8 characters)')
    colour: Colour = "YELLOW"

    _label = field_validator("label")(_short(8))


class ShadeArgs(_Args):
    curve: str
    a: float = Field(description="from x = a")
    b: float = Field(description="to x = b")
    colour: Colour = "TEAL"


class TraceArgs(_Args):
    curve: str
    x_from: float
    x_to: float
    colour: Colour = "YELLOW"


class VLineArgs(_Args):
    x: float
    colour: Colour = "GREY"


class PeakArgs(_Args):
    curve: str
    kind: Literal["max", "min"] = "max"
    colour: Colour = "GOLD"


class PointsArgs(_Args):
    xs: list[float] = Field(description="the points' x values")
    ys: list[float] = Field(description="their y values")
    colour: Colour = "BLUE"


class SegmentArgs(_Args):
    x1: float
    y1: float
    x2: float
    y2: float
    colour: Colour = "ORANGE"
    dashed: bool = False


class PlotGhostArgs(_Args):
    fn: str = Field(description="the wrong curve, a formula in x")
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


class HighlightCurveArgs(_Args):
    curve: str
    colour: Colour = "YELLOW"


class PlotNoteArgs(_Args):
    text: str | None = Field(None, description="plain words, at most 26 characters")
    tex: str | None = Field(None, description="or a short formula in TeX")

    _text = field_validator("text")(_short(26))
    _tex = field_validator("tex")(_readable_tex)

    @model_validator(mode="after")
    def _one(self) -> PlotNoteArgs:
        if (self.text is None) == (self.tex is None):
            raise ValueError("give exactly one of text or tex")
        return self


def _plot_state(p: PlotParams) -> dict:
    return {"x": (float(p.x_range[0]), float(p.x_range[1])), "y": plot_y_range(p), "var": "x",
            "curves": {c.name: c.fn for c in p.curves}, "ghost": False}


def _init_plot_check(p: PlotParams) -> str | None:
    st = _plot_state(p)
    for c in p.curves:
        if problem := _curve_visible(st, c.name, c.fn):
            return problem
    return None


def _curve_visible(st: dict, name: str, expr: str) -> str | None:
    import numpy as np

    try:
        fn = parse_fn(expr)
    except ValueError as e:
        return str(e)
    _, ys = fn_samples(fn, *st["x"])
    lo, hi = st["y"]
    inside = np.isfinite(ys) & (ys >= lo) & (ys <= hi)
    if inside.mean() < 0.2:
        return (f"curve {name} ({expr}) is off the axes for most of x from {_num(st['x'][0])} to "
                f"{_num(st['x'][1])} (y shown: {_num(lo)} to {_num(hi)}); change y_range or the formula")
    return None


def _need_curve(st: dict, name: str) -> str | None:
    if name not in st["curves"]:
        known = ", ".join(st["curves"]) or "none yet"
        return f"there is no curve {name!r} (curves: {known})"
    return None


def _need_x(st: dict, x: float) -> str | None:
    lo, hi = st["x"]
    return None if lo <= x <= hi else f"x = {_num(x)} is outside the axes ({_num(lo)} to {_num(hi)})"


def _value_at(st: dict, name: str, x: float) -> float:
    import numpy as np

    return float(np.asarray(parse_fn(st["curves"][name])(np.array([x])))[0])


def fn_slope(fn, x: float, span: float) -> float:
    import numpy as np

    h = span * 1e-4
    return float((fn(np.array([x + h])) - fn(np.array([x - h])))[0] / (2 * h))


def fn_extreme(fn, lo: float, hi: float, kind: str) -> tuple[float, float]:
    """(x, y) of the curve's max (or min) over [lo, hi], from dense samples."""
    import numpy as np

    xs, ys = fn_samples(fn, lo, hi, 2001)
    ok = np.isfinite(ys)
    k = int(np.nanargmax(np.where(ok, ys, -np.inf)) if kind == "max" else np.nanargmin(np.where(ok, ys, np.inf)))
    return float(xs[k]), float(ys[k])


def fn_area(fn, a: float, b: float) -> float:
    import numpy as np

    xs, ys = fn_samples(fn, a, b, 2001)
    return float(np.trapezoid(np.nan_to_num(ys), xs)) if hasattr(np, "trapezoid") else float(np.trapz(np.nan_to_num(ys), xs))


def _check_plot(state: dict, a: PlotArgs) -> str | None:
    if a.name in state["curves"]:
        return f"there is already a curve {a.name!r}"
    if len(state["curves"]) >= MAX_CURVES:
        return f"at most {MAX_CURVES} curves; remove one first"
    if problem := _curve_visible(state, a.name, a.fn):
        return problem
    state["curves"][a.name] = a.fn
    return None


def _check_curve_x(state: dict, a: CurveXArgs) -> str | None:
    import math

    if problem := _need_curve(state, a.curve) or _need_x(state, a.x):
        return problem
    y = _value_at(state, a.curve, a.x)
    lo, hi = state["y"]
    if not math.isfinite(y) or not lo <= y <= hi:
        return f"{a.curve} at x = {_num(a.x)} is off the axes"
    return None


def _check_peak(state: dict, a: PeakArgs) -> str | None:
    if problem := _need_curve(state, a.curve):
        return problem
    x, y = fn_extreme(parse_fn(state["curves"][a.curve]), *state["x"], a.kind)
    lo, hi = state["y"]
    if not lo <= y <= hi:
        word = "highest" if a.kind == "max" else "lowest"
        return (f"the {word} point of {a.curve} (x = {_num(x)}, {a.curve} = {_num(y)}) is off the axes "
                f"(y shown: {_num(lo)} to {_num(hi)}); widen y_range or narrow x_range")
    return None


def _check_shade(state: dict, a: ShadeArgs) -> str | None:
    if problem := _need_curve(state, a.curve) or _need_x(state, a.a) or _need_x(state, a.b):
        return problem
    return None if a.a < a.b else "give a < b"


def _check_trace(state: dict, a: TraceArgs) -> str | None:
    return _need_curve(state, a.curve) or _need_x(state, a.x_from) or _need_x(state, a.x_to) or (
        None if a.x_from != a.x_to else "x_from and x_to must differ")


def _check_points(state: dict, a: PointsArgs) -> str | None:
    if len(a.xs) != len(a.ys) or not a.xs:
        return "xs and ys must be the same length (1 or more)"
    if len(a.xs) > MAX_POINTS:
        return f"at most {MAX_POINTS} points"
    (xl, xh), (yl, yh) = state["x"], state["y"]
    for x, y in zip(a.xs, a.ys):
        if not (xl <= x <= xh and yl <= y <= yh):
            return f"the point ({_num(x)}, {_num(y)}) is off the axes"
    return None


def _check_segment(state: dict, a: SegmentArgs) -> str | None:
    (xl, xh), (yl, yh) = state["x"], state["y"]
    for x, y in ((a.x1, a.y1), (a.x2, a.y2)):
        if not (xl <= x <= xh and yl <= y <= yh):
            return f"the end ({_num(x)}, {_num(y)}) is off the axes"
    return None


def _check_remove_curve(state: dict, a: CurveNameArgs) -> str | None:
    problem = _need_curve(state, a.curve)
    state["curves"].pop(a.curve, None)
    return problem


def _check_ghost_curve(state: dict, a: PlotGhostArgs) -> str | None:
    problem = _curve_visible(state, "the ghost", a.fn)
    state["ghost"] = True
    return problem


def _describe_plot(p: PlotParams) -> str:
    lo, hi = plot_y_range(p)
    out = (f"axes for {p.x_label} from {_num(p.x_range[0])} to {_num(p.x_range[1])} and {p.y_label} from "
           f"{_num(lo)} to {_num(hi)}")
    if p.curves:
        out += ", with the curve" + ("s " if len(p.curves) > 1 else " ") + ", ".join(
            f"{c.name} = {c.fn} ({c.colour.lower()})" for c in p.curves)
    return out + (f', titled "{p.title}"' if p.title else "")


def _said_tangent(s: dict, a: CurveXArgs) -> str:
    fn = parse_fn(s["curves"][a.curve])
    slope = fn_slope(fn, a.x, s["x"][1] - s["x"][0])
    return (f"the tangent to {a.curve} at x = {_num(a.x)} (where {a.curve} = {_num(_value_at(s, a.curve, a.x))}) "
            f"is drawn: slope {_num(slope)}")


def _said_peak(s: dict, a: PeakArgs) -> str:
    x, y = fn_extreme(parse_fn(s["curves"][a.curve]), *s["x"], a.kind)
    word = "highest" if a.kind == "max" else "lowest"
    return f"the {word} point of {a.curve} is marked: x = {_num(x)}, {a.curve} = {_num(y)}"


def _said_shade(s: dict, a: ShadeArgs) -> str:
    area = fn_area(parse_fn(s["curves"][a.curve]), a.a, a.b)
    return f"the area under {a.curve} from x = {_num(a.a)} to {_num(a.b)} is shaded (about {_num(area)})"


FUNCTION_PLOT = TemplateSpec(
    name="FunctionPlot",
    family="function_plot",
    purpose="Axes with plotted functions, computed from their formulas: curves (growth rates, a likelihood, a "
            "density), a point on a curve, a tangent, a shaded area, the highest or lowest point, a dot sliding "
            "along a curve, plus data points and straight lines (a scatter plot, a decision boundary). Needs at "
            "least half the frame.",
    params=PlotParams,
    min_rows=3,
    init_state=_plot_state,
    noun="plot",
    describe=_describe_plot,
    actions={
        "plot": ActionSpec("Draw another curve.", PlotArgs, _check_plot,
                           lambda s, a: f"the curve {a.name} = {a.fn} is drawn in {a.colour.lower()}"),
        "remove_curve": ActionSpec("Fade a curve out.", CurveNameArgs, _check_remove_curve,
                                   lambda s, a: f"the curve {a.curve} fades out"),
        "highlight": ActionSpec("Make a curve stand out.", HighlightCurveArgs,
                                lambda s, a: _need_curve(s, a.curve),
                                lambda s, a: f"the curve {a.curve} stands out in {a.colour.lower()}"),
        "dot": ActionSpec("A dot on a curve at x, with an optional label.", CurveXArgs, _check_curve_x,
                          lambda s, a: f"a dot on {a.curve} at x = {_num(a.x)}, where {a.curve} = "
                                       f"{_num(_value_at(s, a.curve, a.x))}"
                                       + (f', labelled "{a.label}"' if a.label else "")),
        "tangent": ActionSpec("The tangent line to a curve at x, with its slope computed.", CurveXArgs,
                              _check_curve_x, _said_tangent, reveals=True),
        "shade": ActionSpec("Shade the area under a curve from a to b (computed).", ShadeArgs, _check_shade,
                            _said_shade, reveals=True),
        "peak": ActionSpec("Mark a curve's highest (or lowest) point on the axes, found by code.", PeakArgs,
                           _check_peak, _said_peak, reveals=True),
        "trace": ActionSpec("A dot slides along a curve from x_from to x_to.", TraceArgs, _check_trace,
                            lambda s, a: f"a dot slides along {a.curve} from x = {_num(a.x_from)} to "
                                         f"{_num(a.x_to)}"),
        "vline": ActionSpec("A dashed vertical line at x.", VLineArgs, lambda s, a: _need_x(s, a.x),
                            lambda s, a: f"a dashed vertical line at x = {_num(a.x)}"),
        "points": ActionSpec("Data points (a scatter), 1-12 of them.", PointsArgs, _check_points,
                             lambda s, a: f"{len(a.xs)} {a.colour.lower()} point{'s' if len(a.xs) != 1 else ''} at "
                                          + ", ".join(f"({_num(x)}, {_num(y)})" for x, y in zip(a.xs, a.ys))),
        "line": ActionSpec("A straight line from (x1, y1) to (x2, y2): a boundary, a secant.", SegmentArgs,
                           _check_segment,
                           lambda s, a: f"a {'dashed ' if a.dashed else ''}{a.colour.lower()} line from "
                                        f"({_num(a.x1)}, {_num(a.y1)}) to ({_num(a.x2)}, {_num(a.y2)})"),
        "ghost": ActionSpec("A wrong idea: a red dashed curve, with the idea noted in red.", PlotGhostArgs,
                            _check_ghost_curve,
                            lambda s, a: f'a wrong idea: a red dashed curve {a.fn}, noted "{a.text}"'),
        "note": ActionSpec("A short line above the axes: words (text) or a formula (tex).", PlotNoteArgs,
                           says=lambda s, a: f'note above the axes: "{a.text or a.tex}"'),
        "clear": ActionSpec("Remove dots, tangents, shading, lines, the ghost and the note (curves stay).",
                            says=lambda s, a: "the marks on the plot clear; the curves stay"),
    },
    example=[
        ['plot = FunctionPlot(x_range=[1, 10], x_label="n", y_label="steps", y_range=[0, 40], '
         'curves=[{"name": "n", "fn": "n", "colour": "BLUE"}])'],
        ['plot.plot(name="n \\log n", fn="n*log2(n)", colour="TEAL")'],
        ['plot.ghost(fn="2*n", text="all just linear?")'],
        ["plot.clear()", 'plot.dot(curve="n \\log n", x=8, label="n=8")'],
        ['plot.tangent(curve="n \\log n", x=4)'],
    ],
)


# --------------------------------------------------------------------------
# Graph: nodes and edges, with DFS and BFS computed
# --------------------------------------------------------------------------
# The course test drew DFS as a row of cells. Searches here are computed (dfs_next, bfs_next), shared by the checker
# and the drawing (graph.py), so the order nodes are reached in is always the algorithm's.

MAX_NODES = 8
MAX_EDGES = 12


class GraphParams(_Args):
    nodes: list[str] = Field(description='2-8 node names, at most 2 characters each, e.g. ["s", "a", "b"]')
    edges: list[list[str]] = Field(description='pairs of node names, e.g. [["s", "a"], ["a", "b"]] (at most 12)')
    directed: bool = Field(False, description="arrows from the first node of each pair to the second")
    layout: Literal["layers", "circle"] = Field(
        "layers", description='"layers": rows by distance from the first node; "circle": nodes round a circle')
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    @model_validator(mode="after")
    def _valid(self) -> GraphParams:
        if not 2 <= len(self.nodes) <= MAX_NODES:
            raise ValueError(f"{len(self.nodes)} nodes; use 2-{MAX_NODES}")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("node names must differ")
        if any(not 1 <= len(n) <= 2 for n in self.nodes):
            raise ValueError("each node name is 1-2 characters")
        if len(self.edges) > MAX_EDGES:
            raise ValueError(f"{len(self.edges)} edges; at most {MAX_EDGES}")
        seen = set()
        for e in self.edges:
            if len(e) != 2 or e[0] not in self.nodes or e[1] not in self.nodes:
                raise ValueError(f"edge {e}: give two node names from nodes")
            if e[0] == e[1]:
                raise ValueError(f"edge {e}: a node can't link to itself")
            key = tuple(e) if self.directed else tuple(sorted(e))
            if key in seen:
                raise ValueError(f"edge {e} is listed twice")
            seen.add(key)
        return self


def graph_adjacency(nodes: list[str], edges: list[list[str]], directed: bool) -> dict[str, list[str]]:
    """Each node's neighbours, in the order the edges are listed (the order a search tries them)."""
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for u, v in edges:
        adj[u].append(v)
        if not directed:
            adj[v].append(u)
    return adj


def dfs_next(adj: dict[str, list[str]], st: dict) -> dict:
    """The next step of a recursive DFS: the next node it reaches (visit, from), and the nodes it finished on the
    way back up (finished). visit None: the search from start is done."""
    if not st["started"]:
        st["started"] = True
        return {"visit": st["start"], "from": None, "finished": []}
    finished = []
    while st["stack"]:
        top = st["stack"][-1]
        node, k = top
        if k < len(adj[node]):
            top[1] += 1
            v = adj[node][k]
            if v not in st["visited"]:
                st["visited"].append(v)
                st["parent"][v] = node
                st["stack"].append([v, 0])
                return {"visit": v, "from": node, "finished": finished}
        else:
            st["stack"].pop()
            finished.append(node)
            st["order"].append(node)
    st["done"] = True
    return {"visit": None, "from": None, "finished": finished}


def dfs_new(start: str) -> dict:
    return {"kind": "dfs", "start": start, "stack": [[start, 0]], "visited": [start], "parent": {start: None},
            "order": [], "started": False, "done": False}


def bfs_new(start: str) -> dict:
    return {"kind": "bfs", "start": start, "frontier": [start], "level": 0, "dist": {start: 0},
            "parent": {start: None}, "started": False, "done": False}


def bfs_next(adj: dict[str, list[str]], st: dict) -> dict:
    """The next level of a BFS: the nodes at distance `level`, each with the node it was reached from."""
    if not st["started"]:
        st["started"] = True
        return {"level": 0, "nodes": [st["start"]], "from": {}}
    nxt, came = [], {}
    for u in st["frontier"]:
        for v in adj[u]:
            if v not in st["dist"]:
                st["dist"][v] = st["level"] + 1
                st["parent"][v] = u
                came[v] = u
                nxt.append(v)
    if not nxt:
        st["done"] = True
        return {"level": None, "nodes": [], "from": {}}
    st["level"] += 1
    st["frontier"] = nxt
    return {"level": st["level"], "nodes": nxt, "from": came}


class StartArgs(_Args):
    start: str = Field(description="the node the search starts from")


class NodesArgs(_Args):
    nodes: list[str]
    colour: Colour = "YELLOW"


class EdgeArgs(_Args):
    a: str
    b: str
    colour: Colour = "YELLOW"


class GhostEdgeArgs(_Args):
    a: str
    b: str
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _graph_state(p: GraphParams) -> dict:
    return {"adj": graph_adjacency(p.nodes, p.edges, p.directed), "nodes": list(p.nodes), "directed": p.directed,
            "edges": {tuple(e) if p.directed else tuple(sorted(e)) for e in p.edges}, "search": None, "last": None}


def _has_edge(st: dict, a: str, b: str) -> bool:
    return ((a, b) if st["directed"] else tuple(sorted((a, b)))) in st["edges"]


def _need_nodes(st: dict, *names: str) -> str | None:
    bad = [n for n in names if n not in st["nodes"]]
    return f"there is no node {bad[0]!r} (nodes: {', '.join(st['nodes'])})" if bad else None


def _check_search(kind: str):
    def check(state: dict, a: StartArgs) -> str | None:
        if problem := _need_nodes(state, a.start):
            return problem
        s = state["search"]
        if s is None or s["kind"] != kind or s["start"] != a.start:
            s = state["search"] = (dfs_new if kind == "dfs" else bfs_new)(a.start)
        if s["done"]:
            return f"the {kind.upper()} from {a.start} is done: it has reached everything it can"
        state["last"] = (dfs_next if kind == "dfs" else bfs_next)(state["adj"], s)
        return None
    return check


def _said_dfs(state: dict, a) -> str:
    ev, s = state["last"], state["search"]
    back = f"it backs up from {', '.join(ev['finished'])}, then " if ev["finished"] else ""
    if ev["visit"] is None:
        missed = [n for n in state["nodes"] if n not in s["visited"]]
        out = f"{back}DFS from {s['start']} is done: it reached {', '.join(s['visited'])}"
        return out + (f"; {', '.join(missed)} can't be reached" if missed else "")
    if ev["from"] is None:
        return f"DFS starts at {ev['visit']}, which turns yellow: visited {ev['visit']}"
    return (f"{back}DFS goes from {ev['from']} to {ev['visit']} along their edge; visited so far: "
            f"{', '.join(s['visited'])}")


def _said_bfs(state: dict, a) -> str:
    ev, s = state["last"], state["search"]
    if ev["level"] is None:
        missed = [n for n in state["nodes"] if n not in s["dist"]]
        return "BFS is done: no new nodes" + (f"; {', '.join(missed)} can't be reached" if missed else "")
    if ev["level"] == 0:
        return f"BFS starts at {ev['nodes'][0]}: distance 0"
    reached = ", ".join(f"{v} (from {u})" for v, u in ev["from"].items())
    return f"BFS reaches level {ev['level']}: {reached}, each labelled with distance {ev['level']}"


def _check_path(state: dict, a: NodesArgs) -> str | None:
    if problem := _need_nodes(state, *a.nodes):
        return problem
    if len(a.nodes) < 2:
        return "a path needs at least two nodes"
    for u, v in zip(a.nodes, a.nodes[1:]):
        if not _has_edge(state, u, v):
            return f"there is no edge from {u} to {v}"
    return None


def _check_edge(state: dict, a: EdgeArgs) -> str | None:
    if problem := _need_nodes(state, a.a, a.b):
        return problem
    return None if _has_edge(state, a.a, a.b) else f"there is no edge from {a.a} to {a.b}"


def _describe_graph(p: GraphParams) -> str:
    joiner = " -> " if p.directed else " - "
    edges = ", ".join(joiner.join(e) for e in p.edges)
    kind = "a directed graph" if p.directed else "a graph"
    return f"{kind} with nodes {', '.join(p.nodes)} and edges {edges}" + (f', titled "{p.title}"' if p.title else "")


GRAPH = TemplateSpec(
    name="Graph",
    family="graph",
    purpose="A graph of nodes and edges, with searches computed: dfs_step reaches one new node per call in DFS "
            "order, bfs_level one whole level per call with distances; highlight nodes, edges or a path; a wrong "
            "idea as a red dashed edge. Needs at least half the frame.",
    params=GraphParams,
    min_rows=3,
    init_state=_graph_state,
    noun="graph",
    describe=_describe_graph,
    actions={
        "dfs_step": ActionSpec(
            "DFS, one step (computed): the search reaches its next new node, trying each node's edges in the order "
            "they are listed, and backs up when a node has no unvisited neighbour. The current node is yellow, "
            "visited ones teal, the edges it used thick. Calling it with another start starts a new search.",
            StartArgs, _check_search("dfs"), _said_dfs, reveals=True),
        "bfs_level": ActionSpec(
            "BFS, one level (computed): every node at the next distance from start turns teal, labelled with its "
            "distance, and the edges that reached them thicken.", StartArgs, _check_search("bfs"), _said_bfs,
            reveals=True),
        "highlight": ActionSpec("Colour these nodes.", NodesArgs, lambda s, a: _need_nodes(s, *a.nodes),
                                lambda s, a: f"nodes {', '.join(a.nodes)} turn {a.colour.lower()}"),
        "highlight_edge": ActionSpec("Colour one edge.", EdgeArgs, _check_edge,
                                     lambda s, a: f"the edge {a.a}-{a.b} turns {a.colour.lower()}"),
        "path": ActionSpec("Colour a path: the edges between consecutive nodes.", NodesArgs, _check_path,
                           lambda s, a: f"the path {' -> '.join(a.nodes)} lights up in {a.colour.lower()}",
                           reveals=True),
        "ghost_edge": ActionSpec("A wrong idea: a red dashed edge (it may not exist), with the idea noted in red.",
                                 GhostEdgeArgs, lambda s, a: _need_nodes(s, a.a, a.b),
                                 lambda s, a: f'a wrong idea: a red dashed edge {a.a}-{a.b}, noted "{a.text}"'),
        "note": ActionSpec("A short line of text above the graph.", NoteArgs,
                           says=lambda s, a: f'note above the graph: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, the ghost and the note (a search's colours stay).",
                            says=lambda s, a: "the graph's highlights, ghost and note clear"),
        "reset": ActionSpec("Clear everything, a search's colours too.",
                            check=lambda s, a: s.update(search=None) or None,
                            says=lambda s, a: "the graph is back to plain"),
    },
    example=[
        ['g = Graph(nodes=["s", "a", "b", "c", "d"], edges=[["s", "a"], ["s", "b"], ["a", "c"], ["b", "c"], '
         '["c", "d"]], title="who can s reach?")'],
        ['g.dfs_step(start="s")', 'g.dfs_step(start="s")'],
        ['g.ghost_edge(a="s", b="d", text="jump straight to d?")'],
        ['g.clear()', 'g.dfs_step(start="s")', 'g.dfs_step(start="s")'],
        ['g.dfs_step(start="s")', 'g.dfs_step(start="s")'],
        ['g.reset()', 'g.bfs_level(start="s")', 'g.bfs_level(start="s")'],
        ['g.path(nodes=["s", "a", "c", "d"], colour="GOLD")'],
    ],
)


# --------------------------------------------------------------------------
# LinearMap2D: a coordinate grid with vectors, transformed by a 2x2 matrix
# --------------------------------------------------------------------------


def _two_by_two(m: list[list[float]]) -> list[list[float]]:
    if len(m) != 2 or any(len(row) != 2 for row in m):
        raise ValueError("must be 2x2: [[a, b], [c, d]]")
    if any(abs(x) > 5 for row in m for x in row):
        raise ValueError("keep entries between -5 and 5 so the picture stays on screen")
    return m


class VectorSpec(_Args):
    name: str = Field(description=r'TeX label, e.g. "v", "\hat{i}", "Av" (at most 10 characters)')
    x: float
    y: float
    colour: Colour = "YELLOW"

    _name = field_validator("name")(_short(10))


class MapParams(_Args):
    matrix: list[list[float]] = Field(description="2x2, rows first: [[a, b], [c, d]]")
    vectors: list[VectorSpec] = Field(default_factory=list, description="0-4 vectors drawn from the origin")
    extent: int = Field(3, ge=2, le=5, description="the grid shows -extent..extent on the shorter side")
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    _matrix = field_validator("matrix")(_two_by_two)

    @model_validator(mode="after")
    def _few_vectors(self) -> MapParams:
        if len(self.vectors) > 4:
            raise ValueError("at most 4 vectors")
        names = [v.name for v in self.vectors]
        if len(set(names)) != len(names):
            raise ValueError("vector names must differ")
        return self


class VectorArgs(VectorSpec):
    pass


class MatrixArgs(_Args):
    matrix: list[list[float]]

    _matrix = field_validator("matrix")(_two_by_two)


class ApplyArgs(_Args):
    keep_ghost: bool = Field(False, description="leave faded copies of the vectors where they started")


class ColourArgs(_Args):
    colour: Colour = "GOLD"


class HighlightVectorArgs(_Args):
    name: str
    colour: Colour = "YELLOW"


class MapNoteArgs(_Args):
    text: str | None = Field(None, description="plain words, at most 26 characters")
    tex: str | None = Field(None, description="or a short formula in TeX")

    _text = field_validator("text")(_short(26))
    _tex = field_validator("tex")(_readable_tex)

    @model_validator(mode="after")
    def _one(self) -> MapNoteArgs:
        if (self.text is None) == (self.tex is None):
            raise ValueError("give exactly one of text or tex")
        return self


class GhostVectorArgs(_Args):
    x: float
    y: float
    name: str = Field("", description="optional TeX label")


def matvec(m: list[list[float]], x: float, y: float) -> tuple[float, float]:
    return m[0][0] * x + m[0][1] * y, m[1][0] * x + m[1][1] * y


def real_eigenvectors(m: list[list[float]]) -> list[tuple[float, tuple[float, float]]]:
    """(eigenvalue, unit eigenvector) for each real eigenvalue of a 2x2 matrix; one entry per independent line."""
    import numpy as np

    values, vectors = np.linalg.eig(np.array(m, dtype=float))
    out: list[tuple[float, tuple[float, float]]] = []
    for k in range(2):
        if abs(values[k].imag) > 1e-9:
            continue
        v = vectors[:, k].real
        v = v / np.linalg.norm(v)
        if any(abs(abs(float(np.dot(v, w))) - 1) < 1e-6 for _, w in out):
            continue  # a repeated eigenvalue with one line
        out.append((float(values[k].real), (float(v[0]), float(v[1]))))
    return out


def _vector_words(name: str, x: float, y: float, colour: str | None = None) -> str:
    return f"{name} = ({_num(x)}, {_num(y)})" + (f" {colour.lower()}" if colour else "")


def _describe_map(p: MapParams) -> str:
    out = f"a coordinate grid (-{p.extent}..{p.extent}) for the matrix {_matrix_words(p.matrix)}"
    if p.vectors:
        out += " with vector" + ("s " if len(p.vectors) > 1 else " ")
        out += ", ".join(_vector_words(v.name, v.x, v.y, v.colour) for v in p.vectors)
    return out + (f', titled "{p.title}"' if p.title else "")


def _direction(v: tuple[float, float]) -> str:
    """A unit direction as small numbers where it is a simple ratio: (0.71, 0.71) -> (1, 1)."""
    x, y = v
    small = min((abs(c) for c in (x, y) if abs(c) > 1e-9), default=1.0)
    a, b = x / small, y / small
    if a < 0 or (a == 0 and b < 0):
        a, b = -a, -b
    if all(abs(c - round(c)) < 1e-6 for c in (a, b)):
        return f"({round(a):d}, {round(b):d})"
    return f"({_num(x)}, {_num(y)})"


def _said_apply(state: dict, a) -> str:
    m = state["matrix"]
    moves = [f"{n} ({_num(x)}, {_num(y)}) -> ({_num(tx)}, {_num(ty)})"
             for n, (x, y) in state["vectors"].items() for tx, ty in [matvec(m, x, y)]]
    out = f"the grid and its vectors transform by {_matrix_words(m)}" + (": " + ", ".join(moves) if moves else "")
    return out + ("; faded copies stay where the vectors started" if a.keep_ghost else "")


def _said_eigenlines(state: dict, a) -> str:
    lines = real_eigenvectors(state["matrix"])
    if not lines:
        return "the note says the matrix has no real eigenvectors"
    return "dashed eigen-lines appear: " + ", ".join(
        f"along {_direction(v)} labelled lambda = {_num(value)}" for value, v in lines)


def _map_state(p: MapParams) -> dict:
    return {"matrix": p.matrix, "vectors": {v.name: (v.x, v.y) for v in p.vectors}, "extent": p.extent,
            "applied": False}


def _reach(state: dict, x: float, y: float) -> str | None:
    """A vector must stay on the grid both before and after the matrix is applied."""
    e = state["extent"]
    tx, ty = matvec(state["matrix"], x, y)
    for label, (a, b) in (("", (x, y)), (" after the matrix", (tx, ty))):
        if max(abs(a), abs(b)) > e:
            return (f"the vector ({x:g}, {y:g}) lands at ({a:g}, {b:g}){label}, off the grid (-{e}..{e}); "
                    "use a shorter vector or a larger extent")
    return None


def _nonzero(x: float, y: float) -> str | None:
    return "a zero vector can't be drawn as an arrow; give it a length" if x == 0 and y == 0 else None


def _init_map_check(p: MapParams) -> str | None:
    state = _map_state(p)
    for v in p.vectors:
        if problem := _nonzero(v.x, v.y) or _reach(state, v.x, v.y):
            return f"vector {v.name}: {problem}"
    return None


def _check_add_vector(state: dict, a: VectorArgs) -> str | None:
    if a.name in state["vectors"]:
        return f"there is already a vector {a.name}"
    if state["applied"]:
        return "add vectors before apply, or after reset"
    state["vectors"][a.name] = (a.x, a.y)
    return _nonzero(a.x, a.y) or _reach(state, a.x, a.y)


def _check_vector_name(state: dict, a) -> str | None:
    if a.name not in state["vectors"]:
        return f"there is no vector {a.name}"
    return None


def _check_remove_vector(state: dict, a: NameArgs) -> str | None:
    problem = _check_vector_name(state, a)
    state["vectors"].pop(a.name, None)
    return problem


def _check_apply(state: dict, a: ApplyArgs) -> str | None:
    if state["applied"]:
        return "the matrix is already applied; reset first"
    state["applied"] = True
    return None


def _check_reset(state: dict, a: NoArgs) -> str | None:
    state["applied"] = False
    return None


def _check_set_matrix(state: dict, a: MatrixArgs) -> str | None:
    if state["applied"]:
        return "set_matrix before apply, or after reset"
    state["matrix"] = a.matrix
    for name, (x, y) in state["vectors"].items():
        if problem := _reach(state, x, y):
            return f"vector {name}: {problem}"
    return None


def _check_ghost_vector(state: dict, a: GhostVectorArgs) -> str | None:
    e = state["extent"]
    if problem := _nonzero(a.x, a.y):
        return problem
    for name, (x, y) in state["vectors"].items():
        if state["applied"]:
            x, y = matvec(state["matrix"], x, y)
        if abs(x - a.x) < 1e-9 and abs(y - a.y) < 1e-9:
            return (f"the guess sits exactly on vector {name}, so it can't be seen; put it where the wrong idea "
                    "says the vector goes")
    return f"({a.x:g}, {a.y:g}) is off the grid (-{e}..{e})" if max(abs(a.x), abs(a.y)) > e else None


LINEAR_MAP_2D = TemplateSpec(
    name="LinearMap2D",
    family="linear_map_2d",
    purpose="A coordinate grid with vectors from the origin, transformed by a 2x2 matrix: linear maps, "
            "eigenvectors, change of basis, determinant as area. Needs at least half the frame.",
    params=MapParams,
    min_rows=3,
    init_state=_map_state,
    noun="grid",
    describe=_describe_map,
    actions={
        "apply": ActionSpec("Transform the grid and every vector by the matrix.", ApplyArgs, _check_apply,
                            _said_apply, reveals=True),
        "reset": ActionSpec("Undo apply: back to the plain grid.", NoArgs, _check_reset,
                            lambda s, a: "the grid and vectors return to where they started"),
        "add_vector": ActionSpec("Grow a new vector from the origin.", VectorArgs, _check_add_vector,
                                 lambda s, a: f"a {a.colour.lower()} vector {_vector_words(a.name, a.x, a.y)} grows "
                                              "from the origin"),
        "remove_vector": ActionSpec("Fade a vector out.", NameArgs, _check_remove_vector,
                                    lambda s, a: f"vector {a.name} fades out"),
        "highlight_vector": ActionSpec("Make a vector stand out.", HighlightVectorArgs, _check_vector_name,
                                       lambda s, a: f"vector {a.name} stands out in {a.colour.lower()}"),
        "eigenlines": ActionSpec(
            "Dashed lines along the matrix's real eigenvectors, each labelled with its eigenvalue (computed, so "
            "they are always right). Vectors on these lines only stretch when the matrix is applied.",
            ColourArgs, says=_said_eigenlines, reveals=True,
        ),
        "set_matrix": ActionSpec("Use a different matrix (before apply, or after reset).", MatrixArgs,
                                 _check_set_matrix,
                                 lambda s, a: f"the matrix changes to {_matrix_words(a.matrix)}"),
        "show_matrix": ActionSpec("Write the matrix in brackets in the note line above the grid.",
                                  says=lambda s, a: f"the matrix A = {_matrix_words(s['matrix'])} is written at the "
                                                    "grid's top left"),
        "note": ActionSpec("A short line above the grid: words (text) or a formula (tex).", MapNoteArgs,
                           says=lambda s, a: f'note above the grid: "{a.text or a.tex}"'),
        "ghost_vector": ActionSpec("A wrong idea: a dashed red vector where someone guesses it lands.",
                                   GhostVectorArgs, _check_ghost_vector,
                                   lambda s, a: f"a wrong guess: a red dashed vector to ({_num(a.x)}, {_num(a.y)})"
                                                + (f' labelled "{a.name}"' if a.name else "")),
        "clear_ghosts": ActionSpec("Remove ghost vectors and their notes.",
                                   says=lambda s, a: "the red dashed guesses disappear"),
    },
    example=[
        ['grid = LinearMap2D(matrix=[[2, 1], [1, 2]], vectors=[{"name": "v", "x": 1, "y": 1, "colour": "GOLD"}, '
         '{"name": "w", "x": 1, "y": 0, "colour": "BLUE"}], extent=3, area="full")'],
        ['grid.ghost_vector(x=0, y=1, name="?")'],
        ["grid.clear_ghosts()", "grid.apply()"],
        ["grid.eigenlines()"],
        ['grid.note(tex="Av = 3v")'],
    ],
)


# --------------------------------------------------------------------------
# EquationSteps: a derivation, one formula per step
# --------------------------------------------------------------------------


class PartColour(_Args):
    part: str = Field(description=r'a piece of the TeX exactly as written, e.g. "\lambda"')
    colour: Colour


class EquationParams(_Args):
    tex: str = Field(description=f"the first formula, in TeX (at most about {MAX_TEX_SYMBOLS} symbols)")
    colours: list[PartColour] = Field(
        default_factory=list, description="pieces drawn in a colour in every line, e.g. the colour key's terms",
    )
    max_lines: int = Field(3, ge=1, le=4, description="lines kept on screen; older ones scroll away")
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _tex = field_validator("tex")(_readable_tex)
    _title = field_validator("title")(_short(24))


class TexArgs(_Args):
    tex: str = Field(description=f"at most about {MAX_TEX_SYMBOLS} symbols")

    _tex = field_validator("tex")(_readable_tex)


class PartArgs(_Args):
    part: str = Field(description="a piece of the current (last) line's TeX, exactly as written")
    colour: Colour = "YELLOW"


class CoverArgs(_Args):
    part: str = Field(description="a piece of the current (last) line's TeX, exactly as written")


class BoxArgs(_Args):
    colour: Colour = "GOLD"


class EqNoteArgs(_Args):
    text: str = Field(description="at most 26 characters")

    _text = field_validator("text")(_short(26))


def _describe_equation(p: EquationParams) -> str:
    return f"the formula {p.tex}" + (f', titled "{p.title}"' if p.title else "")


def _eq_state(p: EquationParams) -> dict:
    return {"last": p.tex, "covered": False}


def _check_part(state: dict, a) -> str | None:
    if state["covered"]:
        return "a piece is covered; uncover it first"
    if a.part not in state["last"]:
        return f"{a.part!r} is not in the current line {state['last']!r}"
    return None


def _check_new_line(state: dict, a: TexArgs) -> str | None:
    state["last"] = a.tex
    state["covered"] = False
    return None


def _check_cover(state: dict, a: CoverArgs) -> str | None:
    problem = _check_part(state, a)
    state["covered"] = True
    return problem


def _check_uncover(state: dict, a: NoArgs) -> str | None:
    if not state["covered"]:
        return "nothing is covered"
    state["covered"] = False
    return None


EQUATION_STEPS = TemplateSpec(
    name="EquationSteps",
    family="equation_steps",
    purpose="A derivation or calculation, one formula per step: rewrite, add a line, highlight or colour a "
            "term, hide a part for a prediction, box the result, cross out a wrong step.",
    params=EquationParams,
    init_state=_eq_state,
    noun="formula",
    describe=_describe_equation,
    actions={
        "rewrite": ActionSpec("Morph the current line into a new formula (matching pieces move into place).",
                              TexArgs, _check_new_line, lambda s, a: f"the formula morphs into {a.tex}"),
        "then": ActionSpec("Write the next formula on a new line below.", TexArgs, _check_new_line,
                           lambda s, a: f"a new line below: {a.tex}"),
        "highlight": ActionSpec("Colour a piece of the current line and underline it.", PartArgs, _check_part,
                                lambda s, a: f"{a.part} turns {a.colour.lower()} and is underlined"),
        "colour": ActionSpec("Colour a piece of the current line.", PartArgs, _check_part,
                             lambda s, a: f"{a.part} turns {a.colour.lower()}"),
        "cover": ActionSpec("Show a piece of the current line as a boxed ? (for a predict line).",
                            CoverArgs, _check_cover, lambda s, a: f"{a.part} is hidden behind a boxed ?"),
        "uncover": ActionSpec("Lift the grey block.", NoArgs, _check_uncover,
                              lambda s, a: "the hidden piece is revealed", reveals=True),
        "box": ActionSpec("Box the current line: the result.", BoxArgs,
                          says=lambda s, a: f"the line {s['last']} is boxed in {a.colour.lower()}", reveals=True),
        "cross_out": ActionSpec("A wrong step: dim the current line and put a dashed red box around it.",
                                says=lambda s, a: f"the line {s['last']} dims inside a red dashed box: wrong"),
        "note": ActionSpec("A short line of words above the formulas.", EqNoteArgs,
                           says=lambda s, a: f'note above the formulas: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, boxes and the note.",
                            says=lambda s, a: "the formulas' highlights, boxes and note clear"),
    },
    example=[
        [r'eq = EquationSteps(tex="A v = \lambda v", colours=[{"part": "\lambda", "colour": "ORANGE"}], '
         'area="top_half")'],
        [r'eq.rewrite(tex="(A - \lambda I) v = 0")'],
        [r'eq.highlight(part="(A - \lambda I)")'],
        [r'eq.then(tex="\det(A - \lambda I) = 0")', 'eq.cover(part="0")'],
        ["eq.uncover()", "eq.box()"],
    ],
)


# --------------------------------------------------------------------------
# Note: a short piece of text
# --------------------------------------------------------------------------


class NoteParams(_Args):
    text: str = Field(description="at most 70 characters; wraps onto up to three lines")
    colour: Colour = "WHITE"
    big: bool = Field(False, description="larger type, for a single key word or question")
    area: Area = "top_third"

    _text = field_validator("text")(_short(70))


class SayArgs(_Args):
    text: str = Field(description="at most 70 characters")
    colour: Colour = "WHITE"

    _text = field_validator("text")(_short(70))


NOTE = TemplateSpec(
    name="Note",
    family="note",
    purpose="A short piece of text: a question, a key word, a takeaway. Use it beside a diagram, not instead "
            "of one.",
    params=NoteParams,
    noun="note",
    describe=lambda p: f'the text "{p.text}"' + (" in large type" if p.big else ""),
    actions={"say": ActionSpec("Replace the text.", SayArgs,
                               says=lambda s, a: f'the text changes to "{a.text}"')},
    example=[
        ['q = Note(text="Why does halving win?", big=True, area="top_third")'],
        ['q.say(text="n, n/2, n/4 ... 1", colour="TEAL")'],
    ],
)


REGISTRY: dict[str, TemplateSpec] = {s.name: s for s in (
    ARRAY_BARS, MERGE_SORT, GRAPH, FUNCTION_PLOT, LINEAR_MAP_2D, EQUATION_STEPS, NOTE)}

# Extra checks a template's parameters need beyond its model (the vectors fit the grid, the curves fit the axes).
INIT_CHECKS: dict[str, Callable[[BaseModel], str | None]] = {"LinearMap2D": _init_map_check,
                                                             "FunctionPlot": _init_plot_check}


# --------------------------------------------------------------------------
# The writer's prompt
# --------------------------------------------------------------------------


def _type_name(annotation) -> str:
    text = str(annotation).replace("typing.", "").replace("animation_agent.visuals.specs.", "")
    return text.replace("NoneType", "None").replace("<class '", "").replace("'>", "")


def _signature(model: type[BaseModel], auto_layout: bool = False) -> str:
    parts = []
    for name, f in model.model_fields.items():
        if f.annotation in (Area,):
            if auto_layout:
                continue  # code places it (normalize.lay_out)
            parts.append(f"{name}=<area>" if f.is_required() else f'{name}="{f.default}"')
        elif f.annotation in (Colour,):
            parts.append(f'{name}="{f.default}"' if f.default is not None and not f.is_required() else f"{name}=<colour>")
        elif f.is_required():
            parts.append(name)
        else:
            default = f.default if f.default_factory is None else f.default_factory()
            parts.append(f"{name}={default!r}")
    return ", ".join(parts)


def _field_notes(model: type[BaseModel]) -> list[str]:
    return [f"{name}: {f.description}" for name, f in model.model_fields.items() if f.description]


_AREA_ARG = re.compile(r""",?\s*area=["'][a-z_]+["']""")


def template_card(spec: TemplateSpec, auto_layout: bool = False) -> str:
    """The template as the writer sees it. With `auto_layout`, without areas or `move` (code lays objects out)."""
    lines = [f"{spec.name}({_signature(spec.params, auto_layout)})", f"  {spec.purpose}"]
    lines += [f"  - {note}" for note in _field_notes(spec.params)]
    lines.append("  Actions:")
    for name, action in spec.all_actions().items():
        if auto_layout and name == "move":
            continue
        lines.append(f"    .{name}({_signature(action.args, auto_layout)}): {action.doc}")
        lines += [f"        {note}" for note in _field_notes(action.args)]
    lines.append("  Example (one segment):")
    for k, calls in enumerate(spec.example, 1):
        lines.append(f"    beat {k}:" + ("" if calls else " (no calls: the picture stays)"))
        lines += [f"      {_AREA_ARG.sub('', call).replace('(, ', '(') if auto_layout else call}" for call in calls]
    return "\n".join(lines)


def template_cards(names: list[str] | None = None, auto_layout: bool = False) -> str:
    return "\n\n".join(template_card(REGISTRY[n], auto_layout) for n in (names or list(REGISTRY)))
