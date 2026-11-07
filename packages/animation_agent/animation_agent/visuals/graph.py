"""Graph: nodes (circles with names) and edges, laid out in rows by distance from the first node (or round a
circle), with DFS and BFS computed by specs.dfs_next / specs.bfs_next, the functions the checker runs.

A node's state shows in its outline (yellow: current, teal: visited, or a highlight colour), never its fill: the
fill stays opaque black so the white name keeps its contrast and an edge passing behind a node is hidden. Edges
are background for the layout audit for the same reason."""

from __future__ import annotations

import numpy as np
from manim import (
    BLACK,
    TAU,
    WHITE,
    ArcBetweenPoints,
    Arrow,
    Circle,
    Create,
    CurvedArrow,
    DashedLine,
    Dot,
    FadeIn,
    Line,
    MoveAlongPath,
    RoundedRectangle,
    VGroup,
)

from animation_agent.visuals.base import (
    GHOST_COLOUR,
    MIN_FONT,
    NOTE_ROW,
    Step,
    Steps,
    Template,
    colour,
    mark_background,
    text,
    wrapped,
)
from animation_agent.visuals.specs import (
    GRAPH,
    bfs_new,
    bfs_next,
    dfs_new,
    dfs_next,
    graph_adjacency,
    box_share,
    graph_positions,
    spread_rows,
)

MAX_R = 0.28
STATE_COLOUR = {"current": "YELLOW", "visited": "TEAL"}
BOX_PAD = 0.12
BOX_H = 0.46
MARKER_R = 0.09
EDGE_LABEL_OFFSET = 0.2
LOOP_W = 0.26


def _clip(center: np.ndarray, half_w: float, half_h: float, toward: np.ndarray) -> np.ndarray:
    """Where the segment from a box's centre toward a point leaves the box."""
    d = toward - center
    if not np.any(d[:2]):
        return center
    tx = half_w / abs(d[0]) if d[0] else np.inf
    ty = half_h / abs(d[1]) if d[1] else np.inf
    return center + d * min(tx, ty, 1.0)


class Graph(Template):
    spec = GRAPH
    durations = {"create": 1.0, "dfs_step": 0.8, "bfs_level": 0.9, "path": 0.8, "ghost_edge": 0.7, "walk": 0.8,
                 "feed": 0.9}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.adj = graph_adjacency(params.nodes, params.edges, params.directed)
        self.search = None
        self.search_state: dict[str, str] = {}  # node -> "current" | "visited"
        self.search_edges: set[tuple[str, str]] = set()
        self.hl_nodes: dict[str, str] = {}
        self.hl_edges: dict[tuple[str, str], str] = {}
        self.note_mob = self.ghost_mob = None
        self.marker = None
        self.at: str | None = None
        self.read = ""
        self.boxes = params.labels is not None
        self._layout()

    # ---- layout ---------------------------------------------------------

    def _key(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if self.p.directed else tuple(sorted((a, b)))

    def _layout(self) -> None:
        box = self.bounds
        unit = graph_positions(self.p.nodes, self.p.edges, self.p.layout, self.p.directed)
        if self.boxes and self.p.layout == "layers":
            unit = spread_rows(unit)
        top, bottom = box.top - NOTE_ROW, box.bottom
        width, height = box.width, top - bottom
        rows: dict[float, list[float]] = {}
        for x, y in unit.values():
            rows.setdefault(round(y, 6), []).append(x)
        ys = sorted(rows)
        # The closest two nodes in a row, and the closest two rows, in the unit square.
        gx = min([b - a for row in rows.values() for a, b in zip(sorted(row), sorted(row)[1:])] or [1.0])
        gy = min([b - a for a, b in zip(ys, ys[1:])] or [1.0])
        if self.p.layout == "circle" and not self.boxes:
            self.r = min(MAX_R, 0.32 * width / 3, 0.32 * height / 3)
            half_w = half_h = self.r
        elif self.boxes:
            # Wide enough for the words, but the closest two boxes in a row keep a tenth of a box between them:
            # box_w = 0.9 * gx * (width - box_w - 0.1), solved for box_w; the same for the rows' heights.
            # Beside other boxes in a row, a tenth of a box between them; along a "flow" row, room for an arrow.
            share = box_share(self.p.layout)
            self.box_w = min(2.6, share * gx * (width - 0.1) / (1 + share * gx))
            self.box_h = min(BOX_H + 0.3, 0.55 * gy * (height - 0.1) / (1 + 0.55 * gy))
            half_w, half_h = self.box_w / 2, self.box_h / 2
            self.r = min(half_w, half_h)
        else:
            per_row = max(len(row) for row in rows.values())
            dx = min(width / (per_row + 1), gx * width)
            self.r = min(MAX_R, 0.32 * dx, 0.32 * height / max(len(ys), 1))
            half_w = half_h = self.r
        span_w, span_h = width - 2 * half_w - 0.1, height - 2 * half_h - 0.1
        if self.p.layout == "circle" and not self.boxes:
            span_w = span_h = min(span_w, span_h)
        cx, cy = box.center[0], (top + bottom) / 2
        self.pos = {n: np.array([cx + (x - 0.5) * span_w, cy + (y - 0.5) * span_h, 0.0]) for n, (x, y) in unit.items()}
        self.half = (half_w, half_h)
        self.note_y = box.top - NOTE_ROW / 2

    def _node(self, name: str) -> object:
        if self.boxes:
            shape = RoundedRectangle(width=self.box_w, height=self.box_h, corner_radius=0.08, stroke_width=3,
                                     stroke_color=colour("BLUE"), fill_color=BLACK, fill_opacity=1)
            shape.move_to(self.pos[name])
            label = wrapped(self.p.labels[name], self.box_w - 2 * BOX_PAD, MIN_FONT, WHITE, max_lines=2)
            if label.height > self.box_h - 0.1:  # two lines: the box grows to hold them (its row has the room)
                shape.stretch_to_fit_height(label.height + 0.16)
            if label.width > self.box_w - 0.12:  # never below the readable size (the spec keeps labels short)
                label.scale(max(0.94, (self.box_w - 0.12) / label.width))
            label.move_to(shape)
            return VGroup(shape, label).set_z_index(2)
        circle = Circle(radius=self.r, stroke_width=3, stroke_color=colour("BLUE"), fill_color=BLACK, fill_opacity=1)
        circle.move_to(self.pos[name])
        label = text(name, MIN_FONT, WHITE, max_width=self.r * 1.6).move_to(circle)
        return VGroup(circle, label).set_z_index(2)  # above every edge, the ghost edge too

    def _ends(self, a: str, b: str) -> tuple[np.ndarray, np.ndarray]:
        """Where an edge from a to b starts and ends: on the two nodes' outlines."""
        pa, pb = self.pos[a], self.pos[b]
        if self.boxes:
            hw, hh = self.half
            return _clip(pa, hw, hh, pb), _clip(pb, hw, hh, pa)
        d = (pb - pa) / max(np.linalg.norm(pb - pa), 1e-6)
        return pa + d * self.r, pb - d * self.r

    def _loop(self, a: str, col, width: float):
        """A small loop on top of the node (left of centre, clear of the marker's corner)."""
        hw, hh = self.half
        p = self.pos[a] + np.array([-min(hw * 0.4, 0.3), 0, 0])
        start, end = p + np.array([-LOOP_W / 2, hh, 0]), p + np.array([LOOP_W / 2, hh, 0])
        return CurvedArrow(start, end, angle=-TAU * 0.7, color=col, stroke_width=width, tip_length=0.12)

    def _blocked(self, a: str, b: str) -> bool:
        """Whether the straight edge from a to b would pass through another node."""
        pa, pb = self.pos[a], self.pos[b]
        d = pb - pa
        length2 = float(np.dot(d, d)) or 1e-9
        hw, hh = self.half
        for n, p in self.pos.items():
            if n in (a, b):
                continue
            t = float(np.clip(np.dot(p - pa, d) / length2, 0, 1))
            near = pa + t * d - p
            if 0 < t < 1 and abs(near[0]) < hw + 0.08 and abs(near[1]) < hh + 0.08:
                return True
        return False

    def _bend(self, a: str, b: str) -> float:
        """How much an edge curves (0: straight): one that would cross a node bends round it, and a pair of edges
        between the same two nodes, one each way, bend apart."""
        if a == b:
            return 0.0
        if self._blocked(a, b):
            angle = 1.1
            mid = (self.pos[a] + self.pos[b]) / 2
            centre = np.mean(list(self.pos.values()), axis=0)
            d = self.pos[b] - self.pos[a]
            right = np.array([d[1], -d[0], 0.0])  # a positive angle bulges to this side
            lean = float(np.dot(right, mid - centre))
            if abs(lean) < 0.05:  # no side is outward (a single row): below, where no loop sits
                lean = -right[1]
            return angle if lean >= 0 else -angle
        if self.p.directed and any(e[0] == b and e[1] == a for e in self.p.edges):
            return 0.5
        return 0.0

    def _edge(self, a: str, b: str, col=None, width: float = 3) -> object:
        col = col or colour("GREY")
        if a == b:
            return mark_background(self._loop(a, col, width))
        start, end = self._ends(a, b)
        bend = self._bend(a, b)
        if bend:
            if self.p.directed:
                e = CurvedArrow(start, end, angle=bend, color=col, stroke_width=width, tip_length=0.16)
            else:
                e = ArcBetweenPoints(start, end, angle=bend, color=col, stroke_width=width)
        elif self.p.directed:
            e = Arrow(start, end, buff=0, stroke_width=width, color=col, max_tip_length_to_length_ratio=0.18)
        else:
            e = Line(start, end, stroke_width=width, color=col)
        return mark_background(e)

    def _edge_label(self, e: list[str]):
        a, b, label = e
        if a == b:
            loop = self._loop(a, WHITE, 1)
            return text(label, MIN_FONT, colour("GOLD")).next_to(loop, np.array([-1.0, 0, 0]), buff=0.06)
        lab = text(label, MIN_FONT, colour("GOLD"))
        start, end = self._ends(a, b)
        chord_mid = (start + end) / 2
        if self._bend(a, b):  # beside the curve's middle, on its outer side
            mid = self.edges[self._key(a, b)].point_from_proportion(0.5)
            away = mid - chord_mid
            away = away / max(np.linalg.norm(away), 1e-6)
            reach = 0.1 + 0.5 * abs(np.dot(away, [lab.width, lab.height, 0]))
            return lab.move_to(mid + away * reach)
        d = end - start
        centre = np.mean(list(self.pos.values()), axis=0)
        # Beside a straight edge's middle, sideways: above a level edge, else on the side away from the middle
        # of the drawing, so the label stays in the gap between two rows.
        if abs(d[1]) < 1e-6:
            side = np.array([0.0, 1.0, 0.0])
            reach = 0.08 + lab.height / 2
        else:
            side = np.array([1.0 if chord_mid[0] >= centre[0] else -1.0, 0.0, 0.0])
            slope = abs(d[0] / d[1])
            reach = 0.1 + lab.width / 2 + slope * lab.height / 2
        return lab.move_to(chord_mid + side * reach)

    def _corner(self, n: str) -> np.ndarray:
        """Where the marker sits on a node: its top right corner, clear of the words."""
        hw, hh = self.half
        if self.boxes:  # just outside the top right corner, clear of words that run to the box's edge
            return self.pos[n] + np.array([hw + MARKER_R * 0.5, hh + MARKER_R * 0.5, 0])
        return self.pos[n] + np.array([0.7, -0.7, 0]) * (self.r + MARKER_R)  # outside the circle, below right

    def _node_colour(self, n: str):
        if n in self.hl_nodes:
            return colour(self.hl_nodes[n]), 6
        if n in self.search_state:
            return colour(STATE_COLOUR[self.search_state[n]]), 6
        return colour("BLUE"), 3

    def _edge_style(self, key: tuple[str, str]):
        if key in self.hl_edges:
            return colour(self.hl_edges[key]), 6
        if key in self.search_edges:
            return colour("TEAL"), 6
        return colour("GREY"), 3

    def _restyle(self, nodes=(), edges=()) -> list:
        anims = []
        for n in nodes:
            col, w = self._node_colour(n)
            anims.append(self.nodes[n][0].animate.set_stroke(col, w))
        for key in edges:
            col, w = self._edge_style(key)
            anims.append(self.edges[key].animate.set_stroke(col, w).set_fill(col))
        return anims

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    # ---- create ---------------------------------------------------------

    def create(self) -> Steps:
        self.edges = {self._key(e[0], e[1]): self._edge(e[0], e[1]) for e in self.p.edges}
        self.nodes = {n: self._node(n) for n in self.p.nodes}
        labels = [self._edge_label(e) for e in self.p.edges if len(e) == 3]
        for e in self.edges.values():
            self.group.add(e)
        for n in self.nodes.values():
            self.group.add(n)
        for lab in labels:
            self.group.add(lab)
        anims = ([Create(e) for e in self.edges.values()] + [FadeIn(n) for n in self.nodes.values()]
                 + [FadeIn(lab) for lab in labels])
        if self.p.title:
            anims += self._note(self.p.title, colour("GREY"))
        yield Step(anims)

    # ---- searches ---------------------------------------------------------

    def _start(self, kind: str, start: str) -> list:
        s = self.search
        if s is not None and s["kind"] == kind and s["start"] == start:
            return []
        old = list(self.search_state)
        old_edges = list(self.search_edges)
        self.search = (dfs_new if kind == "dfs" else bfs_new)(start)
        self.search_state, self.search_edges = {}, set()
        return self._restyle(old, old_edges)

    def dfs_step(self, a) -> Steps:
        anims = self._start("dfs", a.start)
        ev = dfs_next(self.adj, self.search)
        changed = []
        for n, st in self.search_state.items():
            if st == "current":
                self.search_state[n] = "visited"
                changed.append(n)
        edges = []
        if ev["visit"] is not None:
            self.search_state[ev["visit"]] = "current"
            changed.append(ev["visit"])
            if ev["from"] is not None:
                key = self._key(ev["from"], ev["visit"])
                self.search_edges.add(key)
                edges.append(key)
            note = "visited: " + ", ".join(self.search["visited"])
        else:
            note = "DFS done"
        yield Step(anims + self._restyle(changed, edges) + self._note(note))

    def bfs_level(self, a) -> Steps:
        anims = self._start("bfs", a.start)
        ev = bfs_next(self.adj, self.search)
        if ev["level"] is None:
            yield Step(anims + self._note("BFS done"))
            return
        for n in ev["nodes"]:
            self.search_state[n] = "visited"
        edges = [self._key(u, v) for v, u in ev["from"].items()]
        self.search_edges |= set(edges)
        yield Step(anims + self._restyle(ev["nodes"], edges)
                   + self._note(f"distance {ev['level']}: " + ", ".join(ev["nodes"])))

    # ---- the marker ---------------------------------------------------------

    def _move_marker(self, to: str) -> list:
        old = self.at
        self.at = to
        restyle = []
        if old is not None and old not in self.hl_nodes:
            restyle = self._restyle([old])
        self.hl_nodes[to] = "GOLD"
        restyle += self._restyle([to])
        if self.marker is None:
            self.marker = Dot(self._corner(to), radius=MARKER_R, color=colour("GOLD")).set_z_index(3)
            return restyle + self.add(self.marker)
        if old == to:
            return restyle + [self.marker.animate.move_to(self._corner(to))]
        path = Line(self._corner(old), self._corner(to))
        return restyle + [MoveAlongPath(self.marker, path)]

    def walk(self, a) -> Steps:
        if self.at is not None and self.at in self.hl_nodes and self.hl_nodes[self.at] == "GOLD":
            del self.hl_nodes[self.at]
        yield Step(self._move_marker(a.to))

    def feed(self, a) -> Steps:
        at = self.at if self.at is not None else self.p.nodes[0]
        nxt = next(e[1] for e in self.p.edges if len(e) == 3 and e[2] == a.symbol
                   and (e[0] == at or (not self.p.directed and e[1] == at)))
        if not self.p.directed and nxt == at:
            nxt = next(e[0] for e in self.p.edges if len(e) == 3 and e[2] == a.symbol and e[1] == at)
        if self.at is not None and self.hl_nodes.get(self.at) == "GOLD":
            del self.hl_nodes[self.at]
        if self.at is None:  # the run starts at the first node
            yield Step(self._move_marker(at), 0.3)
            del self.hl_nodes[at]
        self.read += a.symbol
        yield Step(self._move_marker(nxt) + self._note(f'read: "{self.read}"'), 0.7)

    # ---- marks ----------------------------------------------------------

    def highlight(self, a) -> Steps:
        for n in a.nodes:
            self.hl_nodes[n] = a.colour
        yield Step(self._restyle(a.nodes))

    def highlight_edge(self, a) -> Steps:
        key = self._key(a.a, a.b)
        self.hl_edges[key] = a.colour
        yield Step(self._restyle(edges=[key]))

    def path(self, a) -> Steps:
        keys = [self._key(u, v) for u, v in zip(a.nodes, a.nodes[1:])]
        for k in keys:
            self.hl_edges[k] = a.colour
        for n in a.nodes:
            self.hl_nodes[n] = a.colour
        yield Step(self._restyle(a.nodes, keys))

    def ghost_edge(self, a) -> Steps:
        old = self.ghost_mob
        self.ghost_mob = mark_background(DashedLine(self.pos[a.a], self.pos[a.b], buff=self.r, color=GHOST_COLOUR,
                                                    stroke_width=4))
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        nodes, edges = list(self.hl_nodes), list(self.hl_edges)
        self.hl_nodes, self.hl_edges = {}, {}
        anims = self._restyle(nodes, edges) + self.drop(self.ghost_mob, self.note_mob)
        self.ghost_mob = self.note_mob = None
        if anims:
            yield Step(anims)

    def reset(self, a) -> Steps:
        nodes = set(self.hl_nodes) | set(self.search_state)
        edges = set(self.hl_edges) | self.search_edges
        self.hl_nodes, self.hl_edges, self.search_state, self.search_edges = {}, {}, {}, set()
        self.search = None
        anims = self._restyle(nodes, edges) + self.drop(self.ghost_mob, self.note_mob, self.marker)
        self.ghost_mob = self.note_mob = self.marker = None
        self.at, self.read = None, ""
        if anims:
            yield Step(anims)


__all__ = ["Graph"]
