"""MergeSort: a row of cells split into runs (gaps show the split tree), and merges drawn front by front into a row
below. The splits and merges are computed by specs.ms_split / specs.ms_merge_step, the same functions the checker
runs, so the picture is what merge sort really does."""

from __future__ import annotations

import copy

from manim import WHITE, DashedVMobject, Square, SurroundingRectangle, VGroup

from animation_agent.visuals.base import (
    GHOST_COLOUR,
    MIN_FONT,
    NOTE_ROW,
    Step,
    Steps,
    Template,
    colour,
    text,
)
from animation_agent.visuals.specs import (
    MERGE_SORT,
    MS_GAP,
    _fmt,
    _ms_ready,
    ms_full_gap_units,
    ms_gaps,
    ms_merge,
    ms_merge_step,
    ms_new,
    ms_split,
)

MAX_CELL = 0.62
ROW_GAP = 0.3
COUNTER_ROW = 0.4
MERGES = ("merge_step", "merge", "merge_level")


class MergeSort(Template):
    spec = MERGE_SORT
    durations = {"create": 0.8, "split": 0.8, "merge_step": 1.0, "merge": 2.4, "merge_level": 3.0}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.st = ms_new(params.values, params.runs)
        self.n = len(self.st["values"])
        self.base = colour(params.colour)
        self.cells: list = []  # per slot of the top row; None while its cell sits in the merged row below
        self.buffer: list = []  # the merged list in progress, in order
        self.cell_state = ["base"] * self.n
        self.note_mob = self.ghost_mob = self.counter_mob = None
        self._layout()

    # ---- layout ---------------------------------------------------------

    def _layout(self) -> None:
        box = self.bounds
        units = ms_full_gap_units(self.st)
        self.w = min(MAX_CELL, box.width / (self.n + units * MS_GAP))
        merges = self.will(*MERGES)
        note = NOTE_ROW if self.p.title or self.will("note", "ghost", *MERGES) else 0.0
        counter = COUNTER_ROW if merges else 0.0
        rows = 2 if merges else 1
        gap = ROW_GAP if merges else 0.0
        self.h = min(self.w, max((box.height - note - counter - gap) / rows, 0.3))
        block = rows * self.h + gap + counter
        spare = max(box.height - note - block, 0)
        top = box.top - note - spare / 2
        self.row_y = top - self.h / 2
        self.buffer_y = self.row_y - self.h - gap
        self.counter_y = top - rows * self.h - gap - counter / 2
        self.note_y = top + NOTE_ROW / 2 if note else box.top - NOTE_ROW / 2

    def _xs(self) -> list[float]:
        gaps = ms_gaps(self.st["tree"])
        total = self.n * self.w + sum(gaps) * MS_GAP * self.w
        x = self.bounds.center[0] - total / 2
        out = []
        for g in gaps:
            x += g * MS_GAP * self.w
            out.append(x + self.w / 2)
            x += self.w
        return out

    def _side(self) -> float:
        return min(self.w, self.h) * 0.9

    def _cell(self, value, x: float, y: float) -> VGroup:
        shape = Square(side_length=self._side()).move_to([x, y, 0])
        size = max(MIN_FONT, min(40, int(self._side() * 0.6 / 0.0072)))
        label = text(_fmt(value), size, WHITE, max_width=self._side() * 0.8).move_to(shape)
        cell = VGroup(shape, label)
        self._style(cell, "base")
        return cell

    def _style(self, cell: VGroup, state: str) -> None:
        shape, label = cell
        if state == "base":
            shape.set_stroke(self.base, 3).set_fill(self.base, 0.15)
        else:
            c = colour(state)
            shape.set_stroke(c, 6).set_fill(c, 0.3)
        label.set_color(WHITE)

    def _restyle(self, cell: VGroup, state: str):
        target = cell.copy()
        self._style(target, state)
        return cell.animate.become(target)

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    def _counter(self) -> list:
        old = self.counter_mob
        self.counter_mob = text(f"comparisons: {self.st['comparisons']}", 32, WHITE, max_width=self.bounds.width)
        self.counter_mob.move_to([self.bounds.center[0], self.counter_y, 0])
        return self.drop(old) + self.add(self.counter_mob)

    # ---- create ---------------------------------------------------------

    def create(self) -> Steps:
        xs = self._xs()
        self.cells = [self._cell(v, x, self.row_y) for v, x in zip(self.st["values"], xs)]
        anims = self.add(*self.cells)
        if self.p.title:
            anims += self._note(self.p.title, colour("GREY"))
        yield Step(anims)

    # ---- actions --------------------------------------------------------

    def split(self, a) -> Steps:
        ms_split(self.st)
        xs = self._xs()
        yield Step([c.animate.move_to([x, self.row_y, 0]) for c, x in zip(self.cells, xs) if c is not None])

    def _merge_event(self, ev: dict, share: float) -> Steps:
        anims = []
        if ev["compared"] is not None:
            i, j = ev["compared"]
            a, b = ev["pair"]
            sign = "<" if a < b else ">" if a > b else "="
            anims += [self._restyle(self.cells[i], "YELLOW"), self._restyle(self.cells[j], "YELLOW")]
            anims += self._note(f"{_fmt(a)} {sign} {_fmt(b)}")
            yield Step(anims, share * 0.45)
            anims = []
        xs = self._xs()  # the tree as it was before this step finished the merge
        for k in ev["took"]:
            cell, self.cells[k] = self.cells[k], None
            slot = ev["lo"] + len(self.buffer)
            target = cell.copy()  # one animation per cell: down into the merged list, back to its colour
            self._style(target, "base")
            target.move_to([xs[slot], self.buffer_y, 0])
            anims.append(cell.animate.become(target))
            self.buffer.append(cell)
        # The front that stayed goes back to its colour; the counter updates with the move (two plays a step, so a
        # whole merge fits its line).
        stayed = [self.cells[k] for k in (ev["compared"] or ()) if self.cells[k] is not None]
        anims += [self._restyle(c, "base") for c in stayed] + self._counter()
        moved = share * (0.55 if ev["compared"] is None else 0.3 if ev["done"] else 0.55)
        yield Step(anims, moved)
        if ev["done"]:
            new_xs = self._xs()  # the node is one run now: the gaps inside it close
            self.cells[ev["lo"]:ev["hi"]] = self.buffer
            self.buffer = []
            moves = [c.animate.move_to([x, self.row_y, 0]) for c, x in zip(self.cells, new_xs) if c is not None]
            yield Step(moves, share * 0.25)

    def _unyellow(self) -> list:
        return [self._restyle(c, "base") for c in self.cells if c is not None]

    def merge_step(self, a) -> Steps:
        ev = ms_merge_step(self.st)
        if not isinstance(ev, str):
            yield from self._merge_event(ev, 1.0)

    def _merges(self, whole_level: bool) -> Steps:
        # Count the steps first (on a copy), so each gets its share of the line.
        steps = ms_merge(copy.deepcopy(self.st), whole_level=whole_level)
        if isinstance(steps, str):
            return
        targets: list | None = None
        if whole_level:
            targets = [self.st["merge"]["node"]] if self.st["merge"] else []
            targets += [n for n in _ms_ready(self.st) if not any(n is t for t in targets)]
        share = 1.0 / len(steps)
        for _ in steps:
            ev = ms_merge_step(self.st, targets)
            if isinstance(ev, str):
                return
            yield from self._merge_event(ev, share)

    def merge(self, a) -> Steps:
        yield from self._merges(False)

    def merge_level(self, a) -> Steps:
        yield from self._merges(True)

    def highlight(self, a) -> Steps:
        anims = [self._restyle(self.cells[i], a.colour) for i in a.indices if self.cells[i] is not None]
        if anims:
            yield Step(anims)

    def ghost(self, a) -> Steps:
        old = self.ghost_mob
        row = VGroup(*[c for c in self.cells if c is not None])
        self.ghost_mob = DashedVMobject(SurroundingRectangle(row, color=GHOST_COLOUR, buff=0.06), num_dashes=40)
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        anims = self._unyellow() + self.drop(self.ghost_mob, self.note_mob)
        self.ghost_mob = self.note_mob = None
        if anims:
            yield Step(anims)


__all__ = ["MergeSort"]
