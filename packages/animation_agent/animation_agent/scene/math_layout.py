"""
Where a math view's parts go (plan/scene-grammar-plan.md, P2): axes, Venn diagrams and geometric figures. Pure
Python (numpy), no Manim.

The program records shapes in its own coordinates (scene/api.py); this module fits them to the view's band, one
layout for the whole program, so axes keep their scale while curves are drawn on them and a Venn diagram keeps its
circles while regions are shaded. The rules are the ones graphs follow (scene/layout.py): the picture is as large
as its band allows, and every label sits clear of every line, edge and other label, inside the band, or the picture
is refused with the reason.

  - Axes: tick labels sit outside the plot area (left and below), never among the curves; the axes cross at 0 when
    0 is in range. A label for a curve, a line, a point or an area is placed beside it, clear of everything else.
  - Venn: 1-3 circles, sized to the band; each set's name outside its circle; elements written inside their own
    region, clear of every circle's edge.
  - Geometry: one scale for x and y; point labels go around their point, clear of the figure's lines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from animation_agent.scene.api import PictureError

CHAR_W = 0.18  # a character of a label at the minimum font
TEXT_H = 0.28
ROOM = 0.05  # free space around a label
TICK_GAP = 0.08
POINT_R = 0.07
MIN_PLOT = 1.2  # the least plot height or width worth drawing
LABEL_FONT = 30


def pretty(label: str) -> str:
    """A label as shown: x^2 as x², e^-x as e⁻x, * as ·, sqrt as √. Only a whole power standing on its own is
    raised (65^1/3 and x^(1/3) stay as written: there is no superscript slash)."""
    sup = str.maketrans("0123456789-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻ⁿ")
    out, i = "", 0
    while i < len(label):
        if label[i] == "^" and i + 1 < len(label):
            j = i + 1
            while j < len(label) and (label[j].isdigit() or (j == i + 1 and label[j] in "-n")):
                j += 1
            if j > i + 1 and (j == len(label) or label[j] not in "/.("):
                out += label[i + 1:j].translate(sup)
                i = j
                continue
        out += label[i]
        i += 1
    return out.replace("*", "·").replace("sqrt ", "√").replace("sqrt", "√")


_NARROW = set("iljI.,:;'|!()[] ")


def text_width(text: str, font: int = LABEL_FONT) -> float:
    """A text's width at a font size, from measured character widths at 30 (capitals 0.26, digits 0.2, lowercase
    0.17, i and l 0.1, M and W 0.37), with 4% to spare: a flat 0.18 a character ran 'SYN-ACK 300' 0.6 short."""
    w = 0.0
    for ch in text:
        if ch in "MWmw@%":
            w += 0.34 if ch.islower() else 0.38
        elif ch in _NARROW:
            w += 0.1
        elif ch.isupper():
            w += 0.265
        elif ch.isdigit():
            w += 0.2
        elif ch.isalpha():
            w += 0.17
        else:
            w += 0.19
    return w * 1.04 * font / LABEL_FONT


def text_half(text: str, font: int = LABEL_FONT, exact: bool = False) -> np.ndarray:
    """Half a label's box, with ROOM round it: by a flat CHAR_W a character (the math views were tuned on it), or
    with exact=True by measured widths (the diagrams, whose labels are words with capitals)."""
    k = font / LABEL_FONT
    shown = pretty(text)
    w = text_width(shown, font) if exact else CHAR_W * k * len(shown)
    return np.array([w / 2, TEXT_H * k / 2]) + ROOM


# ---- geometry helpers ----------------------------------------------------------------------------------


def seg_hits_box(p, q, lo, hi) -> bool:
    t0, t1 = 0.0, 1.0
    d = (q[0] - p[0], q[1] - p[1])
    for k in range(2):
        if abs(d[k]) < 1e-12:
            if p[k] < lo[k] or p[k] > hi[k]:
                return False
            continue
        a, b = (lo[k] - p[k]) / d[k], (hi[k] - p[k]) / d[k]
        a, b = min(a, b), max(a, b)
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return False
    return True


def clip(p, q, lo, hi):
    """The part of segment p-q inside the box, or None (Liang-Barsky)."""
    t0, t1 = 0.0, 1.0
    d = (q[0] - p[0], q[1] - p[1])
    for k in range(2):
        if abs(d[k]) < 1e-12:
            if p[k] < lo[k] - 1e-9 or p[k] > hi[k] + 1e-9:
                return None
            continue
        a, b = (lo[k] - p[k]) / d[k], (hi[k] - p[k]) / d[k]
        a, b = min(a, b), max(a, b)
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return None
    return ((p[0] + d[0] * t0, p[1] + d[1] * t0), (p[0] + d[0] * t1, p[1] + d[1] * t1))


def cut_out(points, lo, hi) -> list[list[tuple[float, float]]]:
    """A polyline with the part inside the box taken out (a label set into the line)."""
    pieces, cur = [], []
    for p, q in zip(points, points[1:]):
        if seg_hits_box(p, q, lo, hi):
            inside_p = lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1]
            if not inside_p:
                cur.append(p)
            if len(cur) > 1:
                pieces.append(cur)
            cur = []
            continue
        if not cur:
            cur = [p]
        cur.append(q)
    if len(cur) > 1:
        pieces.append(cur)
    return pieces


def clip_polyline(points, lo, hi) -> list[list[tuple[float, float]]]:
    """A polyline cut to the box: the pieces inside it."""
    pieces, cur = [], []
    for p, q in zip(points, points[1:]):
        c = clip(p, q, lo, hi)
        if c is None:
            if len(cur) > 1:
                pieces.append(cur)
            cur = []
            continue
        a, b = c
        if cur and math.dist(cur[-1], a) < 1e-9:
            cur.append(b)
        else:
            if len(cur) > 1:
                pieces.append(cur)
            cur = [a, b]
    if len(cur) > 1:
        pieces.append(cur)
    return pieces


@dataclass
class Obstacles:
    """What a label must keep clear of: line segments, boxes (other labels, tick labels) and discs (points)."""

    segments: list[tuple] = field(default_factory=list)
    boxes: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    discs: list[tuple[tuple[float, float], float]] = field(default_factory=list)

    def add_polyline(self, pts) -> None:
        self.segments += list(zip(pts, pts[1:]))

    def clear(self, c: np.ndarray, half: np.ndarray, own: set[int] = frozenset()) -> bool:
        lo, hi = c - half, c + half
        if any(np.all(np.abs(c - c2) < half + h2 + 0.03) for c2, h2 in self.boxes):
            return False
        if any(np.hypot(*(np.clip(d, lo, hi) - d)) < r for d, r in self.discs):
            return False
        return not any(seg_hits_box(p, q, lo, hi) for k, (p, q) in enumerate(self.segments) if k not in own)


@dataclass
class Request:
    """A label to place: its key (thing key, label text), text, candidate centres (best first), what it must keep
    clear of, and the snapshots it is shown in (it may share a place with a label never on screen with it)."""

    key: tuple[str, str]
    text: str
    candidates: list[np.ndarray]
    obstacles: Obstacles
    shown: set[int]
    own: Obstacles = field(default_factory=Obstacles)  # its own line, which a label beside it keeps clear of
    inline: list[np.ndarray] = field(default_factory=list)  # places on its own line (the line breaks round it)


def place(requests: list[Request], bounds: tuple, what: str, inline: set | None = None,
          dropped: list | None = None, exact: bool = False) -> dict[tuple[str, str], np.ndarray]:
    """Each request gets the first candidate inside bounds (x0, x1, y0, y1), clear of its obstacles, its own line
    and the labels already placed that share a snapshot with it; failing that, a place on its own line (whose
    key then goes in `inline`: the line is drawn broken round it). The ones with fewest clear places go first.
    A label with no clear place is left out (its text goes in `dropped`), never drawn over something: in
    runs/picture-p2 one such label refused the whole picture, and the planner then dropped the video's formulas
    or drew a weaker picture to get round it."""
    x0, x1, y0, y1 = bounds

    def ok(c, half, r, on_line=False) -> bool:
        return (c[0] - half[0] >= x0 and c[0] + half[0] <= x1 and c[1] - half[1] >= y0 and c[1] + half[1] <= y1
                and r.obstacles.clear(c, half) and (on_line or r.own.clear(c, half)))

    halves = {r.key: text_half(r.text, exact=exact) for r in requests}
    counts = {r.key: sum(ok(c, halves[r.key], r) for c in r.candidates) + sum(
        ok(c, halves[r.key], r, True) for c in r.inline) for r in requests}
    out: dict[tuple[str, str], np.ndarray] = {}
    placed: list[tuple[np.ndarray, np.ndarray, set[int]]] = []
    for r in sorted(requests, key=lambda r: counts[r.key]):
        half = halves[r.key]

        def free(c) -> bool:
            return not any(r.shown & shown and np.all(np.abs(c - c2) < half + h2 + 0.06) for c2, h2, shown in placed)

        spot = next((c for c in r.candidates if ok(c, half, r) and free(c)), None)
        if spot is None:
            spot = next((c for c in r.inline if ok(c, half, r, True) and free(c)), None)
            if spot is not None and inline is not None:
                inline.add(r.key)
        if spot is None:  # left out: a picture missing a label beats a refused picture (the lines say it)
            if dropped is not None:
                dropped.append(r.text)
            continue
        placed.append((spot, half, r.shown))
        out[r.key] = spot
    return out


def around(p, half, d=0.2) -> list[np.ndarray]:
    """Places for a label around point p, nearest first: above right, above, right, below right..."""
    out = []
    for r in (d, d + 0.15):
        for ang in (45, 90, 0, -45, 135, 180, -90, -135):
            t = math.radians(ang)
            out.append(np.array([p[0] + math.cos(t) * (r + half[0]), p[1] + math.sin(t) * (r + half[1])]))
    return out


def beside(points, half, fractions=(0.85, 0.7, 0.95, 0.55, 0.4, 0.25, 0.1)) -> list[np.ndarray]:
    """Places for a label beside a polyline, near its end first, either side."""
    out = []
    n = len(points)
    for f in fractions:
        # the point a fraction f along the line (a two-point segment too, not just its middle)
        at = f * (n - 1)
        i = min(n - 2, max(0, int(at)))
        p, q = np.array(points[i]), np.array(points[i + 1])
        d = q - p
        length = float(np.hypot(*d)) or 1e-9
        normal = np.array([-d[1], d[0]]) / length
        reach = abs(normal[0]) * half[0] + abs(normal[1]) * half[1]
        c = p + d * min(1.0, max(0.0, at - i))
        for side in (1, -1):
            for extra in (0.06, 0.2):
                out.append(c + normal * side * (reach + extra))
    return out


# ---- axes ----------------------------------------------------------------------------------------------


def nice_ticks(lo: float, hi: float, most: int = 5) -> list[float]:
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / max(1, most - 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    first = math.ceil(lo / step - 1e-9) * step
    ticks = []
    t = first
    while t <= hi + 1e-9:
        ticks.append(round(t, 10))
        t += step
    return ticks


def tick_text(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:g}"


def _data_extent(views: list[dict]) -> tuple[list[float], list[float]]:
    """The x and y ranges every snapshot's things need."""
    xs, ys = [], []
    for v in views:
        for it in v["items"].values():
            t = it["type"]
            if t == "curve":
                for piece in it["pieces"]:
                    xs += [p[0] for p in piece]
                    ys += [p[1] for p in piece]
            elif t in ("area", "segment", "vector", "polygon"):
                xs += [p[0] for p in it["points"]]
                ys += [p[1] for p in it["points"]]
            elif t in ("rects", "bars"):
                for x0, x1, h in it["rects" if t == "rects" else "bars"]:
                    xs += [x0, x1]
                    ys += [0.0, h]
            elif t == "points":
                xs += [p[0] for p in it["at"]]
                ys += [p[1] for p in it["at"]]
            elif t == "point":
                xs.append(it["at"][0])
                ys.append(it["at"][1])
            elif t == "field":
                for px, py, _u, _v in it["arrows"]:
                    xs.append(px)
                    ys.append(py)
    return xs, ys


def _bar_names(views: list[dict]) -> list[tuple[float, str]]:
    """(x, name) for each named bar any snapshot draws."""
    out: dict[float, str] = {}
    for v in views:
        for it in v["items"].values():
            if it["type"] == "bars" and it.get("names"):
                for (x0, x1, _h), name in zip(it["bars"], it["names"]):
                    out[round((x0 + x1) / 2, 9)] = name
    return sorted(out.items())


@dataclass
class AxesLayout:
    box: tuple[float, float, float, float]  # the plot area on screen: x0, x1, y0, y1
    x: tuple[float, float]  # the data ranges shown
    y: tuple[float, float]
    xticks: list[tuple[float, str, np.ndarray]]  # value, text, label centre
    yticks: list[tuple[float, str, np.ndarray]]
    xaxis_y: float  # where the x-axis is drawn (screen y)
    yaxis_x: float
    xlabel: np.ndarray | None
    ylabel: np.ndarray | None
    labels: dict[tuple[str, str], np.ndarray]  # each label's centre, by (thing key, label text)
    hidden: dict[str, set[int]] = field(default_factory=dict)  # field arrows left out under labels, by key
    inline: set = field(default_factory=set)  # labels set into their curve, by (key, label text)
    dropped: list = field(default_factory=list)  # labels with no clear place, left out
    inside_spots: dict = field(default_factory=dict)  # a bar value's place inside its bar (drawn white there)

    def to_screen(self, p) -> tuple[float, float]:
        x0, x1, y0, y1 = self.box
        return (x0 + (p[0] - self.x[0]) / (self.x[1] - self.x[0]) * (x1 - x0),
                y0 + (p[1] - self.y[0]) / (self.y[1] - self.y[0]) * (y1 - y0))


def _ranges(views: list[dict]) -> tuple[tuple[float, float], tuple[float, float]]:
    first = views[0]
    xs, ys = _data_extent(views)
    if first["x"] is not None:
        x = (float(first["x"][0]), float(first["x"][1]))
    elif xs:  # fitted to the bars and points drawn, with a little room
        pad = (max(xs) - min(xs)) * 0.04 or 0.5
        x = (min(xs) - pad, max(xs) + pad)
    else:
        x = (-5.0, 5.0)
    if first["y"] is not None:
        return x, (float(first["y"][0]), float(first["y"][1]))
    if not ys:
        return x, x
    lo, hi = min(ys), max(ys)
    if lo > 0 and lo < 0.35 * (hi - lo):  # a curve sitting a little above the axis: show the axis
        lo = 0.0
    if hi < 0 and -hi < 0.35 * (hi - lo):
        hi = 0.0
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.06
    valued = any(it["type"] == "bars" and it.get("values") for v in views for it in v["items"].values())
    return x, (lo - pad, hi + (hi - lo) * (0.24 if valued else 0.06))  # room above a bar for its value


def axes_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    x, y = _ranges(views)
    margin = TEXT_H + TICK_GAP + 0.1 + TEXT_H  # x tick labels below, the y name above
    if views[0]["equal"]:
        plot_w = width - 0.7
        h = plot_w * (y[1] - y[0]) / (x[1] - x[0])
        return title + margin + min(h, MIN_PLOT), title + margin + h
    return title + margin + MIN_PLOT - 0.1, title + margin + (width - 0.7) * 0.95


def axes_layout(views: list[dict], region) -> AxesLayout:
    title = 0.38 if any(v.get("title") for v in views) else 0.0
    x, y = _ranges(views)
    first = views[0]
    xt, yt = nice_ticks(*x), nice_ticks(*y)  # a bar chart of categories shows each bar's name instead
    ylabel_w = max((len(tick_text(t)) for t in yt), default=1) * CHAR_W
    left = region.cx - region.w / 2 + ylabel_w + TICK_GAP + 0.08
    right = region.cx + region.w / 2 - 0.12
    top = region.top - title - TEXT_H - 0.16  # the y-axis name sits above the plot, clear of the title
    named = _bar_names(views)
    # category names that won't fit side by side go on two rows, alternating, not dropped
    two_rows = bool(named) and sum(text_half(n)[0] * 2 for _x, n in named) > (region.w - 1.0) * 0.92
    bottom = region.bottom + TEXT_H + TICK_GAP + 0.04 + (TEXT_H + 0.02 if two_rows else 0.0)
    if right - left < MIN_PLOT or top - bottom < MIN_PLOT * 0.8:
        raise PictureError(f"the axes need more room than {region.w:.1f} by {region.h:.1f}")
    if first["equal"]:  # one scale for x and y, centred in the room
        scale = min((right - left) / (x[1] - x[0]), (top - bottom) / (y[1] - y[0]))
        w, h = scale * (x[1] - x[0]), scale * (y[1] - y[0])
        cx, cy = (left + right) / 2, (top + bottom) / 2
        left, right, bottom, top = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    box = (left, right, bottom, top)
    if first["y"] is None and not first["equal"]:
        # room above the tallest bar for its value, in screen units: a fraction of the range is too little in a
        # short plot (runs/picture-p4: a stacked bar chart dropped its tallest bar's value)
        tallest = max((h for v in views for it in v["items"].values() if it["type"] == "bars" and it.get("values")
                       for _a, _b, h in it["bars"]), default=None)
        if tallest is not None:
            need = TEXT_H + 2 * ROOM + 0.14  # on screen, above the tallest bar
            plot_h = top - bottom
            if need < plot_h * 0.6:
                # the top of the range such that (top - tallest) is `need` on screen once the range includes it
                hi = (tallest - need * y[0] / plot_h) / (1 - need / plot_h)
                if hi > y[1]:
                    y = (y[0], hi)
                    yt = nice_ticks(*y)
    lay = AxesLayout(box, x, y, [], [], 0.0, 0.0, None, None, {}, {}, set())
    lay.xaxis_y = lay.to_screen((0, min(max(0.0, y[0]), y[1])))[1]
    lay.yaxis_x = lay.to_screen((min(max(0.0, x[0]), x[1]), 0))[0]
    obstacles = Obstacles()
    for k, (t, text) in enumerate(named if named else [(t, tick_text(t)) for t in xt]):
        sx = lay.to_screen((t, 0))[0]
        row = k % 2 if two_rows else 0
        c = np.array([sx, bottom - TICK_GAP - TEXT_H / 2 - row * (TEXT_H + 0.02)])
        lay.xticks.append((t, text, c))
    for t in yt:
        sy = lay.to_screen((0, t))[1]
        half = text_half(tick_text(t))
        c = np.array([left - TICK_GAP - half[0] + ROOM, sy])
        lay.yticks.append((t, tick_text(t), c))
    # tick labels may not crowd: drop every other one until they stand apart
    for name in ("xticks", "yticks"):
        ticks = getattr(lay, name)
        if name == "xticks" and named:  # names are never thinned: two rows hold them
            continue
        while len(ticks) > 2 and any(np.all(np.abs(a[2] - b[2]) < text_half(a[1]) + text_half(b[1]))
                                     for a, b in zip(ticks, ticks[1:])):
            ticks = ticks[::2]
        setattr(lay, name, ticks)
    for _t, text, c in lay.xticks + lay.yticks:
        obstacles.boxes.append((c, text_half(text)))
    if first["xlabel"]:
        half = text_half(first["xlabel"])
        c = np.array([right - half[0] + ROOM, bottom - TICK_GAP - TEXT_H / 2])
        if any(np.all(np.abs(c - c2) < half + h2) for c2, h2 in obstacles.boxes):  # the last tick gives way
            lay.xticks = [t for t in lay.xticks if not np.all(np.abs(c - t[2]) < half + text_half(t[1]))]
            obstacles.boxes = [(t[2], text_half(t[1])) for t in lay.xticks + lay.yticks]
        lay.xlabel = c
        obstacles.boxes.append((c, half))
    if first["ylabel"]:
        half = text_half(first["ylabel"])
        lay.ylabel = np.array([max(lay.yaxis_x, left + half[0] - ROOM), top + 0.05 + TEXT_H / 2])
        obstacles.boxes.append((lay.ylabel, half))
    # what each label keeps clear of: the axes, the tick labels, and everything on screen with it (a vector
    # field aside: its arrows are a texture, and the ones under a label are left out instead)
    lo, hi = (left, bottom), (right, top)
    # the axes and their tick marks (drawn across the axes, 0.05 each side)
    marks = [((lay.to_screen((t, 0))[0], lay.xaxis_y - 0.05), (lay.to_screen((t, 0))[0], lay.xaxis_y + 0.05))
             for t, _text, _c in lay.xticks]
    marks += [((lay.yaxis_x - 0.05, lay.to_screen((0, t))[1]), (lay.yaxis_x + 0.05, lay.to_screen((0, t))[1]))
              for t, _text, _c in lay.yticks]
    base = Obstacles(segments=[((left, lay.xaxis_y), (right, lay.xaxis_y)), ((lay.yaxis_x, bottom),
                                                                             (lay.yaxis_x, top))] + marks,
                     boxes=list(obstacles.boxes))
    requests: dict[tuple[str, str], Request] = {}
    for i, v in enumerate(views):
        lines = {key: [piece for line in item_polylines(it, lay) for piece in clip_polyline(line, lo, hi)]
                 for key, it in v["items"].items() if it["type"] not in ("field", "grid")}
        for key, it in v["items"].items():
            if not it.get("label"):
                continue
            rk = (key, it["label"])
            if rk not in requests:
                half = text_half(it["label"])
                if it["type"] == "point":
                    cands = around(lay.to_screen(it["at"]), half)
                elif it["type"] == "vector":  # past its tip first, then beside it
                    tail, tip = map(np.array, item_polylines(it, lay)[0])
                    d = (tip - tail) / (float(np.hypot(*(tip - tail))) or 1e-9)
                    reach = abs(d[0]) * half[0] + abs(d[1]) * half[1]
                    cands = [tip + d * (reach + e) for e in (0.08, 0.2)] + around(tuple(tip), half, 0.22) + beside(
                        [tuple(tail), tuple(tip)], half)
                elif it["type"] == "points":
                    cands = [c for p in it["at"][::-1][:4] for c in around(lay.to_screen(p), half)]
                elif it["type"] in ("area", "polygon"):
                    cands = _inside(it, lay, half)
                else:
                    own = lines.get(key) or [[(0, 0), (0, 0)]]
                    cands = beside(max(own, key=len), half)
                requests[rk] = Request(rk, it["label"], cands, Obstacles(list(base.segments), list(base.boxes)),
                                       set())
                if it["type"] == "curve":  # failing a place beside it, on the curve, as a contour plot labels
                    longest = max(lines.get(key) or [[(0, 0)]], key=len)
                    requests[rk].inline = [np.array(longest[int(f * (len(longest) - 1))])
                                           for f in (0.5, 0.25, 0.75, 0.1, 0.9, 0.4, 0.6)]
            req = requests[rk]
            req.shown.add(i)
            for other, ls in lines.items():  # an area's label sits inside its outline, which it keeps clear of
                for line in ls:
                    (req.own if other == key and it["type"] not in ("area", "polygon") else req.obstacles
                     ).add_polyline(line)
            for other, it2 in v["items"].items():
                if it2["type"] == "point" and other != key:
                    req.obstacles.discs.append((lay.to_screen(it2["at"]), POINT_R + ROOM))
                if it2["type"] == "points" and other != key:
                    req.obstacles.discs += [(lay.to_screen(p), POINT_R + ROOM) for p in it2["at"]]
        for key, it in v["items"].items():  # each bar's value, just above it
            if it["type"] != "bars" or not it.get("values"):
                continue
            for j, ((x0, x1, h), text) in enumerate(zip(it["bars"], it["values"])):
                rk = (f"{key}#{j}", text)
                if rk not in requests:
                    top_y = lay.to_screen(((x0 + x1) / 2, max(h, 0.0)))
                    base_y = lay.to_screen(((x0 + x1) / 2, 0.0))[1]
                    bar_w = abs(lay.to_screen((x1, 0))[0] - lay.to_screen((x0, 0))[0])
                    half = text_half(text)
                    cands = [np.array([top_y[0], top_y[1] + half[1] + d]) for d in (0.04, 0.12, 0.22, 0.34, 0.46)]
                    if top_y[1] - base_y > 2 * half[1] + 0.12 and bar_w > 2 * half[0]:  # inside a tall bar's top
                        inside = np.array([top_y[0], top_y[1] - half[1] - 0.04])
                        cands.append(inside)
                        lay.inside_spots[rk] = inside
                    requests[rk] = Request(rk, text, cands, Obstacles(list(base.segments), list(base.boxes)), set())
                req = requests[rk]
                req.shown.add(i)
                for other, ls in lines.items():
                    if other != key:
                        for line in ls:
                            req.obstacles.add_polyline(line)
    lay.labels = place(list(requests.values()), (region.cx - region.w / 2, region.cx + region.w / 2,
                                                 region.bottom, region.top - title), "the axes", lay.inline,
                       lay.dropped)
    # field arrows that would cross a label shown with them are left out
    for i, v in enumerate(views):
        for key, it in v["items"].items():
            if it["type"] != "field":
                continue
            boxes = [(c, text_half(r.text)) for rk, c in lay.labels.items() for r in [requests[rk]]
                     if i in r.shown]
            for j, (p, q) in enumerate(field_arrows(it, lay)):
                if any(seg_hits_box(p, q, c - h, c + h) for c, h in boxes):
                    lay.hidden.setdefault(key, set()).add(j)
    return lay


def _inside(item: dict, lay: AxesLayout, half: np.ndarray) -> list[np.ndarray]:
    """Places for an area's label inside it (its border then doesn't cut the label), nearest its middle first."""
    pts = np.array([lay.to_screen(p) for p in item["points"]])
    lo, hi = pts.min(0), pts.max(0)
    centre = pts.mean(0)
    cands = [np.array([lo[0] + (hi[0] - lo[0]) * i / 8, lo[1] + (hi[1] - lo[1]) * j / 8])
             for i in range(1, 8) for j in range(1, 8)]
    inside = [c for c in cands if _in_polygon(c, pts)]
    return sorted(inside, key=lambda c: float(np.hypot(*(c - centre))))


def _in_polygon(c, pts) -> bool:
    x, y = c
    inside = False
    for (x1, y1), (x2, y2) in zip(pts, np.roll(pts, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def item_polylines(it: dict, lay: AxesLayout) -> list[list[tuple[float, float]]]:
    """A thing on the axes as screen polylines (unclipped)."""
    t = it["type"]
    if t == "curve":
        return [[lay.to_screen(p) for p in piece] for piece in it["pieces"]]
    if t in ("area", "polygon"):
        pts = [lay.to_screen(p) for p in it["points"]]
        return [pts + pts[:1]]
    if t in ("segment", "vector"):
        return [[lay.to_screen(p) for p in it["points"]]]
    if t == "grid":
        return [[lay.to_screen(p) for p in piece] for piece in it["pieces"]]
    if t in ("rects", "bars"):
        out = []
        for x0, x1, h in it["rects" if t == "rects" else "bars"]:
            corners = [(x0, 0), (x0, h), (x1, h), (x1, 0)]
            out.append([lay.to_screen(p) for p in corners])
        return out
    if t == "field":
        return [list(a) for a in field_arrows(it, lay)]
    return []


def field_arrows(it: dict, lay: AxesLayout) -> list[tuple[tuple, tuple]]:
    """Each arrow of a vector field on screen, scaled so the longest fills most of its grid cell."""
    x0, x1, y0, y1 = lay.box
    n = it["n"]
    cell = min((x1 - x0), (y1 - y0)) / n
    biggest = max((math.hypot(u, v) for _x, _y, u, v in it["arrows"]), default=0) or 1.0
    sx = (x1 - x0) / (lay.x[1] - lay.x[0])
    sy = (y1 - y0) / (lay.y[1] - lay.y[0])
    out = []
    for px, py, u, v in it["arrows"]:
        su, sv = u * sx, v * sy
        m = math.hypot(su, sv)
        if m < 1e-12:
            continue
        length = 0.8 * cell * math.hypot(u, v) / biggest
        length = max(length, 0.25 * cell)
        c = lay.to_screen((px, py))
        dx, dy = su / m * length / 2, sv / m * length / 2
        out.append(((c[0] - dx, c[1] - dy), (c[0] + dx, c[1] + dy)))
    return out


# ---- Venn ----------------------------------------------------------------------------------------------


@dataclass
class VennLayout:
    circles: list[tuple[tuple[float, float], float]]  # each set's circle: centre, radius
    names: list[np.ndarray]  # each set's name, centre
    universe: tuple[float, float, float, float] | None  # the box round everything, when anything is outside
    elements: dict[str, np.ndarray]  # each element's centre


def _member(p, circles) -> str:
    return "".join("1" if math.dist(p, c) < r else "0" for c, r in circles)


# a diagram of n sets is this many radii wide and tall (3 sets: centres on a triangle, 0.62 radii from the middle)
VENN_SPAN = {1: (2.0, 2.0), 2: (3.1, 2.0), 3: (3.07, 2.93)}


def _venn_pad(views) -> float:
    n = len(views[0]["sets"])
    outside = any(m == "0" * n for v in views for m in v["elements"].values()) or any(
        "0" * n in cells for v in views for cells, _s in v["shaded"])
    return 0.12 + (0.3 if outside else 0.0)


def venn_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    sw, sh = VENN_SPAN[len(views[0]["sets"])]
    pad = _venn_pad(views)
    r = (width - 2 * pad) / sw
    return title + 1.8, title + TEXT_H + 2 * pad + sh * r + 0.1


def venn_layout(views: list[dict], region) -> VennLayout:
    title = 0.38 if any(v.get("title") for v in views) else 0.0
    n = len(views[0]["sets"])
    outside = _venn_pad(views) > 0.2
    pad = _venn_pad(views)
    w, h = region.w - 2 * pad, region.h - title - 2 * pad - TEXT_H  # set names need a row
    sw, sh = VENN_SPAN[n]
    r = min(w / sw, h / sh)
    middle_y = region.top - title - (region.h - title) / 2
    # the names' row sits above (1-2 sets) or below (3 sets: C's name) the circles
    cx, cy = region.cx, middle_y - TEXT_H / 2 if n < 3 else middle_y + TEXT_H / 2
    if n == 1:
        centres = [(cx, cy)]
    elif n == 2:
        centres = [(cx - 0.55 * r, cy), (cx + 0.55 * r, cy)]
    else:
        d = 0.62 * r  # the centres' distance from the middle: each pair overlaps by about a radius
        # the circles reach d/2 + r above the middle and d + r below it, so the middle sits d/4 above centre
        mid = cy + d / 4
        half_w = d * math.cos(math.radians(30))
        centres = [(cx - half_w, mid + d / 2), (cx + half_w, mid + d / 2), (cx, mid - d)]
    if r < 0.6:
        raise PictureError(f"the Venn diagram needs more room than {region.w:.1f} by {region.h:.1f}")
    circles = [(c, r) for c in centres]
    names = []
    for k, ((c, _r), set_name) in enumerate(zip(circles, views[0]["sets"])):
        ang = math.radians(-90 if (n == 3 and k == 2) else 135 if (n == 1 or k == 0) else 45)
        half = text_half(set_name)
        reach = abs(math.cos(ang)) * half[0] + abs(math.sin(ang)) * half[1]  # the name's extent that way
        names.append(np.array([c[0] + math.cos(ang) * (r + reach + 0.06), c[1] + math.sin(ang) * (r + reach + 0.06)]))
    box = None
    if outside:  # round the circles and their names
        xs = [c[0] for c, _ in circles]
        ys = [c[1] for c, _ in circles]
        x0, x1, y0, y1 = min(xs) - r - 0.26, max(xs) + r + 0.26, min(ys) - r - 0.26, max(ys) + r + 0.26
        for p, set_name in zip(names, views[0]["sets"]):
            half = text_half(set_name)
            x0, x1 = min(x0, p[0] - half[0] - 0.06), max(x1, p[0] + half[0] + 0.06)
            y0, y1 = min(y0, p[1] - half[1] - 0.06), max(y1, p[1] + half[1] + 0.06)
        box = (x0, x1, y0, y1)
    # elements: each inside its own region, clear of every circle's edge and of the other elements
    elements: dict[str, np.ndarray] = {}
    placed: list[tuple[np.ndarray, np.ndarray]] = [(p, text_half("AB")) for p in names]
    every = {}
    for v in views:
        every.update(v["elements"])
    by_region: dict[str, list[str]] = {}
    for e, m in sorted(every.items()):
        by_region.setdefault(m, []).append(e)
    x0, x1 = (box[0], box[1]) if box else (region.cx - region.w / 2, region.cx + region.w / 2)
    y0, y1 = (box[2], box[3]) if box else (region.bottom, region.top - title)
    grid = [np.array([x0 + (x1 - x0) * i / 40, y0 + (y1 - y0) * j / 40]) for i in range(1, 40) for j in range(1, 40)]
    def fits(c, half, m) -> bool:
        """The box round c lies wholly inside the circles m marks 1 and wholly outside the others."""
        for (centre, rr), bit in zip(circles, m):
            dx = max(abs(c[0] - centre[0]) - half[0], 0.0)
            dy = max(abs(c[1] - centre[1]) - half[1], 0.0)
            near = math.hypot(dx, dy)  # the box's nearest point to the centre
            far = math.hypot(abs(c[0] - centre[0]) + half[0], abs(c[1] - centre[1]) + half[1])
            if bit == "1" and far > rr - 0.05:
                return False
            if bit == "0" and near < rr + 0.05:
                return False
        return box is None or (box[0] + half[0] + 0.05 < c[0] < box[1] - half[0] - 0.05
                               and box[2] + half[1] + 0.05 < c[1] < box[3] - half[1] - 0.05)

    for m, elems in by_region.items():
        cell = [p for p in grid if _member(p, circles) == m]
        if not cell:
            raise PictureError(f"the Venn diagram has no region {m} to put {', '.join(elems)} in")
        middle = np.mean(cell, axis=0)
        for e in elems:
            half = text_half(e)
            spot = next((p for p in sorted(cell, key=lambda p: float(np.hypot(*(p - middle))))
                         if fits(p, half, m) and not any(np.all(np.abs(p - q) < half + hq + 0.04)
                                                         for q, hq in placed)), None)
            if spot is None:
                raise PictureError(f"the Venn diagram's region {m} has no room for {len(elems)} elements; "
                                   "use fewer elements")
            placed.append((spot, half))
            elements[e] = spot
    return VennLayout(circles, names, box, elements)


# ---- geometry ------------------------------------------------------------------------------------------


@dataclass
class GeometryLayout:
    scale: float
    origin: tuple[float, float]  # the screen point of data (0, 0)
    labels: dict[tuple[str, str], np.ndarray]  # by (key, label text): a point's key is "pt-" + its own
    dropped: list = field(default_factory=list)  # labels with no clear place, left out

    def to_screen(self, p) -> tuple[float, float]:
        return (self.origin[0] + p[0] * self.scale, self.origin[1] + p[1] * self.scale)


def _geo_extent(views: list[dict]):
    xs, ys = [], []
    for v in views:
        for pt in v["points"].values():
            xs.append(pt["at"][0])
            ys.append(pt["at"][1])
        for it in v["items"].values():
            if it["type"] == "circle" and it["center"] in v["points"]:
                cx, cy = v["points"][it["center"]]["at"]
                xs += [cx - it["r"], cx + it["r"]]
                ys += [cy - it["r"], cy + it["r"]]
            if it["type"] in ("arc", "sector") and it["center"] in v["points"]:
                cx, cy = v["points"][it["center"]]["at"]
                for t in np.linspace(it["t1"], it["t2"], 13):
                    for rr in (it["r1"], it["r2"]):
                        xs.append(cx + rr * math.cos(t))
                        ys.append(cy + rr * math.sin(t))
    if not xs:
        raise PictureError("the figure has no points")
    return min(xs), max(xs), min(ys), max(ys)


def geometry_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    x0, x1, y0, y1 = _geo_extent(views)
    w = max(x1 - x0, 1e-9)
    h = max(y1 - y0, 1e-9)
    usable = width - 1.0
    return title + 1.4, title + 1.0 + usable * h / w


def geometry_points(v: dict, lay: GeometryLayout) -> dict[str, tuple[float, float]]:
    return {k: lay.to_screen(p["at"]) for k, p in v["points"].items()}


def geometry_layout(views: list[dict], region) -> GeometryLayout:
    title = 0.38 if any(v.get("title") for v in views) else 0.0
    x0, x1, y0, y1 = _geo_extent(views)
    margin = 0.5  # room for point labels round the figure
    w, h = region.w - 2 * margin, region.h - title - 2 * margin
    scale = min(w / max(x1 - x0, 1e-9), h / max(y1 - y0, 1e-9))
    if scale * max(x1 - x0, y1 - y0) < MIN_PLOT:
        raise PictureError(f"the figure needs more room than {region.w:.1f} by {region.h:.1f}")
    cx, cy = region.cx, region.top - title - (region.h - title) / 2
    origin = (cx - (x0 + x1) / 2 * scale, cy - (y0 + y1) / 2 * scale)
    lay = GeometryLayout(scale, origin, {}, [])
    requests: dict[tuple[str, str], Request] = {}
    for i, v in enumerate(views):
        pts = geometry_points(v, lay)
        lines = {key: geometry_polylines(it, pts, lay) for key, it in v["items"].items()}
        wanted = [(("pt-" + k, p["label"]), p["label"], lambda k=k, p=p: around(pts[k], text_half(p["label"]), 0.14))
                  for k, p in v["points"].items() if p["label"]]
        for key, it in v["items"].items():
            if not it.get("label"):
                continue
            half = text_half(it["label"])
            if it["type"] == "angle":
                vx, vy = pts[it["vertex"]]
                mid = it["start"] + it["sweep"] / 2
                along = abs(math.cos(mid)) * half[0] + abs(math.sin(mid)) * half[1]

                def cands(vx=vx, vy=vy, mid=mid, along=along):
                    return [np.array([vx + math.cos(mid) * (ANGLE_R + 0.06 + along + k * 0.08),
                                      vy + math.sin(mid) * (ANGLE_R + 0.06 + along + k * 0.08)]) for k in range(10)]
            else:
                def cands(key=key, half=half):
                    ls = lines.get(key) or []
                    return beside(max(ls, key=len), half, (0.5, 0.35, 0.65)) if ls else []
            wanted.append(((key, it["label"]), it["label"], cands))
        for rk, text, make in wanted:
            if rk not in requests:
                requests[rk] = Request(rk, text, make(), Obstacles(), set())
            req = requests[rk]
            req.shown.add(i)
            for ls in lines.values():
                for line in ls:
                    req.obstacles.add_polyline(line)
            for k, p in pts.items():
                if not v["points"][k].get("hidden"):
                    req.obstacles.discs.append((p, POINT_R + ROOM))
    lay.labels = place(list(requests.values()), (region.cx - region.w / 2, region.cx + region.w / 2,
                                                 region.bottom, region.top - title), "the figure",
                       dropped=lay.dropped)
    return lay


ANGLE_R = 0.32


def geometry_polylines(it: dict, pts: dict, lay: GeometryLayout) -> list[list[tuple[float, float]]]:
    t = it["type"]
    if t == "segment":
        return [[pts[it["ends"][0]], pts[it["ends"][1]]]]
    if t == "polygon":
        ring = [pts[k] for k in it["points"]]
        return [ring + ring[:1]]
    if t == "circle":
        c, r = pts[it["center"]], it["r"] * lay.scale
        return [[(c[0] + r * math.cos(a), c[1] + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 49)]]
    if t == "angle":
        vx, vy = pts[it["vertex"]]
        return [[(vx + ANGLE_R * math.cos(a), vy + ANGLE_R * math.sin(a))
                 for a in np.linspace(it["start"], it["start"] + it["sweep"], 13)]]
    if t in ("arc", "sector"):
        return [ring_points(it, pts, lay)]
    return []


def ring_points(it: dict, pts: dict, lay: GeometryLayout) -> list[tuple[float, float]]:
    """An arc (one radius) or an annular sector (inner arc, outer arc back, closed) on screen."""
    cx, cy = pts[it["center"]]
    ts = np.linspace(it["t1"], it["t2"], 25)
    outer = [(cx + it["r2"] * lay.scale * math.cos(t), cy + it["r2"] * lay.scale * math.sin(t)) for t in ts]
    if it["type"] == "arc":
        return outer
    inner = [(cx + it["r1"] * lay.scale * math.cos(t), cy + it["r1"] * lay.scale * math.sin(t)) for t in ts]
    return inner + outer[::-1] + inner[:1]


# ---- number line ---------------------------------------------------------------------------------------

JUMP_MAX = 0.9  # the tallest arc


@dataclass
class NumberLineLayout:
    x0: float
    x1: float
    y: float  # the line's height on screen
    lo: float
    hi: float
    ticks: list[tuple[float, str, np.ndarray]]  # value, text, label centre (below the line)
    labels: dict[tuple[str, str], np.ndarray]
    dropped: list = field(default_factory=list)

    def at(self, v: float) -> float:
        return self.x0 + (v - self.lo) / (self.hi - self.lo) * (self.x1 - self.x0)


def numberline_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    jumps = any(it["type"] == "jump" for v in views for it in v["items"].values())
    return title + 1.3, title + (2.4 if jumps else 1.6)


def jump_points(it: dict, lay: NumberLineLayout) -> list[tuple[float, float]]:
    a, b = lay.at(it["a"]), lay.at(it["b"])
    h = min(JUMP_MAX, 0.35 + 0.3 * abs(b - a))
    return [(a + (b - a) * t, lay.y + 0.08 + h * 4 * t * (1 - t)) for t in np.linspace(0, 1, 21)]


def numberline_layout(views: list[dict], region) -> NumberLineLayout:
    title = 0.38 if any(v.get("title") for v in views) else 0.0
    first = views[0]
    lo, hi = first["lo"], first["hi"]
    x0, x1 = region.cx - region.w / 2 + 0.3, region.cx + region.w / 2 - 0.3
    jumps = any(it["type"] == "jump" for v in views for it in v["items"].values())
    above = (JUMP_MAX + TEXT_H + 0.45) if jumps else (TEXT_H + 0.6)
    below = TEXT_H + 0.2
    room = region.h - title
    above = min(above, room - below)
    y = region.top - title - (room - above - below) / 2 - above  # the drawing centred in its band
    lay = NumberLineLayout(x0, x1, y, lo, hi, [], {})
    step = first["step"]
    values = [lo + k * step for k in range(int(round((hi - lo) / step)) + 1)] if step else nice_ticks(lo, hi, 7)
    ticks = [(v, tick_text(v), np.array([lay.at(v), y - 0.1 - TEXT_H / 2])) for v in values]
    while len(ticks) > 2 and any(np.all(np.abs(a[2] - b[2]) < text_half(a[1]) + text_half(b[1]))
                                 for a, b in zip(ticks, ticks[1:])):
        ticks = ticks[::2]  # numbers that would touch: every other one (the marks stay)
    lay.ticks = ticks
    base = Obstacles(segments=[((x0 - 0.2, y), (x1 + 0.2, y))], boxes=[(c, text_half(t)) for _v, t, c in ticks])
    requests: dict[tuple[str, str], Request] = {}
    for i, v in enumerate(views):
        arcs = {key: jump_points(it, lay) for key, it in v["items"].items() if it["type"] == "jump"}
        for key, it in v["items"].items():
            if not it.get("label"):
                continue
            rk = (key, it["label"])
            if rk not in requests:
                half = text_half(it["label"])
                if it["type"] == "point":
                    px = lay.at(it["x"])
                    cands = [np.array([px + dx, y + POINT_R + 0.06 + half[1] + dy]) for dy in (0.0, 0.25, 0.5, 0.75)
                             for dx in (0.0, 0.25, -0.25, 0.5, -0.5)]
                elif it["type"] == "interval":
                    mid = (lay.at(it["a"]) + lay.at(it["b"])) / 2
                    cands = [np.array([mid + dx, y + 0.12 + half[1] + dy]) for dy in (0.0, 0.25, 0.5, 0.75)
                             for dx in (0, .3, -.3, .6, -.6)]
                else:
                    top = max(arcs[key], key=lambda p: p[1])
                    cands = [np.array([top[0] + dx, top[1] + 0.04 + half[1] + dy]) for dy in (0.0, 0.15, 0.3, 0.45, 0.6)
                             for dx in (0.0, 0.25, -0.25, 0.5, -0.5)]
                    cands += [np.array([top[0], top[1] - 0.04 - half[1]])]  # under the arc's peak
                requests[rk] = Request(rk, it["label"], cands, Obstacles(list(base.segments), list(base.boxes)), set())
            req = requests[rk]
            req.shown.add(i)
            for k2, pts in arcs.items():
                req.obstacles.add_polyline(pts)
            for k2, it2 in v["items"].items():
                if it2["type"] == "point" and k2 != key:
                    req.obstacles.discs.append(((lay.at(it2["x"]), y), POINT_R + ROOM))
    lay.labels = place(list(requests.values()), (region.cx - region.w / 2, region.cx + region.w / 2, region.bottom,
                                                 region.top - title), "the number line", dropped=lay.dropped)
    return lay


# ---- 3D surface (drawn flat from one fixed view) ------------------------------------------------------

AZIMUTH, ELEVATION = math.radians(-55), math.radians(24)
Z_HEIGHT = 1.25  # the z range's height, in units of half the x range
_R = np.array([-math.sin(AZIMUTH), math.cos(AZIMUTH), 0.0])
_U = np.array([-math.cos(AZIMUTH) * math.sin(ELEVATION), -math.sin(AZIMUTH) * math.sin(ELEVATION), math.cos(ELEVATION)])
_D = np.array([math.cos(AZIMUTH) * math.cos(ELEVATION), math.sin(AZIMUTH) * math.cos(ELEVATION), math.sin(ELEVATION)])


@dataclass
class SurfaceLayout:
    x: tuple[float, float]
    y: tuple[float, float]
    z: tuple[float, float]
    scale: float
    origin: tuple[float, float]
    axes: list[tuple[tuple, tuple]]  # the floor's back edges and the z axis, on screen
    names: list[tuple[str, np.ndarray]]  # axis names and end values, placed
    labels: dict[tuple[str, str], np.ndarray]
    dropped: list = field(default_factory=list)

    def unit(self, p) -> np.ndarray:
        """A data point in the view's own cube: x, y in [-1, 1], z in [0, Z_HEIGHT]."""
        (x0, x1), (y0, y1), (z0, z1) = self.x, self.y, self.z
        return np.array([(p[0] - x0) / (x1 - x0) * 2 - 1, (p[1] - y0) / (y1 - y0) * 2 - 1,
                         (p[2] - z0) / (z1 - z0) * Z_HEIGHT])

    def to_screen(self, p) -> tuple[float, float]:
        q = self.unit(p)
        return (self.origin[0] + float(q @ _R) * self.scale, self.origin[1] + float(q @ _U) * self.scale)

    def depth(self, p) -> float:
        return float(self.unit(p) @ _D)


def _surface_z(views: list[dict]) -> tuple[float, float]:
    if views[0]["z"] is not None:
        return tuple(views[0]["z"])
    zs = [0.0]
    for v in views:
        for it in v["items"].values():
            if it["type"] == "mesh":
                zs += [z for row in it["z"] for z in row]
            elif it["type"] == "columns":
                zs += [c[4] for c in it["columns"]]
            elif it["type"] == "point":
                zs.append(it["at"][2])
    lo, hi = min(zs), max(zs)
    return (lo, hi if hi > lo else lo + 1)


def surface_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    return title + 2.2, title + width * 1.05


def surface_faces(it: dict, lay: SurfaceLayout) -> list[tuple[list[tuple[float, float]], float, float]]:
    """A thing's faces: (screen corners, depth, brightness 0-1), the ones a viewer sees, far first."""
    faces = []

    def face(corners):
        q = [lay.unit(c) for c in corners]
        normal = np.cross(q[1] - q[0], q[2] - q[0])
        if np.linalg.norm(normal) < 1e-12:
            return
        normal /= np.linalg.norm(normal)
        if normal @ _D < 0:
            normal = -normal if it["type"] == "mesh" else normal  # a mesh shows both sides
        if normal @ _D < -1e-9:
            return
        light = 0.45 + 0.55 * max(0.0, float(normal @ np.array([0.3, -0.2, 0.93])))
        faces.append(([lay.to_screen(c) for c in corners], float(np.mean([lay.depth(c) for c in corners])), light))

    if it["type"] == "mesh":
        n, z = it["n"], it["z"]
        (x0, x1), (y0, y1) = lay.x, lay.y
        for i in range(n):
            for j in range(n):
                xs = [x0 + (x1 - x0) * k / n for k in (i, i + 1)]
                ys = [y0 + (y1 - y0) * k / n for k in (j, j + 1)]
                face([(xs[0], ys[0], z[i][j]), (xs[1], ys[0], z[i + 1][j]), (xs[1], ys[1], z[i + 1][j + 1]),
                      (xs[0], ys[1], z[i][j + 1])])
    elif it["type"] == "columns":
        base = lay.z[0] if lay.z[0] > 0 else 0.0
        for xa, xb, ya, yb, h in it["columns"]:
            lo, hi = min(base, h), max(base, h)
            face([(xa, ya, hi), (xb, ya, hi), (xb, yb, hi), (xa, yb, hi)])  # top
            face([(xa, ya, lo), (xb, ya, lo), (xb, ya, hi), (xa, ya, hi)])  # y = ya side
            face([(xb, yb, lo), (xa, yb, lo), (xa, yb, hi), (xb, yb, hi)])  # y = yb side
            face([(xa, yb, lo), (xa, ya, lo), (xa, ya, hi), (xa, yb, hi)])  # x = xa side
            face([(xb, ya, lo), (xb, yb, lo), (xb, yb, hi), (xb, ya, hi)])  # x = xb side
    return sorted(faces, key=lambda f: f[1])


def surface_layout(views: list[dict], region) -> SurfaceLayout:
    title = 0.38 if any(v.get("title") for v in views) else 0.0
    first = views[0]
    lay = SurfaceLayout(tuple(first["x"]), tuple(first["y"]), _surface_z(views), 1.0, (0.0, 0.0), [], [], {})
    (x0, x1), (y0, y1), (z0, z1) = lay.x, lay.y, lay.z
    cube = [(a, b, c) for a in (x0, x1) for b in (y0, y1) for c in (z0, z1)]
    pts = np.array([lay.to_screen(p) for p in cube])
    margin = 0.45  # axis names and end values round the box
    w, h = region.w - 2 * margin, region.h - title - 2 * margin
    lay.scale = min(w / max(np.ptp(pts[:, 0]), 1e-9), h / max(np.ptp(pts[:, 1]), 1e-9))
    pts = np.array([lay.to_screen(p) for p in cube])  # at the new scale, origin still 0
    cx, cy = region.cx, region.top - title - (region.h - title) / 2
    lay.origin = (cx - (pts[:, 0].min() + pts[:, 0].max()) / 2, cy - (pts[:, 1].min() + pts[:, 1].max()) / 2)
    # the axes run along the floor's back edges from its farthest corner, and up from it
    floor = [(a, b, z0) for a in (x0, x1) for b in (y0, y1)]
    back = min(floor, key=lay.depth)
    ex = (x1 if back[0] == x0 else x0, back[1], z0)
    ey = (back[0], y1 if back[1] == y0 else y0, z0)
    ez = (back[0], back[1], z1)
    lay.axes = [(lay.to_screen(back), lay.to_screen(e)) for e in (ex, ey, ez)]
    obstacles = Obstacles()
    for a, b in lay.axes:
        obstacles.segments.append((a, b))
    for v in views:
        for it in v["items"].values():
            for corners, _d, _l in surface_faces(it, lay):
                obstacles.add_polyline(corners + corners[:1])
    bounds = (region.cx - region.w / 2, region.cx + region.w / 2, region.bottom, region.top - title)
    # axis names beyond each axis's far end; then each axis's end values beside its ends
    wanted = []
    for (a, b), name in zip(lay.axes, first["labels"]):
        if name:
            d = np.array(b) - np.array(a)
            d /= np.linalg.norm(d) or 1
            half = text_half(name)
            wanted.append(((f"axis-{name}", name), name, [np.array(b) + d * (half.max() + k * 0.1) for k in range(1, 6)]))
    reqs = [Request(rk, text, cands, Obstacles(list(obstacles.segments), list(obstacles.boxes), []), {0})
            for rk, text, cands in wanted]
    names = place(reqs, bounds, "the 3D view", dropped=[])
    lay.names = [(text, c) for (_k, text), c in names.items()]
    requests = []
    for i, v in enumerate(views):
        for key, it in v["items"].items():
            if it["type"] == "point" and it.get("label"):
                p = lay.to_screen(it["at"])
                obs = Obstacles(list(obstacles.segments), [(c, text_half(t)) for t, c in lay.names], [])
                requests.append(Request((key, it["label"]), it["label"], around(p, text_half(it["label"])), obs, {i}))
    lay.labels = place(requests, bounds, "the 3D view", dropped=lay.dropped)
    return lay
