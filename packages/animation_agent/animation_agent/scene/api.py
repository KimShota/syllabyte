"""
What a picture program can call (plan/scene-grammar-plan.md). Pure Python, no Manim: it runs inside the sandbox
(scene/sandbox.py), and the state it records is drawn by scene/draw.py.

A program makes up to MAX_VIEWS views (cells, nodes, code, container; for math: axes, venn, geometry), changes them
as the algorithm or the math runs, and calls
snap("what this picture shows") after each step it wants seen. Each snap() records every view's whole state; the
storyboard steps through the snapshots one beat at a time, and the engine animates the change between two of them
by object identity (a node key, a cell index), so a node that moved slides and a recoloured cell recolours.

Styles are words, not colours: STYLES lists them. The engine maps them to colours that pass the contrast rules.

The math views record shapes in the program's own coordinates, computed here (a curve is sampled, a Riemann sum's
rectangles and a level curve's lines are worked out, a Venn region's elements are a set operation), so every value
on screen comes from running the math; scene/layout.py fits the coordinates to the frame.
"""

from __future__ import annotations

import copy
import math
from fractions import Fraction

MAX_VIEWS = 3
MAX_SNAPS = 40
MAX_NODES = 15
MAX_CELLS = 12
MAX_CODE_LINES = 6
MAX_LABEL = 2  # characters in a node or cell: "10" is 0.35 units wide at the minimum font
MAX_TITLE = 18
STYLES = ("current", "visited", "found", "compare", "red", "grey", "new", "blue")
LAYOUTS = ("tree", "binary", "graph")


class PictureError(Exception):
    """The program asked for something the engine can't draw (it is sent back to the writer with this text)."""


_views: dict[str, _View] = {}
_snaps: list[dict] = []


INFINITY = "∞"


def _label(v) -> str:
    s = INFINITY if (isinstance(v, float) and v == float("inf")) or v in ("INF", "inf", "Infinity") else str(v)
    if len(s) > MAX_LABEL:
        raise PictureError(f"label {s!r} is longer than {MAX_LABEL} characters")
    return s


def _style(style):
    if style is not None and style not in STYLES:
        raise PictureError(f"unknown style {style!r}; use one of {', '.join(STYLES)}")
    return style


class _View:
    kind = ""

    def __init__(self, name: str, title: str | None):
        if name in _views:
            raise PictureError(f"there is already a view named {name!r}")
        if len(_views) >= MAX_VIEWS:
            raise PictureError(f"at most {MAX_VIEWS} views on screen")
        if title is not None and len(title) > MAX_TITLE:
            raise PictureError(f"title {title!r} is longer than {MAX_TITLE} characters")
        self.name, self.title = name, title
        _views[name] = self

    def state(self) -> dict:
        raise NotImplementedError


class Cells(_View):
    """A row of cells (an array, a string, the slots of a queue). Index like a list; mark cells; point at them."""

    kind = "cells"

    def __init__(self, name, values, title=None, index=True):
        super().__init__(name, title)
        self._values = [_label(v) for v in values]
        self._raw = list(values)
        if not 1 <= len(self._raw) <= MAX_CELLS:
            raise PictureError(f"{name}: 1-{MAX_CELLS} cells")
        self.index = bool(index)
        self._marks: dict[int, str] = {}
        self._pointers: dict[str, int] = {}

    def __len__(self):
        return len(self._raw)

    def __getitem__(self, i):
        return self._raw[i]

    def __setitem__(self, i, v):
        self._raw[i] = v
        self._values[i] = _label(v)

    def __iter__(self):
        return iter(self._raw)

    def mark(self, i, style="current"):
        self._marks[i % len(self)] = _style(style)

    def unmark(self, i=None):
        if i is None:
            self._marks.clear()
        else:
            self._marks.pop(i % len(self), None)

    def point(self, label, i):
        """A short label (e.g. "lo", "head") under cell i."""
        self._pointers[_label(label)] = i % len(self)

    def unpoint(self, label):
        self._pointers.pop(str(label), None)

    def state(self):
        return {"kind": self.kind, "title": self.title, "values": list(self._values), "index": self.index,
                "marks": {str(k): v for k, v in self._marks.items()}, "pointers": dict(self._pointers)}


class Nodes(_View):
    """Nodes and links. layout="tree": links go parent -> child, children in `slot` order, roots side by side (a
    forest wraps onto more rows when it is wider than the frame); "binary": the same with slot 0 = left, 1 = right,
    a missing child keeps its side; "graph": laid out once for every node and link the program ever shows."""

    kind = "nodes"

    def __init__(self, name, nodes=(), layout="tree", directed=False, title=None):
        super().__init__(name, title)
        if layout not in LAYOUTS:
            raise PictureError(f"layout must be one of {', '.join(LAYOUTS)}")
        self.layout, self.directed = layout, bool(directed)
        self._nodes: dict[str, dict] = {}
        self._links: dict[tuple[str, str], dict] = {}
        for n in nodes:
            self.add(n)

    def add(self, key, label=None, style=None):
        key = str(key)
        if key not in self._nodes and len(self._nodes) >= MAX_NODES:
            raise PictureError(f"{self.name}: at most {MAX_NODES} nodes")
        self._nodes[key] = {"label": _label(key if label is None else label), "style": _style(style)}

    def remove(self, key):
        key = str(key)
        self._nodes.pop(key, None)
        for e in [e for e in self._links if key in e]:
            del self._links[e]

    def link(self, a, b, style=None, label=None, slot=None):
        a, b = str(a), str(b)
        for k in (a, b):
            if k not in self._nodes:
                raise PictureError(f"{self.name}: no node {k!r} to link")
        if self.layout != "graph":
            # a tree node has one parent: linking it under a new one moves it
            for e in [e for e in self._links if e[1] == b]:
                del self._links[e]
        self._links[(a, b)] = {"style": _style(style), "label": None if label is None else str(label)[:6],
                               "slot": slot}

    def unlink(self, a, b):
        self._links.pop((str(a), str(b)), None)

    def restyle_link(self, a, b, style):
        if (str(a), str(b)) in self._links:
            self._links[(str(a), str(b))]["style"] = _style(style)

    def parent(self, key):
        key = str(key)
        return next((a for (a, b) in self._links if b == key), None)

    def mark(self, key, style="current"):
        if str(key) in self._nodes:
            self._nodes[str(key)]["style"] = _style(style)

    def unmark(self, key=None):
        for k, n in self._nodes.items():
            if key is None or k == str(key):
                n["style"] = None

    def state(self):
        return {"kind": self.kind, "title": self.title, "layout": self.layout, "directed": self.directed,
                "nodes": copy.deepcopy(self._nodes),
                "links": [[a, b, d["style"], d["label"], d["slot"]] for (a, b), d in self._links.items()]}


class Code(_View):
    """Code lines, the current one lit."""

    kind = "code"

    def __init__(self, name, lines, title=None):
        super().__init__(name, title)
        if not 1 <= len(lines) <= MAX_CODE_LINES:
            raise PictureError(f"{name}: 1-{MAX_CODE_LINES} code lines")
        self.lines = [str(s) for s in lines]
        self.current = None

    def line(self, i):
        self.current = None if i is None else int(i)

    def state(self):
        return {"kind": self.kind, "title": self.title, "lines": list(self.lines), "current": self.current}


class Container(_View):
    """A vessel holding `level` of `capacity` units (a jug, a tank, a budget)."""

    kind = "container"
    MAX = 3

    def __init__(self, name, capacity, level=0, title=None):
        super().__init__(name, title)
        self.capacity, self.level = capacity, level
        self.style = None

    def pour_into(self, other: Container):
        amount = min(self.level, other.capacity - other.level)
        self.level -= amount
        other.level += amount
        return amount

    def state(self):
        if not 0 <= self.level <= self.capacity:
            raise PictureError(f"{self.name}: level {self.level} outside 0..{self.capacity}")
        return {"kind": self.kind, "title": self.title, "capacity": self.capacity, "level": self.level,
                "style": self.style}


# ---- math ------------------------------------------------------------------------------------------------

MAX_ITEMS = 12  # things drawn on one set of axes or one figure
SAMPLES = 120  # points a curve is sampled at
MAX_RECTS = 40
MAX_MATH_LABEL = 8  # characters in a curve's, point's or line's label ("f(x)", "x^2", "y = 2x")
BIG = 1e6


def _num(v) -> float:
    v = float(v)
    if not math.isfinite(v):
        raise PictureError(f"{v} is not a finite number")
    return v


def _math_label(label):
    if label is None or not str(label).strip():  # '' or ' ': no label
        return None
    label = str(label).strip()
    if len(label) > MAX_MATH_LABEL:
        raise PictureError(f"label {label!r} is longer than {MAX_MATH_LABEL} characters")
    return label


def _value(f, x):
    """f(x), or None where f isn't defined or blows up (a curve breaks there)."""
    try:
        y = float(f(x))
    except (ZeroDivisionError, ValueError, OverflowError, TypeError):
        return None
    return y if math.isfinite(y) and abs(y) < BIG else None


def _pieces(f, lo, hi, n=SAMPLES) -> list[list[list[float]]]:
    """f sampled from lo to hi, split where it is undefined or jumps (1/x at 0, tan at pi/2)."""
    xs = [lo + (hi - lo) * i / n for i in range(n + 1)]
    ys = [_value(f, x) for x in xs]
    finite = [y for y in ys if y is not None]
    span = (max(finite) - min(finite)) if finite else 0.0
    pieces, cur = [], []
    for i, (x, y) in enumerate(zip(xs, ys)):
        if y is None or (cur and span and abs(y - cur[-1][1]) > span / 3 and i > 0
                         and abs(y - cur[-1][1]) > 50 * (hi - lo) / n * max(1.0, abs(y))):
            if len(cur) > 1:
                pieces.append(cur)
            cur = [] if y is None else [[x, y]]
            continue
        cur.append([x, y])
    if len(cur) > 1:
        pieces.append(cur)
    return pieces


def derivative(f, x, h=1e-5):
    """f'(x), by a central difference."""
    return (f(x + h) - f(x - h)) / (2 * h)


def integral(f, a, b, n=400):
    """The integral of f from a to b (Simpson's rule)."""
    n += n % 2
    h = (b - a) / n
    total = f(a) + f(b) + sum((4 if i % 2 else 2) * f(a + i * h) for i in range(1, n))
    return total * h / 3


def root(f, a, b, tol=1e-10):
    """A root of f between a and b, where f(a) and f(b) have opposite signs (bisection)."""
    fa = f(a)
    if fa * f(b) > 0:
        raise PictureError(f"f({a}) and f({b}) have the same sign, so root() can't bracket a root there")
    for _ in range(200):
        m = (a + b) / 2
        fm = f(m)
        if abs(b - a) < tol or fm == 0:
            return m
        if fa * fm < 0:
            b = m
        else:
            a, fa = m, fm
    return (a + b) / 2


def _marching_squares(F, xr, yr, level, n=48) -> list[list[list[float]]]:
    """The curve F(x, y) = level as polylines (marching squares on an n x n grid, segments chained)."""
    (x0, x1), (y0, y1) = xr, yr
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    ys = [y0 + (y1 - y0) * j / n for j in range(n + 1)]
    v = [[(_value(lambda q: F(q[0], q[1]), (x, y)) or 0.0) - level for y in ys] for x in xs]
    segs = []

    def cross(p, q, vp, vq):
        t = vp / (vp - vq) if vp != vq else 0.5
        return (round(p[0] + (q[0] - p[0]) * t, 9), round(p[1] + (q[1] - p[1]) * t, 9))

    for i in range(n):
        for j in range(n):
            corners = [((xs[i], ys[j]), v[i][j]), ((xs[i + 1], ys[j]), v[i + 1][j]),
                       ((xs[i + 1], ys[j + 1]), v[i + 1][j + 1]), ((xs[i], ys[j + 1]), v[i][j + 1])]
            pts = []
            for k in range(4):
                (p, vp), (q, vq) = corners[k], corners[(k + 1) % 4]
                if (vp < 0) != (vq < 0):
                    pts.append(cross(p, q, vp, vq))
            if len(pts) == 2:
                segs.append((pts[0], pts[1]))
            elif len(pts) == 4:
                segs += [(pts[0], pts[1]), (pts[2], pts[3])]
    # chain the segments into lines
    ends: dict = {}
    for k, (a, b) in enumerate(segs):
        ends.setdefault(a, []).append(k)
        ends.setdefault(b, []).append(k)
    used, lines = set(), []
    for k in range(len(segs)):
        if k in used:
            continue
        used.add(k)
        line = [segs[k][0], segs[k][1]]
        for forward in (True, False):
            while True:
                tip = line[-1] if forward else line[0]
                nxt = next((m for m in ends.get(tip, []) if m not in used), None)
                if nxt is None:
                    break
                used.add(nxt)
                a, b = segs[nxt]
                other = b if a == tip else a
                if forward:
                    line.append(other)
                else:
                    line.insert(0, other)
        if len(line) > 2:
            lines.append([list(p) for p in line])
    return lines


class Axes(_View):
    """Axes over x in `x` (and y in `y`, or fitted to what is drawn), with curves, shaded areas, Riemann
    rectangles, lines, points, a vector field or level curves on them. Each thing has a key: drawing it again
    under the same key changes it in place."""

    kind = "axes"

    def __init__(self, name, x=(-5, 5), y=None, title=None, xlabel="x", ylabel="y", equal=False):
        super().__init__(name, title)
        self.x = [_num(x[0]), _num(x[1])]
        if not self.x[0] < self.x[1]:
            raise PictureError(f"{name}: x must run from low to high")
        self.y = None if y is None else [_num(y[0]), _num(y[1])]
        if self.y is not None and not self.y[0] < self.y[1]:
            raise PictureError(f"{name}: y must run from low to high")
        self.xlabel, self.ylabel = _math_label(xlabel), _math_label(ylabel)
        self.equal = bool(equal)
        self._items: dict[str, dict] = {}

    def _put(self, key, item, style, label=None):
        key = str(key)
        if key not in self._items and len(self._items) >= MAX_ITEMS:
            raise PictureError(f"{self.name}: at most {MAX_ITEMS} things on one set of axes")
        self._items[key] = {**item, "style": _style(style), "label": _math_label(label)}

    def plot(self, key, f, style=None, label=None, x=None):
        lo, hi = (self.x if x is None else [_num(x[0]), _num(x[1])])
        pieces = _pieces(f, lo, hi)
        if not pieces:
            raise PictureError(f"{self.name}: {key} is undefined everywhere on {lo}..{hi}")
        self._put(key, {"type": "curve", "pieces": pieces}, style, label)

    def area(self, key, f, a, b, g=None, style="visited", label=None):
        """The region between f and g (or the x-axis) from a to b, shaded."""
        a, b = _num(a), _num(b)
        top = _pieces(f, a, b, 60)
        bottom = _pieces(g, a, b, 60) if g is not None else [[[a, 0.0], [b, 0.0]]]
        if len(top) != 1 or len(bottom) != 1:
            raise PictureError(f"{self.name}: {key}: the curves must be defined all the way from {a} to {b}")
        self._put(key, {"type": "area", "points": top[0] + bottom[0][::-1]}, style, label)

    def riemann(self, key, f, a, b, n, rule="left", style="visited"):
        """n rectangles under f from a to b, each as tall as f at its left end, right end or middle; returns
        their total area."""
        a, b, n = _num(a), _num(b), int(n)
        if not 1 <= n <= MAX_RECTS:
            raise PictureError(f"{self.name}: 1-{MAX_RECTS} rectangles")
        at = {"left": 0.0, "right": 1.0, "mid": 0.5}.get(rule)
        if at is None:
            raise PictureError("rule must be 'left', 'right' or 'mid'")
        w = (b - a) / n
        rects = []
        for i in range(n):
            h = _value(f, a + (i + at) * w)
            if h is None:
                raise PictureError(f"{self.name}: {key}: f is undefined at x = {a + (i + at) * w:g}")
            rects.append([a + i * w, a + (i + 1) * w, h])
        self._put(key, {"type": "rects", "rects": rects}, style)
        return sum(h * w for _x0, _x1, h in rects)

    def line(self, key, p, q, style=None, label=None):
        """The segment from point p to point q (each an (x, y) pair)."""
        self._put(key, {"type": "segment", "points": [[_num(p[0]), _num(p[1])], [_num(q[0]), _num(q[1])]]},
                  style, label)

    def tangent(self, key, f, x0, half=None, style="current", label=None):
        """The tangent to f at x0 (slope by derivative()), drawn `half` either side; returns the slope."""
        x0 = _num(x0)
        y0, m = _value(f, x0), derivative(f, x0)
        if y0 is None:
            raise PictureError(f"{self.name}: f is undefined at x = {x0:g}")
        half = (self.x[1] - self.x[0]) / 4 if half is None else _num(half)
        self.line(key, (x0 - half, y0 - m * half), (x0 + half, y0 + m * half), style, label)
        return m

    def point(self, key, x, y, label=None, style="current"):
        self._put(key, {"type": "point", "at": [_num(x), _num(y)]}, style, label)

    def field(self, key, F, n=7, style="blue"):
        """Arrows of the vector field F(x, y) -> (u, v) on an n x n grid (lengths scaled to the largest)."""
        n = max(3, min(int(n), 9))
        y = self.y or self.x
        arrows = []
        for i in range(n):
            for j in range(n):
                px = self.x[0] + (self.x[1] - self.x[0]) * (i + 0.5) / n
                py = y[0] + (y[1] - y[0]) * (j + 0.5) / n
                try:
                    u, v = F(px, py)
                    u, v = float(u), float(v)
                except (ZeroDivisionError, ValueError, OverflowError, TypeError):
                    continue
                if math.isfinite(u) and math.isfinite(v):
                    arrows.append([px, py, u, v])
        self._put(key, {"type": "field", "arrows": arrows, "n": n}, style)

    def contour(self, key, F, level, style=None, label=None):
        """The level curve F(x, y) = level (marching squares over the axes' ranges)."""
        y = self.y or self.x
        lines = _marching_squares(F, self.x, y, _num(level))
        if not lines:
            raise PictureError(f"{self.name}: F never equals {level} on these axes")
        self._put(key, {"type": "curve", "pieces": lines}, style, label)

    def mark(self, key, style="current"):
        if str(key) in self._items:
            self._items[str(key)]["style"] = _style(style)

    def remove(self, key):
        self._items.pop(str(key), None)

    def state(self):
        return {"kind": self.kind, "title": self.title, "x": list(self.x), "y": None if self.y is None else
                list(self.y), "xlabel": self.xlabel, "ylabel": self.ylabel, "equal": self.equal,
                "items": copy.deepcopy(self._items)}


VENN_REGION = set("&|-()~ ")
MAX_ELEMENTS = 16


class Venn(_View):
    """Up to 3 sets as overlapping circles. shade(region) colours a region given as an expression over the set
    names (A&B, A|B, A-B, (A|B)-C, ~A for outside A); show_elements() writes each element in its region."""

    kind = "venn"

    def __init__(self, name, sets, universe=None, title=None):
        super().__init__(name, title)
        if not 1 <= len(sets) <= 3:
            raise PictureError(f"{name}: 1-3 sets (for more, show membership as a table of cells)")
        self.sets = {str(k): set(v) for k, v in sets.items()}
        for k in self.sets:
            if not (k.isidentifier() and len(k) <= 2):
                raise PictureError(f"{name}: a set's name is a letter or two, like A or B ({k!r})")
        self.universe = set().union(*self.sets.values()) | set(universe or ())
        if len(self.universe) > MAX_ELEMENTS:
            raise PictureError(f"{name}: at most {MAX_ELEMENTS} elements in all")
        for e in self.universe:
            _label(e)
        self._shaded: dict[str, str] = {}
        self.elements = False

    def region(self, expr):
        """The elements of a region, e.g. region('A&B') (computed with Python sets)."""
        expr = str(expr)
        if not set(expr) <= VENN_REGION | set("".join(self.sets)):
            raise PictureError(f"region {expr!r}: use set names and & | - ~ ( )")
        env = {k: set(v) for k, v in self.sets.items()}
        try:
            return eval(expr.replace("~", "U-"), {"__builtins__": {}}, {**env, "U": set(self.universe)})
        except Exception as e:
            raise PictureError(f"region {expr!r} can't be read: {e}") from e

    def _cells(self, expr) -> list[str]:
        """The region as atomic cells, each a membership string such as '101' (in A, not B, in C)."""
        names = list(self.sets)
        env = {}
        cells = []
        for bits in range(2 ** len(names)):
            member = "".join("1" if bits >> (len(names) - 1 - i) & 1 else "0" for i in range(len(names)))
            for i, n in enumerate(names):
                env[n] = {0} if member[i] == "1" else set()
            try:
                inside = eval(str(expr).replace("~", "U-"), {"__builtins__": {}}, {**env, "U": {0}})
            except Exception as e:
                raise PictureError(f"region {expr!r} can't be read: {e}") from e
            if inside:
                cells.append(member)
        return cells

    def shade(self, expr, style="found"):
        self.region(expr)  # refuses a bad expression with its reason
        self._shaded[str(expr)] = _style(style)

    def unshade(self, expr=None):
        if expr is None:
            self._shaded.clear()
        else:
            self._shaded.pop(str(expr), None)

    def show_elements(self, on=True):
        self.elements = bool(on)

    def state(self):
        names = list(self.sets)
        placed = {}
        for e in sorted(self.universe, key=str):
            placed[_label(e)] = "".join("1" if e in self.sets[n] else "0" for n in names)
        return {"kind": self.kind, "title": self.title, "sets": names,
                "shaded": [[self._cells(expr), style] for expr, style in self._shaded.items()],
                "elements": placed if self.elements else {}}


class Geometry(_View):
    """A figure in the program's own coordinates (fitted to the frame, one scale for x and y): points, segments,
    circles, polygons and angle marks. Points have keys; the rest refer to them."""

    kind = "geometry"

    def __init__(self, name, title=None):
        super().__init__(name, title)
        self._points: dict[str, dict] = {}
        self._items: dict[str, dict] = {}

    def point(self, key, x, y, label=None, style=None):
        key = str(key)
        self._points[key] = {"at": [_num(x), _num(y)], "label": _math_label(key if label is None else label),
                             "style": _style(style)}

    def at(self, key):
        """A point's (x, y)."""
        return tuple(self._need(key)["at"])

    def _need(self, key):
        """A point by its key, or by its (x, y): a coordinate pair becomes an unlabelled point of its own."""
        if isinstance(key, (tuple, list)) and len(key) == 2:
            x, y = _num(key[0]), _num(key[1])
            found = next((k for k, p in self._points.items() if p["at"] == [x, y]), None)
            if found is None:
                found = f"({x:g}, {y:g})"
                self._points[found] = {"at": [x, y], "label": None, "style": None, "hidden": True}
            return self._points[found]
        if str(key) not in self._points:
            raise PictureError(f"{self.name}: no point {key!r}; make it with point(key, x, y), or give (x, y)")
        return self._points[str(key)]

    def _key(self, key) -> str:
        """The key of a point given by key or by (x, y)."""
        point = self._need(key)
        return next(k for k, p in self._points.items() if p is point)

    def _put(self, key, item, style, label=None):
        key = str(key)
        if key not in self._items and len(self._items) >= MAX_ITEMS:
            raise PictureError(f"{self.name}: at most {MAX_ITEMS} things in one figure")
        self._items[key] = {**item, "style": _style(style), "label": _math_label(label)}

    def segment(self, key, a, b, style=None, label=None):
        self._put(key, {"type": "segment", "ends": [self._key(a), self._key(b)]}, style, label)

    def circle(self, key, center, r, style=None):
        self._put(key, {"type": "circle", "center": self._key(center), "r": _num(r)}, style)

    def polygon(self, key, points, style=None, fill=False):
        self._put(key, {"type": "polygon", "points": [self._key(p) for p in points], "fill": bool(fill)}, style)

    def arc(self, key, center, r, t1, t2, style=None, label=None):
        """The arc of radius r round center from angle t1 to t2 (radians, counter-clockwise)."""
        self._put(key, {"type": "arc", "center": self._key(center), "r1": _num(r), "r2": _num(r), "t1": _num(t1),
                        "t2": _num(t2)}, style, label)

    def sector(self, key, center, r1, r2, t1, t2, style="current", fill=True, label=None):
        """The region between radii r1 and r2 and angles t1 and t2 round center (a polar patch; r1 = 0: a pie
        slice); returns its area, (r2^2 - r1^2)(t2 - t1)/2."""
        r1, r2, t1, t2 = _num(r1), _num(r2), _num(t1), _num(t2)
        self._put(key, {"type": "sector", "center": self._key(center), "r1": r1, "r2": r2, "t1": t1, "t2": t2,
                        "fill": bool(fill)}, style, label)
        return (r2 * r2 - r1 * r1) * (t2 - t1) / 2

    def angle(self, key, a, vertex, b, style="current", label=None):
        """The angle at `vertex` from a to b, marked with an arc; returns it in degrees."""
        (ax, ay), (vx, vy), (bx, by) = self.at(a), self.at(vertex), self.at(b)
        vertex = self._key(vertex)
        t1, t2 = math.atan2(ay - vy, ax - vx), math.atan2(by - vy, bx - vx)
        sweep = (t2 - t1) % (2 * math.pi)
        if sweep > math.pi:
            t1, sweep = t2, 2 * math.pi - sweep
        self._put(key, {"type": "angle", "vertex": str(vertex), "start": t1, "sweep": sweep}, style, label)
        return math.degrees(sweep)

    def mark(self, key, style="current"):
        key = str(key)
        if key in self._items:
            self._items[key]["style"] = _style(style)
        elif key in self._points:
            self._points[key]["style"] = _style(style)

    def remove(self, key):
        self._items.pop(str(key), None)
        if str(key) in self._points:
            self._points.pop(str(key))
            for k in [k for k, it in self._items.items() if str(key) in (it.get("ends") or []) + (
                    it.get("points") or []) + [it.get("center"), it.get("vertex")]]:
                del self._items[k]

    def state(self):
        return {"kind": self.kind, "title": self.title, "points": copy.deepcopy(self._points),
                "items": copy.deepcopy(self._items)}


def axes(name, x=(-5, 5), y=None, title=None, xlabel="x", ylabel="y", equal=False):
    return Axes(name, x, y, title, xlabel, ylabel, equal)


def venn(name, sets, universe=None, title=None):
    return Venn(name, sets, universe, title)


def geometry(name, title=None):
    return Geometry(name, title)


def cells(name, values, title=None, index=True):
    return Cells(name, values, title, index)


def nodes(name, nodes=(), layout="tree", directed=False, title=None):
    return Nodes(name, nodes, layout, directed, title)


def code(name, lines, title=None):
    return Code(name, lines, title)


def container(name, capacity, level=0, title=None):
    return Container(name, capacity, level, title)


def snap(caption="", name=None):
    """Records the picture as it is now: one state the storyboard can show, by its name (p.show(snap=name))."""
    if len(_snaps) >= MAX_SNAPS:
        raise PictureError(f"at most {MAX_SNAPS} snapshots")
    name = str(len(_snaps)) if name is None else str(name)
    if any(s["name"] == name for s in _snaps):
        raise PictureError(f"two snapshots are named {name!r}; give each its own name")
    _snaps.append({"caption": str(caption), "name": name, "views": {k: v.state() for k, v in _views.items()}})


MATH = {k: getattr(math, k) for k in ("sin", "cos", "tan", "asin", "acos", "atan", "atan2", "exp", "log", "log2",
                                       "log10", "sqrt", "floor", "ceil", "pi", "e", "hypot", "radians", "degrees",
                                       "factorial", "comb", "perm", "gcd")}

EXPORTS = {"INF": float("inf"), "cells": cells, "nodes": nodes, "code": code, "container": container, "snap": snap,
           "axes": axes, "venn": venn, "geometry": geometry, "derivative": derivative, "integral": integral,
           "root": root, "Fraction": Fraction, "PictureError": PictureError, **MATH}


def reset() -> None:
    _views.clear()
    _snaps.clear()


def snapshots() -> list[dict]:
    return list(_snaps)
