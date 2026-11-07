"""FunctionPlot: axes with curves sampled from their formulas (specs.parse_fn), and marks computed from them: a dot,
a tangent and its slope, a shaded area, the highest point, a dot sliding along a curve, data points, lines.

Layout: a note row on top, the y labels in a left margin, the x labels under the axis, and each curve's label in a
right margin, beside where the curve ends, so no curve ever runs through a label. The axes are background (the
layout audit lets marks cross them)."""

from __future__ import annotations

import numpy as np
from manim import (
    GREY_B,
    WHITE,
    Create,
    DashedLine,
    DashedVMobject,
    Dot,
    FadeIn,
    GrowFromCenter,
    Line,
    MoveAlongPath,
    Polygon,
    VGroup,
    VMobject,
)

from animation_agent.visuals.base import (
    GHOST_COLOUR,
    MIN_FONT,
    NOTE_ROW,
    Step,
    Steps,
    Template,
    colour,
    fit_width,
    mark_background,
    tex,
    text,
)
from animation_agent.visuals.specs import (
    FUNCTION_PLOT,
    _num,
    path_points,
    fn_extreme,
    fn_samples,
    fn_slope,
    parse_fn,
    plot_y_range,
)

X_LABEL_ROW = 0.42
LABEL_MARGIN = 0.95  # right margin for curve labels
LABEL_FONT = 32
DOT_R = 0.07


class FunctionPlot(Template):
    spec = FUNCTION_PLOT
    durations = {"create": 1.0, "plot": 1.0, "tangent": 0.9, "shade": 0.9, "peak": 1.0, "trace": 1.4, "dot": 0.6,
                 "points": 0.8, "line": 0.7, "ghost": 0.9, "vline": 0.6}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.xr = (float(params.x_range[0]), float(params.x_range[1]))
        self.yr = plot_y_range(params)
        self.curves: dict[str, dict] = {}  # name -> {"fn", "colour", "mob", "label"}
        self.marks: list = []
        self.ghost_mob = self.note_mob = None
        self._layout()

    # ---- layout ---------------------------------------------------------

    def _layout(self) -> None:
        box = self.bounds
        self.y_texts = [_num(self.yr[1]), _num(self.yr[0]), self.p.y_label]
        widths = [text(s, MIN_FONT).width for s in self.y_texts]
        self.ml = max(widths) + 0.14
        labels = bool(self.p.curves) or self.will("plot", "parametric", "polar")
        self.mr = LABEL_MARGIN if labels else 0.2
        self.left, self.right = box.left + self.ml, box.right - self.mr
        self.top = box.top - NOTE_ROW - 0.08
        self.bottom = box.bottom + X_LABEL_ROW
        self.note_y = box.top - NOTE_ROW / 2
        if self.p.equal_scale or self.will("polar", "parametric"):
            # One unit is as long on both axes: the axes shrink along the roomier direction, centred.
            (x0, x1), (y0, y1) = self.xr, self.yr
            unit = min((self.right - self.left) / (x1 - x0), (self.top - self.bottom) / (y1 - y0))
            w, h = unit * (x1 - x0), unit * (y1 - y0)
            cx, cy = (self.left + self.right) / 2, (self.top + self.bottom) / 2
            self.left, self.right = cx - w / 2, cx + w / 2
            self.bottom, self.top = cy - h / 2, cy + h / 2

    def c2p(self, x: float, y: float) -> np.ndarray:
        (x0, x1), (y0, y1) = self.xr, self.yr
        return np.array([self.left + (x - x0) / (x1 - x0) * (self.right - self.left),
                         self.bottom + (y - y0) / (y1 - y0) * (self.top - self.bottom), 0.0])

    def _inside(self, ys: np.ndarray) -> np.ndarray:
        return np.isfinite(ys) & (ys >= self.yr[0]) & (ys <= self.yr[1])

    def _axes(self) -> list:
        x_axis = mark_background(Line([self.left, self.bottom, 0], [self.right, self.bottom, 0], color=GREY_B,
                                      stroke_width=3))
        y_axis = mark_background(Line([self.left, self.bottom, 0], [self.left, self.top, 0], color=GREY_B,
                                      stroke_width=3))
        parts = [x_axis, y_axis]
        if self.yr[0] < 0 < self.yr[1]:  # the line y = 0, faint
            zero = self.c2p(0, 0)[1]
            parts.append(mark_background(DashedLine([self.left, zero, 0], [self.right, zero, 0], color=GREY_B,
                                                    stroke_width=1.5, dash_length=0.08)))
        number_y = self.bottom - X_LABEL_ROW * 0.5
        x_lo = text(_num(self.xr[0]), MIN_FONT, GREY_B).move_to([self.left, number_y, 0])
        x_hi = text(_num(self.xr[1]), MIN_FONT, GREY_B).move_to([self.right, number_y, 0])
        x_name = text(self.p.x_label, MIN_FONT, WHITE).move_to([(self.left + self.right) / 2, number_y, 0])
        y_hi_t, y_lo_t, y_name_t = self.y_texts
        y_hi = text(y_hi_t, MIN_FONT, GREY_B)
        y_hi.move_to([self.left - 0.07 - y_hi.width / 2, self.top - 0.1, 0])
        y_lo = text(y_lo_t, MIN_FONT, GREY_B)
        y_lo.move_to([self.left - 0.07 - y_lo.width / 2, self.bottom + 0.16, 0])
        y_name = text(y_name_t, MIN_FONT, WHITE)
        y_name.move_to([self.left - 0.07 - y_name.width / 2, (self.top + self.bottom) / 2, 0])
        labels = [x_lo, x_hi, y_hi, y_lo, y_name]
        if x_name.get_left()[0] > x_lo.get_right()[0] + 0.05 and x_name.get_right()[0] < x_hi.get_left()[0] - 0.05:
            labels.append(x_name)
        return parts + labels

    def _curve_mob(self, fn, col, *, dashed: bool = False, lo: float | None = None, hi: float | None = None,
                   width: float = 4) -> VGroup:
        xs, ys = fn_samples(fn, self.xr[0] if lo is None else lo, self.xr[1] if hi is None else hi)
        ok = self._inside(ys)
        pieces, run = [], []
        for x, y, good in zip(xs, ys, ok):
            if good:
                run.append(self.c2p(x, y))
            elif run:
                pieces.append(run)
                run = []
        if run:
            pieces.append(run)
        group = VGroup()
        for pts in pieces:
            if len(pts) < 2:
                continue
            piece = VMobject(stroke_color=col, stroke_width=width).set_points_as_corners(pts)
            group.add(DashedVMobject(piece, num_dashes=max(6, len(pts) // 6)) if dashed else piece)
        return group

    def _end_y(self, fn) -> float:
        """Where a curve's label goes: beside the last point of it that is on the axes."""
        xs, ys = fn_samples(fn, *self.xr)
        ok = np.where(self._inside(ys))[0]
        if ok.size == 0:
            return (self.top + self.bottom) / 2
        return float(self.c2p(xs[ok[-1]], ys[ok[-1]])[1])

    def _label_targets(self) -> dict[str, np.ndarray]:
        """Each curve's label beside its end, nudged apart so no two touch."""
        items = sorted(((c["end_y"] if "end_y" in c else self._end_y(c["fn"]), name)
                        for name, c in self.curves.items()), reverse=True)
        out, last = {}, None
        for y, name in items:
            h = self.curves[name]["label"].height
            if last is not None and y > last - h - 0.08:
                y = last - h - 0.08
            y = min(max(y, self.bottom + h / 2), self.top - h / 2)
            out[name] = np.array([self.right + 0.1 + self.curves[name]["label"].width / 2, y, 0.0])
            last = y
        return out

    def _add_curve(self, name: str, expr: str, col_name: str) -> list:
        fn = parse_fn(expr)
        col = colour(col_name)
        mob = self._curve_mob(fn, col)
        label = fit_width(tex(name, LABEL_FONT, col), self.mr - 0.15)
        self.curves[name] = {"fn": fn, "colour": col, "mob": mob, "label": label}
        moves = []
        for other, target in self._label_targets().items():
            lab = self.curves[other]["label"]
            if other == name:
                lab.move_to(target)
            else:
                moves.append(lab.animate.move_to(target))
        self.group.add(mob, label)
        return [Create(mob), FadeIn(label)] + moves

    def _note(self, s: str | None = None, *, formula: str | None = None, col=WHITE) -> list:
        old = self.note_mob
        if formula is not None:
            self.note_mob = fit_width(tex(formula, 36, col), self.bounds.width)
        else:
            self.note_mob = text(s or "", 32, col, max_width=self.bounds.width)
        self.note_mob.move_to([self.bounds.center[0], self.note_y, 0])
        return self.drop(old) + self.add(self.note_mob)

    def _mark(self, *mobs) -> None:
        for m in mobs:
            self.marks.append(m)
            self.group.add(m)

    # ---- create ---------------------------------------------------------

    def create(self) -> Steps:
        axes = self._axes()
        anims = self.add(*axes)
        for c in self.p.curves:
            anims += self._add_curve(c.name, c.fn, c.colour)
        if self.p.title:
            anims += self._note(self.p.title, col=GREY_B)
        yield Step(anims)

    # ---- actions --------------------------------------------------------

    def plot(self, a) -> Steps:
        yield Step(self._add_curve(a.name, a.fn, a.colour))

    def remove_curve(self, a) -> Steps:
        c = self.curves.pop(a.curve)
        anims = self.drop(c["mob"], c["label"])
        anims += [self.curves[n]["label"].animate.move_to(t) for n, t in self._label_targets().items()]
        yield Step(anims)

    def highlight(self, a) -> Steps:
        c = self.curves[a.curve]
        col = colour(a.colour)
        anims = [c["mob"].animate.set_stroke(col, 7), c["label"].animate.set_color(col)]
        c["colour"] = col
        yield Step(anims)

    def _dot(self, name: str, x: float, col):
        fn = self.curves[name]["fn"]
        y = float(fn(np.array([x]))[0])
        return Dot(self.c2p(x, y), radius=DOT_R, color=col), y

    def dot(self, a) -> Steps:
        d, y = self._dot(a.curve, a.x, colour(a.colour))
        self._mark(d)
        anims = [GrowFromCenter(d)]
        if a.label:
            lab = tex(a.label, 30, colour(a.colour))
            slope = fn_slope(self.curves[a.curve]["fn"], a.x, self.xr[1] - self.xr[0])
            side = -1 if slope >= 0 else 1  # away from the curve: up-left of a rising one, up-right of a falling one
            lab.next_to(d, np.array([side, 1, 0]), buff=0.06)
            lab.shift([min(0, self.right - lab.get_right()[0]) + max(0, self.left - lab.get_left()[0]),
                       min(0, self.top - lab.get_top()[1]), 0])
            self._mark(lab)
            anims.append(FadeIn(lab))
        yield Step(anims)

    def tangent(self, a) -> Steps:
        fn = self.curves[a.curve]["fn"]
        y0 = float(fn(np.array([a.x]))[0])
        m = fn_slope(fn, a.x, self.xr[1] - self.xr[0])
        half = 0.22 * (self.xr[1] - self.xr[0])
        ends = []
        for dx in (-half, half):
            x = min(max(a.x + dx, self.xr[0]), self.xr[1])
            y = y0 + m * (x - a.x)
            if not self.yr[0] <= y <= self.yr[1] and m != 0:  # pull the end in to where it leaves the axes
                y = min(max(y, self.yr[0]), self.yr[1])
                x = a.x + (y - y0) / m
            ends.append(self.c2p(x, y))
        col = colour(a.colour)
        line = Line(ends[0], ends[1], color=col, stroke_width=4)
        d = Dot(self.c2p(a.x, y0), radius=DOT_R, color=col)
        self._mark(line, d)
        yield Step([Create(line), GrowFromCenter(d)] + self._note(f"slope {_num(m)}", col=col))

    def shade(self, a) -> Steps:
        fn = self.curves[a.curve]["fn"]
        xs, ys = fn_samples(fn, a.a, a.b, 81)
        base = 0.0 if self.yr[0] <= 0 <= self.yr[1] else self.yr[0]
        ys = np.clip(np.nan_to_num(ys, nan=base), *self.yr)
        pts = [self.c2p(a.a, base)] + [self.c2p(x, y) for x, y in zip(xs, ys)] + [self.c2p(a.b, base)]
        col = colour(a.colour)
        region = Polygon(*pts, stroke_width=0, fill_color=col, fill_opacity=0.35)
        self._mark(region)
        yield Step([FadeIn(region)])

    def peak(self, a) -> Steps:
        fn = self.curves[a.curve]["fn"]
        x, y = fn_extreme(fn, *self.xr, a.kind)
        col = colour(a.colour)
        d = Dot(self.c2p(x, y), radius=DOT_R * 1.3, color=col)
        drop = DashedLine(self.c2p(x, y), [self.c2p(x, y)[0], self.bottom, 0], color=col, stroke_width=3)
        self._mark(d, drop)
        word = "max" if a.kind == "max" else "min"
        yield Step([GrowFromCenter(d), Create(drop)] + self._note(f"{word} at {self.p.x_label} = {_num(x)}", col=col))

    def trace(self, a) -> Steps:
        fn = self.curves[a.curve]["fn"]
        lo, hi = sorted((a.x_from, a.x_to))
        path = self._curve_mob(fn, colour(a.colour), lo=lo, hi=hi)
        if not len(path):
            return
        piece = path[0] if a.x_from <= a.x_to else path[-1]
        if a.x_from > a.x_to:
            piece = piece.copy().reverse_points()
        d, _ = self._dot(a.curve, a.x_from, colour(a.colour))
        self._mark(d)
        yield Step([FadeIn(d)], 0.15)
        yield Step([MoveAlongPath(d, piece)], 0.85)

    def vline(self, a) -> Steps:
        x = self.c2p(a.x, 0)[0]
        line = DashedLine([x, self.bottom, 0], [x, self.top, 0], color=colour(a.colour), stroke_width=3)
        self._mark(line)
        yield Step([Create(line)])

    def points(self, a) -> Steps:
        col = colour(a.colour)
        dots = [Dot(self.c2p(x, y), radius=DOT_R * 1.2, color=col) for x, y in zip(a.xs, a.ys)]
        self._mark(*dots)
        names = []
        origin = self.c2p(min(max(0.0, self.xr[0]), self.xr[1]), min(max(0.0, self.yr[0]), self.yr[1]))
        for k, lab in enumerate(a.labels or []):
            name = text(lab, MIN_FONT, col)
            names.append(self._beside(name, self.c2p(a.xs[k], a.ys[k]), origin))
        self._mark(*names)
        yield Step([GrowFromCenter(d) for d in dots] + [FadeIn(n) for n in names])

    def _beside(self, label, p: np.ndarray, away_from: np.ndarray):
        """The label next to the point p: on the side away from `away_from` if it fits there (clear of the tick
        numbers and the note row, off the dot), else the next side round."""
        d = p - away_from
        d = np.array([1.0, 0.6, 0.0]) if np.linalg.norm(d[:2]) < 1e-6 else d / np.linalg.norm(d)
        box = self.bounds
        lo_x, hi_x = self.left + 0.05, box.right
        lo_y, hi_y = self.bottom + 0.05, box.top - NOTE_ROW
        best = None
        for turn in (0, 1, -1, 2, -2, 4):
            a = turn * np.pi / 4
            v = np.array([d[0] * np.cos(a) - d[1] * np.sin(a), d[0] * np.sin(a) + d[1] * np.cos(a), 0.0])
            label.move_to(p + v * (0.14 + 0.5 * (abs(v[0]) * label.width + abs(v[1]) * label.height)))
            dx = max(0.0, lo_x - label.get_left()[0]) - max(0.0, label.get_right()[0] - hi_x)
            dy = max(0.0, lo_y - label.get_bottom()[1]) - max(0.0, label.get_top()[1] - hi_y)
            label.shift(np.array([dx, dy, 0.0]))
            clear = (abs(label.get_center()[0] - p[0]) > label.width / 2 + DOT_R * 1.4
                     or abs(label.get_center()[1] - p[1]) > label.height / 2 + DOT_R * 1.4)
            if clear and dx == 0 and dy == 0:
                return label
            if clear and best is None:
                best = label.get_center().copy()
        if best is not None:
            label.move_to(best)
        return label

    def _path(self, name: str, kind: str, f1: str, f2: str | None, t0: float, t1: float, col_name: str) -> list:
        col = colour(col_name)
        _, xs, ys = path_points(kind, f1, f2, t0, t1)
        ok = np.isfinite(xs) & np.isfinite(ys) & (xs >= self.xr[0]) & (xs <= self.xr[1]) & self._inside(ys)
        group, run = VGroup(), []
        for x, y, good in zip(xs, ys, ok):
            if good:
                run.append(self.c2p(x, y))
            elif run:
                if len(run) > 1:
                    group.add(VMobject(stroke_color=col, stroke_width=4).set_points_as_corners(run))
                run = []
        if len(run) > 1:
            group.add(VMobject(stroke_color=col, stroke_width=4).set_points_as_corners(run))
        label = fit_width(tex(name, LABEL_FONT, col), self.mr - 0.15)
        end_y = float(ys[ok][np.argmax(xs[ok])]) if ok.any() else self.yr[1]
        self.curves[name] = {"fn": None, "colour": col, "mob": group, "label": label,
                             "end_y": float(self.c2p(0, end_y)[1]), "path": (kind, f1, f2)}
        moves = []
        for other, target in self._label_targets().items():
            lab = self.curves[other]["label"]
            if other == name:
                lab.move_to(target)
            else:
                moves.append(lab.animate.move_to(target))
        self.group.add(group, label)
        return [Create(group), FadeIn(label)] + moves

    def parametric(self, a) -> Steps:
        yield Step(self._path(a.name, "parametric", a.x_t, a.y_t, a.t_from, a.t_to, a.colour))

    def polar(self, a) -> Steps:
        yield Step(self._path(a.name, "polar", a.r, None, a.t_from, a.t_to, a.colour))

    def sector(self, a) -> Steps:
        ts = np.linspace(a.t_from, a.t_to, 40)
        outer = [self.c2p(a.r_to * np.cos(t), a.r_to * np.sin(t)) for t in ts]
        inner = [self.c2p(a.r_from * np.cos(t), a.r_from * np.sin(t)) for t in ts[::-1]]
        col = colour(a.colour)
        shape = Polygon(*outer, *inner, color=col, stroke_width=3).set_fill(col, 0.45)
        mobs = [mark_background(shape)]
        if a.label:  # on the inner side, toward the origin (a curve at r_to would cross it outside)
            mid_t = (a.t_from + a.t_to) / 2
            inner_p = self.c2p(a.r_from * np.cos(mid_t), a.r_from * np.sin(mid_t))
            outer_p = self.c2p(a.r_to * np.cos(mid_t), a.r_to * np.sin(mid_t))
            mobs.append(self._beside(text(a.label, MIN_FONT, col), inner_p, outer_p))
        self._mark(*mobs)
        yield Step([FadeIn(m) for m in mobs])

    def dot_t(self, a) -> Steps:
        kind, f1, f2 = self.curves[a.curve]["path"]
        _, xs, ys = path_points(kind, f1, f2, a.t, a.t, 1)
        p = self.c2p(float(xs[0]), float(ys[0]))
        d = Dot(p, radius=DOT_R * 1.2, color=colour(a.colour)).set_z_index(2)
        mobs = [d]
        if a.label:  # outside the curve: away from its middle
            centre = self.curves[a.curve]["mob"].get_center()
            mobs.append(self._beside(text(a.label, MIN_FONT, colour(a.colour)), p, centre))
        self._mark(*mobs)
        yield Step([GrowFromCenter(d)] + [FadeIn(m) for m in mobs[1:]])

    def line(self, a) -> Steps:
        kind = DashedLine if a.dashed else Line
        seg = kind(self.c2p(a.x1, a.y1), self.c2p(a.x2, a.y2), color=colour(a.colour), stroke_width=4)
        self._mark(seg)
        yield Step([Create(seg)])

    def ghost(self, a) -> Steps:
        old = self.ghost_mob
        self.ghost_mob = self._curve_mob(parse_fn(a.fn), GHOST_COLOUR, dashed=True)
        yield Step(self.drop(old) + self.add(self.ghost_mob) + self._note(a.text, col=GHOST_COLOUR))

    def note(self, a) -> Steps:
        yield Step(self._note(a.text, formula=a.tex))

    def clear(self, a) -> Steps:
        anims = self.drop(*self.marks, self.ghost_mob, self.note_mob)
        self.marks, self.ghost_mob, self.note_mob = [], None, None
        if anims:
            yield Step(anims)


__all__ = ["FunctionPlot"]
