"""NumberLine: one axis with ticks, named points, jump arcs, shaded intervals, a sequence's terms (computed by
specs.nl_terms, the function the checker runs) and an epsilon band.

Layout, top to bottom: the note row, room for jump arcs and point names, the line, the tick labels. Point names
sit above their dots, raised a row when two would touch. The line and ticks are background for the layout audit."""

from __future__ import annotations

import numpy as np
from manim import (
    WHITE,
    ArcBetweenPoints,
    Circle,
    CurvedArrow,
    DashedLine,
    Dot,
    Line,
    Rectangle,
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
)
from animation_agent.visuals.specs import NUMBER_LINE, _num, nl_terms, nl_ticks

TICK_ROW = 0.42
NAME_ROW = 0.36
ARC_ROOM = 0.75
DOT_R = 0.08
END_R = 0.09


class NumberLine(Template):
    spec = NUMBER_LINE
    durations = {"create": 0.9, "point": 0.6, "slide": 0.9, "jump": 0.9, "interval": 0.8, "sequence": 1.4,
                 "band": 0.8, "ghost": 0.7}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.lo, self.hi = (float(x) for x in params.x_range)
        self.points: dict[str, dict] = {}
        self.marks: list = []  # jumps, intervals, the band
        self.term_mobs: list = []
        self.note_mob = self.ghost_mob = None
        self._layout()

    def _layout(self) -> None:
        box = self.bounds
        self.note_y = box.top - NOTE_ROW / 2
        self.left, self.right = box.left + 0.25, box.right - 0.25
        # The line sits low enough to leave room above for arcs and two rows of names, high enough for ticks.
        below = TICK_ROW + 0.4  # tick labels, then the terms' names
        above = box.top - NOTE_ROW
        self.y = max(box.bottom + below, (box.bottom + below + above) / 2 - 0.35)
        self.name_y = self.y + DOT_R + NAME_ROW / 2 + 0.04

    def x2p(self, x: float) -> np.ndarray:
        return np.array([self.left + (x - self.lo) / (self.hi - self.lo) * (self.right - self.left), self.y, 0.0])

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    # ---- the line ---------------------------------------------------------

    def create(self) -> Steps:
        line = mark_background(Line(self.x2p(self.lo) + [-0.12, 0, 0], self.x2p(self.hi) + [0.12, 0, 0],
                                    color=colour("GREY"), stroke_width=3))
        ticks = nl_ticks(self.lo, self.hi, self.p.step)
        labels = [_num(t) for t in ticks]
        widths = [text(s, MIN_FONT).width for s in labels]
        gap = (self.right - self.left) / max(len(ticks) - 1, 1)
        every = 1
        while every < len(ticks) and max(widths) + 0.08 > gap * every:
            every += 1
        parts = [line]
        for k, t in enumerate(ticks):
            p = self.x2p(t)
            parts.append(mark_background(Line(p + [0, -0.08, 0], p + [0, 0.08, 0], color=colour("GREY"),
                                              stroke_width=2)))
            if k % every == 0:
                parts.append(text(labels[k], MIN_FONT, colour("GREY")).move_to(p + [0, -TICK_ROW * 0.6, 0]))
        anims = self.add(*parts)
        for q in self.p.points:
            anims += self._place(q.name, q.x, q.colour)
        if self.p.title:
            anims += self._note(self.p.title, colour("GREY"))
        yield Step(anims)

    def _name_pos(self, name: str, x: float) -> np.ndarray:
        """Above the dot; a row higher if another name, or a jump's arc, would touch it there."""
        p = self.x2p(x)
        w = text(name, MIN_FONT).width
        arcs = [m for m in self.marks if isinstance(m, CurvedArrow)]
        for level in range(5):
            y = self.name_y + level * NAME_ROW
            clash = any(abs(q["x_screen"] - p[0]) < (w + q["w"]) / 2 + 0.06 and abs(q["y"] - y) < 0.05
                        for n, q in self.points.items() if n != name)
            clash = clash or any(m.get_left()[0] - w / 2 < p[0] < m.get_right()[0] + w / 2
                                 and m.get_bottom()[1] - NAME_ROW / 2 < y < m.get_top()[1] + NAME_ROW / 2
                                 for m in arcs)
            if not clash:
                return np.array([p[0], y, 0.0])
        return np.array([p[0], self.name_y + 5 * NAME_ROW, 0.0])

    def _place(self, name: str, x: float, col: str) -> list:
        old = self.points.pop(name, None)
        where = self._name_pos(name, x)
        dot = Dot(self.x2p(x), radius=DOT_R, color=colour(col)).set_z_index(2)
        label = text(name, MIN_FONT, colour(col)).move_to(where)
        entry = {"x": x, "col": col, "dot": dot, "label": label, "x_screen": where[0], "y": where[1],
                 "w": label.width}
        self.points[name] = entry
        if old is None:
            return self.add(dot, label)
        # The mobjects on screen stay the ones tracked, so a later clear or move acts on what is shown.
        dot_moves, entry["dot"] = self.morph(old["dot"], dot)
        label_moves, entry["label"] = self.morph(old["label"], label)
        return dot_moves + label_moves

    # ---- actions ----------------------------------------------------------

    def point(self, a) -> Steps:
        yield Step(self._place(a.name, a.x, a.colour))

    def slide(self, a) -> Steps:
        q = self.points[a.name]
        old_dot, old_label = q["dot"], q["label"]
        self.points.pop(a.name)
        where = self._name_pos(a.name, a.x)
        self.points[a.name] = {**q, "x": a.x, "x_screen": where[0], "y": where[1]}
        yield Step([old_dot.animate.move_to(self.x2p(a.x)), old_label.animate.move_to(where)])

    def jump(self, a) -> Steps:
        p0, p1 = self.x2p(a.from_x) + [0, 0.06, 0], self.x2p(a.to_x) + [0, 0.06, 0]
        span = abs(p1[0] - p0[0])
        angle = -1.6 if a.to_x > a.from_x else 1.6  # always bulging upwards
        arc = CurvedArrow(p0, p1, angle=angle, color=colour(a.colour), stroke_width=4, tip_length=0.14)
        arc.set_z_index(1)
        mobs = [arc]
        if a.label:
            top = arc.get_top()
            mobs.append(text(a.label, MIN_FONT, colour(a.colour)).next_to(top, np.array([0, 1, 0]), buff=0.06))
        del span
        self.marks += mobs
        anims = self.add(*mobs)
        for n, q in list(self.points.items()):  # names the arc would cross move above it
            where = self._name_pos(n, q["x"])
            if abs(where[1] - q["y"]) > 1e-6:
                q["x_screen"], q["y"] = where[0], where[1]
                anims.append(q["label"].animate.move_to(where))
        yield Step(anims)

    def interval(self, a) -> Steps:
        col = colour(a.colour)
        lo = self.x2p(a.lo if a.lo is not None else self.lo) - ([0.12, 0, 0] if a.lo is None else 0)
        hi = self.x2p(a.hi if a.hi is not None else self.hi) + ([0.12, 0, 0] if a.hi is None else 0)
        band = Line(lo, hi, color=col, stroke_width=10).set_z_index(1)
        mobs = [band]
        for end, closed in ((a.lo, a.lo_closed), (a.hi, a.hi_closed)):
            if end is None:
                continue
            c = Circle(radius=END_R, color=col, stroke_width=4).move_to(self.x2p(end)).set_z_index(2)
            c.set_fill(col if closed else "#000000", 1)
            mobs.append(c)
        if a.lo is None or a.hi is None:  # running off to infinity: an arrowhead at that end
            from manim import Triangle
            tip = Triangle(color=col).set_fill(col, 1).scale(0.09).set_z_index(1)
            tip.rotate(np.pi / 2 if a.lo is None else -np.pi / 2).move_to(lo if a.lo is None else hi)
            mobs.append(tip)
        self.marks += mobs
        yield Step(self.add(*mobs))

    def sequence(self, a) -> Steps:
        terms = [(n, v) for n, v in nl_terms(a.fn, a.n_from, a.n_to) if self.lo <= v <= self.hi]
        anims = self.drop(*self.term_mobs)
        self.term_mobs = []
        col = colour(a.colour)
        named: list[tuple[float, float]] = []  # (x, width) of the term names shown
        for n, v in terms:
            p = self.x2p(v)
            dot = Dot(p, radius=DOT_R * 0.9, color=col).set_z_index(2)
            self.term_mobs.append(dot)
            label = text(f"a{n}", MIN_FONT, col)
            if all(abs(p[0] - x) > (label.width + w) / 2 + 0.05 for x, w in named):  # names only where they fit
                label.move_to([p[0], self.y - TICK_ROW * 0.6 - 0.36, 0])
                named.append((p[0], label.width))
                self.term_mobs.append(label)
        yield Step(anims + self.add(*self.term_mobs))

    def band(self, a) -> Steps:
        lo, hi = self.x2p(max(self.lo, a.center - a.eps)), self.x2p(min(self.hi, a.center + a.eps))
        rect = Rectangle(width=max(hi[0] - lo[0], 0.02), height=0.3)
        rect.move_to([(lo[0] + hi[0]) / 2, self.y, 0]).set_stroke(colour("GOLD"), 2).set_fill(colour("GOLD"), 0.25)
        mark_background(rect)
        self.marks.append(rect)
        yield Step(self.add(rect) + self._note(f"within {_num(a.eps)} of {_num(a.center)}", colour("GOLD")))

    def highlight(self, a) -> Steps:
        anims = []
        for n in a.names:
            q = self.points[n]
            anims += self._place(n, q["x"], a.colour)
        yield Step(anims)

    def ghost(self, a) -> Steps:
        p = self.x2p(a.x)
        old = self.ghost_mob
        self.ghost_mob = VGroup(DashedLine(p + [0, -0.25, 0], p + [0, 0.45, 0], color=GHOST_COLOUR, stroke_width=4),
                                ArcBetweenPoints(p + [-0.01, 0.45, 0], p + [0.01, 0.45, 0], color=GHOST_COLOUR))
        mark_background(self.ghost_mob)
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        anims = self.drop(*self.marks, self.ghost_mob, self.note_mob)
        self.marks, self.ghost_mob, self.note_mob = [], None, None
        if anims:
            yield Step(anims)


__all__ = ["NumberLine"]
