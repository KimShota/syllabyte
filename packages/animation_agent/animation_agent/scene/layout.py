"""
Where everything in a picture program's snapshots goes. Pure Python (numpy, networkx), no Manim.

One layout for the whole program, not one per snapshot: each view gets a fixed band of the area (views stack top
to bottom in the order the program made them; containers made one after another share a row), and nodes and cells
keep one size throughout, so nothing grows or shrinks between steps. Positions then change only when the
structure does, and the drawing animates exactly that.

Sizes are in scene units for the 4.5-unit-wide portrait frame and keep text at the layout audit's minimum font.

The main picture gets the room (runs/picture-p1, Bellman-Ford: a 4-node graph was squeezed into a band 1.6 units
tall above an array and a code panel that had grown to fill theirs, and its arrows and weights piled up): arrays
and code panels take their compact readable size first, a node view or container takes the rest up to what it can
use, and only then do arrays grow. A graph is drawn as large as it can be legibly: its nodes try radii from large
to small, and a layout is kept only when no two nodes crowd, no link passes near a node it doesn't join, no two
links leave a node at nearly the same angle, and every label sits clear of every node, link and other label
inside its own band; of those, the fewest crossing links, then the largest nodes, win.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from animation_agent.scene.api import PictureError

NODE_R = 0.2  # the smallest node: "10" at the minimum font just fits
NODE_UNIT = 0.48  # the least horizontal room per leaf
MAX_UNIT = 0.8
MAX_R = 0.3
TREE_GAP = 0.5  # leaf units between the trees of a forest
LEVEL_H = 0.62
MIN_LEVEL_H = 0.46
MAX_LEVEL_H = 0.95
GRAPH_R = 0.2  # the same as a tree node: two characters fit at the minimum font
CELL = 0.46
MIN_CELL = 0.36
MAX_CELL = 0.72  # a short row grows to this (the font with it), so the picture uses its room
INDEX_H = 0.3
POINTER_H = 0.32
TITLE_H = 0.38
CODE_LINE_H = 0.48
CODE_CHAR_W = 0.245  # Menlo at the minimum font (30), measured: about 15 characters across the frame
CONTAINER_H = 2.0
GAP = 0.14
MAIN_ROOM = 2.0  # below this much height for its drawing, a diagram's title gives way to it


@dataclass
class Region:
    cx: float
    top: float
    w: float
    h: float

    @property
    def bottom(self) -> float:
        return self.top - self.h


def _title(views: list[dict]) -> float:
    return TITLE_H if any(v.get("title") for v in views) else 0.0


def pointer_rows(views: list[dict]) -> int:
    """The most pointers any snapshot puts under one cell: they stack, one row each."""
    most = 0
    for v in views:
        per: dict[int, int] = {}
        for i in v["pointers"].values():
            per[i] = per.get(i, 0) + 1
        most = max(most, max(per.values(), default=0))
    return most


def _cells_height(views: list[dict], cell: float) -> float:
    return _title(views) + cell + (INDEX_H if views[0]["index"] else 0.0) + POINTER_H * pointer_rows(views)


CONTAINER_LABEL_H = 0.42
CONTAINER_MAX = 3.2  # the tallest vessel


def _heights(kind: str, views: list[dict], width: float) -> tuple[float, float]:
    """The least height a view can be drawn legibly in, and the most it can use."""
    title = _title(views)
    if kind == "cells":
        n = max(len(v["values"]) for v in views)
        most = min(MAX_CELL, width / n)
        return _cells_height(views, min(CELL, most)), _cells_height(views, most)
    if kind == "code":
        h = title + CODE_LINE_H * max(len(v["lines"]) for v in views)
        return h, h
    if kind == "container":
        return title + CONTAINER_H, title + 0.1 + CONTAINER_LABEL_H + CONTAINER_MAX
    if kind in MATH_KINDS:
        return _view_layouts()[kind][0](views, width, title)
    if views[0]["layout"] == "graph":
        return title + LEVEL_H, title + width  # about square at most: taller only stretches the links
    _unit, _gap, levels = _tree_shape(views, width)
    level_h = LABELLED_LEVEL_H if _labelled(views) else MAX_LEVEL_H
    return title + LEVEL_H, title + (levels - 1) * level_h + 2 * MAX_R + 0.1


def _fill(h: list[float], most: list[float], which: list[int], spare: float) -> float:
    """Shares `spare` equally among the bands `which`, none past its most; what is left."""
    open_ = [i for i in which if most[i] - h[i] > 1e-9]
    while spare > 1e-9 and open_:
        share = spare / len(open_)
        for i in list(open_):
            add = min(share, most[i] - h[i])
            h[i] += add
            spare -= add
            if most[i] - h[i] <= 1e-9:
                open_.remove(i)
    return spare


_WHAT = {"cells": "an array", "code": "the code panel", "container": "a container", "nodes": "the diagram",
         "axes": "the axes", "venn": "the Venn diagram", "geometry": "the figure", "numberline": "the number line",
         "surface": "the 3D view", "grid": "the table", "flow": "the flow diagram", "timeline": "the timeline",
         "sequence": "the message diagram", "circuit": "the circuit", "memory": "the memory diagram"}
# views laid out by their own module (scene/math_layout.py, scene/diagram_layout.py): (heights, layout) each
MATH_KINDS = ("axes", "venn", "geometry", "numberline", "surface", "grid", "flow", "timeline", "sequence", "circuit",
              "memory")
MAIN_KINDS = ("nodes", "container") + MATH_KINDS  # what gets the room first


def _view_layouts() -> dict:
    from animation_agent.scene import diagram_layout as D
    from animation_agent.scene import math_layout as M

    return {"axes": (M.axes_heights, M.axes_layout), "venn": (M.venn_heights, M.venn_layout),
            "geometry": (M.geometry_heights, M.geometry_layout),
            "numberline": (M.numberline_heights, M.numberline_layout),
            "surface": (M.surface_heights, M.surface_layout), "grid": (D.grid_heights, D.grid_layout),
            "flow": (D.flow_heights, D.flow_layout), "timeline": (D.timeline_heights, D.timeline_layout),
            "sequence": (D.sequence_heights, D.sequence_layout), "circuit": (D.circuit_heights, D.circuit_layout),
            "memory": (D.memory_heights, D.memory_layout)}


def plan_regions(snaps: list[dict], width: float, height: float, top: float) -> dict[str, Region]:
    names = list(snaps[-1]["views"])
    for s in snaps:
        for n in s["views"]:
            if n not in names:
                names.append(n)
    by_name = {n: [s["views"][n] for s in snaps if n in s["views"]] for n in names}
    kinds = {n: by_name[n][0]["kind"] for n in names}

    # bands: consecutive containers share one
    bands: list[list[str]] = []
    for n in names:
        if bands and kinds[n] == "container" and all(kinds[m] == "container" for m in bands[-1]):
            bands[-1].append(n)
        else:
            bands.append([n])
    sizes = [[_heights(kinds[n], by_name[n], width / len(band)) for n in band] for band in bands]
    h = [max(lo for lo, _ in band) for band in sizes]
    most = [max(hi for _, hi in band) for band in sizes]
    spare = height - sum(h) - GAP * (len(bands) - 1)
    if spare < -1e-6:
        if len(names) == 1 and kinds[names[0]] in MATH_KINDS:  # one view too big: its own reason says what to cut
            try:
                _view_layouts()[kinds[names[0]]][1](by_name[names[0]], Region(0.0, top, width, height))
            except PictureError:
                raise
        need = ", ".join(f"{_WHAT[kinds[b[0]]]} {x:.1f}" for b, x in zip(bands, h))
        # a view that needs most of the frame by itself can't share it (runs/p5: a full adder's circuit with its
        # truth table, twice, and the video lost its picture): say so plainly
        alone = [(b, x) for b, x in zip(bands, h) if x > 0.7 * height]
        if alone and len(bands) > 1:
            band, x = max(alone, key=lambda bx: bx[1])  # the biggest: the one the rest must give way to
            what = _WHAT[kinds[band[0]]]
            raise PictureError(f"{what} needs {x:.1f} of the {height:.1f} units by itself, so it can't share the "
                               f"frame: draw {what} as the only view and let the lines say what the others would "
                               f"show (they need {need})")
        raise PictureError(f"these views don't fit on screen together: they need {sum(h):.1f} units of the "
                           f"{height:.1f} ({need}); use fewer or smaller ones")
    main = [i for i, band in enumerate(bands) if any(kinds[n] in MAIN_KINDS for n in band)]
    spare = _fill(h, most, main, spare)  # the main picture first
    spare = _fill(h, most, [i for i in range(len(bands)) if i not in main], spare)
    regions: dict[str, Region] = {}
    y = top - spare / 2  # what nothing can use centres the stack
    for band, bh in zip(bands, h):
        w = width / len(band)
        for j, n in enumerate(band):
            regions[n] = Region(-width / 2 + w * (j + 0.5), y, w, bh)
        y -= bh + GAP
    return regions


# ---- trees -------------------------------------------------------------------------------------------------


def _children(view: dict) -> tuple[dict[str, list], list[str]]:
    kids: dict[str, list] = {k: [] for k in view["nodes"]}
    has_parent = set()
    for order, (a, b, _style, _label, slot) in enumerate(view["links"]):
        if a in kids and b in view["nodes"]:
            kids[a].append((slot if slot is not None else order, order, b))
            has_parent.add(b)
    roots = [k for k in view["nodes"] if k not in has_parent]
    return kids, roots


def _tree_units(view: dict) -> list[tuple[str, dict[str, tuple[float, int]], float, int]]:
    """Each tree of the forest: (root, {node: (x in units from the tree's left, depth)}, width, depth)."""
    kids, roots = _children(view)
    binary = view["layout"] == "binary"
    trees = []
    for root in roots:
        pos: dict[str, tuple[float, int]] = {}
        cursor = [0.0]
        seen: set[str] = set()

        def place(k: str, depth: int) -> float:
            if k in seen:
                raise PictureError(f"node {k} is its own ancestor: a tree can't have a cycle")
            seen.add(k)
            ordered = [c for _s, _o, c in sorted(kids[k])]
            slots = {(s if binary else None): c for s, _o, c in sorted(kids[k])}
            if binary:
                xs = []
                for side in (0, 1):
                    if side in slots:
                        xs.append(place(slots[side], depth + 1))
                    elif ordered:  # the missing side keeps half a unit, so the child sits to its side
                        xs.append(cursor[0] + 0.25)
                        cursor[0] += 0.5
                if not ordered:
                    xs = [cursor[0] + 0.5]
                    cursor[0] += 1
            else:
                xs = [place(c, depth + 1) for c in ordered]
                if not xs:
                    xs = [cursor[0] + 0.5]
                    cursor[0] += 1
            x = (min(xs) + max(xs)) / 2
            pos[k] = (x, depth)
            return x

        place(root, 0)
        trees.append((root, pos, cursor[0], max(d for _x, d in pos.values()) + 1))
    return trees


@dataclass
class NodeScale:
    """One size for a node view's whole program: the leaf spacing, the node radius, the level spacing, and the y
    of the first level (the drawing is centred in its band at its tallest)."""

    unit: float
    r: float
    level_h: float
    top: float
    gap: float = TREE_GAP  # leaf units between trees: less when a forest would otherwise wrap


def _rows(trees: list, per_row: float, gap: float = TREE_GAP) -> list[list]:
    rows: list[list] = [[]]
    used = 0.0
    for t in trees:
        extra = gap if rows[-1] else 0.0
        if rows[-1] and used + extra + t[2] > per_row + 1e-9:
            rows.append([])
            used, extra = 0.0, 0.0
        if t[2] > per_row + 1e-9:
            raise PictureError(f"a tree is {t[2]:.0f} nodes wide; at most {int(per_row)} fit across the frame")
        rows[-1].append(t)
        used += extra + t[2]
    return rows


NODE_CHAR_W = 0.19  # a character at the minimum font (measured: "v3" is 0.37 wide, "10" 0.35)
NODE_TEXT_H = 0.285


def node_r(views: list[dict]) -> float:
    """The least node radius that holds the view's longest label inside its circle at the minimum font."""
    longest = max((len(n["label"]) for v in views for n in v["nodes"].values()), default=1)
    return max(NODE_R, float(np.hypot(NODE_CHAR_W * longest / 2, NODE_TEXT_H / 2)) + 0.03)


LABELLED_UNIT = 1.4  # a tree whose links carry labels (a probability tree) spreads out further
LABELLED_LEVEL_H = 1.5


def _labelled(views: list[dict]) -> bool:
    return any(label for v in views for _a, _b, _s, label, _slot in v["links"])


def _tree_shape(views: list[dict], width: float) -> tuple[float, float, int]:
    """A forest view's leaf unit, gap between trees and levels in all (rows of trees stack) at this width."""
    forests = [_tree_units(v) for v in views]
    least = max(NODE_UNIT, node_r(views) / 0.42)  # a leaf's room holds its node
    # the gap between trees shrinks (to none) before a forest wraps onto a second row, which reads as children
    leaves = max((sum(t[2] for t in ts) for ts in forests if ts), default=1.0)
    most = max((len(ts) for ts in forests), default=1)
    slack = width / least - leaves
    gap = TREE_GAP if most <= 1 else max(0.0, min(TREE_GAP, slack / (most - 1)))
    widest = max((sum(t[2] for t in ts) + gap * (len(ts) - 1) for ts in forests if ts), default=1.0)
    unit = max(least, min(LABELLED_UNIT if _labelled(views) else MAX_UNIT, width / widest))
    per_row = width / unit
    levels = max((sum(max(t[3] for t in row) for row in _rows(ts, per_row, gap)) for ts in forests if ts), default=1)
    return unit, gap, levels


def node_scale(views: list[dict], region: Region) -> NodeScale:
    title = _title(views)
    unit, gap, levels = _tree_shape(views, region.w)
    r = max(node_r(views), min(MAX_R, unit * 0.42))
    room = region.h - title - 2 * r - 0.08
    most_h = LABELLED_LEVEL_H if _labelled(views) else MAX_LEVEL_H
    level_h = most_h if levels <= 1 else min(most_h, room / (levels - 1))
    if levels > 1 and level_h < MIN_LEVEL_H:
        raise PictureError(f"the trees are {levels} levels deep in all; at most "
                           f"{int(room / MIN_LEVEL_H) + 1} fit; use a smaller example")
    used = (levels - 1) * level_h + 2 * r
    top = region.top - title - (region.h - title - used) / 2 - r
    return NodeScale(unit, r, level_h, top, gap)


def layout_nodes(view: dict, region: Region, graph_pos: dict[str, np.ndarray] | None,
                 scale: NodeScale) -> dict[str, np.ndarray]:
    if view["layout"] == "graph":
        return {k: graph_pos[k] for k in view["nodes"]}
    out: dict[str, np.ndarray] = {}
    depth0 = 0
    for row in _rows(_tree_units(view), region.w / scale.unit, scale.gap):
        width = (sum(t[2] for t in row) + scale.gap * (len(row) - 1)) * scale.unit
        left = region.cx - width / 2
        for _root, pos, w, _d in row:
            for k, (x, d) in pos.items():
                out[k] = np.array([left + x * scale.unit, scale.top - (depth0 + d) * scale.level_h, 0.0])
            left += (w + scale.gap) * scale.unit
        depth0 += max(t[3] for t in row)
    return out


GRAPH_RS = (0.32, 0.28, 0.24, 0.2)  # node radii tried, largest first (0.2: two characters at the minimum font)
NODE_ROOM = 0.22  # free space between two nodes
LINK_ROOM = 0.1  # free space between a link and a node it doesn't join
MIN_ANGLE = np.radians(22)  # the least angle between two links leaving one node, so arrows never merge
LABEL_CHAR_W = 0.17  # a digit at the minimum font
LABEL_H = 0.28
LABEL_ROOM = 0.04  # free space around a label
LABEL_APART = 0.1  # free space between two labels, so "2" and "9" never read as "29"
OWN_LINK = -0.03  # a label sits no nearer another link than its own (within this), so it reads as its link's
LABEL_FONT = 30  # the minimum; a graph with larger nodes gets larger labels (label_font)
RECIPROCAL = 0.09  # how far a->b and b->a are drawn apart, each to its own side


def label_font(r: float) -> int:
    return round(LABEL_FONT * min(1.3, r / GRAPH_R))


@dataclass
class GraphLayout:
    pos: dict[str, np.ndarray]
    labels: dict[str, np.ndarray]  # each labelled link's label centre, by "a>b"
    r: float
    font: int = LABEL_FONT  # the labels' font size


def link_segment(pos: dict[str, np.ndarray], a: str, b: str, r: float,
                 reciprocal: bool) -> tuple[np.ndarray, np.ndarray]:
    """Where the link a -> b is drawn: from one node's rim to the other's, moved to its own side when b -> a is
    drawn too (so the two arrows don't lie on one line)."""
    p, q = pos[a], pos[b]
    d = (q - p) / max(float(np.linalg.norm(q - p)), 1e-6)
    side = np.array([d[1], -d[0], 0.0]) * (RECIPROCAL if reciprocal else 0.0)
    return p + d * r + side, q - d * r + side


def _link_segments(pos, links: list[tuple[str, str]], r: float, directed: bool) -> dict[tuple[str, str], tuple]:
    present = set(links)
    return {(a, b): link_segment(pos, a, b, r, directed and (b, a) in present) for a, b in links}


def _seg_dist(p: np.ndarray, q: np.ndarray, c: np.ndarray) -> float:
    d = q[:2] - p[:2]
    t = float(np.clip((c[:2] - p[:2]) @ d / (float(d @ d) or 1e-9), 0, 1))
    return float(np.linalg.norm(p[:2] + t * d - c[:2]))


def _seg_hits_box(p: np.ndarray, q: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> bool:
    """Whether the segment p-q passes through the box lo-hi (Liang-Barsky clipping)."""
    t0, t1 = 0.0, 1.0
    d = q[:2] - p[:2]
    for k in range(2):
        if abs(d[k]) < 1e-12:
            if p[k] < lo[k] or p[k] > hi[k]:
                return False
            continue
        a, b = (lo[k] - p[k]) / d[k], (hi[k] - p[k]) / d[k]
        a, b = min(a, b), max(a, b)
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return False
    return True


def _box_near_node(lo, hi, c, r) -> bool:
    return float(np.linalg.norm(np.clip(c[:2], lo, hi) - c[:2])) < r + LABEL_ROOM


_ALONG = (0.5, 0.42, 0.58, 0.34, 0.66, 0.27, 0.73, 0.2, 0.8)
GAP_ROOM = 0.05  # link left clear on each side of a label set into it
MIN_STUB = 0.18  # the least link drawn on each side of a label set into it


def _label_spots(p, q, half) -> list[tuple[np.ndarray, bool]]:
    """Where a label may go, best first: beside its link (either side, nearer first), then set into the link
    (the link drawn with a gap around it, the usual way to write a weight on an edge). (centre, set in)."""
    d = (q - p) / max(float(np.linalg.norm(q - p)), 1e-6)
    normal = np.array([-d[1], d[0], 0.0])
    reach = abs(normal[0]) * half[0] + abs(normal[1]) * half[1]  # the box's extent across its link
    beside = [((p + (q - p) * t + normal * side * (reach + extra))[:2], False)
              for extra in (0.03, 0.12) for t in _ALONG for side in (1, -1)]
    length = float(np.linalg.norm(q - p))
    along = label_gap(d, half)
    inside = [((p + (q - p) * t)[:2], True) for t in _ALONG
              if min(t, 1 - t) * length - along >= MIN_STUB]
    return beside + inside


def label_gap(d: np.ndarray, half: np.ndarray) -> float:
    """Half the gap a label set into a link along direction d needs."""
    return abs(d[0]) * half[0] + abs(d[1]) * half[1] + GAP_ROOM


def _place_in_order(order, pos, labelled, segments, r, region, half_of) -> dict[str, np.ndarray] | None:
    boxes: list[tuple[np.ndarray, np.ndarray]] = []
    out: dict[str, np.ndarray] = {}
    x0, x1 = region.cx - region.w / 2, region.cx + region.w / 2
    for key in order:
        half = half_of[key]
        for c, set_in in _label_spots(*segments[key], half):
            lo, hi = c - half, c + half
            if lo[0] < x0 or hi[0] > x1 or hi[1] > region.top or lo[1] < region.bottom:
                continue
            if any(_box_near_node(lo, hi, n, r) for n in pos.values()):
                continue
            if any(_seg_hits_box(s0, s1, lo - 0.01, hi + 0.01) for k2, (s0, s1) in segments.items()
                   if not (set_in and k2 == key)):
                continue
            if any(np.all(np.abs(c - c2) < half + h2 + LABEL_APART) for c2, h2 in boxes):
                continue
            own = _seg_dist(*segments[key], c)
            if any(_seg_dist(s0, s1, c) < own + OWN_LINK for k2, (s0, s1) in segments.items() if k2 != key):
                continue
            boxes.append((c, half))
            out[f"{key[0]}>{key[1]}"] = np.array([c[0], c[1], 0.0])
            break
        else:
            return None
    return out


def place_labels(pos: dict[str, np.ndarray], labelled: dict[tuple[str, str], str], segments: dict, r: float,
                 region: Region, font: int) -> dict[str, np.ndarray] | None:
    """A place for every label, beside its own link or set into it: clear of every node, every other link and
    the other labels, and inside the region; None when one has no such place. The labels with the fewest free places go
    first, and a few other orders are tried before giving up. Shared by graphs and trees."""
    if not labelled:
        return {}
    k = font / LABEL_FONT
    half_of = {key: np.array([LABEL_CHAR_W * k * len(text) / 2, LABEL_H * k / 2]) + LABEL_ROOM
               for key, text in labelled.items()}
    x0, x1 = region.cx - region.w / 2, region.cx + region.w / 2

    def free(key) -> int:  # its places clear of nodes and links (labels aside)
        half = half_of[key]
        n = 0
        for c, set_in in _label_spots(*segments[key], half):
            lo, hi = c - half, c + half
            if (x0 <= lo[0] and hi[0] <= x1 and lo[1] >= region.bottom and hi[1] <= region.top
                    and not any(_box_near_node(lo, hi, m, r) for m in pos.values())
                    and not any(_seg_hits_box(s0, s1, lo - 0.01, hi + 0.01) for k2, (s0, s1) in segments.items()
                                if not (set_in and k2 == key))):
                n += 1
        return n

    counts = {key: free(key) for key in labelled}
    if min(counts.values()) == 0:
        return None
    order = sorted(labelled, key=lambda key: counts[key])
    rng = np.random.default_rng(0)
    for attempt in range(6):
        if (out := _place_in_order(order, pos, labelled, segments, r, region, half_of)) is not None:
            return out
        order = sorted(labelled, key=lambda key: counts[key] + rng.uniform(0, 3))
    return None


def _clearance(pos: dict[str, np.ndarray], segments: dict, r: float) -> float | None:
    """The least free space between two nodes or between a link and a node it doesn't join, or None when it is
    under the minimum or two links leave a node at nearly the same angle."""
    keys = list(pos)
    least = np.inf
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            free = float(np.linalg.norm(pos[a][:2] - pos[b][:2])) - 2 * r
            if free < NODE_ROOM:
                return None
            least = min(least, free)
    for (a, b), (p, q) in segments.items():
        for k, c in pos.items():
            if k not in (a, b):
                free = _seg_dist(p, q, c) - r
                if free < LINK_ROOM:
                    return None
                least = min(least, free)
    leaving: dict[str, list[float]] = {}
    for a, b in segments:
        for x, y in ((a, b), (b, a)):
            v = pos[y][:2] - pos[x][:2]
            leaving.setdefault(x, []).append(float(np.arctan2(v[1], v[0])))
    for angles in leaving.values():
        angles = sorted(set(round(t, 9) for t in angles))  # a->b and b->a leave along one line, apart by side
        for i, t in enumerate(angles):
            gap = (angles[(i + 1) % len(angles)] - t) % (2 * np.pi) if len(angles) > 1 else 2 * np.pi
            if gap < MIN_ANGLE:
                return None
    return least


def _candidates(g: nx.Graph) -> list[dict]:
    order = sorted(g.nodes)
    out = [nx.kamada_kawai_layout(g)]
    planar, _ = nx.check_planarity(g)
    if planar:
        out.append(nx.planar_layout(g))
    out.append({k: np.array([np.cos(a), np.sin(a)]) for k, a in
                zip(order, np.pi / 2 - 2 * np.pi * np.arange(len(order)) / len(order))})
    out += [nx.spring_layout(g, seed=s) for s in range(48)]
    return out


def _refine(raw: dict, edges: list[tuple[str, str]], r: float, box: tuple[float, float, float, float],
            min_len: float = 0.0, label_room: float = 0.0) -> dict:
    """An arrangement moved, inside the box (for node centres), until its nodes stand apart, its links pass clear
    of the nodes they don't join and the links at each node leave at distinct angles, keeping links about one
    length (so it keeps its shape) and no shorter than `min_len`, with `label_room` free around each link's middle
    (room for its label set into it). A penalty minimised over the node positions, as Penrose lays out
    diagrams."""
    from scipy.optimize import minimize

    keys = list(raw)
    index = {k: i for i, k in enumerate(keys)}
    n = len(keys)
    e = np.array([(index[a], index[b]) for a, b in edges]) if edges else np.zeros((0, 2), int)
    x0, x1, y0, y1 = box
    start = _stretch(raw, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)
    p0 = np.array([start[k][:2] for k in keys])
    apart, clear, angle = 2 * r + NODE_ROOM + 0.06, r + LINK_ROOM + 0.06, MIN_ANGLE + np.radians(6)
    ends = np.zeros((len(e), n), bool)
    if len(e):
        ends[np.arange(len(e)), e[:, 0]] = ends[np.arange(len(e)), e[:, 1]] = True
    incident = [[(j, 0 if a == i else 1) for j, (a, b) in enumerate(e) if i in (a, b)] for i in range(n)]
    length0 = float(np.mean(np.linalg.norm(p0[e[:, 1]] - p0[e[:, 0]], axis=1))) if len(e) else 1.0

    def cost(x: np.ndarray) -> float:
        pts = x.reshape(n, 2)
        d = np.linalg.norm(pts[:, None] - pts[None], axis=2) + np.eye(n) * 1e6
        c = float(np.sum(np.maximum(0, apart - d) ** 2)) / 2
        if len(e):
            a, b = pts[e[:, 0]], pts[e[:, 1]]
            ab = b - a
            t = np.clip(np.einsum("mnk,mk->mn", pts[None] - a[:, None], ab) / np.maximum(
                np.einsum("mk,mk->m", ab, ab), 1e-9)[:, None], 0, 1)
            dist = np.linalg.norm(pts[None] - (a[:, None] + t[..., None] * ab[:, None]), axis=2)
            c += 2 * float(np.sum(np.where(ends, 0, np.maximum(0, clear - dist) ** 2)))
            lengths = np.linalg.norm(ab, axis=1)
            c += 0.01 * float(np.sum((lengths - length0) ** 2))
            c += float(np.sum(np.maximum(0, min_len - lengths) ** 2))
            if label_room:
                mid = (a + b) / 2  # each link's middle: clear of the other nodes and the other links
                to_node = np.linalg.norm(mid[:, None] - pts[None], axis=2)
                c += float(np.sum(np.where(ends, 0, np.maximum(0, r + label_room - to_node) ** 2)))
                t2 = np.clip(np.einsum("fmk,mk->fm", mid[:, None] - a[None], ab) / np.maximum(
                    np.einsum("mk,mk->m", ab, ab), 1e-9)[None], 0, 1)  # (link f's middle, link m)
                d2 = np.linalg.norm(mid[:, None] - (a[None] + t2[..., None] * ab[None]), axis=2)
                np.fill_diagonal(d2, np.inf)
                c += float(np.sum(np.maximum(0, label_room - d2) ** 2))
            for i, inc in enumerate(incident):
                if len(inc) < 2:
                    continue
                th = np.sort([np.arctan2(*(ab[j] * (1 if s == 0 else -1))[::-1]) for j, s in inc])
                gaps = np.diff(np.append(th, th[0] + 2 * np.pi))
                c += float(np.sum(np.maximum(0, angle - gaps) ** 2))
        return c

    bounds = [(x0, x1), (y0, y1)] * n
    res = minimize(cost, p0.ravel(), method="L-BFGS-B", bounds=bounds, options={"maxiter": 300})
    pts = res.x.reshape(n, 2)
    return {k: np.array([pts[i][0], pts[i][1], 0.0]) for i, k in enumerate(keys)}


REFINED = 8  # arrangements refined when none is clear as it stands


def graph_positions(views: list[dict], region: Region) -> GraphLayout:
    """One layout for every node and link any snapshot shows, so nodes stay put while the graph is explored."""
    g = nx.Graph()
    links: list[tuple[str, str]] = []
    for v in views:
        g.add_nodes_from(v["nodes"])
        for a, b, *_ in v["links"]:
            g.add_edge(a, b)
            if (a, b) not in links:
                links.append((a, b))
    directed = bool(views[0]["directed"])
    title = _title(views)
    cy = region.top - title - (region.h - title) / 2
    if len(g) == 1:
        return GraphLayout({next(iter(g)): np.array([region.cx, cy, 0.0])}, {}, max(GRAPH_RS))
    labelled = {}
    for v in views:
        for a, b, _s, label, _slot in v["links"]:
            if label:
                labelled[(a, b)] = str(label)
    band = Region(region.cx, region.top - title, region.w, region.h - title)
    raws = _candidates(g)
    edges = list(g.edges)
    best = None

    def consider(pos: dict, r: float) -> None:
        nonlocal best
        segments = _link_segments(pos, links, r, directed)
        if (room := _clearance(pos, segments, r)) is None:
            return
        for font in dict.fromkeys((label_font(r), LABEL_FONT)):  # larger labels with larger nodes, if they fit
            spots = place_labels(pos, labelled, segments, r, band, font)
            if spots is not None:
                break
        else:
            return
        score = (_crossings(pos, edges), -r, -room)
        if best is None or score < best[0]:
            best = (score, GraphLayout(pos, spots, r, font))

    least = node_r(views)
    radii = [r for r in GRAPH_RS if r >= least] or [least]
    for r in radii:
        # each arrangement stretched to fill the band (a portrait band is wide and short, so one uniform scale
        # wastes most of it)
        w, h = region.w - 2 * r - 0.1, region.h - title - 2 * r - 0.1
        if h <= 0:
            continue
        for raw in raws:
            consider(_stretch(raw, region.cx, cy, w, h), r)
    if best is None:  # none is clear as it stands: refine the ones with the fewest crossings, largest nodes first
        ranked = sorted(raws, key=lambda raw: _crossings(_stretch(raw, 0, 0, 1, 1), edges))[:REFINED]
        for r in radii:
            w, h = region.w - 2 * r - 0.1, region.h - title - 2 * r - 0.1
            if h <= 0:
                continue
            # with labels, nodes keep off the band's edge so a label has room on the outer side of a link there,
            # and labelled links are long enough for a label beside them
            inset = max(0.0, min(LABEL_H + 0.06 if labelled else 0.0, w / 2 - 0.05, h / 2 - 0.05))
            box = (region.cx - w / 2 + inset, region.cx + w / 2 - inset, cy - h / 2 + inset, cy + h / 2 - inset)
            longest = max((len(t) for t in labelled.values()), default=0)
            min_len = 2 * r + LABEL_CHAR_W * longest + 0.4 if labelled else 0.0
            room = LABEL_CHAR_W * longest / 2 + LABEL_ROOM + 0.12 if labelled else 0.0
            for raw in ranked:
                consider(_refine(raw, edges, r, box, min_len, room), r)
            if best is not None:
                break
    if best is None:
        what = f"{len(g)} nodes and {g.number_of_edges()} links" + (" with their labels" if labelled else "")
        raise PictureError(f"the graph's {what} can't be drawn clearly in a band {region.w:.1f} wide and "
                           f"{region.h:.1f} tall")
    return best[1]


def _stretch(raw: dict, cx: float, cy: float, w: float, h: float) -> dict[str, np.ndarray]:
    pts = np.array(list(raw.values()), dtype=float)
    lo, hi = pts.min(0), pts.max(0)
    span = np.where(hi - lo < 1e-6, 1.0, hi - lo)
    mid = (hi + lo) / 2
    return {k: np.array([cx + (p[0] - mid[0]) / span[0] * w, cy + (p[1] - mid[1]) / span[1] * h, 0.0])
            for k, p in raw.items()}


def _crossings(pos: dict[str, np.ndarray], edges: list) -> int:
    def cross(p1, p2, p3, p4) -> bool:
        def orient(a, b, c):
            return np.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        return (orient(p1, p2, p3) != orient(p1, p2, p4)) and (orient(p3, p4, p1) != orient(p3, p4, p2))

    n = 0
    for i, (a, b) in enumerate(edges):
        for c, d in edges[i + 1:]:
            if len({a, b, c, d}) == 4 and cross(pos[a], pos[b], pos[c], pos[d]):
                n += 1
    return n


def tree_labels(view: dict, region: Region, scale: NodeScale) -> dict[str, np.ndarray] | None:
    """A tree snapshot's link labels (a probability tree's), placed as a graph's are; None when one won't fit."""
    labelled = {(a, b): str(label) for a, b, _s, label, _slot in view["links"] if label
                and a in view["nodes"] and b in view["nodes"]}
    if not labelled:
        return {}
    pos = layout_nodes(view, region, None, scale)
    links = [(a, b) for a, b, *_ in view["links"] if a in pos and b in pos]
    segments = _link_segments(pos, links, scale.r, False)
    title = _title([view])
    return place_labels(pos, labelled, segments, scale.r, Region(region.cx, region.top - title, region.w,
                                                                 region.h - title), LABEL_FONT)


# ---- the rest ----------------------------------------------------------------------------------------------


def _cell(views: list[dict], width: float) -> float:
    n = max(len(v["values"]) for v in views)
    return min(MAX_CELL, width / n)


def cell_size(views: list[dict], region: Region) -> float:
    n = max(len(v["values"]) for v in views)
    size = min(_cell(views, region.w), region.h - _cells_height(views, 0.0) + 1e-9)
    if size < MIN_CELL:
        raise PictureError(f"{n} cells don't fit across the frame; at most {int(region.w / MIN_CELL)}")
    return size


def check_code(views: list[dict], region: Region) -> None:
    longest = max(len(line) for v in views for line in v["lines"])
    fits = int((region.w - 0.3) / CODE_CHAR_W)
    if longest > fits:
        raise PictureError(f"a code line is {longest} characters; at most {fits} fit across the frame")


@dataclass
class PictureLayout:
    regions: dict[str, Region]
    graph_pos: dict[str, dict[str, np.ndarray]]
    cell: dict[str, float]
    nodes: dict[str, NodeScale]
    labels: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)  # a graph's link labels, by "a>b"
    label_font: dict[str, int] = field(default_factory=dict)
    untitled: frozenset = frozenset()
    math: dict = field(default_factory=dict)  # an axes, Venn or geometry view's layout (scene/math_layout.py)  # views whose titles were left out to give the picture room


def without_titles(snaps: list[dict], names) -> list[dict]:
    return [{**s, "views": {n: ({**v, "title": None} if n in names else v) for n, v in s["views"].items()}}
            for s in snaps]


def plan(snaps: list[dict], width: float, height: float, top: float) -> PictureLayout:
    """The layout for a whole program, or PictureError when it can't be drawn legibly. A title costs 0.38 units
    of height and the lines can say it, so it gives way to the picture: the main picture's (a node view's) title
    is left out when the picture would be short, and when the picture can't be drawn clearly the main title,
    then every title, is left out before giving up (runs/picture-p1: the slide's Bellman-Ford graph and all 16
    of its weights fit beside its array only untitled)."""
    titled = [n for n in snaps[-1]["views"] if any(s["views"].get(n, {}).get("title") for s in snaps)]
    main = [n for n in titled if snaps[-1]["views"][n]["kind"] in MAIN_KINDS and n in snaps[-1]["views"]
            and snaps[-1]["views"][n]["kind"] != "container"]

    def untitled(names) -> PictureLayout | None:
        try:
            layout = _plan(without_titles(snaps, set(names)), width, height, top)
        except PictureError:
            return None
        layout.untitled = frozenset(names)
        return layout

    try:
        layout = _plan(snaps, width, height, top)
    except PictureError as error:
        for names in dict.fromkeys((tuple(main), tuple(titled))):
            if names and (layout := untitled(names)) is not None:
                return layout
        raise error
    if main and min(layout.regions[n].h for n in main) - TITLE_H < MAIN_ROOM:
        return untitled(main) or layout
    return layout


def _plan(snaps: list[dict], width: float, height: float, top: float) -> PictureLayout:
    regions = plan_regions(snaps, width, height, top)
    graph_pos, cell, scales, labels, fonts, maths = {}, {}, {}, {}, {}, {}
    for name, region in regions.items():
        views = [s["views"][name] for s in snaps if name in s["views"]]
        kind = views[0]["kind"]
        try:
            if kind == "nodes" and views[0]["layout"] == "graph":
                g = graph_positions(views, region)
                graph_pos[name], labels[name], fonts[name] = g.pos, g.labels, g.font
                scales[name] = NodeScale(NODE_UNIT, g.r, 0.0, 0.0)
            elif kind == "nodes":
                scales[name] = node_scale(views, region)  # raises if any snapshot can't be drawn
                fonts[name] = LABEL_FONT
                for i, v in enumerate(views):
                    if tree_labels(v, region, scales[name]) is None:
                        raise PictureError(f"a link label can't be placed clear of the tree in snapshot {i + 1}; "
                                           "use shorter labels or fewer nodes")
            elif kind in MATH_KINDS:
                maths[name] = _view_layouts()[kind][1](views, region)
            elif kind == "cells":
                cell[name] = cell_size(views, region)
            elif kind == "code":
                check_code(views, region)
        except PictureError as e:
            others = [f"{_WHAT[snaps_kind]} {regions[n].h:.1f}" for n in regions if n != name
                      for snaps_kind in [next(s["views"][n]["kind"] for s in snaps if n in s["views"])]]
            if kind in MAIN_KINDS and others:
                raise PictureError(f"{e}: it gets {region.h:.1f} of the {height:.1f} units because the other views "
                                   f"take {', '.join(others)}. Drop a view the lines can say instead (a code panel "
                                   "first) before making the example smaller; the slide's own example matters "
                                   "more") from e
            if kind == "nodes" and "fit" not in str(e):
                raise PictureError(f"{e}; use fewer links or nodes, or give the picture the whole frame (it shares "
                                   "the frame whenever the video also shows a formula or note)") from e
            raise
    return PictureLayout(regions, graph_pos, cell, scales, labels, fonts, math=maths)
