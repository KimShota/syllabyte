"""
Layout audit — deterministic legibility checks for every LLM-generated scene.

The Visual Critic (visual_critic.py) is a VLM looking at a few sampled
frames: it misses beats that fall between its samples, and it can pass a
frame that is plainly broken (ku-rl-definition-gemini segment 3 shipped a
blank beat and a diagram running off the right edge with no issues
reported). But Manim already knows the exact geometry of everything on
screen, so most "is this easy to see?" questions don't need vision at all.

GridLayoutScene (layout.py) calls `audit_scene()` after every animation,
on the scene's end state, and collects what it finds into a report that
renderer.py feeds back to the repair ladder. Each message names the
variable and the problem in concrete terms ("runs 0.9 units past the
right edge"), which a repair prompt can act on far more reliably than a
VLM's prose.

Rules, worst first:
  off_frame   an object extends past the edge of the camera frame
  covered     an opaque shape is drawn on top of a text label
  overlap     two labels overlap; a line/border runs through a label; a
              filled shape partly sits under/over a label; an opaque
              shape partly covers another shape
  too_small   text rendered below MIN_FONT_SIZE
  contrast    text below 4.5:1 against what's behind it (WCAG AA), or a
              shape below 3:1 against the background (WCAG 1.4.11)
(`empty_beat` — a beat with nothing on screen — is tracked across a whole
beat, so it lives in layout.py.)

Deliberately allowed: a label fully inside a box, a dot sitting on
anything (dots are markers), arrows and lines touching or crossing shapes,
and translucent or outline-only shapes overlapping (Venn diagrams).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
from manim import (
    DL,
    UR,
    BraceLabel,
    Circle,
    Dot,
    Group,
    ManimColor,
    Mobject,
    Polygram,
    SingleStringMathTex,
    Text,
    VDict,
    VGroup,
    VMobject,
)

from animation_agent.manim_prompt import FRAME_HEIGHT, FRAME_WIDTH

# Smallest legible text on a phone. The codegen prompt asks for font_size
# >= 36 at creation; this leaves room for the scale_to_fit_width() shrinks
# the model routinely applies, while still flagging labels squeezed until
# they're unreadable. Text at 28 is ~0.27 units (~5 mm on a 6" phone) tall.
MIN_FONT_SIZE = 28
MIN_TEXT_CONTRAST = 4.5
MIN_SHAPE_CONTRAST = 3.0

# Geometry tolerances, in Manim units (the frame is 4.5 x 8.0).
EDGE_TOLERANCE = 0.03  # how far past the frame edge counts as "off-frame"
OVERLAP_TOLERANCE = 0.03  # intersections thinner than this are just touching
TEXT_INSET = 0.02  # strokes this close to a label's edge don't "run through" it
# Fraction of the smaller object's area an intersection must reach before
# a partial overlap counts (bounding boxes overestimate round shapes).
MIN_OVERLAP_FRACTION = 0.12
OPAQUE_FILL = 0.6  # fill opacity at which a shape hides what's under it
VISIBLE_OPACITY = 0.05

RULE_ORDER = ["empty_beat", "off_frame", "covered", "overlap", "too_small", "contrast"]

# Containers the audit looks *through*: their parts are checked one by one.
# Everything else (Text, Arrow, Axes, ...) is checked as a single unit.
_GROUP_TYPES = (VGroup, Group, VDict)

_BEZIER_T = np.linspace(0.0, 1.0, 9)
_BERNSTEIN = np.stack(
    [(1 - _BEZIER_T) ** 3, 3 * (1 - _BEZIER_T) ** 2 * _BEZIER_T,
     3 * (1 - _BEZIER_T) * _BEZIER_T ** 2, _BEZIER_T ** 3],
    axis=1,
)


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str
    # Stable identity for de-duplicating the same problem across checks.
    key: tuple


@dataclass
class _Unit:
    mob: Mobject
    kind: str  # "text" | "region" | "connector"
    label: str
    top: str  # label of the top-level scene mobject this unit belongs to
    order: int  # draw order: later units are drawn on top
    bbox: np.ndarray = field(init=False)  # [xmin, ymin, xmax, ymax]

    def __post_init__(self) -> None:
        (x0, y0, _), (x1, y1, _) = self.mob.get_corner(DL), self.mob.get_corner(UR)
        self.bbox = np.array([x0, y0, x1, y1])

    @cached_property
    def strokes(self) -> np.ndarray:
        return _stroke_samples(self.mob, include_fill=False)

    @cached_property
    def marks(self) -> np.ndarray:
        """Strokes plus filled parts (arrow tips) — everything a connector draws."""
        return _stroke_samples(self.mob, include_fill=True)

    @property
    def area(self) -> float:
        return max(self.bbox[2] - self.bbox[0], 0.0) * max(self.bbox[3] - self.bbox[1], 0.0)


# --------------------------------------------------------------------------
# Collecting what's on screen
# --------------------------------------------------------------------------


def _kind(mob: Mobject) -> str:
    if isinstance(mob, (Text, SingleStringMathTex)):
        return "text"
    if isinstance(mob, (Polygram, Circle)):
        return "region"
    return "connector"  # Line/Arrow/Arc/Brace/Axes/NumberLine/...


def _is_visible(mob: Mobject) -> bool:
    for sub in mob.get_family():
        if not isinstance(sub, VMobject) or len(sub.points) == 0:
            continue
        if sub.get_fill_opacity() > VISIBLE_OPACITY:
            return True
        if sub.get_stroke_width() > 0 and sub.get_stroke_opacity() > VISIBLE_OPACITY:
            return True
    return False


def _describe(mob: Mobject, name: str | None, context: str | None) -> str:
    if isinstance(mob, Text):
        what = f'text "{mob.original_text}"'
    elif isinstance(mob, SingleStringMathTex):
        what = f'formula "{mob.tex_string}"'
    else:
        what = type(mob).__name__
    if name:
        return f"`{name}` ({what})"
    if context:
        return f"{what} in `{context}`"
    return what


def collect_units(top_level: list[Mobject], names: dict[int, str]) -> list[_Unit]:
    """Flattens the scene into checkable units, in draw order. `names` maps
    id(mobject) -> the variable name it has in construct(), so findings can
    point at the code."""
    units: list[_Unit] = []
    seen: set[int] = set()
    ordered = sorted(enumerate(top_level), key=lambda p: (p[1].z_index, p[0]))

    def visit(mob: Mobject, context: str | None, top: str) -> None:
        if id(mob) in seen:
            return
        seen.add(id(mob))
        name = names.get(id(mob))
        if type(mob) in _GROUP_TYPES or isinstance(mob, BraceLabel):
            for sub in mob.submobjects:
                visit(sub, name or context, top)
            return
        if _is_visible(mob):
            units.append(_Unit(mob, _kind(mob), _describe(mob, name, context), top, len(units)))

    for _, mob in ordered:
        name = names.get(id(mob))
        visit(mob, None, f"`{name}`" if name else _describe(mob, None, None))
    return units


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------


def _intersection(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])


def _overlap_area(a: _Unit, b: _Unit) -> float:
    w, h = _intersection(a.bbox, b.bbox)
    if w <= OVERLAP_TOLERANCE or h <= OVERLAP_TOLERANCE:
        return 0.0
    return w * h


def _contains(outer: np.ndarray, inner: np.ndarray, tol: float = 0.02) -> bool:
    return (outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1]
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _stroke_samples(mob: Mobject, *, include_fill: bool) -> np.ndarray:
    """Points along every visible stroke (and, for connectors, filled parts
    like arrow tips) of `mob`'s family."""
    chunks = []
    for sub in mob.get_family():
        if not isinstance(sub, VMobject) or len(sub.points) < 4:
            continue
        stroked = sub.get_stroke_width() > 0 and sub.get_stroke_opacity() > VISIBLE_OPACITY
        filled = include_fill and sub.get_fill_opacity() > VISIBLE_OPACITY
        if not (stroked or filled):
            continue
        curves = sub.get_cubic_bezier_tuples()
        if len(curves):
            chunks.append(np.einsum("tk,nkd->ntd", _BERNSTEIN, curves).reshape(-1, 3))
    return np.concatenate(chunks) if chunks else np.zeros((0, 3))


def _crosses(points: np.ndarray, bbox: np.ndarray) -> bool:
    if len(points) == 0:
        return False
    x0, y0, x1, y1 = bbox + np.array([TEXT_INSET, TEXT_INSET, -TEXT_INSET, -TEXT_INSET])
    inside = (points[:, 0] > x0) & (points[:, 0] < x1) & (points[:, 1] > y0) & (points[:, 1] < y1)
    return bool(inside.any())


def _fill_opacity(mob: Mobject) -> float:
    return max((s.get_fill_opacity() for s in mob.get_family() if isinstance(s, VMobject)), default=0.0)


# --------------------------------------------------------------------------
# Color
# --------------------------------------------------------------------------


def _luminance(rgb: np.ndarray) -> float:
    c = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])


def contrast_ratio(a: np.ndarray, b: np.ndarray) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _rgb(color: ManimColor) -> np.ndarray:
    return np.array(color.to_rgb(), dtype=float)


def _first_visible(mob: Mobject) -> VMobject | None:
    return next(
        (s for s in mob.get_family() if isinstance(s, VMobject) and len(s.points) and _is_visible(s)),
        None,
    )


def _text_rgb(unit: _Unit, behind: np.ndarray) -> np.ndarray:
    glyph = _first_visible(unit.mob)
    if glyph is None:
        return behind
    opacity = glyph.get_fill_opacity()
    return _rgb(glyph.get_fill_color()) * opacity + behind * (1 - opacity)


def _shape_rgb(unit: _Unit) -> np.ndarray | None:
    """The color that makes a shape visible: its stroke if it has one,
    else its fill. Opacity is ignored on purpose — dimming a finished part
    of a diagram is a legitimate way to de-emphasize it."""
    part = _first_visible(unit.mob)
    if part is None:
        return None
    if part.get_stroke_width() > 0 and part.get_stroke_opacity() > VISIBLE_OPACITY:
        return _rgb(part.get_stroke_color())
    return _rgb(part.get_fill_color())


def _hex(rgb: np.ndarray) -> str:
    return "#" + "".join(f"{round(float(c) * 255):02X}" for c in rgb)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def _check_frame(units: list[_Unit]) -> list[Finding]:
    """One finding per top-level object, describing every edge it crosses."""
    half_w, half_h = FRAME_WIDTH / 2, FRAME_HEIGHT / 2
    by_top: dict[str, np.ndarray] = {}
    for u in units:
        b = by_top.get(u.top)
        by_top[u.top] = u.bbox.copy() if b is None else np.array(
            [min(b[0], u.bbox[0]), min(b[1], u.bbox[1]), max(b[2], u.bbox[2]), max(b[3], u.bbox[3])]
        )
    findings = []
    for top, (x0, y0, x1, y1) in by_top.items():
        if x1 <= -half_w or x0 >= half_w or y1 <= -half_h or y0 >= half_h:
            continue  # entirely off screen: an exit (e.g. slid away), not a clipped object
        past = []
        if x0 < -half_w - EDGE_TOLERANCE:
            past.append(f"{-half_w - x0:.2f} units past the left edge")
        if x1 > half_w + EDGE_TOLERANCE:
            past.append(f"{x1 - half_w:.2f} units past the right edge")
        if y1 > half_h + EDGE_TOLERANCE:
            past.append(f"{y1 - half_h:.2f} units past the top edge")
        if y0 < -half_h - EDGE_TOLERANCE:
            past.append(f"{-half_h - y0:.2f} units past the bottom edge")
        if past:
            findings.append(Finding(
                "off_frame",
                f"{top} runs off screen: {', '.join(past)} (it spans x {x0:.2f}..{x1:.2f}, "
                f"y {y0:.2f}..{y1:.2f}; the frame is x -{half_w:.2f}..{half_w:.2f}, "
                f"y -{half_h:.2f}..{half_h:.2f}). Make it smaller or move it inward.",
                ("off_frame", top),
            ))
    return findings


def _check_text_vs_region(text: _Unit, shape: _Unit, *, shape_on_top: bool) -> Finding | None:
    area = _overlap_area(text, shape)
    if area == 0:
        return None
    is_dot = isinstance(shape.mob, Dot)
    holds_label = _contains(shape.bbox, text.bbox) and not is_dot
    fill = _fill_opacity(shape.mob)

    if shape_on_top and fill >= OPAQUE_FILL:
        # An opaque shape that hides a label completely is a deliberate
        # cover ("a gray cover slides over the values"); one that leaves
        # it half-visible is a defect.
        if holds_label:
            return None
        return Finding(
            "covered",
            f"{shape.label} is drawn on top of {text.label} and hides part of it. Move one "
            "of them so they don't overlap.",
            ("covered", shape.label, text.label),
        )
    if (not holds_label and (fill > VISIBLE_OPACITY or is_dot)
            and area > MIN_OVERLAP_FRACTION * min(text.area, shape.area)):
        return Finding(
            "overlap",
            f"{text.label} partly overlaps {shape.label}. Put the label fully inside the shape "
            "(and make the shape big enough) or fully outside it.",
            ("overlap", text.label, shape.label),
        )
    if _crosses(shape.strokes, text.bbox):
        return Finding(
            "overlap",
            f"The border of {shape.label} cuts through {text.label}. Make the shape larger "
            "than its label, or move the label clear of the border.",
            ("overlap", shape.label, text.label),
        )
    return None


def _check_pair(a: _Unit, b: _Unit) -> Finding | None:
    """`a` is drawn before (under) `b`."""
    kinds = {a.kind, b.kind}

    if kinds == {"text"}:
        area = _overlap_area(a, b)
        if area > MIN_OVERLAP_FRACTION * min(a.area, b.area):
            return Finding("overlap", f"{a.label} and {b.label} overlap. Move one of them apart.",
                           ("overlap", a.label, b.label))
        return None

    if "text" in kinds:
        text, other = (a, b) if a.kind == "text" else (b, a)
        if other.kind == "connector":
            if _crosses(other.marks, text.bbox):
                return Finding(
                    "overlap",
                    f"{other.label} runs through {text.label}. Move the label beside the line "
                    "(e.g. .next_to(..., buff=0.15)) so nothing crosses the letters.",
                    ("overlap", other.label, text.label),
                )
            return None
        return _check_text_vs_region(text, other, shape_on_top=other is b)

    if kinds == {"region"}:
        # Dots are markers meant to sit on things; nested shapes are fine.
        if isinstance(a.mob, Dot) or isinstance(b.mob, Dot):
            return None
        if _contains(a.bbox, b.bbox) or _contains(b.bbox, a.bbox):
            return None
        # Outline-only and translucent shapes may overlap (e.g. a Venn diagram).
        if _fill_opacity(b.mob) < OPAQUE_FILL:
            return None
        area = _overlap_area(a, b)
        if area > MIN_OVERLAP_FRACTION * min(a.area, b.area):
            return Finding(
                "overlap",
                f"{b.label} partly covers {a.label}. Space them apart (e.g. .arrange(..., buff=0.2)).",
                ("overlap", a.label, b.label),
            )
    return None


def _check_text_size(unit: _Unit) -> Finding | None:
    try:
        size = float(unit.mob.font_size)
    except (AttributeError, ZeroDivisionError):
        return None
    if size < MIN_FONT_SIZE - 0.5:  # font_size=28 measures as 27.99 after scaling
        return Finding(
            "too_small",
            f"{unit.label} is drawn at about font size {size:.0f}, too small to read on a "
            f"phone (needs at least {MIN_FONT_SIZE}). Give it more room or a larger "
            "scale_factor, or shorten it, instead of shrinking it to fit.",
            ("too_small", unit.label),
        )
    return None


def _background_behind(text: _Unit, units: list[_Unit], background: np.ndarray) -> tuple[np.ndarray, str]:
    """The color directly behind a label: the topmost filled shape drawn
    under it that contains it, blended over the scene background."""
    for u in reversed(units[: text.order]):
        if u.kind == "region" and _contains(u.bbox, text.bbox):
            opacity = _fill_opacity(u.mob)
            if opacity > VISIBLE_OPACITY:
                fill = _rgb(u.mob.get_fill_color())
                return fill * opacity + background * (1 - opacity), f"the fill of {u.label}"
    return background, "the background"


def _check_contrast(unit: _Unit, units: list[_Unit], background: np.ndarray) -> Finding | None:
    if unit.kind == "text":
        behind, what = _background_behind(unit, units, background)
        color = _text_rgb(unit, behind)
        ratio = contrast_ratio(color, behind)
        if ratio < MIN_TEXT_CONTRAST:
            return Finding(
                "contrast",
                f"{unit.label} is hard to read: {_hex(color)} on {what} ({_hex(behind)}) is "
                f"{ratio:.1f}:1, needs at least {MIN_TEXT_CONTRAST}:1. Use a lighter text color "
                "or a darker fill behind it.",
                ("contrast", unit.label),
            )
        return None
    color = _shape_rgb(unit)
    if color is None:
        return None
    ratio = contrast_ratio(color, background)
    if ratio < MIN_SHAPE_CONTRAST:
        return Finding(
            "contrast",
            f"{unit.label} is hard to see: {_hex(color)} on the background is {ratio:.1f}:1, "
            f"needs at least {MIN_SHAPE_CONTRAST}:1. Use a brighter color.",
            ("contrast", unit.label),
        )
    return None


def audit_units(units: list[_Unit], background: np.ndarray) -> list[Finding]:
    findings = _check_frame(units)
    for i, a in enumerate(units):
        for b in units[i + 1:]:
            if (f := _check_pair(a, b)) is not None:
                findings.append(f)
        if a.kind == "text" and (f := _check_text_size(a)) is not None:
            findings.append(f)
        if (f := _check_contrast(a, units, background)) is not None:
            findings.append(f)
    return findings


def audit_scene(top_level: list[Mobject], names: dict[int, str], background: ManimColor) -> tuple[list[Finding], bool]:
    """Returns (findings, anything_visible_in_frame)."""
    units = collect_units(top_level, names)
    half_w, half_h = FRAME_WIDTH / 2, FRAME_HEIGHT / 2
    in_frame = any(
        u.bbox[2] > -half_w and u.bbox[0] < half_w and u.bbox[3] > -half_h and u.bbox[1] < half_h
        for u in units
    )
    return audit_units(units, _rgb(background)), in_frame
