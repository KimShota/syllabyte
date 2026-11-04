"""
What each visual template takes and can do, without importing Manim.

The script writer's prompt is built from these (`template_cards`), and calls.py checks a script's calls against
them before anything renders. The drawing classes (array_bars.py, ...) implement the same names: every action
here is a method there with the same arguments (tests/test_visual_templates.py checks this).

Logic a drawing has to get right, like which half bisection discards, lives here as plain functions, so the
checker and the drawing compute the same thing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Bump when a template draws differently (or the call language changes): it is part of the cache key of every
# video drawn with templates (syllabyte_common.video_jobs.video_key), so those videos are made again.
TEMPLATES_VERSION = "2"

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
    indices = list(indices)
    values = ", ".join(_fmt(state["values"][i]) for i in indices)
    if len(indices) == 1:
        return f"cell {indices[0]} (value {values})"
    return f"cells {', '.join(map(str, indices))} (values {values})"


def _span(first: int, last: int) -> str:
    return f"cell {first}" if first == last else f"cells {first}-{last}"


def _verb(indices, verb: str) -> str:
    return verb + "s" if len(list(indices)) == 1 else verb


def _said_bisect_check(state: dict, a) -> str:
    b = state["bisect"]
    lo, hi = b["range"]
    mid = (lo + hi) // 2
    return (f"lo, mid, hi point at cells {lo}, {mid}, {hi}; the middle value {_fmt(state['values'][mid])} is "
            f"compared with the target {_fmt(b['target'])}")


def _said_bisect_discard(state: dict, a) -> str:
    b = state["bisect"]
    mid, lo0, hi0, found = b["last"]
    value, target = state["values"][mid], b["target"]
    if found:
        return f"{_fmt(value)} is the target: cell {mid} turns green, found"
    if value < target:
        out = f"{_fmt(value)} < {_fmt(target)}, so {_span(lo0, mid)} grey out"
    else:
        out = f"{_fmt(value)} > {_fmt(target)}, so {_span(mid, hi0)} grey out"
    if b["lo"] > b["hi"]:
        return out + "; nothing is left in play: the target isn't in the list"
    return out + f"; {_span(b['lo'], b['hi'])} stay in play"


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
    if b is None or b["target"] != a.target:
        b = state["bisect"] = {"lo": 0, "hi": len(state["values"]) - 1, "target": a.target, "checked": False,
                               "done": False}
    if b["done"]:
        return "the search already ended (found, or nothing left to check)"
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


ARRAY_BARS = TemplateSpec(
    name="ArrayBars",
    family="array_bars",
    purpose="A list/array as cells or bars: searching, sorting, pointers, halves, swaps. Needs at least half "
            "the frame.",
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
                               lambda s, a: f"{_span(a.start, a.end)} grey out: ruled out"),
        "restore": ActionSpec("Un-grey every cell.", says=lambda s, a: "every cell is back in play"),
        "point": ActionSpec("Show (or move) a named pointer under a cell.", PointArgs, _check_point,
                            lambda s, a: f'pointer "{a.name}" under {_cells(s, [a.index])}'),
        "unpoint": ActionSpec("Remove a pointer.", NameArgs, _check_unpoint,
                              lambda s, a: f'pointer "{a.name}" disappears'),
        "compare": ActionSpec('Highlight two cells and note the comparison, e.g. "4 < 7".', PairArgs,
                              lambda s, a: _in_range(s, a.i, a.j),
                              lambda s, a: f"{_cells(s, [a.i, a.j])} light up and are compared"),
        "swap": ActionSpec("Swap two cells (they move past each other).", PairArgs, _check_swap,
                           lambda s, a: f"cells {a.i} and {a.j} swap places; the row now reads "
                                        f"{', '.join(_fmt(v) for v in s['values'])}"),
        "set_value": ActionSpec("Change one cell's value.", SetValueArgs, _check_set_value,
                                lambda s, a: f"cell {a.index} changes to {_fmt(a.value)}"),
        "note": ActionSpec("A short line of text above the list.", NoteArgs,
                           says=lambda s, a: f'note above the list: "{a.text}"'),
        "counter": ActionSpec('Show or update a counter, e.g. checks: 3.', CounterArgs,
                              says=lambda s, a: f"counter {a.label}: {a.value}"),
        "scan": ActionSpec("Linear search: pointer i moves to this cell, the checks counter goes up by one.",
                           ScanArgs, _check_scan, _said_scan),
        "bisect_check": ActionSpec(
            "Bisection: show lo, mid, hi on the part still in play and compare the middle value with the target. "
            "The first call starts the search over the whole list. Values must be sorted numbers.",
            TargetArgs, _check_bisect_check, _said_bisect_check,
        ),
        "bisect_discard": ActionSpec(
            "Bisection: grey out the half that can't hold the target (or mark mid green if it is the target).",
            NoArgs, _check_bisect_discard, _said_bisect_discard,
        ),
        "bisect_step": ActionSpec("bisect_check and bisect_discard in one line.", TargetArgs, _check_bisect_step,
                                  lambda s, a: f"{_said_bisect_check(s, a)}; {_said_bisect_discard(s, a)}"),
        "found": ActionSpec("Mark this cell green: found.", IndexArgs, lambda s, a: _in_range(s, a.index),
                            lambda s, a: f"{_cells(s, [a.index])} turns green: found"),
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
                            _said_apply),
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
            ColourArgs, says=_said_eigenlines,
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
                              lambda s, a: "the hidden piece is revealed"),
        "box": ActionSpec("Box the current line: the result.", BoxArgs,
                          says=lambda s, a: f"the line {s['last']} is boxed in {a.colour.lower()}"),
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


REGISTRY: dict[str, TemplateSpec] = {s.name: s for s in (ARRAY_BARS, LINEAR_MAP_2D, EQUATION_STEPS, NOTE)}

# Extra checks a template's parameters need beyond its model (the vectors fit the grid).
INIT_CHECKS: dict[str, Callable[[BaseModel], str | None]] = {"LinearMap2D": _init_map_check}


# --------------------------------------------------------------------------
# The writer's prompt
# --------------------------------------------------------------------------


def _type_name(annotation) -> str:
    text = str(annotation).replace("typing.", "").replace("animation_agent.visuals.specs.", "")
    return text.replace("NoneType", "None").replace("<class '", "").replace("'>", "")


def _signature(model: type[BaseModel]) -> str:
    parts = []
    for name, f in model.model_fields.items():
        if f.annotation in (Area,):
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


def template_card(spec: TemplateSpec) -> str:
    lines = [f"{spec.name}({_signature(spec.params)})", f"  {spec.purpose}"]
    lines += [f"  - {note}" for note in _field_notes(spec.params)]
    lines.append("  Actions:")
    for name, action in spec.all_actions().items():
        lines.append(f"    .{name}({_signature(action.args)}): {action.doc}")
        lines += [f"        {note}" for note in _field_notes(action.args)]
    lines.append("  Example (one segment):")
    for k, calls in enumerate(spec.example, 1):
        lines.append(f"    beat {k}:" + ("" if calls else " (no calls: the picture stays)"))
        lines += [f"      {call}" for call in calls]
    return "\n".join(lines)


def template_cards(names: list[str] | None = None) -> str:
    return "\n\n".join(template_card(REGISTRY[n]) for n in (names or list(REGISTRY)))
