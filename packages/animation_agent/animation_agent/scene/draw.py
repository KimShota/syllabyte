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
    BLUE_C,
    BLUE_D,
    PINK,
    Arc,
    Difference,
    Dot,
    Intersection,
    Polygon,
    ReplacementTransform,
    interpolate_color,
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
from manim import DashedLine, RoundedRectangle

from animation_agent.scene import diagram_layout as D
from animation_agent.scene.api import GRAPH_LAYOUTS
from animation_agent.scene import layout as L
from animation_agent.scene import math_layout as M
from animation_agent.scene import text_layout as T

FONT = 30
MONO = "Menlo"
STYLE_COLOUR = {None: WHITE, "current": YELLOW, "visited": TEAL, "found": GREEN, "compare": ORANGE, "red": RED,
                "grey": GREY_C, "new": YELLOW, "blue": BLUE_C}
CURVE_COLOURS = (BLUE_C, ORANGE, PINK, TEAL)  # unstyled curves, in the order they were drawn
FILL = 0.4  # shaded areas, rectangles and Venn regions: translucent, so what is under them shows
LIQUID = BLUE_D


HEAT = ("#1d2b53", "#2a6f97", "#2a9d8f", "#8ab17d", "#e9c46a")  # low to high: dark navy to yellow


def heat_colour(t: float):
    """A value's colour on the heat scale, t from 0 (low) to 1 (high)."""
    from manim import ManimColor

    t = min(max(float(t), 0.0), 1.0) * (len(HEAT) - 1)
    i = min(int(t), len(HEAT) - 2)
    return interpolate_color(ManimColor(HEAT[i]), ManimColor(HEAT[i + 1]), t - i)


def readable_on(fill):
    """White or black, whichever reads better on this fill (the layout audit's contrast rule)."""
    from animation_agent.layout_audit import contrast_ratio

    rgb = np.array(fill.to_rgb())
    return WHITE if contrast_ratio(np.array([1.0, 1.0, 1.0]), rgb) >= contrast_ratio(np.zeros(3), rgb) else BLACK


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
    """Draws `snaps` in an area of the frame (width, height, top; centred), or the whole safe frame. With `group`
    (a template's VGroup), parts on screen are kept in it, so the template can fade or move the whole picture."""

    def __init__(self, scene, snaps: list[dict], area: tuple[float, float, float] | None = None,
                 group: VGroup | None = None):
        self.scene = scene
        self.snaps = snaps
        if area is None:
            w, h = scene_safe_size()
            area = (w, h, h / 2)
        # a layout for each run of snapshots with the same views, so the picture has the whole frame until a
        # formula or code panel joins it (layout.plan_groups); titles a run leaves out to give the picture room
        # are left out of its snapshots
        self.where: list[tuple[int, int]] = [(0, 0)] * len(snaps)
        self.layouts, self.drawn = [], []
        for gi, (members, layout) in enumerate(L.plan_groups(snaps, *area)):
            run = [snaps[i] for i in members]
            self.layouts.append(layout)
            self.drawn.append(L.without_titles(run, layout.untitled) if layout.untitled else run)
            for k, i in enumerate(members):
                self.where[i] = (gi, k)
        self.layout = self.layouts[0]
        self.group = group
        self.on_screen: dict[str, VMobject] = {}
        # containers are drawn to one scale, so a 3-litre jug is shorter than a 5-litre one
        self.max_capacity = max((v["capacity"] for s in snaps for v in s["views"].values() if v["kind"] == "container"),
                                default=1)
        self.shown: int | None = None

    # ---- parts of one snapshot -------------------------------------------------------------------------

    def parts(self, i: int) -> dict[str, VMobject]:
        out: dict[str, VMobject] = {}
        gi, k = self.where[i]
        self.layout = self.layouts[gi]
        group = self.drawn[gi]
        for name, view in group[k]["views"].items():
            # a view laid out snapshot by snapshot (a scrolled code panel, a turning 3D scene) is laid out over the
            # snapshots of its run it appears in, so it reads its own index among them
            self._snap = sum(1 for s in group[:k] if name in s["views"])
            region = self.layout.regions[name]
            if view.get("title") and view["kind"] != "container":
                t = _text(M.pretty(view["title"]), GREY_B)
                t.move_to([region.cx, region.top - L.TITLE_H / 2, 0])
                out[f"{name}:title"] = t
            getattr(self, f"_{view['kind']}")(name, view, region, out)
        return out

    def _nodes(self, name, view, region, out):
        scale = self.layout.nodes[name]
        r = scale.r
        font = min(42, round(FONT * r / L.NODE_R))
        pos = L.layout_nodes(view, region, self.layout.graph_pos.get(name), scale)
        graph = view["layout"] in GRAPH_LAYOUTS
        spots = self.layout.labels.get(name, {}) if graph else (L.tree_labels(view, region, scale) or {})
        label_font = self.layout.label_font.get(name, FONT)
        present = {(a, b) for a, b, *_ in view["links"]}
        for a, b, style, label, slot in view["links"]:
            if a not in pos or b not in pos:
                continue
            start, end = L.link_segment(pos, a, b, r, bool(view["directed"]) and (b, a) in present)
            keys = view["nodes"][a].get("keys")
            if keys and slot is not None and not graph:  # a B-tree's child hangs from the gap between two keys
                left = pos[a][0] - L.KEY_W * len(keys) / 2
                start = np.array([left + L.KEY_W * min(max(int(slot), 0), len(keys)), pos[a][1] - r, 0.0])
                end = pos[b] + np.array([0.0, r, 0.0])
            colour = STYLE_COLOUR.get(style, WHITE) if style else GREY_B
            width = 7 if style == "red" else 3
            spot = spots.get(f"{a}>{b}") if label else None
            d = (end - start) / max(np.linalg.norm(end - start), 1e-6)
            pieces = [(start, end)]
            if spot is not None and L._seg_dist(start, end, spot) < 1e-3:  # set into the link: a gap around it
                k = label_font / L.LABEL_FONT
                half = np.array([L.LABEL_CHAR_W * k * len(str(label)) / 2, L.LABEL_H * k / 2]) + L.LABEL_ROOM
                gap = L.label_gap(d, half)
                pieces = [(start, spot - d * gap), (spot + d * gap, end)]
            parts = []
            for j, (p0, p1) in enumerate(pieces):
                if view["directed"] and j == len(pieces) - 1:
                    parts.append(Arrow(p0, p1, buff=0, stroke_width=width, color=colour, tip_length=0.16,
                                       max_tip_length_to_length_ratio=0.5))
                else:
                    parts.append(Line(p0, p1, stroke_width=width, color=colour))
            out[f"{name}:link:{a}>{b}"] = parts[0] if len(parts) == 1 else VGroup(*parts)
            if label:
                # beside its link or set into it, clear of every node, link and label (layout.place_labels), so
                # the layout audit checks it like any other text
                t = Text(str(label), font_size=label_font, color=GREY_B)
                out[f"{name}:linklabel:{a}>{b}"] = t.move_to(spot if spot is not None else (pos[a] + pos[b]) / 2)
        for k, node in view["nodes"].items():
            colour = STYLE_COLOUR[node["style"]]
            if node.get("keys") and not graph:  # a B-tree node: its keys side by side in one box
                n = len(node["keys"])
                box = Rectangle(width=L.KEY_W * n, height=2 * r, stroke_color=colour,
                                stroke_width=6 if node["style"] else 3, fill_color=BLACK, fill_opacity=1)
                parts = VGroup(box)
                for j, key_text in enumerate(node["keys"]):
                    x = -L.KEY_W * n / 2 + L.KEY_W * (j + 0.5)
                    parts.add(Text(key_text, font_size=L.PILL_FONT, color=colour).move_to([x, 0, 0]))
                    if j:
                        parts.add(Line([x - L.KEY_W / 2, -r, 0], [x - L.KEY_W / 2, r, 0], stroke_width=2, color=colour))
                out[f"{name}:node:{k}"] = parts.move_to(pos[k])
                continue
            if not graph and len(node["label"]) > 2:  # a pill round a longer label (layout.pill_w)
                pill = RoundedRectangle(width=max(L.pill_w(node["label"]), 2 * r), height=2 * r, corner_radius=r,
                                        stroke_color=colour, stroke_width=6 if node["style"] else 3, fill_color=BLACK,
                                        fill_opacity=1)
                label = Text(node["label"], font_size=L.PILL_FONT, color=colour)
                out[f"{name}:node:{k}"] = VGroup(pill, label).move_to(pos[k])
                continue
            circle = Circle(radius=r, stroke_color=colour, stroke_width=6 if node["style"] else 3,
                            fill_color=BLACK, fill_opacity=1)
            size = font
            label = Text(node["label"], font_size=size, color=colour)
            while np.hypot(label.width / 2, label.height / 2) > r - 0.03 and size > FONT:  # inside the circle
                size -= 2
                label = Text(node["label"], font_size=size, color=colour)
            out[f"{name}:node:{k}"] = VGroup(circle, label).move_to(pos[k])

    def _cells(self, name, view, region, out):
        size = self.layout.cell[name]
        n = len(view["values"])
        title = L.TITLE_H if view.get("title") else 0.0
        y = region.top - title - size / 2
        first, shown = 0, n
        if name in self.layout.windows:  # a long array: a window onto it, "…" on the side it goes on
            shown, starts = self.layout.windows[name]
            first = starts[self._snap]
            for side, more, x in (("l", first > 0, region.cx - size * shown / 2 - L.ELLIPSIS_W / 2),
                                  ("r", first + shown < n, region.cx + size * shown / 2 + L.ELLIPSIS_W / 2)):
                if more:
                    out[f"{name}:more:{side}"] = _text("…", GREY_B).move_to([x, y, 0])
        left = region.cx - size * shown / 2 - size * first
        for i, v in enumerate(view["values"]):
            if not first <= i < first + shown:
                continue
            style = view["marks"].get(str(i))
            colour = STYLE_COLOUR[style]
            box = Square(side_length=size, stroke_color=colour, stroke_width=6 if style else 3,
                         fill_color=BLACK, fill_opacity=1)
            x = left + size * (i + 0.5)
            group = VGroup(box)
            if v != "":
                font = max(FONT, min(44, round(FONT * size / L.CELL)))
                label = Text(v, font_size=font, color=colour)
                while label.width > 0.74 * size and font > FONT:  # a margin inside the box
                    font -= 2
                    label = Text(v, font_size=font, color=colour)
                group.add(label)
            out[f"{name}:cell:{i}"] = group.move_to([x, y, 0])
            if view["index"]:
                idx = _text(str(i), GREY_B)
                idx.move_to([x, y - size / 2 - L.INDEX_H / 2, 0])
                out[f"{name}:index:{i}"] = idx
        below = y - size / 2 - (L.INDEX_H if view["index"] else 0.0)
        stacked: dict[int, int] = {}
        for label, i in sorted(view["pointers"].items()):  # pointers under one cell stack, a row each
            if not first <= i < first + shown:
                continue
            row = stacked.get(i, 0)
            stacked[i] = row + 1
            t = _text(label, YELLOW)
            t.move_to([left + size * (i + 0.5), below - L.POINTER_H * (row + 0.5), 0])
            out[f"{name}:pointer:{label}"] = t

    def _code(self, name, view, region, out):
        """The rows in the snapshot's window (scene/text_layout.py), each keyed by its logical line and part, so a
        scroll slides them; the current line yellow with a marker, a marked line in its style; watched variables
        in chips under the code."""
        lay: T.CodeLayout = self.layout.math[name]
        snap = self._snap
        rows, start = lay.rows[snap], lay.start[snap]
        marks = view.get("marks", {})
        shown = range(start, min(len(rows), start + lay.window))
        part: dict[int, int] = {}
        for k, (i, text, _cont) in enumerate(rows):
            part[k] = sum(1 for kk in range(k) if rows[kk][0] == i)
            if k not in shown or not text.strip():
                continue
            colour = YELLOW if view["current"] == i else STYLE_COLOUR.get(marks.get(str(i)), WHITE)
            t = Text(text.strip(), font_size=lay.font, color=colour, font=MONO)
            lead = len(text) - len(text.lstrip(" "))
            t.move_to([lay.left + lead * T.INDENT * T.char_w(lay.font) + t.width / 2, T.code_row_y(lay, k, snap), 0])
            out[f"{name}:line:{i}:{part[k]}"] = t
        if view["current"] is not None:
            mine = [k for k in shown if rows[k][0] == view["current"]]
            if mine:
                marker = Triangle(color=YELLOW, fill_color=YELLOW, fill_opacity=1).scale(0.08).rotate(-np.pi / 2)
                marker.move_to([lay.left - 0.17, T.code_row_y(lay, mine[0], snap), 0])
                out[f"{name}:marker"] = marker
        if lay.scrolled:  # small grey arrows say more code is above or below the window
            for side, more in (("up", start > 0), ("down", start + lay.window < len(rows))):
                if not more:
                    continue
                y = (lay.top + T.MORE_H / 2) if side == "up" else (lay.top - T.CODE_LINE_H * lay.window - T.MORE_H / 2)
                tri = Triangle(color=GREY_B, fill_color=GREY_B, fill_opacity=1).scale(0.07)
                if side == "down":
                    tri.rotate(np.pi)
                out[f"{name}:more:{side}"] = tri.move_to([lay.left - 0.17, y, 0])
        for wname, value in view.get("watch", {}).items():
            cx, cy, w = lay.watch[wname]
            box = RoundedRectangle(width=w, height=T.WATCH_H - 0.08, corner_radius=0.1, stroke_color=TEAL,
                                   stroke_width=3, fill_color=BLACK, fill_opacity=1).move_to([cx, cy, 0])
            label = Text(T.watch_text(wname, value), font_size=FONT, color=WHITE).move_to([cx, cy, 0])
            out[f"{name}:watch:{wname}"] = VGroup(box, label)

    def _tape(self, name, view, region, out):
        """One-character cells on one line or wrapped onto more, the rows aligned under them (keyed by their own
        index, so a row that shifts slides along), then the index, heads and field brackets."""
        lay: T.TapeLayout = self.layout.math[name]
        start = FONT if lay.h < 0.5 else 34

        def cell(text, colour, style, x, y):
            box = Rectangle(width=lay.w, height=lay.h, stroke_color=colour, stroke_width=6 if style else 3,
                            fill_color=BLACK, fill_opacity=1).move_to([x, y, 0])
            group = VGroup(box)
            if text:
                font = start
                t = Text(text, font_size=font, color=colour)
                while t.width > lay.w - 0.05 and font > 28:  # down to the audit's minimum in a narrow cell
                    font -= 2
                    t = Text(text, font_size=font, color=colour)
                group.add(t.move_to([x, y, 0]))
            return group

        # an index under every cell when the numbers fit the cells, else under every 2nd or 5th
        every = next((k for k in (1, 2, 5, 10) if M.text_width(str(len(view["values"]) - 1)) * 28 / 30 + 0.06
                      <= lay.w * k), 10)
        for j, v in enumerate(view["values"]):
            style = view["marks"].get(str(j))
            out[f"{name}:cell:{j}"] = cell(v, STYLE_COLOUR[style], style, lay.x(j), lay.y(j))
            if lay.index and j % every == 0:
                out[f"{name}:index:{j}"] = Text(str(j), font_size=28, color=GREY_B).move_to(
                    [lay.x(j), T.index_y(lay, j), 0])
        for r, key in enumerate(lay.rows):
            row = view["rows"].get(key)
            if row is None:
                continue
            for jj, v in enumerate(row["values"]):
                j = row["at"] + jj
                style = row["marks"].get(str(jj))
                out[f"{name}:row:{key}:{jj}"] = cell(v, STYLE_COLOUR[style], style, lay.x(j), lay.y(j, r))
            if row.get("label"):
                t = _text(row["label"], GREY_B)
                out[f"{name}:rowname:{key}"] = t.move_to([lay.label_x - t.width / 2, lay.y(0, r), 0])
        stacked: dict[int, int] = {}
        for label, j in sorted(view["heads"].items()):
            k = stacked.get(j, 0)
            stacked[j] = k + 1
            c = T.head_spot(lay, j, k)
            caret = Triangle(color=YELLOW, fill_color=YELLOW, fill_opacity=1).scale(0.06).move_to(
                [c[0] - 0.02 - 0.09 * len(label), c[1], 0])
            t = _text(label, YELLOW).move_to([c[0] + 0.08, c[1], 0])
            out[f"{name}:head:{label}"] = VGroup(caret, t)
        for key, (a, b, label, style) in view["fields"].items():
            colour = STYLE_COLOUR[style] if style else GREY_B
            parts = VGroup()
            for x0, x1, y in T.field_segments(lay, a, b):
                parts.add(VMobject(stroke_width=3, color=colour).set_points_as_corners(
                    [[x0, y + 0.08, 0], [x0, y, 0], [x1, y, 0], [x1, y + 0.08, 0]]))
            spot = lay.field_spots.get((key, label)) if label else None
            if spot is not None:  # placed clear of the other fields' labels (text_layout.place_field_labels)
                parts.add(Text(label, font_size=FONT, color=colour).move_to([spot[0], spot[1], 0]))
            out[f"{name}:field:{key}"] = parts

    def _formula(self, name, view, region, out):
        """Each TeX line centred in its row, scaled down to fit the band (visuals/base.tex: a line LaTeX can't
        compile falls back to plain text), its style colouring the line and its lit terms their own colour."""
        from manim import SurroundingRectangle

        from animation_agent.visuals.base import fit_width, tex

        lay: T.FormulaLayout = self.layout.math[name]
        snap = self._snap
        if lay.start[snap] > 0:  # older lines scrolled up out of view
            tri = Triangle(color=GREY_B, fill_color=GREY_B, fill_opacity=1).scale(0.07)
            out[f"{name}:more"] = tri.move_to([region.cx - region.w / 2 + 0.12, lay.top + T.MORE_H / 2, 0])
        for j, line in enumerate(view["lines"]):
            if not lay.start[snap] <= j < lay.end[snap]:
                continue
            y, pitch = T.formula_row(lay, j, snap)
            terms = view["terms"].get(str(j), [])
            colour = STYLE_COLOUR.get(view["styles"].get(str(j)), WHITE)
            t = tex(line, col=colour, isolate=[term for term, _ in terms])
            for term, style in terms:
                t.set_color_by_tex(term, STYLE_COLOUR[style])
            fit_width(t, region.w - 0.3)
            cap = pitch * (0.7 if j in view["boxed"] else 0.86)  # a boxed result leaves room for its box
            if t.height > cap:
                t.scale_to_fit_height(cap)
            # never below the audit's minimum font (28 of 40): a line too wide or tall for that overruns a little
            # rather than becoming unreadable; the layout gives tall lines room so this rarely happens
            if t.font_size < 28:
                t.scale(28 / t.font_size)
            t.move_to([region.cx, y, 0])
            out[f"{name}:formula:{j}"] = t
            if j in view["boxed"]:
                out[f"{name}:box:{j}"] = SurroundingRectangle(t, color=GREEN, buff=0.08, stroke_width=4)

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

    # ---- math ------------------------------------------------------------------------------------------

    def _colour(self, it: dict, order: int):
        if it.get("style"):
            return STYLE_COLOUR[it["style"]]
        return CURVE_COLOURS[order % len(CURVE_COLOURS)] if it["type"] in ("curve", "area", "rects", "vector",
                                                                           "polygon") else WHITE

    def _label(self, name, key, text, at, colour, out):
        out[f"{name}:label:{key}"] = Text(M.pretty(text), font_size=FONT, color=colour).move_to([at[0], at[1], 0])

    def _axes(self, name, view, region, out):
        lay: M.AxesLayout = self.layout.math[name]
        x0, x1, y0, y1 = lay.box
        lo, hi = (x0, y0), (x1, y1)
        out[f"{name}:xaxis"] = Line([x0, lay.xaxis_y, 0], [x1, lay.xaxis_y, 0], stroke_width=2, color=GREY_B)
        out[f"{name}:yaxis"] = Line([lay.yaxis_x, y0, 0], [lay.yaxis_x, y1, 0], stroke_width=2, color=GREY_B)
        # tick labels along the plot's bottom and left edges; their marks on the axes themselves
        for t, text, c in lay.xticks:
            sx = lay.to_screen((t, 0))[0]
            out[f"{name}:xtick:{text}"] = VGroup(
                Line([sx, lay.xaxis_y - 0.05, 0], [sx, lay.xaxis_y + 0.05, 0], stroke_width=2, color=GREY_B),
                Text(text, font_size=FONT, color=GREY_B).move_to([c[0], c[1], 0]))
        for t, text, c in lay.yticks:
            sy = lay.to_screen((0, t))[1]
            out[f"{name}:ytick:{text}"] = VGroup(
                Line([lay.yaxis_x - 0.05, sy, 0], [lay.yaxis_x + 0.05, sy, 0], stroke_width=2, color=GREY_B),
                Text(text, font_size=FONT, color=GREY_B).move_to([c[0], c[1], 0]))
        if lay.xlabel is not None and view["xlabel"]:
            out[f"{name}:xname"] = Text(M.pretty(view["xlabel"]), font_size=FONT, color=GREY_B).move_to(
                [lay.xlabel[0], lay.xlabel[1], 0])
        if lay.ylabel is not None and view["ylabel"]:
            out[f"{name}:yname"] = Text(M.pretty(view["ylabel"]), font_size=FONT, color=GREY_B).move_to(
                [lay.ylabel[0], lay.ylabel[1], 0])
        for order, (key, it) in enumerate(view["items"].items()):
            colour = self._colour(it, order)
            part = None
            t = it["type"]
            if t in ("curve", "segment"):
                pieces = [piece for line in M.item_polylines(it, lay) for piece in M.clip_polyline(line, lo, hi)]
                if (key, it.get("label")) in lay.inline:  # the label is set into the curve: the curve breaks there
                    c = lay.labels[(key, it["label"])]
                    half = M.text_half(it["label"]) + 0.02
                    pieces = [p for piece in pieces for p in M.cut_out(piece, c - half, c + half)]
                lines = [VMobject(stroke_width=4 if t == "curve" else 3, color=colour).set_points_as_corners(
                    [[x, y, 0] for x, y in piece]) for piece in pieces]
                part = lines[0] if len(lines) == 1 else VGroup(*lines) if lines else None
            elif t == "area":
                pts = [(min(max(x, x0), x1), min(max(y, y0), y1)) for x, y in M.item_polylines(it, lay)[0][:-1]]
                part = Polygon(*[[x, y, 0] for x, y in pts], stroke_width=0, fill_color=colour, fill_opacity=FILL)
            elif t == "polygon":
                pts = [(min(max(x, x0), x1), min(max(y, y0), y1)) for x, y in M.item_polylines(it, lay)[0][:-1]]
                part = Polygon(*[[x, y, 0] for x, y in pts], stroke_width=3, color=colour, fill_color=colour,
                               fill_opacity=FILL if it.get("fill", True) else 0)
            elif t == "vector":
                (ax, ay), (bx, by) = M.item_polylines(it, lay)[0]
                part = Arrow([ax, ay, 0], [bx, by, 0], buff=0, stroke_width=5, color=colour, tip_length=0.16,
                             max_tip_length_to_length_ratio=0.35)
            elif t == "heat":  # behind everything else on the axes
                span = (it["hi"] - it["lo"]) or 1.0
                squares = []
                for cx0, cx1, cy0, cy1, v in it["cells"]:
                    (sx0, sy0), (sx1, sy1) = lay.to_screen((cx0, cy0)), lay.to_screen((cx1, cy1))
                    squares.append(Rectangle(width=abs(sx1 - sx0) + 0.004, height=abs(sy1 - sy0) + 0.004,
                                             stroke_width=0, fill_color=heat_colour((v - it["lo"]) / span),
                                             fill_opacity=0.85).move_to([(sx0 + sx1) / 2, (sy0 + sy1) / 2, 0]))
                part = _bg(VGroup(*squares)).set_z_index(-1)
            elif t == "grid":
                # a coordinate grid (the plane before or after a linear map): a background, thin and faint
                lines = [VMobject(stroke_width=1.5, color=colour).set_points_as_corners([[x, y, 0] for x, y in piece])
                         for line in M.item_polylines(it, lay) for piece in M.clip_polyline(line, lo, hi)]
                part = _bg(VGroup(*lines)) if lines else None
            elif t in ("rects", "bars"):
                rects = []
                for poly in M.item_polylines(it, lay):
                    pts = [(min(max(x, x0), x1), min(max(y, y0), y1)) for x, y in poly]
                    rects.append(Polygon(*[[x, y, 0] for x, y in pts], stroke_width=2, color=colour,
                                         fill_color=colour, fill_opacity=FILL))
                part = VGroup(*rects)
            elif t in ("box", "errors"):  # a box plot's box, median and whiskers; error bars with their points
                lines = [VMobject(stroke_width=3, color=colour).set_points_as_corners([[x, y, 0] for x, y in poly])
                         for poly in M.item_polylines(it, lay)]
                dots = ([Dot([sx, sy, 0], radius=M.POINT_R, color=colour)
                         for sx, sy in (lay.to_screen((it["x"], v)) for v in it["out"])] if t == "box" else
                        [Dot([sx, sy, 0], radius=M.POINT_R, color=colour)
                         for sx, sy in (lay.to_screen((x, y)) for x, _lo, _hi, y in it["bars"])])
                part = VGroup(*lines, *dots)
            elif t == "points":
                dots = [Dot([sx, sy, 0], radius=M.POINT_R, color=colour) for sx, sy in map(lay.to_screen, it["at"])
                        if x0 - 1e-6 <= sx <= x1 + 1e-6 and y0 - 1e-6 <= sy <= y1 + 1e-6]
                part = VGroup(*dots) if dots else None
            elif t == "point":
                sx, sy = lay.to_screen(it["at"])
                if x0 - 1e-6 <= sx <= x1 + 1e-6 and y0 - 1e-6 <= sy <= y1 + 1e-6:
                    part = Dot([sx, sy, 0], radius=M.POINT_R, color=colour)
            elif t == "field":
                hidden = lay.hidden.get(key, set())
                part = VGroup(*[Arrow([a[0], a[1], 0], [b[0], b[1], 0], buff=0, stroke_width=3, color=colour,
                                      tip_length=0.1, max_tip_length_to_length_ratio=0.4)
                                for j, (a, b) in enumerate(M.field_arrows(it, lay)) if j not in hidden])
            if part is not None:
                out[f"{name}:item:{key}"] = part
            if it.get("label") and (key, it["label"]) in lay.labels:
                self._label(name, key, it["label"], lay.labels[(key, it["label"])], colour, out)
            for j, text in enumerate(it.get("values") or []):
                rk = (f"{key}#{j}", text)
                if rk in lay.labels:  # inside its bar it is white, to read on the bar's fill
                    inside = rk in lay.inside_spots and np.allclose(lay.labels[rk], lay.inside_spots[rk])
                    self._label(name, f"{key}#{j}", text, lay.labels[rk], WHITE if inside else colour, out)

    def _venn(self, name, view, region, out):
        lay: M.VennLayout = self.layout.math[name]
        circles = [Circle(radius=r, color=WHITE, stroke_width=4).move_to([c[0], c[1], 0]) for c, r in lay.circles]
        universe = None
        if lay.universe:
            ux0, ux1, uy0, uy1 = lay.universe
            universe = Rectangle(width=ux1 - ux0, height=uy1 - uy0, stroke_width=2, color=GREY_B).move_to(
                [(ux0 + ux1) / 2, (uy0 + uy1) / 2, 0])
            out[f"{name}:universe"] = universe
        style_of: dict[str, str] = {}
        for cells, style in view["shaded"]:
            for m in cells:
                style_of[m] = style
        for m, style in style_of.items():
            region_shape = self._venn_cell(m, circles, universe)
            if region_shape is not None:
                region_shape.set_stroke(width=0).set_fill(STYLE_COLOUR[style], opacity=FILL)
                out[f"{name}:shade:{m}"] = region_shape
        for k, (circle, set_name, at) in enumerate(zip(circles, view["sets"], lay.names)):
            out[f"{name}:set:{set_name}"] = circle
            out[f"{name}:setname:{set_name}"] = Text(set_name, font_size=FONT, color=WHITE).move_to([at[0], at[1], 0])
        for e in view["elements"]:
            if e in lay.elements:
                p = lay.elements[e]
                out[f"{name}:elem:{e}"] = Text(e, font_size=FONT, color=WHITE).move_to([p[0], p[1], 0])

    @staticmethod
    def _venn_cell(member: str, circles, universe):
        """The region inside the circles marked 1 and outside those marked 0 (outside all: inside the box)."""
        inside = [c for c, bit in zip(circles, member) if bit == "1"]
        outside = [c for c, bit in zip(circles, member) if bit == "0"]
        if inside:
            shape = inside[0].copy()
            for c in inside[1:]:
                shape = Intersection(shape, c)
        elif universe is not None:
            shape = universe.copy()
        else:
            return None
        for c in outside:
            shape = Difference(shape, c)
        return shape

    def _geometry(self, name, view, region, out):
        lay: M.GeometryLayout = self.layout.math[name]
        pts = M.geometry_points(view, lay)
        for key, it in view["items"].items():
            colour = STYLE_COLOUR[it.get("style")]
            t = it["type"]
            if t == "segment":
                a, b = pts[it["ends"][0]], pts[it["ends"][1]]
                part = Line([a[0], a[1], 0], [b[0], b[1], 0], stroke_width=4, color=colour)
            elif t == "polygon":
                part = Polygon(*[[pts[k][0], pts[k][1], 0] for k in it["points"]], stroke_width=4, color=colour,
                               fill_color=colour, fill_opacity=FILL if it["fill"] else 0)
            elif t == "circle":
                c = pts[it["center"]]
                part = Circle(radius=it["r"] * lay.scale, stroke_width=4, color=colour).move_to([c[0], c[1], 0])
            elif t == "angle":
                v = pts[it["vertex"]]
                part = Arc(radius=M.ANGLE_R, start_angle=it["start"], angle=it["sweep"], arc_center=[v[0], v[1], 0],
                           stroke_width=4, color=colour)
            elif t == "arc":
                part = VMobject(stroke_width=4, color=colour).set_points_as_corners(
                    [[x, y, 0] for x, y in M.ring_points(it, pts, lay)])
            elif t == "sector":
                part = Polygon(*[[x, y, 0] for x, y in M.ring_points(it, pts, lay)[:-1]], stroke_width=3,
                               color=colour, fill_color=colour, fill_opacity=FILL if it["fill"] else 0)
            else:
                continue
            out[f"{name}:item:{key}"] = part
            if it.get("label") and (key, it["label"]) in lay.labels:
                self._label(name, key, it["label"], lay.labels[(key, it["label"])], colour, out)
        for k, p in view["points"].items():
            if p.get("hidden"):  # made from a coordinate pair: a corner or a centre, not a point to show
                continue
            colour = STYLE_COLOUR[p.get("style")]
            out[f"{name}:point:{k}"] = Dot([pts[k][0], pts[k][1], 0], radius=M.POINT_R, color=colour)
            if p["label"] and (f"pt-{k}", p["label"]) in lay.labels:
                self._label(name, f"pt-{k}", p["label"], lay.labels[(f"pt-{k}", p["label"])], colour, out)

    def _numberline(self, name, view, region, out):
        lay: M.NumberLineLayout = self.layout.math[name]
        y = lay.y
        out[f"{name}:line"] = Line([lay.x0 - 0.2, y, 0], [lay.x1 + 0.2, y, 0], stroke_width=3, color=GREY_B)
        for v, text, c in lay.ticks:
            x = lay.at(v)
            out[f"{name}:tick:{text}"] = VGroup(Line([x, y - 0.07, 0], [x, y + 0.07, 0], stroke_width=2, color=GREY_B),
                                                Text(text, font_size=FONT, color=GREY_B).move_to([c[0], c[1], 0]))
        for key, it in view["items"].items():
            colour = STYLE_COLOUR[it.get("style")]
            t = it["type"]
            if t == "point":
                part = Dot([lay.at(it["x"]), y, 0], radius=M.POINT_R + 0.02, color=colour)
            elif t == "interval":
                a, b = lay.at(it["a"]), lay.at(it["b"])
                ends = [Circle(radius=0.07, stroke_width=3, color=colour, fill_color=colour if closed else BLACK,
                               fill_opacity=1).move_to([x, y, 0]) for x, closed in zip((a, b), it["closed"])]
                part = VGroup(Line([a, y, 0], [b, y, 0], stroke_width=8, color=colour), *ends)
            elif t == "jump":
                part = VMobject(stroke_width=4, color=colour).set_points_as_corners(
                    [[px, py, 0] for px, py in M.jump_points(it, lay)])
            else:
                continue
            out[f"{name}:item:{key}"] = part
            if it.get("label") and (key, it["label"]) in lay.labels:
                self._label(name, key, it["label"], lay.labels[(key, it["label"])], colour, out)

    def _surface(self, name, view, region, out):
        lay: M.SurfaceLayout = self.layout.math[name]
        for k, (a, b) in enumerate(lay.axes):
            out[f"{name}:axis:{k}"] = Line([a[0], a[1], 0], [b[0], b[1], 0], stroke_width=2, color=GREY_B)
        for text, c in lay.names:
            out[f"{name}:axisname:{text}"] = Text(M.pretty(text), font_size=FONT, color=GREY_B).move_to([c[0], c[1], 0])
        for order, (key, it) in enumerate(view["items"].items()):
            colour = self._colour({**it, "type": "curve"}, order)
            if it["type"] == "point":
                sx, sy = lay.to_screen(it["at"])
                out[f"{name}:item:{key}"] = Dot([sx, sy, 0], radius=M.POINT_R, color=STYLE_COLOUR[it.get("style")])
                if it.get("label") and (key, it["label"]) in lay.labels:
                    self._label(name, key, it["label"], lay.labels[(key, it["label"])], STYLE_COLOUR[it.get("style")],
                                out)
                continue
            # faces far to near, opaque: each drawn over the ones behind it (the painter's algorithm), shaded by
            # how it faces the light. They overlap by design, so the audit leaves them out (BACKGROUND_ATTR); the
            # layout keeps every label clear of every face's edge.
            faces = [Polygon(*[[x, y, 0] for x, y in corners], stroke_width=1.5, stroke_color=colour,
                             fill_color=interpolate_color(BLACK, colour, 0.2 + 0.55 * light), fill_opacity=1)
                     for corners, _depth, light in M.surface_faces(it, lay)]
            solid = _bg(VGroup(*faces))
            solid.syllabyte_solid = True
            out[f"{name}:item:{key}"] = solid

    def _space(self, name, view, region, out):
        """The 3D scene from this snapshot's camera: its axes, then faces (far things first, each shaded by how it
        faces the light), then lines, vectors and points over them, then the labels."""
        lay: M.SpaceLayout = self.layout.math[name]
        i = self._snap
        for (a, b), axis in lay.axes[i]:
            out[f"{name}:axis:{axis}"] = _bg(_path_arrow([np.array(a), np.array(b)], GREY_B, 2))
            spot = lay.labels[i].get((f"axis-{axis}", axis))
            if spot is not None:
                out[f"{name}:axisname:{axis}"] = Text(axis, font_size=FONT, color=GREY_B).move_to([spot[0], spot[1], 0])
        order = sorted(view["items"].items(), key=lambda kv: M.item_depth(kv[1], lay, i))
        for rank, (key, it) in enumerate(order):
            colour = self._colour({**it, "type": "curve"}, list(view["items"]).index(key))
            t = it["type"]
            if t in ("mesh", "polygon"):
                plane = t == "polygon"
                faces = [Polygon(*[[x, y, 0] for x, y in corners], stroke_width=2 if plane else 1.2,
                                 stroke_color=colour,
                                 fill_color=colour if plane else interpolate_color(BLACK, colour, 0.2 + 0.55 * light),
                                 fill_opacity=0.35 if plane else 1)
                         for corners, _d, light in M.space_faces(it, lay, i)]
                solid = _bg(VGroup(*faces)).set_z_index(rank)
                solid.syllabyte_solid = True
                out[f"{name}:item:{key}"] = solid
            elif t in ("curve", "segment"):
                lines = [VMobject(stroke_width=4, color=colour).set_points_as_corners([[x, y, 0] for x, y in line])
                         for line in M.space_lines(it, lay, i)]
                out[f"{name}:item:{key}"] = VGroup(*lines).set_z_index(100)
            elif t == "vector":
                (ax, ay), (bx, by) = M.space_lines(it, lay, i)[0]
                out[f"{name}:item:{key}"] = Arrow([ax, ay, 0], [bx, by, 0], buff=0, stroke_width=5, color=colour,
                                                  tip_length=0.16, max_tip_length_to_length_ratio=0.35).set_z_index(100)
            elif t == "point":
                sx, sy = lay.to_screen(it["at"], i)
                out[f"{name}:item:{key}"] = Dot([sx, sy, 0], radius=M.POINT_R,
                                                color=STYLE_COLOUR[it.get("style")]).set_z_index(100)
            if it.get("label") and (key, it["label"]) in lay.labels[i]:
                c = lay.labels[i][(key, it["label"])]
                self._label(name, key, it["label"], c, STYLE_COLOUR[it["style"]] if it.get("style") else colour, out)
                out[f"{name}:label:{key}"].set_z_index(101)

    # ---- diagrams --------------------------------------------------------------------------------------

    def _grid(self, name, view, region, out):
        lay: D.GridLayout = self.layout.math[name]
        if lay.transposed:
            view = D.transpose(view)
        font = max(FONT, lay.font)
        heat = view.get("heat") or {}
        snap = self._snap
        if lay.window:  # a tall table: a window of rows, arrows where more is above or below
            n = len(view["values"])
            for side, more, y in (("up", lay.start[snap] > 0, lay.top + D.GRID_MORE / 2 - 0.02),
                                  ("down", lay.start[snap] + lay.window < n, lay.bottom - D.GRID_MORE / 2 + 0.02)):
                if more:
                    tri = Triangle(color=GREY_B, fill_color=GREY_B, fill_opacity=1).scale(0.07)
                    out[f"{name}:more:{side}"] = (tri.rotate(np.pi) if side == "down" else tri).move_to(
                        [(lay.left + lay.right) / 2, y, 0])
        for r, row in enumerate(view["values"]):
            if not lay.shown(r, snap):
                continue
            for c, text in enumerate(row):
                style = view["marks"].get(f"{r},{c}")
                colour = STYLE_COLOUR[style]
                x, y, w, h = lay.x[c], lay.row_y(r, snap), lay.w[c], lay.h
                fill = heat_colour(heat[f"{r},{c}"]) if f"{r},{c}" in heat else BLACK
                if not view["matrix"] or f"{r},{c}" in heat:
                    out[f"{name}:cell:{r},{c}"] = Rectangle(width=w, height=h, stroke_color=GREY_B, stroke_width=2,
                                                            fill_color=fill, fill_opacity=1).move_to([x, y, 0])
                # on a heat colour the number is black or white, whichever reads (a mark's style shows in its
                # outline)
                ink = readable_on(fill) if f"{r},{c}" in heat else colour
                if text:
                    out[f"{name}:val:{r},{c}"] = Text(text, font_size=font, color=ink).move_to([x, y, 0])
                if style:  # inside the cell, so it never covers a neighbour's border
                    out[f"{name}:mark:{r},{c}"] = Rectangle(width=w - 0.08, height=h - 0.08, stroke_color=colour,
                                                            stroke_width=4, fill_opacity=0).move_to([x, y, 0])
        if view["matrix"]:  # square brackets either side
            lip = 0.1
            for side, x in (("l", lay.left - 0.06), ("r", lay.right + 0.06)):
                t = 1 if side == "l" else -1
                out[f"{name}:bracket:{side}"] = VMobject(stroke_width=3, color=WHITE).set_points_as_corners(
                    [[x + t * lip, lay.top, 0], [x, lay.top, 0], [x, lay.bottom, 0], [x + t * lip, lay.bottom, 0]])
        for r, text in enumerate(view["row_names"] or []):
            if text and lay.shown(r, snap):
                out[f"{name}:rowname:{r}"] = Text(text, font_size=font, color=GREY_B).move_to(
                    [lay.name_x, lay.row_y(r, snap), 0])
        for c, text in enumerate(view["col_names"] or []):
            if text:
                out[f"{name}:colname:{c}"] = Text(text, font_size=font, color=GREY_B).move_to([lay.x[c], lay.head_y, 0])

    @staticmethod
    def _lines(text: str, font: int, colour) -> VGroup:
        lines = [Text(line, font_size=font, color=colour) for line in text.split("\n") if line] or [
            Text(" ", font_size=font, color=colour)]
        return VGroup(*lines).arrange(np.array([0, -1, 0]), buff=0.06)

    def _flow(self, name, view, region, out):
        lay: D.FlowLayout = self.layout.math[name]
        k = lay.k
        font = max(FONT, round(FONT * k))
        for key, b in view["boxes"].items():
            c, w, h = lay.boxes[key]
            style = b["style"]
            colour = STYLE_COLOUR[style]
            shape = _flow_shape(b["shape"], c, w, h, colour, 5 if style else 3, k)
            if b["shape"] == "record":  # its name, a rule, its fields left-aligned
                rfont = max(D.RECORD_FONT, round(D.RECORD_FONT * k))
                top = c[1] + h / 2 - D.BOX_PAD_Y * k
                title_t = Text(b["text"], font_size=rfont, color=colour).move_to(
                    [c[0], top - D.LINE_H * k / 2, 0])
                group = VGroup(shape, title_t)
                fields = b.get("fields") or []
                if fields:
                    rule_y = top - D.LINE_H * k - D.RECORD_RULE * k / 2
                    group.add(Line([c[0] - w / 2, rule_y, 0], [c[0] + w / 2, rule_y, 0], stroke_width=2, color=colour))
                    for j, f in enumerate(fields):
                        t = Text(f, font_size=rfont, color=WHITE)
                        t.move_to([c[0] - w / 2 + D.RECORD_PAD * k + t.width / 2,
                                   rule_y - D.RECORD_RULE * k / 2 - D.LINE_H * k * (j + 0.5), 0])
                        group.add(t)
                out[f"{name}:box:{key}"] = group
                continue
            text = self._lines(b["text"], font, colour)
            if b["shape"] in D.ICON_SHAPES:
                icon_x = c[0] - w / 2 + D.BOX_PAD_X * k + D.ICON_H * k / 2
                shape.add(_icon(b["shape"], icon_x, c[1], D.ICON_H * k, colour))
                text_x = (icon_x + D.ICON_H * k / 2 + 0.06 * k + c[0] + w / 2) / 2
                text.move_to([text_x, c[1], 0])
            else:
                text.move_to([c[0], c[1] - (0.08 * k if b["shape"] == "cylinder" else 0.03 * k if b["shape"] ==
                                            "document" else 0.0), 0])
            out[f"{name}:box:{key}"] = VGroup(shape, text)
        for a, b, style, label, *rest in view["arrows"]:
            kind = rest[0] if rest else "arrow"
            colour = STYLE_COLOUR[style] if style else GREY_B
            width = 5 if style else 3
            if a == b:
                if f"{a}>{a}" not in lay.loops:
                    continue
                centre, d = lay.loops[f"{a}>{a}"]
                back = float(np.arctan2(-d[1], -d[0]))  # toward the box: the gap the loop leaves there
                arc = Arc(radius=D.LOOP_R, start_angle=back + 0.95, angle=2 * np.pi - 1.9,
                          arc_center=[centre[0], centre[1], 0], stroke_width=width, color=colour)
                arc.add_tip(tip_length=0.12, tip_width=0.12)
                out[f"{name}:arrow:{a}>{b}"] = arc
            else:
                path = lay.arrows.get(f"{a}>{b}")
                if path is None:
                    continue
                out[f"{name}:arrow:{a}>{b}"] = _path_arrow(path, colour, width, dashed=kind == "dashed",
                                                           tip="none" if kind == "line" else
                                                           "hollow" if kind == "inherit" else "solid")
            spot = lay.labels.get((f"{a}>{b}", label)) if label else None
            if spot is not None:
                out[f"{name}:arrowlabel:{a}>{b}"] = Text(label, font_size=FONT, color=colour if style else GREY_B
                                                         ).move_to([spot[0], spot[1], 0])

    def _timeline(self, name, view, region, out):
        lay: D.TimelineLayout = self.layout.math[name]
        for i, lane in enumerate(view["lanes"]):
            t = Text(lane, font_size=FONT, color=GREY_B)
            out[f"{name}:lane:{i}"] = t.move_to([lay.name_x - t.width / 2, lay.lane_y[i], 0])
        out[f"{name}:axis"] = Line([lay.x0, lay.axis_y, 0], [lay.x1, lay.axis_y, 0], stroke_width=2, color=GREY_B)
        for v, text, c in lay.ticks:
            x = lay.at(v)
            out[f"{name}:tick:{text}"] = VGroup(
                Line([x, lay.axis_y - 0.05, 0], [x, lay.axis_y + 0.05, 0], stroke_width=2, color=GREY_B),
                Text(text, font_size=FONT, color=GREY_B).move_to([c[0], c[1], 0]))
        bh = lay.lane_h * 0.76
        for key, it in view["items"].items():
            colour = STYLE_COLOUR[it.get("style")] if it.get("style") else BLUE_C
            if it["type"] == "signal":  # a square wave: high at the lane's top, low at its bottom
                y = lay.lane_y[it["lane"]]
                pts, prev = [], None
                for k, v in enumerate(it["values"]):
                    level = y + (bh / 2 if v else -bh / 2)
                    x0, x1 = lay.at(it["t0"] + k * it["step"]), lay.at(it["t0"] + (k + 1) * it["step"])
                    if prev is not None and prev != level:
                        pts.append([x0, level, 0])
                    elif prev is None:
                        pts.append([x0, level, 0])
                    pts.append([x1, level, 0])
                    prev = level
                out[f"{name}:item:{key}"] = VMobject(stroke_width=4, color=colour if it.get("style") else TEAL
                                                     ).set_points_as_corners(pts)
                continue
            if it["type"] == "block":
                a, b = lay.at(it["a"]), lay.at(it["b"])
                y = lay.lane_y[it["lane"]]
                out[f"{name}:item:{key}"] = Rectangle(width=b - a, height=bh, stroke_color=colour, stroke_width=3,
                                                      fill_color=colour, fill_opacity=FILL).move_to([(a + b) / 2, y, 0])
                if it.get("label") and (key, it["label"]) in lay.shown_labels:
                    out[f"{name}:label:{key}"] = Text(it["label"], font_size=FONT, color=WHITE).move_to(
                        [(a + b) / 2, y, 0])
            else:
                x = lay.at(it["t"])
                out[f"{name}:item:{key}"] = DashedLine([x, lay.top + 0.04, 0], [x, lay.axis_y, 0], stroke_width=3,
                                                       color=colour, dash_length=0.08)
                spot = lay.mark_spots.get((key, it.get("label")))
                if spot is not None:
                    out[f"{name}:label:{key}"] = Text(it["label"], font_size=FONT, color=colour).move_to(
                        [spot[0], spot[1], 0])

    def _sequence(self, name, view, region, out):
        lay: D.SequenceLayout = self.layout.math[name]
        snap = self._snap
        gaps = D.sequence_gaps(view, lay, snap)
        for i, actor in enumerate(view["actors"]):
            x = lay.x[i]
            box = Rectangle(width=lay.box_w, height=D.ACTOR_H, stroke_color=WHITE, stroke_width=3, fill_color=BLACK,
                            fill_opacity=1).move_to([x, lay.top - D.ACTOR_H / 2, 0])
            out[f"{name}:actor:{i}"] = VGroup(box, Text(actor, font_size=FONT, color=WHITE).move_to(box))
            # broken round any label it would cross (a long label spans the lifelines between its ends)
            y, pieces = lay.top - D.ACTOR_H, []
            for g0, g1 in sorted(gaps.get(i, []), key=lambda g: -g[1]):
                if g1 < y - 0.05:
                    pieces.append(DashedLine([x, y, 0], [x, g1, 0], stroke_width=2, color=GREY_B, dash_length=0.1))
                y = min(y, g0)
            if y - lay.bottom > 0.05:
                pieces.append(DashedLine([x, y, 0], [x, lay.bottom, 0], stroke_width=2, color=GREY_B, dash_length=0.1))
            out[f"{name}:life:{i}"] = VGroup(*pieces)
        if lay.start[snap] > 0:  # older messages scrolled up out of view
            tri = Triangle(color=GREY_B, fill_color=GREY_B, fill_opacity=1).scale(0.07)
            out[f"{name}:more"] = tri.move_to([lay.x[0] - lay.box_w / 2 + 0.08, lay.first_row - 0.06, 0])
        for key, m in view["messages"].items():
            if not lay.shown(m["row"], snap):
                continue
            colour = STYLE_COLOUR[m.get("style")] if m.get("style") else WHITE
            y = lay.row_y(m["row"], snap)
            a, b = lay.x[m["a"]], lay.x[m["b"]]
            if m["a"] == m["b"]:
                path = [(a, y + 0.12), (a + lay.self_w, y + 0.12), (a + lay.self_w, y - 0.12), (a, y - 0.12)]
            else:
                path = [(a, y), (b, y)]
            out[f"{name}:item:{key}"] = _path_arrow([np.array(p) for p in path], colour, 3, dashed=m["dashed"])
            if key in lay.labels:
                cx, dy = lay.labels[key]
                out[f"{name}:label:{key}"] = Text(m["label"], font_size=FONT, color=colour).move_to([cx, y + dy, 0])

    def _circuit(self, name, view, region, out):
        lay: D.CircuitLayout = self.layout.math[name]
        values = view["values"]
        on, off = YELLOW, GREY_B
        for key, path in lay.wires.items():
            src = key.split(">")[0]
            out[f"{name}:wire:{key}"] = VMobject(stroke_width=4 if values[src] else 3,
                                                 color=on if values[src] else off).set_points_as_corners(
                [[x, y, 0] for x, y in path])
        for key, p in view["parts"].items():
            c, (w, h) = lay.pos[key], lay.size[key]
            style = p.get("style")
            if p["type"] in ("gate", "block"):
                colour = STYLE_COLOUR[style] if style else WHITE
                if p["type"] == "gate":
                    body = _gate(p["gate"], c, w, h, colour, 5 if style else 3)
                else:  # a block: a box with its kind inside (a DFF shows the bit it holds)
                    text = p["block"] + (f" {p['state']}" if p["block"] == "DFF" else "")
                    body = VGroup(Rectangle(width=w, height=h, stroke_color=colour, stroke_width=5 if style else 3,
                                            fill_color=BLACK, fill_opacity=1).move_to([c[0], c[1], 0]),
                                  Text(text, font_size=28, color=colour).move_to([c[0], c[1], 0]))
                n = len(p["inputs"])
                pins = [Line([px, c[1] + h / 2, 0], [px, py, 0], stroke_width=3, color=colour)
                        for px, py in (D._port(lay.pos, lay.size, view["parts"], key, j) for j in range(n))]
                for o in range(len(D._outs(p))):
                    ox, oy = D._port(lay.pos, lay.size, view["parts"], key, None, o)
                    pins.append(Line([ox, c[1] - h / 2, 0], [ox, oy, 0], stroke_width=3, color=colour))
                out[f"{name}:part:{key}"] = VGroup(*pins, body)
            else:
                v = values[key]
                colour = STYLE_COLOUR[style] if style else (on if v else off)
                box = Square(side_length=D.TERM, stroke_color=colour, stroke_width=4, fill_color=BLACK, fill_opacity=1)
                box.move_to([c[0], c[1], 0])
                out[f"{name}:part:{key}"] = VGroup(box, Text(str(v), font_size=FONT, color=colour).move_to(box))
                nc = lay.names[key]
                out[f"{name}:name:{key}"] = Text(p["label"], font_size=FONT, color=WHITE).move_to([nc[0], nc[1], 0])

    def _memory(self, name, view, region, out):
        lay: D.MemoryLayout = self.layout.math[name]
        for key, b in view["boxes"].items():
            left, top, w, h = lay.boxes[key]
            colour = STYLE_COLOUR[b["style"]] if b["style"] else WHITE
            frame = Rectangle(width=w, height=h, stroke_color=colour, stroke_width=5 if b["style"] else 3,
                              fill_color=BLACK, fill_opacity=1).move_to([left + w / 2, top - h / 2, 0])
            rule = Line([left, top - D.BOX_TITLE_H, 0], [left + w, top - D.BOX_TITLE_H, 0], stroke_width=2,
                        color=GREY_B)
            split = Line([left + lay.name_w[key], top - D.BOX_TITLE_H, 0], [left + lay.name_w[key], top - h, 0],
                         stroke_width=2, color=GREY_B)
            title = Text(b["title"], font_size=FONT, color=GREY_B if b["area"] == "heap" else colour).move_to(
                [left + w / 2, top - D.BOX_TITLE_H / 2, 0])
            out[f"{name}:box:{key}"] = VGroup(frame, rule, split, title)
            fields = {f[0]: f for f in b["fields"]}
            for fname, y in D.memory_rows(view, lay, key):
                _n, text, ref, fstyle = fields[fname]
                fc = STYLE_COLOUR[fstyle] if fstyle else WHITE
                parts = [Text(fname, font_size=FONT, color=GREY_B).move_to([left + lay.name_w[key] / 2, y, 0])]
                vx = left + lay.name_w[key] + (w - lay.name_w[key]) / 2
                if ref:
                    parts.append(Dot([vx, y, 0], radius=D.REF_DOT, color=BLUE_C))
                elif text:
                    parts.append(Text(text, font_size=FONT, color=fc).move_to([vx, y, 0]))
                out[f"{name}:field:{key}.{fname}"] = VGroup(*parts)
        for key, path in D.memory_arrows(view, lay).items():
            out[f"{name}:item:ref:{key}"] = _path_arrow([np.array(p) for p in path], BLUE_C, 3)

    # ---- showing ---------------------------------------------------------------------------------------

    def changes(self, i: int) -> list:
        """The animations from what is on screen to snapshot i (each part by its key: a part in both becomes its
        new self in place, a new one fades in, a gone one fades out)."""
        target = self.parts(i)
        anims = []
        for key, new in target.items():
            old = self.on_screen.get(key)
            if old is None:
                anims.append(FadeIn(new))
                self._keep(new)
                self.on_screen[key] = new
            elif _same_parts(old, new):
                anims.append(old.animate.become(new))
            elif ":formula:" in key:  # a step rewritten: the symbols it keeps move to their new places
                from manim import TransformMatchingShapes

                anims.append(TransformMatchingShapes(old, new))
                self._drop(old)
                self._keep(new)
                self.on_screen[key] = new
            elif ":item:" in key and not getattr(new, "syllabyte_solid", False):
                # a math thing that changed shape (more rectangles, a new curve) morphs; a 3D solid (opaque faces in
                # depth order) cross-fades instead, since its faces mid-morph would cut through each other
                anims.append(ReplacementTransform(old, new))
                self._drop(old)
                self._keep(new)
                self.on_screen[key] = new
            else:
                anims += [FadeOut(old), FadeIn(new)]
                self._drop(old)
                self._keep(new)
                self.on_screen[key] = new
        for key in [k for k in self.on_screen if k not in target]:
            old = self.on_screen.pop(key)
            self._drop(old)
            anims.append(FadeOut(old))
        self.shown = i
        return anims

    def _keep(self, m: VMobject) -> None:
        if self.group is not None:
            self.group.add(m)

    def _drop(self, m: VMobject) -> None:
        if self.group is not None:
            self.group.remove(m)

    def show(self, i: int, seconds: float) -> None:
        if anims := self.changes(i):
            self.scene.play(*anims, run_time=max(seconds, 0.1))


# ---- shapes the diagrams draw ----------------------------------------------------------------------------


def _path_arrow(path, colour, width, dashed: bool = False, tip: str = "solid") -> VGroup:
    """A polyline ending in an arrowhead (solid; hollow for UML's "is a"; none for a plain line), dashed for a
    reply or a dependency."""
    pts = [np.array([p[0], p[1], 0.0]) for p in path]
    end, before = pts[-1], pts[-2]
    d = (end - before) / (float(np.linalg.norm(end - before)) or 1e-9)
    tip_l = 0.0 if tip == "none" else min(0.22 if tip == "hollow" else 0.16, float(np.linalg.norm(end - before)) * 0.5)
    base = end - d * tip_l
    normal = np.array([-d[1], d[0], 0.0])
    head = [] if tip == "none" else [Polygon(end, base + normal * tip_l * 0.5, base - normal * tip_l * 0.5,
                                            stroke_width=2 if tip == "hollow" else 0, stroke_color=colour,
                                            fill_color=BLACK if tip == "hollow" else colour, fill_opacity=1)]
    body = pts[:-1] + [base]
    if dashed:
        lines = [DashedLine(p, q, stroke_width=width, color=colour, dash_length=0.08) for p, q in zip(body, body[1:])
                 if np.linalg.norm(q - p) > 1e-6]
    else:
        lines = [VMobject(stroke_width=width, color=colour).set_points_as_corners(body)]
    return VGroup(*lines, *head)


def _curve(points, colour, width, fill: bool = True) -> VMobject:
    m = VMobject(stroke_width=width, color=colour).set_points_as_corners([[x, y, 0] for x, y in points])
    if fill:
        m.set_fill(BLACK, opacity=1)
    return m


def _flow_shape(shape: str, c, w: float, h: float, colour, width: float, k: float) -> VGroup:
    x, y = float(c[0]), float(c[1])
    if shape in ("box",):
        body = Rectangle(width=w, height=h)
    elif shape in ("round",) + D.ICON_SHAPES:
        body = RoundedRectangle(width=w, height=h, corner_radius=min(0.16, h / 3))
    elif shape == "diamond":
        body = Polygon([x, y + h / 2, 0], [x + w / 2, y, 0], [x, y - h / 2, 0], [x - w / 2, y, 0])
        return VGroup(body.set_stroke(colour, width).set_fill(BLACK, 1))
    elif shape in ("circle", "double"):
        group = VGroup(Circle(radius=w / 2).set_stroke(colour, width).set_fill(BLACK, 1).move_to([x, y, 0]))
        if shape == "double":
            group.add(Circle(radius=w / 2 - 0.08 * k).set_stroke(colour, width).move_to([x, y, 0]))
        return group
    elif shape == "cylinder":
        ry = 0.08 * k
        top, bottom, x0, x1 = y + h / 2, y - h / 2, x - w / 2, x + w / 2
        t = np.linspace(0, np.pi, 24)
        outline = ([(x0, top - ry), (x0, bottom + ry)] + [(x - np.cos(a) * w / 2, bottom + ry - np.sin(a) * ry)
                                                            for a in t] + [(x1, top - ry)]
                   + [(x + np.cos(a) * w / 2, top - ry + np.sin(a) * ry) for a in t])
        rim = [(x - np.cos(a) * w / 2, top - ry - np.sin(a) * ry) for a in t]
        return VGroup(_curve(outline + outline[:1], colour, width), _curve(rim, colour, width, fill=False))
    elif shape == "document":
        x0, x1, top, bottom = x - w / 2, x + w / 2, y + h / 2, y - h / 2
        wave = [(x1 - (x1 - x0) * i / 24, bottom + 0.05 * k * np.sin(2 * np.pi * i / 24)) for i in range(25)]
        return VGroup(_curve([(x0, top), (x1, top)] + wave + [(x0, top)], colour, width))
    elif shape == "cloud":
        t = np.linspace(0, 2 * np.pi, 97)
        r = 0.9 + 0.1 * np.abs(np.cos(4 * t))
        return VGroup(_curve(list(zip(x + w / 2 * r * np.cos(t), y + h / 2 * r * np.sin(t))), colour, width))
    else:
        body = Rectangle(width=w, height=h)
    return VGroup(body.set_stroke(colour, width).set_fill(BLACK, 1).move_to([x, y, 0]))


def _icon(shape: str, x: float, y: float, size: float, colour) -> VGroup:
    """A pictogram `size` tall centred at (x, y), in outline: what the box stands for."""
    s = size / 2
    if shape == "person":
        return VGroup(Circle(radius=s * 0.36).set_stroke(colour, 3).move_to([x, y + s * 0.5, 0]),
                      Arc(radius=s * 0.62, start_angle=0, angle=np.pi, arc_center=[x, y - s * 0.75, 0],
                          stroke_width=3, color=colour))
    if shape == "chip":
        body = Square(side_length=s * 1.1).set_stroke(colour, 3).move_to([x, y, 0])
        pins = VGroup()
        for t in (-0.3, 0.0, 0.3):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p = np.array([x + dx * s * 0.55 + dy * t * s * 1.6, y + dy * s * 0.55 + dx * t * s * 1.6, 0])
                pins.add(Line(p, p + np.array([dx, dy, 0]) * s * 0.3, stroke_width=2, color=colour))
        return VGroup(body, pins)
    if shape == "monitor":
        screen = Rectangle(width=s * 1.7, height=s * 1.2).set_stroke(colour, 3).move_to([x, y + s * 0.25, 0])
        return VGroup(screen, Line([x, y - s * 0.35, 0], [x, y - s * 0.75, 0], stroke_width=3, color=colour),
                      Line([x - s * 0.45, y - s * 0.8, 0], [x + s * 0.45, y - s * 0.8, 0], stroke_width=3, color=colour))
    if shape == "lock":
        body = Rectangle(width=s * 1.3, height=s * 1.0).set_stroke(colour, 3).move_to([x, y - s * 0.4, 0])
        return VGroup(body, Arc(radius=s * 0.42, start_angle=0, angle=np.pi, arc_center=[x, y + s * 0.1, 0],
                                stroke_width=3, color=colour))
    if shape == "server":
        out = VGroup()
        for j in range(3):
            cy = y + s * (0.62 - 0.62 * j)
            out.add(Rectangle(width=s * 1.6, height=s * 0.5).set_stroke(colour, 3).move_to([x, cy, 0]))
            out.add(Dot([x + s * 0.55, cy, 0], radius=0.025, color=colour))
        return out
    return VGroup()


def _gate(kind: str, c, w: float, h: float, colour, width: float) -> VGroup:
    """A logic gate pointing down (inputs along the top, the output at the bottom): AND's flat back and round
    front, OR's curved shield, XOR's extra back curve, a buffer's triangle, and a bubble for each inverted one."""
    x, y = float(c[0]), float(c[1])
    bubble = 0.05 if kind in ("NOT", "NAND", "NOR", "XNOR") else 0.0
    top, bottom = y + h / 2, y - h / 2 + 2 * bubble
    t = np.linspace(0, np.pi, 25)
    base = {"AND": "AND", "NAND": "AND", "OR": "OR", "NOR": "OR", "XOR": "OR", "XNOR": "OR"}.get(kind, "BUF")
    if base == "AND":
        mid = (top + bottom) / 2
        pts = ([(x - w / 2, top), (x + w / 2, top), (x + w / 2, mid)]
               + [(x + np.cos(a) * w / 2, mid - np.sin(a) * (mid - bottom)) for a in t] + [(x - w / 2, top)])
    elif base == "OR":  # a concave back, sides curving in to a point
        dip = 0.08
        right = [(x + w / 2 * (1 - (u ** 1.6)), top - (top - bottom) * u) for u in np.linspace(0, 1, 13)]
        left = [(x - w / 2 * (1 - (u ** 1.6)), top - (top - bottom) * u) for u in np.linspace(1, 0, 13)]
        back = [(x - w / 2 + w * u, top - dip * np.sin(np.pi * u)) for u in np.linspace(0, 1, 13)]
        pts = back + right[1:] + left[1:]
    else:  # BUF / NOT: a triangle
        pts = [(x - w / 2, top), (x + w / 2, top), (x, bottom), (x - w / 2, top)]
    group = VGroup(_curve(pts, colour, width))
    if kind in ("XOR", "XNOR"):
        group.add(_curve([(x - w / 2 + w * u, top + 0.07 - 0.08 * np.sin(np.pi * u)) for u in np.linspace(0, 1, 13)],
                         colour, width, fill=False))
    if bubble:
        group.add(Circle(radius=bubble).set_stroke(colour, width).set_fill(BLACK, 1).move_to([x, y - h / 2 + bubble, 0]))
    return group
