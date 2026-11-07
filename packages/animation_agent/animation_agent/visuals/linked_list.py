"""LinkedList: nodes as boxes left to right with their links, named pointers above, null below, computed by the
spec's functions (specs.ll_insert, ll_delete, ll_reverse_step), the ones the checker runs.

Rows, top to bottom: the note row, the pointer rows (head and named pointers, each an arrow down to its node), the
nodes, the null row. A link between neighbours is a straight arrow: forward links (to the right) on the upper half
of the boxes, back links (to the left: a reversal, or a doubly linked list's prev) on the lower half. A node whose
link is null gets a short arrow down to "null" (the tail's, at the right end, goes right). Links and pointer arrows
are background for the layout audit; every link is redrawn after each change, while nodes keep their identity and
slide to their place."""

from __future__ import annotations

import copy

import numpy as np
from manim import WHITE, Arrow, CurvedArrow, DashedVMobject, RoundedRectangle, VGroup

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
from animation_agent.visuals.specs import LINKED_LIST, _fmt, ll_delete, ll_insert, ll_new, ll_order, ll_reverse_step

POINTER_ROW = 0.42
NULL_ROW = 0.5
MAX_BOX = 0.62


class LinkedList(Template):
    spec = LINKED_LIST
    durations = {"create": 0.9, "insert": 1.1, "delete": 1.0, "reverse_step": 1.0, "advance": 0.7, "find_step": 0.7,
                 "ghost": 0.7}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.st = ll_new(list(params.values), params.doubly)
        self.colours: dict[int, str] = {}
        self.node_mobs: dict[int, VGroup] = {}
        self.links = VGroup()
        self.pointer_mobs = VGroup()
        self.note_mob = self.ghost_mob = None
        self._layout()

    # ---- layout -----------------------------------------------------------

    def _layout(self) -> None:
        box = self.bounds
        self.note_y = box.top - NOTE_ROW / 2
        n = max(len(self.st["slots"]), 1) + 1  # a slot for the tail's null
        self.slot_w = box.width / n
        self.box = min(MAX_BOX, self.slot_w * 0.58)
        rows = 3  # pointer rows kept for head, curr, prev
        self.y = box.top - NOTE_ROW - POINTER_ROW * rows - self.box / 2
        self.y = max(self.y, box.bottom + NULL_ROW + self.box / 2)
        self.left = box.left

    def _x(self, slot: int) -> float:
        return self.left + self.slot_w * (slot + 0.5)

    def _slot_of(self, node: int) -> int:
        return self.st["slots"].index(node)

    # ---- drawing ------------------------------------------------------------

    def _node(self, i: int) -> VGroup:
        col = colour(self.colours[i]) if i in self.colours else colour("BLUE")
        rect = RoundedRectangle(width=self.box, height=self.box, corner_radius=0.06, stroke_width=4 if i in self.colours
                                else 3, stroke_color=col, fill_color=col, fill_opacity=0.25)
        rect.move_to([self._x(self._slot_of(i)), self.y, 0])
        value = text(_fmt(self.st["vals"][i]), MIN_FONT, WHITE, max_width=self.box * 0.85).move_to(rect)
        return VGroup(rect, value).set_z_index(2)

    def _arrow(self, a: np.ndarray, b: np.ndarray, col=None, width: float = 3):
        return mark_background(Arrow(a, b, buff=0, stroke_width=width, color=col or colour("GREY"),
                                     max_tip_length_to_length_ratio=0.3, max_stroke_width_to_length_ratio=12))

    def _links(self) -> VGroup:
        out = VGroup()
        half, slots = self.box / 2, self.st["slots"]
        for i in slots:
            j = self.st["nxt"].get(i)
            si = self._slot_of(i)
            x, y = self._x(si), self.y
            if j is None:
                if si == len(slots) - 1:  # the tail: an arrow right, to "null"
                    out.add(self._arrow(np.array([x + half, y + 0.08, 0]), np.array([self._x(si + 1) - 0.3, y + 0.08, 0])))
                    out.add(text("null", MIN_FONT, colour("GREY")).move_to([self._x(si + 1) + 0.02, y + 0.08, 0]))
                else:  # mid-reversal or a head at the left: down to "null"
                    out.add(self._arrow(np.array([x, y - half, 0]), np.array([x, y - half - NULL_ROW * 0.55, 0])))
                    out.add(text("null", MIN_FONT, colour("GREY")).move_to([x, y - half - NULL_ROW * 0.8, 0]))
                continue
            sj = self._slot_of(j)
            if abs(sj - si) == 1:
                dy = 0.08 if sj > si else -0.08
                sign = 1 if sj > si else -1
                out.add(self._arrow(np.array([x + sign * half, y + dy, 0]),
                                    np.array([self._x(sj) - sign * half, y + dy, 0])))
            else:
                out.add(mark_background(CurvedArrow(np.array([x, y + half, 0]), np.array([self._x(sj), y + half, 0]),
                                                    angle=-1.2 if sj > si else 1.2, color=colour("GREY"),
                                                    stroke_width=3, tip_length=0.12)))
        if self.st["doubly"]:  # prev links: from each node back to the one before it, on the lower half
            order = ll_order(self.st)
            for a, b in zip(order, order[1:]):
                sa, sb = self._slot_of(a), self._slot_of(b)
                if abs(sa - sb) == 1:
                    sign = 1 if sa > sb else -1
                    out.add(self._arrow(np.array([self._x(sb) + sign * half, self.y - 0.1, 0]),
                                        np.array([self._x(sa) - sign * half, self.y - 0.1, 0]), colour("TEAL")))
        return out

    def _pointers(self) -> VGroup:
        """Each pointer's name above its node, an arrow down to it; a name that would touch another (on the same
        node, or a neighbour's) goes a row higher."""
        out = VGroup()
        placed: list[tuple[int, float, float]] = []  # (row, left, right) of each name so far
        names = [("head", self.st["head"])] + [(n, t) for n, t in self.st["ptrs"].items() if n != "head"]
        top = self.y + self.box / 2
        for name, target in names:
            if target is None or target not in self.st["slots"]:
                continue
            x = self._x(self._slot_of(target))
            label = text(name, MIN_FONT, colour("GOLD") if name == "head" else colour("YELLOW"))
            lo, hi = x - label.width / 2 - 0.04, x + label.width / 2 + 0.04
            row = 0
            while any(r == row and not (hi < a or lo > b) for r, a, b in placed):
                row += 1
            placed.append((row, lo, hi))
            y = top + POINTER_ROW * (row + 0.75)
            label.move_to([x, y, 0])
            out.add(label)
            if not any(r < row and a <= x <= b for r, a, b in placed[:-1]):  # an arrow only from the lowest name
                out.add(self._arrow(np.array([x, y - label.height / 2 - 0.03, 0]), np.array([x, top + 0.02, 0]),
                                    colour("GOLD"), 3))
        return out

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    def _refresh(self, moved: bool = True) -> list:
        """Every node to its place and colour, every link and pointer redrawn."""
        anims = []
        for i in list(self.node_mobs):
            if i not in self.st["vals"]:
                anims += self.drop(self.node_mobs.pop(i))
        for i in self.st["slots"]:
            target = self._node(i)
            if i in self.node_mobs:
                moves, self.node_mobs[i] = self.morph(self.node_mobs[i], target)
                anims += moves
            else:
                self.node_mobs[i] = target
                anims += self.add(target)
        anims += self.drop(self.links, self.pointer_mobs)
        self.links, self.pointer_mobs = self._links(), self._pointers()
        return anims + self.add(self.links, self.pointer_mobs)

    # ---- create and actions ------------------------------------------------------

    def create(self) -> Steps:
        anims = self._refresh()
        if self.p.title:
            anims += self._note(self.p.title, colour("GREY"))
        yield Step(anims)

    def point(self, a) -> Steps:
        self.st["ptrs"][a.name] = None if a.index is None else self.st["slots"][a.index]
        yield Step(self._refresh())

    def advance(self, a) -> Steps:
        at = self.st["ptrs"][a.name]
        self.st["ptrs"][a.name] = self.st["nxt"][at]
        yield Step(self._refresh())

    def _raised(self, index: int) -> np.ndarray:
        """Where a new node waits above the row before it is linked in: over the gap it goes into."""
        order = ll_order(self.st)
        n = len(order)
        x = self._x(0) - self.slot_w * 0.5 if index == 0 else (self._x(index - 1) + self.slot_w * 0.5 if index < n
                                                               else self._x(n - 1) + self.slot_w * 0.5)
        return np.array([x, self.y - self.box * 1.9, 0.0])

    def insert(self, a) -> Steps:
        """In the order code does it: the new node points to the one it goes before, then the node before it (or
        head) points to it, then the row makes room."""
        order = ll_order(self.st)
        succ = order[a.index] if a.index < len(order) else None
        pred = order[a.index - 1] if a.index > 0 else None
        spot = self._raised(a.index)
        rect = RoundedRectangle(width=self.box, height=self.box, corner_radius=0.06, stroke_color=colour("GOLD"),
                                stroke_width=4, fill_color=colour("GOLD"), fill_opacity=0.25).move_to(spot)
        node = VGroup(rect, text(_fmt(a.value), MIN_FONT, WHITE, max_width=self.box * 0.85).move_to(rect))
        node.set_z_index(2)
        half = self.box / 2
        if succ is not None:
            to = np.array([self._x(self._slot_of(succ)), self.y - half, 0])
        else:
            to = spot + np.array([self.slot_w * 0.6, 0, 0])
        new_link = self._arrow(spot + np.array([0, half, 0]) if succ is not None else spot + np.array([half, 0, 0]),
                               to, colour("GOLD"))
        yield Step(self.add(node, new_link), 0.35)
        # The node before it (or head) now points to the new node.
        if pred is not None:
            src = np.array([self._x(self._slot_of(pred)), self.y - half, 0])
            re_link = self._arrow(src, spot + np.array([-half * 0.6, half, 0]), colour("GOLD"))
        else:  # a new head: head now points to it
            re_link = self._arrow(spot + np.array([-half - 0.35, 0, 0]), spot + np.array([-half, 0, 0]),
                                  colour("GOLD"))
        yield Step(self.add(re_link), 0.3)
        ll_insert(self.st, a.index, a.value)
        new = self.st["last"]["id"]
        self.node_mobs[new] = node  # slides down into its place
        self.colours[new] = "GOLD"
        self._layout()
        yield Step(self._refresh() + self.drop(new_link, re_link), 0.35)

    def delete(self, a) -> Steps:
        """The node before it skips over it (its link now jumps to the next one), then it goes."""
        order = ll_order(self.st)
        gone = order[a.index]
        pred = order[a.index - 1] if a.index > 0 else None
        succ = self.st["nxt"][gone]
        self.colours[gone] = "RED"
        yield Step([self.node_mobs[gone].animate.become(self._node(gone))], 0.25)
        half = self.box / 2
        sg = self._slot_of(gone)
        if pred is not None and succ is not None:
            bypass = CurvedArrow(np.array([self._x(sg - 1), self.y - half, 0]),
                                 np.array([self._x(self._slot_of(succ)), self.y - half, 0]), angle=1.3,
                                 color=colour("GOLD"), stroke_width=4, tip_length=0.12)
            bypass = mark_background(bypass)
            yield Step(self.add(bypass), 0.35)
        else:
            bypass = None
        ll_delete(self.st, a.index)
        self.colours.pop(gone, None)
        self._layout()
        yield Step(self._refresh() + self.drop(bypass), 0.4)

    def find_step(self, a) -> Steps:
        from animation_agent.visuals.specs import _check_ll_find

        st = copy.deepcopy(self.st)
        _check_ll_find(st, a)
        self.st["find"], self.st["ptrs"] = st["find"], st["ptrs"]
        ev = st["last"]
        self.colours = {k: v for k, v in self.colours.items() if v != "YELLOW"}
        if ev["id"] is not None:
            self.colours[ev["id"]] = "GREEN" if ev["hit"] else "YELLOW"
        yield Step(self._refresh() + self._note(f"checks: {ev['checks']}", colour("GOLD")))

    def reverse_step(self, a) -> Steps:
        ll_reverse_step(self.st)
        for i in self.st["rev"]["flipped"]:
            self.colours[i] = "TEAL"  # reversed so far
        if self.st["rev"]["done"]:
            self.st["ptrs"].pop("curr", None)
        yield Step(self._refresh())

    def highlight(self, a) -> Steps:
        for k in a.indices:
            self.colours[self.st["slots"][k]] = a.colour
        yield Step(self._refresh())

    def ghost(self, a) -> Steps:
        old = self.ghost_mob
        src = self._x(a.from_index)
        top = self.y + self.box / 2
        if a.to_index is None:
            end = np.array([src, self.y - self.box / 2 - NULL_ROW * 0.6, 0])
            arrow = Arrow(np.array([src + 0.06, self.y - self.box / 2, 0]), end, buff=0, color=GHOST_COLOUR,
                          stroke_width=4, max_tip_length_to_length_ratio=0.3)
        else:
            arrow = CurvedArrow(np.array([src, top, 0]), np.array([self._x(a.to_index), top, 0]),
                                angle=-1.0 if a.to_index > a.from_index else 1.0, color=GHOST_COLOUR, stroke_width=4,
                                tip_length=0.12)
        self.ghost_mob = mark_background(DashedVMobject(arrow, num_dashes=12)).set_z_index(1)
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        self.colours = {k: v for k, v in self.colours.items() if v == "TEAL" and self.st["rev"]}
        anims = self._refresh() + self.drop(self.ghost_mob, self.note_mob)
        self.ghost_mob = self.note_mob = None
        yield Step(anims)


__all__ = ["LinkedList"]
