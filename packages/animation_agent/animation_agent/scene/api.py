"""
What a picture program can call (plan/scene-grammar-plan.md). Pure Python, no Manim: it runs inside the sandbox
(scene/sandbox.py), and the state it records is drawn by scene/draw.py.

A program makes up to MAX_VIEWS views (cells, nodes, code, container), changes them as the algorithm runs, and calls
snap("what this picture shows") after each step it wants seen. Each snap() records every view's whole state; the
storyboard steps through the snapshots one beat at a time, and the engine animates the change between two of them
by object identity (a node key, a cell index), so a node that moved slides and a recoloured cell recolours.

Styles are words, not colours: STYLES lists them. The engine maps them to colours that pass the contrast rules.
"""

from __future__ import annotations

import copy

MAX_VIEWS = 3
MAX_SNAPS = 40
MAX_NODES = 15
MAX_CELLS = 12
MAX_CODE_LINES = 6
MAX_LABEL = 2  # characters in a node or cell: "10" is 0.35 units wide at the minimum font
MAX_TITLE = 18
STYLES = ("current", "visited", "found", "compare", "red", "grey", "new")
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


EXPORTS = {"INF": float("inf"), "cells": cells, "nodes": nodes, "code": code, "container": container, "snap": snap,
           "PictureError": PictureError}


def reset() -> None:
    _views.clear()
    _snaps.clear()


def snapshots() -> list[dict]:
    return list(_snaps)
