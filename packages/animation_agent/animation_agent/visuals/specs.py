"""
What each visual template takes and can do, without importing Manim.

The script writer's prompt is built from these (`template_cards`), and calls.py checks a script's calls against
them before anything renders. The drawing classes (array_bars.py, ...) implement the same names: every action
here is a method there with the same arguments (tests/test_visual_templates.py checks this).

Logic a drawing has to get right, like which half bisection discards, lives here as plain functions, so the
checker and the drawing compute the same thing.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Bump when a template draws differently (or the call language changes): it is part of the cache key of every
# video drawn with templates (syllabyte_common.video_jobs.video_key), so those videos are made again.
TEMPLATES_VERSION = "11"  # SlopeField, GeometryConstruction and projected Scene3D

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
    return f"{round(float(x), 2) + 0.0:g}" if isinstance(x, int | float) else str(x)  # + 0.0: never "-0"


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
    return {"values": list(p.values), "pointers": set(), "bisect": None, "found": set()}


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
    state["edited"] = True  # changed by hand: code no longer knows which cells are in place
    return None


def _check_swap(state: dict, a: PairArgs) -> str | None:
    if problem := _in_range(state, a.i, a.j):
        return problem
    v = state["values"]
    v[a.i], v[a.j] = v[a.j], v[a.i]
    state["edited"] = True
    return None


def _check_scan(state: dict, a: ScanArgs) -> str | None:
    state["pointers"].add("i")
    if problem := _in_range(state, a.index):
        return problem
    if a.target is not None and state["values"][a.index] == a.target:
        state.setdefault("found", set()).add(a.index)
    return None


def _check_found(state: dict, a: IndexArgs) -> str | None:
    if problem := _in_range(state, a.index):
        return problem
    state.setdefault("found", set()).add(a.index)
    return None


def green_cells(state: dict) -> set[int]:
    """The cells the list's steps have turned green (sorted, or found): the only cells a GREEN highlight may
    colour, since green is what sorted and found look like."""
    n = len(state["values"])
    out = set(state.get("found") or ())
    b = state.get("bisect")
    if b and b.get("last") and b["last"][3]:
        out.add(b["last"][0])
    st = state.get("sort")
    if st:
        if st["done"]:
            out |= set(range(n))
        elif st["kind"] == "selection":
            out |= set(range(st["k"]))
        elif st["kind"] == "bubble":
            out |= set(range(st["end"] + 1, n))
    return out


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


# ---- Quicksort's partition (Lomuto), computed ------------------------------------------------------------------


class PartitionArgs(_Args):
    lo: int | None = Field(None, description="the first index of the part to partition (left out: the whole list)")
    hi: int | None = Field(None, description="the last index; its value is the pivot")


def partition_next(values: list, part: dict) -> dict:
    """One step of Lomuto's partition of values[lo..hi] around the pivot values[hi]: j looks at its next value, which
    joins the small side (swapped to just after i) if it is at most the pivot; the last step swaps the pivot in
    between the two sides."""
    lo, hi, pivot = part["lo"], part["hi"], values[part["hi"]]
    j = part["j"]
    if j < hi:
        v = values[j]
        small = v <= pivot
        swap = None
        if small:
            part["i"] += 1
            if part["i"] != j:
                swap = (part["i"], j)
                values[part["i"]], values[j] = values[j], values[part["i"]]
        part["j"] += 1
        return {"kind": "compare", "j": j, "value": v, "pivot": pivot, "small": small, "swap": swap, "i": part["i"]}
    k = part["i"] + 1
    swap = (k, hi) if k != hi else None
    values[k], values[hi] = values[hi], values[k]
    part["done"], part["at"] = True, k
    return {"kind": "place", "at": k, "pivot": pivot, "swap": swap, "lo": lo, "hi": hi}


def _check_partition(state: dict, a: PartitionArgs) -> str | None:
    values = state["values"]
    if not all(isinstance(v, int | float) for v in values):
        return "partition needs numeric values"
    n = len(values)
    lo = 0 if a.lo is None else a.lo
    hi = n - 1 if a.hi is None else a.hi
    if not 0 <= lo <= hi < n:
        return f"lo and hi must satisfy 0 <= lo <= hi <= {n - 1}"
    part = state.get("part")
    if part is None or part["done"] or (part["lo"], part["hi"]) != (lo, hi):
        part = state["part"] = {"lo": lo, "hi": hi, "i": lo - 1, "j": lo, "done": False}
    state["last_part"] = partition_next(values, part)
    if part["done"]:
        state.setdefault("found", set()).add(part["at"])  # a placed pivot is where it belongs: green
    return None


def _said_partition(state: dict, a) -> str:
    ev = state["last_part"]
    if ev["kind"] == "compare":
        v, p = _fmt(ev["value"]), _fmt(ev["pivot"])
        out = (f"{v} <= pivot {p}: it joins the small side" + (" (swapped to the front of the large side)"
                                                                if ev["swap"] else "")
               if ev["small"] else f"{v} > pivot {p}: it stays on the large side")
        return out + f"; the row reads {_row(state)}"
    return (f"the pivot {_fmt(ev['pivot'])} swaps into place between the two sides, at index {ev['at']}, and turns "
            f"green; the row reads {_row(state)}")


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
        "partition_step": ActionSpec(
            "Quicksort's partition (Lomuto), one step (computed): the pivot is the last value of lo..hi; j looks at "
            "the next value, and a value at most the pivot joins the small side; the last step swaps the pivot in "
            "between, where it stays (green). Then partition each side with lo and hi.", PartitionArgs,
            _check_partition, _said_partition, reveals=True),
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
        "found": ActionSpec("Mark this cell green: found.", IndexArgs, _check_found,
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
    return {"values": vals, "tree": root, "merge": None, "comparisons": 0, "pairs": [], "splittable": runs is None}


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
        st.setdefault("pairs", []).append((a, b))
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


def ms_fronts(st: dict) -> tuple | None:
    """The two front values the next merge step compares (the merge in progress, or the next one ready), or None
    when no comparison is next (nothing ready to merge, or a run is used up and the rest is copied)."""
    v, m = st["values"], st["merge"]
    if m is not None:
        left, right = m["node"]["kids"]
        return (v[m["i"]], v[m["j"]]) if m["i"] < left["hi"] and m["j"] < right["hi"] else None
    ready = _ms_ready(st)
    if not ready or not all(k["sorted"] for k in ready[0]["kids"]):
        return None
    left, right = ready[0]["kids"]
    return v[left["lo"]], v[right["lo"]]


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
    equal_scale: bool = Field(False, description="the same unit on both axes, so a circle looks round: the complex "
                                                 "plane, geometry (on with a polar or parametric curve)")
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
    labels: list[str] | None = Field(None, description='a name beside each point, e.g. ["z", "1+2i"] (at most 6 '
                                                       "characters each)")
    colour: Colour = "BLUE"


MAX_PATH_SAMPLES = 241


class ParametricArgs(_Args):
    name: str = Field(description=r'its label in TeX (at most 12 characters), e.g. "c", "C_1"')
    x_t: str = Field(description='x as a formula in t, e.g. "cos(t)"')
    y_t: str = Field(description='y as a formula in t, e.g. "sin(2*t)"')
    t_from: float = 0.0
    t_to: float = Field(6.283185307179586, description="default 2 pi")
    colour: Colour = "TEAL"

    _name = field_validator("name")(_short(12))


class PolarArgs(_Args):
    name: str = Field(description=r'its label in TeX (at most 12 characters), e.g. "r", "r_1"')
    r: str = Field(description='the radius as a formula in t (the angle), e.g. "1 + cos(t)", "sin(3*t)"')
    t_from: float = 0.0
    t_to: float = Field(6.283185307179586, description="default 2 pi")
    colour: Colour = "TEAL"

    _name = field_validator("name")(_short(12))


class SectorArgs(_Args):
    r_from: float = Field(description="inner radius (0 for a pie slice)")
    r_to: float = Field(description="outer radius")
    t_from: float = Field(description="first angle, radians")
    t_to: float = Field(description="last angle, radians")
    label: str | None = Field(None, description="at most 8 characters, e.g. \"dA\"")
    colour: Colour = "GOLD"

    _label = field_validator("label")(_short(8))


class DotTArgs(_Args):
    curve: str = Field(description="a parametric or polar curve's name")
    t: float
    label: str | None = Field(None, description="at most 8 characters")
    colour: Colour = "YELLOW"

    _label = field_validator("label")(_short(8))


def path_points(kind: str, f1: str, f2: str | None, t0: float, t1: float, k: int = MAX_PATH_SAMPLES):
    """(ts, xs, ys) along a parametric curve (x_t, y_t) or a polar one (r(t) at angle t)."""
    import numpy as np

    ts = np.linspace(t0, t1, k)
    if kind == "polar":
        r = parse_fn(f1)(ts)
        return ts, r * np.cos(ts), r * np.sin(ts)
    return ts, parse_fn(f1)(ts), parse_fn(f2)(ts)


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
    if a.labels is not None and (len(a.labels) != len(a.xs) or any(not 1 <= len(lab) <= 6 for lab in a.labels)):
        return "labels: one name of 1-6 characters per point"
    if len(a.xs) > MAX_POINTS:
        return f"at most {MAX_POINTS} points"
    (xl, xh), (yl, yh) = state["x"], state["y"]
    for x, y in zip(a.xs, a.ys):
        if not (xl <= x <= xh and yl <= y <= yh):
            return f"the point ({_num(x)}, {_num(y)}) is off the axes"
    return None


def _check_path(kind: str):
    def check(state: dict, a) -> str | None:
        import numpy as np

        if a.name in state["curves"] or a.name in state.setdefault("paths", {}):
            return f"there is already a curve {a.name!r}"
        if not a.t_from < a.t_to:
            return "t_from is below t_to"
        try:
            f1, f2 = (a.r, None) if kind == "polar" else (a.x_t, a.y_t)
            _, xs, ys = path_points(kind, f1, f2, a.t_from, a.t_to)
        except ValueError as e:
            return str(e).replace(" x (or n, t)", " t")
        (xl, xh), (yl, yh) = state["x"], state["y"]
        inside = np.isfinite(xs) & np.isfinite(ys) & (xs >= xl) & (xs <= xh) & (ys >= yl) & (ys <= yh)
        if inside.mean() < 0.9:
            return (f"the curve leaves the axes (x {_num(np.nanmin(xs))} to {_num(np.nanmax(xs))}, y "
                    f"{_num(np.nanmin(ys))} to {_num(np.nanmax(ys))}): widen x_range or y_range")
        state["paths"][a.name] = (kind, f1, f2, a.t_from, a.t_to)
        return None
    return check


def _path_point(state: dict, name: str, t: float) -> tuple[float, float]:
    kind, f1, f2, _, _ = state["paths"][name]
    _, xs, ys = path_points(kind, f1, f2, t, t, 1)
    return float(xs[0]), float(ys[0])


def _check_sector(state: dict, a: SectorArgs) -> str | None:
    import math

    if not 0 <= a.r_from < a.r_to:
        return "0 <= r_from < r_to"
    if not 0 < a.t_to - a.t_from <= 2 * math.pi:
        return "t_from < t_to, at most a full turn"
    (xl, xh), (yl, yh) = state["x"], state["y"]
    for t in (a.t_from, (a.t_from + a.t_to) / 2, a.t_to):
        for r in (a.r_from, a.r_to):
            x, y = r * math.cos(t), r * math.sin(t)
            if not (xl <= x <= xh and yl <= y <= yh):
                return f"the sector reaches ({_num(x)}, {_num(y)}), off the axes"
    return None


def _said_sector(state: dict, a: SectorArgs) -> str:
    dt = a.t_to - a.t_from
    area = (a.r_to ** 2 - a.r_from ** 2) / 2 * dt
    mid = (a.r_from + a.r_to) / 2
    return (f"the polar cell between r = {_num(a.r_from)} and {_num(a.r_to)} and angles {_num(a.t_from)} to "
            f"{_num(a.t_to)} is shaded {a.colour.lower()}: its sides are dr = {_num(a.r_to - a.r_from)} and an arc "
            f"r dtheta = {_num(mid * dt)} long, its area {_num(area)}"
            + (f', labelled "{a.label}"' if a.label else ""))


def _check_dot_t(state: dict, a: DotTArgs) -> str | None:
    paths = state.get("paths", {})
    if a.curve not in paths:
        return (f"there is no parametric or polar curve {a.curve!r}"
                + (f" (they are {', '.join(paths)})" if paths else ""))
    _, _, _, t0, t1 = paths[a.curve]
    if not t0 <= a.t <= t1:
        return f"t = {_num(a.t)} is off the curve (t runs {_num(t0)} to {_num(t1)})"
    x, y = _path_point(state, a.curve, a.t)
    (xl, xh), (yl, yh) = state["x"], state["y"]
    if not (xl <= x <= xh and yl <= y <= yh):
        return f"at t = {_num(a.t)} the curve is at ({_num(x)}, {_num(y)}), off the axes"
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
        "points": ActionSpec("Data points (a scatter), 1-12 of them, optionally named (complex numbers on Re/Im "
                             "axes: 1+2i at (1, 2)).", PointsArgs, _check_points,
                             lambda s, a: f"{len(a.xs)} {a.colour.lower()} point{'s' if len(a.xs) != 1 else ''} at "
                                          + ", ".join(f"({_num(x)}, {_num(y)})" + (f" named {a.labels[k]}"
                                                                                     if a.labels else "")
                                                      for k, (x, y) in enumerate(zip(a.xs, a.ys)))),
        "parametric": ActionSpec("A curve (x(t), y(t)) for t from t_from to t_to: a path, a circle, a Lissajous "
                                 "figure.", ParametricArgs, _check_path("parametric"),
                                 lambda s, a: f"the curve {a.name}, (x, y) = ({a.x_t}, {a.y_t}) for t from "
                                              f"{_num(a.t_from)} to {_num(a.t_to)}, is drawn in "
                                              f"{a.colour.lower()}"),
        "polar": ActionSpec("A polar curve r(t) at angle t, for t from t_from to t_to: a cardioid, a rose.",
                            PolarArgs, _check_path("polar"),
                            lambda s, a: f"the polar curve {a.name}, r = {a.r} for angle t from {_num(a.t_from)} to "
                                         f"{_num(a.t_to)}, is drawn in {a.colour.lower()}"),
        "sector": ActionSpec("Shade a polar cell: between radii r_from and r_to and angles t_from and t_to (a pie "
                             "slice from r_from = 0); its sides and area are computed (area = (r_to^2 - r_from^2) / 2 "
                             "x dtheta). The same cell drawn again only changes its label.", SectorArgs,
                             _check_sector, _said_sector),
        "dot_t": ActionSpec("A dot on a parametric or polar curve at parameter t (computed).", DotTArgs, _check_dot_t,
                            lambda s, a: "a dot on {} at t = {}, the point ({}, {})".format(
                                a.curve, _num(a.t), *(_num(v) for v in _path_point(s, a.curve, a.t)))),
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


MAX_LABEL = 14  # a node's words, when it is a box
MAX_EDGE_LABEL = 6
# The video is portrait: 3.9 units of usable width, and a character at the smallest readable size is about 0.19
# units wide. So at most three boxes sit side by side (a row in "layers"/"tree", the columns of "flow"), each
# label wraps onto at most two lines, and a box diagram has at most four levels.
MAX_BOXES_PER_ROW = 3
MAX_BOX_LEVELS = 4
SAFE_WIDTH = 3.9
CHAR_W = 0.19


_NARROW = set("ijlrtfI:;!'|()[] ")


def _char_w(c: str) -> float:
    if c in ".,":
        return 0.07
    if c in _NARROW:
        return 0.11
    if c in "mwMW":
        return 0.27
    if c.isupper():
        return 0.26
    if c.isdigit():
        return 0.2
    return 0.13 if c in "-+=" else 0.185


def est_width(s: str) -> float:
    """About how wide a line of text is at the smallest readable size (units; Text at font 30, measured: "start"
    0.70, "print x" 1.05, "saw ab" 1.12, "merge halves" 2.19, "-0.4" 0.63, "8.8" 0.46, "ABCDEF" 1.67), with a 5%
    margin."""
    return 1.05 * sum(_char_w(c) for c in s)


def label_lines(label: str, max_width: float) -> list[str] | None:
    """The label wrapped onto lines at most `max_width` wide, or None if a single word is wider."""
    lines: list[str] = []
    for word in label.split():
        if est_width(word) > max_width:
            return None
        if lines and est_width(lines[-1] + " " + word) <= max_width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


def box_share(layout: str) -> float:
    """How much of the distance between two boxes in a row the boxes take: in "flow" and round a "circle" the
    arrows between them need the rest; in "layers" and "tree" rows hold no arrows."""
    return 0.62 if layout in ("flow", "circle") else 0.9


def box_width(nodes: list[str], edges: list[list[str]], layout: str, directed: bool,
              width: float = SAFE_WIDTH - 0.1) -> float:
    """How wide each box is drawn (graph.py lays the boxes out the same way)."""
    unit = graph_positions(nodes, edges, layout, directed)
    if layout == "layers":
        unit = spread_rows(unit)
    rows: dict[float, list[float]] = {}
    for x, y in unit.values():
        rows.setdefault(round(y, 6), []).append(x)
    gx = min([b - a for row in rows.values() for a, b in zip(sorted(row), sorted(row)[1:])] or [1.0])
    share = box_share(layout)
    return min(2.6, share * gx * width / (1 + share * gx))


def box_chars(side_by_side: int) -> int:
    """How many characters fit on one line of a box when this many boxes share a row."""
    k = max(side_by_side, 1)
    box = (SAFE_WIDTH - 0.12 * (k - 1)) / k if k > 1 else min(2.6, SAFE_WIDTH)
    return int((box - 0.24) / CHAR_W)


class GraphParams(_Args):
    nodes: list[str] = Field(description='2-8 node names, at most 2 characters each, e.g. ["s", "a", "b"]; with '
                                         "labels they are only ids for the calls")
    edges: list[list[str]] = Field(description='pairs of node names, e.g. [["s", "a"], ["a", "b"]] (at most 12); a '
                                               'third item labels the edge, e.g. ["q0", "q1", "a"], ["d", "e", "yes"], '
                                               '["r", "h", "0.3"] (at most 6 characters)')
    directed: bool = Field(False, description="arrows from the first node of each pair to the second")
    labels: dict[str, str] | None = Field(
        None, description="words for the nodes, drawn as boxes: a flowchart's steps, a tree's or a call tree's "
                          'entries, e.g. {"s": "start", "d": "x > 0?"} (at most 14 characters each; every node)')
    layout: Literal["layers", "tree", "flow", "circle"] = Field(
        "layers", description='"layers": rows by distance from the first node; "tree": the first node on top, each '
                              'node centred over its children (trees, call trees, probability trees); "flow": '
                              'columns left to right (pipelines, state machines, linked lists); "circle": round a '
                              "circle (a loop of steps: up to 5 boxes)")
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
            if len(e) not in (2, 3) or e[0] not in self.nodes or e[1] not in self.nodes:
                raise ValueError(f"edge {e}: give two node names from nodes (and optionally a label)")
            if e[0] == e[1] and not self.directed:
                raise ValueError(f"edge {e}: a node can't link to itself (only in a directed graph: a loop)")
            if len(e) == 3 and not 1 <= len(e[2]) <= MAX_EDGE_LABEL:
                raise ValueError(f"edge {e}: its label is 1-{MAX_EDGE_LABEL} characters")
            key = (e[0], e[1]) if self.directed else tuple(sorted(e[:2]))
            if key in seen:
                raise ValueError(f"edge {e[:2]} is listed twice")
            seen.add(key)
        if self.labels is not None:
            missing = [n for n in self.nodes if n not in self.labels]
            extra = [n for n in self.labels if n not in self.nodes]
            if missing or extra:
                raise ValueError(f"labels needs exactly the nodes: missing {missing}, unknown {extra}")
            long = [v for v in self.labels.values() if not 1 <= len(v) <= MAX_LABEL]
            if long:
                raise ValueError(f"label {long[0]!r}: 1-{MAX_LABEL} characters")
            if self.layout == "circle" and len(self.nodes) > 5:
                raise ValueError("at most 5 boxes round a circle")
            rows = graph_rows(self.nodes, self.edges, self.layout, self.directed)
            widest = max(rows)
            if widest > MAX_BOXES_PER_ROW:
                raise ValueError(f"{widest} boxes side by side; at most {MAX_BOXES_PER_ROW} fit on the portrait "
                                 "screen (use fewer nodes, or short names in circles without labels)")
            levels = len(rows) if self.layout != "flow" else max(
                graph_rows(self.nodes, self.edges, "layers", self.directed))
            if levels > MAX_BOX_LEVELS:
                raise ValueError(f"{levels} levels of boxes; at most {MAX_BOX_LEVELS} fit")
            # The words may fill the box but for a small margin (graph.py lets them shrink to 94%, still readable).
            room = (box_width(self.nodes, self.edges, self.layout, self.directed) - 0.12) / 0.94
            chars = int(room / 0.18)
            for label in self.labels.values():
                lines = label_lines(label, room)
                if lines is None or len(lines) > 2:
                    hint = ('; a loop of up to 5 steps fits better as layout "circle"' if self.layout == "flow"
                            else "")
                    raise ValueError(f"label {label!r} doesn't fit a box when {widest} share a row: at most two "
                                     f"lines of about {chars} characters (shorter words, or fewer boxes side by side"
                                     f"{hint})")
        return self


def _levels(nodes: list[str], adj: dict[str, list[str]]) -> tuple[list[list[str]], dict[str, str | None]]:
    """Breadth-first levels from the first node (then from each node not reached yet), and each node's parent."""
    levels: list[list[str]] = []
    parent: dict[str, str | None] = {}
    for root in nodes:
        if root in parent:
            continue
        parent[root] = None
        frontier = [root]
        while frontier:
            levels.append(frontier)
            nxt = []
            for u in frontier:
                for v in adj[u]:
                    if v not in parent:
                        parent[v] = u
                        nxt.append(v)
            frontier = nxt
    return levels, parent


def _layout_adjacency(nodes: list[str], edges: list[list[str]], directed: bool) -> dict[str, list[str]]:
    """The neighbours a layout's levels follow: along the arrows in a directed graph (a chain reads left to right
    even if its last node links back to the first), else both ways."""
    return graph_adjacency(nodes, [e[:2] for e in edges if e[0] != e[1]], directed=directed)


def graph_rows(nodes: list[str], edges: list[list[str]], layout: str, directed: bool = False) -> list[int]:
    """How many nodes sit side by side in each row ("layers", "tree") or how many columns there are ("flow")."""
    if layout == "circle":  # nodes at the same height share a row
        rows: dict[float, int] = {}
        for _, y in graph_positions(nodes, edges, "circle").values():
            rows[round(y, 3)] = rows.get(round(y, 3), 0) + 1
        return list(rows.values())
    levels, _ = _levels(nodes, _layout_adjacency(nodes, edges, directed))
    if layout == "flow":
        return [len(levels)]
    if layout == "tree":
        return [len(level) for level in levels]
    return [len(level) for level in levels]


def graph_positions(nodes: list[str], edges: list[list[str]], layout: str,
                    directed: bool = False) -> dict[str, tuple[float, float]]:
    """Each node's place in the unit square (y up). "layers": a row per distance from the first node (other parts
    below), each row ordered by where its neighbours above sit; "tree": the same rows, each node centred over its
    children (leaves spaced evenly); "flow": "layers" turned on its side, columns left to right; "circle": evenly
    round a circle."""
    import math

    if layout == "circle":
        k = len(nodes)
        return {n: (0.5 + 0.5 * math.sin(2 * math.pi * i / k), 0.5 + 0.5 * math.cos(2 * math.pi * i / k))
                for i, n in enumerate(nodes)}
    adj = _layout_adjacency(nodes, edges, directed)
    levels, parent = _levels(nodes, adj)
    adj = graph_adjacency(nodes, [e[:2] for e in edges if e[0] != e[1]], directed=False)  # for row order
    rows = len(levels)
    pos: dict[str, tuple[float, float]] = {}
    if layout == "tree":
        kids: dict[str, list[str]] = {n: [] for n in nodes}
        for n in nodes:  # children in the order their edges are listed
            if parent[n] is not None:
                kids[parent[n]].append(n)
        for n in kids:
            kids[n].sort(key=lambda c: next(i for i, e in enumerate(edges) if c in e[:2] and n in e[:2]))
        depth = {}
        for li, level in enumerate(levels):
            for n in level:
                depth[n] = li
        slot = [0]
        xs: dict[str, float] = {}

        def place(n: str) -> None:
            if not kids[n]:
                xs[n] = slot[0]
                slot[0] += 1
                return
            for c in kids[n]:
                place(c)
            xs[n] = (xs[kids[n][0]] + xs[kids[n][-1]]) / 2

        for n in nodes:
            if parent[n] is None:
                place(n)
        width = max(slot[0] - 1, 1)
        depths = max(depth.values()) if depth else 0
        for n in nodes:
            x = 0.5 if slot[0] == 1 else xs[n] / width
            y = 0.5 if depths == 0 else 1 - depth[n] / depths
            pos[n] = (x, y)
        return pos
    for li, level in enumerate(levels):
        if li:  # order by the mean place of neighbours already placed (fewer crossings)
            def key(n: str) -> float:
                xs_ = [pos[m][0] for m in adj[n] if m in pos]
                return sum(xs_) / len(xs_) if xs_ else 0.5
            level = sorted(level, key=key)
        y = 0.5 if rows == 1 else 1 - li / (rows - 1)
        for i, n in enumerate(level):  # (i + 0.5) / k: a row's nodes use the width, leaving room for edge labels
            pos[n] = ((i + 0.5) / len(level), y)
    if layout == "flow":  # rows become columns, left to right
        return {n: (1 - y, x) for n, (x, y) in pos.items()}
    return pos


def spread_rows(pos: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    """Each row's nodes spread from edge to edge (0..1) instead of (i + 1) / (k + 1): for boxes, which need the
    width more than a margin."""
    rows: dict[float, list[str]] = {}
    for n, (x, y) in pos.items():
        rows.setdefault(round(y, 6), []).append(n)
    out = dict(pos)
    for row in rows.values():
        row.sort(key=lambda n: pos[n][0])
        for i, n in enumerate(row):
            out[n] = (0.5 if len(row) == 1 else i / (len(row) - 1), pos[n][1])
    return out


def graph_adjacency(nodes: list[str], edges: list[list[str]], directed: bool) -> dict[str, list[str]]:
    """Each node's neighbours, in the order the edges are listed (the order a search tries them)."""
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for u, v, *_ in edges:
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


class GhostMarkArgs(_Args):
    nodes: list[str] = Field(description="the nodes the wrong idea is about (1-4)")
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


class GhostEdgeArgs(_Args):
    a: str
    b: str
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


# ---- Algorithms on weighted and directed graphs, computed -------------------------------------------------------


def graph_weights(st: dict) -> dict | None:
    """Each edge's weight (its label as a number), or None if some edge has none."""
    try:
        return {k: float(v) for k, v in st["edge_labels"].items()} if len(st["edge_labels"]) == len(st["edges"]) \
            else None
    except ValueError:
        return None


def _w(st: dict, a: str, b: str) -> float:
    return st["weights"][(a, b) if st["directed"] else tuple(sorted((a, b)))]


def dijkstra_next(st: dict) -> dict:
    """Settle the closest unsettled node, then relax its edges."""
    d = st["algo"]
    if not d["dist"]:
        d["dist"][d["start"]] = 0.0
    open_ = [n for n in d["dist"] if n not in d["settled"]]
    if not open_:
        d["done"] = True
        return {"settled": None}
    u = min(open_, key=lambda n: (d["dist"][n], st["nodes"].index(n)))
    d["settled"].append(u)
    updated = []
    for v in st["adj"][u]:
        if v in d["settled"] or not _has_edge(st, u, v):
            continue
        nd = d["dist"][u] + _w(st, u, v)
        if v not in d["dist"] or nd < d["dist"][v]:
            d["dist"][v], d["prev"][v] = nd, u
            updated.append((v, nd))
    d["done"] = all(n in d["settled"] for n in d["dist"]) and not any(
        v not in d["dist"] for v in st["adj"][u] if _has_edge(st, u, v))
    return {"settled": u, "dist": d["dist"][u], "updated": updated}


def prim_next(st: dict) -> dict:
    d = st["algo"]
    if not d["tree"]:
        d["tree"].append(d["start"])
        return {"added": d["start"], "edge": None}
    best = None
    for u in d["tree"]:
        for v in st["adj"][u]:
            if v not in d["tree"]:
                w = _w(st, u, v)
                if best is None or w < best[0]:
                    best = (w, u, v)
    if best is None:
        d["done"] = True
        return {"added": None}
    w, u, v = best
    d["tree"].append(v)
    d["edges"].append((u, v))
    d["total"] += w
    d["done"] = len(d["tree"]) == len(st["nodes"])
    return {"added": v, "edge": (u, v), "w": w, "total": d["total"]}


def kruskal_next(st: dict) -> dict:
    d = st["algo"]
    if d["queue"] is None:
        d["queue"] = sorted(st["weights"], key=lambda k: (st["weights"][k], k))
        d["parent"] = {n: n for n in st["nodes"]}

    def find(x):
        while d["parent"][x] != x:
            x = d["parent"][x]
        return x

    if not d["queue"] or len(d["edges"]) == len(st["nodes"]) - 1:
        d["done"] = True
        return {"edge": None}
    a, b = d["queue"].pop(0)
    w = st["weights"][(a, b)]
    ra, rb = find(a), find(b)
    if ra == rb:
        return {"edge": (a, b), "w": w, "taken": False}
    d["parent"][ra] = rb
    d["edges"].append((a, b))
    d["total"] += w
    d["done"] = len(d["edges"]) == len(st["nodes"]) - 1
    return {"edge": (a, b), "w": w, "taken": True, "total": d["total"]}


def topo_next(st: dict) -> dict:
    d = st["algo"]
    if d["indeg"] is None:
        d["indeg"] = {n: 0 for n in st["nodes"]}
        for a, b in st["edges"]:
            d["indeg"][b] += 1
    ready = [n for n in st["nodes"] if n not in d["order"] and d["indeg"][n] == 0]
    if not ready:
        d["done"] = True
        left = [n for n in st["nodes"] if n not in d["order"]]
        return {"node": None, "cycle": left}
    u = ready[0]
    d["order"].append(u)
    for v in st["adj"][u]:
        if (u, v) in st["edges"]:
            d["indeg"][v] -= 1
    d["done"] = len(d["order"]) == len(st["nodes"])
    return {"node": u}


_ALGOS = {"dijkstra": lambda start: {"kind": "dijkstra", "start": start, "dist": {}, "settled": [], "prev": {},
                                     "done": False},
          "prim": lambda start: {"kind": "prim", "start": start, "tree": [], "edges": [], "total": 0.0, "done": False},
          "kruskal": lambda start: {"kind": "kruskal", "start": None, "queue": None, "edges": [], "total": 0.0,
                                    "done": False, "parent": {}},
          "topo": lambda start: {"kind": "topo", "start": None, "indeg": None, "order": [], "done": False}}
_NEXT = {"dijkstra": dijkstra_next, "prim": prim_next, "kruskal": kruskal_next, "topo": topo_next}


def _check_algo(kind: str):
    def check(st: dict, a) -> str | None:
        start = getattr(a, "start", None)
        if start is not None and (problem := _need_nodes(st, start)):
            return problem
        if kind in ("dijkstra", "prim", "kruskal"):
            st["weights"] = graph_weights(st)
            if st["weights"] is None:
                return f"{kind} needs a weight on every edge: a number as each edge's third item"
            if any(w < 0 for w in st["weights"].values()) and kind == "dijkstra":
                return "Dijkstra needs weights of 0 or more"
            if kind in ("prim", "kruskal") and st["directed"]:
                return f"{kind} builds a spanning tree of an undirected graph"
        if kind == "topo" and not st["directed"]:
            return "a topological order needs a directed graph"
        algo = st.get("algo")
        if algo is None or algo["kind"] != kind or algo.get("start") != start:
            algo = st["algo"] = _ALGOS[kind](start)
        if algo["done"]:
            return f"{kind} is done: call it again on a new graph, or reset"
        st["last"] = _NEXT[kind](st)
        return None
    return check


def _said_algo(kind: str):
    def says(st: dict, a) -> str:
        ev, d = st["last"], st["algo"]
        nm = lambda n: _name(st, n)  # noqa: E731
        if kind == "dijkstra":
            if ev["settled"] is None:
                return "every node reachable is settled"
            out = f"node {nm(ev['settled'])} is settled at distance {_num(ev['dist'])}, the smallest open"
            if ev["updated"]:
                out += "; its edges update " + ", ".join(f"{nm(v)} to {_num(x)}" for v, x in ev["updated"])
            return out
        if kind == "prim":
            if ev.get("edge") is None:
                return f"the tree starts at {nm(ev['added'])}" if ev.get("added") else "the tree spans everything"
            u, v = ev["edge"]
            return (f"the cheapest edge out of the tree, {nm(u)}-{nm(v)} ({_num(ev['w'])}), joins it; total "
                    f"{_num(ev['total'])}")
        if kind == "kruskal":
            if ev["edge"] is None:
                return "the spanning tree is complete"
            u, v = ev["edge"]
            if not ev["taken"]:
                return f"the next cheapest edge, {nm(u)}-{nm(v)} ({_num(ev['w'])}), would close a cycle: skipped"
            return f"the next cheapest edge, {nm(u)}-{nm(v)} ({_num(ev['w'])}), joins the tree; total {_num(ev['total'])}"
        if ev["node"] is None:
            return "no node is left without incoming edges" + (f": {', '.join(map(nm, ev['cycle']))} form a cycle"
                                                              if ev["cycle"] else "")
        return (f"node {nm(ev['node'])} has no incoming edges left, so it comes next; order so far: "
                f"{', '.join(map(nm, d['order']))}")
    return says


class OptStartArgs(_Args):
    start: str = Field(description="the node it starts from")


class WalkArgs(_Args):
    to: str = Field(description="the node the marker moves to, along an edge (the first walk puts it there)")


class FeedArgs(_Args):
    symbol: str = Field(description="the input read: the marker follows the edge with this label")


def _graph_state(p: GraphParams) -> dict:
    return {"adj": graph_adjacency(p.nodes, p.edges, p.directed), "nodes": list(p.nodes), "directed": p.directed,
            "edges": {(e[0], e[1]) if p.directed else tuple(sorted(e[:2])) for e in p.edges}, "search": None,
            "last": None, "labels": dict(p.labels or {}), "at": None, "walked": None, "read": "", "algo": None,
            "edge_labels": {((e[0], e[1]) if p.directed else tuple(sorted(e[:2]))): e[2] for e in p.edges
                            if len(e) == 3}}


def _name(st: dict, n: str) -> str:
    """A node as the sentences say it: its words if it is a box."""
    return f'"{st["labels"][n]}"' if n in st["labels"] else n


def _edge_label(st: dict, a: str, b: str) -> str | None:
    return st["edge_labels"].get((a, b) if st["directed"] else tuple(sorted((a, b))))


def _check_walk(state: dict, a: WalkArgs) -> str | None:
    if problem := _need_nodes(state, a.to):
        return problem
    at = state["at"]
    if at is not None and not _has_edge(state, at, a.to):
        return f"there is no edge from {at} to {a.to}, so the marker can't go there"
    state["walked"], state["at"] = (at, a.to), a.to
    return None


def _check_feed(state: dict, a: FeedArgs) -> str | None:
    at = state["at"] if state["at"] is not None else state["nodes"][0]
    out = [v for v in state["adj"][at] if _edge_label(state, at, v) == a.symbol and _has_edge(state, at, v)]
    if not out:
        labels = sorted({_edge_label(state, at, v) for v in state["adj"][at] if _has_edge(state, at, v)} - {None})
        return (f"no edge out of {at} is labelled {a.symbol!r}" + (f" (its edges read {', '.join(labels)})"
                                                                     if labels else ""))
    if len(out) > 1:
        return f"two edges out of {at} read {a.symbol!r}; the machine must have one"
    state["walked"], state["at"] = (at, out[0]), out[0]
    state["read"] += a.symbol
    return None


def _said_walk(state: dict, a) -> str:
    frm, to = state["walked"]
    if frm is None:
        return f"a gold marker appears at {_name(state, to)}"
    label = _edge_label(state, frm, to)
    return (f"the marker moves from {_name(state, frm)} to {_name(state, to)}"
            + (f' along the edge marked "{label}"' if label else ""))


def _said_feed(state: dict, a) -> str:
    frm, to = state["walked"]
    return (f'reading "{a.symbol}", the marker follows the edge from {_name(state, frm)} to {_name(state, to)}; '
            f'input read so far: "{state["read"]}"')


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
    nm = lambda ns: ", ".join(_name(state, n) for n in ns)  # noqa: E731
    back = f"it backs up from {nm(ev['finished'])}, then " if ev["finished"] else ""
    if ev["visit"] is None:
        missed = [n for n in state["nodes"] if n not in s["visited"]]
        out = f"{back}DFS from {_name(state, s['start'])} is done: it reached {nm(s['visited'])}"
        return out + (f"; {nm(missed)} can't be reached" if missed else "")
    if ev["from"] is None:
        return f"DFS starts at {_name(state, ev['visit'])}, which turns yellow: visited {_name(state, ev['visit'])}"
    return (f"{back}DFS goes from {_name(state, ev['from'])} to {_name(state, ev['visit'])} along their edge; "
            f"visited so far: {nm(s['visited'])}")


def _said_bfs(state: dict, a) -> str:
    ev, s = state["last"], state["search"]
    if ev["level"] is None:
        missed = [n for n in state["nodes"] if n not in s["dist"]]
        return "BFS is done: no new nodes" + (f"; {', '.join(_name(state, n) for n in missed)} can't be reached"
                                               if missed else "")
    if ev["level"] == 0:
        return f"BFS starts at {_name(state, ev['nodes'][0])}: distance 0"
    reached = ", ".join(f"{_name(state, v)} (from {_name(state, u)})" for v, u in ev["from"].items())
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
    say = (lambda n: f'"{p.labels[n]}"') if p.labels else (lambda n: n)
    edges = ", ".join(joiner.join(say(n) for n in e[:2]) + (f" ({e[2]})" if len(e) == 3 else "") for e in p.edges)
    kind = {"tree": "a tree", "flow": "a flow"}.get(p.layout, "a graph")
    kind = ("a directed " + kind[2:]) if p.directed and kind == "a graph" else kind
    what = f"boxes {', '.join(say(n) for n in p.nodes)}" if p.labels else f"nodes {', '.join(p.nodes)}"
    return f"{kind} of {what}, linked {edges}" + (f', titled "{p.title}"' if p.title else "")


GRAPH = TemplateSpec(
    name="Graph",
    family="graph",
    purpose="Boxes and arrows: a graph, a tree, a call tree, a flowchart, a state machine, a linked list. Nodes are "
            "circles with short names, or boxes with words (labels); edges can carry a label (a symbol, yes/no, a "
            "probability). Searches are computed: dfs_step reaches one new node per call in DFS order (also the "
            "order a recursion's calls run in), bfs_level one whole level per call. A gold marker walks along "
            "edges (walk), or reads an input symbol and follows the edge it labels (feed, computed: a state "
            "machine run). Highlight nodes, edges or a path; a wrong idea as a red dashed edge. Needs at least half "
            "the frame.",
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
        "dijkstra_step": ActionSpec("Dijkstra, one node per call (computed): the closest unsettled node is "
                                    "settled, then its edges update its neighbours' distances, shown beside them. "
                                    "Every edge needs a weight.", OptStartArgs, _check_algo("dijkstra"),
                                    _said_algo("dijkstra"), reveals=True),
        "prim_step": ActionSpec("Prim's minimum spanning tree, one node per call (computed): the cheapest edge "
                                "leaving the tree joins it.", OptStartArgs, _check_algo("prim"), _said_algo("prim"),
                                reveals=True),
        "kruskal_step": ActionSpec("Kruskal's minimum spanning tree, one edge per call (computed): the next "
                                   "cheapest edge joins unless it would close a cycle.", NoArgs,
                                   _check_algo("kruskal"), _said_algo("kruskal"), reveals=True),
        "topo_step": ActionSpec("Topological order (Kahn), one node per call (computed): a node with no incoming "
                                "edges left goes next. Directed graphs.", NoArgs, _check_algo("topo"),
                                _said_algo("topo"), reveals=True),
        "walk": ActionSpec("Move the gold marker along an edge to this node (the first walk puts it there): a "
                           "flowchart's path, a step through a list or a machine.", WalkArgs, _check_walk, _said_walk,
                           reveals=True),
        "feed": ActionSpec("State machine (computed): read one input symbol and follow the edge out of the marker's "
                           "node that it labels (from the first node if the marker isn't out yet).", FeedArgs,
                           _check_feed, _said_feed, reveals=True),
        "highlight": ActionSpec("Colour these nodes.", NodesArgs, lambda s, a: _need_nodes(s, *a.nodes),
                                lambda s, a: f"{', '.join(_name(s, n) for n in a.nodes)} "
                                             f"turn{'s' if len(a.nodes) == 1 else ''} {a.colour.lower()}"),
        "highlight_edge": ActionSpec("Colour one edge.", EdgeArgs, _check_edge,
                                     lambda s, a: f"the edge {a.a}-{a.b} turns {a.colour.lower()}"),
        "path": ActionSpec("Colour a path: the edges between consecutive nodes.", NodesArgs, _check_path,
                           lambda s, a: f"the path {' -> '.join(_name(s, n) for n in a.nodes)} lights up in "
                                        f"{a.colour.lower()}",
                           reveals=True),
        "ghost_edge": ActionSpec("A wrong idea: a red dashed edge (it may not exist), with the idea noted in red.",
                                 GhostEdgeArgs, lambda s, a: _need_nodes(s, a.a, a.b),
                                 lambda s, a: f'a wrong idea: a red dashed edge {a.a}-{a.b}, noted "{a.text}"'),
        "ghost_mark": ActionSpec("A wrong idea about nodes (a wrong order, a distance taken as final too soon): "
                                 "red dashed rings round them, noted in red.", GhostMarkArgs,
                                 lambda s, a: ("ring 1-4 nodes" if not 1 <= len(a.nodes) <= 4
                                               else _need_nodes(s, *a.nodes)),
                                 lambda s, a: f"a wrong idea: red dashed rings round "
                                              f'{", ".join(_name(s, n) for n in a.nodes)}, noted "{a.text}"'),
        "note": ActionSpec("A short line of text above the graph.", NoteArgs,
                           says=lambda s, a: f'note above the graph: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, the ghost and the note (a search's colours stay).",
                            says=lambda s, a: "the graph's highlights, ghost and note clear"),
        "reset": ActionSpec("Clear everything, a search's colours and the marker too.",
                            check=lambda s, a: s.update(search=None, at=None, read="", algo=None) or None,
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


# --------------------------------------------------------------------------
# BarChart: a few quantities side by side, with totals, shares and averages computed
# --------------------------------------------------------------------------
# For the coverage study's bar_meter, probability and series pictures (27 of its 77 KUs with no template): counts,
# frequencies, a distribution, partial sums. Totals, running sums, shares, the mean and an expected value are
# computed from the bars, so they are always right.

MAX_BARS = 13  # a deck's ranks; past 8 the bars are too narrow for their numbers
MAX_BAR_LABEL = 8


def nice_top(v: float) -> float:
    """A round number a little above v, for the top of the axis: 1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10 x 10^k."""
    import math

    if v <= 0:
        return 1.0
    k = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * k >= v * 1.08:
            return round(m * k, 10)
    return round(10 * k, 10)


def bar_slot(n: int) -> float:
    """The width each bar's slot gets when n share the chart (bar_chart.py lays them out the same way)."""
    return (SAFE_WIDTH - 0.1) / max(n, 1)


def bar_label_fits(label: str, n: int) -> bool:
    return est_width(label) <= bar_slot(n) * 0.95


def bar_chars(n: int) -> int:
    """About how many characters fit under one bar when n share the width."""
    return max(1, int(bar_slot(n) * 0.95 / 0.18))


class BarParams(_Args):
    labels: list[str] = Field(description='1-13 bar names, left to right, e.g. ["H", "T"], ["1", "2", "3"], '
                                          '["Mon", "Tue"]; short (with 8 bars about 2 characters, with 13 one)')
    values: list[float] = Field(description="each bar's height, 0 or more (counts, amounts, probabilities)")
    y_max: float | None = Field(None, description="the top of the scale; left out, it fits the bars (and grows if "
                                                  "a bar outgrows it)")
    y_label: str | None = Field(None, description='what the heights measure, e.g. "count", "P(x)" (at most 14 '
                                                  "characters)")
    colour: Colour = "BLUE"
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))
    _y_label = field_validator("y_label")(_short(14))

    @model_validator(mode="after")
    def _fits(self) -> BarParams:
        n = len(self.labels)
        if not 1 <= n <= MAX_BARS:
            raise ValueError(f"{n} bars; use 1-{MAX_BARS}")
        if len(self.values) != n:
            raise ValueError(f"{n} labels but {len(self.values)} values: give one value per bar")
        if len(set(self.labels)) != n:
            raise ValueError("bar labels must differ")
        long = [lab for lab in self.labels if not 1 <= len(lab) <= MAX_BAR_LABEL or not bar_label_fits(lab, n)]
        if long:
            raise ValueError(f"label {long[0]!r} is too wide under one of {n} bars (about {bar_chars(n)} characters "
                             'fit; "T" for ten, "J" for jack)')
        if any(v < 0 for v in self.values):
            raise ValueError("bar heights are 0 or more")
        if self.y_max is not None and self.y_max < max(self.values):
            raise ValueError(f"y_max {self.y_max:g} is below the tallest bar ({max(self.values):g})")
        return self


class BarArgs(_Args):
    label: str
    value: float = Field(description="the new height, 0 or more")


class BarLabelsArgs(_Args):
    labels: list[str]
    colour: Colour = "YELLOW"


class BarPairArgs(_Args):
    a: str
    b: str


class BarSeriesArgs(_Args):
    fn: str = Field(description='the n-th bar\'s height as a formula in n, e.g. "8*0.5**(n-1)", "1/n**2", "n"')
    n_from: int = Field(1, description="the first n")
    n_to: int = Field(5, description="the last n (at most 13 bars)")
    label: str = Field("n", description='each bar is named this followed by n, e.g. "R" gives R1, R2 ...; "n" '
                                         "gives 1, 2 ...")


class BarGhostArgs(_Args):
    label: str
    value: float = Field(description="the wrong height")
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _bar_state(p: BarParams) -> dict:
    return {"labels": list(p.labels), "values": [float(v) for v in p.values], "last": None,
            "y_max": p.y_max or nice_top(max(p.values) or 1)}


def _need_bars(st: dict, *labels: str) -> str | None:
    bad = [lab for lab in labels if lab not in st["labels"]]
    return f"there is no bar {bad[0]!r} (bars: {', '.join(st['labels'])})" if bad else None


def _bar_value(st: dict, label: str) -> float:
    return st["values"][st["labels"].index(label)]


def _check_set_bar(st: dict, a: BarArgs) -> str | None:
    if problem := _need_bars(st, a.label):
        return problem
    if a.value < 0:
        return "a bar's height is 0 or more"
    i = st["labels"].index(a.label)
    st["last"] = (st["values"][i], a.value)
    st["values"][i] = float(a.value)
    st["y_max"] = max(st["y_max"], nice_top(a.value)) if a.value > st["y_max"] else st["y_max"]
    return None


def _check_add_bar(st: dict, a: BarArgs) -> str | None:
    if a.label in st["labels"]:
        return f"there is already a bar {a.label!r}: use set to change it"
    n = len(st["labels"]) + 1
    if n > MAX_BARS:
        return f"at most {MAX_BARS} bars"
    if not all(bar_label_fits(lab, n) for lab in st["labels"] + [a.label]):
        return f"with {n} bars a label is at most about {bar_chars(n)} characters"
    if a.value < 0:
        return "a bar's height is 0 or more"
    st["labels"].append(a.label)
    st["values"].append(float(a.value))
    st["y_max"] = max(st["y_max"], nice_top(a.value)) if a.value > st["y_max"] else st["y_max"]
    return None


def bar_series(a: BarSeriesArgs) -> tuple[list[str], list[float]]:
    """The bars a formula gives: labels and heights, computed."""
    import math

    f = parse_fn(a.fn)
    labels, values = [], []
    for n in range(a.n_from, a.n_to + 1):
        v = float(f(float(n)))
        if not math.isfinite(v):
            raise ValueError(f"{a.fn} isn't a number at n = {n}")
        labels.append(str(n) if a.label == "n" else f"{a.label}{n}")
        values.append(v)
    return labels, values


def _check_bar_series(st: dict, a: BarSeriesArgs) -> str | None:
    if not 1 <= a.n_to - a.n_from + 1 <= MAX_BARS:
        return f"1-{MAX_BARS} bars (n_from to n_to)"
    try:
        labels, values = bar_series(a)
    except ValueError as e:
        return str(e)
    if any(v < 0 for v in values):
        return "bar heights are 0 or more"
    if not all(bar_label_fits(lab, len(labels)) for lab in labels):
        return f"the bar names ({labels[-1]}) are too wide for {len(labels)} bars: a shorter label, or fewer bars"
    st["labels"], st["values"] = labels, values
    st["y_max"] = nice_top(max(values) or 1)
    return None


def _check_cumulative(st: dict, a) -> str | None:
    total = 0.0
    for i, v in enumerate(st["values"]):
        total += v
        st["values"][i] = total
    if total > st["y_max"]:
        st["y_max"] = nice_top(total)
    return None


def _check_normalize(st: dict, a) -> str | None:
    total = sum(st["values"])
    if total <= 0:
        return "every bar is 0: there is no total to divide by"
    st["values"] = [v / total for v in st["values"]]
    st["y_max"] = nice_top(max(st["values"]))
    return None


def _check_expected(st: dict, a) -> str | None:
    try:
        xs = [float(lab) for lab in st["labels"]]
    except ValueError:
        return "an expected value needs numbers as the bar labels (the outcomes), e.g. 1, 2, 3"
    total = sum(st["values"])
    if total <= 0:
        return "every bar is 0"
    st["last"] = sum(x * v for x, v in zip(xs, st["values"])) / total
    return None


def _bars_words(st: dict) -> str:
    return ", ".join(f"{lab}: {_num(v)}" for lab, v in zip(st["labels"], st["values"]))


def _said_compare(st: dict, a: BarPairArgs) -> str:
    va, vb = _bar_value(st, a.a), _bar_value(st, a.b)
    rel = "taller than" if va > vb else "shorter than" if va < vb else "as tall as"
    sign = ">" if va > vb else "<" if va < vb else "="
    return (f"bars {a.a} and {a.b} light up: {a.a} ({_num(va)}) is {rel} {a.b} ({_num(vb)}), noted "
            f'"{_num(va)} {sign} {_num(vb)}"')


def _describe_bars(p: BarParams) -> str:
    st = _bar_state(p)
    narrow = "; the bars are too narrow to carry their numbers" if len(p.labels) > 8 else ""
    return (f"a bar chart of {_bars_words(st)}" + (f" ({p.y_label})" if p.y_label else "") + narrow
            + (f', titled "{p.title}"' if p.title else ""))


BAR_CHART = TemplateSpec(
    name="BarChart",
    family="bar_meter",
    purpose="A few quantities as bars side by side, each with its value on top: counts, amounts, frequencies, a "
            "probability distribution, partial sums. Computed: a total, running totals (cumulative), each bar as "
            "its share of the total (normalize), the mean, and an expected value (bars labelled with numbers). "
            "Needs at least half the frame.",
    params=BarParams,
    min_rows=3,
    init_state=_bar_state,
    noun="bar chart",
    describe=_describe_bars,
    actions={
        "set": ActionSpec("Change one bar's height (it grows or shrinks).", BarArgs, _check_set_bar,
                          lambda s, a: f"bar {a.label} goes from {_num(s['last'][0])} to {_num(a.value)}",
                          reveals=True),
        "add_bar": ActionSpec("A new bar on the right.", BarArgs, _check_add_bar,
                          lambda s, a: f"a new bar {a.label} rises to {_num(a.value)}", reveals=True),
        "series": ActionSpec("Replace the bars with a formula's terms, n = n_from..n_to (computed): a geometric "
                             "or discounted sequence, 1/n^2, then cumulative for its partial sums.", BarSeriesArgs,
                             _check_bar_series,
                             lambda s, a: f"the bars become the terms of {a.fn}: {_bars_words(s)}", reveals=True),
        "highlight": ActionSpec("Colour these bars.", BarLabelsArgs, lambda s, a: _need_bars(s, *a.labels),
                                lambda s, a: (f"bar {a.labels[0]} turns" if len(a.labels) == 1 else
                                              f"bars {', '.join(a.labels)} turn") + f" {a.colour.lower()}"),
        "compare": ActionSpec("Light up two bars and note which is taller (computed).", BarPairArgs,
                              lambda s, a: _need_bars(s, a.a, a.b), _said_compare, reveals=True),
        "total": ActionSpec("Note the sum of all the bars (computed).",
                            says=lambda s, a: f"the total of the bars, {_num(sum(s['values']))}, is noted",
                            reveals=True),
        "cumulative": ActionSpec("Each bar becomes the running total up to it (computed): partial sums, a "
                                 "cumulative distribution.", NoArgs, _check_cumulative,
                                 lambda s, a: f"each bar becomes the running total: {_bars_words(s)}", reveals=True),
        "normalize": ActionSpec("Each bar becomes its share of the total (computed): counts to relative "
                                "frequencies or probabilities that add to 1.", NoArgs, _check_normalize,
                                lambda s, a: f"each bar becomes its share of the total: {_bars_words(s)}",
                                reveals=True),
        "mean_line": ActionSpec("A dashed line across the chart at the bars' mean height (computed).",
                                says=lambda s, a: "a dashed line at the mean height, "
                                                  f"{_num(sum(s['values']) / len(s['values']))}", reveals=True),
        "expected": ActionSpec("The expected value, sum of outcome x probability, noted (computed; the bar labels "
                               "are the outcomes).", NoArgs, _check_expected,
                               lambda s, a: f"the expected value, {_num(s['last'])}, is noted", reveals=True),
        "ghost": ActionSpec("A wrong idea: a red dashed outline of a bar at the wrong height, noted in red.",
                            BarGhostArgs, lambda s, a: _need_bars(s, a.label),
                            lambda s, a: f'a wrong idea: a red dashed bar {a.label} at {_num(a.value)}, noted '
                                         f'"{a.text}"'),
        "note": ActionSpec("A short line of text above the bars.", NoteArgs,
                           says=lambda s, a: f'note above the bars: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, the ghost, the mean line and the note.",
                            says=lambda s, a: "the chart's highlights, ghost, line and note clear"),
    },
    example=[
        ['bars = BarChart(labels=["1", "2", "3", "4", "5", "6"], values=[3, 5, 4, 2, 4, 6], y_label="count", '
         'title="24 die rolls")'],
        ['bars.highlight(labels=["6"], colour="GOLD")'],
        ['bars.ghost(label="1", value=6, text="every face equal?")'],
        ["bars.clear()", "bars.total()"],
        ["bars.normalize()"],
        ["bars.expected()"],
        ['bars.compare(a="6", b="4")'],
    ],
)


# --------------------------------------------------------------------------
# NumberLine: points, jumps, intervals, a sequence's terms and an epsilon band on one axis
# --------------------------------------------------------------------------
# For the coverage study's number_line pictures (9 KUs) and series convergence: candidate guesses on a line,
# inequalities as intervals, a sequence closing in on its limit. A sequence's terms, and how many of them lie
# inside a band, are computed (parse_fn with n), so they are always right.

MAX_NL_POINTS = 8
MAX_TERMS = 12


class NLPoint(_Args):
    name: str = Field(description="at most 4 characters, e.g. \"a\", \"x0\", \"√2\"")
    x: float
    colour: Colour = "YELLOW"

    _name = field_validator("name")(_short(4))


class NumberLineParams(_Args):
    x_range: list[float] = Field(description="[low, high]")
    step: float | None = Field(None, description="the distance between ticks; left out, about 5-10 ticks")
    points: list[NLPoint] = Field(default_factory=list, description="points to show at the start (at most 8)")
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))
    _range = field_validator("x_range")(_range_pair)

    @model_validator(mode="after")
    def _fits(self) -> NumberLineParams:
        lo, hi = self.x_range
        if self.step is not None and not 0 < self.step <= hi - lo:
            raise ValueError("step is above 0 and at most the line's length")
        if len(nl_ticks(lo, hi, self.step)) > 21:
            raise ValueError("more than 21 ticks: use a larger step")
        if len(self.points) > MAX_NL_POINTS:
            raise ValueError(f"at most {MAX_NL_POINTS} points")
        names = [p.name for p in self.points]
        if len(set(names)) != len(names):
            raise ValueError("point names must differ")
        out = [p.name for p in self.points if not lo <= p.x <= hi]
        if out:
            raise ValueError(f"point {out[0]} is off the line ({_num(lo)} to {_num(hi)})")
        return self


def nl_ticks(lo: float, hi: float, step: float | None) -> list[float]:
    """The tick positions: every `step`, or a round step giving about 5-10 ticks."""
    import math

    if step is None:
        raw = (hi - lo) / 8
        k = 10 ** math.floor(math.log10(raw))
        step = next(m * k for m in (1, 2, 2.5, 5, 10) if m * k >= raw)
    first = math.ceil(lo / step - 1e-9) * step
    out, x = [], first
    while x <= hi + 1e-9 and len(out) < 100:
        out.append(round(x, 10))
        x += step
    return out


class NLPointArgs(NLPoint):
    pass


class NLMoveArgs(_Args):
    name: str
    x: float


class JumpArgs(_Args):
    from_x: float
    to_x: float
    label: str | None = Field(None, description='e.g. "+3", "x2", "/2" (at most 6 characters)')
    colour: Colour = "TEAL"

    _label = field_validator("label")(_short(6))


class IntervalArgs(_Args):
    lo: float | None = Field(None, description="the left end; None: it runs off the left edge (to -infinity)")
    hi: float | None = Field(None, description="the right end; None: to +infinity")
    lo_closed: bool = Field(True, description="the left end included (filled dot) or not (hollow)")
    hi_closed: bool = Field(True, description="the right end included or not")
    colour: Colour = "TEAL"


class SequenceArgs(_Args):
    fn: str = Field(description='the n-th term as a formula in n, e.g. "1/n", "(1 + 1/n)**n", "sum" not allowed')
    n_from: int = Field(1, description="the first n")
    n_to: int = Field(6, description="the last n (at most 12 terms)")
    colour: Colour = "YELLOW"


class BandArgs(_Args):
    center: float
    eps: float = Field(description="the half-width: the band runs from center - eps to center + eps")


class NLNamesArgs(_Args):
    names: list[str]
    colour: Colour = "YELLOW"


class NLGhostArgs(_Args):
    x: float
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _nl_state(p: NumberLineParams) -> dict:
    return {"range": tuple(p.x_range), "points": {q.name: q.x for q in p.points}, "terms": [], "last": None}


def _on_line(st: dict, *xs: float | None) -> str | None:
    lo, hi = st["range"]
    bad = [x for x in xs if x is not None and not lo <= x <= hi]
    return f"{_num(bad[0])} is off the line ({_num(lo)} to {_num(hi)})" if bad else None


def _check_nl_point(st: dict, a: NLPointArgs) -> str | None:
    if problem := _on_line(st, a.x):
        return problem
    if a.name not in st["points"] and len(st["points"]) >= MAX_NL_POINTS:
        return f"at most {MAX_NL_POINTS} points"
    st["last"] = st["points"].get(a.name)
    st["points"][a.name] = a.x
    return None


def _check_nl_move(st: dict, a: NLMoveArgs) -> str | None:
    if a.name not in st["points"]:
        return f"there is no point {a.name!r} (points: {', '.join(st['points']) or 'none'})"
    if problem := _on_line(st, a.x):
        return problem
    st["last"] = st["points"][a.name]
    st["points"][a.name] = a.x
    return None


def _check_interval(st: dict, a: IntervalArgs) -> str | None:
    if a.lo is None and a.hi is None:
        return "give at least one end"
    if a.lo is not None and a.hi is not None and not a.lo < a.hi:
        return "lo is below hi"
    return _on_line(st, a.lo, a.hi)


def nl_terms(fn: str, n_from: int, n_to: int) -> list[tuple[int, float]]:
    """(n, a_n) for each n, computed from the formula; terms that aren't finite are left out."""
    import math

    f = parse_fn(fn)
    out = []
    for n in range(n_from, n_to + 1):
        v = float(f(float(n)))
        if math.isfinite(v):
            out.append((n, v))
    return out


def _check_sequence(st: dict, a: SequenceArgs) -> str | None:
    if not 1 <= a.n_to - a.n_from + 1 <= MAX_TERMS:
        return f"1-{MAX_TERMS} terms (n_from to n_to)"
    try:
        terms = nl_terms(a.fn, a.n_from, a.n_to)
    except ValueError as e:
        return str(e)
    lo, hi = st["range"]
    inside = [(n, v) for n, v in terms if lo <= v <= hi]
    if not inside:
        return "no term lands on the line: widen x_range"
    st["terms"] = inside
    st["last"] = [(n, v) for n, v in terms if not lo <= v <= hi]
    return None


def _check_band(st: dict, a: BandArgs) -> str | None:
    if a.eps <= 0:
        return "eps is above 0"
    if problem := _on_line(st, a.center):
        return problem
    st["last"] = [n for n, v in st["terms"] if abs(v - a.center) < a.eps]
    return None


def _interval_words(a: IntervalArgs) -> str:
    left = "(-∞" if a.lo is None else ("[" if a.lo_closed else "(") + _num(a.lo)
    right = "∞)" if a.hi is None else _num(a.hi) + ("]" if a.hi_closed else ")")
    return f"{left}, {right}"


def _said_sequence(st: dict, a: SequenceArgs) -> str:
    terms = ", ".join(_num(v) for _, v in st["terms"])
    n0, n1 = st["terms"][0][0], st["terms"][-1][0]
    out = f"the terms a_{n0} to a_{n1} of {a.fn} appear as dots at {terms}"
    if st["last"]:
        out += f"; {len(st['last'])} more fall off the line"
    return out


def _said_band(st: dict, a: BandArgs) -> str:
    lo, hi = _num(a.center - a.eps), _num(a.center + a.eps)
    out = f"a band from {lo} to {hi} (within {_num(a.eps)} of {_num(a.center)}) is shaded"
    if st["terms"]:
        inside = st["last"]
        out += (f"; {len(inside)} of the {len(st['terms'])} terms lie inside"
                + (f", every one from a_{inside[0]} on" if inside and inside == [n for n, _ in st["terms"]
                                                                                  if n >= inside[0]] else ""))
    return out


def _describe_nl(p: NumberLineParams) -> str:
    out = f"a number line from {_num(p.x_range[0])} to {_num(p.x_range[1])}"
    if p.points:
        out += " with points " + ", ".join(f"{q.name} at {_num(q.x)}" for q in p.points)
    return out + (f', titled "{p.title}"' if p.title else "")


NUMBER_LINE = TemplateSpec(
    name="NumberLine",
    family="number_line",
    purpose="One axis with ticks: named points (and sliding them), jumps between numbers (an arc marked +3 or x2), "
            "intervals for inequalities (filled or hollow ends, or running off to infinity), a sequence's terms "
            "computed from its formula, and a band within eps of a number with the terms inside it counted "
            "(convergence). Needs at least half the frame (its title, jumps, names and ticks stack up).",
    params=NumberLineParams,
    min_rows=3,
    init_state=_nl_state,
    noun="number line",
    describe=_describe_nl,
    actions={
        "point": ActionSpec("Put a named point on the line (or move it there).", NLPointArgs, _check_nl_point,
                            lambda s, a: (f"point {a.name} moves from {_num(s['last'])} to {_num(a.x)}"
                                          if s["last"] is not None else f"point {a.name} at {_num(a.x)}")),
        "slide": ActionSpec("Slide a point to a new place: the next guess, the next term.", NLMoveArgs,
                           _check_nl_move, lambda s, a: f"point {a.name} slides from {_num(s['last'])} to {_num(a.x)}",
                           reveals=True),
        "jump": ActionSpec("An arc arrow from one number to another, with an optional label (+3, x2, /2).",
                           JumpArgs, lambda s, a: _on_line(s, a.from_x, a.to_x),
                           lambda s, a: f"an arrow jumps from {_num(a.from_x)} to {_num(a.to_x)}"
                                        + (f', marked "{a.label}"' if a.label else ""), reveals=True),
        "interval": ActionSpec("Shade an interval on the line: an inequality's solutions.", IntervalArgs,
                               _check_interval,
                               lambda s, a: f"the interval {_interval_words(a)} is shaded {a.colour.lower()}",
                               reveals=True),
        "sequence": ActionSpec("Dots at a sequence's terms a_n, computed from its formula.", SequenceArgs,
                               _check_sequence, _said_sequence, reveals=True),
        "band": ActionSpec("Shade the band within eps of a number; with a sequence shown, count the terms inside "
                           "(computed).", BandArgs, _check_band, _said_band, reveals=True),
        "highlight": ActionSpec("Colour these points.", NLNamesArgs,
                                lambda s, a: next((f"there is no point {n!r}" for n in a.names if n not in s["points"]),
                                                  None),
                                lambda s, a: f"{'point' if len(a.names) == 1 else 'points'} {', '.join(a.names)} "
                                             f"turn{'s' if len(a.names) == 1 else ''} {a.colour.lower()}"),
        "ghost": ActionSpec("A wrong idea: a red dashed marker at a number, noted in red.", NLGhostArgs,
                            lambda s, a: _on_line(s, a.x),
                            lambda s, a: f'a wrong idea: a red dashed marker at {_num(a.x)}, noted "{a.text}"'),
        "note": ActionSpec("A short line of text above the line.", NoteArgs,
                           says=lambda s, a: f'note above the line: "{a.text}"'),
        "clear": ActionSpec("Remove jumps, intervals, the band, the ghost and the note (points and terms stay).",
                            says=lambda s, a: "the line's jumps, shading, ghost and note clear"),
    },
    example=[
        ['line = NumberLine(x_range=[0, 1.2], step=0.2, title="a_n = 1/n")'],
        ['line.sequence(fn="1/n", n_from=1, n_to=8)'],
        ['line.ghost(x=0.1, text="stops at 0.1?")'],
        ["line.clear()", "line.band(center=0, eps=0.15)"],
        ['line.point(name="L", x=0, colour="GOLD")'],
    ],
)


# --------------------------------------------------------------------------
# Table: a grid of cells, filled by the writer or computed in order with arrows to what each cell came from
# --------------------------------------------------------------------------
# For the coverage study's dp_table and code_trace pictures, and truth tables, counting grids and Pascal's
# triangle. A table built from a rule (pascal, grid_paths, fibonacci, truth_table) is filled by code, one cell (or
# row) per call, each from the cells it depends on, so the numbers are always right.

MAX_TABLE_ROWS = 8
MAX_TABLE_COLS = 7
TABLE_RULES = ("pascal", "grid_paths", "fibonacci", "truth_table", "lcs", "edit_distance", "knapsack", "coin_change")
_TRUTH_VARS = ("A", "B", "C")


def truth_fn(expr: str):
    """A boolean expression in A, B, C with and, or, not, xor and brackets, as a function of a dict of 0/1 values.
    Parsed, never executed as code. Raises ValueError with what to fix."""
    import ast as _ast

    source = re.sub(r"\bxor\b", "^", expr.strip())
    try:
        tree = _ast.parse(source, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"{expr!r} isn't an expression: use A, B, C with and, or, not, xor and brackets") from e
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Name) and node.id not in _TRUTH_VARS:
            raise ValueError(f"{expr!r}: the variables are A, B and C")
        if not isinstance(node, (_ast.Expression, _ast.BoolOp, _ast.And, _ast.Or, _ast.UnaryOp, _ast.Not,
                                 _ast.BinOp, _ast.BitXor, _ast.Name, _ast.Load)):
            raise ValueError(f"{expr!r}: only A, B, C, and, or, not, xor and brackets")
    code = compile(tree, "<truth>", "eval")
    used = sorted({n.id for n in _ast.walk(tree) if isinstance(n, _ast.Name)})
    return (lambda env: int(bool(eval(code, {"__builtins__": {}}, {k: bool(v) for k, v in env.items()})))), used  # noqa: S307


def table_cell_width(cols: int) -> float:
    """The room for words in a cell when this many columns share the width (table.py: at most 1.3 wide)."""
    return min(1.3, (SAFE_WIDTH - 0.1) / max(cols, 1)) * 0.9


def table_cells(cols: int) -> int:
    """About how many characters fit in a cell when this many columns share the width."""
    return max(1, int(table_cell_width(cols) / 0.18))


class TableParams(_Args):
    columns: list[str] | None = Field(None, description='the column headers, e.g. ["i", "x", "total"] (1-7)')
    rows: list[list[Value]] | None = Field(
        None, description='the cells, row by row, "" for an empty cell to fill later (1-8 rows), e.g. '
                          '[[0, 5, ""], [1, 3, ""]]')
    row_labels: list[str] | None = Field(None, description="a label in front of each row (optional)")
    rule: Literal["pascal", "grid_paths", "fibonacci", "truth_table", "lcs", "edit_distance", "knapsack",
                  "coin_change"] | None = Field(
        None, description='instead of rows, a table code fills (fill_next): "pascal" (Pascal\'s triangle, size=[n] '
                          'rows), "grid_paths" (paths to each cell moving right or down, size=[rows, cols]), '
                          '"fibonacci" (one row, size=[n]), "truth_table" (every row of 0/1 values for expr), '
                          '"lcs" or "edit_distance" (of strings s and t), "knapsack" (items weights and values, '
                          'capacity), "coin_change" (fewest coins for each amount up to amount)')
    s: str | None = Field(None, description="lcs, edit_distance: the string down the side (at most 6 letters)")
    t: str | None = Field(None, description="lcs, edit_distance: the string across the top (at most 5 letters)")
    weights: list[int] | None = Field(None, description="knapsack: each item's weight")
    values: list[int] | None = Field(None, description="knapsack: each item's value")
    capacity: int | None = Field(None, description="knapsack: the bag's capacity (at most 5)")
    coins: list[int] | None = Field(None, description="coin_change: the coin values")
    amount: int | None = Field(None, description="coin_change: the largest amount (at most 5)")
    size: list[int] | None = Field(None, description="for pascal and fibonacci [n]; for grid_paths [rows, cols]")
    expr: str | None = Field(None, description='for truth_table: e.g. "A and not B", "(A or B) xor C"')
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    @model_validator(mode="after")
    def _fits(self) -> TableParams:
        if self.rule is None:
            if not self.rows:
                raise ValueError("give rows (or a rule for code to fill)")
            width = len(self.rows[0])
            if any(len(r) != width for r in self.rows):
                raise ValueError("every row has the same number of cells")
            if self.columns is not None and len(self.columns) != width:
                raise ValueError(f"{len(self.columns)} headers for {width} columns")
        elif self.rows is not None:
            raise ValueError("give rows or a rule, not both")
        nrows, ncols, _, cols = table_shape(self)
        if not 1 <= nrows <= MAX_TABLE_ROWS:
            raise ValueError(f"{nrows} rows; use 1-{MAX_TABLE_ROWS}")
        total_cols = ncols + (1 if table_row_labels(self) else 0)
        if not 1 <= total_cols <= MAX_TABLE_COLS:
            raise ValueError(f"{total_cols} columns; use 1-{MAX_TABLE_COLS}")
        if self.row_labels is not None and len(self.row_labels) != nrows and self.rule is None:
            raise ValueError(f"{len(self.row_labels)} row labels for {nrows} rows")
        cell = table_cell_width(total_cols)
        texts = [str(h) for h in cols or []] + [str(lab) for lab in table_row_labels(self) or []]
        texts += [_fmt(v) for row in self.rows or [] for v in row if v != ""]
        long = [t for t in texts if est_width(t) > cell]
        if long:
            raise ValueError(f"{long[0]!r} doesn't fit a cell: with {total_cols} columns, about "
                             f"{table_cells(total_cols)} characters (fewer columns, no row_labels, or rounder "
                             "numbers)")
        return self


def table_shape(p: TableParams) -> tuple[int, int, list[list[str]], list[str] | None]:
    """(rows, columns, the starting cells, the headers) of the table the parameters describe."""
    if p.rule is None:
        rows = [[_fmt(v) if v != "" else "" for v in r] for r in p.rows or []]
        return len(rows), len(rows[0]) if rows else 0, rows, p.columns
    size = p.size or []
    if p.rule == "truth_table":
        if not p.expr:
            raise ValueError("a truth_table needs expr")
        _, used = truth_fn(p.expr)
        n = len(used)
        rows = [[str((k >> (n - 1 - j)) & 1) for j in range(n)] + [""] for k in range(2 ** n)]
        return len(rows), n + 1, rows, used + [p.expr if len(p.expr) <= 6 else "out"]
    if p.rule == "grid_paths":
        if len(size) != 2 or min(size) < 1:
            raise ValueError("grid_paths needs size=[rows, cols]")
        r, c = size
        return r, c, [[""] * c for _ in range(r)], None
    if p.rule in ("lcs", "edit_distance"):
        if not p.s or not p.t or len(p.s) > 6 or len(p.t) > 5:
            raise ValueError(f"{p.rule} needs strings s (at most 6 letters) and t (at most 5)")
        r, c = len(p.s) + 1, len(p.t) + 1
        cells = [[""] * c for _ in range(r)]
        return r, c, cells, ["-"] + list(p.t)
    if p.rule == "knapsack":
        if not p.weights or not p.values or len(p.weights) != len(p.values) or p.capacity is None:
            raise ValueError("knapsack needs weights and values (one each per item) and a capacity")
        if not 1 <= p.capacity <= 5 or len(p.weights) > 6 or min(p.weights) < 1:
            raise ValueError("knapsack: a capacity of 1-5, at most 6 items, weights of 1 or more")
        return len(p.weights) + 1, p.capacity + 1, [[""] * (p.capacity + 1) for _ in range(len(p.weights) + 1)], \
            [str(k) for k in range(p.capacity + 1)]
    if p.rule == "coin_change":
        if not p.coins or p.amount is None or not 1 <= p.amount <= 5 or min(p.coins) < 1:
            raise ValueError("coin_change needs coins (values of 1 or more) and an amount of 1-5")
        return 1, p.amount + 1, [[""] * (p.amount + 1)], [str(k) for k in range(p.amount + 1)]
    if len(size) != 1 or size[0] < 2:
        raise ValueError(f"{p.rule} needs size=[n] (2 or more)")
    n = size[0]
    if p.rule == "pascal":
        return n, n, [[""] * n for _ in range(n)], [str(k) for k in range(n)]
    return 1, n, [[""] * n], [str(k) for k in range(n)]


def table_row_labels(p) -> list[str] | None:
    """The labels in front of the rows: given, or the rule's (a string's letters, the items, the coins)."""
    if p.row_labels:
        return list(p.row_labels)
    if p.rule == "fibonacci":
        return ["F"]
    if p.rule in ("lcs", "edit_distance") and p.s:
        return ["-"] + list(p.s)
    if p.rule == "knapsack" and p.weights:  # item numbers (their weights and values are in the sentence)
        return ["-"] + [str(k) for k in range(1, len(p.weights) + 1)]
    if p.rule == "coin_change":
        return ["#"]
    return None


def table_next(st: dict) -> dict | None:
    """The next cell a rule fills, its value and the cells it came from, or None when the table is full."""
    rule, cells = st["rule"], st["cells"]
    for r, row in enumerate(cells):
        for c, v in enumerate(row):
            if v != "" or (rule == "pascal" and c > r) or (rule == "truth_table" and c != len(row) - 1):
                continue
            if rule == "pascal":
                frm = [] if c in (0, r) else [(r - 1, c - 1), (r - 1, c)]
                value = 1 if not frm else sum(int(cells[a][b]) for a, b in frm)
            elif rule == "grid_paths":
                frm = [] if r == 0 or c == 0 else [(r - 1, c), (r, c - 1)]
                value = 1 if not frm else sum(int(cells[a][b]) for a, b in frm)
            elif rule == "fibonacci":
                frm = [] if c < 2 else [(0, c - 2), (0, c - 1)]
                value = c if not frm else sum(int(cells[a][b]) for a, b in frm)
            elif rule in ("lcs", "edit_distance", "knapsack", "coin_change"):
                return _dp_next(st, r, c)
            else:
                frm = [(r, j) for j in range(len(row) - 1)]
                value = st["truth"]({st["vars"][j]: int(row[j]) for j in range(len(row) - 1)})
            return {"cell": (r, c), "value": str(value), "from": frm}
    return None


def _dp_next(st: dict, r: int, c: int) -> dict:
    """The value of cell (r, c) of a classic DP table, the cells it comes from, and why."""
    cells, rule = st["cells"], st["rule"]
    num = lambda x: int(cells[x[0]][x[1]]) if cells[x[0]][x[1]] not in ("", "-") else None  # noqa: E731
    if rule in ("lcs", "edit_distance"):
        s, t = st["s"], st["t"]
        if r == 0 or c == 0:
            v = 0 if rule == "lcs" else r + c
            return {"cell": (r, c), "value": str(v), "from": [],
                    "why": "an empty prefix" + (" shares nothing" if rule == "lcs" else f": {v} edits")}
        a, b = s[r - 1], t[c - 1]
        diag, up, left = (r - 1, c - 1), (r - 1, c), (r, c - 1)
        if a == b:
            v = num(diag) + (1 if rule == "lcs" else 0)
            return {"cell": (r, c), "value": str(v), "from": [diag],
                    "why": f"{a} matches {b}, so the diagonal" + (" + 1" if rule == "lcs" else "")}
        if rule == "lcs":
            v = max(num(up), num(left))
            return {"cell": (r, c), "value": str(v), "from": [up, left],
                    "why": f"{a} and {b} differ, so the larger of up and left"}
        v = 1 + min(num(up), num(left), num(diag))
        return {"cell": (r, c), "value": str(v), "from": [up, left, diag],
                "why": f"{a} and {b} differ, so 1 + the smallest of up, left and the diagonal"}
    if rule == "knapsack":
        w, val = st["weights"], st["values"]
        if r == 0:
            return {"cell": (r, c), "value": "0", "from": [], "why": "no items: nothing to take"}
        wi, vi = w[r - 1], val[r - 1]
        skip = num((r - 1, c))
        if wi > c:
            return {"cell": (r, c), "value": str(skip), "from": [(r - 1, c)],
                    "why": f"item {r} (weight {wi}) doesn't fit in {c}, so the value above"}
        take = vi + num((r - 1, c - wi))
        v = max(skip, take)
        return {"cell": (r, c), "value": str(v), "from": [(r - 1, c), (r - 1, c - wi)],
                "why": f"skip item {r} ({skip}) or take it ({vi} + {num((r - 1, c - wi))} = {take}): {v}"}
    coins = st["coins"]
    if c == 0:
        return {"cell": (0, 0), "value": "0", "from": [], "why": "no coins for an amount of 0"}
    options = [(num((0, c - k)) + 1, k) for k in coins if k <= c and num((0, c - k)) is not None]
    if not options:
        return {"cell": (0, c), "value": "-", "from": [], "why": f"no coins add up to {c}"}
    best, k = min(options)
    return {"cell": (0, c), "value": str(best), "from": [(0, c - k) for _, k in sorted(options)][:3],
            "why": f"one more coin than the best of {', '.join(str(c - k) for _, k in sorted(options))}: "
                   f"{best} (with a {k})"}


class TableCellArgs(_Args):
    row: int
    col: int
    value: Value

    @model_validator(mode="after")
    def _short_value(self) -> TableCellArgs:
        if len(_fmt(self.value)) > 6:
            raise ValueError("a cell holds at most 6 characters")
        return self


def _cell_fits(st: dict, value) -> str | None:
    cols = st["ncols"] + (1 if st.get("lead") else 0)
    if est_width(_fmt(value)) > table_cell_width(cols):
        return f"{_fmt(value)!r} doesn't fit a cell: with {cols} columns, about {table_cells(cols)} characters"
    return None


class CellsArgs(_Args):
    cells: list[list[int]] = Field(description="[row, col] pairs, e.g. [[0, 1], [2, 2]]")
    colour: Colour = "YELLOW"


class RowArgs(_Args):
    row: int
    colour: Colour = "YELLOW"


class ColArgs(_Args):
    col: int
    colour: Colour = "YELLOW"


class DependsArgs(_Args):
    cell: list[int] = Field(description="[row, col] of the cell")
    on: list[list[int]] = Field(description="the [row, col] cells it is worked out from")


class TableGhostArgs(_Args):
    row: int
    col: int
    value: Value
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _table_state(p: TableParams) -> dict:
    nrows, ncols, cells, cols = table_shape(p)
    st = {"rule": p.rule, "cells": cells, "nrows": nrows, "ncols": ncols, "columns": cols, "last": None,
          "lead": bool(table_row_labels(p)), "s": p.s, "t": p.t, "weights": p.weights, "values": p.values,
          "coins": p.coins}
    if p.rule == "truth_table":
        st["truth"], st["vars"] = truth_fn(p.expr)
    return st


def _in_table(st: dict, *cells) -> str | None:
    for cell in cells:
        if len(cell) != 2:
            return "a cell is [row, col]"
        r, c = cell
        if not (0 <= r < st["nrows"] and 0 <= c < st["ncols"]):
            return f"cell [{r}, {c}] is outside the table ({st['nrows']} rows, {st['ncols']} columns, from 0)"
    return None


def _check_fill(st: dict, a: TableCellArgs) -> str | None:
    if problem := _in_table(st, (a.row, a.col)):
        return problem
    if st["rule"] is not None:
        return f"this table's cells are computed: call fill_next (its rule is {st['rule']})"
    if problem := _cell_fits(st, a.value):
        return problem
    st["last"] = st["cells"][a.row][a.col]
    st["cells"][a.row][a.col] = _fmt(a.value)
    return None


def _check_fill_next(st: dict, a) -> str | None:
    if st["rule"] is None:
        return "fill_next fills a table built from a rule; write this table's cells with fill"
    ev = table_next(st)
    if ev is None:
        return "the table is full"
    r, c = ev["cell"]
    st["cells"][r][c] = ev["value"]
    st["last"] = ev
    return None


def _check_fill_row(st: dict, a) -> str | None:
    if st["rule"] is None:
        return "fill_row fills a table built from a rule; write this table's cells with fill"
    first = table_next(st)
    if first is None:
        return "the table is full"
    events = []
    while (ev := table_next(st)) is not None and ev["cell"][0] == first["cell"][0]:
        r, c = ev["cell"]
        st["cells"][r][c] = ev["value"]
        events.append(ev)
    st["last"] = events
    return None


def _cell_words(st: dict, r: int, c: int) -> str:
    cols = st["columns"]
    col = (f'"{cols[c]}"' if not cols[c].isdigit() else cols[c]) if cols else str(c)
    return f"row {r}, column {col}"


def _said_fill_next(st: dict, a) -> str:
    ev = st["last"]
    r, c = ev["cell"]
    if "why" in ev:
        return f"{_cell_words(st, r, c)} is filled with {ev['value']}: {ev['why']}" + (
            ", arrows from the cells it uses" if ev["from"] else "")
    if not ev["from"]:
        return f"{_cell_words(st, r, c)} is filled with {ev['value']}, a starting value"
    if st["rule"] == "truth_table":
        ins = ", ".join(f"{st['vars'][j]} = {st['cells'][r][j]}" for j in range(len(st["vars"])))
        return f"for {ins}, the result {ev['value']} is filled in"
    parts = " + ".join(st["cells"][x][y] for x, y in ev["from"])
    return (f"{_cell_words(st, r, c)} is filled with {ev['value']} = {parts}, arrows from the "
            f"cell{'s' if len(ev['from']) > 1 else ''} it adds")


def _said_fill_row(st: dict, a) -> str:
    events = st["last"]
    r = events[0]["cell"][0]
    if st["rule"] == "truth_table":
        ins = ", ".join(f"{st['vars'][j]} = {st['cells'][r][j]}" for j in range(len(st["vars"])))
        return f"for {ins}, the result {events[0]['value']} is filled in"
    return f"row {r} is filled in: " + ", ".join(ev["value"] for ev in events)


def _describe_table(p: TableParams) -> str:
    nrows, ncols, cells, cols = table_shape(p)
    kind = {"pascal": "Pascal's triangle to fill", "grid_paths": "a grid of path counts to fill",
            "fibonacci": "a row of Fibonacci numbers to fill",
            "truth_table": f"a truth table for {p.expr}",
            "lcs": f"a DP table for the longest common subsequence of {p.s} and {p.t}",
            "edit_distance": f"a DP table for the edit distance from {p.s} to {p.t}",
            "knapsack": "a knapsack DP table (items "
                        + ", ".join(f"{k} of weight {w} and value {v}" for k, (w, v) in
                                    enumerate(zip(p.weights or [], p.values or []), 1))
                        + f"; capacities 0 to {p.capacity})",
            "coin_change": f"a DP row of the fewest coins ({', '.join(map(str, p.coins or []))}) for each amount"
            }.get(p.rule or "", "a table")
    out = f"{kind}, {nrows} row{'s' if nrows != 1 else ''} by {ncols} column{'s' if ncols != 1 else ''}"
    if cols:
        out += " headed " + ", ".join(cols)
    filled = [", ".join(v or "_" for v in row) for row in cells] if p.rule is None else []
    if filled:
        out += "; rows " + "; ".join(filled)
    return out + (f', titled "{p.title}"' if p.title else "")


TABLE = TemplateSpec(
    name="Table",
    family="dp_table",
    purpose="A grid of cells: a table of values, a variable trace, a DP table, a truth table, Pascal's triangle. "
            "Cells are filled by you (fill), or, for a table built from a rule, computed in order by code "
            "(fill_next: one cell, with arrows from the cells it came from; fill_row: the rest of the row). "
            "Highlight cells, rows or columns; draw arrows from the cells a value depends on. Needs at least half "
            "the frame.",
    params=TableParams,
    min_rows=3,
    init_state=_table_state,
    noun="table",
    describe=_describe_table,
    actions={
        "fill": ActionSpec("Write a value in a cell (row and col count from 0).", TableCellArgs, _check_fill,
                           lambda s, a: f"{_cell_words(s, a.row, a.col)} is filled with {_fmt(a.value)}",
                           reveals=True),
        "fill_next": ActionSpec("Fill the next cell of a rule's table (computed), with arrows from the cells it "
                                "came from.", NoArgs, _check_fill_next, _said_fill_next, reveals=True),
        "fill_row": ActionSpec("Fill the rest of the current row (computed).", NoArgs, _check_fill_row,
                               _said_fill_row, reveals=True),
        "highlight": ActionSpec("Colour these cells.", CellsArgs, lambda s, a: _in_table(s, *a.cells),
                                lambda s, a: ("the cells " if len(a.cells) > 1 else "the cell ")
                                + "; ".join(_cell_words(s, r, c) for r, c in a.cells)
                                + f" turn{'' if len(a.cells) > 1 else 's'} {a.colour.lower()}"),
        "highlight_row": ActionSpec("Colour a whole row.", RowArgs, lambda s, a: _in_table(s, (a.row, 0)),
                                    lambda s, a: f"row {a.row} turns {a.colour.lower()}"),
        "highlight_col": ActionSpec("Colour a whole column.", ColArgs, lambda s, a: _in_table(s, (0, a.col)),
                                    lambda s, a: f"column {_cell_words(s, 0, a.col).split(', column ')[1]} turns "
                                                 f"{a.colour.lower()}"),
        "depends": ActionSpec("Arrows from the cells a value is worked out from to that cell.", DependsArgs,
                              lambda s, a: _in_table(s, a.cell, *a.on),
                              lambda s, a: "arrows run from " + "; ".join(_cell_words(s, r, c) for r, c in a.on)
                              + f" to {_cell_words(s, *a.cell)}"),
        "ghost": ActionSpec("A wrong idea: a wrong value in an empty cell, in a red dashed box, noted in red.",
                            TableGhostArgs,
                            lambda s, a: _in_table(s, (a.row, a.col)) or (
                                f"the cell holds {s['cells'][a.row][a.col]}; a wrong idea goes in an empty cell"
                                if s["cells"][a.row][a.col] else None),
                            lambda s, a: f"a wrong idea: {_fmt(a.value)} in a red dashed box at "
                                         f'{_cell_words(s, a.row, a.col)}, noted "{a.text}"'),
        "note": ActionSpec("A short line of text above the table.", NoteArgs,
                           says=lambda s, a: f'note above the table: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, arrows, the ghost and the note (values stay).",
                            says=lambda s, a: "the table's highlights, arrows, ghost and note clear"),
    },
    example=[
        ['t = Table(rule="grid_paths", size=[3, 4], title="paths to each cell")'],
        ["t.fill_row()"],
        ["t.fill_next()"],
        ['t.ghost(row=1, col=1, value=1, text="still one way?")'],
        ["t.clear()", "t.fill_next()"],
        ["t.fill_row()"],
        ["t.fill_row()", 't.highlight(cells=[[2, 3]], colour="GOLD")'],
    ],
)


# ==========================================================================
# Data structures (plan/one-shot-storyboard-plan.md, "Data structure templates")
# ==========================================================================
# Each structure's operations are computed here, shared by the checker and the drawing, so the picture is always
# what the operation does (the course test's hand-run algorithms lost track). Each shows the current operation,
# named pointers as code names them, and its invariant, and marks its result as a reveal so a predict line can ask
# first (algorithm-visualisation studies: what the learner does with a picture, here predicting, matters more than
# what it shows).

# ---- LinkedList -----------------------------------------------------------------------------------------------

MAX_LL_NODES = 5


class LinkedListParams(_Args):
    values: list[Value] = Field(description="the nodes' values from head to tail, 1-5 of them, short (1-2 "
                                            "characters)")
    doubly: bool = Field(False, description="each node also links back to the one before it")
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    @model_validator(mode="after")
    def _fits(self) -> LinkedListParams:
        if not 1 <= len(self.values) <= MAX_LL_NODES:
            raise ValueError(f"{len(self.values)} nodes; use 1-{MAX_LL_NODES} (a longer list doesn't fit the screen)")
        long = [v for v in self.values if est_width(_fmt(v)) > 0.42]
        if long:
            raise ValueError(f"value {_fmt(long[0])!r} is too wide for a node: 1-2 characters")
        return self


def ll_new(values: list, doubly: bool) -> dict:
    ids = list(range(len(values)))
    nxt = {i: (i + 1 if i + 1 < len(ids) else None) for i in ids}
    return {"vals": {i: v for i, v in zip(ids, values)}, "nxt": nxt, "head": 0 if ids else None,
            "doubly": doubly, "ptrs": {}, "rev": None, "find": None, "next_id": len(ids), "last": None,
            "slots": list(ids)}  # the nodes left to right as drawn: list order, until a reversal flips links


def ll_order(st: dict) -> list[int]:
    """The node ids from head along the next links (stopping at a cycle)."""
    out, seen, c = [], set(), st["head"]
    while c is not None and c not in seen:
        out.append(c)
        seen.add(c)
        c = st["nxt"][c]
    return out


def _ll_words(st: dict) -> str:
    order = ll_order(st)
    return " -> ".join(_fmt(st["vals"][i]) for i in order) + " -> null" if order else "empty: head is null"


def _ll_at(st: dict, index: int) -> int | None:
    """The node at a place counted from the left as drawn."""
    return st["slots"][index] if 0 <= index < len(st["slots"]) else None


def ll_insert(st: dict, index: int, value) -> str | None:
    order = ll_order(st)
    if not 0 <= index <= len(order):
        return f"position {index} is outside 0-{len(order)} (0 puts it at the head)"
    if len(st["vals"]) >= MAX_LL_NODES + 1:
        return f"at most {MAX_LL_NODES + 1} nodes fit"
    if st["rev"] is not None and not st["rev"]["done"]:
        return "finish the reversal first"
    new = st["next_id"]
    st["next_id"] += 1
    st["vals"][new] = value
    if index == 0:
        st["nxt"][new], st["head"] = st["head"], new
    else:
        before = order[index - 1]
        st["nxt"][new], st["nxt"][before] = st["nxt"][before], new
    st["last"] = {"op": "insert", "id": new, "index": index}
    st["slots"], st["rev"] = ll_order(st), None
    return None


def ll_delete(st: dict, index: int) -> str | None:
    order = ll_order(st)
    if not 0 <= index < len(order):
        return f"there is no node at position {index} (positions 0-{len(order) - 1})"
    if st["rev"] is not None and not st["rev"]["done"]:
        return "finish the reversal first"
    gone = order[index]
    if index == 0:
        st["head"] = st["nxt"][gone]
    else:
        st["nxt"][order[index - 1]] = st["nxt"][gone]
    st["last"] = {"op": "delete", "id": gone, "value": st["vals"][gone], "index": index}
    del st["vals"][gone], st["nxt"][gone]
    st["ptrs"] = {n: (None if t == gone else t) for n, t in st["ptrs"].items()}
    st["slots"], st["rev"] = ll_order(st), None
    return None


def ll_reverse_step(st: dict) -> str | None:
    """One step of the in-place reversal: curr's next link flips to prev, then prev and curr move on."""
    r = st["rev"]
    if r is None or r["done"]:
        r = st["rev"] = {"prev": None, "curr": st["head"], "done": False, "flipped": []}
    c = r["curr"]
    if c is None:
        return "the list is empty"
    after = st["nxt"][c]
    st["nxt"][c] = r["prev"]
    r["flipped"].append(c)
    r["prev"], r["curr"] = c, after
    if after is None:
        st["head"], r["done"] = c, True
    st["ptrs"]["prev"], st["ptrs"]["curr"] = r["prev"], r["curr"]
    st["last"] = {"op": "reverse", "id": c, "to": st["nxt"][c], "done": r["done"]}
    return None


class LLPointArgs(_Args):
    name: str = Field(description='a pointer as the code names it, e.g. "curr", "prev", "slow" (at most 5 '
                                  "characters)")
    index: int | None = Field(description="the node's place from the left as drawn (0 = the leftmost); None: "
                                          "null")

    _name = field_validator("name")(_short(5))


class LLNameArgs(_Args):
    name: str


class LLInsertArgs(_Args):
    index: int = Field(description="the new node's position (0 = the new head)")
    value: Value


class LLIndexArgs(_Args):
    index: int


class LLFindArgs(_Args):
    value: Value


class LLHighlightArgs(_Args):
    indices: list[int]
    colour: Colour = "YELLOW"


class LLGhostArgs(_Args):
    from_index: int = Field(description="the node a wrong link starts at")
    to_index: int | None = Field(description="where it points (None: null)")
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _check_ll_point(st: dict, a: LLPointArgs) -> str | None:
    if a.index is None:
        st["ptrs"][a.name] = None
        return None
    target = _ll_at(st, a.index)
    if target is None:
        return f"there is no node at position {a.index}"
    st["ptrs"][a.name] = target
    return None


def _check_ll_advance(st: dict, a: LLNameArgs) -> str | None:
    if a.name not in st["ptrs"]:
        return f'there is no pointer "{a.name}": point it first'
    at = st["ptrs"][a.name]
    if at is None:
        return f'"{a.name}" is null: it can\'t move on'
    st["last"] = {"op": "advance", "from": at, "to": st["nxt"][at]}
    st["ptrs"][a.name] = st["nxt"][at]
    return None


def _check_ll_find(st: dict, a: LLFindArgs) -> str | None:
    f = st["find"]
    if f is None or f["value"] != a.value or f["done"]:
        f = st["find"] = {"value": a.value, "at": None, "done": False, "checks": 0}
    nxt = st["head"] if f["at"] is None else st["nxt"][f["at"]]
    if nxt is None:
        f["done"], f["hit"] = True, False
        st["last"] = {"op": "find", "id": None, "hit": False, "checks": f["checks"]}
        return None
    f["at"] = nxt
    f["checks"] += 1
    hit = st["vals"][nxt] == a.value
    f["done"], f["hit"] = hit, hit
    st["ptrs"]["curr"] = nxt
    st["last"] = {"op": "find", "id": nxt, "hit": hit, "checks": f["checks"]}
    return None


def _said_ll_find(st: dict, a: LLFindArgs) -> str:
    ev = st["last"]
    if ev["id"] is None:
        return f"\"curr\" reaches null after {ev['checks']} checks: {_fmt(a.value)} isn't in the list"
    v = _fmt(st["vals"][ev["id"]])
    return (f"\"curr\" moves to the node holding {v} (check {ev['checks']}): "
            + (f"it matches {_fmt(a.value)} and turns green" if ev["hit"] else f"{v} isn't {_fmt(a.value)}"))


def _said_ll_reverse(st: dict, a) -> str:
    ev, v = st["last"], st["vals"]
    to = "null" if ev["to"] is None else _fmt(v[ev["to"]])
    out = f"the node holding {_fmt(v[ev['id']])} now points back to {to}"
    if ev["done"]:
        return out + f"; curr is null, so head moves to {_fmt(v[st['head']])}: the list reads {_ll_words(st)}"
    return out + f"; prev moves to {_fmt(v[ev['id']])}, curr to {_fmt(v[st['rev']['curr']])}"


def _ll_index_ok(st: dict, *indices) -> str | None:
    n = len(st["slots"])
    bad = [i for i in indices if i is not None and not 0 <= i < n]
    return f"there is no node at position {bad[0]} (positions 0-{n - 1})" if bad else None


def _describe_ll(p: LinkedListParams) -> str:
    kind = "a doubly linked list" if p.doubly else "a linked list"
    return f"{kind}: head -> " + " -> ".join(_fmt(v) for v in p.values) + " -> null" + (
        f', titled "{p.title}"' if p.title else "")


LINKED_LIST = TemplateSpec(
    name="LinkedList",
    family="linked_list",
    purpose="A linked list: nodes with their next links (and back links if doubly), head, null, and named "
            "pointers (curr, prev, slow, fast). Computed: insert and delete at a position (the links rewire), "
            "find (curr walks node by node, counting checks), and the in-place reversal (reverse_step: curr's "
            "link flips back to prev, one node per call). Needs at least half the frame.",
    params=LinkedListParams,
    min_rows=3,
    init_state=lambda p: ll_new(list(p.values), p.doubly),
    noun="list",
    describe=_describe_ll,
    actions={
        "point": ActionSpec("Show (or move) a named pointer at a node, or at null.", LLPointArgs, _check_ll_point,
                            lambda s, a: f'pointer "{a.name}" at '
                                         + ("null" if a.index is None else
                                            f"the node holding {_fmt(s['vals'][s['ptrs'][a.name]])}")),
        "advance": ActionSpec("A pointer follows its node's next link (computed): curr = curr.next.", LLNameArgs,
                              _check_ll_advance,
                              lambda s, a: f'"{a.name}" moves from {_fmt(s["vals"][s["last"]["from"]])} to '
                                           + ("null" if s["last"]["to"] is None
                                              else _fmt(s["vals"][s["last"]["to"]])), reveals=True),
        "insert": ActionSpec("Link a new node in at a position (computed): the node before it now points to it, "
                             "and it points to the rest.", LLInsertArgs,
                             lambda s, a: ll_insert(s, a.index, a.value),
                             lambda s, a: f"a new node {_fmt(a.value)} is linked in at position {a.index}: "
                                          + _ll_words(s), reveals=True),
        "delete": ActionSpec("Unlink the node at a position (computed): the node before it skips over it.",
                             LLIndexArgs, lambda s, a: ll_delete(s, a.index),
                             lambda s, a: f"the node holding {_fmt(s['last']['value'])} is unlinked: "
                                          + _ll_words(s), reveals=True),
        "find_step": ActionSpec("Search, one node per call (computed): curr moves to the next node and compares "
                                "it with the value; green when it matches.", LLFindArgs, _check_ll_find,
                                _said_ll_find, reveals=True),
        "reverse_step": ActionSpec("In-place reversal, one node per call (computed): curr's next link flips to "
                                   "prev, then prev and curr move on; at the end head moves to the old tail.",
                                   NoArgs, lambda s, a: ll_reverse_step(s), _said_ll_reverse, reveals=True),
        "highlight": ActionSpec("Colour the nodes at these positions.", LLHighlightArgs,
                                lambda s, a: _ll_index_ok(s, *a.indices),
                                lambda s, a: "the node" + ("s" if len(a.indices) > 1 else "") + " holding "
                                             + ", ".join(_fmt(s["vals"][s["slots"][i]]) for i in a.indices)
                                             + f" turn{'' if len(a.indices) > 1 else 's'} {a.colour.lower()}"),
        "ghost": ActionSpec("A wrong idea: a red dashed link from one node to another (or null), noted in red.",
                            LLGhostArgs, lambda s, a: _ll_index_ok(s, a.from_index, a.to_index),
                            lambda s, a: f"a wrong idea: a red dashed link from "
                                         f"{_fmt(s['vals'][s['slots'][a.from_index]])} to "
                                         + ("null" if a.to_index is None else
                                            _fmt(s["vals"][s["slots"][a.to_index]])) + f', noted "{a.text}"'),
        "note": ActionSpec("A short line of text above the list.", NoteArgs,
                           says=lambda s, a: f'note above the list: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, the ghost and the note (pointers stay).",
                            says=lambda s, a: "the list's highlights, ghost and note clear"),
    },
    example=[
        ['lst = LinkedList(values=[3, 8, 5, 1], title="reverse in place")'],
        ['lst.point(name="curr", index=0)'],
        ["lst.reverse_step()"],
        ["lst.reverse_step()"],
        ['lst.ghost(from_index=2, to_index=None, text="lose the rest?")'],
        ["lst.clear()", "lst.reverse_step()"],
        ["lst.reverse_step()"],
    ],
)


# ---- StackQueue -----------------------------------------------------------------------------------------------

MAX_SQ = 7


class StackQueueParams(_Args):
    kind: Literal["stack", "queue", "deque", "call_stack"] = Field(
        description='"stack" (push and pop at the top), "queue" (enqueue at the rear, dequeue at the front), '
                    '"deque" (both ends), "call_stack" (frames of running calls, e.g. "fact(3)")')
    values: list[Value] = Field(default_factory=list,
                                description="what it holds at the start: bottom to top for a stack, front to rear "
                                            "for a queue (0-7 items)")
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    @model_validator(mode="after")
    def _fits(self) -> StackQueueParams:
        if len(self.values) > MAX_SQ:
            raise ValueError(f"at most {MAX_SQ} items")
        limit = 12 if self.kind == "call_stack" else 3
        long = [v for v in self.values if len(_fmt(v)) > limit]
        if long:
            raise ValueError(f"{_fmt(long[0])!r} is too long: at most {limit} characters")
        return self


class SQValueArgs(_Args):
    value: Value = Field(description="what goes in (a frame such as \"fact(2)\" for a call stack)")


class SQPopArgs(_Args):
    returns: Value | None = Field(None, description='call stack only: what the call returns, e.g. 2')


class SQHighlightArgs(_Args):
    positions: list[int] = Field(description="0 = the bottom of a stack, the front of a queue")
    colour: Colour = "YELLOW"


class SQGhostArgs(_Args):
    end: Literal["top", "bottom", "front", "rear"] = Field(description="the end the wrong idea uses")
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


_SQ_ACTIONS = {"stack": {"push", "pop", "peek"}, "call_stack": {"push", "pop", "peek"},
               "queue": {"enqueue", "dequeue", "peek"},
               "deque": {"push_front", "push_back", "pop_front", "pop_back", "peek"}}


def _sq_state(p: StackQueueParams) -> dict:
    return {"kind": p.kind, "items": list(p.values), "last": None}


def _sq_op(op: str):
    def check(st: dict, a) -> str | None:
        kind, items = st["kind"], st["items"]
        if op not in _SQ_ACTIONS[kind]:
            return f"a {kind.replace('_', ' ')} has no {op}; it has {', '.join(sorted(_SQ_ACTIONS[kind]))}"
        if op in ("push", "enqueue", "push_back", "push_front"):
            if len(items) >= MAX_SQ:
                return f"at most {MAX_SQ} items fit"
            limit = 12 if kind == "call_stack" else 3
            if len(_fmt(a.value)) > limit:
                return f"{_fmt(a.value)!r} is too long: at most {limit} characters"
            if op == "push_front":
                items.insert(0, a.value)
            else:
                items.append(a.value)
            st["last"] = a.value
            return None
        if not items:
            return f"the {kind.replace('_', ' ')} is empty: nothing to {op.replace('_', ' ')}"
        if op == "peek":
            st["last"] = items[0] if kind == "queue" else items[-1]
            return None
        st["last"] = items.pop(0) if op in ("dequeue", "pop_front") else items.pop()
        return None
    return check


def _sq_words(st: dict) -> str:
    items = ", ".join(_fmt(v) for v in st["items"])
    if not st["items"]:
        return "it is empty"
    return {"stack": f"bottom to top: {items}", "call_stack": f"bottom to top: {items}",
            "queue": f"front to rear: {items}", "deque": f"front to back: {items}"}[st["kind"]]


def _said_sq(op: str):
    def says(st: dict, a) -> str:
        v = _fmt(st["last"])
        kind = st["kind"]
        if op == "push":
            what = f"the call {v} starts: a new frame on top" if kind == "call_stack" else f"{v} is pushed on top"
        elif op == "pop":
            if kind == "call_stack":
                what = f"the call {v} returns" + (f" {_fmt(a.returns)} to the frame below" if a.returns is not None
                                                  else "") + " and its frame comes off"
            else:
                what = f"pop takes {v} off the top"
        elif op == "enqueue":
            what = f"{v} joins the rear"
        elif op == "dequeue":
            what = f"dequeue takes {v} from the front"
        elif op == "peek":
            what = f"peek shows {v} without removing it"
        else:
            what = {"push_front": f"{v} goes on the front", "push_back": f"{v} goes on the back",
                    "pop_front": f"{v} comes off the front", "pop_back": f"{v} comes off the back"}[op]
        return f"{what}; {_sq_words(st)}"
    return says


def _sq_positions(st: dict, positions) -> str | None:
    bad = [i for i in positions if not 0 <= i < len(st["items"])]
    return f"there is no item at position {bad[0]}" if bad else None


STACK_QUEUE = TemplateSpec(
    name="StackQueue",
    family="stack_queue",
    purpose='A stack (a column: push and pop at the top), a queue (a row: enqueue at the rear, dequeue at the '
            'front), a deque (a row, both ends), or a call stack (frames of running calls, each popped with what it '
            'returns: recursion). Computed: what each operation takes out, and "empty" when there is nothing. '
            "Needs at least half the frame.",
    params=StackQueueParams,
    min_rows=3,
    init_state=_sq_state,
    noun="stack",
    describe=lambda p: (f"an empty {p.kind.replace('_', ' ')}" if not p.values else
                        f"a {p.kind.replace('_', ' ')}, " + _sq_words({"kind": p.kind, "items": list(p.values)}))
    + (f', titled "{p.title}"' if p.title else ""),
    actions={
        "push": ActionSpec("Stack or call stack: put a value (a frame) on top.", SQValueArgs, _sq_op("push"),
                           _said_sq("push"), reveals=True),
        "pop": ActionSpec("Stack or call stack: take the top off (a call stack's frame returns `returns`).",
                          SQPopArgs, _sq_op("pop"), _said_sq("pop"), reveals=True),
        "enqueue": ActionSpec("Queue: add at the rear.", SQValueArgs, _sq_op("enqueue"), _said_sq("enqueue"),
                              reveals=True),
        "dequeue": ActionSpec("Queue: take from the front.", NoArgs, _sq_op("dequeue"), _said_sq("dequeue"),
                              reveals=True),
        "push_front": ActionSpec("Deque: add at the front.", SQValueArgs, _sq_op("push_front"),
                                 _said_sq("push_front"), reveals=True),
        "push_back": ActionSpec("Deque: add at the back.", SQValueArgs, _sq_op("push_back"), _said_sq("push_back"),
                                reveals=True),
        "pop_front": ActionSpec("Deque: take from the front.", NoArgs, _sq_op("pop_front"), _said_sq("pop_front"),
                                reveals=True),
        "pop_back": ActionSpec("Deque: take from the back.", NoArgs, _sq_op("pop_back"), _said_sq("pop_back"),
                               reveals=True),
        "peek": ActionSpec("Light up the item the next pop or dequeue would take, without taking it.", NoArgs,
                           _sq_op("peek"), _said_sq("peek"), reveals=True),
        "highlight": ActionSpec("Colour the items at these positions (0 = bottom or front).", SQHighlightArgs,
                                lambda s, a: _sq_positions(s, a.positions),
                                lambda s, a: ", ".join(_fmt(s["items"][i]) for i in a.positions)
                                             + f" turn{'s' if len(a.positions) == 1 else ''} {a.colour.lower()}"),
        "ghost": ActionSpec("A wrong idea: a red dashed arrow at the wrong end, noted in red.", SQGhostArgs,
                            says=lambda s, a: f'a wrong idea: a red dashed arrow at the {a.end}, noted "{a.text}"'),
        "note": ActionSpec("A short line of text above it.", NoteArgs,
                           says=lambda s, a: f'note above it: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, the ghost and the note.",
                            says=lambda s, a: "the highlights, ghost and note clear"),
    },
    example=[
        ['st = StackQueue(kind="call_stack", values=["fact(3)"], title="fact(3) runs")'],
        ['st.push(value="fact(2)")'],
        ['st.push(value="fact(1)")'],
        ['st.ghost(end="bottom", text="fact(3) returns first?")'],
        ["st.clear()", "st.pop(returns=1)"],
        ["st.pop(returns=2)"],
        ["st.pop(returns=6)"],
    ],
)


# ---- HashTable ------------------------------------------------------------------------------------------------

MAX_BUCKETS = 8
MAX_CHAIN = 4


class HashTableParams(_Args):
    size: int = Field(description="the number of buckets m, 3-8; a key k goes to bucket k mod m")
    mode: Literal["chaining", "probing"] = Field(
        "chaining", description='"chaining": colliding keys form a chain in their bucket; "probing": linear '
                                "probing, a collision tries the next bucket")
    keys: list[int] = Field(default_factory=list, description="whole-number keys already in it (0-99), inserted "
                                                              "in this order")
    a: int = Field(1, description="the hash is h(k) = (a k + b) mod m: a = 1, b = 0 is k mod m; a = 0 sends every "
                                  "key to bucket b (a bad hash: one long chain)")
    b: int = 0
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    @model_validator(mode="after")
    def _fits(self) -> HashTableParams:
        if not 3 <= self.size <= MAX_BUCKETS:
            raise ValueError(f"size {self.size}; use 3-{MAX_BUCKETS} buckets")
        if any(not 0 <= k <= 99 for k in self.keys):
            raise ValueError("keys are whole numbers 0-99")
        if not (0 <= self.a <= 99 and 0 <= self.b <= 99):
            raise ValueError("a and b are whole numbers 0-99")
        st = ht_new(self.size, self.mode, self.a, self.b)
        for k in self.keys:
            if problem := ht_insert(st, k):
                raise ValueError(problem)
        return self


def ht_new(size: int, mode: str, a: int = 1, b: int = 0) -> dict:
    return {"m": size, "mode": mode, "buckets": [[] for _ in range(size)] if mode == "chaining" else [None] * size,
            "last": None, "a": a, "b": b}


def ht_hash(st: dict, key: int) -> int:
    return (st.get("a", 1) * key + st.get("b", 0)) % st["m"]


def ht_formula(st: dict, key: int | None = None) -> str:
    """The hash as written: "k mod 7", "(3k + 1) mod 7", "0 mod 7"; with a key, its working."""
    a, b, m = st.get("a", 1), st.get("b", 0), st["m"]
    inner = ("k" if a == 1 else f"{a}k" if a else "") + (f" + {b}" if b and a else str(b) if not a else "")
    form = (f"({inner})" if a and b else inner or "0") + f" mod {m}"
    if key is None:
        return f"h(k) = {form}"
    filled = ((str(key) if a == 1 else f"{a}*{key}" if a else "") + (f" + {b}" if b and a else str(b) if not a else
                                                                    ""))
    filled = (f"({filled})" if a and b else filled or "0") + f" mod {m}"
    return f"h({key}) = {filled} = {ht_hash(st, key)}"


def ht_insert(st: dict, key: int) -> str | None:
    m, h = st["m"], ht_hash(st, key)
    if st["mode"] == "chaining":
        if key in st["buckets"][h]:
            return f"{key} is already in bucket {h}"
        if len(st["buckets"][h]) >= MAX_CHAIN:
            return f"bucket {h}'s chain is full on screen ({MAX_CHAIN} keys)"
        st["buckets"][h].append(key)
        st["last"] = {"op": "insert", "key": key, "h": h, "probes": [h], "at": h,
                      "chain": list(st["buckets"][h])}
        return None
    probes = []
    for k in range(m):
        b = (h + k) % m
        probes.append(b)
        if st["buckets"][b] == key:
            return f"{key} is already in bucket {b}"
        if st["buckets"][b] is None:
            st["buckets"][b] = key
            st["last"] = {"op": "insert", "key": key, "h": h, "probes": probes, "at": b}
            return None
    return "the table is full"


def ht_find(st: dict, key: int) -> dict:
    m, h = st["m"], ht_hash(st, key)
    if st["mode"] == "chaining":
        chain = st["buckets"][h]
        return {"op": "find", "key": key, "h": h, "probes": [h], "at": h if key in chain else None,
                "checks": (chain.index(key) + 1) if key in chain else len(chain)}
    probes = []
    for k in range(m):
        b = (h + k) % m
        probes.append(b)
        if st["buckets"][b] == key:
            return {"op": "find", "key": key, "h": h, "probes": probes, "at": b, "checks": len(probes)}
        if st["buckets"][b] is None:
            break
    return {"op": "find", "key": key, "h": h, "probes": probes, "at": None, "checks": len(probes)}


class HTKeyArgs(_Args):
    key: int = Field(description="a whole number 0-99")


class HTBucketsArgs(_Args):
    buckets: list[int]
    colour: Colour = "YELLOW"


class HTGhostArgs(_Args):
    key: int
    bucket: int = Field(description="the wrong bucket")
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _check_ht_insert(st: dict, a: HTKeyArgs) -> str | None:
    if not 0 <= a.key <= 99:
        return "keys are whole numbers 0-99"
    return ht_insert(st, a.key)


def _check_ht_find(st: dict, a: HTKeyArgs) -> str | None:
    st["last"] = ht_find(st, a.key)
    return None


def _check_ht_delete(st: dict, a: HTKeyArgs) -> str | None:
    if st["mode"] != "chaining":
        return "delete is for chaining (deleting under probing needs a tombstone, which this table doesn't draw)"
    h = ht_hash(st, a.key)
    if a.key not in st["buckets"][h]:
        return f"{a.key} isn't in the table (bucket {h} holds {st['buckets'][h] or 'nothing'})"
    st["buckets"][h].remove(a.key)
    st["last"] = {"op": "delete", "key": a.key, "h": h}
    return None


def _said_ht(st: dict, a) -> str:
    ev = st["last"]
    head = "the hash " + ht_formula(st, ev["key"])
    if ev["op"] == "insert":
        if st["mode"] == "chaining":
            others = [k for k in ev["chain"] if k != ev["key"]]
            return head + (f"; bucket {ev['h']} already holds {', '.join(map(str, others))}, so {ev['key']} joins "
                           "its chain" if others else f"; {ev['key']} goes in bucket {ev['h']}")
        taken = ev["probes"][:-1]
        return head + (f"; bucket{'s' if len(taken) > 1 else ''} {', '.join(map(str, taken))} "
                       f"{'are' if len(taken) > 1 else 'is'} taken, so {ev['key']} goes in bucket {ev['at']}"
                       if taken else f"; {ev['key']} goes in bucket {ev['h']}")
    if ev["op"] == "find":
        if ev["at"] is None:
            return head + f"; not there, after {ev['checks']} check{'s' if ev['checks'] != 1 else ''}"
        return head + f"; found in bucket {ev['at']} after {ev['checks']} check{'s' if ev['checks'] != 1 else ''}"
    return head + f"; {ev['key']} is taken out of bucket {ev['h']}'s chain"


def _ht_load(st: dict) -> float:
    n = sum(len(b) for b in st["buckets"]) if st["mode"] == "chaining" else sum(b is not None for b in st["buckets"])
    return n / st["m"]


def _describe_ht(p: HashTableParams) -> str:
    st = ht_new(p.size, p.mode, p.a, p.b)
    for k in p.keys:
        ht_insert(st, k)
    filled = [f"bucket {i}: {', '.join(map(str, b)) if isinstance(b, list) else b}"
              for i, b in enumerate(st["buckets"]) if b not in (None, [])]
    return (f"a hash table of {p.size} buckets ({'chaining' if p.mode == 'chaining' else 'linear probing'}, "
            f"{ht_formula(st)})" + (": " + "; ".join(filled) if filled else ", empty")
            + (f', titled "{p.title}"' if p.title else ""))


HASH_TABLE = TemplateSpec(
    name="HashTable",
    family="hash_table",
    purpose="A hash table: m buckets, h(k) = (a k + b) mod m (k mod m by default; a = 0 is a bad hash sending "
            "every key to one bucket), with chaining (colliding keys form a chain) or linear "
            "probing (a collision tries the next bucket). Computed: where each key goes and why (its hash, the "
            "buckets probed), find with its number of checks, delete (chaining), and the load factor n / m. Needs "
            "at least two thirds of the frame.",
    params=HashTableParams,
    min_rows=4,
    init_state=lambda p: _ht_init(p),
    noun="table",
    describe=_describe_ht,
    actions={
        "insert": ActionSpec("Put a key in (computed): its hash picks the bucket; a collision chains or probes.",
                             HTKeyArgs, _check_ht_insert, _said_ht, reveals=True),
        "find": ActionSpec("Look a key up (computed): its bucket, then the chain or the probes, counting checks.",
                           HTKeyArgs, _check_ht_find, _said_ht, reveals=True),
        "delete": ActionSpec("Take a key out of its chain (chaining only).", HTKeyArgs, _check_ht_delete, _said_ht,
                             reveals=True),
        "load": ActionSpec("Note the load factor n / m (computed).",
                           says=lambda s, a: f"the load factor, {_num(_ht_load(s))} keys per bucket, is noted",
                           reveals=True),
        "highlight": ActionSpec("Colour these buckets.", HTBucketsArgs,
                                lambda s, a: next((f"there is no bucket {b} (0-{s['m'] - 1})" for b in a.buckets
                                                   if not 0 <= b < s["m"]), None),
                                lambda s, a: f"bucket{'s' if len(a.buckets) > 1 else ''} "
                                             f"{', '.join(map(str, a.buckets))} turn{'' if len(a.buckets) > 1 else 's'}"
                                             f" {a.colour.lower()}"),
        "ghost": ActionSpec("A wrong idea: a key in a red dashed box at the wrong bucket, noted in red.",
                            HTGhostArgs,
                            lambda s, a: None if 0 <= a.bucket < s["m"] else f"there is no bucket {a.bucket}",
                            lambda s, a: f"a wrong idea: {a.key} in a red dashed box at bucket {a.bucket}, noted "
                                         f'"{a.text}"'),
        "note": ActionSpec("A short line of text above the table.", NoteArgs,
                           says=lambda s, a: f'note above the table: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, the ghost and the note.",
                            says=lambda s, a: "the table's highlights, ghost and note clear"),
    },
    example=[
        ['ht = HashTable(size=7, keys=[10, 22], title="h(k) = k mod 7")'],
        ["ht.insert(key=31)"],
        ['ht.ghost(key=17, bucket=0, text="17 goes first free?")'],
        ["ht.clear()", "ht.insert(key=17)"],
        ["ht.find(key=24)"],
        ["ht.load()"],
    ],
)


def _ht_init(p: HashTableParams) -> dict:
    st = ht_new(p.size, p.mode, p.a, p.b)
    for k in p.keys:
        ht_insert(st, k)
    st["last"] = None
    return st


# ---- BinaryTree: binary search trees and heaps ----------------------------------------------------------------

MAX_TREE_NODES = 12
MAX_TREE_DEPTH = 5


class BinaryTreeParams(_Args):
    kind: Literal["bst", "min_heap", "max_heap"] = Field(
        description='"bst": a binary search tree, the values inserted in order; "min_heap" / "max_heap": a binary '
                    "heap, the values its array in level order (call heapify to make it a heap)")
    values: list[int] = Field(default_factory=list, description="0-12 whole numbers, 0-99")
    show_array: bool = Field(True, description="heaps: the array the heap lives in, under the tree")
    title: str | None = Field(None, description="at most 24 characters")
    area: Area = "full"

    _title = field_validator("title")(_short(24))

    @model_validator(mode="after")
    def _fits(self) -> BinaryTreeParams:
        if len(self.values) > MAX_TREE_NODES:
            raise ValueError(f"at most {MAX_TREE_NODES} nodes")
        if any(not 0 <= v <= 99 for v in self.values):
            raise ValueError("values are whole numbers 0-99")
        if self.kind == "bst":
            if len(set(self.values)) != len(self.values):
                raise ValueError("a binary search tree holds each value once")
            st = bt_new("bst", [])
            for v in self.values:
                bst_insert(st, v)
            if bt_depth(st) > MAX_TREE_DEPTH:
                raise ValueError(f"this order makes the tree {bt_depth(st)} levels deep; at most {MAX_TREE_DEPTH} "
                                 "fit (insert a middle value first)")
        return self


def bt_new(kind: str, values: list[int]) -> dict:
    st = {"kind": kind, "nodes": {}, "root": None, "next_id": 0, "heap": [], "trav": None, "last": None, "op": None}
    if kind == "bst":
        for v in values:
            bst_insert(st, v)
    else:
        st["heap"] = list(values)
    st["last"] = None
    return st


def _new_node(st: dict, v: int) -> int:
    i = st["next_id"]
    st["next_id"] += 1
    st["nodes"][i] = {"v": v, "l": None, "r": None}
    return i


def bst_insert(st: dict, v: int) -> dict:
    """Insert into the BST; the comparisons on the way down, and where it went."""
    path = []
    if st["root"] is None:
        st["root"] = _new_node(st, v)
        return {"op": "insert", "v": v, "path": [], "parent": None, "side": None}
    c = st["root"]
    while True:
        node = st["nodes"][c]
        if v == node["v"]:
            return {"op": "insert", "v": v, "path": path, "dup": True}
        side = "l" if v < node["v"] else "r"
        path.append((node["v"], "left" if side == "l" else "right"))
        if node[side] is None:
            node[side] = _new_node(st, v)
            return {"op": "insert", "v": v, "path": path, "parent": node["v"], "side": side}
        c = node[side]


def bst_search(st: dict, v: int) -> dict:
    path, c = [], st["root"]
    while c is not None:
        node = st["nodes"][c]
        if v == node["v"]:
            return {"op": "search", "v": v, "path": path, "found": True}
        side = "l" if v < node["v"] else "r"
        path.append((node["v"], "left" if side == "l" else "right"))
        c = node[side]
    return {"op": "search", "v": v, "path": path, "found": False}


def bst_delete(st: dict, v: int) -> dict | str:
    parent, c, side = None, st["root"], None
    while c is not None and st["nodes"][c]["v"] != v:
        parent, side = c, ("l" if v < st["nodes"][c]["v"] else "r")
        c = st["nodes"][c][side]
    if c is None:
        return f"{v} isn't in the tree"
    node = st["nodes"][c]

    def relink(child):
        if parent is None:
            st["root"] = child
        else:
            st["nodes"][parent][side] = child

    if node["l"] is None or node["r"] is None:
        child = node["l"] if node["l"] is not None else node["r"]
        case = "leaf" if child is None else "one child"
        relink(child)
        del st["nodes"][c]
        return {"op": "delete", "v": v, "case": case,
                "child": None if child is None else st["nodes"][child]["v"]}
    sp, s = c, node["r"]  # two children: the in-order successor (the smallest on the right) takes its place
    while st["nodes"][s]["l"] is not None:
        sp, s = s, st["nodes"][s]["l"]
    succ = st["nodes"][s]["v"]
    if sp == c:
        st["nodes"][sp]["r"] = st["nodes"][s]["r"]
    else:
        st["nodes"][sp]["l"] = st["nodes"][s]["r"]
    del st["nodes"][s]
    node["v"] = succ
    return {"op": "delete", "v": v, "case": "two children", "succ": succ}


def bt_depth(st: dict) -> int:
    if st["kind"] != "bst":
        n = len(st["heap"])
        return n.bit_length()
    def d(i):
        return 0 if i is None else 1 + max(d(st["nodes"][i]["l"]), d(st["nodes"][i]["r"]))
    return d(st["root"])


def bt_order(st: dict, order: str) -> list[int]:
    """The values in a traversal order: inorder, preorder, postorder or level."""
    if st["kind"] != "bst":
        h = st["heap"]
        if order == "level":
            return list(h)
        def rec(i):
            if i >= len(h):
                return []
            l, r = rec(2 * i + 1), rec(2 * i + 2)
            return {"inorder": l + [h[i]] + r, "preorder": [h[i]] + l + r, "postorder": l + r + [h[i]]}[order]
        return rec(0)
    nodes = st["nodes"]
    if order == "level":
        out, q = [], [st["root"]] if st["root"] is not None else []
        while q:
            i = q.pop(0)
            out.append(nodes[i]["v"])
            q += [c for c in (nodes[i]["l"], nodes[i]["r"]) if c is not None]
        return out
    def rec(i):
        if i is None:
            return []
        n = nodes[i]
        l, r = rec(n["l"]), rec(n["r"])
        return {"inorder": l + [n["v"]] + r, "preorder": [n["v"]] + l + r, "postorder": l + r + [n["v"]]}[order]
    return rec(st["root"])


def _better(st: dict, a: int, b: int) -> bool:
    return a < b if st["kind"] == "min_heap" else a > b


def heap_push(st: dict, v: int) -> dict:
    h = st["heap"]
    h.append(v)
    i, swaps = len(h) - 1, []
    while i > 0 and _better(st, h[i], h[(i - 1) // 2]):
        p = (i - 1) // 2
        swaps.append((i, p))
        h[i], h[p] = h[p], h[i]
        i = p
    return {"op": "push", "v": v, "swaps": swaps}


def _sift_down(st: dict, i: int, swaps: list) -> None:
    h = st["heap"]
    while True:
        best = i
        for c in (2 * i + 1, 2 * i + 2):
            if c < len(h) and _better(st, h[c], h[best]):
                best = c
        if best == i:
            return
        swaps.append((i, best))
        h[i], h[best] = h[best], h[i]
        i = best


def heap_pop(st: dict) -> dict | str:
    h = st["heap"]
    if not h:
        return "the heap is empty"
    top = h[0]
    last = h.pop()
    swaps: list = []
    if h:
        h[0] = last
        _sift_down(st, 0, swaps)
    return {"op": "pop", "v": top, "last": last, "swaps": swaps}


def heap_heapify(st: dict) -> dict:
    swaps: list = []
    for i in range(len(st["heap"]) // 2 - 1, -1, -1):
        _sift_down(st, i, swaps)
    return {"op": "heapify", "swaps": swaps}


# ---- One comparison or swap per call (insert_step, search_step, push_step, pop_step, heapify_step) ----------------
# The whole operations above light up a whole path, or play every swap, in one call, so one line had to narrate
# several steps at once. A step action does one comparison (and the move or swap it decides) per call; the
# operation in progress is kept in st["op"] until its last step, and nothing else may change the tree meanwhile.

_STEP_CALL = {"insert": "insert_step(value={v})", "search": "search_step(value={v})", "push": "push_step(value={v})",
              "pop": "pop_step()", "heapify": "heapify_step()"}


def bt_pending(st: dict) -> str | None:
    """The problem with starting something else while an operation is half done, or None."""
    o = st.get("op")
    if o is None:
        return None
    of = f" of {o['v']}" if o.get("v") is not None else ""
    return f"the {o['op']}{of} is half done: finish it with {_STEP_CALL[o['op']].format(v=o.get('v'))} first"


def _heap_children(st: dict, i: int) -> list[int]:
    return [c for c in (2 * i + 1, 2 * i + 2) if c < len(st["heap"])]


def _heap_best_child(st: dict, i: int) -> int | None:
    kids = _heap_children(st, i)
    if not kids:
        return None
    best = kids[0]
    for c in kids[1:]:
        if _better(st, st["heap"][c], st["heap"][best]):
            best = c
    return best


def _bst_find_id(st: dict, v: int) -> int | None:
    return next((i for i, n in st["nodes"].items() if n["v"] == v), None)


def bt_step(st: dict, op: str, value: int | None = None) -> dict | str:
    """One step of an operation: a comparison (and the move or swap it decides), or the first move of a heap's
    push or pop. Returns the event, or a problem. st["op"] holds the operation until its last step."""
    o = st.get("op")
    if o is not None and (o["op"] != op or o.get("v") != value):
        return bt_pending(st)
    heap = st["kind"] != "bst"
    if op in ("insert", "search") and heap or op in ("push", "pop", "heapify") and not heap:
        return f"this is a {st['kind'].replace('_', ' ')}: no {op}_step"
    nodes, h = st["nodes"], st["heap"]
    if op == "insert":
        if o is None:
            if _bst_find_id(st, value) is not None:
                return f"{value} is already in the tree"
            if len(nodes) >= MAX_TREE_NODES:
                return f"at most {MAX_TREE_NODES} nodes"
            trial = copy.deepcopy(st)
            trial["op"] = None
            bst_insert(trial, value)
            if bt_depth(trial) > MAX_TREE_DEPTH:
                return f"{value} would make the tree deeper than {MAX_TREE_DEPTH} levels"
            if st["root"] is None:
                st["root"] = _new_node(st, value)
                return {"op": "insert_step", "v": value, "at": None, "new": st["root"], "parent": None, "k": 0}
            o = st["op"] = {"op": "insert", "v": value, "at": st["root"], "k": 0}
        at = o["at"]
        node = nodes[at]
        side = "l" if value < node["v"] else "r"
        o["k"] += 1
        ev = {"op": "insert_step", "v": value, "at": at, "with": node["v"], "dir": "left" if side == "l" else "right",
              "k": o["k"]}
        if node[side] is None:
            node[side] = _new_node(st, value)
            st["op"] = None
            return ev | {"new": node[side], "parent": node["v"]}
        o["at"] = node[side]
        return ev | {"new": None, "next": nodes[node[side]]["v"]}
    if op == "search":
        if o is None:
            if st["root"] is None:
                return {"op": "search_step", "v": value, "at": None, "found": False, "k": 0, "end": True}
            o = st["op"] = {"op": "search", "v": value, "at": st["root"], "k": 0}
        at = o["at"]
        node = nodes[at]
        o["k"] += 1
        ev = {"op": "search_step", "v": value, "at": at, "with": node["v"], "k": o["k"]}
        if node["v"] == value:
            st["op"] = None
            st.setdefault("found", set()).add(value)
            return ev | {"found": True, "end": True}
        side = "l" if value < node["v"] else "r"
        ev |= {"dir": "left" if side == "l" else "right", "found": False}
        if node[side] is None:
            st["op"] = None
            return ev | {"end": True}
        o["at"] = node[side]
        return ev | {"end": False, "next": nodes[node[side]]["v"]}
    if op == "push":
        if o is None:
            if len(h) >= MAX_TREE_NODES:
                return f"at most {MAX_TREE_NODES} values"
            h.append(value)
            i = len(h) - 1
            if i > 0:
                st["op"] = {"op": "push", "v": value, "i": i}
            return {"op": "push_step", "v": value, "placed": i, "parent": h[(i - 1) // 2] if i else None,
                    "end": i == 0}
        i = o["i"]
        p = (i - 1) // 2
        ev = {"op": "push_step", "v": value, "at": i, "with": h[p], "other": p}
        if _better(st, h[i], h[p]):
            h[i], h[p] = h[p], h[i]
            o["i"] = p
            if p == 0:
                st["op"] = None
            return ev | {"swapped": True, "end": p == 0}
        st["op"] = None
        return ev | {"swapped": False, "end": True}
    if op == "pop":
        if o is None:
            if not h:
                return "the heap is empty"
            top, last = h[0], h.pop()
            if h:
                h[0] = last
            more = len(h) > 1
            if more:
                st["op"] = {"op": "pop", "v": None, "i": 0}
            return {"op": "pop_step", "out": top, "last": last if h else None, "end": not more}
        i = o["i"]
        c = _heap_best_child(st, i)
        ev = {"op": "pop_step", "at": i, "v": h[i], "with": h[c], "other": c}
        if _better(st, h[c], h[i]):
            h[i], h[c] = h[c], h[i]
            o["i"] = c
            end = not _heap_children(st, c)
            if end:
                st["op"] = None
            return ev | {"swapped": True, "end": end}
        st["op"] = None
        return ev | {"swapped": False, "end": True}
    # heapify: sift each parent down from the last, one comparison per call
    if o is None:
        if len(h) < 2:
            return "there is nothing to heapify"
        p = len(h) // 2 - 1
        o = st["op"] = {"op": "heapify", "v": None, "p": p, "i": p}
    i = o["i"]
    c = _heap_best_child(st, i)
    ev = {"op": "heapify_step", "at": i, "v": h[i], "with": h[c], "other": c, "parent": o["p"]}
    swapped = _better(st, h[c], h[i])
    if swapped:
        h[i], h[c] = h[c], h[i]
        o["i"] = c
    if not swapped or not _heap_children(st, c):
        o["p"] -= 1
        o["i"] = o["p"]
    end = o["p"] < 0
    if end:
        st["op"] = None
    return ev | {"swapped": swapped, "end": end}


def _check_bt_step(op: str):
    def check(st: dict, a) -> str | None:
        ev = bt_step(st, op, getattr(a, "value", None))
        if isinstance(ev, str):
            return ev
        st["last"] = ev
        return None
    return check


def _said_bt_step(st: dict, a) -> str:
    ev, h = st["last"], st["heap"]
    sign = lambda x, y: "<" if x < y else (">" if x > y else "=")  # noqa: E731
    small = "smaller" if st["kind"] == "min_heap" else "larger"
    array = f"; the array reads {', '.join(map(str, h))}" if ev.get("end") and st["kind"] != "bst" else ""
    v = ev.get("v")
    if ev["op"] == "insert_step":
        if ev["at"] is None:
            return f"the tree is empty: {v} becomes the root"
        out = f"{v} {sign(v, ev['with'])} {ev['with']}, go {ev['dir']}"
        if ev["new"] is None:
            return out + f", to {ev['next']}"
        return out + f": {ev['with']} has no {ev['dir']} child, so {v} goes there"
    if ev["op"] == "search_step":
        if ev["at"] is None:
            return f"the tree is empty: {v} isn't in it"
        if ev["found"]:
            return f"{v} = {ev['with']}: found after {ev['k']} comparison{'s' if ev['k'] != 1 else ''}"
        out = f"{v} {sign(v, ev['with'])} {ev['with']}, go {ev['dir']}"
        if not ev["end"]:
            return out + f", to {ev['next']}"
        return out + f": {ev['with']} has no {ev['dir']} child, so {v} isn't in the tree ({ev['k']} comparisons)"
    if ev["op"] == "push_step":
        if "placed" in ev:
            if ev["parent"] is None:
                return f"{v} goes in the empty heap as its root"
            return f"{v} goes in the next free place, index {ev['placed']}, under {ev['parent']}"
        if ev["swapped"]:
            return (f"{v} is {small} than its parent {ev['with']}, so they swap"
                    + (f": {v} is the root now" if ev["end"] else "") + array)
        return f"{v} isn't {small} than its parent {ev['with']}, so it stays" + array
    if ev["op"] == "pop_step":
        if "out" in ev:
            top = "smallest" if st["kind"] == "min_heap" else "largest"
            if ev["last"] is None:
                return f"the root {ev['out']}, the {top}, comes out: the heap is empty"
            return (f"the root {ev['out']}, the {top}, comes out; the last value {ev['last']} moves to the root"
                    + array)
        if ev["swapped"]:
            return f"{v}'s {small} child is {ev['with']}, {small} than {v}, so they swap" + array
        return f"{v}'s {small} child is {ev['with']}, not {small} than {v}, so {v} stays" + array
    # heapify_step
    if ev["swapped"]:
        return f"{v}'s {small} child is {ev['with']}, {small} than {v}, so they swap" + array
    return f"{v}'s {small} child is {ev['with']}, not {small} than {v}, so {v} stays" + array


class BTValueArgs(_Args):
    value: int = Field(description="a whole number 0-99")


class BTOrderArgs(_Args):
    order: Literal["inorder", "preorder", "postorder", "level"]


class BTValuesArgs(_Args):
    values: list[int]
    colour: Colour = "YELLOW"


class BTGhostArgs(_Args):
    parent: int = Field(description="the value of the node a wrong child hangs from")
    side: Literal["left", "right"]
    value: int
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


class BTTurnArgs(_Args):
    at: int = Field(description="the node the wrong turn starts from")
    side: Literal["left", "right"]
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


class BTMarkArgs(_Args):
    values: list[int] = Field(description="the nodes the wrong idea is about (1-4)")
    text: str = Field(description="the wrong idea, at most 24 characters")

    _text = field_validator("text")(_short(24))


def _check_bt_turn(st: dict, a: BTTurnArgs) -> str | None:
    return None if a.at in _bt_values(st) else f"there is no node {a.at}"


def _check_bt_mark(st: dict, a: BTMarkArgs) -> str | None:
    if not 1 <= len(a.values) <= 4:
        return "ring 1-4 nodes"
    return next((f"there is no node {v}" for v in a.values if v not in _bt_values(st)), None)


def _bt_child(st: dict, at: int, side: str) -> int | None:
    """The value of a node's child on that side, or None."""
    if st["kind"] == "bst":
        node = next(n for n in st["nodes"].values() if n["v"] == at)
        c = node["l" if side == "left" else "r"]
        return None if c is None else st["nodes"][c]["v"]
    c = 2 * st["heap"].index(at) + (1 if side == "left" else 2)
    return st["heap"][c] if c < len(st["heap"]) else None


def _said_bt_turn(st: dict, a: BTTurnArgs) -> str:
    child = _bt_child(st, a.at, a.side)
    to = f" to {child}" if child is not None else " into the empty place"
    return f'a wrong idea: a red dashed arrow from {a.at} down its {a.side} side{to}, noted "{a.text}"'


def _bt_kind(kind: str):
    def check(st: dict, a) -> str | None:
        want = ("bst",) if kind == "bst" else ("min_heap", "max_heap")
        return None if st["kind"] in want else f"this is a {st['kind'].replace('_', ' ')}: no such action"
    return check


def _check_bt_insert(st: dict, a: BTValueArgs) -> str | None:
    if problem := _bt_kind("bst")(st, a) or bt_pending(st):
        return problem
    if len(st["nodes"]) >= MAX_TREE_NODES:
        return f"at most {MAX_TREE_NODES} nodes"
    ev = bst_insert(st, a.value)
    if ev.get("dup"):
        return f"{a.value} is already in the tree"
    if bt_depth(st) > MAX_TREE_DEPTH:
        bst_delete(st, a.value)
        return f"{a.value} would make the tree deeper than {MAX_TREE_DEPTH} levels"
    st["last"] = ev
    return None


def _check_bt_search(st: dict, a: BTValueArgs) -> str | None:
    if problem := _bt_kind("bst")(st, a) or bt_pending(st):
        return problem
    st["last"] = bst_search(st, a.value)
    if st["last"]["found"]:
        st.setdefault("found", set()).add(a.value)
    return None


def _check_bt_delete(st: dict, a: BTValueArgs) -> str | None:
    if problem := _bt_kind("bst")(st, a) or bt_pending(st):
        return problem
    ev = bst_delete(st, a.value)
    if isinstance(ev, str):
        return ev
    st["last"] = ev
    st.get("found", set()).discard(a.value)
    return None


def _path_words(path) -> str:
    return "; ".join(f"{'<' if d == 'left' else '>'} {v}, go {d}" for v, d in path)


def _said_bt(st: dict, a) -> str:
    ev = st["last"]
    if ev["op"] == "insert":
        if ev["parent"] is None:
            return f"{ev['v']} becomes the root"
        walk = "; ".join(f"{ev['v']} {'<' if d == 'left' else '>'} {v}, go {d}" for v, d in ev["path"])
        return f"{walk}; {ev['v']} becomes {ev['parent']}'s {'left' if ev['side'] == 'l' else 'right'} child"
    if ev["op"] == "search":
        walk = "; ".join(f"{ev['v']} {'<' if d == 'left' else '>'} {v}, go {d}" for v, d in ev["path"])
        end = f"{ev['v']} is found" if ev["found"] else f"the path runs out: {ev['v']} isn't in the tree"
        return (walk + "; " if walk else "") + end + f" after {len(ev['path']) + (1 if ev['found'] else 0)} comparisons"
    if ev["op"] == "delete":
        if ev["case"] == "two children":
            return (f"{ev['v']} has two children, so its in-order successor {ev['succ']} (the smallest on its "
                    f"right) takes its place")
        if ev["case"] == "one child":
            return f"{ev['v']} has one child, {ev['child']}, which takes its place"
        return f"{ev['v']} is a leaf and is simply removed"
    if ev["op"] in ("push", "pop", "heapify"):
        h = st["heap"]
        moves = ", ".join(f"{h[j]} and {h[i]}" for i, j in ev["swaps"])  # after the swaps: the pair, in order
        top = "smallest" if st["kind"] == "min_heap" else "largest"
        if ev["op"] == "push":
            out = f"{ev['v']} goes in the next free place" + (f", then rises: {len(ev['swaps'])} swap"
                                                              f"{'s' if len(ev['swaps']) != 1 else ''}"
                                                              if ev["swaps"] else ", and stays")
        elif ev["op"] == "pop":
            out = (f"the root {ev['v']}, the {top}, comes out; the last value {ev['last']} moves to the root"
                   + (f" and sinks: {len(ev['swaps'])} swap{'s' if len(ev['swaps']) != 1 else ''}" if ev["swaps"]
                      else ""))
        else:
            out = f"heapify sifts each parent down from the last: {len(ev['swaps'])} swaps"
        del moves
        return out + f"; the array reads {', '.join(map(str, h))}"
    if ev["op"] == "traverse":
        return (f"{ev['order']} visits {ev['v']}; visited so far: {', '.join(map(str, ev['seen']))}"
                + ("; done" if ev["done"] else ""))
    return ""


def _check_heap(op: str):
    def check(st: dict, a) -> str | None:
        if problem := _bt_kind("heap")(st, a) or bt_pending(st):
            return problem
        if op == "push":
            if len(st["heap"]) >= MAX_TREE_NODES:
                return f"at most {MAX_TREE_NODES} values"
            st["last"] = heap_push(st, a.value)
        elif op == "pop":
            ev = heap_pop(st)
            if isinstance(ev, str):
                return ev
            st["last"] = ev
        else:
            st["last"] = heap_heapify(st)
        return None
    return check


def _check_traverse(st: dict, a: BTOrderArgs) -> str | None:
    if problem := bt_pending(st):
        return problem
    t = st["trav"]
    if t is None or t["order"] != a.order or t["done"]:
        t = st["trav"] = {"order": a.order, "seq": bt_order(st, a.order), "k": 0, "done": False}
    if not t["seq"]:
        return "the tree is empty"
    v = t["seq"][t["k"]]
    t["k"] += 1
    t["done"] = t["k"] >= len(t["seq"])
    st["last"] = {"op": "traverse", "order": a.order, "v": v, "seen": t["seq"][:t["k"]], "done": t["done"]}
    return None


def _check_bt_ghost(st: dict, a: BTGhostArgs) -> str | None:
    if a.parent not in _bt_values(st):
        return f"there is no node {a.parent}"
    if st["kind"] == "bst":
        node = next(n for n in st["nodes"].values() if n["v"] == a.parent)
        child = node["l" if a.side == "left" else "r"]
        taken = None if child is None else st["nodes"][child]["v"]
    else:
        i = st["heap"].index(a.parent)
        c = 2 * i + (1 if a.side == "left" else 2)
        taken = st["heap"][c] if c < len(st["heap"]) else None
    if taken is not None:
        return (f"{a.parent}'s {a.side} child is {taken} already: for a wrong turn or a taken place use "
                f"ghost_turn(at={a.parent}, side=\"{a.side}\", text=...)")
    return None


def _bt_values(st: dict) -> list[int]:
    return list(st["heap"]) if st["kind"] != "bst" else [n["v"] for n in st["nodes"].values()]


def _describe_bt(p: BinaryTreeParams) -> str:
    if p.kind == "bst":
        st = bt_new("bst", list(p.values))
        out = f"a binary search tree built from {', '.join(map(str, p.values))}" if p.values else "an empty BST"
        if p.values:
            out += f" (root {p.values[0]}, {bt_depth(st)} levels)"
    else:
        out = (f"a {p.kind.replace('_', '-')} tree" + (" with its array" if p.show_array else "")
               + (f", the array {', '.join(map(str, p.values))}" if p.values else ", empty"))
    return out + (f', titled "{p.title}"' if p.title else "")


BINARY_TREE = TemplateSpec(
    name="BinaryTree",
    family="tree",
    purpose="A binary search tree or a binary heap (the tree, and under it the array it lives in). BST, "
            "computed: insert and search (each comparison on the way down lights up), delete (leaf, one child, "
            "or two children: the in-order successor takes its place). Heap, computed: push (the value rises), "
            "pop (the root comes out, the last value sinks), heapify. Each of these but delete also has a _step "
            "form, one comparison or swap per call, for a line per step. Both: traverse_step visits the next node in "
            "inorder, preorder, postorder or level order. Needs at least half the frame.",
    params=BinaryTreeParams,
    min_rows=3,
    init_state=lambda p: bt_new(p.kind, list(p.values)),
    noun="tree",
    describe=_describe_bt,
    actions={
        "insert": ActionSpec("BST: insert a value (computed): compare down from the root, left if smaller, right "
                             "if larger, until a free place.", BTValueArgs, _check_bt_insert, _said_bt,
                             reveals=True),
        "search": ActionSpec("BST: search for a value (computed), comparing down from the root.", BTValueArgs,
                             _check_bt_search, _said_bt, reveals=True),
        "delete": ActionSpec("BST: delete a value (computed, by its case).", BTValueArgs, _check_bt_delete,
                             _said_bt, reveals=True),
        "push": ActionSpec("Heap: add a value (computed): it goes in the next free place and rises past larger "
                           "parents (smaller, in a max-heap).", BTValueArgs, _check_heap("push"), _said_bt,
                           reveals=True),
        "pop": ActionSpec("Heap: take the root out (computed): the last value moves up and sinks.", NoArgs,
                          _check_heap("pop"), _said_bt, reveals=True),
        "heapify": ActionSpec("Heap: turn the array into a heap (computed), sifting each parent down from the "
                              "last.", NoArgs, _check_heap("heapify"), _said_bt, reveals=True),
        "insert_step": ActionSpec("BST: insert one comparison at a time (computed): each call compares the value "
                                  "with the next node down and goes left or right; the call that finds a free "
                                  "place puts it there. Call it again with the same value until it is in.",
                                  BTValueArgs, _check_bt_step("insert"), _said_bt_step, reveals=True),
        "search_step": ActionSpec("BST: search one comparison at a time (computed): each call compares the value "
                                  "with the next node down; it ends found (green) or at a missing child.",
                                  BTValueArgs, _check_bt_step("search"), _said_bt_step, reveals=True),
        "push_step": ActionSpec("Heap: push one swap at a time (computed): the first call puts the value in the "
                                "next free place, each later one compares it with its parent and swaps or stops. "
                                "Same value each call until it settles.", BTValueArgs, _check_bt_step("push"),
                                _said_bt_step, reveals=True),
        "pop_step": ActionSpec("Heap: pop one swap at a time (computed): the first call takes the root out and "
                               "moves the last value up, each later one compares it with its better child and "
                               "swaps or stops.", NoArgs, _check_bt_step("pop"), _said_bt_step, reveals=True),
        "heapify_step": ActionSpec("Heap: heapify one comparison at a time (computed), sifting each parent down "
                                   "from the last.", NoArgs, _check_bt_step("heapify"), _said_bt_step,
                                   reveals=True),
        "traverse_step": ActionSpec("Visit the next node in this order (computed); the visited values are listed.",
                                    BTOrderArgs, _check_traverse, _said_bt, reveals=True),
        "highlight": ActionSpec("Colour the nodes holding these values.", BTValuesArgs,
                                lambda s, a: next((f"there is no node {v}" for v in a.values
                                                   if v not in _bt_values(s)), None),
                                lambda s, a: f"{', '.join(map(str, a.values))} turn"
                                             f"{'s' if len(a.values) == 1 else ''} {a.colour.lower()}"),
        "ghost": ActionSpec("A wrong idea: a red dashed node hung in a free place it doesn't belong, noted in red "
                            "(for a wrong turn or a taken place use ghost_turn; for a wrong order, ghost_mark).",
                            BTGhostArgs, _check_bt_ghost,
                            lambda s, a: f"a wrong idea: a red dashed {a.value} as {a.parent}'s {a.side} child, "
                                         f'noted "{a.text}"'),
        "ghost_turn": ActionSpec("A wrong turn: a red dashed arrow from a node down the side the wrong idea goes "
                                 "(\"go left at 50\", \"put it under 40\"), noted in red. The side may hold a "
                                 "child already.", BTTurnArgs, _check_bt_turn, _said_bt_turn),
        "ghost_mark": ActionSpec("A wrong idea about nodes already there (a wrong order, \"50 is listed first\"; "
                                 "a wrong answer): red dashed rings round them, noted in red.", BTMarkArgs,
                                 _check_bt_mark,
                                 lambda s, a: f"a wrong idea: red dashed rings round {', '.join(map(str, a.values))}, "
                                              f'noted "{a.text}"'),
        "note": ActionSpec("A short line of text above the tree.", NoteArgs,
                           says=lambda s, a: f'note above the tree: "{a.text}"'),
        "clear": ActionSpec("Remove highlights, the ghost and the note.",
                            says=lambda s, a: "the tree's highlights, ghost and note clear"),
    },
    example=[
        ['t = BinaryTree(kind="bst", values=[8, 3, 10, 1, 6], title="insert 7")'],
        ["t.search(value=6)"],
        ['t.ghost(parent=10, side="left", value=7, text="7 goes under 10?")'],
        ["t.clear()", "t.insert(value=7)"],
        ['t.traverse_step(order="inorder")', 't.traverse_step(order="inorder")'],
        ["t.delete(value=3)"],
    ],
)


# --------------------------------------------------------------------------
# Memory references and two-set Venn diagrams: state shared by checks and drawing.
# --------------------------------------------------------------------------

class MemoryParams(_Args):
    objects: dict[str, str] = Field(description="1-3 object IDs mapped to short displayed values; IDs stay stable during mutation")
    refs: dict[str, str] = Field(description="1-3 variable names mapped to existing object IDs; shared IDs mean aliasing")
    area: Area = "full"

    @model_validator(mode="after")
    def valid(self):
        if not 1 <= len(self.objects) <= 3 or not 1 <= len(self.refs) <= 3:
            raise ValueError("use 1-3 objects and 1-3 variables")
        if any(not x or len(x) > 6 for x in [*self.objects, *self.refs]):
            raise ValueError("names must have 1-6 characters")
        if any(not x or len(x) > 10 for x in self.objects.values()):
            raise ValueError("object values must have 1-10 characters")
        if any(est_width(x) > 1.05 for x in self.refs) or any(est_width(x) > 1.5 for x in [*self.objects, *self.objects.values()]):
            raise ValueError("memory labels are too wide to fit on screen; shorten them")
        if any(x not in self.objects for x in self.refs.values()):
            raise ValueError("every reference must name an existing object")
        return self


class BindRefArgs(_Args):
    variable: str = Field(min_length=1, max_length=6)
    object: str = Field(min_length=1, max_length=6)


class MutateRefArgs(_Args):
    object: str
    value: str = Field(min_length=1, max_length=10)


class CopyRefArgs(_Args):
    source: str
    target: str = Field(min_length=1, max_length=6)


class UnbindRefArgs(_Args):
    variable: str


def memory_op(op, s, a):
    if op == "bind":
        if est_width(a.variable) > 1.05:
            return "variable name is too wide to fit on screen"
        if a.object not in s["objects"]:
            return "reference target is not an existing object"
        if a.variable not in s["refs"] and len(s["refs"]) == 3:
            return "at most 3 variables fit on screen"
        s["refs"][a.variable] = a.object
    elif op == "mutate":
        if est_width(a.value) > 1.5:
            return "object value is too wide to fit on screen"
        if a.object not in s["objects"]:
            return "cannot mutate an unknown object"
        s["objects"][a.object] = a.value
    elif op == "copy":
        if est_width(a.target) > 1.5:
            return "object ID is too wide to fit on screen"
        if a.source not in s["objects"] or a.target in s["objects"]:
            return "copy needs an existing source and a new target ID"
        if len(s["objects"]) == 3:
            return "at most 3 objects fit on screen"
        s["objects"][a.target] = s["objects"][a.source]
    elif op == "unbind":
        if a.variable not in s["refs"]:
            return "cannot unbind an unknown variable"
        del s["refs"][a.variable]
    return None


def memory_words(s):
    return ("objects " + "; ".join(f"{k} holds {v}" for k, v in s["objects"].items()) + "; references "
            + (", ".join(f"{k} points to {v}" for k, v in s["refs"].items()) or "none"))


MEMORY_REFS = TemplateSpec(
    name="MemoryRefs", family="memory_refs", noun="memory diagram", min_rows=4,
    purpose="Variable boxes point to object boxes. Aliasing shares an object ID; mutation changes that object for every alias. Copy makes a distinct object with the same displayed value (not a recursive deep copy).",
    params=MemoryParams,
    init_state=lambda p: {"objects": dict(p.objects), "refs": dict(p.refs)},
    describe=lambda p: "A memory diagram: " + memory_words(p.model_dump()),
    actions={op: ActionSpec(doc, args, lambda s, a, op=op: memory_op(op, s, a),
                           lambda s, a: memory_words(s), reveals=True)
             for op, args, doc in [
                 ("bind", BindRefArgs, "Point a variable at an existing object; this does not copy its value."),
                 ("mutate", MutateRefArgs, "Change an object's displayed value; all aliases still point at it."),
                 ("copy", CopyRefArgs, "Create a new object with the source's displayed value; references do not change."),
                 ("unbind", UnbindRefArgs, "Remove a variable and its reference; keep the object visible.")
             ]},
    example=[['m = MemoryRefs(objects={"o1": "[1,2]"}, refs={"x": "o1", "y": "o1"})'],
             ['m.mutate(object="o1", value="[1,2,3]")'], ['m.copy(source="o1", target="o2")'],
             ['m.bind(variable="y", object="o2")'], ['m.mutate(object="o1", value="[9]")']],
)


class VennParams(_Args):
    universe: list[str] = Field(description="1-12 distinct element labels, each 1-3 characters; at most 4 in each region (A only, both, B only) and 6 outside both")
    a: list[str] = Field(description="elements in set A")
    b: list[str] = Field(description="elements in set B")
    area: Area = "full"

    @model_validator(mode="after")
    def valid(self):
        if not 1 <= len(self.universe) <= 12 or len(set(self.universe)) != len(self.universe):
            raise ValueError("use 1-12 distinct universe elements")
        if any(not x or len(x) > 3 or est_width(x) > 0.65 for x in self.universe):
            raise ValueError("element labels must have 1-3 characters")
        if any(len(set(xs)) != len(xs) or not set(xs) <= set(self.universe) for xs in (self.a, self.b)):
            raise ValueError("sets must contain distinct elements from the universe")
        groups = venn_regions(self.model_dump())
        if any(len(xs) > 4 for xs in groups[:3]) or len(groups[3]) > 6:
            raise ValueError("at most 4 elements fit in each Venn region (A only, both, B only) and 6 outside both")
        return self


def venn_regions(s):
    a, b = set(s["a"]), set(s["b"])
    return [[x for x in s["universe"] if (x in a, x in b) == region]
            for region in ((True, False), (True, True), (False, True), (False, False))]


SetOperation = Literal["a", "b", "union", "intersection", "a_minus_b", "b_minus_a", "symmetric_difference", "complement_a", "complement_b"]


class VennShadeArgs(_Args):
    operation: SetOperation
    colour: Colour = "TEAL"


def venn_result(s, operation):
    a, b, u = set(s["a"]), set(s["b"]), set(s["universe"])
    result = {"a": a, "b": b, "union": a | b, "intersection": a & b, "a_minus_b": a - b,
              "b_minus_a": b - a, "symmetric_difference": a ^ b, "complement_a": u - a, "complement_b": u - b}[operation]
    return [x for x in s["universe"] if x in result]


def _venn_shade(s, a):
    s["operation"] = a.operation
    s["result"] = venn_result(s, a.operation)


VENN_DIAGRAM = TemplateSpec(
    name="VennDiagram", family="sets_logic", noun="Venn diagram", min_rows=4,
    purpose="Two sets A and B inside a finite universe U, with elements placed by membership. Shade union, intersection, differences or complements. Circle areas are schematic, not proportional to counts. Not a three-set diagram or proof engine.",
    params=VennParams, init_state=lambda p: p.model_dump(),
    describe=lambda p: f"Two sets inside U = {p.universe}: A = {p.a}, B = {p.b}; elements placed by membership",
    actions={"shade": ActionSpec("Shade the operation's region; its membership is computed from the sets.", VennShadeArgs,
                                  _venn_shade, lambda s, a: f"{a.operation.replace('_', ' ')} is shaded {a.colour.lower()}; elements: {s['result'] or 'empty set'}", reveals=True),
             "clear": ActionSpec("Remove shading, keeping sets and elements.", check=lambda s, a: s.update(operation=None, result=[]), says=lambda s, a: "the shading clears")},
    example=[['v = VennDiagram(universe=["1", "2", "3", "4"], a=["1", "2"], b=["2", "3"])'],
             ['v.shade(operation="intersection")'], ['v.shade(operation="union")'],
             ['v.shade(operation="complement_a")'], ['v.clear()']],
)


# --------------------------------------------------------------------------
# Bounded advanced mathematics: numerical ODEs, Euclidean constructions, 3D
# --------------------------------------------------------------------------
from typing import Annotated
from pydantic import FiniteFloat
from animation_agent.visuals.math_support import (
    slope_samples, solution_curve, line_intersections, plane_polygon, surface_mesh, vector_label,
)

MathCoord = Annotated[FiniteFloat, Field(ge=-100, le=100)]
Point2 = tuple[MathCoord, MathCoord]
Point3 = tuple[MathCoord, MathCoord, MathCoord]
DiagramName = Annotated[str, Field(pattern=r"^[A-Za-z]$")]


class SlopeFieldParams(_Args):
    fn: str = Field(description="dy/dx=f(x,y); arithmetic + - * / **, sin cos tan exp log ln sqrt abs, pi e; max 96 characters")
    x_range: Point2 = (-2, 2)
    y_range: Point2 = (-2, 2)
    density: int = Field(9, ge=5, le=13, description="samples per axis")
    area: Area = "full"

    @model_validator(mode="after")
    def valid(self):
        if any(not 0.1 <= r[1] - r[0] <= 40 for r in (self.x_range, self.y_range)):
            raise ValueError("axis ranges must increase with span 0.1-40")
        if any(est_width(str(float(v)).removesuffix(".0")) > 1.15 for v in (*self.x_range, *self.y_range)):
            raise ValueError("axis endpoint labels are too long to fit on screen; use shorter values")
        if not slope_samples(self.fn, self.x_range, self.y_range, self.density):
            raise ValueError("the slope must be finite somewhere on the sampling grid")
        return self


class SolutionArgs(_Args):
    initial: Point2 = Field(description="initial [x,y] inside the axes where f is defined")
    colour: Colour = "GOLD"


def slope_solution(s, a):
    if len(s["solutions"]) >= 3:
        return "at most 3 solution curves fit on screen; clear before adding another"
    try:
        pts = solution_curve(s["fn"], a.initial, s["x_range"], s["y_range"])
    except ValueError as e:
        return str(e)
    if len(pts) < 2:
        return "no visible numerical solution from this initial condition"
    s["solutions"].append({"initial": list(a.initial), "colour": a.colour, "points": pts})


SLOPE_FIELD = TemplateSpec(
    name="SlopeField", family="slope_field", noun="slope field", min_rows=6,
    purpose="Requires the whole frame; show formulas/notes before or after, never beside. First-order scalar ODE dy/dx=f(x,y), 5-13 slopes per axis, up to 3 approximate numerical solution curves. Finite arithmetic formulas only; no ODE systems, implicit equations, or exact symbolic solutions. Undefined samples are omitted; curves stop at detected singularities or frame boundaries.",
    params=SlopeFieldParams, init_state=lambda p: {**p.model_dump(), "solutions": []},
    describe=lambda p: f"Slope field dy/dx = {p.fn} on x={p.x_range}, y={p.y_range}; undefined samples omitted",
    actions={
        "solution": ActionSpec("Trace an approximate numerical solution through initial [x,y], in both x directions.", SolutionArgs,
                               slope_solution, lambda s, a: f"An approximate numerical solution through {a.initial}; stops at the axes boundary or numerical/domain limit", reveals=True),
        "clear": ActionSpec("Remove solution curves, retaining the slope field.", check=lambda s, a: s.update(solutions=[]), says=lambda s, a: "solution curves clear; the slope field stays"),
    },
    example=[['f = SlopeField(fn="x-y", x_range=[-2,2], y_range=[-2,2])'],
             ['f.solution(initial=[0,1])'], ['f.solution(initial=[0,-1], colour="PINK")'], ['f.clear()']],
)


class GeometryParams(_Args):
    points: dict[DiagramName, Point2] = Field(description="1-8 named points; one letter per name")
    extent: Annotated[FiniteFloat, Field(ge=1, le=20)] = 4
    area: Area = "full"

    @model_validator(mode="after")
    def valid(self):
        if not 1 <= len(self.points) <= 8:
            raise ValueError("use 1-8 points")
        problem = geometry_points(self.points, self.extent)
        if problem:
            raise ValueError(problem)
        return self


def geometry_points(points, extent):
    import math
    vals = list(points.values())
    if any(max(abs(v) for v in p) > extent * 0.85 for p in vals):
        return "points must lie within 85% of extent to leave room for labels"
    if any(math.dist(p, q) < extent * 0.18 for i, p in enumerate(vals) for q in vals[i+1:]):
        return "points are too close for distinct labels; enlarge the construction or use fewer points"
    return None


class GeoLineArgs(_Args):
    name: DiagramName
    a: DiagramName
    b: DiagramName


class GeoCircleArgs(_Args):
    name: DiagramName
    center: DiagramName
    radius: Annotated[FiniteFloat, Field(gt=0, le=40)]


class GeoIntersectionArgs(_Args):
    first: DiagramName
    second: DiagramName
    names: list[DiagramName] = Field(max_length=2, description="name ALL intersections, sorted by x then y: [] for none, one for tangent, two for crossing circles; reuse an existing point name only at its exact position")


class GeoPerpendicularArgs(_Args):
    name: DiagramName
    line: DiagramName
    through: DiagramName


class GeoAngleArgs(_Args):
    name: DiagramName
    a: DiagramName
    vertex: DiagramName
    b: DiagramName


class GeoTriangleArgs(_Args):
    a: DiagramName
    b: DiagramName
    c: DiagramName


def geometry_op(op, s, a):
    import numpy as np
    points, shapes = s["points"], s["shapes"]
    next_points, next_shapes = copy.deepcopy(points), copy.deepcopy(shapes)
    try:
        if hasattr(a, "name") and (a.name in points or a.name in shapes):
            return "construction names must be new and unique"
        def pt(name):
            if name not in points:
                raise ValueError(f"unknown point {name}")
            return np.array(points[name], float)
        def shape(name):
            if name not in shapes:
                raise ValueError(f"unknown construction {name}")
            return shapes[name]
        if op in ("line", "segment", "midpoint", "bisector"):
            p, q = pt(a.a), pt(a.b)
            if np.linalg.norm(q-p) < 1e-9:
                return "a construction needs two distinct points"
            if op == "midpoint":
                next_points[a.name] = ((p+q)/2).tolist()
            else:
                if op == "bisector":
                    d, p = q-p, (p+q)/2
                    q = p + [-d[1], d[0]]
                next_shapes[a.name] = {"kind": "segment" if op == "segment" else "line", "p": p.tolist(), "q": q.tolist()}
        elif op == "circle":
            p = pt(a.center)
            if a.radius < s["extent"] * 0.1:
                return "circle is too small at this extent to read on screen"
            if max(abs(p)) + a.radius > s["extent"]:
                return "circle must fit inside the viewing square"
            next_shapes[a.name] = {"kind": "circle", "center": p.tolist(), "radius": a.radius}
        elif op == "intersect":
            intersections = line_intersections(shape(a.first), shape(a.second))
            if len(a.names) != len(intersections):
                return f"this construction has {len(intersections)} intersections; supply exactly that many names"
            if len(set(a.names)) != len(a.names) or any(n in shapes for n in a.names):
                return "intersection names must be distinct point names"
            if any(n in points and not np.allclose(points[n], p, rtol=0, atol=1e-9)
                   for n, p in zip(a.names, intersections)):
                return "an existing point name can only be reused at its original position"
            next_points.update(zip(a.names, intersections))
        elif op == "perpendicular":
            line = shape(a.line)
            if line["kind"] == "circle":
                return "perpendicular needs a line or segment"
            p, d = pt(a.through), np.array(line["q"]) - line["p"]
            next_shapes[a.name] = {"kind": "line", "p": p.tolist(), "q": (p + [-d[1], d[0]]).tolist()}
        elif op == "angle_bisector":
            p = pt(a.vertex)
            u, v = pt(a.a)-p, pt(a.b)-p
            if min(np.linalg.norm(u), np.linalg.norm(v)) < 1e-9:
                return "angle needs distinct arm points and vertex"
            u, v = u / np.linalg.norm(u), v / np.linalg.norm(v)
            d = u + v
            if abs(u[0]*v[1]-u[1]*v[0]) < 1e-9:
                return "angle bisector needs a nondegenerate angle between 0 and 180 degrees"
            next_shapes[a.name] = {"kind": "line", "p": p.tolist(), "q": (p+d).tolist()}
        elif op == "triangle":
            p, q, r = pt(a.a), pt(a.b), pt(a.c)
            u, v = q-p, r-p
            if abs(u[0]*v[1]-u[1]*v[0]) < 1e-9:
                return "triangle vertices must not be collinear"
            for i, (start, end) in enumerate(((p,q),(q,r),(r,p))):
                next_shapes[f"triangle{len(shapes)}_{i}"] = {"kind": "segment", "p": start.tolist(), "q": end.tolist()}
        if len(next_points) > 8 or len(next_shapes) > 8:
            return "at most 8 points and 8 constructions fit on screen"
        problem = geometry_points(next_points, s["extent"])
        if problem:
            return problem
    except ValueError as e:
        return str(e)
    s.update(points=next_points, shapes=next_shapes)
    s["result"] = ("No intersection" if op == "intersect" and not a.names else
                   f"{op.replace('_', ' ')} constructed")
    return None


GEOMETRY_CONSTRUCTION = TemplateSpec(
    name="GeometryConstruction", family="geometry", noun="geometric construction", min_rows=6,
    purpose="Requires the whole frame; show formulas/notes before or after, never beside. Euclidean 2D points, lines, segments, circles, triangles, midpoint, perpendicular, perpendicular bisector, internal angle bisector, and all line/circle intersections (including none/tangent). Equal scales. Up to 8 labeled points and 8 constructions. No arbitrary transformations, conics, 3D geometry, or proof engine.",
    params=GeometryParams, init_state=lambda p: {**p.model_dump(), "shapes": {}, "result": ""},
    describe=lambda p: f"Euclidean construction with points {p.points}, equal scale on both axes",
    actions={op: ActionSpec(doc, args, lambda s, a, op=op: geometry_op(op, s, a),
                           lambda s, a: f"{s['result']}; points {s['points']}", reveals=True)
             for op, args, doc in [
                 ("line", GeoLineArgs, "Infinite line through a,b, clipped to the frame."),
                 ("segment", GeoLineArgs, "Segment joining a,b."),
                 ("circle", GeoCircleArgs, "Circle with given center point and positive radius."),
                 ("triangle", GeoTriangleArgs, "Join three noncollinear vertices."),
                 ("midpoint", GeoLineArgs, "Compute and label midpoint of a,b with name."),
                 ("bisector", GeoLineArgs, "Construct perpendicular bisector of segment a,b."),
                 ("perpendicular", GeoPerpendicularArgs, "Line perpendicular to line through the named point."),
                 ("angle_bisector", GeoAngleArgs, "Line along the internal bisector of angle a,vertex,b."),
                 ("intersect", GeoIntersectionArgs, "Compute and label ALL intersections of two named constructions; [] displays No intersection.")
             ]},
    example=[['g = GeometryConstruction(points={"A":[-2,0],"B":[2,0]}, extent=4)'],
             ['g.segment(name="s", a="A", b="B")'], ['g.midpoint(name="M", a="A", b="B")'],
             ['g.bisector(name="p", a="A", b="B")']],
)


class Scene3DParams(_Args):
    extent: Annotated[FiniteFloat, Field(ge=1, le=20, description="half-width of the viewing cube: the smallest that holds the vectors or the part of the surface the lesson discusses (a region 0<=x,y<=1 needs about 1.5); a larger extent shrinks the picture")] = 3
    azimuth: Annotated[FiniteFloat, Field(ge=-180, le=180)] = 35
    elevation: Annotated[FiniteFloat, Field(ge=15, le=75)] = 25
    area: Area = "full"


class Vector3DArgs(_Args):
    name: DiagramName
    value: Point3
    colour: Colour = "BLUE"


class Plane3DArgs(_Args):
    normal: Point3 = Field(description="nonzero [a,b,c] for ax+by+cz=offset; includes vertical planes")
    offset: MathCoord = 0
    colour: Colour = "TEAL"


class Surface3DArgs(_Args):
    fn: str = Field(description="z=f(x,y), same restricted arithmetic as SlopeField; wireframe clipped to cube")
    colour: Colour = "TEAL"


class View3DArgs(_Args):
    azimuth: Annotated[FiniteFloat, Field(ge=-180, le=180)]
    elevation: Annotated[FiniteFloat, Field(ge=15, le=75)] = 25


class Cross3DArgs(_Args):
    name: DiagramName
    first: DiagramName
    second: DiagramName
    colour: Colour = "GOLD"


def scene3d_op(op, s, a):
    import numpy as np
    if op in ("vector", "cross"):
        if a.name in s["vectors"] or len(s["vectors"]) >= 3:
            return "use a new vector name; at most 3 vectors fit on screen"
        if op == "cross":
            if a.first not in s["vectors"] or a.second not in s["vectors"]:
                return "cross product needs two existing vectors"
            v = np.cross(s["vectors"][a.first]["value"], s["vectors"][a.second]["value"])
        else:
            v = np.array(a.value)
        if max(abs(v)) > s["extent"]:
            return "vector is outside the viewing cube; increase extent"
        if est_width(vector_label(a.name, v)) > 3.6:
            return "vector coordinates are too long to fit on screen; use shorter values"
        s["vectors"][a.name] = {"value": v.tolist(), "colour": a.colour}
        s["result"] = f"vector {a.name} = {v.tolist()}"
    elif op in ("plane", "surface"):
        if s["sheet"] is not None:
            return "one plane or surface at a time; clear before replacing it"
        try:
            visible = plane_polygon(a.normal, a.offset, s["extent"]) if op == "plane" else surface_mesh(a.fn, s["extent"])
        except ValueError as e:
            return str(e)
        if not visible:
            return "surface has no visible finite wire segments inside the viewing cube"
        s["sheet"] = {"kind": op, **a.model_dump()}
        s["result"] = (f"plane {a.normal} dot (x,y,z) = {a.offset}" if op == "plane" else f"wireframe z = {a.fn}, undefined and clipped regions omitted")
    elif op == "view":
        s.update(azimuth=a.azimuth, elevation=a.elevation)
        s["result"] = f"orthographic view at azimuth {a.azimuth}, elevation {a.elevation} degrees"
    return None


SCENE_3D = TemplateSpec(
    name="Scene3D", family="vectors_3d", noun="3D coordinate scene", min_rows=6,
    purpose="Requires the whole frame; show formulas/notes before or after, never beside. Equal-unit orthographic 3D view: up to 3 named origin vectors (zero shown as a labeled dot), computed cross product, one bounded plane ax+by+cz=d OR sampled wireframe z=f(x,y), and rotating viewpoint. Cube extent 1-20; transparent wireframe with no hidden-surface removal. No implicit/parametric surfaces, solid rendering, or arbitrary 3D objects.",
    params=Scene3DParams, init_state=lambda p: {**p.model_dump(), "vectors": {}, "sheet": None, "result": ""},
    describe=lambda p: f"Labeled x,y,z axes in an orthographic 3D view, cube bounds {-p.extent} to {p.extent}",
    actions={**{op: ActionSpec(doc, args, lambda s, a, op=op: scene3d_op(op, s, a),
                              lambda s, a: s["result"], reveals=op != "view")
                for op, args, doc in [
                    ("vector", Vector3DArgs, "Draw a named origin vector with three coordinates."),
                    ("cross", Cross3DArgs, "Compute first cross second and add the resulting vector."),
                    ("plane", Plane3DArgs, "Draw plane normal dot (x,y,z)=offset clipped to the viewing cube."),
                    ("surface", Surface3DArgs, "Draw a sampled wireframe z=f(x,y); gaps at detected singularities."),
                    ("view", View3DArgs, "Rotate the orthographic viewpoint, preserving coordinates and scale.")
                ]},
             "clear": ActionSpec("Remove vectors and plane/surface, retaining axes and viewpoint.",
                                 check=lambda s, a: s.update(vectors={}, sheet=None), says=lambda s, a: "vectors and surfaces clear; the axes stay")},
    example=[['s = Scene3D(extent=3)'], ['s.vector(name="u", value=[2,0,0])', 's.vector(name="v", value=[0,1,0], colour="PINK")'],
             ['s.cross(name="w", first="u", second="v")'], ['s.plane(normal=[0,0,1], offset=0)'],
             ['s.view(azimuth=110, elevation=35)'], ['s.clear()', 's.surface(fn="(x*x-y*y)/3")']],
)


REGISTRY: dict[str, TemplateSpec] = {s.name: s for s in (
    ARRAY_BARS, MERGE_SORT, GRAPH, BAR_CHART, NUMBER_LINE, TABLE, LINKED_LIST, STACK_QUEUE, HASH_TABLE,
    BINARY_TREE, FUNCTION_PLOT, LINEAR_MAP_2D, EQUATION_STEPS, NOTE, MEMORY_REFS, VENN_DIAGRAM, SLOPE_FIELD, GEOMETRY_CONSTRUCTION, SCENE_3D)}

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
