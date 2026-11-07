"""ArrayBars: a list as cells (or bars) with index numbers, named pointers, a note line and a counter."""

from __future__ import annotations

import numpy as np
from manim import (
    GREY_B,
    WHITE,
    Arrow,
    DashedVMobject,
    Rectangle,
    Square,
    SurroundingRectangle,
    VGroup,
)

from animation_agent.visuals.base import (
    DOWN,
    GHOST_COLOUR,
    GREYED,
    MIN_FONT,
    NOTE_ROW,
    UP,
    Step,
    Steps,
    Template,
    colour,
    text,
)
from animation_agent.visuals.specs import ARRAY_BARS, _fmt, bisect_next, sort_events

INDEX_ROW = 0.36
ARROW_LEN = 0.3
SLOT = 0.3  # vertical spacing of stacked pointer labels
MAX_SLOTS = 3
COUNTER_ROW = 0.4
MAX_CELL = 0.62
BAR_MAX = 1.6


class ArrayBars(Template):
    spec = ARRAY_BARS
    durations = {"create": 0.8, "swap": 0.9, "partition_step": 1.1, "bisect_check": 1.0, "bisect_discard": 1.0, "bisect_step": 1.8,
                 "ghost": 0.8, "scan": 0.7, "bubble_step": 1.0, "bubble_pass": 2.4, "selection_step": 1.2,
                 "insertion_step": 1.2}
    SORT_ACTIONS = ("bubble_step", "bubble_pass", "selection_step", "insertion_step")

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.values = list(params.values)
        self.base = colour(params.colour)
        self.n = len(self.values)
        self.cell_state = ["base"] * self.n  # "base" | "grey" | a colour name
        self.pointers: dict[str, int] = {}
        self.pointer_mobs: dict[str, VGroup] = {}
        self.note_mob = None
        self.counter_mob = None
        self.counters: dict[str, int] = {}
        self.ghost_mob = None
        self.note_spec = None  # (text, colour) of the note on screen
        self.bisect = None
        self.sort = None  # a sort's progress (specs.new_sort)
        self._layout()

    # ---- layout ---------------------------------------------------------

    def _layout(self) -> None:
        """Rows from the top: note, cells, index numbers, pointers, counter. Only the rows this segment uses
        get room, so the cells are as large as the area allows."""
        box = self.bounds
        self.cell_w = min(MAX_CELL, box.width / self.n)
        note = NOTE_ROW if self.p.title or self.will(
            "note", "compare", "found", "ghost", "bisect_check", "bisect_discard", "bisect_step", "partition_step",
            *self.SORT_ACTIONS) else 0.0
        index = INDEX_ROW if self.p.show_indices or self.p.style == "bars" else 0.05
        bisects = self.will("bisect_check", "bisect_step")
        pointers = ARROW_LEN + SLOT * (2 if bisects else 1) if self.will("point", "scan") or bisects else 0.0
        counter = COUNTER_ROW if self.will("counter", "scan", *self.SORT_ACTIONS) else 0.0
        rest = note + index + pointers + counter
        if self.p.style == "cells":
            self.cell_h = min(self.cell_w, max(box.height - rest, 0.3))
        else:
            self.cell_h = min(BAR_MAX, max(box.height - rest, 0.5))
        # Centre the block (cells to counter) in what's left under the note row.
        spare = max(box.height - rest - self.cell_h, 0)
        self.cells_top = box.top - note - spare / 2
        self.cells_bottom = self.cells_top - self.cell_h
        self.index_y = self.cells_bottom - INDEX_ROW * 0.55
        self.arrow_top = self.cells_bottom - index
        self.slot0_y = self.arrow_top - ARROW_LEN - SLOT / 2
        self.counter_y = self.cells_bottom - index - pointers - COUNTER_ROW / 2
        self.note_y = self.cells_top + NOTE_ROW / 2
        left = box.center[0] - self.cell_w * self.n / 2
        self.xs = [left + self.cell_w * (i + 0.5) for i in range(self.n)]

    def _side(self) -> float:
        return min(self.cell_w, self.cell_h) * 0.9

    def _value_font(self) -> int:
        """As large as fits inside the square (digits are about 0.0072 units tall per font point)."""
        return max(MIN_FONT, min(40, int(self._side() * 0.6 / 0.0072)))

    def _cell(self, i: int, value) -> VGroup:
        x = self.xs[i]
        if self.p.style == "cells":
            shape = Square(side_length=self._side())  # never taller than its row
            shape.move_to([x, (self.cells_top + self.cells_bottom) / 2, 0])
            label = text(_fmt(value), self._value_font(), WHITE, max_width=self._side() * 0.8).move_to(shape)
        else:
            top = max(float(v) for v in self.values) or 1
            h = max(0.08, self.cell_h * float(value) / top)
            shape = Rectangle(width=self.cell_w * 0.75, height=h)
            shape.move_to([x, self.cells_bottom + h / 2, 0])
            label = text(_fmt(value), MIN_FONT, WHITE, max_width=self.cell_w * 0.95)
            label.move_to([x, self.index_y, 0])
        cell = VGroup(shape, label)
        self._style(cell, self.cell_state[i] if i < len(self.cell_state) else "base")
        return cell

    def _style(self, cell: VGroup, state: str) -> None:
        shape, label = cell
        if state == "grey":
            shape.set_stroke(GREYED, 2).set_fill(GREYED, 0.0)
            label.set_color(GREYED)
        elif state == "base":
            shape.set_stroke(self.base, 3).set_fill(self.base, 0.15 if self.p.style == "cells" else 0.5)
            label.set_color(WHITE)
        else:
            c = colour(state)
            shape.set_stroke(c, 6).set_fill(c, 0.3 if self.p.style == "cells" else 0.7)
            label.set_color(WHITE)

    def _restyle(self, indices, state) -> Step:
        targets = []
        for i in indices:
            self.cell_state[i] = state
            target = self.cells[i].copy()
            self._style(target, state)
            targets.append(self.cells[i].animate.become(target))
        return Step(targets)

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_spec = (s, col)
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    # ---- pointers -------------------------------------------------------

    def _pointer_positions(self) -> dict[str, tuple[float, int]]:
        """name -> (x, slot): labels stack under their arrow, and drop a slot when they'd touch a neighbour's."""
        placed: list[tuple[float, float, int]] = []  # (left, right, slot)
        out = {}
        for name, i in sorted(self.pointers.items(), key=lambda kv: (kv[1], list(self.pointers).index(kv[0]))):
            half = text(name, MIN_FONT).width / 2 + 0.04
            x = self.xs[i]
            slot = 0
            while slot < MAX_SLOTS - 1 and any(s == slot and l < x + half and x - half < r for l, r, s in placed):
                slot += 1
            placed.append((x - half, x + half, slot))
            out[name] = (x, slot)
        return out

    def _pointer_mob(self, name: str, x: float, slot: int) -> VGroup:
        # Every pointer's arrow ends above the first label row, so it never runs through a label stacked above
        # this one; a label pushed down a row just hangs a little lower.
        label_y = self.slot0_y - slot * SLOT
        arrow = Arrow([x, self.slot0_y + SLOT / 2 + 0.03, 0], [x, self.arrow_top, 0], buff=0, stroke_width=4,
                      max_tip_length_to_length_ratio=0.35, color=GREY_B)
        return VGroup(arrow, text(name, MIN_FONT, GREY_B).move_to([x, label_y, 0]))

    def _relayout_pointers(self) -> Step | None:
        anims = []
        for name, (x, slot) in self._pointer_positions().items():
            target = self._pointer_mob(name, x, slot)
            if name in self.pointer_mobs:
                anims.append(self.pointer_mobs[name].animate.become(target))
            else:
                self.pointer_mobs[name] = target
                anims += self.add(target)
        for name in [n for n in self.pointer_mobs if n not in self.pointers]:
            anims += self.drop(self.pointer_mobs.pop(name))
        return Step(anims) if anims else None

    # ---- create ---------------------------------------------------------

    def create(self) -> Steps:
        self.cells = [self._cell(i, v) for i, v in enumerate(self.values)]
        parts = list(self.cells)
        if self.p.show_indices and self.p.style == "cells":
            self.index_mobs = [text(str(i), MIN_FONT, GREY_B).move_to([self.xs[i], self.index_y, 0])
                               for i in range(self.n)]
            parts += self.index_mobs
        anims = self.add(*parts)
        if self.p.title:
            anims += self._note(self.p.title, GREY_B)
        yield Step(anims)

    def move(self, a) -> Steps:
        """Lay everything out again in the new area at full size (scaling would shrink the numbers)."""
        self.area = a.area
        self._layout()
        anims = [cell.animate.become(self._cell(i, self.values[i])) for i, cell in enumerate(self.cells)]
        for i, mob in enumerate(getattr(self, "index_mobs", [])):
            anims.append(mob.animate.move_to([self.xs[i], self.index_y, 0]))
        if step := self._relayout_pointers():
            anims += step.anims
        anims += self.drop(self.ghost_mob)
        self.ghost_mob = None
        if self.note_spec:
            anims += self._note(*self.note_spec)
        if self.counters:
            anims += self._counter()
        yield Step(anims)

    # ---- actions --------------------------------------------------------

    def highlight(self, a) -> Steps:
        yield self._restyle(a.indices, a.colour)

    def clear(self, a) -> Steps:
        anims = []
        hl = [i for i, s in enumerate(self.cell_state) if s not in ("base", "grey")]
        if hl:
            anims += self._restyle(hl, "base").anims
        anims += self.drop(self.ghost_mob, self.note_mob)
        self.ghost_mob = self.note_mob = self.note_spec = None
        if anims:
            yield Step(anims)

    def grey_out(self, a) -> Steps:
        yield self._restyle(range(a.start, a.end + 1), "grey")

    def restore(self, a) -> Steps:
        grey = [i for i, s in enumerate(self.cell_state) if s == "grey"]
        if grey:
            yield self._restyle(grey, "base")

    def point(self, a) -> Steps:
        self.pointers[a.name] = a.index
        if step := self._relayout_pointers():
            yield step

    def unpoint(self, a) -> Steps:
        self.pointers.pop(a.name, None)
        if step := self._relayout_pointers():
            yield step

    def compare(self, a) -> Steps:
        x, y = self.values[a.i], self.values[a.j]
        try:
            sign = "<" if x < y else ">" if x > y else "="
        except TypeError:
            sign = "vs"
        step = self._restyle([a.i, a.j], "YELLOW")
        yield Step(step.anims + self._note(f"{_fmt(x)} {sign} {_fmt(y)}"))

    def swap(self, a) -> Steps:
        i, j = a.i, a.j
        if i == j:
            return
        ci, cj = self.cells[i], self.cells[j]
        di = np.array([self.xs[j] - self.xs[i], 0, 0])
        yield Step([ci.animate.shift(di), cj.animate.shift(-di)])
        self.cells[i], self.cells[j] = cj, ci
        self.values[i], self.values[j] = self.values[j], self.values[i]
        self.cell_state[i], self.cell_state[j] = self.cell_state[j], self.cell_state[i]

    def set_value(self, a) -> Steps:
        i = a.index
        self.values[i] = a.value
        new = self._cell(i, a.value)
        yield Step([self.cells[i].animate.become(new)])

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def counter(self, a) -> Steps:
        self.counters[a.label] = a.value
        yield Step(self._counter())

    def _counter(self) -> list:
        old = self.counter_mob
        s = "   ".join(f"{k}: {v}" for k, v in self.counters.items())
        self.counter_mob = text(s, 32, WHITE, max_width=self.bounds.width).move_to(
            [self.bounds.center[0], self.counter_y, 0])
        return self.drop(old) + self.add(self.counter_mob)

    def scan(self, a) -> Steps:
        self.pointers["i"] = a.index
        anims = []
        if step := self._relayout_pointers():
            anims += step.anims
        prev = [k for k, s in enumerate(self.cell_state) if s == "YELLOW"]
        if prev:
            anims += self._restyle(prev, "base").anims
        hit = a.target is not None and self.values[a.index] == a.target
        anims += self._restyle([a.index], "GREEN" if hit else "YELLOW").anims
        self.counters["checks"] = self.counters.get("checks", 0) + 1
        anims += self._counter()
        yield Step(anims)

    def found(self, a) -> Steps:
        yield Step(self._restyle([a.index], "GREEN").anims + self._note("found it", colour("GREEN")))

    def ghost(self, a) -> Steps:
        old = self.ghost_mob
        cells = VGroup(*[self.cells[i] for i in a.indices])
        outline = SurroundingRectangle(cells, color=GHOST_COLOUR, buff=0.05)
        note = self._note(a.text, GHOST_COLOUR)
        # A full-height bar reaches the note row: keep the outline's top edge clear of the note's letters.
        limit = self.note_mob.get_bottom()[1] - 0.06
        if (over := outline.get_top()[1] - limit) > 0:
            outline.stretch_to_fit_height(max(outline.height - over, 0.2), about_edge=DOWN)
        self.ghost_mob = DashedVMobject(outline, num_dashes=30)
        yield Step(self.drop(old) + self.add(self.ghost_mob) + note)

    # ---- bisection --------------------------------------------------------

    def bisect_check(self, a) -> Steps:
        b = self.bisect
        if b is None or b["target"] != a.target or b.get("done"):
            if b is not None:  # a new search: every cell back in play
                out = [i for i, st in enumerate(self.cell_state) if st != "base"]
                if out:
                    yield Step(self._restyle(out, "base").anims, 0.2)
            b = self.bisect = {"lo": 0, "hi": self.n - 1, "target": a.target}
        mid = (b["lo"] + b["hi"]) // 2
        b["mid"] = mid
        self.pointers.update(lo=b["lo"], mid=mid, hi=b["hi"])
        if step := self._relayout_pointers():
            yield Step(step.anims, 0.45)
        value, target = self.values[mid], a.target
        sign = "=" if value == target else "<" if value < target else ">"
        verdict = {"=": "", "<": ": go right", ">": ": go left"}[sign]
        yield Step(self._restyle([mid], "YELLOW").anims + self._note(f"{_fmt(value)} {sign} {_fmt(target)}{verdict}"),
                   0.55)

    def bisect_discard(self, a) -> Steps:
        b = self.bisect
        mid, lo, hi, found = bisect_next(self.values, b["lo"], b["hi"], b["target"])
        if found:
            b["done"] = True
            yield Step(self._restyle([mid], "GREEN").anims + self._note("found it", colour("GREEN")))
            return
        out = range(b["lo"], mid + 1) if lo > b["lo"] else range(mid, b["hi"] + 1)
        yield Step(self._restyle(out, "grey").anims, 0.5)
        b["lo"], b["hi"] = lo, hi
        self.pointers.pop("mid", None)
        if lo > hi:
            b["done"] = True
            for name in ("lo", "hi"):
                self.pointers.pop(name, None)
            anims = self._note("not in the list", GREY_B)
        else:
            self.pointers.update(lo=lo, hi=hi)
            anims = self.drop(self.note_mob)
            self.note_mob = self.note_spec = None
        step = self._relayout_pointers()
        yield Step((step.anims if step else []) + anims, 0.5)

    def bisect_step(self, a) -> Steps:
        for step in self.bisect_check(a):
            yield Step(step.anims, step.share / 2)
        for step in self.bisect_discard(a):
            yield Step(step.anims, step.share / 2)

    # ---- sorts (computed by specs.sort_step, the same steps the checker counts) ----

    def _move_cells(self, order: list[int]) -> list:
        """Moves the cells so that slot k shows the cell now at order[k]; values and states follow."""
        anims = []
        for k, i in enumerate(order):
            if k != i:
                anims.append(self.cells[i].animate.shift([self.xs[k] - self.xs[i], 0, 0]))
        self.cells = [self.cells[i] for i in order]
        self.values = [self.values[i] for i in order]
        self.cell_state = [self.cell_state[i] for i in order]
        return anims

    def _sorted(self, kind: str, whole_pass: bool = False) -> Steps:
        self.sort, events = sort_events(list(self.values), self.sort, kind, whole_pass)
        share = 1 / max(1, len(events))
        for ev in events:
            if kind == "bubble":
                (i, j), (x, y) = ev["compared"], ev["values"]
                verdict = (f"{_fmt(x)} > {_fmt(y)}: swap" if ev["swapped"]
                           else f"{_fmt(x)} {'=' if x == y else '<'} {_fmt(y)}: keep")
                yield Step(self._restyle([i, j], "YELLOW").anims + self._note(verdict), share * 0.5)
                order = list(range(self.n))
                if ev["swapped"]:
                    order[i], order[j] = j, i
                anims = self._move_cells(order)
                after = {i: "base", j: "base"} | {k: "GREEN" for k in ev["placed"]}
            elif kind == "selection":
                m, k = ev["min"], ev["into"]
                yield Step(self._restyle([m], "YELLOW").anims + self._note(f"smallest: {_fmt(ev['value'])}"),
                           share * 0.45)
                order = list(range(self.n))
                order[k], order[m] = m, k
                anims = self._move_cells(order)
                after = {k: "GREEN" for k in ev["placed"]}
            else:
                src, dst = ev["from"], ev["to"]
                yield Step(self._restyle([src], "YELLOW").anims + self._note(f"insert {_fmt(ev['value'])}"),
                           share * 0.45)
                order = list(range(self.n))
                order.insert(dst, order.pop(src))
                anims = self._move_cells(order)
                after = {dst: "base"} | ({k: "GREEN" for k in range(self.n)} if ev["done"] else {})
            if anims:
                yield Step(anims, share * 0.3)
            restyle = []
            for k, state in after.items():
                restyle += self._restyle([k], state).anims
            self.counters["comparisons"] = self.sort["comparisons"]
            yield Step(restyle + self._counter(), share * 0.25)

    def partition_step(self, a) -> Steps:
        """Lomuto's partition: the pivot gold, the small side teal, the value j looks at yellow."""
        from animation_agent.visuals.specs import partition_next

        n = self.n
        lo = 0 if a.lo is None else a.lo
        hi = n - 1 if a.hi is None else a.hi
        part = getattr(self, "part", None)
        if part is None or part["done"] or (part["lo"], part["hi"]) != (lo, hi):
            part = self.part = {"lo": lo, "hi": hi, "i": lo - 1, "j": lo, "done": False}
        values = list(self.values)
        ev = partition_next(values, part)
        restyle = self._restyle([hi], "GOLD").anims if ev["kind"] == "compare" else []
        if ev["kind"] == "compare":
            yield Step(restyle + self._restyle([ev["j"]], "YELLOW").anims
                       + self._note(f"{_fmt(ev['value'])} {'<=' if ev['small'] else '>'} {_fmt(ev['pivot'])}"), 0.45)
        if ev["swap"] is not None:
            i, j = ev["swap"]
            order = list(range(n))
            order[i], order[j] = j, i
            yield Step(self._move_cells(order), 0.3)
        if ev["kind"] == "compare":
            states = {k: "TEAL" for k in range(lo, part["i"] + 1)}
            states |= {k: "base" for k in range(part["i"] + 1, part["j"]) if self.cell_state[k] != "GREEN"}
        else:
            states = {k: "base" for k in range(lo, hi + 1) if self.cell_state[k] != "GREEN"} | {ev["at"]: "GREEN"}
        anims = [] if ev["kind"] == "compare" else self._note(f"pivot {_fmt(ev['pivot'])} in place")
        for k, st in states.items():
            anims += self._restyle([k], st).anims
        yield Step(anims, 0.25)

    def bubble_step(self, a) -> Steps:
        yield from self._sorted("bubble")

    def bubble_pass(self, a) -> Steps:
        yield from self._sorted("bubble", whole_pass=True)

    def selection_step(self, a) -> Steps:
        yield from self._sorted("selection")

    def insertion_step(self, a) -> Steps:
        yield from self._sorted("insertion")


__all__ = ["ArrayBars", "DOWN", "UP"]
