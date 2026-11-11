"""
Draws a picture program's snapshots (scene/api.py) and animates the change from one to the next.

Every part on screen has a key (a node's, a link's, a cell's index...). Showing snapshot i builds the parts it
needs, then compares keys with what is on screen: a part in both turns into its new self in place (`become`, so a
node slides to its new spot and a cell recolours), a new part fades in, a gone part fades out. Nothing is
positioned by the model: scene/layout.py decides where everything goes.

Colours keep to the layout audit's contrast rules: shapes are outlined (fill stays opaque black, so a white label
always reads), and a style changes the outline and the label colour.
"""

from __future__ import annotations

import numpy as np
from manim import (
    BLACK,
    BLUE_D,
    GREEN,
    GREY_B,
    GREY_C,
    ORANGE,
    RED,
    TEAL,
    WHITE,
    YELLOW,
    Arrow,
    Circle,
    FadeIn,
    FadeOut,
    Line,
    Rectangle,
    Square,
    Text,
    Triangle,
    VGroup,
    VMobject,
)

from animation_agent.frame import scene_safe_size
from animation_agent.layout_audit import BACKGROUND_ATTR
from animation_agent.scene import layout as L

FONT = 30
MONO = "Menlo"
STYLE_COLOUR = {None: WHITE, "current": YELLOW, "visited": TEAL, "found": GREEN, "compare": ORANGE, "red": RED,
                "grey": GREY_C, "new": YELLOW}
LIQUID = BLUE_D


def _bg(m: VMobject) -> VMobject:
    setattr(m, BACKGROUND_ATTR, True)
    return m


def _same_parts(a: VMobject, b: VMobject) -> bool:
    if len(a.submobjects) != len(b.submobjects) or a.has_points() != b.has_points():
        return False
    return all(_same_parts(x, y) for x, y in zip(a.submobjects, b.submobjects))


def _text(s: str, colour=WHITE, mono: bool = False) -> Text:
    return Text(s, font_size=FONT, color=colour, **({"font": MONO} if mono else {}))


class PictureRunner:
    def __init__(self, scene, snaps: list[dict]):
        self.scene = scene
        self.snaps = snaps
        w, h = scene_safe_size()
        self.layout = L.plan(snaps, w, h, h / 2)
        self.on_screen: dict[str, VMobject] = {}
        # containers are drawn to one scale, so a 3-litre jug is shorter than a 5-litre one
        self.max_capacity = max((v["capacity"] for s in snaps for v in s["views"].values() if v["kind"] == "container"),
                                default=1)
        self.shown: int | None = None

    # ---- parts of one snapshot -------------------------------------------------------------------------

    def parts(self, i: int) -> dict[str, VMobject]:
        out: dict[str, VMobject] = {}
        for name, view in self.snaps[i]["views"].items():
            region = self.layout.regions[name]
            if view.get("title") and view["kind"] != "container":
                t = _text(view["title"], GREY_B)
                t.move_to([region.cx, region.top - L.TITLE_H / 2, 0])
                out[f"{name}:title"] = t
            getattr(self, f"_{view['kind']}")(name, view, region, out)
        return out

    def _nodes(self, name, view, region, out):
        scale = self.layout.nodes[name]
        r = scale.r
        font = min(42, round(FONT * r / L.NODE_R))
        pos = L.layout_nodes(view, region, self.layout.graph_pos.get(name), scale)
        for a, b, style, label, _slot in view["links"]:
            if a not in pos or b not in pos:
                continue
            p, q = pos[a], pos[b]
            d = (q - p) / max(np.linalg.norm(q - p), 1e-6)
            start, end = p + d * r, q - d * r
            colour = STYLE_COLOUR.get(style, WHITE) if style else GREY_B
            width = 7 if style == "red" else 3
            if view["directed"]:
                line = Arrow(start, end, buff=0, stroke_width=width, color=colour, tip_length=0.14,
                             max_tip_length_to_length_ratio=0.35)
            else:
                line = Line(start, end, stroke_width=width, color=colour)
            out[f"{name}:link:{a}>{b}"] = _bg(line)
            if label:
                t = _text(label, GREY_B)
                normal = np.array([-d[1], d[0], 0.0])
                t.move_to((p + q) / 2 + normal * 0.22)
                out[f"{name}:linklabel:{a}>{b}"] = t
        for k, node in view["nodes"].items():
            colour = STYLE_COLOUR[node["style"]]
            circle = Circle(radius=r, stroke_color=colour, stroke_width=6 if node["style"] else 3,
                            fill_color=BLACK, fill_opacity=1)
            label = Text(node["label"], font_size=font, color=colour)
            out[f"{name}:node:{k}"] = VGroup(circle, label).move_to(pos[k])

    def _cells(self, name, view, region, out):
        size = self.layout.cell[name]
        n = len(view["values"])
        title = L.TITLE_H if view.get("title") else 0.0
        y = region.top - title - size / 2
        left = region.cx - size * n / 2
        for i, v in enumerate(view["values"]):
            style = view["marks"].get(str(i))
            colour = STYLE_COLOUR[style]
            box = Square(side_length=size, stroke_color=colour, stroke_width=6 if style else 3,
                         fill_color=BLACK, fill_opacity=1)
            x = left + size * (i + 0.5)
            group = VGroup(box)
            if v != "":
                group.add(_text(v, colour))
            out[f"{name}:cell:{i}"] = group.move_to([x, y, 0])
            if view["index"]:
                idx = _text(str(i), GREY_B)
                idx.move_to([x, y - size / 2 - L.INDEX_H / 2, 0])
                out[f"{name}:index:{i}"] = idx
        below = y - size / 2 - (L.INDEX_H if view["index"] else 0.0)
        for label, i in view["pointers"].items():
            t = _text(label, YELLOW)
            t.move_to([left + size * (i + 0.5), below - L.POINTER_H / 2, 0])
            out[f"{name}:pointer:{label}"] = t

    def _code(self, name, view, region, out):
        title = L.TITLE_H if view.get("title") else 0.0
        left = region.cx - region.w / 2 + 0.3
        for j, line in enumerate(view["lines"]):
            current = view["current"] == j
            t = _text(line, YELLOW if current else WHITE, mono=True)
            y = region.top - title - L.CODE_LINE_H * (j + 0.5)
            t.move_to([left + t.width / 2, y, 0])
            out[f"{name}:line:{j}"] = t
        if view["current"] is not None:
            y = region.top - title - L.CODE_LINE_H * (view["current"] + 0.5)
            marker = Triangle(color=YELLOW, fill_color=YELLOW, fill_opacity=1).scale(0.08).rotate(-np.pi / 2)
            marker.move_to([left - 0.17, y, 0])
            out[f"{name}:marker"] = marker

    def _container(self, name, view, region, out):
        """Drawn to one scale with the other containers, the tallest filling its band (up to 3.2 units), all
        standing on one line, each with its title above it and its amount below."""
        title = L.TITLE_H if view.get("title") else 0.0
        label_h = 0.42
        avail = region.h - title - 0.1 - label_h
        tallest = min(avail, 3.2)
        height = tallest * view["capacity"] / self.max_capacity
        width = min(region.w * 0.6, 1.4)
        bottom = region.bottom + label_h + (avail - tallest) / 2
        top = bottom + height
        liquid_h = height * view["level"] / view["capacity"] if view["capacity"] else 0
        if liquid_h > 1e-6:
            liquid = Rectangle(width=width - 0.08, height=liquid_h, stroke_width=0, fill_color=LIQUID,
                               fill_opacity=1)
            liquid.move_to([region.cx, bottom + liquid_h / 2, 0])
        else:  # an empty vessel keeps a zero-height liquid, so filling it grows in place
            liquid = Rectangle(width=width - 0.08, height=0.001, stroke_width=0, fill_color=LIQUID, fill_opacity=0)
            liquid.move_to([region.cx, bottom, 0])
        out[f"{name}:liquid"] = _bg(liquid)
        x0, x1 = region.cx - width / 2, region.cx + width / 2
        wall = VGroup(Line([x0, top, 0], [x0, bottom, 0]), Line([x0, bottom, 0], [x1, bottom, 0]),
                      Line([x1, bottom, 0], [x1, top, 0])).set_stroke(STYLE_COLOUR[view["style"]], 4)
        out[f"{name}:wall"] = _bg(wall)
        amount = _text(f"{view['level']} / {view['capacity']}", STYLE_COLOUR[view["style"]])
        amount.move_to([region.cx, bottom - label_h / 2 - 0.02, 0])
        out[f"{name}:amount"] = amount
        if view.get("title"):
            t = _text(view["title"], GREY_B)
            t.move_to([region.cx, top + L.TITLE_H / 2 + 0.06, 0])
            out[f"{name}:title"] = t

    # ---- showing ---------------------------------------------------------------------------------------

    def show(self, i: int, seconds: float) -> None:
        target = self.parts(i)
        anims = []
        for key, new in target.items():
            old = self.on_screen.get(key)
            if old is None:
                anims.append(FadeIn(new))
                self.on_screen[key] = new
            elif _same_parts(old, new):
                anims.append(old.animate.become(new))
            else:
                anims += [FadeOut(old), FadeIn(new)]
                self.on_screen[key] = new
        for key in [k for k in self.on_screen if k not in target]:
            anims.append(FadeOut(self.on_screen.pop(key)))
        if anims:
            self.scene.play(*anims, run_time=max(seconds, 0.1))
        self.shown = i
