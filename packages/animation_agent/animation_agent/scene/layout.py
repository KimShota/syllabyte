"""
Where everything in a picture program's snapshots goes. Pure Python (numpy, networkx), no Manim.

One layout for the whole program, not one per snapshot: each view gets a fixed band of the area (views stack top
to bottom in the order the program made them; containers made one after another share a row), and nodes and cells
keep one size throughout, so nothing grows or shrinks between steps. Positions then change only when the
structure does, and the drawing animates exactly that.

Sizes are in scene units for the 4.5-unit-wide portrait frame and keep text at the layout audit's minimum font.
"""

from __future__ import annotations

from dataclasses import dataclass

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
GRAPH_R = 0.24
CELL = 0.46
MIN_CELL = 0.36
INDEX_H = 0.3
POINTER_H = 0.32
TITLE_H = 0.38
CODE_LINE_H = 0.48
CODE_CHAR_W = 0.245  # Menlo at the minimum font (30), measured: about 15 characters across the frame
CONTAINER_H = 2.0
GAP = 0.14


@dataclass
class Region:
    cx: float
    top: float
    w: float
    h: float

    @property
    def bottom(self) -> float:
        return self.top - self.h


def _natural_height(kind: str, views: list[dict]) -> float:
    """The height a view needs (its largest snapshot), before the nodes take what is left."""
    first = views[0]
    title = TITLE_H if any(v.get("title") for v in views) else 0.0
    if kind == "cells":
        ptr = POINTER_H if any(v["pointers"] for v in views) else 0.0
        return title + CELL + (INDEX_H if first["index"] else 0.0) + ptr
    if kind == "code":
        return title + CODE_LINE_H * len(first["lines"])
    if kind == "container":
        return title + CONTAINER_H
    return title + LEVEL_H  # nodes: at least one level; they get the rest


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
    need = [max(_natural_height(kinds[n], by_name[n]) for n in band) for band in bands]
    spare = height - sum(need) - GAP * (len(bands) - 1)
    if spare < -1e-6:
        raise PictureError("these views don't fit on screen together; use fewer or smaller ones")
    grow = [i for i, band in enumerate(bands) if any(kinds[n] in ("nodes", "container") for n in band)]
    for i in grow:
        need[i] += spare / len(grow)
    regions: dict[str, Region] = {}
    y = top if grow else top - spare / 2  # with nothing to grow, centre the stack
    for band, h in zip(bands, need):
        w = width / len(band)
        for j, n in enumerate(band):
            regions[n] = Region(-width / 2 + w * (j + 0.5), y, w, h)
        y -= h + GAP
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


def node_scale(views: list[dict], region: Region) -> NodeScale:
    title = TITLE_H if any(v.get("title") for v in views) else 0.0
    forests = [_tree_units(v) for v in views]
    # the gap between trees shrinks (to none) before a forest wraps onto a second row, which reads as children
    leaves = max((sum(t[2] for t in ts) for ts in forests if ts), default=1.0)
    most = max((len(ts) for ts in forests), default=1)
    slack = region.w / NODE_UNIT - leaves
    gap = TREE_GAP if most <= 1 else max(0.0, min(TREE_GAP, slack / (most - 1)))
    widest = max((sum(t[2] for t in ts) + gap * (len(ts) - 1) for ts in forests if ts), default=1.0)
    unit = max(NODE_UNIT, min(MAX_UNIT, region.w / widest))
    r = min(MAX_R, unit * 0.42)
    per_row = region.w / unit
    levels = max((sum(max(t[3] for t in row) for row in _rows(ts, per_row, gap)) for ts in forests if ts), default=1)
    room = region.h - title - 2 * r - 0.08
    level_h = MAX_LEVEL_H if levels <= 1 else min(MAX_LEVEL_H, room / (levels - 1))
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


def graph_positions(views: list[dict], region: Region) -> dict[str, np.ndarray]:
    """One layout for every node and link any snapshot shows, so nodes stay put while the graph is explored."""
    g = nx.Graph()
    for v in views:
        g.add_nodes_from(v["nodes"])
        g.add_edges_from((a, b) for a, b, *_ in v["links"])
    if len(g) == 1:
        raw = {next(iter(g)): np.zeros(2)}
    else:
        raw = nx.kamada_kawai_layout(g)
    pts = np.array(list(raw.values()))
    span = np.maximum(pts.max(0) - pts.min(0), 1e-6)
    title = TITLE_H if any(v.get("title") for v in views) else 0.0
    w, h = region.w - 2 * GRAPH_R - 0.1, region.h - title - 2 * GRAPH_R - 0.1
    scale = min(w / span[0], h / span[1])
    mid = (pts.max(0) + pts.min(0)) / 2
    cy = region.top - title - (region.h - title) / 2
    out = {k: np.array([region.cx + (p[0] - mid[0]) * scale, cy + (p[1] - mid[1]) * scale, 0.0]) for k, p in raw.items()}
    keys = list(out)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if np.linalg.norm(out[a] - out[b]) < 2 * GRAPH_R + 0.06:
                raise PictureError("the graph has too many nodes to draw apart in the frame; use fewer")
    return out


# ---- the rest ----------------------------------------------------------------------------------------------


def cell_size(views: list[dict], region: Region) -> float:
    n = max(len(v["values"]) for v in views)
    size = min(CELL, region.w / n)
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


def plan(snaps: list[dict], width: float, height: float, top: float) -> PictureLayout:
    """The layout for a whole program, or PictureError when it can't be drawn legibly."""
    regions = plan_regions(snaps, width, height, top)
    graph_pos, cell, scales = {}, {}, {}
    for name, region in regions.items():
        views = [s["views"][name] for s in snaps if name in s["views"]]
        kind = views[0]["kind"]
        if kind == "nodes" and views[0]["layout"] == "graph":
            graph_pos[name] = graph_positions(views, region)
            scales[name] = NodeScale(NODE_UNIT, GRAPH_R, 0.0, 0.0)
        elif kind == "nodes":
            scales[name] = node_scale(views, region)  # raises if any snapshot can't be drawn
        elif kind == "cells":
            cell[name] = cell_size(views, region)
        elif kind == "code":
            check_code(views, region)
    return PictureLayout(regions, graph_pos, cell, scales)

