"""HashTable: a column of buckets 0..m-1, each with its chain to the right (chaining) or its one key (linear
probing), computed by specs.ht_insert / ht_find, the functions the checker runs. An insert or a find shows its hash
in the note row and lights up each bucket it probes in turn; a found key turns green."""

from __future__ import annotations

import copy

from manim import WHITE, Arrow, DashedVMobject, RoundedRectangle, VGroup

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
    HASH_TABLE,
    MAX_CHAIN,
    _ht_load,
    _num,
    ht_find,
    ht_formula,
    ht_hash,
    ht_insert,
    ht_new,
)

INDEX_W = 0.42


class HashTable(Template):
    spec = HASH_TABLE
    durations = {"create": 0.9, "insert": 1.2, "find": 1.1, "delete": 0.9, "load": 0.6, "ghost": 0.7}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.st = ht_new(params.size, params.mode, params.a, params.b)
        for k in params.keys:
            ht_insert(self.st, k)
        self.m, self.chaining = params.size, params.mode == "chaining"
        self.bucket_col: dict[int, str] = {}
        self.key_col: dict[int, str] = {}
        self.rows: list[VGroup] = []
        self.note_mob = self.ghost_mob = None
        self._layout()

    def _layout(self) -> None:
        box = self.bounds
        self.note_y = box.top - NOTE_ROW / 2
        self.row_h = min(0.56, (box.height - NOTE_ROW - 0.1) / self.m)
        width = box.width - INDEX_W
        self.cell_w = min(0.62, width / (MAX_CHAIN + 0.6) * 0.78) if self.chaining else min(1.0, width * 0.5)
        self.gap = self.cell_w * 0.32 if self.chaining else 0
        total = INDEX_W + (self.cell_w + self.gap) * (MAX_CHAIN if self.chaining else 1)
        self.x0 = box.center[0] - total / 2
        top = box.top - NOTE_ROW - max(0.0, (box.height - NOTE_ROW - self.row_h * self.m) / 2)
        self.y0 = top - self.row_h / 2

    def _y(self, b: int) -> float:
        return self.y0 - self.row_h * b

    def _key_x(self, k: int) -> float:
        return self.x0 + INDEX_W + self.gap * (k + 1) + self.cell_w * (k + 0.5) - (self.gap if not self.chaining else 0)

    def _row(self, b: int) -> VGroup:
        y = self._y(b)
        col = colour(self.bucket_col[b]) if b in self.bucket_col else colour("GREY")
        index = text(str(b), MIN_FONT, col).move_to([self.x0 + INDEX_W / 2, y, 0])
        out = VGroup(index)
        keys = self.st["buckets"][b] if self.chaining else ([] if self.st["buckets"][b] is None
                                                            else [self.st["buckets"][b]])
        h = max(self.row_h * 0.78, 0.38)  # a key's number at the smallest readable size fits
        if not self.chaining:
            slot = RoundedRectangle(width=self.cell_w, height=h, corner_radius=0.05, stroke_color=col,
                                    stroke_width=4 if b in self.bucket_col else 2, fill_opacity=0)
            slot.move_to([self._key_x(0), y, 0])
            out.add(mark_background(slot))
        for k, key in enumerate(keys):
            kc = colour(self.key_col.get(key, "BLUE"))
            cell = RoundedRectangle(width=self.cell_w * (0.92 if not self.chaining else 1), height=h * 0.9,
                                    corner_radius=0.05, stroke_color=kc, stroke_width=3, fill_color=kc,
                                    fill_opacity=0.25).move_to([self._key_x(k), y, 0])
            out.add(cell, text(str(key), MIN_FONT, WHITE).move_to(cell))
            if self.chaining:
                start = (self.x0 + INDEX_W - 0.02) if k == 0 else (self._key_x(k - 1) + self.cell_w / 2)
                out.add(mark_background(Arrow([start, y, 0], [self._key_x(k) - self.cell_w / 2, y, 0], buff=0,
                                              color=colour("GREY"), stroke_width=3,
                                              max_tip_length_to_length_ratio=0.4)))
        return out

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    def _refresh(self, buckets=None) -> list:
        anims = []
        for b in range(self.m) if buckets is None else buckets:
            target = self._row(b)
            if b < len(self.rows):
                moves, self.rows[b] = self.morph(self.rows[b], target)
                anims += moves
            else:
                self.rows.append(target)
                anims += self.add(target)
        return anims

    def create(self) -> Steps:
        anims = self._refresh()
        if self.p.title:
            anims += self._note(self.p.title, colour("GREY"))
        yield Step(anims)

    def _probe_steps(self, probes: list[int], formula: str) -> Steps:
        share = 0.5 / max(len(probes), 1)
        for k, b in enumerate(probes):
            self.bucket_col = {b: "YELLOW"}
            yield Step(self._refresh() + (self._note(formula, colour("GOLD")) if k == 0 else []), share)

    def insert(self, a) -> Steps:
        st = copy.deepcopy(self.st)
        ht_insert(st, a.key)
        ev = st["last"]
        yield from self._probe_steps(ev["probes"], ht_formula(self.st, a.key))
        self.st = st
        self.key_col = {a.key: "GOLD"}
        self.bucket_col = {}
        yield Step(self._refresh(), 0.5)

    def find(self, a) -> Steps:
        ev = ht_find(self.st, a.key)
        yield from self._probe_steps(ev["probes"], ht_formula(self.st, a.key))
        self.bucket_col = {}
        if ev["at"] is not None:
            self.key_col = {a.key: "GREEN"}
            yield Step(self._refresh(), 0.5)
        else:
            self.bucket_col = {ev["probes"][-1]: "RED"}
            yield Step(self._refresh() + self._note(f"{a.key}: not there", colour("RED")), 0.5)

    def delete(self, a) -> Steps:
        h = ht_hash(self.st, a.key)
        self.key_col = {a.key: "RED"}
        yield Step(self._refresh([h]), 0.4)
        self.st["buckets"][h].remove(a.key)
        self.key_col = {}
        yield Step(self._refresh([h]), 0.6)

    def load(self, a) -> Steps:
        n = round(_ht_load(self.st) * self.m)
        yield Step(self._note(f"load factor = {n}/{self.m} = {_num(n / self.m)}", colour("GOLD")))

    def highlight(self, a) -> Steps:
        self.bucket_col = {b: a.colour for b in a.buckets}
        yield Step(self._refresh())

    def ghost(self, a) -> Steps:
        old = self.ghost_mob
        used = len(self.st["buckets"][a.bucket]) if self.chaining else 0
        x = self._key_x(min(used, MAX_CHAIN - 1)) if self.chaining else self._key_x(0) + self.cell_w * 0.9
        box = RoundedRectangle(width=self.cell_w, height=self.row_h * 0.7, corner_radius=0.05).move_to(
            [x, self._y(a.bucket), 0])
        self.ghost_mob = VGroup(mark_background(DashedVMobject(box.set_stroke(GHOST_COLOUR, 4), num_dashes=14)),
                                text(str(a.key), MIN_FONT, GHOST_COLOUR).move_to(box))
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        self.bucket_col, self.key_col = {}, {}
        anims = self._refresh() + self.drop(self.ghost_mob, self.note_mob)
        self.ghost_mob = self.note_mob = None
        yield Step(anims)


__all__ = ["HashTable"]
