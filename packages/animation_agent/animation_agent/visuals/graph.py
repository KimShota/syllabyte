"""Graph: nodes (circles with names) and edges, laid out in rows by distance from the first node (or round a
circle), with DFS and BFS computed by specs.dfs_next / specs.bfs_next, the functions the checker runs.

A node's state shows in its outline (yellow: current, teal: visited, or a highlight colour), never its fill: the
fill stays opaque black so the white name keeps its contrast and an edge passing behind a node is hidden. Edges
are background for the layout audit for the same reason."""

from __future__ import annotations

import numpy as np
from manim import BLACK, WHITE, Arrow, Circle, Create, DashedLine, FadeIn, Line, VGroup

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
)
from animation_agent.visuals.specs import GRAPH, bfs_new, bfs_next, dfs_new, dfs_next, graph_adjacency

MAX_R = 0.28
STATE_COLOUR = {"current": "YELLOW", "visited": "TEAL"}


def graph_positions(nodes: list[str], edges: list[list[str]], layout: str) -> dict[str, tuple[float, float]]:
    """Each node's place in the unit square (y up). "layers": a row per distance from the first node (other parts
    of the graph below), each row ordered by where its neighbours above sit; "circle": evenly round a circle."""
    if layout == "circle":
        k = len(nodes)
        return {n: (0.5 + 0.5 * np.sin(2 * np.pi * i / k), 0.5 + 0.5 * np.cos(2 * np.pi * i / k))
                for i, n in enumerate(nodes)}
    adj = graph_adjacency(nodes, edges, directed=False)
    levels: list[list[str]] = []
    seen: set[str] = set()
    for root in nodes:
        if root in seen:
            continue
        frontier = [root]
        seen.add(root)
        while frontier:
            levels.append(frontier)
            nxt = []
            for u in frontier:
                for v in adj[u]:
                    if v not in seen:
                        seen.add(v)
                        nxt.append(v)
            frontier = nxt
    pos: dict[str, tuple[float, float]] = {}
    rows = len(levels)
    for li, level in enumerate(levels):
        if li:  # order by the mean x of neighbours already placed (fewer crossings)
            def key(n: str) -> float:
                xs = [pos[m][0] for m in adj[n] if m in pos]
                return sum(xs) / len(xs) if xs else 0.5
            level = sorted(level, key=key)
        y = 0.5 if rows == 1 else 1 - li / (rows - 1)
        for i, n in enumerate(level):
            pos[n] = ((i + 1) / (len(level) + 1), y)
    return pos


class Graph(Template):
    spec = GRAPH
    durations = {"create": 1.0, "dfs_step": 0.8, "bfs_level": 0.9, "path": 0.8, "ghost_edge": 0.7}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.adj = graph_adjacency(params.nodes, params.edges, params.directed)
        self.search = None
        self.search_state: dict[str, str] = {}  # node -> "current" | "visited"
        self.search_edges: set[tuple[str, str]] = set()
        self.hl_nodes: dict[str, str] = {}
        self.hl_edges: dict[tuple[str, str], str] = {}
        self.note_mob = self.ghost_mob = None
        self._layout()

    # ---- layout ---------------------------------------------------------

    def _key(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if self.p.directed else tuple(sorted((a, b)))

    def _layout(self) -> None:
        box = self.bounds
        unit = graph_positions(self.p.nodes, self.p.edges, self.p.layout)
        top, bottom = box.top - NOTE_ROW, box.bottom
        width, height = box.width, top - bottom
        xs = sorted({round(x, 6) for x, _ in unit.values()})
        ys = sorted({round(y, 6) for _, y in unit.values()})
        per_row = max(sum(1 for p in unit.values() if round(p[1], 6) == y) for y in ys)
        dx = width / (per_row + 1) if self.p.layout == "layers" else width / 3
        dy = height / max(len(ys), 1) if self.p.layout == "layers" else height / 3
        self.r = min(MAX_R, 0.32 * dx, 0.32 * dy)
        span_w, span_h = width - 2 * self.r - 0.1, height - 2 * self.r - 0.1
        if self.p.layout == "circle":
            span_w = span_h = min(span_w, span_h)
        cx, cy = box.center[0], (top + bottom) / 2
        self.pos = {n: np.array([cx + (x - 0.5) * span_w, cy + (y - 0.5) * span_h, 0.0]) for n, (x, y) in unit.items()}
        del xs
        self.note_y = box.top - NOTE_ROW / 2

    def _node(self, name: str) -> object:
        circle = Circle(radius=self.r, stroke_width=3, stroke_color=colour("BLUE"), fill_color=BLACK, fill_opacity=1)
        circle.move_to(self.pos[name])
        label = text(name, MIN_FONT, WHITE, max_width=self.r * 1.6).move_to(circle)
        return VGroup(circle, label).set_z_index(2)  # above every edge, the ghost edge too

    def _edge(self, a: str, b: str, col=None, width: float = 3) -> object:
        col = col or colour("GREY")
        if self.p.directed:
            e = Arrow(self.pos[a], self.pos[b], buff=self.r, stroke_width=width, color=col,
                      max_tip_length_to_length_ratio=0.18)
        else:
            e = Line(self.pos[a], self.pos[b], buff=self.r, stroke_width=width, color=col)
        return mark_background(e)

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
        self.edges = {self._key(a, b): self._edge(a, b) for a, b in self.p.edges}
        self.nodes = {n: self._node(n) for n in self.p.nodes}
        for e in self.edges.values():
            self.group.add(e)
        for n in self.nodes.values():
            self.group.add(n)
        anims = [Create(e) for e in self.edges.values()] + [FadeIn(n) for n in self.nodes.values()]
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
        anims = self._restyle(nodes, edges) + self.drop(self.ghost_mob, self.note_mob)
        self.ghost_mob = self.note_mob = None
        if anims:
            yield Step(anims)


__all__ = ["Graph"]
