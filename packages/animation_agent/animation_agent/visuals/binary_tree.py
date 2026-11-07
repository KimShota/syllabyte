"""BinaryTree: a binary search tree, or a binary heap with the array it lives in drawn under it (the two views of one
structure: the array is the implementation, the tree the idea). Every operation is computed by the spec's functions
(specs.bst_insert, bst_search, bst_delete, heap_push, heap_pop, heap_heapify, bt_order), the ones the checker runs.

A BST's nodes sit left to right in sorted order (by in-order rank) and down by depth, so no two ever overlap, even
in a lopsided tree. A heap's sit where a complete binary tree puts them. A path down the tree lights up node by node;
a heap's swaps play one after another, in the tree and the array together. Edges are background for the layout
audit."""

from __future__ import annotations

import copy

import numpy as np
from manim import WHITE, Circle, DashedVMobject, Dot, Line, MoveAlongPath, RoundedRectangle, VGroup, VMobject

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
from animation_agent.visuals.specs import (
    BINARY_TREE,
    MAX_TREE_DEPTH,
    MAX_TREE_NODES,
    bst_delete,
    bst_insert,
    bt_new,
    bt_step,
    heap_heapify,
    heap_pop,
    heap_push,
)

MAX_R = 0.25
MIN_R = 0.215
ARRAY_ROW = 0.5
INDEX_ROW = 0.32


class BinaryTree(Template):
    spec = BINARY_TREE
    durations = {"create": 1.0, "insert": 1.3, "search": 1.2, "delete": 1.1, "push": 1.3, "pop": 1.4,
                 "heapify": 1.8, "traverse_step": 0.7, "ghost": 0.7, "insert_step": 0.9, "search_step": 0.9,
                 "push_step": 0.9, "pop_step": 1.0, "heapify_step": 0.9}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.st = bt_new(params.kind, list(params.values))
        self.heap = params.kind != "bst"
        self.array = self.heap and params.show_array
        self.colours: dict[int, str] = {}  # node id (BST) or array index (heap) -> colour
        self.visited: list[int] = []
        self.node_mobs: dict[int, VGroup] = {}
        self.edges = VGroup()
        self.cells: dict[int, VGroup] = {}
        self.note_mob = self.ghost_mob = None
        self._layout()

    # ---- layout ---------------------------------------------------------------

    def _layout(self) -> None:
        box = self.bounds
        self.note_y = box.top - NOTE_ROW / 2
        bottom = box.bottom + ((ARRAY_ROW + INDEX_ROW + 0.15) if self.array else 0.05)
        top = box.top - NOTE_ROW - 0.05
        # Room for the tree it is now plus one level (an insert or a push), re-laid out if it grows past that:
        # sizing for the largest tree allowed left two-digit values bursting out of their circles.
        if self.heap:
            levels = max(3, (len(self.st["heap"]) + 1).bit_length())
            slots = 2 ** (levels - 1)
        else:
            from animation_agent.visuals.specs import bt_depth

            levels = max(3, min(MAX_TREE_DEPTH, bt_depth(self.st) + 1))
            slots = max(4, len(self.st["nodes"]) + 1)
        self.levels = levels
        self.row_h = (top - bottom) / levels
        self.top, self.width = top, box.width
        self.r = min(MAX_R, 0.42 * box.width / slots * (2 if not self.heap else 1), 0.32 * self.row_h)
        # A two-digit value at the smallest readable size needs a circle about 0.42 across: eight leaves in a row
        # still leave a gap between them at that size.
        self.r = max(self.r, min(MIN_R, 0.48 * box.width / slots * (2 if not self.heap else 1)))
        self.left = box.left
        self.array_y = box.bottom + INDEX_ROW + ARRAY_ROW / 2
        self.cell_w = min(0.55, box.width / max(len(self.st["heap"]) + 1, 6))  # the array as it is, one to grow

    def _positions(self) -> dict[int, np.ndarray]:
        """Where each node sits: by in-order rank (BST) or in complete-tree places (heap)."""
        out = {}
        if self.heap:
            n = len(self.st["heap"])
            for i in range(n):
                level = (i + 1).bit_length() - 1
                k = i - (2 ** level - 1)
                x = self.left + self.width * (k + 0.5) / 2 ** level
                out[i] = np.array([x, self.top - self.row_h * (level + 0.5), 0.0])
            return out
        nodes = self.st["nodes"]
        order, depth = [], {}

        def walk(i, d):
            if i is None:
                return
            walk(nodes[i]["l"], d + 1)
            order.append(i)
            depth[i] = d
            walk(nodes[i]["r"], d + 1)

        walk(self.st["root"], 0)
        n = max(len(order), 1)
        for rank, i in enumerate(order):
            x = self.left + self.width * (rank + 0.5) / n
            out[i] = np.array([x, self.top - self.row_h * (depth[i] + 0.5), 0.0])
        return out

    def _value(self, i: int) -> int:
        return self.st["heap"][i] if self.heap else self.st["nodes"][i]["v"]

    def _children(self, i: int) -> list[int]:
        if self.heap:
            return [c for c in (2 * i + 1, 2 * i + 2) if c < len(self.st["heap"])]
        n = self.st["nodes"][i]
        return [c for c in (n["l"], n["r"]) if c is not None]

    # ---- drawing ------------------------------------------------------------------

    def _node(self, i: int, pos) -> VGroup:
        state = self.colours.get(i) or ("TEAL" if i in self.visited else None)
        col = colour(state) if state else colour("BLUE")
        circle = Circle(radius=self.r, stroke_color=col, stroke_width=5 if state else 3, fill_color="#000000",
                        fill_opacity=1).move_to(pos)
        return VGroup(circle, text(str(self._value(i)), MIN_FONT, WHITE, max_width=self.r * 1.75).move_to(pos)
                      ).set_z_index(2)

    def _edges(self, pos) -> VGroup:
        out = VGroup()
        for i, p in pos.items():
            for c in self._children(i):
                q = pos[c]
                d = (q - p) / max(np.linalg.norm(q - p), 1e-6)
                out.add(mark_background(Line(p + d * self.r, q - d * self.r, color=colour("GREY"), stroke_width=3)))
        return out

    def _cell(self, i: int) -> VGroup:
        n = len(self.st["heap"])
        x0 = self.bounds.center[0] - self.cell_w * n / 2
        state = self.colours.get(i)
        col = colour(state) if state else colour("BLUE")
        rect = RoundedRectangle(width=self.cell_w * 0.94, height=ARRAY_ROW * 0.84, corner_radius=0.05,
                                stroke_color=col, stroke_width=4 if state else 2, fill_color=col,
                                fill_opacity=0.25).move_to([x0 + self.cell_w * (i + 0.5), self.array_y, 0])
        value = text(str(self.st["heap"][i]), MIN_FONT, WHITE, max_width=self.cell_w * 0.85).move_to(rect)
        index = text(str(i), MIN_FONT, colour("GREY")).move_to([rect.get_center()[0], self.array_y - ARRAY_ROW / 2
                                                                 - INDEX_ROW / 2 + 0.02, 0])
        return VGroup(rect, value, index)

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    def _refresh(self) -> list:
        self._layout()
        pos = self._positions()
        anims = []
        for i in list(self.node_mobs):
            if i not in pos:
                anims += self.drop(self.node_mobs.pop(i))
        for i, p in pos.items():
            target = self._node(i, p)
            if i in self.node_mobs:
                moves, self.node_mobs[i] = self.morph(self.node_mobs[i], target)
                anims += moves
            else:
                self.node_mobs[i] = target
                anims += self.add(target)
        anims += self.drop(self.edges)
        self.edges = self._edges(pos)
        anims += self.add(self.edges)
        if self.array:
            n = len(self.st["heap"])
            for i in list(self.cells):
                if i >= n:
                    anims += self.drop(self.cells.pop(i))
            for i in range(n):
                target = self._cell(i)
                if i in self.cells:
                    moves, self.cells[i] = self.morph(self.cells[i], target)
                    anims += moves
                else:
                    self.cells[i] = target
                    anims += self.add(target)
        return anims

    # ---- actions --------------------------------------------------------------------

    def create(self) -> Steps:
        anims = self._refresh()
        if self.p.title:
            anims += self._note(self.p.title, colour("GREY"))
        yield Step(anims)

    def _path_ids(self, values: list[int]) -> list[int]:
        by_value = {n["v"]: i for i, n in self.st["nodes"].items()}
        return [by_value[v] for v in values if v in by_value]

    def _walk(self, path_values: list[int]) -> Steps:
        ids = self._path_ids(path_values)
        share = 0.5 / max(len(ids), 1)
        for i in ids:
            self.colours = {k: c for k, c in self.colours.items() if c != "YELLOW"} | {i: "YELLOW"}
            yield Step(self._refresh(), share)

    def insert(self, a) -> Steps:
        before = copy.deepcopy(self.st)
        ev = bst_insert(before, a.value)
        yield from self._walk([v for v, _ in ev["path"]])
        bst_insert(self.st, a.value)
        new = next(i for i, n in self.st["nodes"].items() if n["v"] == a.value)
        self.colours = {new: "GOLD"}
        yield Step(self._refresh(), 0.5)

    def search(self, a) -> Steps:
        from animation_agent.visuals.specs import bst_search

        ev = bst_search(self.st, a.value)
        yield from self._walk([v for v, _ in ev["path"]])
        self.colours = {}
        if ev["found"]:
            self.colours = {self._path_ids([a.value])[0]: "GREEN"}
            yield Step(self._refresh(), 0.5)
        else:
            yield Step(self._refresh() + self._note(f"{a.value} isn't in the tree", colour("RED")), 0.5)

    def delete(self, a) -> Steps:
        target = self._path_ids([a.value])[0]
        self.colours = {target: "RED"}
        yield Step(self._refresh(), 0.4)
        bst_delete(self.st, a.value)
        self.colours = {}
        yield Step(self._refresh(), 0.6)

    def _swaps(self, swaps: list, final: list[int]) -> Steps:
        share = 0.6 / max(len(swaps), 1)
        for i, j in swaps:
            h = self.st["heap"]
            h[i], h[j] = h[j], h[i]
            self.colours = {i: "YELLOW", j: "YELLOW"}
            yield Step(self._refresh(), share)
        self.st["heap"] = list(final)
        self.colours = {}
        yield Step(self._refresh(), 0.15)

    def push(self, a) -> Steps:
        after = copy.deepcopy(self.st)
        ev = heap_push(after, a.value)
        self.st["heap"].append(a.value)
        self.colours = {len(self.st["heap"]) - 1: "GOLD"}
        yield Step(self._refresh(), 0.25)
        yield from self._swaps(ev["swaps"], after["heap"])

    def pop(self, a) -> Steps:
        after = copy.deepcopy(self.st)
        ev = heap_pop(after)
        self.colours = {0: "GOLD"}
        yield Step(self._refresh() + self._note(f"out: {ev['v']}", colour("GOLD")), 0.15)
        h = self.st["heap"]
        last = h.pop()
        if h:
            h[0] = last
        self.colours = {}
        yield Step(self._refresh(), 0.1)
        yield from self._swaps(ev["swaps"], after["heap"])

    def heapify(self, a) -> Steps:
        after = copy.deepcopy(self.st)
        ev = heap_heapify(after)
        yield from self._swaps(ev["swaps"], after["heap"])

    # ---- one comparison or swap per call ------------------------------------------------------------------------

    def insert_step(self, a) -> Steps:
        ev = bt_step(self.st, "insert", a.value)
        if ev["new"] is None:
            self.colours = {ev["at"]: "YELLOW"}
            yield Step(self._refresh() + self._note(f"insert {a.value}: {a.value} "
                                                    f"{'<' if ev['dir'] == 'left' else '>'} {ev['with']}, go "
                                                    f"{ev['dir']}", colour("GOLD")))
            return
        self.colours = {ev["new"]: "GOLD"}
        where = "the root" if ev["at"] is None else f"{ev['with']}'s {ev['dir']} child"
        yield Step(self._refresh() + self._note(f"{a.value} becomes {where}", colour("GOLD")))

    def search_step(self, a) -> Steps:
        ev = bt_step(self.st, "search", a.value)
        if ev["at"] is None:
            yield Step(self._note(f"{a.value} isn't in the tree", colour("RED")))
            return
        if ev["found"]:
            self.colours = {ev["at"]: "GREEN"}
            yield Step(self._refresh() + self._note(f"{a.value} = {ev['with']}: found", colour("GREEN")))
            return
        self.colours = {ev["at"]: "YELLOW"}
        sign = "<" if ev["dir"] == "left" else ">"
        note = (f"find {a.value}: {a.value} {sign} {ev['with']}, go {ev['dir']}" if not ev["end"]
                else f"{a.value} {sign} {ev['with']}: no {ev['dir']} child")
        yield Step(self._refresh() + self._note(note, colour("RED") if ev["end"] else colour("GOLD")))

    def _swap_step(self, ev) -> Steps:
        """A comparison of two places in the heap (already swapped in self.st if `swapped`)."""
        i, j = ev["at"], ev["other"]
        if ev["swapped"]:
            h = self.st["heap"]
            h[i], h[j] = h[j], h[i]  # the values as they were, both yellow; then swapped
            self.colours = {i: "YELLOW", j: "YELLOW"}
            yield Step(self._refresh(), 0.4)
            h[i], h[j] = h[j], h[i]
            self.colours = {j: "GOLD"}
            yield Step(self._refresh() + self._note(f"swap {ev['v']} and {ev['with']}", colour("GOLD")), 0.6)
        else:
            self.colours = {i: "GOLD", j: "YELLOW"}
            yield Step(self._refresh() + self._note(f"{ev['v']} stays", colour("GREY")))
        if ev["end"]:
            self.colours = {}

    def push_step(self, a) -> Steps:
        ev = bt_step(self.st, "push", a.value)
        if "placed" in ev:
            self.colours = {ev["placed"]: "GOLD"}
            yield Step(self._refresh() + self._note(f"push {a.value}", colour("GOLD")))
            return
        yield from self._swap_step(ev)

    def pop_step(self, a) -> Steps:
        before = list(self.st["heap"])
        ev = bt_step(self.st, "pop")
        if "out" in ev:
            after = self.st["heap"]
            self.st["heap"] = before
            self.colours = {0: "GOLD"}
            yield Step(self._refresh() + self._note(f"out: {ev['out']}", colour("GOLD")), 0.45)
            self.st["heap"] = after
            self.colours = {0: "YELLOW"} if after else {}
            yield Step(self._refresh(), 0.55)
            return
        yield from self._swap_step(ev)

    def heapify_step(self, a) -> Steps:
        ev = bt_step(self.st, "heapify")
        yield from self._swap_step(ev)

    def traverse_step(self, a) -> Steps:
        from animation_agent.visuals.specs import _check_traverse

        st = copy.deepcopy(self.st)
        _check_traverse(st, a)
        self.st["trav"] = st["trav"]
        ev = st["last"]
        ids = list(range(len(self.st["heap"]))) if self.heap else self._path_ids([ev["v"]])
        current = self.st["heap"].index(ev["v"]) if self.heap else ids[0]
        walk = self._tree_path(self.visited[-1] if self.visited else None, current)
        self.visited = [i for i in self.visited if i != current] + [current]
        self.colours = {current: "YELLOW"}
        pos = self._positions()
        points = [pos[i] + np.array([-self.r * 1.05, self.r * 1.05, 0]) for i in walk if i in pos]  # outside the circle
        if getattr(self, "cursor", None) is None:
            self.cursor = Dot(points[0], radius=0.07, color=colour("GOLD")).set_z_index(3)
            yield Step(self.add(self.cursor), 0.1)
        if len(points) > 1:  # the recursion's route: down to the node, or back up and down again
            path = VMobject().set_points_as_corners(points)
            yield Step([MoveAlongPath(self.cursor, path)], 0.45)
        seen = ", ".join(map(str, ev["seen"]))
        note = f"{a.order}: {seen}"
        while text(note, MIN_FONT).width > self.bounds.width and ", " in seen:  # the latest values, if all don't fit
            seen = seen.split(", ", 1)[1]
            note = f"{a.order}: ... {seen}"
        yield Step(self._refresh() + self._note(note, colour("TEAL")), 0.45)  # the shares of a call add to 1

    def _parent(self, i: int) -> int | None:
        if self.heap:
            return (i - 1) // 2 if i > 0 else None
        return next((k for k, n in self.st["nodes"].items() if i in (n["l"], n["r"])), None)

    def _tree_path(self, a: int | None, b: int) -> list[int]:
        """The nodes from a to b along the tree's edges (from the root, if a is None)."""
        def up(i):
            out = []
            while i is not None:
                out.append(i)
                i = self._parent(i)
            return out
        root = 0 if self.heap else self.st["root"]
        pa, pb = up(a) if a is not None else [root], up(b)
        common = next((i for i in pa if i in pb), root)
        return pa[:pa.index(common) + 1] + list(reversed(pb[:pb.index(common)]))

    def highlight(self, a) -> Steps:
        for v in a.values:
            i = self.st["heap"].index(v) if self.heap else self._path_ids([v])[0]
            self.colours[i] = a.colour
        yield Step(self._refresh())

    def ghost(self, a) -> Steps:
        old = self.ghost_mob
        pos = self._positions()
        parent = self.st["heap"].index(a.parent) if self.heap else self._path_ids([a.parent])[0]
        p = pos[parent]
        level = round((self.top - p[1]) / self.row_h - 0.5)
        dx = self.width / 2 ** (level + 2)
        q = p + np.array([-dx if a.side == "left" else dx, -self.row_h, 0])
        ring = DashedVMobject(Circle(radius=self.r, color=GHOST_COLOUR, stroke_width=4).move_to(q), num_dashes=14)
        link = DashedVMobject(Line(p, q, buff=self.r, color=GHOST_COLOUR, stroke_width=3), num_dashes=6)
        self.ghost_mob = VGroup(mark_background(link), ring, text(str(a.value), MIN_FONT, GHOST_COLOUR).move_to(q))
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        self.colours = {}
        anims = self._refresh() + self.drop(self.ghost_mob, self.note_mob)
        self.ghost_mob = self.note_mob = None
        yield Step(anims)


__all__ = ["BinaryTree"]
