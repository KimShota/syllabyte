"""
Where a diagram view's parts go (plan/scene-grammar-plan.md, P5): tables, boxes and arrows, timelines, message
sequences, logic circuits and memory diagrams. Pure Python (numpy), no Manim.

The rules are the ones every view follows (scene/layout.py, scene/math_layout.py): one layout for the whole program,
so nothing moves unless the structure does; the picture is as large as its band allows; text keeps the minimum font;
every label sits clear of every line, box and other label; and what can't be drawn legibly is refused with the
reason, so the planner can make it smaller.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from animation_agent.scene.api import PictureError
from animation_agent.scene.math_layout import TEXT_H, Obstacles, Request, place
from animation_agent.scene.math_layout import text_half as _math_half

TITLE_H = 0.38
CHAR = 0.19  # a character at the minimum font, with a little to spare (digits measure 0.17, capitals up to 0.21)
MAX_GROW = 1.4  # how much a diagram with room to spare grows, its text with it (42 at most)


def _title(views: list[dict]) -> float:
    return TITLE_H if any(v.get("title") for v in views) else 0.0


def text_half(text: str) -> np.ndarray:
    """Half a label's box by measured widths (a diagram's labels are words, often with capitals)."""
    return _math_half(text, exact=True)


def text_w(text: str, k: float = 1.0) -> float:
    from animation_agent.scene.math_layout import text_width

    return text_width(text) * k


# ---- grid (a table or a matrix) -------------------------------------------------------------------------

ROW_H = 0.42
MIN_COL = 0.46
HEAD_H = 0.36
BRACKET = 0.16  # a matrix's bracket, each side


@dataclass
class GridLayout:
    k: float  # the scale: 1 at the minimum font
    transposed: bool  # drawn on its side (rows as columns): too wide for the frame, not too tall
    x: list[float]  # each column's centre
    w: list[float]  # each column's width
    y: list[float]  # each row's centre
    h: float  # a row's height
    head_y: float | None  # the column names' centre
    name_x: float | None  # the row names' centre
    left: float
    right: float
    top: float
    bottom: float

    @property
    def font(self) -> int:
        return round(30 * self.k)


def _grid_size(views: list[dict]) -> tuple[list[float], float, float, float]:
    """At scale 1: each column's width, the row names' width, the header's height and the body's height."""
    first = views[0]
    cols = len(first["values"][0])
    texts = [max((text_w(r[c]) for v in views for r in v["values"]), default=0.0) for c in range(cols)]
    if first["col_names"]:
        texts = [max(w, text_w(h)) for w, h in zip(texts, first["col_names"])]
    widths = [max(MIN_COL, w + 0.14) for w in texts]
    names = (max(text_w(n) for n in first["row_names"]) + 0.16) if first["row_names"] else 0.0
    head = HEAD_H if first["col_names"] else 0.0
    return widths, names, head, ROW_H * len(first["values"])


def _grid_width(views):
    widths, names, _head, _body = _grid_size(views)
    return sum(widths) + names + (2 * BRACKET + 0.1 if views[0]["matrix"] else 0.0)


def transpose(view: dict) -> dict:
    """A table on its side: row r, column c drawn at row c, column r (its names swap too)."""
    return {**view, "values": [list(col) for col in zip(*view["values"])], "row_names": view["col_names"],
            "col_names": view["row_names"], "marks": {f"{k.split(',')[1]},{k.split(',')[0]}": s
                                                      for k, s in view["marks"].items()}}


def _turned(views: list[dict], width: float) -> list[dict]:
    """The table as drawn: on its side when it is too wide for the frame across but not on its side (the frame is
    tall: runs/p5's 7-column DP table was 4.6 units wide and 3.8 fit)."""
    if _grid_width(views) <= width - 0.1 or views[0]["matrix"]:
        return views
    turned = [transpose(v) for v in views]
    return turned if _grid_width(turned) < _grid_width(views) else views


def grid_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    views = _turned(views, width)
    _widths, _names, head, body = _grid_size(views)
    k = max(1.0, min(MAX_GROW, (width - 0.1) / _grid_width(views)))
    return title + head + body + 0.08, title + (head + body) * k + 0.08


def grid_layout(views: list[dict], region) -> GridLayout:
    title = _title(views)
    turned = _turned(views, region.w)
    transposed = turned is not views
    views = turned
    widths, names, head, body = _grid_size(views)
    total = _grid_width(views)
    room_h = region.h - title - 0.08
    k = min(MAX_GROW, (region.w - 0.1) / total, room_h / (head + body))
    if k < 1 - 1e-9:
        if (region.w - 0.1) / total < 1:
            raise PictureError(f"the table is {total:.1f} units wide and {region.w:.1f} fit: use shorter entries "
                               "or fewer columns")
        raise PictureError(f"the table needs {head + body:.1f} units of height and gets {room_h:.1f}: use fewer rows")
    w = [x * k for x in widths]
    cx = region.cx + (names * k) / 2  # the body centred with its row names
    left = cx - sum(w) / 2
    xs = list(np.cumsum([0.0] + w[:-1]) + np.array(w) / 2 + left)
    top = region.top - title - (room_h - (head + body) * k) / 2 - head * k
    h = ROW_H * k
    ys = [top - h * (i + 0.5) for i in range(len(views[0]["values"]))]
    return GridLayout(k, transposed, xs, w, ys, h, top + head * k / 2 if head else None,
                      left - names * k / 2 if names else None, left, left + sum(w), top, top - h * len(ys))


# ---- flow (labelled boxes and arrows) ----------------------------------------------------------------------

BOX_PAD_X = 0.18
BOX_PAD_Y = 0.1
LINE_H = 0.32  # a line of text in a box
ICON_H = 0.42  # the pictogram left of an icon box's text
LAYER_GAP = 0.55  # between layers, room for an arrow and its label
MIN_LAYER_GAP = 0.36
MAX_LAYER_GAP = 1.1
SLOT_GAP = 0.3  # between boxes in one layer
ICON_SHAPES = ("person", "chip", "monitor", "lock", "server")
LOOP_R = 0.16


def box_size(text: str, shape: str, k: float = 1.0) -> tuple[float, float]:
    lines = text.split("\n") if text else [""]
    w = max(text_w(line, k) for line in lines) + 2 * BOX_PAD_X * k
    h = LINE_H * k * len(lines) + 2 * BOX_PAD_Y * k
    if shape == "diamond":  # the text sits in the middle half
        w, h = w * 1.55, h * 1.55
    elif shape == "circle" or shape == "double":
        d = max(w, h) * (1.12 if shape == "double" else 1.0)
        w = h = d
    elif shape == "cylinder":
        h += 0.2 * k
    elif shape == "document":
        h += 0.1 * k
    elif shape == "cloud":
        w, h = w * 1.25, h * 1.35
    elif shape in ICON_SHAPES:  # the pictogram left of the text: the frame is tall, so height is what's scarce
        w += (ICON_H + 0.1) * k
        h = max(h, (ICON_H + 2 * BOX_PAD_Y) * k)
    return max(w, 0.5 * k), max(h, 0.46 * k)


@dataclass
class FlowLayout:
    k: float
    boxes: dict[str, tuple[np.ndarray, float, float]]  # key: (centre, width, height)
    arrows: dict[str, list[np.ndarray]]  # "a>b": the polyline from a's border to b's
    labels: dict[tuple[str, str], np.ndarray]
    dropped: list = field(default_factory=list)
    loops: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)  # "a>a": (centre, out direction)


def _union(views: list[dict]):
    boxes: dict[str, dict] = {}
    arrows: list[tuple[str, str]] = []
    for v in views:
        for k, b in v["boxes"].items():
            old = boxes.get(k)
            # the largest text a box ever shows decides its size, so it doesn't change size between steps
            if old is None or len(b["text"]) > len(old["text"]):
                boxes[k] = b
        for a, b, *_ in v["arrows"]:
            if (a, b) not in arrows:
                arrows.append((a, b))
    return boxes, arrows


def _ranks(keys: list[str], arrows: list[tuple[str, str]], fixed: dict[str, int]) -> dict[str, int]:
    """Each box's layer: the longest path to it from a box nothing points to, along arrows that don't close a cycle
    (a depth-first search from the boxes in program order finds those); a box given a layer keeps it."""
    out_of: dict[str, list[str]] = {k: [] for k in keys}
    for a, b in arrows:
        if a != b:
            out_of[a].append(b)
    state: dict[str, int] = {}
    forward: list[tuple[str, str]] = []

    def visit(k: str) -> None:
        state[k] = 1
        for b in out_of[k]:
            if state.get(b) == 1:
                continue  # a back arrow: it closes a cycle
            forward.append((k, b))
            if b not in state:
                visit(b)
        state[k] = 2

    for k in keys:
        if k not in state:
            visit(k)
    rank = {k: 0 for k in keys}
    for _ in range(len(keys)):
        changed = False
        for a, b in forward:
            if rank[b] < rank[a] + 1 and b not in fixed:
                rank[b] = rank[a] + 1
                changed = True
        if not changed:
            break
    rank.update(fixed)
    used = sorted(set(rank.values()))
    return {k: used.index(r) for k, r in rank.items()}  # no empty layers


def flow_order(keys: list[str], arrows, rank: dict[str, int]) -> list[list[str]]:
    """The boxes of each layer, ordered to keep arrows short and uncrossed: by the mean position of their
    neighbours, a few sweeps down and up (the barycentre method)."""
    layers = [[k for k in keys if rank[k] == r] for r in range(max(rank.values()) + 1)]
    nbrs: dict[str, list[str]] = {k: [] for k in keys}
    for a, b in arrows:
        if a != b:
            nbrs[a].append(b)
            nbrs[b].append(a)
    for sweep in range(8):
        rng = range(1, len(layers)) if sweep % 2 == 0 else range(len(layers) - 2, -1, -1)
        for i in rng:
            ref = {k: j / max(1, len(layers[i + (-1 if sweep % 2 == 0 else 1)]) - 1)
                   for j, k in enumerate(layers[i + (-1 if sweep % 2 == 0 else 1)])}
            cur = {k: j / max(1, len(layers[i]) - 1) for j, k in enumerate(layers[i])}

            def bary(k):
                ns = [ref[n] for n in nbrs[k] if n in ref]
                return (sum(ns) / len(ns)) if ns else cur[k]

            layers[i] = sorted(layers[i], key=lambda k: (bary(k), cur[k]))
    return layers


DUMMY = 0.26  # the room an arrow takes through a layer it passes


def _chains(keys, arrows, rank):
    """An arrow that skips layers passes each one between at a slot of its own (a dummy box, as layered drawings
    route long edges), so it runs between the boxes, not through them. The ranks with the dummies, the arrows to
    order by, and each long arrow's dummies in order."""
    ranked = dict(rank)
    order: list[tuple[str, str]] = []
    chains: dict[tuple[str, str], list[str]] = {}
    for a, b in arrows:
        if a == b:
            continue
        ra, rb = rank[a], rank[b]
        if abs(ra - rb) <= 1:
            order.append((a, b))
            continue
        step = 1 if rb > ra else -1
        ds = [f"~{a}>{b}~{r}" for r in range(ra + step, rb, step)]
        for d, r in zip(ds, range(ra + step, rb, step)):
            ranked[d] = r
        chains[(a, b)] = ds
        chain = [a] + ds + [b]
        order += list(zip(chain, chain[1:]))
    return ranked, order, chains


def _rect_hit(p, q, c, w, h, margin=0.04) -> bool:
    from animation_agent.scene.math_layout import seg_hits_box

    lo = (c[0] - w / 2 - margin, c[1] - h / 2 - margin)
    hi = (c[0] + w / 2 + margin, c[1] + h / 2 + margin)
    return seg_hits_box(p, q, lo, hi)


def border_point(c: np.ndarray, w: float, h: float, toward: np.ndarray, shape: str = "box") -> np.ndarray:
    """Where the line from a box's centre toward a point leaves the box."""
    d = toward[:2] - c[:2]
    n = float(np.hypot(*d)) or 1e-9
    d = d / n
    if shape in ("circle", "double"):
        return c[:2] + d * (w / 2)
    if shape == "diamond":
        t = 1 / (abs(d[0]) / (w / 2) + abs(d[1]) / (h / 2))
        return c[:2] + d * t
    tx = (w / 2) / abs(d[0]) if abs(d[0]) > 1e-9 else np.inf
    ty = (h / 2) / abs(d[1]) if abs(d[1]) > 1e-9 else np.inf
    return c[:2] + d * min(tx, ty)


def flow_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    boxes, arrows = _union(views)
    fixed = {k: b["layer"] for k, b in boxes.items() if b.get("layer") is not None}
    rank = _ranks(list(boxes), arrows, fixed)
    across = views[0]["direction"] == "right"
    ranked, order, chains = _chains(list(boxes), arrows, rank)
    layers = flow_order(list(ranked), order, ranked)
    sizes = {k: box_size(b["text"], b["shape"]) for k, b in boxes.items()}
    sizes.update({d: (0.01, DUMMY) if across else (DUMMY, 0.01) for ds in chains.values() for d in ds})
    if across:  # layers left to right: the height is the tallest layer's, with room for labels and loops
        h = max(sum(sizes[k][1] for k in layer) + SLOT_GAP * (len(layer) - 1) for layer in layers)
        return title + h + 0.12, title + h * MAX_GROW + 1.4
    h = sum(max(sizes[k][1] for k in layer) for layer in layers) + MIN_LAYER_GAP * (len(layers) - 1)
    most = sum(max(sizes[k][1] for k in layer) for layer in layers) * MAX_GROW + MAX_LAYER_GAP * (len(layers) - 1)
    return title + h + 0.12, title + most + 0.12


def flow_layout(views: list[dict], region) -> FlowLayout:
    title = _title(views)
    boxes, arrows = _union(views)
    if not boxes:
        raise PictureError("the flow diagram has no boxes")
    keys = list(boxes)
    fixed = {k: b["layer"] for k, b in boxes.items() if b.get("layer") is not None}
    rank = _ranks(keys, arrows, fixed)
    ranked, order, chains = _chains(keys, arrows, rank)
    layers = flow_order(list(ranked), order, ranked)
    across = views[0]["direction"] == "right"
    dummies = [d for ds in chains.values() for d in ds]
    room_w, room_h = region.w - 0.1, region.h - title - 0.1
    labelled = {}
    for v in views:
        for a, b, _s, label in v["arrows"]:
            if label:
                labelled[(a, b)] = label
    loops = [(a, b) for a, b in arrows if a == b]

    def attempt(k: float, gap: float) -> FlowLayout | str:
        sizes = {key: box_size(boxes[key]["text"], boxes[key]["shape"], k) for key in keys}
        sizes.update({d: (0.01, DUMMY) if across else (DUMMY, 0.01) for d in dummies})
        # the main axis runs through the layers; the cross axis through the boxes of a layer
        main = [max(sizes[key][1 if not across else 0] for key in layer) for layer in layers]
        span = sum(main) + gap * (len(layers) - 1)
        cross = [sum(sizes[key][0 if not across else 1] for key in layer) + SLOT_GAP * k * (len(layer) - 1)
                 for layer in layers]
        if (span > (room_h if not across else room_w) + 1e-9
                or max(cross) > (room_w if not across else room_h) + 1e-9):
            return (f"the boxes need {max(cross) if not across else span:.1f} by "
                    f"{span if not across else max(cross):.1f} units and get {room_w:.1f} by {room_h:.1f}")
        centre_y = region.top - title - 0.05 - room_h / 2
        pos: dict[str, np.ndarray] = {}
        at = -span / 2
        for layer, m in zip(layers, main):
            along = at + m / 2
            total = sum(sizes[key][0 if not across else 1] for key in layer)
            free = (room_w if not across else room_h) - total
            # boxes of a layer spread over the room, but no further apart than a box's width or so
            spacing = min(free / (len(layer) - 1), 0.9 * k) if len(layer) > 1 else 0.0
            spread = total + spacing * (len(layer) - 1)
            c = -spread / 2
            for key in layer:
                s = sizes[key][0 if not across else 1]
                if not across:
                    pos[key] = np.array([region.cx + c + s / 2, centre_y + span / 2 - (along + span / 2)])
                else:
                    pos[key] = np.array([region.cx - span / 2 + (along + span / 2), centre_y + spread / 2 - c - s / 2])
                c += s + spacing
            at += m + gap
        out: dict[str, list[np.ndarray]] = {}
        present = set(arrows)
        for a, b in arrows:
            if a == b:
                continue
            ca, cb = pos[a], pos[b]
            side = np.zeros(2)
            if (b, a) in present:  # both ways: each to its own side
                d = (cb - ca) / (float(np.hypot(*(cb - ca))) or 1e-9)
                side = np.array([d[1], -d[0]]) * 0.16 * k
            if (a, b) in chains:  # through its own slot in each layer it passes
                via = [pos[d] for d in chains[(a, b)]]
                path = [border_point(ca, *sizes[a], via[0], boxes[a]["shape"]), *via,
                        border_point(cb, *sizes[b], via[-1], boxes[b]["shape"])]
            else:
                path = [border_point(ca + side, *sizes[a], cb + side, boxes[a]["shape"]),
                        border_point(cb + side, *sizes[b], ca + side, boxes[b]["shape"])]
            blocked = [key for key in keys if key not in (a, b) and any(
                _rect_hit(p, q, pos[key], *sizes[key]) for p, q in zip(path, path[1:]))]
            if blocked:
                # round the boxes in the way: bend at the side of the layers between, where there is room
                bent = _bend(ca, cb, a, b, pos, sizes, region, title, across, boxes)
                if bent is None:
                    return f"the arrow {a} -> {b} can't pass the boxes between them"
                path = bent
            out[f"{a}>{b}"] = path
        loop_spots = {}
        for a, _b in loops:
            c, (w, h) = pos[a], sizes[a]
            spot = None
            for d in (np.array([1.0, 0.0]), np.array([-1.0, 0.0]), np.array([0.0, 1.0]), np.array([0.0, -1.0])):
                reach = abs(d[0]) * w / 2 + abs(d[1]) * h / 2
                centre = c + d * (reach + LOOP_R * 0.8)
                lo, hi = centre - LOOP_R - 0.05, centre + LOOP_R + 0.05
                if lo[0] < region.cx - region.w / 2 or hi[0] > region.cx + region.w / 2:
                    continue
                if lo[1] < region.bottom or hi[1] > region.top - title:
                    continue
                if any(key != a and _rect_hit(lo, hi, pos[key], *sizes[key], margin=0.0) for key in keys):
                    continue
                from animation_agent.scene.math_layout import seg_hits_box

                if any(seg_hits_box(p, q, lo, hi) for path in out.values() for p, q in zip(path, path[1:])):
                    continue
                spot = (centre, d)
                break
            if spot is None:
                return f"the loop on {a} has no room beside it"
            loop_spots[f"{a}>{a}"] = spot
        # no two boxes may crowd, and no arrow may run along another
        for i, x in enumerate(keys):
            for y in keys[i + 1:]:
                gap_x = abs(pos[x][0] - pos[y][0]) - (sizes[x][0] + sizes[y][0]) / 2
                gap_y = abs(pos[x][1] - pos[y][1]) - (sizes[x][1] + sizes[y][1]) / 2
                if max(gap_x, gap_y) < 0.12:
                    return "two boxes crowd each other"
        lay = FlowLayout(k, {key: (pos[key], *sizes[key]) for key in keys}, out, {}, loops=loop_spots)
        lay.labels = _flow_labels(views, lay, labelled, region, title, lay.dropped)
        return lay

    # largest first; a layout that drops a label is kept only if none drops fewer
    best, why = None, []
    room_main = room_h if not across else room_w
    for k in (MAX_GROW, 1.25, 1.1, 1.0):
        sized = {key: box_size(boxes[key]["text"], boxes[key]["shape"], k) for key in keys}
        used = sum(max([sized[key][1 if not across else 0] for key in layer if key in sized] or [0.01])
                   for layer in layers)
        # the layers as far apart as the room allows (labels sit in the gaps), then closer
        widest = (room_main - used) / max(1, len(layers) - 1)
        gaps = [g for g in (min(MAX_LAYER_GAP * k, widest), LAYER_GAP * k, MIN_LAYER_GAP) if g >= MIN_LAYER_GAP - 1e-9]
        for gap in dict.fromkeys(gaps or [MIN_LAYER_GAP]):
            got = attempt(k, gap)
            if isinstance(got, FlowLayout):
                if not got.dropped:
                    return got
                if best is None or len(got.dropped) < len(best.dropped):
                    best = got
            else:
                why.append(got)
    if best is not None:
        return best
    raise PictureError(f"the flow diagram can't be drawn clearly: {why[-1]}; use fewer boxes or shorter text")


def _bend(ca, cb, a, b, pos, sizes, region, title, across, boxes):
    """A path from a to b round the boxes between them: out of a, along a free lane at the side, into b."""
    x0, x1 = region.cx - region.w / 2 + 0.08, region.cx + region.w / 2 - 0.08
    y0, y1 = region.bottom + 0.08, region.top - title - 0.08
    others = [k for k in pos if k not in (a, b)]
    lanes = []
    if not across:
        for side in (1, -1):
            for f in (0.0, 0.15, 0.3):
                edge = max(pos[k][0] + side * sizes[k][0] / 2 for k in pos) if side > 0 else \
                    min(pos[k][0] - sizes[k][0] / 2 for k in pos)
                lanes.append(edge + side * (0.16 + f))
        for lane in sorted(lanes, key=lambda x: abs(x - (ca[0] + cb[0]) / 2)):
            if not x0 <= lane <= x1:
                continue
            p = border_point(ca, *sizes[a], np.array([lane, ca[1]]), boxes[a]["shape"])
            q = border_point(cb, *sizes[b], np.array([lane, cb[1]]), boxes[b]["shape"])
            path = [p, np.array([lane, p[1]]), np.array([lane, q[1]]), q]
            if not any(_rect_hit(s, t, pos[k], *sizes[k]) for k in others for s, t in zip(path, path[1:])):
                return path
    else:
        for side in (1, -1):
            for f in (0.0, 0.15, 0.3):
                edge = max(pos[k][1] + sizes[k][1] / 2 for k in pos) if side > 0 else \
                    min(pos[k][1] - sizes[k][1] / 2 for k in pos)
                lanes.append(edge + side * (0.16 + f))
        for lane in sorted(lanes, key=lambda y: abs(y - (ca[1] + cb[1]) / 2)):
            if not y0 <= lane <= y1:
                continue
            p = border_point(ca, *sizes[a], np.array([ca[0], lane]), boxes[a]["shape"])
            q = border_point(cb, *sizes[b], np.array([cb[0], lane]), boxes[b]["shape"])
            path = [p, np.array([p[0], lane]), np.array([q[0], lane]), q]
            if not any(_rect_hit(s, t, pos[k], *sizes[k]) for k in others for s, t in zip(path, path[1:])):
                return path
    return None


def _along(path, f):
    """The point a fraction f along a polyline, and the direction there."""
    lengths = [float(np.hypot(*(q - p))) for p, q in zip(path, path[1:])]
    total = sum(lengths) or 1e-9
    at = f * total
    for (p, q), L in zip(zip(path, path[1:]), lengths):
        if at <= L or L == lengths[-1]:
            t = at / (L or 1e-9)
            return p + (q - p) * min(t, 1.0), (q - p) / (L or 1e-9)
        at -= L
    return path[-1], (path[-1] - path[-2]) / (float(np.hypot(*(path[-1] - path[-2]))) or 1e-9)


def _path_dist(path, c) -> float:
    """How far point c is from a polyline."""
    best = np.inf
    for p, q in zip(path, path[1:]):
        p, q = np.asarray(p, float)[:2], np.asarray(q, float)[:2]
        d = q - p
        t = float(np.clip((c[:2] - p) @ d / (float(d @ d) or 1e-9), 0, 1))
        best = min(best, float(np.hypot(*(p + t * d - c[:2]))))
    return best


def _flow_labels(views, lay: FlowLayout, labelled, region, title, dropped) -> dict:
    base = Obstacles()
    for c, w, h in lay.boxes.values():
        x0, x1, y0, y1 = c[0] - w / 2 - 0.02, c[0] + w / 2 + 0.02, c[1] - h / 2 - 0.02, c[1] + h / 2 + 0.02
        base.add_polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
        base.boxes.append((np.array(c[:2], dtype=float), np.array([w / 2, h / 2])))  # nor inside it
    for key, (c, d) in lay.loops.items():
        base.discs.append((tuple(c), LOOP_R + 0.12))  # the arc and its arrowhead
    for key, path in lay.arrows.items():
        base.add_polyline([tuple(p) for p in path])
    requests = []
    for (a, b), text in labelled.items():
        half = text_half(text)
        shown = {i for i, v in enumerate(views) if any(x == a and y == b and lab for x, y, _s, lab in v["arrows"])}
        cands = []
        if a == b:
            c, d = lay.loops[f"{a}>{a}"]
            for extra in (0.04, 0.14, 0.26):
                reach = abs(d[0]) * half[0] + abs(d[1]) * half[1]
                cands.append(c + d * (LOOP_R + reach + extra))
            normal = np.array([-d[1], d[0]])
            cands += [c + normal * (LOOP_R + abs(normal[0]) * half[0] + abs(normal[1]) * half[1] + 0.05) * s
                      for s in (1, -1)]
        else:
            path = lay.arrows[f"{a}>{b}"]
            for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
                p, d = _along(path, f)
                normal = np.array([-d[1], d[0]])
                reach = abs(normal[0]) * half[0] + abs(normal[1]) * half[1]
                for extra in (0.05, 0.15, 0.3):
                    for s in (1, -1):
                        cands.append(p + normal * s * (reach + extra))
            for f in (0.5, 0.35, 0.65):  # straight left or right of it (a steep arrow), above or below (a flat one)
                p, d = _along(path, f)
                slope = abs(d[0] / d[1]) if abs(d[1]) > 1e-9 else np.inf
                for extra in (0.06, 0.2, 0.4):
                    if slope < 3:
                        dx = half[0] + min(slope, 2.0) * half[1] + extra
                        cands += [p + np.array([dx, 0.0]), p - np.array([dx, 0.0])]
                    if slope > 1 / 3:
                        dy = half[1] + (min(1 / slope, 2.0) if slope < np.inf else 0.0) * half[0] + extra
                        cands += [p + np.array([0.0, dy]), p - np.array([0.0, dy])]
        if a != b:
            # a label reads as its own arrow's only if no other arrow is nearer to it (as a graph's link labels)
            own = lay.arrows[f"{a}>{b}"]
            others = [p for key, p in lay.arrows.items() if key != f"{a}>{b}"]
            near = max(half) + 0.3  # and close enough to it to read as its label at all
            cands = [c for c in cands if _path_dist(own, c) <= near
                     and all(_path_dist(o, c) > _path_dist(own, c) + 0.05 for o in others)]
        requests.append(Request((f"{a}>{b}", text), text, cands, base, shown))
    return place(requests, (region.cx - region.w / 2, region.cx + region.w / 2, region.bottom, region.top - title),
                 "the flow diagram", dropped=dropped, exact=True)


# ---- timeline ----------------------------------------------------------------------------------------------

LANE_H = 0.52
BLOCK_H = 0.4
MARK_ROOM = TEXT_H + 0.12  # above the lanes, for markers' labels


def _t_range(views: list[dict]) -> tuple[float, float]:
    first = views[0]
    if first["t"] is not None:
        return float(first["t"][0]), float(first["t"][1])
    ts = [x for v in views for it in v["items"].values() for x in ((it["a"], it["b"]) if it["type"] == "block"
                                                                       else (it["t"],))]
    if not ts:
        return 0.0, 10.0
    lo, hi = min(0.0, min(ts)), max(ts)
    return lo, hi if hi > lo else lo + 1


@dataclass
class TimelineLayout:
    x0: float  # the time axis on screen
    x1: float
    t: tuple[float, float]
    lane_y: list[float]  # each lane's centre
    lane_h: float
    name_x: float  # the lane names' right edge
    axis_y: float
    ticks: list[tuple[float, str, np.ndarray]]
    mark_y: float  # markers' labels' centre
    top: float  # the top of the first lane
    shown_labels: set = field(default_factory=set)  # (key, label) of the block labels that fit inside their block
    mark_spots: dict = field(default_factory=dict)  # a marker's label centre, by (key, label)
    dropped: list = field(default_factory=list)

    def at(self, t: float) -> float:
        return self.x0 + (t - self.t[0]) / (self.t[1] - self.t[0]) * (self.x1 - self.x0)


def _marked(views) -> int:
    """The rows markers' labels need above the lanes: two when a snapshot labels more than one."""
    most = max((sum(1 for it in v["items"].values() if it["type"] == "marker" and it.get("label")) for v in views),
               default=0)
    return min(2, most)


def timeline_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    n = len(views[0]["lanes"])
    extra = MARK_ROOM * _marked(views) + 0.1 + TEXT_H + 0.12
    return title + n * LANE_H + extra, title + n * LANE_H * 1.6 + extra


def timeline_layout(views: list[dict], region) -> TimelineLayout:
    from animation_agent.scene.math_layout import nice_ticks, tick_text

    title = _title(views)
    first = views[0]
    n = len(first["lanes"])
    names = max(text_w(x) for x in first["lanes"]) + 0.14
    x0, x1 = region.cx - region.w / 2 + names + 0.08, region.cx + region.w / 2 - 0.2
    if x1 - x0 < 1.6:
        raise PictureError("the lanes' names leave the timeline too little room; use shorter names")
    marks = MARK_ROOM * _marked(views)
    axis = 0.1 + TEXT_H + 0.12
    room = region.h - title - marks - axis
    lane_h = min(LANE_H * 1.6, room / n)
    if lane_h < LANE_H - 1e-9:
        raise PictureError(f"{n} lanes need {n * LANE_H:.1f} units of height and get {room:.1f}")
    used = lane_h * n
    top = region.top - title - marks - (room - used) / 2
    t = _t_range(views)
    lay = TimelineLayout(x0, x1, t, [top - lane_h * (i + 0.5) for i in range(n)], lane_h, x0 - 0.1, top - used,
                         [], top + MARK_ROOM / 2 + 0.02, top)
    values = ([t[0] + k * first["step"] for k in range(int(round((t[1] - t[0]) / first["step"])) + 1)]
              if first["step"] else nice_ticks(*t, 7))
    ticks = [(v, tick_text(v), np.array([lay.at(v), lay.axis_y - 0.1 - TEXT_H / 2])) for v in values
             if t[0] - 1e-9 <= v <= t[1] + 1e-9]
    while len(ticks) > 2 and any(np.all(np.abs(a[2] - b[2]) < text_half(a[1]) + text_half(b[1]))
                                 for a, b in zip(ticks, ticks[1:])):
        ticks = ticks[::2]
    lay.ticks = ticks
    for v in views:
        for key, it in v["items"].items():
            if it["type"] == "block" and it.get("label"):
                w = lay.at(it["b"]) - lay.at(it["a"])
                if text_w(it["label"]) + 0.08 <= w:
                    lay.shown_labels.add((key, it["label"]))
                elif it["label"] not in lay.dropped:
                    lay.dropped.append(it["label"])
    # markers' labels above the lanes may not touch each other
    for v in views:
        placed = []
        for key, it in sorted(v["items"].items(), key=lambda kv: kv[1].get("t", 0)):
            if it["type"] != "marker" or not it.get("label"):
                continue
            half = text_half(it["label"])
            x = min(max(lay.at(it["t"]), region.cx - region.w / 2 + half[0]), region.cx + region.w / 2 - half[0])
            spot = None
            for row in range(_marked(views)):  # the lower row first, the upper if that one is taken
                c = np.array([x, lay.mark_y + row * MARK_ROOM])
                if not any(abs(c[0] - c2[0]) < half[0] + h2[0] + 0.04 and abs(c[1] - c2[1]) < 1e-6
                           for c2, h2 in placed):
                    spot = c
                    break
            if spot is None:
                if it["label"] not in lay.dropped:
                    lay.dropped.append(it["label"])
                continue
            placed.append((spot, half))
            lay.mark_spots[(key, it["label"])] = spot
            lay.shown_labels.add((key, it["label"]))
    return lay


# ---- sequence (messages between actors) --------------------------------------------------------------------

ACTOR_H = 0.48
MSG_ROW = 0.5  # a message's row: its label above its arrow
MAX_MSG_ROW = 0.8


@dataclass
class SequenceLayout:
    x: list[float]  # each actor's lifeline
    box_w: float
    top: float  # the actor boxes' top
    rows: dict[int, float]  # each message row's arrow height
    bottom: float  # where the lifelines end
    labels: dict[str, np.ndarray]  # a message's label centre, by key
    self_w: float = 0.36  # how far a message to itself loops out
    dropped: list = field(default_factory=list)
    gaps: dict = field(default_factory=dict)  # each lifeline's breaks round the labels it would cross: [(y0, y1)]


def _rows(views) -> list[int]:
    return sorted({m["row"] for v in views for m in v["messages"].values()})


def sequence_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    rows = max(1, len(_rows(views)))
    return title + ACTOR_H + 0.15 + rows * MSG_ROW + 0.1, title + ACTOR_H + 0.15 + rows * MAX_MSG_ROW + 0.1


def sequence_layout(views: list[dict], region) -> SequenceLayout:
    title = _title(views)
    actors = views[0]["actors"]
    n = len(actors)
    # boxes as wide as the longest name, the outer two at the edges, so the messages between have the most room
    box_w = max(text_w(a) for a in actors) + 0.24
    span = region.w - 0.1 - box_w
    if n * box_w + (n - 1) * 0.16 > region.w - 0.1:
        raise PictureError(f"{n} actors' names need {n * box_w + (n - 1) * 0.16:.1f} units across and "
                           f"{region.w - 0.1:.1f} fit: use shorter names or fewer actors")
    xs = [region.cx - span / 2 + span * i / (n - 1) for i in range(n)]
    rows = _rows(views)
    room = region.h - title - ACTOR_H - 0.15 - 0.1
    row_h = min(MAX_MSG_ROW, room / max(1, len(rows)))
    if row_h < MSG_ROW - 1e-9:
        raise PictureError(f"{len(rows)} messages need {len(rows) * MSG_ROW:.1f} units of height and get {room:.1f}")
    top = region.top - title - (room - row_h * len(rows)) / 2
    first_row = top - ACTOR_H - 0.15
    ys = {r: first_row - row_h * (i + 0.5) - (TEXT_H / 2 - 0.02) for i, r in enumerate(rows)}
    lay = SequenceLayout(xs, box_w, top, ys, first_row - row_h * len(rows), {})
    x_lo, x_hi = region.cx - region.w / 2, region.cx + region.w / 2
    for v in views:
        for key, m in v["messages"].items():
            if not m.get("label") or key in lay.labels:
                continue
            half = text_half(m["label"])
            a, b = xs[m["a"]], xs[m["b"]]
            if m["a"] == m["b"]:  # beside the loop
                c = np.array([a + lay.self_w + 0.08 + half[0], ys[m["row"]] - 0.12])
                if a + lay.self_w + 0.08 + 2 * half[0] > x_hi:  # no room right of the loop: above it
                    c = np.array([min(max(a, x_lo + half[0]), x_hi - half[0]), ys[m["row"]] + 0.18 + half[1]])
            else:
                # centred over its arrow, inside the frame; a lifeline it covers is drawn with a gap round it
                c = np.array([min(max((a + b) / 2, x_lo + half[0]), x_hi - half[0]), ys[m["row"]] + 0.06 + half[1]])
            if 2 * half[0] > region.w:
                if m["label"] not in lay.dropped:
                    lay.dropped.append(m["label"])
                continue
            lay.labels[key] = c
            for i, x in enumerate(xs):
                if c[0] - half[0] - 0.04 < x < c[0] + half[0] + 0.04:
                    lay.gaps.setdefault(i, []).append((c[1] - half[1] - 0.03, c[1] + half[1] + 0.03))
    return lay


# ---- circuit (drawn top to bottom: the portrait frame is tall, not wide) ----------------------------------

GATE_LEN = 0.44  # a gate along the signal (down the frame)
PIN = 0.06  # the stubs into and out of a gate
TERM = 0.36  # an input's or output's value box
NAME_H = TEXT_H + 0.04  # an input's name above its box, an output's below
MIN_WIRE_GAP = 0.22  # between two levels, for the wires' turns
CHANNEL_GAP = 0.08  # between two wires turning in one gap
MAX_WIRE_GAP = 0.7
PART_GAP = 0.34  # between two parts side by side
DUMMY_W = 0.16  # a wire passing a level


def gate_wid(n_inputs: int) -> float:
    return max(0.56, 0.22 * n_inputs + 0.16)


@dataclass
class CircuitLayout:
    pos: dict[str, np.ndarray]  # each part's centre
    size: dict[str, tuple[float, float]]  # width, height on screen
    wires: dict[str, list[tuple[float, float]]]  # "src>dst#i": the polyline, from the source's pin to the input
    names: dict[str, np.ndarray]  # an input's or output's name


def _depths(parts: dict) -> dict[str, int]:
    depth: dict[str, int] = {}
    for k, p in parts.items():
        if p["type"] == "input":
            depth[k] = 0
        elif p["type"] == "gate":
            depth[k] = 1 + max(depth[i] for i in p["inputs"])
    last = max(depth.values(), default=0) + 1
    for k, p in parts.items():
        if p["type"] == "output":
            depth[k] = last
    return depth


def _turns(parts, depth) -> dict[int, list[str]]:
    """The sources whose wires turn in each gap between levels (each gets a channel of its own there)."""
    users: dict[int, list[str]] = {}
    for k, p in parts.items():
        for src in p.get("inputs", []):
            for d in range(depth[src], depth[k]):
                users.setdefault(d, [])
                if src not in users[d]:
                    users[d].append(src)
    return users


def _gap_need(n: int) -> float:
    return max(MIN_WIRE_GAP, 0.06 + CHANNEL_GAP * (n + 1))


def _level_lens(parts, depth) -> list[float]:
    levels = max(depth.values()) + 1
    return [TERM + NAME_H if d in (0, levels - 1) else GATE_LEN + 2 * PIN for d in range(levels)]


def circuit_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    parts = views[-1]["parts"]
    depth = _depths(parts)
    lens = _level_lens(parts, depth)
    users = _turns(parts, depth)
    need = [_gap_need(len(users.get(d, []))) for d in range(len(lens) - 1)]
    return title + sum(lens) + sum(need) + 0.12, title + sum(lens) + sum(max(g, MAX_WIRE_GAP) for g in need) + 0.12


def _port(pos, size, parts, key, j=None) -> tuple[float, float]:
    c, (w, h) = pos[key], size[key]
    pin = PIN if parts[key]["type"] == "gate" else 0.0
    if j is None:  # the output, at the bottom
        return (float(c[0]), float(c[1] - h / 2 - pin))
    n = len(parts[key]["inputs"])
    span = w - 0.2
    return (float(c[0] - span / 2 + span * j / (n - 1)) if n > 1 else float(c[0]), float(c[1] + h / 2 + pin))


def circuit_layout(views: list[dict], region) -> CircuitLayout:
    from animation_agent.scene.math_layout import seg_hits_box

    title = _title(views)
    parts = views[-1]["parts"]
    for v in views:  # the last snapshot has every part; a part may not be removed
        if set(v["parts"]) - set(parts):
            raise PictureError("a circuit keeps its parts once made (set the inputs to show a change)")
    if not any(p["type"] == "input" for p in parts.values()) or len(parts) < 2:
        raise PictureError("a circuit needs inputs and a gate or output")
    depth = _depths(parts)
    lens = _level_lens(parts, depth)
    users = _turns(parts, depth)
    need = [_gap_need(len(users.get(d, []))) for d in range(len(lens) - 1)]
    room = region.h - title - 0.12
    spare = room - sum(lens) - sum(need)
    if spare < -1e-9:
        raise PictureError(f"the circuit is {len(lens)} levels deep (inputs, gates, outputs) and needs "
                           f"{sum(lens) + sum(need):.1f} units of height; it gets {room:.1f}: use fewer levels of "
                           "gates or fewer wires")
    gaps = [min(g + spare / max(1, len(need)), max(g, MAX_WIRE_GAP)) for g in need]
    total = sum(lens) + sum(gaps)
    y = region.top - title - 0.06 - (room - total) / 2
    centre_y = []  # an input's name sits above its box, an output's below
    for d, L in enumerate(lens):
        centre_y.append(y - NAME_H - TERM / 2 if d == 0 else y - TERM / 2 if d == len(lens) - 1 else y - L / 2)
        y -= L + (gaps[d] if d < len(gaps) else 0.0)
    size = {k: ((gate_wid(len(p["inputs"])), GATE_LEN) if p["type"] == "gate" else (TERM, TERM))
            for k, p in parts.items()}
    # a wire that skips a level passes it at a slot of its own (one per source and level, a dummy part, as
    # layered drawings route long edges), so it runs between the parts there, not through them
    passing: dict[int, list[str]] = {}
    for k, p in parts.items():
        for src in p.get("inputs", []):
            for d in range(depth[src] + 1, depth[k]):
                passing.setdefault(d, [])
                if src not in passing[d]:
                    passing[d].append(src)
    levels = [[k for k in parts if depth[k] == d] + [f"~{src}~{d}" for src in passing.get(d, [])]
              for d in range(len(lens))]

    def wide(k: str) -> float:
        return DUMMY_W if k.startswith("~") else size[k][0]

    for d, level in enumerate(levels):
        need = sum(wide(k) for k in level) + PART_GAP * (len(level) - 1)
        if need > region.w - 0.1:
            raise PictureError(f"{len(level)} parts and wires side by side need {need:.1f} units and "
                               f"{region.w - 0.1:.1f} fit: use fewer gates in a level")
    # left to right in each level by where its inputs are (barycentre), so wires run mostly straight down
    x: dict[str, float] = {}
    for d, level in enumerate(levels):
        if d:
            def bary(k: str) -> float:
                ins = [k.split("~")[1]] if k.startswith("~") else parts[k]["inputs"]
                return sum(x[i] for i in ins) / len(ins)

            level.sort(key=bary)
        slot = (region.w - 0.1) / len(level)
        for j, k in enumerate(level):
            x[k] = region.cx - (region.w - 0.1) / 2 + slot * (j + 0.5)
    pos = {k: np.array([x[k], centre_y[depth[k]]]) for k in parts}
    names = {}
    for k, p in parts.items():
        if p["type"] == "input":
            names[k] = np.array([x[k], pos[k][1] + TERM / 2 + NAME_H / 2])
        elif p["type"] == "output":
            names[k] = np.array([x[k], pos[k][1] - TERM / 2 - NAME_H / 2])
    real = [[k for k in level if not k.startswith("~")] for level in levels]

    def gap_between(d: int) -> tuple[float, float]:
        above = min(_port(pos, size, parts, k)[1] for k in real[d])
        below = max(pos[k][1] + size[k][1] / 2 + (PIN if parts[k]["type"] == "gate" else 0) for k in real[d + 1])
        return below + 0.03, above - 0.03

    def clear(path, src, k) -> str | None:
        for other in parts:  # a wire may pass no part but its own two
            if other in (src, k):
                continue
            c, (w, h) = pos[other], size[other]
            pin = PIN if parts[other]["type"] == "gate" else 0.0
            lo = (c[0] - w / 2 - 0.04, c[1] - h / 2 - pin - 0.04)
            hi = (c[0] + w / 2 + 0.04, c[1] + h / 2 + pin + 0.04)
            if any(seg_hits_box(s, t, lo, hi) for s, t in zip(path, path[1:])):
                return other
            if other in names and any(seg_hits_box(s, t, names[other] - text_half(parts[other]["label"]),
                                                   names[other] + text_half(parts[other]["label"]))
                                      for s, t in zip(path, path[1:])):
                return other
        return None

    def ch(d: int, src: str) -> float:
        lo, hi = gap_between(d)
        return hi - (hi - lo) * (users[d].index(src) + 1) / (len(users[d]) + 1)

    wires = {}
    for k, p in parts.items():
        for j, src in enumerate(p.get("inputs", [])):
            a, b = _port(pos, size, parts, src), _port(pos, size, parts, k, j)
            path = [a]
            at = a[0]
            for d in range(depth[src], depth[k]):  # down to the channel, across to the next slot, down again
                nxt = x[f"~{src}~{d + 1}"] if d + 1 < depth[k] else b[0]
                path += [(at, ch(d, src)), (nxt, ch(d, src))]
                at = nxt
            path.append(b)
            if abs(a[0] - b[0]) < 1e-6 and depth[k] == depth[src] + 1:
                path = [a, b]
            path = [q for i, q in enumerate(path) if i == 0 or (abs(q[0] - path[i - 1][0]) > 1e-9
                                                              or abs(q[1] - path[i - 1][1]) > 1e-9)]
            if (other := clear(path, src, k)) is not None:
                raise PictureError(f"the wire from {src} to {k} would cross {other}; use fewer gates or levels")
            wires[f"{src}>{k}#{j}"] = path
    # two different wires may cross but never run along one another
    segs = [(key.split(">")[0], s, t) for key, path in wires.items() for s, t in zip(path, path[1:])]
    for i, (n1, s1, t1) in enumerate(segs):
        for n2, s2, t2 in segs[i + 1:]:
            if n1 == n2:
                continue
            for axis in (0, 1):  # both vertical (axis 0 constant) or both horizontal (axis 1 constant)
                if (abs(s1[axis] - t1[axis]) < 1e-6 and abs(s2[axis] - t2[axis]) < 1e-6
                        and abs(s1[axis] - s2[axis]) < 0.06):
                    o = 1 - axis
                    if min(max(s1[o], t1[o]), max(s2[o], t2[o])) - max(min(s1[o], t1[o]), min(s2[o], t2[o])) > 0.02:
                        raise PictureError(f"the wires from {n1} and {n2} would run along each other; use fewer "
                                           "gates")
    return CircuitLayout(pos, size, wires, names)


# ---- memory (stack frames and heap objects) ----------------------------------------------------------------

FIELD_H = 0.38
BOX_TITLE_H = 0.34
BOX_GAP = 0.14
CHANNEL = 0.12  # between two arrows' vertical runs
REF_DOT = 0.06


@dataclass
class MemoryLayout:
    boxes: dict[str, tuple[float, float, float, float]]  # key: left, top, width, height
    name_w: dict[str, float]  # each box's field-name column
    stack_right: float
    heap_left: float
    heap_right: float
    right_edge: float
    rows: dict[str, list[str]] = field(default_factory=dict)  # each box's fields, in the order first set


def _memory_union(views):
    order: list[str] = []
    boxes: dict[str, dict] = {}
    fields: dict[str, list[str]] = {}
    widths: dict[str, list[float]] = {}
    for v in views:
        for k, b in v["boxes"].items():
            if k not in boxes:
                order.append(k)
                boxes[k] = b
                fields[k], widths[k] = [], [text_w(b["title"]), 0.0, 0.0]
            for name, text, _ref, _s in b["fields"]:
                if name not in fields[k]:
                    fields[k].append(name)
                widths[k][1] = max(widths[k][1], text_w(name))
                widths[k][2] = max(widths[k][2], text_w(text))
    return order, boxes, fields, widths


def _arrows_most(views) -> tuple[int, int]:
    """The most stack-to-heap and heap-to-heap arrows any snapshot draws."""
    s = h = 0
    for v in views:
        a = sum(1 for b in v["boxes"].values() if b["area"] == "stack" for f in b["fields"] if f[2])
        c = sum(1 for b in v["boxes"].values() if b["area"] == "heap" for f in b["fields"] if f[2])
        s, h = max(s, a), max(h, c)
    return s, h


def _box_dims(widths) -> tuple[float, float]:
    title, name, value = widths
    name_w = max(name, CHAR) + 0.16
    value_w = max(0.5, value + 0.16)
    return max(name_w + value_w, title + 0.2), name_w


def memory_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    order, boxes, fields, _w = _memory_union(views)
    tall = {area: sum(BOX_TITLE_H + FIELD_H * max(1, len(fields[k])) + BOX_GAP for k in order
                      if boxes[k]["area"] == area) for area in ("stack", "heap")}
    h = max(tall.values()) + 0.1
    return title + h, title + h + 0.4


def memory_layout(views: list[dict], region) -> MemoryLayout:
    title = _title(views)
    order, boxes, fields, widths = _memory_union(views)
    to_heap, in_heap = _arrows_most(views)
    dims = {k: _box_dims(widths[k]) for k in order}
    stack_w = max([dims[k][0] for k in order if boxes[k]["area"] == "stack"], default=0.0)
    heap_w = max([dims[k][0] for k in order if boxes[k]["area"] == "heap"], default=0.0)
    middle = 0.3 + CHANNEL * max(0, to_heap - 1) if stack_w and heap_w else 0.0
    outer = 0.24 + CHANNEL * max(0, in_heap - 1) if in_heap else 0.0
    need = stack_w + middle + heap_w + outer
    if need > region.w - 0.05:
        raise PictureError(f"the memory diagram is {need:.1f} units wide and {region.w:.1f} fit: use shorter names "
                           "and values, or fewer pointers")
    left = region.cx - need / 2
    stack_right = left + stack_w
    heap_left = stack_right + middle
    heap_right = heap_left + heap_w
    out: dict[str, tuple[float, float, float, float]] = {}
    tall = {}
    for area in ("stack", "heap"):
        keys = [k for k in order if boxes[k]["area"] == area]
        tall[area] = sum(BOX_TITLE_H + FIELD_H * max(1, len(fields[k])) for k in keys) + BOX_GAP * (len(keys) - 1)
    room = region.h - title - 0.1
    if max(tall.values()) > room + 1e-9:
        raise PictureError(f"the memory diagram needs {max(tall.values()):.1f} units of height and gets {room:.1f}: "
                           "use fewer frames, objects or fields")
    for area, x, w in (("stack", left, stack_w), ("heap", heap_left, heap_w)):
        y = region.top - title - 0.05 - (room - tall[area]) / 2
        for k in [k for k in order if boxes[k]["area"] == area]:
            h = BOX_TITLE_H + FIELD_H * max(1, len(fields[k]))
            out[k] = (x, y, w, h)
            y -= h + BOX_GAP
    return MemoryLayout(out, {k: dims[k][1] for k in order}, stack_right, heap_left, heap_right, heap_right + outer,
                        fields)


def memory_rows(view: dict, lay: MemoryLayout, key: str) -> list[tuple[str, float]]:
    """A box's fields in this snapshot and the height of each one's row (rows keep their place across snapshots,
    in the order fields were first set)."""
    left, top, w, h = lay.boxes[key]
    present = {f[0] for f in view["boxes"][key]["fields"]}
    return [(name, top - BOX_TITLE_H - FIELD_H * (i + 0.5)) for i, name in enumerate(lay.rows[key]) if name in present]


def memory_arrows(view: dict, lay: MemoryLayout) -> dict[str, list[tuple[float, float]]]:
    """Each pointer's path, by "box.field": from a dot in the field's value cell to the object it points to. From
    the stack: right to its own channel between the columns, along it to the object's title row, right into the
    object. From the heap: right past the heap to its own channel, along it, left into the object's right side."""
    out = {}
    mid_n = out_n = 0
    for k, b in view["boxes"].items():
        for (name, y) in memory_rows(view, lay, k):
            f = next(f for f in b["fields"] if f[0] == name)
            if not f[2] or f[2] not in lay.boxes:
                continue
            left, top, w, _h = lay.boxes[k]
            vx = left + lay.name_w[k] + (w - lay.name_w[k]) / 2
            tl, ttop, tw, _th = lay.boxes[f[2]]
            ty = ttop - BOX_TITLE_H / 2
            if b["area"] == "stack":
                ch = lay.stack_right + 0.15 + CHANNEL * mid_n
                mid_n += 1
                out[f"{k}.{name}"] = [(vx, y), (ch, y), (ch, ty), (tl, ty)]
            else:
                ch = lay.heap_right + 0.15 + CHANNEL * out_n
                out_n += 1
                out[f"{k}.{name}"] = [(vx, y), (ch, y), (ch, ty), (tl + tw, ty)]
    return out
