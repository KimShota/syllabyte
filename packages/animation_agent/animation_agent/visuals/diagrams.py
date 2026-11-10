"""Small memory-reference and finite-set diagrams, with computed state and fixed readable layouts."""
from __future__ import annotations

import copy
import numpy as np
from manim import Arrow, Circle, Difference, Intersection, Rectangle, Union, VGroup, WHITE

from animation_agent.visuals.base import Template, Step, colour, mark_background, text
from animation_agent.visuals.specs import MEMORY_REFS, VENN_DIAGRAM, memory_op, venn_regions


class MemoryRefs(Template):
    spec = MEMORY_REFS

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.st = {"objects": dict(params.objects), "refs": dict(params.refs)}
        self.picture = None

    def _picture(self):
        box = self.bounds
        out = VGroup()
        left, right = box.left + 0.65, box.right - 0.9
        row_h = min(1.15, (box.height - 0.8) / 3)
        top = box.top - 0.65
        out.add(text("variables", 30).move_to([left, box.top - 0.2, 0]),
                text("objects", 30).move_to([right, box.top - 0.2, 0]))
        targets = {}
        for i, (name, value) in enumerate(self.st["objects"].items()):
            pos = np.array([right, top - i * row_h - 0.3, 0])
            rect = mark_background(Rectangle(width=1.65, height=0.7, color=colour("BLUE")))
            rect.move_to(pos)
            out.add(rect, text(name, 30, colour("BLUE")).move_to(pos + [0, 0.17, 0]),
                    text(value, 30, WHITE, max_width=1.5).move_to(pos + [0, -0.17, 0]))
            targets[name] = rect.get_left()
        for i, (name, target) in enumerate(self.st["refs"].items()):
            pos = np.array([left, top - i * row_h - 0.3, 0])
            rect = mark_background(Rectangle(width=1.15, height=0.6, color=colour("GOLD"))).move_to(pos)
            out.add(rect, text(name, 30, max_width=1.05).move_to(pos))
            out.add(mark_background(Arrow(rect.get_right(), targets[target], buff=0.06, color=colour("GOLD"),
                                          stroke_width=3, max_tip_length_to_length_ratio=0.18)))
        return out

    def _refresh(self):
        picture = self._picture()
        if self.picture is None:
            self.picture = picture
            return self.add(picture)
        anims, self.picture = self.morph(self.picture, picture)
        return anims

    def create(self):
        yield Step(self._refresh())

    def _change(self, op, args):
        state = copy.deepcopy(self.st)
        problem = memory_op(op, state, args)
        if problem:
            raise ValueError(problem)
        self.st = state
        yield Step(self._refresh())

    def bind(self, a):
        yield from self._change("bind", a)

    def mutate(self, a):
        yield from self._change("mutate", a)

    def copy(self, a):
        yield from self._change("copy", a)

    def unbind(self, a):
        yield from self._change("unbind", a)

    def move(self, a):
        self.area = a.area
        yield Step(self._refresh())


class VennDiagram(Template):
    spec = VENN_DIAGRAM

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.shading = None
        self.picture = None
        self.operation = None
        self.shade_colour = "TEAL"

    def _picture(self):
        box = self.bounds
        self.universe = Rectangle(width=box.width - 0.1, height=box.height - 0.1, color=colour("GREY"))
        self.universe.move_to(box.center)
        r = min(box.width / 3.4, (box.height - 1.15) / 2)
        center = box.center + [0, 0.05, 0]
        self.a = Circle(radius=r, color=colour("BLUE")).move_to(center + [-0.55 * r, 0, 0])
        self.b = Circle(radius=r, color=colour("GOLD")).move_to(center + [0.55 * r, 0, 0])
        out = VGroup(*(mark_background(m) for m in (self.universe, self.a, self.b)))
        out.add(text("U", 30).move_to([box.left + 0.25, box.top - 0.25, 0]),
                text("A", 30, colour("BLUE")).move_to(center + [-0.65 * r, r + 0.22, 0]),
                text("B", 30, colour("GOLD")).move_to(center + [0.65 * r, r + 0.22, 0]))
        for region, values in enumerate(venn_regions(self.p.model_dump())):
            for i, value in enumerate(values):
                if region == 3:
                    pos = [box.center[0] + (i - (len(values) - 1) / 2) * 0.65, box.bottom + 0.3, 0]
                else:
                    # four rows sit a little closer so the column stays inside the lens between the circles
                    gap = 0.34 if len(values) <= 3 else 0.3
                    pos = center + [(region - 1) * r, ((len(values) - 1) / 2 - i) * gap, 0]
                out.add(text(value, 30).move_to(pos))
        return out

    def _region(self, operation):
        a, b, u = self.a.copy(), self.b.copy(), self.universe.copy()
        return {
            "a": lambda: a, "b": lambda: b, "union": lambda: Union(a, b),
            "intersection": lambda: Intersection(a, b), "a_minus_b": lambda: Difference(a, b),
            "b_minus_a": lambda: Difference(b, a), "symmetric_difference": lambda: Difference(Union(a, b), Intersection(a, b)),
            "complement_a": lambda: Difference(u, a), "complement_b": lambda: Difference(u, b),
        }[operation]()

    def create(self):
        self.picture = self._picture()
        yield Step(self.add(self.picture))

    def shade(self, a):
        self.operation, self.shade_colour = a.operation, a.colour
        anims = self.drop(self.shading)
        self.shading = mark_background(self._region(a.operation).set_fill(colour(a.colour), opacity=0.35).set_stroke(width=0))
        self.shading.set_z_index(-1)
        yield Step(anims + self.add(self.shading))

    def clear(self, a):
        anims = self.drop(self.shading)
        self.shading = self.operation = None
        yield Step(anims)

    def move(self, a):
        self.area = a.area
        old = self.picture
        self.picture = self._picture()
        yield Step(self.drop(old) + self.add(self.picture))
        if self.operation:
            from animation_agent.visuals.specs import VennShadeArgs
            yield from self.shade(VennShadeArgs(operation=self.operation, colour=self.shade_colour))
