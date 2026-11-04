"""Note: a short piece of text, wrapped to its area."""

from __future__ import annotations

from manim import FadeIn, FadeOut

from animation_agent.visuals.base import BIG_FONT, BODY_FONT, Step, Steps, Template, colour, wrapped
from animation_agent.visuals.specs import NOTE


class Note(Template):
    spec = NOTE
    durations = {"create": 0.6, "say": 0.7}

    def _text(self, s: str, col_name: str):
        self.text, self.col = s, col_name
        size = BIG_FONT if self.p.big else BODY_FONT
        mob = wrapped(s, self.bounds.width, size, colour(col_name))
        if mob.height > self.bounds.height:
            mob.scale_to_fit_height(self.bounds.height)
        return mob.move_to(self.bounds.center)

    def create(self) -> Steps:
        self.mob = self._text(self.p.text, self.p.colour)
        self.group.add(self.mob)
        yield Step([FadeIn(self.mob)])

    def move(self, a) -> Steps:
        """Re-wrap the text for the new area (scaling would shrink it)."""
        self.area = a.area
        old, self.mob = self.mob, self._text(self.text, self.col)
        self.group.remove(old)
        self.group.add(self.mob)
        yield Step([FadeOut(old), FadeIn(self.mob)])

    def say(self, a) -> Steps:
        old, self.mob = self.mob, self._text(a.text, a.colour)
        self.group.remove(old)
        self.group.add(self.mob)
        yield Step([FadeOut(old), FadeIn(self.mob)])
