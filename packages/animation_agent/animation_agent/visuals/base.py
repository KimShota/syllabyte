"""
Building blocks shared by every template, and the Template base class.

A template object owns a VGroup on the scene. Each action is a generator method that takes its checked
arguments (the Pydantic model from specs.py) and yields Steps: animations played together, each given a share
of the time the runner allots the action. Code between yields runs after the previous step has played, so an
action always sees the screen as it is.

Everything a template draws keeps to the layout audit's rules (layout_audit.py) by construction: text at
font size >= MIN_FONT, colours with enough contrast on black, labels clear of lines, nothing past the area.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

import manim
import numpy as np
from manim import (
    DOWN,
    GREY_B,
    GREY_C,
    LEFT,
    RIGHT,
    UP,
    WHITE,
    Animation,
    FadeIn,
    FadeOut,
    MathTex,
    Text,
    VGroup,
    VMobject,
)
from pydantic import BaseModel

from animation_agent.frame import scene_safe_size
from animation_agent.layout_audit import BACKGROUND_ATTR
from animation_agent.visuals.specs import AREAS, MoveArgs, TemplateSpec

# Text sizes. The layout audit flags text under 28 (layout_audit.MIN_FONT_SIZE); MIN_FONT leaves a margin.
MIN_FONT = 30
BODY_FONT = 34
BIG_FONT = 46
TEX_FONT = 40
NOTE_ROW = 0.45  # height of the one-line note row templates keep at the top of their area


GHOST_COLOUR = manim.RED
GREYED = GREY_C  # 5.9:1 on black: still passes the contrast rules, but reads as "out of play"


def colour(name: str):
    """A spec colour name as a Manim colour. GREY is a light grey, so it still reads on black."""
    return GREY_B if name == "GREY" else getattr(manim, name)


def mark_background(mob: VMobject) -> VMobject:
    setattr(mob, BACKGROUND_ATTR, True)
    return mob


@dataclass
class Box:
    center: np.ndarray
    width: float
    height: float

    @property
    def top(self) -> float:
        return float(self.center[1] + self.height / 2)

    @property
    def bottom(self) -> float:
        return float(self.center[1] - self.height / 2)

    @property
    def left(self) -> float:
        return float(self.center[0] - self.width / 2)

    @property
    def right(self) -> float:
        return float(self.center[0] + self.width / 2)

    def below(self, height: float) -> Box:
        """This box without its top `height`."""
        return Box(self.center + DOWN * height / 2, self.width, self.height - height)

    def top_row(self, height: float) -> Box:
        return Box(np.array([self.center[0], self.top - height / 2, 0.0]), self.width, height)


AREA_PADDING = 0.05


def area_box(area: str) -> Box:
    """The part of the safe frame an area covers: a band of the six grid rows, the full safe width."""
    safe_w, safe_h = scene_safe_size()
    first, last = AREAS[area]
    row_h = safe_h / 6
    top = safe_h / 2 - first * row_h
    bottom = safe_h / 2 - (last + 1) * row_h
    return Box(np.array([0.0, (top + bottom) / 2, 0.0]), safe_w - 2 * AREA_PADDING,
               top - bottom - 2 * AREA_PADDING)


def text(s: str, size: int = BODY_FONT, col=WHITE, max_width: float | None = None) -> Text:
    """One line of text, made smaller (down to MIN_FONT) until it is at most `max_width` wide."""
    t = Text(s, font_size=size, color=col)
    while max_width is not None and t.width > max_width and size > MIN_FONT:
        size -= 2
        t = Text(s, font_size=size, color=col)
    return t


def wrapped(s: str, max_width: float, size: int = BODY_FONT, col=WHITE, max_lines: int = 3) -> Text:
    """Text broken onto lines no wider than `max_width` (by measuring), at most `max_lines` of them."""
    words, lines = s.split(), []
    while words:
        line = words.pop(0)
        while words and Text(f"{line} {words[0]}", font_size=size).width <= max_width:
            line = f"{line} {words.pop(0)}"
        lines.append(line)
    if len(lines) > max_lines and size > MIN_FONT:
        return wrapped(s, max_width, size - 2, col, max_lines)
    return Text("\n".join(lines), font_size=size, color=col, line_spacing=0.8)


def tex(s: str, size: int = TEX_FONT, col=WHITE, isolate: list[str] | None = None) -> MathTex:
    parts = [p for p in (isolate or []) if p and p in s]
    return MathTex(s, font_size=size, color=col, substrings_to_isolate=parts or None)


def fit(mob: VMobject, box: Box, *, grow: bool = False) -> VMobject:
    """Scales `mob` to fit inside `box` (never up unless `grow`) and centres it there."""
    if mob.width > 0 and mob.height > 0:
        factor = min(box.width / mob.width, box.height / mob.height)
        if factor < 1 or grow:
            mob.scale(factor)
    mob.move_to(box.center)
    return mob


def fit_width(mob: VMobject, max_width: float) -> VMobject:
    if mob.width > max_width:
        mob.scale_to_fit_width(max_width)
    return mob


def same_parts(a: VMobject, b: VMobject) -> bool:
    """Whether two mobjects have the same tree of parts, each part with points or each without."""
    if len(a.submobjects) != len(b.submobjects) or (a.has_points() != b.has_points()):
        return False
    return all(same_parts(x, y) for x, y in zip(a.submobjects, b.submobjects))


@dataclass
class Step:
    anims: list[Animation]
    share: float = 1.0  # this step's fraction of the action's time


Steps = Iterator[Step]


class Template:
    """One template object on the scene. Subclasses set `spec`, implement `create` and one generator method per
    action in the spec, and may set `durations` (seconds an action takes when the line is long enough)."""

    spec: ClassVar[TemplateSpec]
    durations: ClassVar[dict[str, float]] = {}
    DEFAULT_DURATION: ClassVar[float] = 0.8

    def __init__(self, scene, params: BaseModel, uses: set[str] | None = None):
        self.scene = scene
        self.p = params
        self.area: str = params.area
        self.group = VGroup()
        # The actions this segment will call on the object (runner.SpecRunner reads the whole segment first), so
        # the layout only keeps room for what will appear. None: assume everything.
        self.uses = uses

    def will(self, *actions: str) -> bool:
        return self.uses is None or any(a in self.uses for a in actions)

    @property
    def bounds(self) -> Box:
        return area_box(self.area)

    @classmethod
    def duration(cls, action: str | None) -> float:
        return cls.durations.get(action or "create", cls.DEFAULT_DURATION)

    # Adding and removing parts. A part is added to the group and faded in by the same step; removing takes it
    # out of the group first, so the scene never keeps a stale copy through the group (see the module docstring).

    def add(self, *mobs: VMobject) -> list[Animation]:
        for m in mobs:
            self.group.add(m)
        return [FadeIn(m) for m in mobs]

    def drop(self, *mobs: VMobject | None) -> list[Animation]:
        anims = []
        for m in mobs:
            if m is None:
                continue
            self.group.remove(m)
            anims.append(FadeOut(m))
        return anims

    def morph(self, old: VMobject, new: VMobject) -> tuple[list[Animation], VMobject]:
        """Animations that turn `old` into `new`, and the mobject that is on screen afterwards. `become` when the
        two have the same parts, so a bar grows and a cell recolours in place; else a fade out and in. Morphing
        a part into nothing (a cell emptied, a bar's number left off) squeezes it to a point that stays on screen:
        in runs/general-3 that left "8.8" and eight bar numbers at font size 0, black on black."""
        if same_parts(old, new):
            return [old.animate.become(new)], old
        self.group.remove(old)
        self.group.add(new)
        return [FadeOut(old), FadeIn(new)], new

    def swap_in(self, old: VMobject, new: VMobject) -> None:
        """Replaces `old` with `new` at once (no animation): e.g. a formula rebuilt with a piece isolated."""
        self.group.remove(old)
        self.scene.remove(old)
        self.group.add(new)
        self.scene.add(new)

    def create(self) -> Steps:
        raise NotImplementedError

    def remove(self, a: BaseModel) -> Steps:
        yield Step([FadeOut(self.group)])

    def move(self, a: MoveArgs) -> Steps:
        """Default: scale into the new area. Templates with text re-lay themselves out instead, so their text
        stays readable in a smaller area."""
        old, self.area = self.bounds, a.area
        new = self.bounds
        factor = min(new.width / old.width, new.height / old.height)
        shift = new.center - old.center
        self.moved(factor, old.center, shift)
        yield Step([self.group.animate.scale(factor, about_point=old.center).shift(shift)])

    def moved(self, factor: float, about: np.ndarray, shift: np.ndarray) -> None:
        """Hook for templates that keep screen coordinates (an origin, a unit length)."""


# Re-exported for the template modules.
__all__ = [
    "BIG_FONT", "BODY_FONT", "Box", "DOWN", "GHOST_COLOUR", "GREYED", "LEFT", "MIN_FONT", "NOTE_ROW", "RIGHT",
    "Step", "Steps", "TEX_FONT", "Template", "UP", "area_box", "colour", "fit", "fit_width", "mark_background",
    "tex", "text", "wrapped",
]
