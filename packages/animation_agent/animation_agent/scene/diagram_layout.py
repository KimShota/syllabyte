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
    window: int = 0  # rows shown at once when the table is too tall for its band (0: all of them)
    start: list = field(default_factory=list)  # each snapshot's first row shown

    @property
    def font(self) -> int:
        return round(30 * self.k)

    def row_y(self, r: int, snap: int) -> float:
        return self.y[r - (self.start[snap] if self.window else 0)]

    def shown(self, r: int, snap: int) -> bool:
        return not self.window or self.start[snap] <= r < self.start[snap] + self.window


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
                                                      for k, s in view["marks"].items()},
            "heat": None if not view.get("heat") else {f"{k.split(',')[1]},{k.split(',')[0]}": t
                                                        for k, t in view["heat"].items()}}


def _turned(views: list[dict], width: float) -> list[dict]:
    """The table as drawn: on its side when it is too wide for the frame across but not on its side (the frame is
    tall: runs/p5's 7-column DP table was 4.6 units wide and 3.8 fit). Never a picture of space: a square grid, a heat
    map, or one made with turn=False (runs/bench1-2: a plate's hot top edge and a pixel grid's rows were drawn as
    columns, against the slide)."""
    v = views[0]
    square = len(v["values"]) == len(v["values"][0])
    if (_grid_width(views) <= width - 0.1 or v["matrix"] or square or not v.get("turn", True)
            or any(w.get("heat") for w in views)):
        return views
    turned = [transpose(v) for v in views]
    return turned if _grid_width(turned) < _grid_width(views) else views


TABLE_EDGE = 0.04  # the least room a table leaves across its band (its outer lines are 0.02 thick)
GRID_WINDOW = 4  # rows a tall table shows at least, scrolling to its marked rows
GRID_MORE = 0.24  # above and below a scrolled table: room for the arrows that say more is there


def grid_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    views = _turned(views, width)
    _widths, _names, head, body = _grid_size(views)
    k = max(1.0, min(MAX_GROW, (width - 0.1) / _grid_width(views)))
    rows = len(views[0]["values"])
    least = body if rows <= GRID_WINDOW + 1 or views[0]["matrix"] else ROW_H * GRID_WINDOW + 2 * GRID_MORE
    return title + head + least + 0.08, title + (head + body) * k + 0.08


def grid_starts(views: list[dict], window: int) -> list[int]:
    """Each snapshot's first row shown: the window moves as little as it can to keep the marked rows in view."""
    out, s = [], 0
    for v in views:
        n = len(v["values"])
        rows = sorted({int(key.split(",")[0]) for key in v["marks"]})
        if rows:
            lo, hi = rows[0], rows[-1]
            if hi - lo + 1 > window or lo < s:
                s = lo
            elif hi >= s + window:
                s = hi - window + 1
        s = max(0, min(s, n - window))
        out.append(s)
    return out


def grid_layout(views: list[dict], region) -> GridLayout:
    title = _title(views)
    turned = _turned(views, region.w)
    transposed = turned is not views
    views = turned
    widths, names, head, body = _grid_size(views)
    total = _grid_width(views)
    room_h = region.h - title - 0.08
    # 0.1 to spare across, down to TABLE_EDGE when only the spare is in the way (runs/bench1: a 3-column stack
    # table was 3.71 units wide against 3.70 and was refused)
    room_w = region.w - 0.1 if total <= region.w - 0.1 else region.w - TABLE_EDGE
    k = min(MAX_GROW, room_w / total, room_h / (head + body))
    window = 0
    if k < 1 - 1e-9:
        if room_w / total < 1:
            raise PictureError(f"the table is {total:.2f} units wide and {region.w - TABLE_EDGE:.2f} fit: use "
                               "shorter entries or fewer columns")
        # too tall: a window of rows that follows the marked ones, so the picture beside it keeps its room
        window = int((room_h - head - 2 * GRID_MORE) / ROW_H + 1e-9)
        if views[0]["matrix"] or window < GRID_WINDOW - 1:
            raise PictureError(f"the table needs {head + body:.1f} units of height and gets {room_h:.1f}: use "
                               "fewer rows")
        k, body = 1.0, ROW_H * window
    w = [x * k for x in widths]
    cx = region.cx + (names * k) / 2  # the body centred with its row names
    left = cx - sum(w) / 2
    xs = list(np.cumsum([0.0] + w[:-1]) + np.array(w) / 2 + left)
    more = GRID_MORE if window else 0.0
    top = region.top - title - (room_h - (head + body) * k - 2 * more) / 2 - head * k - more
    h = ROW_H * k
    ys = [top - h * (i + 0.5) for i in range(window or len(views[0]["values"]))]
    return GridLayout(k, transposed, xs, w, ys, h, top + head * k / 2 + more if head else None,
                      left - names * k / 2 if names else None, left, left + sum(w), top, top - h * len(ys),
                      window, grid_starts(views, window) if window else [])


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


RECORD_RULE = 0.1  # between a record's name and its fields
RECORD_PAD = 0.12  # each side of a record's text
RECORD_FONT = 28  # records hold more text than a box: classes side by side must fit the narrow frame


def bsize(box: dict, k: float = 1.0) -> tuple[float, float]:
    return box_size(box["text"], box["shape"], k, box.get("fields"))


def box_size(text: str, shape: str, k: float = 1.0, fields=None) -> tuple[float, float]:
    lines = text.split("\n") if text else [""]
    if shape == "record":  # its name over a rule, then its fields one a line, at the audit's minimum font (28)
        lines = lines + list(fields or [])
        # 6% more than the measured widths: "speak(): Woof" (punctuation counted narrow) ran past its box in bench1
        w = max(text_w(line, k * RECORD_FONT / 30) for line in lines) * 1.06 + 2 * RECORD_PAD * k
        h = LINE_H * k * len(lines) + 2 * BOX_PAD_Y * k + (RECORD_RULE * k if fields else 0.0)
        return max(w, 0.5 * k), max(h, 0.46 * k)
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
            if old is None or (len(b["text"]) + sum(len(f) for f in b.get("fields") or [])
                               > len(old["text"]) + sum(len(f) for f in old.get("fields") or [])):
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


def _shared_slots(views: list[dict]) -> dict[str, str]:
    """Boxes that are never on screen together and sit in the same layer share one slot: each key -> the key whose
    place it takes (itself when it shares with none). A box removed in one step and its replacement added in the next
    ('Date: free text' -> 'Date picker') were laid out side by side, so in runs/bench1 a sign-up form of four rows
    needed twice the width and was refused."""
    boxes, arrows = _union(views)
    keys = list(boxes)
    fixed = {k: b["layer"] for k, b in boxes.items() if b.get("layer") is not None}
    rank = _ranks(keys, arrows, fixed)
    present = [set(v["boxes"]) for v in views]
    linked = {k for a, b in arrows for k in (a, b)}
    groups: list[list[str]] = []
    for k in keys:
        for g in groups:
            same_layer = (fixed.get(k) is not None and fixed.get(k) == fixed.get(g[0])) or (
                fixed.get(k) is None and fixed.get(g[0]) is None and rank[k] == rank[g[0]]
                and k not in linked and g[0] not in linked)
            if same_layer and not any(k in p and m in p for p in present for m in g):
                g.append(k)
                break
        else:
            groups.append([k])
    return {m: g[0] for g in groups for m in g}


def _merged(views: list[dict], rep: dict[str, str]) -> list[dict]:
    """The views with each box renamed to the slot it shares (_shared_slots)."""
    if all(k == r for k, r in rep.items()):
        return views
    out = []
    for v in views:
        w = dict(v)
        w["boxes"] = {rep[k]: b for k, b in v["boxes"].items()}
        w["arrows"] = [(rep[a], rep[b], *rest) for a, b, *rest in v["arrows"]]
        out.append(w)
    return out


def _fit_ranks(boxes: dict, arrows, fixed: dict[str, int], width: float, across: bool) -> dict[str, int]:
    """_ranks, with a layer too wide for the frame split onto rows of its own (the layers after it move down), so
    the arrows that pass a row go through a slot beside its boxes. In runs/bench1 a class diagram (Animal above Dog
    and Cat, each a record of fields) needed 5.1 units across and 3.7 fit."""
    rank = _ranks(list(boxes), arrows, fixed)
    if across:
        return rank
    sizes = {k: bsize(b) for k, b in boxes.items()}
    out, shift = {}, 0
    for r in sorted(set(rank.values())):
        layer = [k for k in boxes if rank[k] == r]
        rows, used = [[]], 0.0
        for k in layer:
            w = sizes[k][0]
            if rows[-1] and used + SLOT_GAP + DUMMY + w > width:  # room for an arrow passing beside it
                rows.append([])
                used = 0.0
            used += w + (SLOT_GAP if rows[-1] else 0.0)
            rows[-1].append(k)
        for i, row in enumerate(rows):
            for k in row:
                out[k] = r + shift + i
        shift += len(rows) - 1
    return out


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
    views = _merged(views, _shared_slots(views))
    boxes, arrows = _union(views)
    if not boxes:  # snapshots before the diagram's first box (runs/bench3: this raised ValueError and ended the run)
        return title + 0.3, title + 0.3
    fixed = {k: b["layer"] for k, b in boxes.items() if b.get("layer") is not None}
    across = views[0]["direction"] == "right"
    rank = _fit_ranks(boxes, arrows, fixed, width - 0.1, across)
    ranked, order, chains = _chains(list(boxes), arrows, rank)
    layers = flow_order(list(ranked), order, ranked)
    sizes = {k: bsize(b) for k, b in boxes.items()}
    sizes.update({d: (0.01, DUMMY) if across else (DUMMY, 0.01) for ds in chains.values() for d in ds})
    if across:  # layers left to right: the height is the tallest layer's, with room for labels and loops
        h = max(sum(sizes[k][1] for k in layer) + SLOT_GAP * (len(layer) - 1) for layer in layers)
        return title + h + 0.12, title + h * MAX_GROW + 1.4
    h = sum(max(sizes[k][1] for k in layer) for layer in layers) + MIN_LAYER_GAP * (len(layers) - 1)
    most = sum(max(sizes[k][1] for k in layer) for layer in layers) * MAX_GROW + MAX_LAYER_GAP * (len(layers) - 1)
    return title + h + 0.12, title + most + 0.12


def flow_layout(views: list[dict], region) -> FlowLayout:
    rep = _shared_slots(views)
    lay = _flow_layout(_merged(views, rep), region)
    if all(k == r for k, r in rep.items()):
        return lay
    # every box takes its slot's place; an arrow or label of a renamed box is its slot's
    lay.boxes = {k: lay.boxes[r] for k, r in rep.items()}
    for v in views:
        for a, b, *_ in v["arrows"]:
            ra, rb = rep[a], rep[b]
            if a == b:
                if f"{ra}>{ra}" in lay.loops:
                    lay.loops[f"{a}>{a}"] = lay.loops[f"{ra}>{ra}"]
            elif f"{ra}>{rb}" in lay.arrows:
                lay.arrows[f"{a}>{b}"] = lay.arrows[f"{ra}>{rb}"]
            if (ra, rb) in lay.labels:
                lay.labels[(a, b)] = lay.labels[(ra, rb)]
    return lay


def _flow_layout(views: list[dict], region) -> FlowLayout:
    title = _title(views)
    boxes, arrows = _union(views)
    if not boxes:  # nothing to place yet: the boxes come in a later snapshot, laid out with its own group
        return FlowLayout(1.0, {}, {}, {})
    keys = list(boxes)
    fixed = {k: b["layer"] for k, b in boxes.items() if b.get("layer") is not None}
    across = views[0]["direction"] == "right"
    rank = _fit_ranks(boxes, arrows, fixed, region.w - 0.1, across)
    ranked, order, chains = _chains(keys, arrows, rank)
    layers = flow_order(list(ranked), order, ranked)
    dummies = [d for ds in chains.values() for d in ds]
    room_w, room_h = region.w - 0.1, region.h - title - 0.1
    labelled = {}
    for v in views:
        for a, b, _s, label, *_ in v["arrows"]:
            if label:
                labelled[(a, b)] = label
    loops = [(a, b) for a, b in arrows if a == b]

    def attempt(k: float, gap: float) -> FlowLayout | str:
        sizes = {key: bsize(boxes[key], k) for key in keys}
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
        sized = {key: bsize(boxes[key], k) for key in keys}
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
        shown = {i for i, v in enumerate(views) if any(x == a and y == b and lab for x, y, _s, lab, *_ in v["arrows"])}
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
    ts = [x for v in views for it in v["items"].values() for x in (
        (it["a"], it["b"]) if it["type"] == "block" else
        (it["t0"], it["t0"] + it["step"] * len(it["values"])) if it["type"] == "signal" else (it["t"],))]
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
    first_row: float  # the top of the first message row
    row_h: float
    window: int  # message rows shown at once
    start: list[int]  # each snapshot's first row shown (old messages scroll up out of view)
    order: list[int]  # the rows in order
    bottom: float  # where the lifelines end
    labels: dict[str, np.ndarray]  # a message's label centre, by key, as (x, height above its arrow)
    self_w: float = 0.36  # how far a message to itself loops out
    dropped: list = field(default_factory=list)
    box_ws: list = field(default_factory=list)  # each actor's box width (its own name)
    drop: list = field(default_factory=list)  # how far each actor's box sits below `top` (staggered names)

    def box_top(self, i: int) -> float:
        return self.top - (self.drop[i] if self.drop else 0.0)

    def row_y(self, row: int, snap: int) -> float:
        """The arrow's height of message row `row` in snapshot `snap`."""
        k = self.order.index(row) - self.start[snap]
        return self.first_row - self.row_h * (k + 0.5) - (TEXT_H / 2 - 0.02)

    def shown(self, row: int, snap: int) -> bool:
        k = self.order.index(row)
        return self.start[snap] <= k < self.start[snap] + self.window


MIN_MSG_WINDOW = 4


def _rows(views) -> list[int]:
    return sorted({m["row"] for v in views for m in v["messages"].values()})


ACTOR_GAP = 0.16  # between two actor boxes side by side
STAGGER = ACTOR_H + 0.08  # how far every other actor's box drops when the names don't fit side by side
LIFE_ROOM = 0.08  # between a lifeline and the edge of another actor's box


def actor_boxes(actors: list[str], width: float) -> tuple[list[float], list[float], list[float]]:
    """Each actor's lifeline x (from the band's left), box width and drop. Boxes are as wide as their own names,
    the outer two at the edges. When the names don't fit side by side, every other box drops a row (runs/bench1:
    'Browser', 'DNS', 'Server' needed 5.3 units with every box as wide as the longest name, and 3.7 fit), so a
    box only has to clear its neighbours' lifelines, not their boxes."""
    n = len(actors)
    ws = [text_w(a) + 0.24 for a in actors]
    if n == 1:
        return [width / 2], ws, [0.0]
    x0, x1 = ws[0] / 2, width - ws[-1] / 2
    xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
    if all(xs[i + 1] - xs[i] >= (ws[i] + ws[i + 1]) / 2 + ACTOR_GAP - 1e-9 for i in range(n - 1)):
        return xs, ws, [0.0] * n
    if n >= 3:
        side = all(xs[i + 2] - xs[i] >= (ws[i] + ws[i + 2]) / 2 + ACTOR_GAP - 1e-9 for i in range(n - 2))
        clear = all(abs(xs[j] - xs[i]) >= ws[j] / 2 + LIFE_ROOM - 1e-9
                    for i in range(n) for j in range(n) if i != j and (i - j) % 2)
        if side and clear:
            return xs, ws, [STAGGER * (i % 2) for i in range(n)]
    need = sum(ws) + (n - 1) * ACTOR_GAP
    raise PictureError(f"{n} actors' names need {need:.1f} units across and {width:.1f} fit: use shorter names "
                       "or fewer actors")


def sequence_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    rows = max(1, len(_rows(views)))
    least = min(rows, MIN_MSG_WINDOW)
    try:
        drop = max(actor_boxes(views[0]["actors"], width - 0.1)[2])
    except PictureError:
        drop = 0.0  # sequence_layout says why
    head = title + ACTOR_H + drop + 0.15
    return head + least * MSG_ROW + 0.1, head + rows * MAX_MSG_ROW + 0.1


def sequence_layout(views: list[dict], region) -> SequenceLayout:
    title = _title(views)
    actors = views[0]["actors"]
    # each box as wide as its own name, the outer two at the edges, so the messages between have the most room
    xs, ws, drop = actor_boxes(actors, region.w - 0.1)
    xs = [region.cx - (region.w - 0.1) / 2 + x for x in xs]
    box_w = max(ws)
    rows = _rows(views)
    room = region.h - title - ACTOR_H - max(drop) - 0.15 - 0.1
    if room / max(1, len(rows)) >= MSG_ROW - 1e-9:
        window, row_h = len(rows), min(MAX_MSG_ROW, room / max(1, len(rows)))
    else:  # more messages than fit: the newest stay in view and the oldest scroll up out of it
        window, row_h = int(room / MSG_ROW + 1e-9), MSG_ROW
        if window < min(MIN_MSG_WINDOW, len(rows)):
            raise PictureError(f"the message diagram gets {room:.1f} units of height, room for {window} messages; "
                               f"it needs room for {MIN_MSG_WINDOW} (drop a view)")
    top = region.top - title - (room - row_h * window) / 2
    first_row = top - ACTOR_H - max(drop) - 0.15
    start = []
    for v in views:
        last = max((rows.index(m["row"]) for m in v["messages"].values()), default=0)
        start.append(max(0, last - window + 1))
    lay = SequenceLayout(xs, box_w, top, first_row, row_h, window, start, rows, first_row - row_h * window, {},
                         box_ws=ws, drop=drop)
    x_lo, x_hi = region.cx - region.w / 2, region.cx + region.w / 2
    for v in views:
        for key, m in v["messages"].items():
            if not m.get("label") or key in lay.labels:
                continue
            half = text_half(m["label"])
            a, b = xs[m["a"]], xs[m["b"]]
            if m["a"] == m["b"]:  # beside the loop
                c = np.array([a + lay.self_w + 0.08 + half[0], -0.12])
                if a + lay.self_w + 0.08 + 2 * half[0] > x_hi:  # no room right of the loop: above it
                    c = np.array([min(max(a, x_lo + half[0]), x_hi - half[0]), 0.18 + half[1]])
            else:
                # centred over its arrow, inside the frame; a lifeline it covers is drawn with a gap round it
                c = np.array([min(max((a + b) / 2, x_lo + half[0]), x_hi - half[0]), 0.06 + half[1]])
            if 2 * half[0] > region.w:
                if m["label"] not in lay.dropped:
                    lay.dropped.append(m["label"])
                continue
            lay.labels[key] = c
    return lay


def sequence_gaps(view: dict, lay: SequenceLayout, snap: int) -> dict[int, list[tuple[float, float]]]:
    """Each lifeline's breaks round the labels it would cross in this snapshot."""
    gaps: dict[int, list[tuple[float, float]]] = {}
    for key, m in view["messages"].items():
        if key not in lay.labels or not lay.shown(m["row"], snap):
            continue
        cx, dy = lay.labels[key]
        cy = lay.row_y(m["row"], snap) + dy
        half = text_half(m["label"])
        for i, x in enumerate(lay.x):
            if cx - half[0] - 0.04 < x < cx + half[0] + 0.04:
                gaps.setdefault(i, []).append((cy - half[1] - 0.03, cy + half[1] + 0.03))
    return gaps


# ---- circuit (drawn top to bottom: the portrait frame is tall, not wide) ----------------------------------

GATE_LEN = 0.44  # a gate along the signal (down the frame)
BLOCK_H = 0.5  # a block (MUX, DFF...): its name inside
PIN = 0.06  # the stubs into and out of a gate
TERM = 0.36  # an input's or output's value box
NAME_H = TEXT_H + 0.04  # an input's name above its box, an output's below
MIN_WIRE_GAP = 0.22  # between two levels, for the wires' turns
CHANNEL_GAP = 0.08  # between two wires turning in one gap
MAX_WIRE_GAP = 0.7
PART_GAP = 0.34  # between two parts side by side
DUMMY_W = 0.16  # a wire passing a level
LANE = 0.14  # a wire looping back up to a flip-flop runs in a lane of its own at the right


def gate_wid(n_inputs: int) -> float:
    return max(0.56, 0.22 * n_inputs + 0.16)


def _outs(p: dict) -> list[str]:
    from animation_agent.scene.api import BLOCKS

    return BLOCKS[p["block"]][1] if p["type"] == "block" else [""]


def part_size(p: dict) -> tuple[float, float]:
    if p["type"] == "gate":
        return gate_wid(len(p["inputs"])), GATE_LEN
    if p["type"] == "block":
        n = max(len(p["inputs"]), len(_outs(p)))
        return max(0.8, 0.24 * n + 0.2, text_w(p["block"], 28 / 30) + 0.24), BLOCK_H
    return TERM, TERM


def _base(src: str) -> str:
    return src.split(".")[0]


def _is_ff(p: dict) -> bool:
    return p["type"] == "block" and p["block"] == "DFF"


@dataclass
class CircuitLayout:
    pos: dict[str, np.ndarray]  # each part's centre
    size: dict[str, tuple[float, float]]  # width, height on screen
    wires: dict[str, list[tuple[float, float]]]  # "src>dst#i": the polyline, from the source's pin to the input
    names: dict[str, np.ndarray]  # an input's or output's name


def _depths(parts: dict) -> dict[str, int]:
    """Each part's level: inputs and flip-flops (sources: their Q is known before anything else) first, each gate
    or block one below its deepest input, the outputs last."""
    depth: dict[str, int] = {}
    for k, p in parts.items():
        if p["type"] == "input" or _is_ff(p):
            depth[k] = 0
    for k, p in parts.items():
        if p["type"] in ("gate", "block") and not _is_ff(p):
            depth[k] = 1 + max(depth[_base(i)] for i in p["inputs"])
    last = max(depth.values(), default=0) + 1
    for k, p in parts.items():
        if p["type"] == "output":
            depth[k] = last
    return depth


def _back(parts, depth) -> list[tuple[str, int, str]]:
    """The wires that loop back up into a flip-flop: (flip-flop, input, source)."""
    return [(k, j, src) for k, p in parts.items() if _is_ff(p) for j, src in enumerate(p["inputs"])]


def _turns(parts, depth) -> dict[int, list[str]]:
    """The sources whose wires turn in each gap between levels (each gets a channel of its own there); a wire back
    up to a flip-flop turns in the gap below its source."""
    users: dict[int, list[str]] = {}
    for k, p in parts.items():
        if _is_ff(p):
            continue
        for src in p.get("inputs", []):
            for d in range(depth[_base(src)], depth[k]):
                users.setdefault(d, [])
                if src not in users[d]:
                    users[d].append(src)
    for _k, _j, src in _back(parts, depth):
        users.setdefault(depth[_base(src)], [])
        if src not in users[depth[_base(src)]]:
            users[depth[_base(src)]].append(src)
    return users


def _gap_need(n: int) -> float:
    return max(MIN_WIRE_GAP, 0.06 + CHANNEL_GAP * (n + 1))


def _level_lens(parts, depth) -> list[float]:
    levels = max(depth.values()) + 1
    out = []
    for d in range(levels):
        here = [p for k, p in parts.items() if depth[k] == d]
        if d in (0, levels - 1):
            out.append(max([TERM + NAME_H] + [BLOCK_H + 2 * PIN for p in here if p["type"] == "block"]))
        else:
            out.append(max(BLOCK_H if p["type"] == "block" else GATE_LEN for p in here) + 2 * PIN)
    return out


def _top_room(parts, depth) -> float:
    """Above the first level, a channel for each wire looping back to a flip-flop."""
    n = len(_back(parts, depth))
    return 0.1 + CHANNEL_GAP * (n + 1) if n else 0.0


def circuit_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    parts = views[-1]["parts"]
    depth = _depths(parts)
    lens = _level_lens(parts, depth)
    users = _turns(parts, depth)
    need = [_gap_need(len(users.get(d, []))) for d in range(len(lens) - 1)]
    top = _top_room(parts, depth)
    return (title + top + sum(lens) + sum(need) + 0.12,
            title + top + sum(lens) + sum(max(g, MAX_WIRE_GAP) for g in need) + 0.12)


def _port(pos, size, parts, key, j=None, out=0) -> tuple[float, float]:
    """A part's input pin j (along its top), or output pin `out` (along its bottom)."""
    c, (w, h) = pos[key], size[key]
    pin = PIN if parts[key]["type"] in ("gate", "block") else 0.0
    if j is None:
        n = len(_outs(parts[key]))
        span = w - 0.2
        return (float(c[0] - span / 2 + span * out / (n - 1)) if n > 1 else float(c[0]), float(c[1] - h / 2 - pin))
    n = len(parts[key]["inputs"])
    span = w - 0.2
    return (float(c[0] - span / 2 + span * j / (n - 1)) if n > 1 else float(c[0]), float(c[1] + h / 2 + pin))


def source_port(pos, size, parts, src: str) -> tuple[float, float]:
    base, _, port = src.partition(".")
    outs = _outs(parts[base])
    return _port(pos, size, parts, base, None, outs.index(port) if port in outs else 0)


def circuit_layout(views: list[dict], region) -> CircuitLayout:
    from animation_agent.scene.math_layout import seg_hits_box

    title = _title(views)
    parts = views[-1]["parts"]
    for v in views:  # the last snapshot has every part; a part may not be removed
        if set(v["parts"]) - set(parts):
            raise PictureError("a circuit keeps its parts once made (set the inputs to show a change)")
    if not any(p["type"] in ("input",) or _is_ff(p) for p in parts.values()) or len(parts) < 2:
        raise PictureError("a circuit needs inputs and a gate or output")
    depth = _depths(parts)
    lens = _level_lens(parts, depth)
    users = _turns(parts, depth)
    back = _back(parts, depth)
    need = [_gap_need(len(users.get(d, []))) for d in range(len(lens) - 1)]
    top_room = _top_room(parts, depth)
    room = region.h - title - 0.12 - top_room
    spare = room - sum(lens) - sum(need)
    if spare < -1e-9:
        raise PictureError(f"the circuit is {len(lens)} levels deep (inputs, gates, outputs) and needs "
                           f"{sum(lens) + sum(need) + top_room:.1f} units of height; it gets {room + top_room:.1f}: "
                           "use fewer levels of gates or fewer wires")
    gaps = [min(g + spare / max(1, len(need)), max(g, MAX_WIRE_GAP)) for g in need]
    total = sum(lens) + sum(gaps)
    y = region.top - title - top_room - 0.06 - (room - total) / 2
    top_channel = y + top_room - 0.04  # the back wires' channels sit between here and the first level
    centre_y = []  # an input's name sits above its box, an output's below
    for d, L in enumerate(lens):
        centre_y.append(y - NAME_H - TERM / 2 if d == 0 else y - TERM / 2 if d == len(lens) - 1 else y - L / 2)
        y -= L + (gaps[d] if d < len(gaps) else 0.0)
    size = {k: part_size(p) for k, p in parts.items()}
    # a wire that skips a level passes it at a slot of its own (one per source and level, a dummy part, as
    # layered drawings route long edges), so it runs between the parts there, not through them
    passing: dict[int, list[str]] = {}
    for k, p in parts.items():
        if _is_ff(p):
            continue
        for src in p.get("inputs", []):
            for d in range(depth[_base(src)] + 1, depth[k]):
                passing.setdefault(d, [])
                if src not in passing[d]:
                    passing[d].append(src)
    levels = [[k for k in parts if depth[k] == d] + [f"~{src}~{d}" for src in passing.get(d, [])]
              for d in range(len(lens))]
    lanes = LANE * len(back)  # room at the right for the wires back up
    width = region.w - 0.1 - lanes
    left_x = region.cx - (region.w - 0.1) / 2

    def wide(k: str) -> float:
        return DUMMY_W if k.startswith("~") else size[k][0]

    for d, level in enumerate(levels):
        need_w = sum(wide(k) for k in level) + PART_GAP * (len(level) - 1)
        if need_w > width:
            raise PictureError(f"{len(level)} parts and wires side by side need {need_w:.1f} units and "
                               f"{width:.1f} fit: use fewer gates in a level")
    # left to right in each level by where its inputs are (barycentre), so wires run mostly straight down
    x: dict[str, float] = {}
    for d, level in enumerate(levels):
        if d:
            def bary(k: str) -> float:
                ins = [k.split("~")[1]] if k.startswith("~") else parts[k]["inputs"]
                return sum(x[_base(i)] for i in ins) / len(ins)

            level.sort(key=bary)
        slot = width / len(level)
        for j, k in enumerate(level):
            x[k] = left_x + slot * (j + 0.5)
    pos = {k: np.array([x[k], centre_y[depth[k]]]) for k in parts}
    names = {}
    for k, p in parts.items():
        if p["type"] == "input":
            names[k] = np.array([x[k], pos[k][1] + TERM / 2 + NAME_H / 2])
        elif p["type"] == "output":
            names[k] = np.array([x[k], pos[k][1] - TERM / 2 - NAME_H / 2])
    real = [[k for k in level if not k.startswith("~")] for level in levels]

    def bottom_of(k):
        return pos[k][1] - size[k][1] / 2 - (PIN if parts[k]["type"] in ("gate", "block") else 0)

    def gap_between(d: int) -> tuple[float, float]:
        above = min(bottom_of(k) for k in real[d])
        below = max(pos[k][1] + size[k][1] / 2 + (PIN if parts[k]["type"] in ("gate", "block") else 0)
                    for k in real[d + 1])
        return below + 0.03, above - 0.03

    def clear(path, src, k) -> str | None:
        for other in parts:  # a wire may pass no part but its own two
            if other in (_base(src), k):
                continue
            c, (w, h) = pos[other], size[other]
            pin = PIN if parts[other]["type"] in ("gate", "block") else 0.0
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
        if _is_ff(p):
            continue
        for j, src in enumerate(p.get("inputs", [])):
            a, b = source_port(pos, size, parts, src), _port(pos, size, parts, k, j)
            path = [a]
            at = a[0]
            for d in range(depth[_base(src)], depth[k]):  # down to the channel, across to the next slot, down again
                nxt = x[f"~{src}~{d + 1}"] if d + 1 < depth[k] else b[0]
                path += [(at, ch(d, src)), (nxt, ch(d, src))]
                at = nxt
            path.append(b)
            if abs(a[0] - b[0]) < 1e-6 and depth[k] == depth[_base(src)] + 1:
                path = [a, b]
            path = [q for i, q in enumerate(path) if i == 0 or (abs(q[0] - path[i - 1][0]) > 1e-9
                                                              or abs(q[1] - path[i - 1][1]) > 1e-9)]
            if (other := clear(path, src, k)) is not None:
                raise PictureError(f"the wire from {src} to {k} would cross {other}; use fewer gates or levels")
            wires[f"{src}>{k}#{j}"] = path
    right = left_x + width  # the back wires' lanes, one each, right of every part
    for n, (k, j, src) in enumerate(back):
        if _base(src) not in parts:
            raise PictureError(f"{k}'s D comes from {src!r}, which is never made")
        a, b = source_port(pos, size, parts, src), _port(pos, size, parts, k, j)
        lane = right + LANE * (n + 0.6)
        ytop = top_channel - CHANNEL_GAP * (n + 1)
        down = ch(depth[_base(src)], src)
        path = [a, (a[0], down), (lane, down), (lane, ytop), (b[0], ytop), b]
        if (other := clear(path, src, k)) is not None:
            raise PictureError(f"the wire from {src} back up to {k} would cross {other}; use fewer gates")
        wires[f"{src}>{k}#{j}"] = path
    # two different wires may cross but never run along one another
    segs = [(key.split(">")[0], s_, t) for key, path in wires.items() for s_, t in zip(path, path[1:])]
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
    stacked: bool = False  # the stack above the heap (too wide side by side); every pointer runs down the right


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


def _memory_widths(views) -> tuple[float, float, float, float]:
    """(side by side, stacked): the width each arrangement needs, and the stack's and heap's column widths."""
    order, boxes, _fields, widths = _memory_union(views)
    to_heap, in_heap = _arrows_most(views)
    dims = {k: _box_dims(widths[k]) for k in order}
    stack_w = max([dims[k][0] for k in order if boxes[k]["area"] == "stack"], default=0.0)
    heap_w = max([dims[k][0] for k in order if boxes[k]["area"] == "heap"], default=0.0)
    middle = 0.3 + CHANNEL * max(0, to_heap - 1) if stack_w and heap_w else 0.0
    outer = 0.24 + CHANNEL * max(0, in_heap - 1) if in_heap else 0.0
    lanes = to_heap + in_heap
    stacked = max(stack_w, heap_w) + (0.24 + CHANNEL * (lanes - 1) if lanes else 0.0)
    return stack_w + middle + heap_w + outer, stacked, stack_w, heap_w


def memory_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    order, boxes, fields, _w = _memory_union(views)
    tall = {area: sum(BOX_TITLE_H + FIELD_H * max(1, len(fields[k])) + BOX_GAP for k in order
                      if boxes[k]["area"] == area) for area in ("stack", "heap")}
    side, _stacked, _s, _h = _memory_widths(views)
    h = (max(tall.values()) if side <= width - 0.05 else sum(tall.values()) + 0.16) + 0.1
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
    if need > region.w - 0.05:  # too wide side by side (runs/bench1: a closure's frames and function object)
        return _memory_stacked(views, region, title, order, boxes, fields, dims, stack_w, heap_w)
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


def _memory_stacked(views, region, title, order, boxes, fields, dims, stack_w, heap_w) -> MemoryLayout:
    """The stack's frames above the heap's objects, one column, every pointer in a lane of its own at the right."""
    _side, need, _s, _h = _memory_widths(views)
    if need > region.w - 0.05:
        raise PictureError(f"the memory diagram is {need:.1f} units wide even with the stack above the heap, and "
                           f"{region.w:.1f} fit: use shorter names and values, or fewer pointers")
    col = max(stack_w, heap_w)
    heights = {k: BOX_TITLE_H + FIELD_H * max(1, len(fields[k])) for k in order}
    keys = [k for k in order if boxes[k]["area"] == "stack"] + [k for k in order if boxes[k]["area"] == "heap"]
    split = 0.16 if any(boxes[k]["area"] == "stack" for k in keys) and any(boxes[k]["area"] == "heap" for k in keys) \
        else 0.0
    tall = sum(heights.values()) + BOX_GAP * (len(keys) - 1) + split
    room = region.h - title - 0.1
    if tall > room + 1e-9:
        raise PictureError(f"the memory diagram is too wide side by side, and stacked it needs {tall:.1f} units of "
                           f"height and gets {room:.1f}: use fewer frames, objects or fields")
    left = region.cx - need / 2
    y = region.top - title - 0.05 - (room - tall) / 2
    out = {}
    for i, k in enumerate(keys):
        if i and boxes[k]["area"] == "heap" and boxes[keys[i - 1]]["area"] == "stack":
            y -= split
        out[k] = (left, y, col, heights[k])
        y -= heights[k] + BOX_GAP
    right = left + col
    return MemoryLayout(out, {k: dims[k][1] for k in order}, right, left, right, left + need, fields, stacked=True)


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
            if lay.stacked:  # one column: every pointer out to its own lane at the right, into the object's side
                ch = lay.heap_right + 0.15 + CHANNEL * out_n
                out_n += 1
                out[f"{k}.{name}"] = [(vx, y), (ch, y), (ch, ty), (tl + tw, ty)]
            elif b["area"] == "stack":
                ch = lay.stack_right + 0.15 + CHANNEL * mid_n
                mid_n += 1
                out[f"{k}.{name}"] = [(vx, y), (ch, y), (ch, ty), (tl, ty)]
            else:
                ch = lay.heap_right + 0.15 + CHANNEL * out_n
                out_n += 1
                out[f"{k}.{name}"] = [(vx, y), (ch, y), (ch, ty), (tl + tw, ty)]
    return out
