"""
What a picture program can call (plan/scene-grammar-plan.md). Pure Python, no Manim: it runs inside the sandbox
(scene/sandbox.py), and the state it records is drawn by scene/draw.py.

A program makes up to MAX_VIEWS views (cells, nodes, code, container; for math: axes, venn, geometry, numberline,
surface; diagrams: grid, flow, timeline, sequence, circuit, memory), changes them
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
        if title is not None and len(str(title)) > MAX_TITLE:
            # left out, not refused: in runs/picture-p4 a 20-character title refused a whole picture, and the
            # redraw lost it (the lines say what a title would)
            title = None
        self.name, self.title = name, None if title is None else str(title)
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
    return label if len(label) <= MAX_MATH_LABEL else None  # too long to sit beside a curve: left out


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

    def __init__(self, name, x=None, y=None, title=None, xlabel="x", ylabel="y", equal=False):
        super().__init__(name, title)
        self.x = None if x is None else [_num(x[0]), _num(x[1])]  # None: fitted to what is drawn (bars, points)
        if self.x is not None and not self.x[0] < self.x[1]:
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

    def _xrange(self, x=None, what="this"):
        if x is not None:
            return [_num(x[0]), _num(x[1])]
        if self.x is None:
            raise PictureError(f"{self.name}: give the axes an x range (axes(name, x=(lo, hi))) to draw {what}")
        return self.x

    def plot(self, key, f, style=None, label=None, x=None):
        lo, hi = self._xrange(x, "a curve")
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
        xr = self._xrange(None, "a tangent")
        half = (xr[1] - xr[0]) / 4 if half is None else _num(half)
        self.line(key, (x0 - half, y0 - m * half), (x0 + half, y0 + m * half), style, label)
        return m

    def point(self, key, x, y, label=None, style="current"):
        self._put(key, {"type": "point", "at": [_num(x), _num(y)]}, style, label)

    def field(self, key, F, n=7, style="blue"):
        """Arrows of the vector field F(x, y) -> (u, v) on an n x n grid (lengths scaled to the largest)."""
        n = max(3, min(int(n), 9))
        y = self.y or self._xrange(None, "a field")
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
        y = self.y or self._xrange(None, "a level curve")
        lines = _marching_squares(F, self.x, y, _num(level))
        if not lines:
            raise PictureError(f"{self.name}: F never equals {level} on these axes")
        self._put(key, {"type": "curve", "pieces": lines}, style, label)

    def bars(self, key, heights, x=None, labels=None, width=0.8, style="visited", values=False):
        """A bar for each height, at x (default 1, 2, 3...), `width` wide; `labels` names each bar on the x-axis
        (a bar chart of categories, each name at most 8 characters); values=True writes each height above its bar.
        Returns the total of the heights."""
        heights = [_num(h) for h in heights]
        if not 1 <= len(heights) <= MAX_RECTS:
            raise PictureError(f"{self.name}: 1-{MAX_RECTS} bars")
        xs = [float(i + 1) for i in range(len(heights))] if x is None else [_num(v) for v in x]
        if len(xs) != len(heights):
            raise PictureError(f"{self.name}: {key}: {len(heights)} heights but {len(xs)} x positions")
        names = None
        if labels is not None:
            names = [str(n).strip() for n in labels]
            if len(names) != len(heights) or any(len(n) > MAX_MATH_LABEL for n in names):
                raise PictureError(f"{self.name}: {key}: one label per bar, each at most {MAX_MATH_LABEL} characters")
        w = _num(width) * (min(b - a for a, b in zip(sorted(xs), sorted(xs)[1:])) if len(xs) > 1 else 1.0)
        shown = [f"{h:g}" if len(f"{h:g}") <= 6 else f"{h:.3g}" for h in heights] if values else None
        self._put(key, {"type": "bars", "bars": [[cx - w / 2, cx + w / 2, h] for cx, h in zip(xs, heights)],
                        "names": names, "values": shown}, style)
        return sum(heights)

    def histogram(self, key, data, bins=8, range=None, style="visited", values=False):
        """Bars counting how many of `data` fall in each of `bins` equal bins over `range` (default: the data's
        own); returns the counts."""
        data = [_num(v) for v in data]
        if not data:
            raise PictureError(f"{self.name}: {key}: no data")
        lo, hi = (min(data), max(data)) if range is None else (_num(range[0]), _num(range[1]))
        bins = max(1, min(int(bins), MAX_RECTS))
        hi = hi if hi > lo else lo + 1
        w = (hi - lo) / bins
        counts = [0] * bins
        for v in data:
            if lo <= v <= hi:
                counts[min(int((v - lo) / w), bins - 1)] += 1
        self._put(key, {"type": "bars", "bars": [[lo + i * w, lo + (i + 1) * w, c] for i, c in enumerate(counts)],
                        "names": None, "values": [str(c) for c in counts] if values else None}, style)
        return counts

    def points(self, key, xs, ys, style="current", label=None):
        """A scatter of points (x, y), one thing however many points."""
        pts = [[_num(a), _num(b)] for a, b in zip(xs, ys)]
        if not 1 <= len(pts) <= 60:
            raise PictureError(f"{self.name}: 1-60 points in one scatter")
        self._put(key, {"type": "points", "at": pts}, style, label)

    def vector(self, key, x, y, origin=(0, 0), style=None, label=None):
        """An arrow from `origin` to origin + (x, y) (a vector, a basis vector, its image under a matrix)."""
        ox, oy = _num(origin[0]), _num(origin[1])
        self._put(key, {"type": "vector", "points": [[ox, oy], [ox + _num(x), oy + _num(y)]]}, style, label)

    def polygon(self, key, points, style=None, fill=True, label=None):
        """The polygon through the (x, y) points, shaded (fill=False: its outline only)."""
        pts = [[_num(p[0]), _num(p[1])] for p in points]
        if len(pts) < 3:
            raise PictureError(f"{self.name}: {key}: a polygon needs at least 3 points")
        self._put(key, {"type": "polygon", "points": pts, "fill": bool(fill)}, style, label)

    def curve(self, key, fx, fy, t=(0, 1), style=None, label=None):
        """The parametric curve (fx(t), fy(t)) for t from t[0] to t[1] (a circle, a cycloid, a path)."""
        lo, hi = _num(t[0]), _num(t[1])
        pieces, cur = [], []
        for i in range(SAMPLES * 2 + 1):
            s = lo + (hi - lo) * i / (SAMPLES * 2)
            x, y = _value(fx, s), _value(fy, s)
            if x is None or y is None:
                if len(cur) > 1:
                    pieces.append(cur)
                cur = []
                continue
            cur.append([x, y])
        if len(cur) > 1:
            pieces.append(cur)
        if not pieces:
            raise PictureError(f"{self.name}: {key} is undefined everywhere on t = {lo:g}..{hi:g}")
        self._put(key, {"type": "curve", "pieces": pieces}, style, label)

    def polar(self, key, r, t=(0, 2 * math.pi), style=None, label=None):
        """The polar curve r = r(theta) for theta from t[0] to t[1]."""
        self.curve(key, lambda s: r(s) * math.cos(s), lambda s: r(s) * math.sin(s), t, style, label)

    def grid(self, key, matrix=None, step=1, style="grey"):
        """The lines x = k*step and y = k*step across the axes, each point sent through `matrix` [[a, b], [c, d]]
        when given (what a linear map does to the plane). A background: labels may sit on it."""
        if self.x is None or self.y is None:
            raise PictureError(f"{self.name}: give the axes x and y ranges to draw a grid")
        step = _num(step)
        if step <= 0:
            raise PictureError(f"{self.name}: a grid's step must be positive")
        (a, b), (c, d) = ((1, 0), (0, 1)) if matrix is None else ((_num(matrix[0][0]), _num(matrix[0][1])),
                                                                   (_num(matrix[1][0]), _num(matrix[1][1])))
        span = max(abs(v) for v in self.x + self.y)
        k = int(span / step) + 1
        if 2 * k + 1 > 41:
            raise PictureError(f"{self.name}: a grid of step {step:g} has too many lines; use a larger step")
        lines = []
        for i in range(-k, k + 1):
            for p, q in (((i * step, -k * step), (i * step, k * step)), ((-k * step, i * step), (k * step, i * step))):
                lines.append([[a * p[0] + b * p[1], c * p[0] + d * p[1]], [a * q[0] + b * q[1], c * q[0] + d * q[1]]])
        self._put(key, {"type": "grid", "pieces": lines}, style)

    def mark(self, key, style="current"):
        if str(key) in self._items:
            self._items[str(key)]["style"] = _style(style)

    def remove(self, key):
        self._items.pop(str(key), None)

    def state(self):
        return {"kind": self.kind, "title": self.title, "x": None if self.x is None else list(self.x),
                "y": None if self.y is None else
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


class NumberLine(_View):
    """A number line from lo to hi (ticks every `step`, or at round numbers): points on it, intervals along it
    (closed or open ends), and jumps between two numbers drawn as arcs (counting by 7s, a gcd's steps)."""

    kind = "numberline"

    def __init__(self, name, lo, hi, step=None, title=None):
        super().__init__(name, title)
        self.lo, self.hi = _num(lo), _num(hi)
        if not self.lo < self.hi:
            raise PictureError(f"{name}: the line must run from low to high")
        self.step = None if step is None else _num(step)
        if self.step is not None and not 0 < self.step <= self.hi - self.lo:
            raise PictureError(f"{name}: step must be positive and at most hi - lo")
        self._items: dict[str, dict] = {}

    def _put(self, key, item, style, label=None):
        key = str(key)
        if key not in self._items and len(self._items) >= MAX_ITEMS * 2:
            raise PictureError(f"{self.name}: at most {MAX_ITEMS * 2} things on one number line")
        self._items[key] = {**item, "style": _style(style), "label": _math_label(label)}

    def _on(self, v):
        v = _num(v)
        if not self.lo - 1e-9 <= v <= self.hi + 1e-9:
            raise PictureError(f"{self.name}: {v:g} is off the line ({self.lo:g} to {self.hi:g})")
        return v

    def point(self, key, x, label=None, style="current"):
        self._put(key, {"type": "point", "x": self._on(x)}, style, label)

    def interval(self, key, a, b, closed=(True, True), style="visited", label=None):
        """The numbers from a to b, a solid dot at a closed end and a hollow one at an open end."""
        a, b = self._on(a), self._on(b)
        if not a < b:
            raise PictureError(f"{self.name}: an interval runs from low to high")
        self._put(key, {"type": "interval", "a": a, "b": b, "closed": [bool(closed[0]), bool(closed[1])]}, style,
                  label)

    def jump(self, key, a, b, label=None, style="compare"):
        """An arc from a to b above the line (a step of a count, a move)."""
        self._put(key, {"type": "jump", "a": self._on(a), "b": self._on(b)}, style, label)

    def mark(self, key, style="current"):
        if str(key) in self._items:
            self._items[str(key)]["style"] = _style(style)

    def remove(self, key):
        self._items.pop(str(key), None)

    def state(self):
        return {"kind": self.kind, "title": self.title, "lo": self.lo, "hi": self.hi, "step": self.step,
                "items": copy.deepcopy(self._items)}


class Surface(_View):
    """z = f(x, y) over a rectangle, seen from above and to the side (a fixed 3D view drawn flat): the surface
    itself, columns under it (the boxes of a double integral's sum) and points in space."""

    kind = "surface"
    MAX_GRID = 16
    MAX_COLUMNS = 8

    def __init__(self, name, x=(-2, 2), y=(-2, 2), z=None, title=None, xlabel="x", ylabel="y", zlabel="z"):
        super().__init__(name, title)
        self.x, self.y = [_num(x[0]), _num(x[1])], [_num(y[0]), _num(y[1])]
        if not (self.x[0] < self.x[1] and self.y[0] < self.y[1]):
            raise PictureError(f"{name}: x and y must each run from low to high")
        self.z = None if z is None else [_num(z[0]), _num(z[1])]
        self.labels = [_math_label(xlabel), _math_label(ylabel), _math_label(zlabel)]
        self._items: dict[str, dict] = {}

    def _put(self, key, item, style, label=None):
        key = str(key)
        if key not in self._items and len(self._items) >= MAX_ITEMS:
            raise PictureError(f"{self.name}: at most {MAX_ITEMS} things in one 3D view")
        self._items[key] = {**item, "style": _style(style), "label": _math_label(label)}

    def _z(self, f, x, y):
        v = _value(lambda q: f(q[0], q[1]), (x, y))
        if v is None:
            raise PictureError(f"{self.name}: f is undefined at ({x:g}, {y:g})")
        return v

    def plot(self, key, f, n=12, style="blue"):
        """The surface z = f(x, y), as an n x n grid of patches."""
        n = max(2, min(int(n), self.MAX_GRID))
        (x0, x1), (y0, y1) = self.x, self.y
        grid = [[self._z(f, x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n) for j in range(n + 1)]
                for i in range(n + 1)]
        self._put(key, {"type": "mesh", "n": n, "z": grid}, style)

    def columns(self, key, f, n=4, style="visited"):
        """n x n boxes standing on the rectangle, each as tall as f at its centre; returns their total volume
        (the double integral's Riemann sum)."""
        n = max(1, min(int(n), self.MAX_COLUMNS))
        (x0, x1), (y0, y1) = self.x, self.y
        w, d = (x1 - x0) / n, (y1 - y0) / n
        cols = [[x0 + i * w, x0 + (i + 1) * w, y0 + j * d, y0 + (j + 1) * d,
                 self._z(f, x0 + (i + 0.5) * w, y0 + (j + 0.5) * d)] for i in range(n) for j in range(n)]
        self._put(key, {"type": "columns", "columns": cols}, style)
        return sum(c[4] for c in cols) * w * d

    def point(self, key, x, y, z, label=None, style="current"):
        self._put(key, {"type": "point", "at": [_num(x), _num(y), _num(z)]}, style, label)

    def mark(self, key, style="current"):
        if str(key) in self._items:
            self._items[str(key)]["style"] = _style(style)

    def remove(self, key):
        self._items.pop(str(key), None)

    def state(self):
        return {"kind": self.kind, "title": self.title, "x": list(self.x), "y": list(self.y),
                "z": None if self.z is None else list(self.z), "labels": list(self.labels),
                "items": copy.deepcopy(self._items)}


# ---- diagrams (plan/scene-grammar-plan.md, P5): tables, boxes and arrows, timelines, message sequences, logic
# circuits and memory. Their layouts are in scene/diagram_layout.py.

MAX_GRID_ROWS = 8
MAX_GRID_COLS = 8
MAX_WORD = 6  # characters in a table entry, a header, a timeline block or a memory value


def _word(v, limit: int = MAX_WORD, what: str = "an entry") -> str:
    """A short text for a table entry, a header or a value: None is blank, a float shows as %g, INF as ∞."""
    if v is None:
        return ""
    if isinstance(v, bool):
        s = str(int(v))
    elif isinstance(v, float):
        s = INFINITY if v == float("inf") else ("-" + INFINITY if v == float("-inf") else f"{v:g}")
        if len(s) > limit:
            s = f"{v:.3g}"
    else:
        s = INFINITY if v in ("INF", "inf", "Infinity") else str(v)
    if len(s) > limit:
        raise PictureError(f"{what} {s!r} is longer than {limit} characters")
    return s


class _Row:
    """One row of a grid, so g[r][c] reads and writes as in a list of lists."""

    def __init__(self, grid: Grid, r: int):
        self._grid, self._r = grid, r

    def __getitem__(self, c):
        return self._grid._raw[self._r][c]

    def __setitem__(self, c, v):
        self._grid[self._r, c] = v

    def __len__(self):
        return self._grid.cols

    def __iter__(self):
        return iter(list(self._grid._raw[self._r]))


class Grid(_View):
    """A table of rows and columns (a matrix, a DP table, a truth table, a database table, an adjacency matrix).
    g[r][c] or g[r, c] reads and writes an entry (None: blank); headers name the rows and columns."""

    kind = "grid"

    def __init__(self, name, rows, row_names=None, col_names=None, title=None, matrix=False):
        super().__init__(name, title)
        rows = [list(r) for r in rows]
        if not 1 <= len(rows) <= MAX_GRID_ROWS:
            raise PictureError(f"{name}: 1-{MAX_GRID_ROWS} rows")
        widths = {len(r) for r in rows}
        if len(widths) != 1 or not 1 <= widths.pop() <= MAX_GRID_COLS:
            raise PictureError(f"{name}: every row needs the same number of entries, 1-{MAX_GRID_COLS}")
        self._raw = rows
        for r in rows:
            for v in r:
                _word(v)
        self.rows, self.cols = len(rows), len(rows[0])
        self.row_names = None if row_names is None else [_word(v, what="a row name") for v in row_names]
        self.col_names = None if col_names is None else [_word(v, what="a column name") for v in col_names]
        if self.row_names is not None and len(self.row_names) != self.rows:
            raise PictureError(f"{name}: {self.rows} rows but {len(self.row_names)} row names")
        if self.col_names is not None and len(self.col_names) != self.cols:
            raise PictureError(f"{name}: {self.cols} columns but {len(self.col_names)} column names")
        self.matrix = bool(matrix)
        self._marks: dict[tuple[int, int], str] = {}

    def _rc(self, rc):
        r, c = rc
        if not (-self.rows <= r < self.rows and -self.cols <= c < self.cols):
            raise PictureError(f"{self.name}: no entry ({r}, {c}) in a {self.rows} x {self.cols} table")
        return r % self.rows, c % self.cols

    def __getitem__(self, key):
        if isinstance(key, tuple):
            r, c = self._rc(key)
            return self._raw[r][c]
        return _Row(self, self._rc((key, 0))[0])

    def __setitem__(self, key, v):
        r, c = self._rc(key)
        _word(v)
        self._raw[r][c] = v

    def __len__(self):
        return self.rows

    def row(self, r):
        return list(self._raw[self._rc((r, 0))[0]])

    def col(self, c):
        c = self._rc((0, c))[1]
        return [row[c] for row in self._raw]

    def mark(self, r, c, style="current"):
        self._marks[self._rc((r, c))] = _style(style)

    def mark_row(self, r, style="current"):
        for c in range(self.cols):
            self.mark(r, c, style)

    def mark_col(self, c, style="current"):
        for r in range(self.rows):
            self.mark(r, c, style)

    def unmark(self, r=None, c=None):
        for k in [k for k in self._marks if (r is None or k[0] == r % self.rows) and (c is None or k[1] == c % self.cols)]:
            del self._marks[k]

    def state(self):
        return {"kind": self.kind, "title": self.title, "values": [[_word(v) for v in r] for r in self._raw],
                "row_names": self.row_names, "col_names": self.col_names, "matrix": self.matrix,
                "marks": {f"{r},{c}": s for (r, c), s in self._marks.items()}}


def grid(name, rows, row_names=None, col_names=None, title=None, matrix=False):
    return Grid(name, rows, row_names, col_names, title, matrix)


SHAPES = ("box", "round", "diamond", "circle", "double", "cylinder", "document", "cloud", "person", "chip",
          "monitor", "lock", "server")
MAX_BOXES = 12
MAX_BOX_TEXT = 14  # characters in a line of a box's text (two lines at most)


def _box_text(text) -> str:
    lines = str(text).split("\n")
    if len(lines) > 2 or any(len(line) > MAX_BOX_TEXT for line in lines):
        raise PictureError(f"a box's text {str(text)!r} is more than 2 lines of {MAX_BOX_TEXT} characters")
    return "\n".join(line.strip() for line in lines)


class Flow(_View):
    """Labelled boxes joined by arrows, laid out in layers (direction 'down': top to bottom; 'right': left to
    right): a flowchart, a pipeline, a system's parts, a state machine with named states, a call or parse tree.
    A box's shape says what it is: box, round, diamond (a decision), circle, double (an accepting state), cylinder
    (a database or disk), document, cloud, and pictograms with the text under them: person, chip (a CPU), monitor
    (a computer), lock, server."""

    kind = "flow"

    def __init__(self, name, direction="down", title=None):
        super().__init__(name, title)
        if direction not in ("down", "right"):
            raise PictureError("direction must be 'down' or 'right'")
        self.direction = direction
        self._boxes: dict[str, dict] = {}
        self._arrows: dict[tuple[str, str], dict] = {}

    def box(self, key, text=None, shape="box", style=None, layer=None):
        key = str(key)
        if key not in self._boxes and len(self._boxes) >= MAX_BOXES:
            raise PictureError(f"{self.name}: at most {MAX_BOXES} boxes")
        if shape not in SHAPES:
            raise PictureError(f"unknown shape {shape!r}; use one of {', '.join(SHAPES)}")
        self._boxes[key] = {"text": _box_text(key if text is None else text), "shape": shape, "style": _style(style),
                            "layer": None if layer is None else int(layer)}

    def text(self, key, text):
        """Changes what a box says (a variable's new value, a state's new name)."""
        self._need(key)["text"] = _box_text(text)

    def _need(self, key):
        if str(key) not in self._boxes:
            raise PictureError(f"{self.name}: no box {key!r}; make it with box(key, text)")
        return self._boxes[str(key)]

    def arrow(self, a, b, label=None, style=None):
        self._need(a), self._need(b)
        label = None if label is None or not str(label).strip() else str(label).strip()
        if label is not None and len(label) > MAX_MATH_LABEL:
            raise PictureError(f"an arrow's label {label!r} is longer than {MAX_MATH_LABEL} characters")
        self._arrows[(str(a), str(b))] = {"label": label, "style": _style(style)}

    def unarrow(self, a, b):
        self._arrows.pop((str(a), str(b)), None)

    def restyle(self, a, b, style):
        """Colours the arrow a -> b (the transition taken, the path followed)."""
        if (str(a), str(b)) in self._arrows:
            self._arrows[(str(a), str(b))]["style"] = _style(style)

    def mark(self, key, style="current"):
        self._need(key)["style"] = _style(style)

    def unmark(self, key=None):
        for k, b in self._boxes.items():
            if key is None or k == str(key):
                b["style"] = None
        if key is None:
            for d in self._arrows.values():
                d["style"] = None

    def remove(self, key):
        key = str(key)
        self._boxes.pop(key, None)
        for e in [e for e in self._arrows if key in e]:
            del self._arrows[e]

    def state(self):
        return {"kind": self.kind, "title": self.title, "direction": self.direction,
                "boxes": copy.deepcopy(self._boxes),
                "arrows": [[a, b, d["style"], d["label"]] for (a, b), d in self._arrows.items()]}


def flow(name, direction="down", title=None):
    return Flow(name, direction, title)


MAX_LANES = 6
MAX_BLOCKS = 24


class Timeline(_View):
    """Lanes along a time axis, with blocks in them (a CPU schedule, a Gantt chart, a pipeline's stages, a
    process's states over time) and markers at moments (a deadline, an arrival)."""

    kind = "timeline"

    def __init__(self, name, lanes, t=None, step=None, title=None):
        super().__init__(name, title)
        self.lanes = [str(x).strip() for x in lanes]
        if not 1 <= len(self.lanes) <= MAX_LANES:
            raise PictureError(f"{name}: 1-{MAX_LANES} lanes")
        if any(len(x) > MAX_MATH_LABEL for x in self.lanes):
            raise PictureError(f"{name}: a lane's name is at most {MAX_MATH_LABEL} characters")
        self.t = None if t is None else [_num(t[0]), _num(t[1])]
        if self.t is not None and not self.t[0] < self.t[1]:
            raise PictureError(f"{name}: t must run from low to high")
        self.step = None if step is None else _num(step)
        self._items: dict[str, dict] = {}

    def _lane(self, lane) -> int:
        if isinstance(lane, int) and 0 <= lane < len(self.lanes):
            return lane
        if str(lane) in self.lanes:
            return self.lanes.index(str(lane))
        raise PictureError(f"{self.name}: no lane {lane!r}; the lanes are {', '.join(self.lanes)}")

    def _put(self, key, item, style, label):
        key = str(key)
        if key not in self._items and len(self._items) >= MAX_BLOCKS:
            raise PictureError(f"{self.name}: at most {MAX_BLOCKS} blocks and markers")
        label = None if label is None or not str(label).strip() else _word(str(label).strip(), MAX_MATH_LABEL,
                                                                             "a label")
        self._items[key] = {**item, "style": _style(style), "label": label}

    def block(self, key, lane, start, end, label=None, style=None):
        """A block in `lane` from `start` to `end` (its label is written inside it when it fits)."""
        a, b = _num(start), _num(end)
        if not a < b:
            raise PictureError(f"{self.name}: {key}: a block ends after it starts")
        self._put(key, {"type": "block", "lane": self._lane(lane), "a": a, "b": b}, style, label)

    def marker(self, key, t, label=None, style="current"):
        """A line across every lane at time t, labelled above them."""
        self._put(key, {"type": "marker", "t": _num(t)}, style, label)

    def mark(self, key, style="current"):
        if str(key) in self._items:
            self._items[str(key)]["style"] = _style(style)

    def remove(self, key):
        self._items.pop(str(key), None)

    def state(self):
        return {"kind": self.kind, "title": self.title, "lanes": list(self.lanes),
                "t": None if self.t is None else list(self.t), "step": self.step, "items": copy.deepcopy(self._items)}


def timeline(name, lanes, t=None, step=None, title=None):
    return Timeline(name, lanes, t, step, title)


MAX_ACTORS = 4
MAX_MESSAGES = 10
MAX_MESSAGE_LABEL = 14


class Sequence(_View):
    """Actors side by side, each with a lifeline down the page, and messages between them in time order (a
    protocol's handshake, a client and a server, threads and a lock). Each message gets its own row, in the order
    the program first sends it."""

    kind = "sequence"

    def __init__(self, name, actors, title=None):
        super().__init__(name, title)
        self.actors = [str(a).strip() for a in actors]
        if not 2 <= len(self.actors) <= MAX_ACTORS:
            raise PictureError(f"{name}: 2-{MAX_ACTORS} actors")
        if any(len(a) > MAX_MATH_LABEL for a in self.actors) or len(set(self.actors)) != len(self.actors):
            raise PictureError(f"{name}: each actor has its own name of at most {MAX_MATH_LABEL} characters")
        self._messages: dict[str, dict] = {}
        self._rows = 0

    def _actor(self, a) -> int:
        if str(a) in self.actors:
            return self.actors.index(str(a))
        if isinstance(a, int) and 0 <= a < len(self.actors):
            return a
        raise PictureError(f"{self.name}: no actor {a!r}; the actors are {', '.join(self.actors)}")

    def message(self, key, a, b, label=None, style=None, dashed=False):
        """An arrow from actor a's lifeline to b's (a == b: to itself), below the messages before it; dashed for a
        reply."""
        key = str(key)
        old = self._messages.get(key)
        if old is None:
            if self._rows >= MAX_MESSAGES:
                raise PictureError(f"{self.name}: at most {MAX_MESSAGES} messages")
            row = self._rows
            self._rows += 1
        else:
            row = old["row"]
        label = None if label is None or not str(label).strip() else str(label).strip()
        if label is not None and len(label) > MAX_MESSAGE_LABEL:
            raise PictureError(f"a message's label {label!r} is longer than {MAX_MESSAGE_LABEL} characters")
        self._messages[key] = {"a": self._actor(a), "b": self._actor(b), "label": label, "style": _style(style),
                               "dashed": bool(dashed), "row": row}

    def mark(self, key, style="current"):
        if str(key) in self._messages:
            self._messages[str(key)]["style"] = _style(style)

    def remove(self, key):
        self._messages.pop(str(key), None)

    def state(self):
        return {"kind": self.kind, "title": self.title, "actors": list(self.actors),
                "messages": copy.deepcopy(self._messages)}


def sequence(name, actors, title=None):
    return Sequence(name, actors, title)


GATES = ("AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR", "BUF")
MAX_PARTS = 14


def _gate_value(kind: str, ins: list[int]) -> int:
    if kind in ("NOT", "BUF"):
        if len(ins) != 1:
            raise PictureError(f"a {kind} gate takes one input")
        return 1 - ins[0] if kind == "NOT" else ins[0]
    if len(ins) < 2:
        raise PictureError(f"an {kind} gate takes two or more inputs")
    base = {"AND": all(ins), "NAND": all(ins), "OR": any(ins), "NOR": any(ins), "XOR": sum(ins) % 2 == 1,
            "XNOR": sum(ins) % 2 == 1}[kind]
    return int(bool(base) != (kind in ("NAND", "NOR", "XNOR")))


class Circuit(_View):
    """A logic circuit: inputs on the left, gates in columns by depth, outputs on the right. Every wire carries
    the value code works out from the inputs (1 lit, 0 dim), so set() an input and snap() to show what changes."""

    kind = "circuit"

    def __init__(self, name, title=None):
        super().__init__(name, title)
        self._parts: dict[str, dict] = {}

    def _add(self, key, part):
        key = str(key)
        if key not in self._parts and len(self._parts) >= MAX_PARTS:
            raise PictureError(f"{self.name}: at most {MAX_PARTS} inputs, gates and outputs")
        label = part.get("label")
        if label is not None and len(str(label)) > 4:
            raise PictureError(f"{self.name}: a label is at most 4 characters ({label!r})")
        self._parts[key] = part

    def input(self, key, value=0, label=None):
        self._add(key, {"type": "input", "value": 1 if value else 0, "label": str(key if label is None else label),
                        "style": None})

    def gate(self, key, kind, inputs, label=None):
        kind = str(kind).upper()
        if kind not in GATES:
            raise PictureError(f"unknown gate {kind!r}; use one of {', '.join(GATES)}")
        ins = [str(i) for i in inputs]
        for i in ins:
            if i not in self._parts or self._parts[i]["type"] == "output":
                raise PictureError(f"{self.name}: {key}'s input {i!r} is not an input or gate made before it")
        _gate_value(kind, [0] * len(ins))  # refuses the wrong number of inputs
        if len(ins) > 4:
            raise PictureError(f"{self.name}: a gate takes at most 4 inputs")
        self._add(key, {"type": "gate", "gate": kind, "inputs": ins, "label": None if label is None else str(label),
                        "style": None})

    def output(self, key, source, label=None):
        if str(source) not in self._parts or self._parts[str(source)]["type"] == "output":
            raise PictureError(f"{self.name}: output {key}'s source {source!r} is not an input or gate")
        self._add(key, {"type": "output", "inputs": [str(source)], "label": str(key if label is None else label),
                        "style": None})

    def set(self, key, value):
        if str(key) not in self._parts or self._parts[str(key)]["type"] != "input":
            raise PictureError(f"{self.name}: {key!r} is not an input")
        self._parts[str(key)]["value"] = 1 if value else 0

    def value(self, key) -> int:
        return self._values()[str(key)]

    def _values(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for k, p in self._parts.items():  # each part made after its inputs, so one pass in order
            if p["type"] == "input":
                out[k] = p["value"]
            elif p["type"] == "gate":
                out[k] = _gate_value(p["gate"], [out[i] for i in p["inputs"]])
            else:
                out[k] = out[p["inputs"][0]]
        return out

    def mark(self, key, style="current"):
        if str(key) in self._parts:
            self._parts[str(key)]["style"] = _style(style)

    def unmark(self, key=None):
        for k, p in self._parts.items():
            if key is None or k == str(key):
                p["style"] = None

    def state(self):
        return {"kind": self.kind, "title": self.title, "parts": copy.deepcopy(self._parts), "values": self._values()}


def circuit(name, title=None):
    return Circuit(name, title)


class Ref:
    """A pointer to a heap object (memory.ref(key)): a field holding one is drawn as an arrow to it."""

    def __init__(self, key):
        self.key = str(key)

    def __eq__(self, other):
        return isinstance(other, Ref) and other.key == self.key

    def __repr__(self):
        return f"ref({self.key!r})"


MAX_FRAMES = 4
MAX_OBJECTS = 4
MAX_FIELDS = 5


class Memory(_View):
    """Memory as boxes: stack frames down the left (the call stack, newest at the bottom), heap objects down the
    right, each a list of named fields. A field holding m.ref(key) is drawn as an arrow to that object (a pointer,
    a reference, a linked list's next)."""

    kind = "memory"

    def __init__(self, name, title=None):
        super().__init__(name, title)
        self._boxes: dict[str, dict] = {}

    def _new(self, key, title, area):
        key = str(key)
        if key in self._boxes:
            raise PictureError(f"{self.name}: there is already a frame or object {key!r}")
        n = sum(1 for b in self._boxes.values() if b["area"] == area)
        if n >= (MAX_FRAMES if area == "stack" else MAX_OBJECTS):
            raise PictureError(f"{self.name}: at most {MAX_FRAMES} stack frames and {MAX_OBJECTS} heap objects")
        title = key if title is None else str(title)
        if len(title) > 10:
            raise PictureError(f"{self.name}: a frame's or object's title is at most 10 characters ({title!r})")
        self._boxes[key] = {"title": title, "area": area, "fields": {}, "style": None}

    def frame(self, key, title=None):
        """A stack frame (a call: 'main', 'f(3)')."""
        self._new(key, title, "stack")

    def obj(self, key, title=None):
        """An object on the heap (a node, an array, an instance)."""
        self._new(key, title, "heap")

    def ref(self, key) -> Ref:
        return Ref(key)

    def _box(self, key):
        if str(key) not in self._boxes:
            raise PictureError(f"{self.name}: no frame or object {key!r}")
        return self._boxes[str(key)]

    def set(self, box, name, value):
        """Field `name` of a frame or object now holds `value` (a short value, None for blank, or m.ref(key))."""
        b = self._box(box)
        name = str(name)
        if len(name) > MAX_WORD:
            raise PictureError(f"{self.name}: a field's name is at most {MAX_WORD} characters ({name!r})")
        if name not in b["fields"] and len(b["fields"]) >= MAX_FIELDS:
            raise PictureError(f"{self.name}: at most {MAX_FIELDS} fields in a frame or object")
        if not isinstance(value, Ref):
            _word(value, what="a value")
        old = b["fields"].get(name)
        b["fields"][name] = {"value": value, "style": None if old is None else old["style"]}

    def get(self, box, name):
        f = self._box(box)["fields"].get(str(name))
        if f is None:
            raise PictureError(f"{self.name}: {box} has no field {name!r}")
        return f["value"]

    def unset(self, box, name):
        self._box(box)["fields"].pop(str(name), None)

    def remove(self, key):
        """Pops a frame or frees an object."""
        self._boxes.pop(str(key), None)

    def mark(self, box, name=None, style="current"):
        b = self._box(box)
        if name is None:
            b["style"] = _style(style)
        elif str(name) in b["fields"]:
            b["fields"][str(name)]["style"] = _style(style)

    def unmark(self, box=None):
        for k, b in self._boxes.items():
            if box is None or k == str(box):
                b["style"] = None
                for f in b["fields"].values():
                    f["style"] = None

    def state(self):
        boxes = {}
        for k, b in self._boxes.items():
            fields = []
            for name, f in b["fields"].items():
                v = f["value"]
                if isinstance(v, Ref):
                    if v.key not in self._boxes or self._boxes[v.key]["area"] != "heap":
                        raise PictureError(f"{self.name}: {k}.{name} points to {v.key!r}, which is not a heap object")
                    fields.append([name, "", v.key, f["style"]])
                else:
                    fields.append([name, _word(v), None, f["style"]])
            boxes[k] = {"title": b["title"], "area": b["area"], "fields": fields, "style": b["style"]}
        return {"kind": self.kind, "title": self.title, "boxes": boxes}


def memory(name, title=None):
    return Memory(name, title)


def surface(name, x=(-2, 2), y=(-2, 2), z=None, title=None, xlabel="x", ylabel="y", zlabel="z"):
    return Surface(name, x, y, z, title, xlabel, ylabel, zlabel)


def numberline(name, lo, hi, step=None, title=None):
    return NumberLine(name, lo, hi, step, title)


def axes(name, x=None, y=None, title=None, xlabel="x", ylabel="y", equal=False):
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
           "axes": axes, "venn": venn, "geometry": geometry, "numberline": numberline, "surface": surface,
           "grid": grid, "flow": flow, "timeline": timeline, "sequence": sequence, "circuit": circuit,
           "memory": memory, "derivative": derivative, "integral": integral, "root": root, "Fraction": Fraction,
           "PictureError": PictureError, **MATH}


def reset() -> None:
    _views.clear()
    _snaps.clear()


def snapshots() -> list[dict]:
    return list(_snaps)
