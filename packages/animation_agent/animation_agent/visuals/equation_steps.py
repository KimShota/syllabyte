"""EquationSteps: a derivation, one formula per line, filled from the top of the area.

Pieces named in `colours`, or highlighted, covered or coloured later, are isolated when a line is built
(MathTex substrings_to_isolate), so they can be found and styled. A line that needs a new piece isolated is
rebuilt in place, which looks identical.
"""

from __future__ import annotations

from manim import (
    GREY_B,
    WHITE,
    DashedVMobject,
    Line,
    SurroundingRectangle,
    TransformMatchingShapes,
    VGroup,
    Write,
)

from animation_agent.visuals.base import (
    GHOST_COLOUR,
    GREYED,
    NOTE_ROW,
    Step,
    Steps,
    Template,
    colour,
    fit_width,
    tex,
    text,
)
from animation_agent.visuals.specs import EQUATION_STEPS

LINE_PITCH_MAX = 0.95
LINE_PITCH_MIN = 0.62  # a line any shorter shrinks its formula below a readable size


class EquationSteps(Template):
    spec = EQUATION_STEPS
    durations = {"create": 0.9, "rewrite": 1.2, "then": 1.0, "cross_out": 0.8}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.colours = {c.part: colour(c.colour) for c in params.colours}
        self.isolate: list[str] = list(self.colours)
        self.lines: list = []  # MathTex mobjects on screen, oldest first
        self.texs: list[str] = []
        self.marks: list = []  # underlines, the result box, the cross-out box
        self.covered: str | None = None  # the piece shown as a boxed "?"
        self.note_mob = None

    # ---- layout ---------------------------------------------------------

    @property
    def region(self):
        return self.bounds.below(NOTE_ROW)

    @property
    def max_lines(self) -> int:
        """max_lines, or fewer when the area is too short to show that many at a readable size."""
        return max(1, min(self.p.max_lines, int(self.region.height / LINE_PITCH_MIN)))

    @property
    def pitch(self) -> float:
        return min(LINE_PITCH_MAX, self.region.height / self.max_lines)

    def _y(self, k: int) -> float:
        return self.region.top - (k + 0.5) * self.pitch

    def _build(self, s: str, k: int):
        line = tex(s, isolate=self.isolate)
        for part, c in self.colours.items():
            if part in s:
                line.set_color_by_tex(part, c)
        fit_width(line, self.bounds.width)
        if line.height > self.pitch * 0.9:
            line.scale_to_fit_height(self.pitch * 0.9)
        line.move_to([self.bounds.center[0], self._y(k), 0])
        return line

    def _rebuild_last(self) -> None:
        new = self._build(self.texs[-1], len(self.lines) - 1)
        self.swap_in(self.lines[-1], new)
        self.lines[-1] = new

    def _part(self, part: str):
        """The current line's mobject for `part`, rebuilding the line first if the part isn't isolated yet; None
        when the line can't show it as a piece."""
        if part not in self.isolate:
            self.isolate.append(part)
            self._rebuild_last()
        found = self.lines[-1].get_part_by_tex(part)
        overlapping = [p for p in self.isolate if p != part and (part in p or p in part)]
        if found is None and overlapping:
            # MathTex can't isolate a piece inside another isolated piece (colours=["w_1 x_1 + b"], then
            # highlight "b": runs/course-test-1, the XOR video), so the newest piece wins.
            self.isolate = [p for p in self.isolate if p not in overlapping]
            self._rebuild_last()
            found = self.lines[-1].get_part_by_tex(part)
        return found

    def move(self, a) -> Steps:
        """Rebuild the formulas in the new area at full size, keeping the latest lines that fit."""
        self.area = a.area
        anims = self.drop(*self.marks, *self.lines[: max(0, len(self.lines) - self.max_lines)])
        self.marks = []
        self.lines = self.lines[-self.max_lines:]
        self.texs = self.texs[-self.max_lines:]
        for k, (line, s) in enumerate(zip(self.lines, self.texs)):
            shown = s.replace(self.covered, r"\boxed{?}", 1) if self.covered and k == len(self.lines) - 1 else s
            new = self._build(shown, k)
            self.group.remove(line)
            self.group.add(new)
            anims.append(TransformMatchingShapes(line, new))
            self.lines[k] = new
        if self.note_mob is not None:
            anims.append(self.note_mob.animate.move_to(self.bounds.top_row(NOTE_ROW).center))
        yield Step(anims)

    # ---- create ---------------------------------------------------------

    def create(self) -> Steps:
        line = self._build(self.p.tex, 0)
        self.lines, self.texs = [line], [self.p.tex]
        self.group.add(line)
        anims = [Write(line)]
        if self.p.title:
            anims += self._note(self.p.title, GREY_B)
        yield Step(anims)

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to(self.bounds.top_row(NOTE_ROW).center)
        return self.drop(old) + self.add(self.note_mob)

    # ---- actions --------------------------------------------------------

    def rewrite(self, a) -> Steps:
        k = len(self.lines) - 1
        new = self._build(a.tex, k)
        old = self.lines[-1]
        anims = self.drop(*self.marks)
        self.covered, self.marks = None, []
        self.group.remove(old)
        self.group.add(new)
        self.lines[-1], self.texs[-1] = new, a.tex
        yield Step([TransformMatchingShapes(old, new)] + anims)

    def then(self, a) -> Steps:
        anims = []
        if self.covered is not None:  # the covered line stays as it is shown, with its "?"
            self.covered = None
        if len(self.lines) == self.max_lines:
            # Scroll: the oldest line goes, the rest move up one place.
            gone, self.lines, self.texs = self.lines[0], self.lines[1:], self.texs[1:]
            anims += self.drop(gone, *self.marks)
            self.marks = []
            anims += [line.animate.shift([0, self.pitch, 0]) for line in self.lines]
            yield Step(anims, 0.4)
            anims = []
        new = self._build(a.tex, len(self.lines))
        self.lines.append(new)
        self.texs.append(a.tex)
        self.group.add(new)
        yield Step(anims + [Write(new)], 0.6)

    def highlight(self, a) -> Steps:
        # Colour the piece and underline it below the whole line: a box around a piece in the middle of a
        # formula would run through its neighbours.
        mob = self._part(a.part) or self.lines[-1]  # a piece the line can't isolate: underline the whole line
        c = colour(a.colour)
        y = self.lines[-1].get_bottom()[1] - 0.08
        underline = Line([mob.get_left()[0], y, 0], [mob.get_right()[0], y, 0], color=c, stroke_width=5)
        self.marks.append(underline)
        # Animate the whole line, not the piece: a piece animated on its own is briefly a separate object, and
        # the layout audit (which runs during play) would see its glyphs crossing the formula.
        yield Step([self.lines[-1].animate.set_color_by_tex(a.part, c)] + self.add(underline))

    def colour(self, a) -> Steps:
        self._part(a.part)
        self.colours[a.part] = colour(a.colour)
        yield Step([self.lines[-1].animate.set_color_by_tex(a.part, colour(a.colour))])

    def _show(self, s: str) -> Step:
        """Morphs the current line into formula `s` (same place), keeping the line's tex unchanged."""
        k = len(self.lines) - 1
        new = self._build(s, k)
        old = self.lines[-1]
        self.group.remove(old)
        self.group.add(new)
        self.lines[-1] = new
        return Step([TransformMatchingShapes(old, new)])

    def cover(self, a) -> Steps:
        # The piece is swapped for a boxed "?" inside the formula itself, so nothing is drawn over the formula.
        self.covered = a.part
        yield self._show(self.texs[-1].replace(a.part, r"\boxed{?}", 1))

    def uncover(self, a) -> Steps:
        self.covered = None
        yield self._show(self.texs[-1])

    def box(self, a) -> Steps:
        rect = SurroundingRectangle(self.lines[-1], color=colour(a.colour), buff=0.12, stroke_width=4)
        self.marks.append(rect)
        yield Step(self.add(rect))

    def cross_out(self, a) -> Steps:
        line = self.lines[-1]
        rect = DashedVMobject(SurroundingRectangle(line, color=GHOST_COLOUR, buff=0.1), num_dashes=30)
        self.marks.append(rect)
        yield Step([line.animate.set_color(GREYED)] + self.add(rect))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text))

    def clear(self, a) -> Steps:
        anims = self.drop(*self.marks, self.note_mob)
        self.marks, self.note_mob = [], None
        if anims:
            yield Step(anims)
