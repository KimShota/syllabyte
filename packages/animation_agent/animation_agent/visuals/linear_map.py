"""LinearMap2D: a coordinate grid with vectors from the origin, transformed by a 2x2 matrix.

The grid is drawn as line segments clipped to the area, recomputed for each frame of a transformation
(M_t = (1 - t) I + t M), so a stretching matrix never pushes grid lines off the screen. Eigenvectors come from
numpy (specs.real_eigenvectors), so the dashed eigen-lines are always right.
"""

from __future__ import annotations

import math

import numpy as np
from manim import (
    BLUE_D,
    GREY_B,
    WHITE,
    Arrow,
    BackgroundRectangle,
    DashedLine,
    DashedVMobject,
    Dot,
    Line,
    UpdateFromAlphaFunc,
    VGroup,
)

from animation_agent.visuals.base import (
    GHOST_COLOUR,
    NOTE_ROW,
    Box,
    Step,
    Steps,
    Template,
    colour,
    mark_background,
    tex,
    text,
)
from animation_agent.visuals.specs import LINEAR_MAP_2D, matvec, real_eigenvectors

LABEL_FONT = 36
I2 = [[1.0, 0.0], [0.0, 1.0]]


def _lerp(m: list[list[float]], t: float) -> list[list[float]]:
    return [[(1 - t) * I2[r][c] + t * m[r][c] for c in range(2)] for r in range(2)]


def _clip(p: np.ndarray, q: np.ndarray, box: Box) -> tuple[np.ndarray, np.ndarray] | None:
    """Liang-Barsky: the part of segment pq inside the box, or None."""
    d = q - p
    t0, t1 = 0.0, 1.0
    for dp, lo, hi, val in ((d[0], box.left, box.right, p[0]), (d[1], box.bottom, box.top, p[1])):
        if abs(dp) < 1e-12:
            if val < lo or val > hi:
                return None
            continue
        a, b = (lo - val) / dp, (hi - val) / dp
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return None
    return p + t0 * d, p + t1 * d


def _dist_to_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    t = 0.0 if not ab.any() else float(np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1))
    return float(np.linalg.norm(p - (a + t * ab)))


class LinearMap2D(Template):
    spec = LINEAR_MAP_2D
    durations = {"create": 1.0, "apply": 2.0, "reset": 1.5, "eigenlines": 1.0, "add_vector": 0.7}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.matrix = [list(map(float, row)) for row in params.matrix]
        self.current = I2  # the transformation the grid shows now
        self.vectors: dict[str, tuple[float, float, object]] = {v.name: (v.x, v.y, colour(v.colour))
                                                                 for v in params.vectors}
        self.vector_mobs: dict[str, VGroup] = {}
        self.ghosts: list = []
        self.note_mob = None
        self.matrix_mob = None
        self.eigen_mobs = None
        self.eigen_colour = None
        self._layout()

    def _layout(self) -> None:
        self.plane = self.bounds.below(NOTE_ROW)
        e = self.p.extent
        self.unit = min(self.plane.width, self.plane.height) / (2 * e)
        self.origin = self.plane.center.copy()

    def move(self, a) -> Steps:
        """Lay the grid out again in the new area (scaling would shrink the labels)."""
        self.area = a.area
        self._layout()
        old_grid, self.grid_mob = self.grid_mob, self._grid(self.current)
        anims = self.drop(old_grid, *self.ghosts) + self.add(self.grid_mob)
        self.ghosts = []
        for name, mob in self._vectors_at(self.current).items():
            anims.append(self.vector_mobs[name].animate.become(mob))
        if self.eigen_mobs is not None:
            old, self.eigen_mobs = self.eigen_mobs, self._eigen_group(self.eigen_colour)
            anims += self.drop(old) + self.add(self.eigen_mobs)
        if self.note_mob is not None:
            note = self.note_mob.copy()
            self.note_mob = None
            anims += self._note_mob(note)
        if self.matrix_mob is not None:
            anims += list(self._show_matrix_anims())
        yield Step(anims)

    def _screen(self, x: float, y: float) -> np.ndarray:
        return self.origin + self.unit * np.array([x, y, 0.0])

    # ---- the grid -------------------------------------------------------------

    def _grid(self, m: list[list[float]]) -> VGroup:
        half = max(self.plane.width, self.plane.height) / (2 * self.unit)
        try:
            stretch = float(np.linalg.norm(np.linalg.inv(np.array(m)), 2))
        except np.linalg.LinAlgError:
            stretch = 3.0
        reach = min(int(math.ceil(half * max(1.0, min(stretch, 4.0)))) + 1, 24)
        lines = VGroup()
        for k in range(-reach, reach + 1):
            for p, q in (((k, -reach), (k, reach)), ((-reach, k), (reach, k))):
                a = self._screen(*matvec(m, *p))
                b = self._screen(*matvec(m, *q))
                seg = _clip(a, b, self.plane)
                if seg is None or np.linalg.norm(seg[1] - seg[0]) < 1e-3:
                    continue
                axis = k == 0
                lines.add(Line(seg[0], seg[1], stroke_width=2.5 if axis else 1.2,
                               color=GREY_B if axis else BLUE_D, stroke_opacity=0.9 if axis else 0.7))
        return mark_background(lines)

    def _vector(self, name: str, x: float, y: float, col, m) -> VGroup:
        tx, ty = matvec(m, x, y)
        tip = self._screen(tx, ty)
        if math.hypot(tx, ty) * self.unit < 0.05:
            arrow = Dot(self.origin, radius=0.06, color=col)
        else:
            arrow = Arrow(self.origin, tip, buff=0, stroke_width=6, color=col,
                          max_tip_length_to_length_ratio=0.3, max_stroke_width_to_length_ratio=10)
        label = tex(name, LABEL_FONT, col)
        label.move_to(self._label_spot(name, tip, label, m))
        return VGroup(arrow, label)

    def _label_spot(self, name: str, tip: np.ndarray, label, m) -> np.ndarray:
        """Beyond the tip, or beside it, inside the plane: wherever is farthest from the other vectors' arrows."""
        d = tip - self.origin
        norm = np.linalg.norm(d)
        d = d / norm if norm > 1e-9 else np.array([0.7, 0.7, 0.0])
        perp = np.array([-d[1], d[0], 0.0])
        half = np.array([label.width / 2 + 0.05, label.height / 2 + 0.05, 0.0])
        lo = np.array([self.plane.left, self.plane.bottom, 0.0]) + half
        hi = np.array([self.plane.right, self.plane.top, 0.0]) - half
        others = [(self.origin, self._screen(*matvec(m, x, y))) for n, (x, y, _) in self.vectors.items() if n != name]
        r = max(half[0], half[1]) + 0.08
        best, best_score = None, -1.0
        for offset in (d, d * 0.7 + perp * 0.7, d * 0.7 - perp * 0.7, perp, -perp):
            p = np.clip(tip + offset * r, lo, hi)
            score = min([_dist_to_segment(p, a, b) for a, b in others] + [9.0])
            if score > best_score + 1e-6:
                best, best_score = p, score
        return best

    def _vectors_at(self, m) -> dict[str, VGroup]:
        return {name: self._vector(name, x, y, c, m) for name, (x, y, c) in self.vectors.items()}

    def _animate_to(self, target: list[list[float]]) -> UpdateFromAlphaFunc:
        start = self.current

        def update(group, alpha):
            m = [[(1 - alpha) * start[r][c] + alpha * target[r][c] for c in range(2)] for r in range(2)]
            # Swap the parts in outright: become() pairs up parts by position, which garbles a grid whose
            # number of visible lines changes from frame to frame (or a vector that shrinks to a dot).
            self.grid_mob.submobjects = self._grid(m).submobjects
            for name, mob in self._vectors_at(m).items():
                self.vector_mobs[name].submobjects = mob.submobjects

        return UpdateFromAlphaFunc(self.group, update)

    # ---- create ---------------------------------------------------------------

    def create(self) -> Steps:
        self.grid_mob = self._grid(I2)
        anims = self.add(self.grid_mob)
        if self.p.title:
            anims += self._note_text(self.p.title, GREY_B)
        yield Step(anims, 0.5)
        self.vector_mobs = self._vectors_at(I2)
        if self.vector_mobs:
            yield Step(self.add(*self.vector_mobs.values()), 0.5)

    def _note_mob(self, mob) -> list:
        old, self.note_mob = self.note_mob, mob
        row = self.bounds.top_row(NOTE_ROW)
        mob.move_to(row.center)
        if mob.width > row.width:
            mob.scale_to_fit_width(row.width)
        return self.drop(old) + self.add(mob)

    def _note_text(self, s: str, col=WHITE) -> list:
        return self._note_mob(text(s, 32, col, max_width=self.bounds.width))

    # ---- actions --------------------------------------------------------------

    def apply(self, a) -> Steps:
        if a.keep_ghost:  # the arrows only: a dimmed label would be hard to read and sit on the live one
            ghosts = [mob[0].copy().set_opacity(0.35) for mob in self.vector_mobs.values()]
            self.ghosts += ghosts
            self.group.add(*ghosts)
            self.scene.add(*ghosts)
        yield Step([self._animate_to(self.matrix)])
        self.current = self.matrix

    def reset(self, a) -> Steps:
        yield Step([self._animate_to(I2)])
        self.current = I2

    def add_vector(self, a) -> Steps:
        self.vectors[a.name] = (a.x, a.y, colour(a.colour))
        mob = self._vector(a.name, a.x, a.y, colour(a.colour), self.current)
        self.vector_mobs[a.name] = mob
        yield Step(self.add(mob))

    def remove_vector(self, a) -> Steps:
        self.vectors.pop(a.name, None)
        yield Step(self.drop(self.vector_mobs.pop(a.name, None)))

    def highlight_vector(self, a) -> Steps:
        x, y, _ = self.vectors[a.name]
        c = colour(a.colour)
        self.vectors[a.name] = (x, y, c)
        target = self._vector(a.name, x, y, c, self.current)
        target[0].set_stroke(width=9)
        yield Step([self.vector_mobs[a.name].animate.become(target)])

    def eigenlines(self, a) -> Steps:
        c = colour(a.colour)
        if not real_eigenvectors(self.matrix):
            yield Step(self._note_text("no real eigenvectors", c))
            return
        old, self.eigen_mobs, self.eigen_colour = self.eigen_mobs, self._eigen_group(c), c
        yield Step(self.drop(old) + self.add(self.eigen_mobs))

    def _eigen_group(self, c) -> VGroup:
        group = VGroup()
        far = 2 * max(self.plane.width, self.plane.height)
        placed: list[np.ndarray] = []
        for value, (vx, vy) in real_eigenvectors(self.matrix):
            d = np.array([vx, vy, 0.0])
            seg = _clip(self.origin - far * d, self.origin + far * d, self.plane)
            if seg is None:
                continue
            line = mark_background(DashedLine(seg[0], seg[1], dash_length=0.12, color=c, stroke_width=3))
            label = tex(rf"\lambda = {value:g}", 32, c)
            label.move_to(self._clear_spot(seg, label, placed))
            placed.append(label.get_center())
            group.add(VGroup(line, label))
        return group

    def _vector_segments(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """Every vector as drawn now and after the matrix is applied: where a label must not sit."""
        segs = []
        for x, y, _ in self.vectors.values():
            for m in (self.current, self.matrix):
                segs.append((self.origin, self._screen(*matvec(m, x, y))))
        return segs

    def _clear_spot(self, seg, label, placed) -> np.ndarray:
        """Where to put an eigen-line's label: near one end of the line, to one side of it, inside the plane, as
        far as possible from every vector and from labels already placed."""
        d = (seg[1] - seg[0]) / max(np.linalg.norm(seg[1] - seg[0]), 1e-9)
        perp = np.array([-d[1], d[0], 0.0])
        half = np.array([label.width / 2 + 0.05, label.height / 2 + 0.05, 0.0])
        lo = np.array([self.plane.left, self.plane.bottom, 0.0]) + half
        hi = np.array([self.plane.right, self.plane.top, 0.0]) - half
        best, best_score = None, -1.0
        for end, inward in ((seg[1], -d), (seg[0], d)):
            for side in (1, -1):
                p = np.clip(end + inward * (half[0] + 0.25) + side * perp * (half[1] + 0.22), lo, hi)
                score = min([_dist_to_segment(p, a, b) for a, b in self._vector_segments()]
                            + [float(np.linalg.norm(p - q)) for q in placed] + [9.0])
                if score > best_score:
                    best, best_score = p, score
        return best

    def set_matrix(self, a) -> Steps:
        self.matrix = [list(map(float, row)) for row in a.matrix]
        if self.matrix_mob is not None:
            yield from self.show_matrix(a)

    def show_matrix(self, a) -> Steps:
        yield Step(list(self._show_matrix_anims()))

    def _show_matrix_anims(self):
        (p, q), (r, s) = self.matrix
        body = rf"A = \begin{{bmatrix}} {p:g} & {q:g} \\ {r:g} & {s:g} \end{{bmatrix}}"
        mob = tex(body, 32, WHITE)
        bg = BackgroundRectangle(mob, fill_opacity=0.85, buff=0.08)
        group = VGroup(bg, mob)
        # Top-left corner of the plane.
        group.move_to([self.plane.left + group.width / 2 + 0.05, self.plane.top - group.height / 2 - 0.05, 0])
        old, self.matrix_mob = self.matrix_mob, group
        return self.drop(old) + self.add(group)

    def note(self, a) -> Steps:
        mob = tex(a.tex, 36) if a.tex is not None else text(a.text, 32, WHITE, max_width=self.bounds.width)
        yield Step(self._note_mob(mob))

    def ghost_vector(self, a) -> Steps:
        tip = self._screen(a.x, a.y)
        arrow = DashedVMobject(Arrow(self.origin, tip, buff=0, stroke_width=5, color=GHOST_COLOUR,
                                     max_tip_length_to_length_ratio=0.3), num_dashes=12)
        parts = [arrow]
        if a.name:
            label = tex(a.name, LABEL_FONT, GHOST_COLOUR)
            direction = np.array([a.x, a.y, 0.0])
            label.move_to(tip + direction / max(np.linalg.norm(direction), 1e-9) * 0.3)
            parts.append(label)
        ghost = VGroup(*parts)
        self.ghosts.append(ghost)
        yield Step(self.add(ghost))

    def clear_ghosts(self, a) -> Steps:
        ghosts, self.ghosts = self.ghosts, []
        if ghosts:
            yield Step(self.drop(*ghosts))
