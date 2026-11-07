"""StackQueue: a stack or call stack as a column (bottom at the base, "top" beside the top item), a queue or deque as
a row ("front" and "rear" under its ends). Items slide in and out at the end the operation uses; the spec's
_sq_op is the one the checker runs, so what comes out is always what the structure gives."""

from __future__ import annotations

import copy

import numpy as np
from manim import DOWN, LEFT, RIGHT, UP, WHITE, Arrow, DashedVMobject, Line, RoundedRectangle, VGroup

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
from animation_agent.visuals.specs import MAX_SQ, STACK_QUEUE, _fmt, _sq_op

CELL_H = 0.5
LABEL_ROW = 0.42


class StackQueue(Template):
    spec = STACK_QUEUE
    durations = {"create": 0.8, "push": 0.8, "pop": 0.9, "enqueue": 0.8, "dequeue": 0.9, "push_front": 0.8,
                 "push_back": 0.8, "pop_front": 0.9, "pop_back": 0.9, "peek": 0.6, "ghost": 0.7}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.kind = params.kind
        self.st = {"kind": params.kind, "items": list(params.values), "last": None}
        self.vertical = params.kind in ("stack", "call_stack")
        self.cells: list[VGroup] = []
        self.colours: dict[int, str] = {}
        self.labels = VGroup()
        self.note_mob = self.ghost_mob = None
        self._layout()

    def _layout(self) -> None:
        box = self.bounds
        self.note_y = box.top - NOTE_ROW / 2
        if self.vertical:  # a call stack's frames hold a call such as "fact(3)"
            self.cell_w = min(box.width * 0.6, 2.6) if self.kind == "call_stack" else 0.9
            room = max(len(self.st["items"]) + 2, 4)
            self.cell_h = max(0.42, min(CELL_H, (box.height - NOTE_ROW - 0.2) / room))
            self.base = box.bottom + 0.15
            self.cx = box.center[0] - 0.3
        else:
            self.cell_w = min(0.62, box.width / (MAX_SQ + 1))
            self.cell_h = self.cell_w
            self.cy = box.bottom + LABEL_ROW + (box.height - NOTE_ROW - LABEL_ROW) / 2
            self.left = box.center[0] - self.cell_w * MAX_SQ / 2

    def _pos(self, k: int) -> np.ndarray:
        if self.vertical:
            return np.array([self.cx, self.base + self.cell_h * (k + 0.5), 0.0])
        return np.array([self.left + self.cell_w * (k + 0.5), self.cy, 0.0])

    def _cell(self, k: int, value) -> VGroup:
        col = colour(self.colours[k]) if k in self.colours else colour("BLUE")
        rect = RoundedRectangle(width=self.cell_w * 0.94, height=self.cell_h * 0.9, corner_radius=0.05,
                                stroke_color=col, stroke_width=4 if k in self.colours else 3, fill_color=col,
                                fill_opacity=0.25).move_to(self._pos(k))
        label = text(_fmt(value), MIN_FONT, WHITE, max_width=self.cell_w * 0.85).move_to(rect)
        return VGroup(rect, label)

    def _end_labels(self) -> VGroup:
        out, n = VGroup(), len(self.st["items"])
        if self.vertical:
            base = mark_background(Line(self._pos(0) + [-self.cell_w * 0.6, -self.cell_h / 2, 0],
                                        self._pos(0) + [self.cell_w * 0.6, -self.cell_h / 2, 0],
                                        color=colour("GREY"), stroke_width=3))
            out.add(base)
            if n:
                tip = self._pos(n - 1) + [self.cell_w / 2 + 0.08, 0, 0]
                arrow = mark_background(Arrow(tip + [0.5, 0, 0], tip, buff=0, color=colour("GOLD"), stroke_width=3,
                                              max_tip_length_to_length_ratio=0.3))
                out.add(arrow, text("top", MIN_FONT, colour("GOLD")).next_to(arrow, RIGHT, buff=0.06))
            return out
        if n:
            front = text("front", MIN_FONT, colour("GOLD")).next_to(self._pos(0), DOWN, buff=self.cell_h / 2 + 0.06)
            out.add(front)
            if n > 1 or self.kind == "deque":
                rear = text("rear" if self.kind == "queue" else "back", MIN_FONT, colour("GOLD"))
                rear.next_to(self._pos(n - 1), DOWN, buff=self.cell_h / 2 + 0.06)
                if n == 1 or rear.get_left()[0] < front.get_right()[0] + 0.05:
                    rear.next_to(front, RIGHT, buff=0.1)
                out.add(rear)
        return out

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    def _refresh(self) -> list:
        self._layout()
        anims = []
        for k, v in enumerate(self.st["items"]):
            target = self._cell(k, v)
            if k < len(self.cells):
                moves, self.cells[k] = self.morph(self.cells[k], target)
                anims += moves
            else:
                self.cells.append(target)
                anims += self.add(target)
        anims += self.drop(self.labels)
        self.labels = self._end_labels()
        return anims + self.add(self.labels)

    def create(self) -> Steps:
        anims = self._refresh()
        if self.p.title:
            anims += self._note(self.p.title, colour("GREY"))
        yield Step(anims)

    def _run(self, op: str, a) -> None:
        st = copy.deepcopy(self.st)
        _sq_op(op)(st, a)
        self.st = st

    def _put(self, op: str, a, front: bool) -> Steps:
        self._run(op, a)
        self.colours = {}
        if front:  # everything shifts one place back to make room at the front
            new = self._cell(0, self.st["items"][0])
            shift = RIGHT * self.cell_w if not self.vertical else UP * self.cell_h
            anims = [c.animate.shift(shift) for c in self.cells]
            self.cells.insert(0, new)
            new.shift(-shift)
            yield Step(anims + self.add(new) + [new.animate.shift(shift)], 0.6)
            yield Step(self._refresh(), 0.4)
            return
        k = len(self.st["items"]) - 1
        new = self._cell(k, self.st["items"][k])
        start = (UP * 1.0) if self.vertical else (RIGHT * 0.8)
        new.shift(start)
        self.cells.append(new)
        yield Step(self.add(new) + [new.animate.shift(-start)], 0.6)
        yield Step(self._refresh(), 0.4)

    def _take(self, op: str, a, front: bool) -> Steps:
        k = 0 if front else len(self.st["items"]) - 1
        self.colours = {k: "GOLD"}
        yield Step(self._refresh(), 0.3)
        self._run(op, a)
        gone = self.cells.pop(k)
        away = (UP * 0.9) if self.vertical else (LEFT * 0.8 if front else RIGHT * 0.8)
        self.colours = {}
        self.group.remove(gone)
        anims = [gone.animate.shift(away).set_opacity(0)]
        if self.kind == "call_stack" and getattr(a, "returns", None) is not None:
            anims += self._note(f"returns {_fmt(a.returns)}", colour("GOLD"))
        yield Step(anims, 0.4)
        self.scene.remove(gone)
        yield Step(self._refresh(), 0.3)

    def push(self, a) -> Steps:
        yield from self._put("push", a, front=False)

    def enqueue(self, a) -> Steps:
        yield from self._put("enqueue", a, front=False)

    def push_back(self, a) -> Steps:
        yield from self._put("push_back", a, front=False)

    def push_front(self, a) -> Steps:
        yield from self._put("push_front", a, front=True)

    def pop(self, a) -> Steps:
        yield from self._take("pop", a, front=False)

    def pop_back(self, a) -> Steps:
        yield from self._take("pop_back", a, front=False)

    def dequeue(self, a) -> Steps:
        yield from self._take("dequeue", a, front=True)

    def pop_front(self, a) -> Steps:
        yield from self._take("pop_front", a, front=True)

    def peek(self, a) -> Steps:
        k = 0 if self.kind == "queue" else len(self.st["items"]) - 1
        self.colours = {k: "YELLOW"}
        yield Step(self._refresh())

    def highlight(self, a) -> Steps:
        for k in a.positions:
            self.colours[k] = a.colour
        yield Step(self._refresh())

    def ghost(self, a) -> Steps:
        old = self.ghost_mob
        n = max(len(self.st["items"]), 1)
        if self.vertical:
            k = n - 1 if a.end in ("top", "rear") else 0
            p = self._pos(k) + [-self.cell_w / 2 - 0.1, 0, 0]
            arrow = Arrow(p + [-0.6, 0, 0], p, buff=0, color=GHOST_COLOUR, stroke_width=4)
        else:
            k = 0 if a.end in ("front", "bottom") else n - 1
            p = self._pos(k) + [0, self.cell_h / 2 + 0.08, 0]
            arrow = Arrow(p + [0, 0.6, 0], p, buff=0, color=GHOST_COLOUR, stroke_width=4)
        self.ghost_mob = mark_background(DashedVMobject(arrow, num_dashes=8))
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        self.colours = {}
        anims = self._refresh() + self.drop(self.ghost_mob, self.note_mob)
        self.ghost_mob = self.note_mob = None
        yield Step(anims)


__all__ = ["StackQueue"]
