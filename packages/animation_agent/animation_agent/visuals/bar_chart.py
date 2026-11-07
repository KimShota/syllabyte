"""BarChart: labelled bars with their values on top, a note row above, and the computed marks (a total, running
totals, shares, the mean line, an expected value) from specs.py, the functions the checker runs.

Layout, top to bottom: the note row, a value row (each bar's number), the bars, the label row. A bar that outgrows
the scale rescales every bar (the scale is never drawn: each bar carries its number)."""

from __future__ import annotations

from manim import DOWN, WHITE, Create, DashedLine, DashedVMobject, FadeIn, GrowFromEdge, Rectangle, VGroup

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
from animation_agent.visuals.specs import BAR_CHART, _num, nice_top

VALUE_ROW = 0.4
LABEL_ROW = 0.42
MAX_BAR_W = 0.9
STAGGER = 0.34


def _short(v: float) -> str:
    """A bar's number: at most two decimals, and no leading zero for a share (0.25 -> .25 when space is tight)."""
    return _num(v)


class BarChart(Template):
    spec = BAR_CHART
    durations = {"create": 1.0, "set": 0.8, "add": 0.8, "cumulative": 1.2, "normalize": 1.2, "mean_line": 0.7,
                 "compare": 0.8, "ghost": 0.8}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.labels = list(params.labels)
        self.values = [float(v) for v in params.values]
        self.y_max = params.y_max or nice_top(max(self.values) or 1)
        self.base = colour(params.colour)
        self.state: dict[str, str] = {}  # label -> highlight colour
        self.note_mob = self.ghost_mob = self.mean_mob = None
        self.slots = len(self.labels) + (1 if self.will("add_bar") else 0)  # room for a bar that may be added
        self._layout()

    # ---- layout ---------------------------------------------------------

    def _layout(self) -> None:
        box = self.bounds
        self.note_y = box.top - NOTE_ROW / 2
        self.base_y = box.bottom + LABEL_ROW
        self.slot_w = box.width / max(self.slots, len(self.labels))
        self.bar_w = min(MAX_BAR_W, self.slot_w * 0.62)
        self.left = box.center[0] - self.slot_w * len(self.labels) / 2
        self._fit_numbers()

    def _fit_numbers(self) -> None:
        """Each bar's number above it; when the numbers are wider than their slots (shares like 0.12 under eight
        bars), every other one sits a row higher, so neighbours never touch; when even that is too tight (more than
        eight bars), the numbers are left off (the spec's sentence says so)."""
        widest = max(text(_short(v), MIN_FONT).width for v in self.values)
        self.stagger = widest > self.slot_w * 0.92
        self.numbers = len(self.labels) <= 8 and widest <= self.slot_w * 1.84
        if not self.numbers:
            self.stagger = False
        self.top = (self.bounds.top - NOTE_ROW - (VALUE_ROW if self.numbers else 0.1)
                    - (STAGGER if self.stagger else 0.0))

    def _x(self, i: int) -> float:
        n = len(self.labels)
        return self.bounds.center[0] + (i - (n - 1) / 2) * self.slot_w

    def _h(self, v: float) -> float:
        return max(0.02, (self.top - self.base_y) * v / self.y_max)

    def _bar(self, i: int) -> VGroup:
        v, lab = self.values[i], self.labels[i]
        h = self._h(v)
        rect = Rectangle(width=self.bar_w, height=h)
        rect.move_to([self._x(i), self.base_y + h / 2, 0])
        state = self.state.get(lab)
        col = colour(state) if state else self.base
        rect.set_stroke(col, 6 if state else 3).set_fill(col, 0.7 if state else 0.5)
        number = text(_short(v), MIN_FONT, WHITE) if self.numbers else VGroup()
        raise_ = STAGGER if self.stagger and i % 2 else 0.0
        if self.numbers:
            number.move_to([self._x(i), self.base_y + h + VALUE_ROW / 2 + raise_, 0])
        name = text(lab, MIN_FONT, WHITE, max_width=self.slot_w * 0.95)
        name.move_to([self._x(i), self.base_y - LABEL_ROW / 2, 0])
        return VGroup(rect, number, name)

    def _baseline(self):
        box = self.bounds
        return mark_background(DashedLine([box.left, self.base_y, 0], [box.right, self.base_y, 0], color=colour("GREY"),
                                          stroke_width=2, dash_length=0.06))

    def _note(self, s: str, col=WHITE) -> list:
        old = self.note_mob
        self.note_mob = text(s, 32, col, max_width=self.bounds.width).move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    def _redraw(self, indices=None) -> list:
        """Every bar (or these) animated to its current value, label and colour."""
        if indices is None:
            self._fit_numbers()
        anims = []
        for i in range(len(self.labels)) if indices is None else indices:
            moves, self.bars[i] = self.morph(self.bars[i], self._bar(i))
            anims += moves
        return anims

    def _rescale_for(self, v: float) -> bool:
        if v > self.y_max:
            self.y_max = nice_top(v)
            return True
        return False

    # ---- create ---------------------------------------------------------

    def create(self) -> Steps:
        self.line = self._baseline()
        self.bars = [self._bar(i) for i in range(len(self.labels))]
        self.group.add(self.line, *self.bars)
        title = self.p.title or ""
        if self.p.y_label:  # beside the title if both fit on the row, else the title alone
            both = f"{title} ({self.p.y_label})" if title else self.p.y_label
            title = both if text(both, MIN_FONT).width <= self.bounds.width else (title or self.p.y_label)
        steps = [Create(self.line)] + [GrowFromEdge(b, DOWN) for b in self.bars]
        if title:
            steps += self._note(title, colour("GREY"))
        yield Step(steps)

    # ---- actions --------------------------------------------------------

    def set(self, a) -> Steps:
        i = self.labels.index(a.label)
        self.values[i] = float(a.value)
        rescale = self._rescale_for(a.value)
        stagger = self.stagger
        self._fit_numbers()
        yield Step(self._redraw(None if rescale or stagger != self.stagger else [i]))

    def add_bar(self, a) -> Steps:
        self.labels.append(a.label)
        self.values.append(float(a.value))
        self._rescale_for(a.value)
        if len(self.labels) > self.slots:
            self.slots = len(self.labels)
        self._layout()
        new = self._bar(len(self.labels) - 1)
        moves = self._redraw(range(len(self.labels) - 1))
        self.bars.append(new)
        self.group.add(new)
        yield Step(moves + [FadeIn(new)])

    def series(self, a) -> Steps:
        from animation_agent.visuals.specs import bar_series

        labels, values = bar_series(a)
        old = self.bars
        self.labels, self.values = labels, values
        self.y_max = nice_top(max(values) or 1)
        self.state = {}
        self.slots = len(labels)
        self._layout()
        self.bars = [self._bar(i) for i in range(len(labels))]
        for b in old:
            self.group.remove(b)
        self.group.add(*self.bars)
        from manim import FadeOut
        yield Step([FadeOut(b) for b in old] + [GrowFromEdge(b, DOWN) for b in self.bars]
                   + self._note(a.fn.replace("**", "^"), colour("GOLD")))

    def highlight(self, a) -> Steps:
        for lab in a.labels:
            self.state[lab] = a.colour
        yield Step(self._redraw([self.labels.index(lab) for lab in a.labels]))

    def compare(self, a) -> Steps:
        va, vb = self.values[self.labels.index(a.a)], self.values[self.labels.index(a.b)]
        self.state[a.a] = self.state[a.b] = "YELLOW"
        sign = ">" if va > vb else "<" if va < vb else "="
        yield Step(self._redraw([self.labels.index(a.a), self.labels.index(a.b)])
                   + self._note(f"{_num(va)} {sign} {_num(vb)}", colour("YELLOW")))

    def total(self, a) -> Steps:
        yield Step(self._note(f"total = {_num(sum(self.values))}", colour("GOLD")))

    def cumulative(self, a) -> Steps:
        total = 0.0
        for i, v in enumerate(self.values):
            total += v
            self.values[i] = total
        self._rescale_for(total)
        yield Step(self._redraw() + self._note("running totals", colour("GOLD")))

    def normalize(self, a) -> Steps:
        total = sum(self.values)
        self.values = [v / total for v in self.values]
        self.y_max = nice_top(max(self.values))
        yield Step(self._redraw() + self._note(f"each / {_num(total)}", colour("GOLD")))

    def mean_line(self, a) -> Steps:
        mean = sum(self.values) / len(self.values)
        y = self.base_y + self._h(mean)
        box = self.bounds
        old = self.mean_mob
        self.mean_mob = mark_background(DashedLine([box.left, y, 0], [box.right, y, 0], color=colour("GOLD"),
                                                   stroke_width=4, dash_length=0.1)).set_z_index(1)
        yield Step(self.drop(old) + self.add(self.mean_mob) + self._note(f"mean = {_num(mean)}", colour("GOLD")))

    def expected(self, a) -> Steps:
        xs = [float(lab) for lab in self.labels]
        e = sum(x * v for x, v in zip(xs, self.values)) / sum(self.values)
        yield Step(self._note(f"E[X] = {_num(e)}", colour("GOLD")))

    def ghost(self, a) -> Steps:
        i = self.labels.index(a.label)
        h = self._h(min(a.value, self.y_max))
        rect = Rectangle(width=self.bar_w, height=h).move_to([self._x(i), self.base_y + h / 2, 0])
        old = self.ghost_mob
        self.ghost_mob = DashedVMobject(rect.set_stroke(GHOST_COLOUR, 4), num_dashes=24)
        self.ghost_mob.set_z_index(1)
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, colour(a.colour)))

    def clear(self, a) -> Steps:
        changed = [self.labels.index(lab) for lab in self.state]
        self.state = {}
        anims = self._redraw(changed) + self.drop(self.ghost_mob, self.mean_mob, self.note_mob)
        self.ghost_mob = self.mean_mob = self.note_mob = None
        if anims:
            yield Step(anims)


__all__ = ["BarChart"]
