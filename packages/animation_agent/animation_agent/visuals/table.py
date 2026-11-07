"""Table: a grid of cells with an optional header row and row labels, filled by the writer or computed in order
(specs.table_next, the function the checker runs), with arrows from the cells a value came from.

Layout, top to bottom: the note row, the header row, the rows. Grid lines and arrows are background for the layout
audit; a highlighted cell is filled with its colour behind its text."""

from __future__ import annotations

import numpy as np
from manim import WHITE, Arrow, DashedVMobject, Rectangle, VGroup

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
from animation_agent.visuals.specs import TABLE, table_next, table_shape, truth_fn

MAX_CELL_W = 1.3
MAX_CELL_H = 0.6


class Table(Template):
    spec = TABLE
    durations = {"create": 1.0, "fill": 0.6, "fill_next": 0.8, "fill_row": 1.2, "depends": 0.7, "ghost": 0.7}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.nrows, self.ncols, cells, self.columns = table_shape(params)
        self.st = {"rule": params.rule, "cells": [list(r) for r in cells], "nrows": self.nrows, "ncols": self.ncols,
                   "columns": self.columns}
        if params.rule == "truth_table":
            self.st["truth"], self.st["vars"] = truth_fn(params.expr)
        self.labels = params.row_labels or (["F"] if params.rule == "fibonacci" else None)
        self.fills: dict[tuple[int, int], str] = {}
        self.arrows: list = []
        self.note_mob = self.ghost_mob = None
        self._layout()

    def _layout(self) -> None:
        box = self.bounds
        self.note_y = box.top - NOTE_ROW / 2
        lead = 1 if self.labels else 0
        header = 1 if self.columns else 0
        self.cw = min(MAX_CELL_W, box.width / (self.ncols + lead))
        self.ch = min(MAX_CELL_H, (box.height - NOTE_ROW) / (self.nrows + header))
        width = self.cw * (self.ncols + lead)
        self.x0 = box.center[0] - width / 2 + self.cw * lead
        height = self.ch * (self.nrows + header)
        top = box.top - NOTE_ROW - max(0.0, (box.height - NOTE_ROW - height) / 2)
        self.y0 = top - self.ch * header  # the top of row 0

    def centre(self, r: int, c: int) -> np.ndarray:
        return np.array([self.x0 + self.cw * (c + 0.5), self.y0 - self.ch * (r + 0.5), 0.0])

    def _font(self) -> int:
        return MIN_FONT if self.ch < 0.5 else 34

    def _cell(self, r: int, c: int) -> VGroup:
        rect = Rectangle(width=self.cw, height=self.ch).move_to(self.centre(r, c))
        fill = self.fills.get((r, c))
        rect.set_stroke(colour("GREY"), 2).set_fill(colour(fill) if fill else "#000000", 0.45 if fill else 0)
        blank = self.p.rule == "pascal" and c > r
        if blank:
            rect.set_stroke(colour("GREY"), 0)
        value = self.st["cells"][r][c]
        label = text(value, self._font(), WHITE, max_width=self.cw * 0.9).move_to(rect) if value else VGroup()
        return VGroup(mark_background(rect), label)

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    def create(self) -> Steps:
        self.cells = [[self._cell(r, c) for c in range(self.ncols)] for r in range(self.nrows)]
        parts = [m for row in self.cells for m in row]
        if self.columns:
            for c, h in enumerate(self.columns):
                parts.append(text(h, self._font(), colour("GOLD"), max_width=self.cw * 0.9)
                             .move_to(self.centre(-1, c)))
        for r, lab in enumerate(self.labels or []):
            parts.append(text(lab, self._font(), colour("GOLD"), max_width=self.cw * 0.9)
                         .move_to(self.centre(r, -1) if self.nrows > 1 or not self.columns else self.centre(0, -1)))
        anims = self.add(*parts)
        if self.p.title:
            anims += self._note(self.p.title, colour("GREY"))
        yield Step(anims)

    def _redraw(self, cells) -> list:
        return [self.cells[r][c].animate.become(self._cell(r, c)) for r, c in cells]

    def _arrows(self, to: tuple[int, int], frm: list) -> list:
        """Arrows from each cell in `frm` to `to`, edge to edge, replacing the last fill's arrows."""
        anims = self.drop(*self.arrows)
        self.arrows = []
        for a in frm:
            p, q = self.centre(*a), self.centre(*to)
            d = (q - p) / max(np.linalg.norm(q - p), 1e-6)
            reach = np.array([self.cw * 0.26, self.ch * 0.26, 0]) * np.abs(d) / max(np.abs(d).max(), 1e-6)
            arrow = Arrow(p + d * np.linalg.norm(reach), q - d * np.linalg.norm(reach), buff=0, stroke_width=6,
                          color=colour("TEAL"), max_tip_length_to_length_ratio=0.35)
            self.arrows.append(mark_background(arrow).set_z_index(1))
        return anims + self.add(*self.arrows)

    def fill(self, a) -> Steps:
        self.st["cells"][a.row][a.col] = text_value(a.value)
        yield Step(self._redraw([(a.row, a.col)]))

    def fill_next(self, a) -> Steps:
        ev = table_next(self.st)
        r, c = ev["cell"]
        self.st["cells"][r][c] = ev["value"]
        self.fills = {k: v for k, v in self.fills.items() if v != "TEAL"}
        self.fills[(r, c)] = "TEAL"
        arrows = self._arrows((r, c), ev["from"]) if ev["from"] and self.p.rule != "truth_table" else []
        yield Step(self._redraw({(r, c), *[k for k in self.fills]} | self._last_teal()) + arrows)

    def _last_teal(self) -> set:
        out = getattr(self, "_teal", set())
        self._teal = {k for k, v in self.fills.items() if v == "TEAL"}
        return out

    def fill_row(self, a) -> Steps:
        first = table_next(self.st)
        done = []
        while (ev := table_next(self.st)) is not None and ev["cell"][0] == first["cell"][0]:
            r, c = ev["cell"]
            self.st["cells"][r][c] = ev["value"]
            done.append((r, c))
        old = {k for k, v in self.fills.items() if v == "TEAL"}
        self.fills = {k: v for k, v in self.fills.items() if v != "TEAL"}
        yield Step(self._redraw(set(done) | old) + self.drop(*self.arrows))
        self.arrows = []

    def highlight(self, a) -> Steps:
        cells = [tuple(c) for c in a.cells]
        for k in cells:
            self.fills[k] = a.colour
        yield Step(self._redraw(cells))

    def highlight_row(self, a) -> Steps:
        cells = [(a.row, c) for c in range(self.ncols)]
        for k in cells:
            self.fills[k] = a.colour
        yield Step(self._redraw(cells))

    def highlight_col(self, a) -> Steps:
        cells = [(r, a.col) for r in range(self.nrows)]
        for k in cells:
            self.fills[k] = a.colour
        yield Step(self._redraw(cells))

    def depends(self, a) -> Steps:
        yield Step(self._arrows(tuple(a.cell), [tuple(c) for c in a.on]))

    def ghost(self, a) -> Steps:
        old = self.ghost_mob
        rect = Rectangle(width=self.cw * 0.9, height=self.ch * 0.85).move_to(self.centre(a.row, a.col))
        box = DashedVMobject(rect.set_stroke(GHOST_COLOUR, 4), num_dashes=16)
        value = text(text_value(a.value), self._font(), GHOST_COLOUR, max_width=self.cw * 0.8).move_to(rect)
        self.ghost_mob = VGroup(mark_background(box), value)
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        changed = list(self.fills)
        self.fills = {}
        anims = self._redraw(changed) + self.drop(*self.arrows, self.ghost_mob, self.note_mob)
        self.arrows, self.ghost_mob, self.note_mob = [], None, None
        if anims:
            yield Step(anims)


def text_value(v) -> str:
    from animation_agent.visuals.specs import _fmt

    return _fmt(v)


__all__ = ["Table"]
