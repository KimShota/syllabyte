"""
Where a code panel's and a tape's parts go (plan/visual-coverage-plan.md, step 2). Pure Python, no Manim.

The frame is narrow (3.9 units in the dialogue frame) and text keeps the minimum font, so a code row holds about
14 characters and a tape row about 15 cells. A code line longer than a row wraps onto the next (indented under
itself); a program taller than its band scrolls, the window following the current line; a tape too long for one
row wraps onto more, unless rows are aligned under it (a pattern under a text must stay under it), when it is
refused with the reason.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from animation_agent.scene.api import PictureError
from animation_agent.scene.math_layout import TEXT_H, text_width

TITLE_H = 0.38
CODE_LINE_H = 0.48
CODE_CHAR_W = 0.245  # Menlo at font 30, measured
CODE_FONTS = (30, 28)  # 28 (the audit's minimum) when it saves a wrap
INDENT = 0.5  # a leading space is drawn half a character wide: nesting costs less of a narrow row
GUTTER = 0.26  # left of the code: the current line's marker
MIN_WINDOW = 4  # rows a scrolled code panel shows at least
MORE_H = 0.24  # above and below a scrolled window: a marker that more is there
WATCH_H = 0.44
WATCH_GAP = 0.12
MAX_WRAP = 3  # rows one logical line may take


def _title(views: list[dict]) -> float:
    return TITLE_H if any(v.get("title") for v in views) else 0.0


# ---- code ---------------------------------------------------------------------------------------------------


def char_w(font: int) -> float:
    return CODE_CHAR_W * font / 30


def fits(width: float, font: int = 30) -> float:
    """How many characters a row holds, in character widths."""
    return (width - GUTTER - 0.05) / char_w(font)


def _span(text: str) -> float:
    lead = len(text) - len(text.lstrip(" "))
    return lead * INDENT + len(text) - lead


def wrap(text: str, n: float) -> list[str]:
    """A code line as rows at most n characters wide (leading spaces counting half): broken at the last space
    that fits, the rest indented two more than the line itself; a word longer than a row is cut."""
    if _span(text) <= n + 1e-9:
        return [text]
    indent = len(text) - len(text.lstrip(" "))
    rows, rest, first = [], text.lstrip(" "), True
    while rest:
        pad = indent if first else indent + 2
        room = max(4, int(n - pad * INDENT + 1e-9))
        if len(rest) <= room:
            rows.append(" " * pad + rest)
            break
        cut = rest.rfind(" ", 0, room + 1)
        if cut <= 0:
            cut = room
        rows.append(" " * pad + rest[:cut].rstrip())
        rest = rest[cut:].lstrip(" ")
        first = False
    return rows


def code_rows(view: dict, n: float) -> list[tuple[int, str, bool]]:
    """The rows a snapshot's code takes: (logical line, text, is a continuation)."""
    out = []
    for i, line in enumerate(view["lines"]):
        parts = wrap(line, n)
        if len(parts) > MAX_WRAP:
            raise PictureError(f"the code line {line!r} needs {len(parts)} rows of {int(n)} characters; shorten it")
        out += [(i, text, j > 0) for j, text in enumerate(parts)]
    return out


def code_font(views: list[dict], width: float) -> int:
    """30, or 28 when that keeps a line from wrapping (or wraps it less)."""
    widest = max(_span(line) for v in views for line in v["lines"])
    return 30 if widest <= fits(width, 30) + 1e-9 else 28


def _watch_order(views: list[dict]) -> list[str]:
    order: list[str] = []
    for v in views:
        for name in v.get("watch", {}):
            if name not in order:
                order.append(name)
    return order


def watch_text(name: str, value: str) -> str:
    return f"{name} = {value}"


def _watch_spots(views: list[dict], width: float) -> tuple[dict[str, tuple[int, float, float]], int]:
    """Each watched name's chip: (row, left x from the band's left, width), placed for the widest value it ever
    shows, so chips never move; and the rows they take."""
    order = _watch_order(views)
    widest = {n: max(text_width(watch_text(n, v["watch"][n])) for v in views if n in v.get("watch", {})) + 0.2
              for n in order}
    spots, row, x = {}, 0, 0.0
    for n in order:
        w = widest[n]
        if x and x + w > width - 0.1:
            row, x = row + 1, 0.0
        if w > width - 0.1:
            raise PictureError(f"the watched variable {n} is too wide for the frame; use a shorter value")
        spots[n] = (row, x, w)
        x += w + WATCH_GAP
    rows = row + 1 if order else 0
    if rows > 2:
        raise PictureError("the watched variables need more than 2 rows; watch fewer")
    return spots, rows


def code_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    n = fits(width, code_font(views, width))
    total = max(len(code_rows(v, n)) for v in views)
    _spots, wrows = _watch_spots(views, width)
    watch = wrows * WATCH_H + (0.06 if wrows else 0.0)
    least = total if total <= MIN_WINDOW + 1 else MIN_WINDOW
    lo = title + CODE_LINE_H * least + watch + (2 * MORE_H if least < total else 0.0)
    return lo, title + CODE_LINE_H * total + watch


@dataclass
class CodeLayout:
    chars: float  # per row
    rows: list[list[tuple[int, str, bool]]]  # each snapshot's rows
    start: list[int]  # each snapshot's first row shown
    window: int  # rows shown
    left: float  # the text's left edge
    top: float  # the first row's top
    scrolled: bool
    font: int = 30
    watch: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # name: (centre x, centre y, width)


def code_layout(views: list[dict], region) -> CodeLayout:
    title = _title(views)
    font = code_font(views, region.w)
    n = fits(region.w, font)
    rows = [code_rows(v, n) for v in views]
    spots, wrows = _watch_spots(views, region.w)
    watch_h = wrows * WATCH_H + (0.06 if wrows else 0.0)
    room = region.h - title - watch_h
    total = max(len(r) for r in rows)
    if room + 1e-9 >= CODE_LINE_H * total:
        window, scrolled = total, False
    else:
        window, scrolled = int((room - 2 * MORE_H) / CODE_LINE_H + 1e-9), True
        if window < MIN_WINDOW - 1:
            raise PictureError(f"the code panel gets {room:.1f} units of height, room for {max(window, 0)} rows; "
                               "it needs a band of at least 4 rows (drop a view, or show fewer lines)")
    used = CODE_LINE_H * window + (2 * MORE_H if scrolled else 0.0)
    top = region.top - title - (MORE_H if scrolled else 0.0) - max(0.0, (room - used) / 2)
    start, s = [], 0
    for v, rs in zip(views, rows):
        if v["current"] is not None:
            mine = [k for k, (i, _t, _c) in enumerate(rs) if i == v["current"]]
            if mine:
                if mine[0] < s:
                    s = mine[0]
                if mine[-1] >= s + window:
                    s = mine[-1] - window + 1
        s = max(0, min(s, len(rs) - window))
        start.append(s)
    left = region.cx - region.w / 2 + GUTTER
    lay = CodeLayout(n, rows, start, window, left, top, scrolled, font)
    wy = region.top - title - room - watch_h + 0.06  # the watch rows' bottom
    x0 = region.cx - region.w / 2 + 0.05
    for name, (row, x, w) in spots.items():
        lay.watch[name] = (x0 + x + w / 2, wy + (wrows - row - 0.5) * WATCH_H, w)
    return lay


def code_row_y(lay: CodeLayout, k: int, snap: int) -> float:
    """The centre of row k of snapshot `snap`'s code, on screen (rows outside the window aren't drawn)."""
    return lay.top - CODE_LINE_H * (k - lay.start[snap] + 0.5)


# ---- tape ---------------------------------------------------------------------------------------------------

TAPE_MIN_W = 0.22  # one character at the audit's minimum font (28) with a margin
TAPE_MAX_W = 0.5
TAPE_H = 0.42
TAPE_MAX_H = 0.56
GROUP_GAP = 0.08
ROW_GAP = 0.06
INDEX_H = 0.26
HEAD_H = 0.34
FIELD_H = 0.44
LINE_GAP = 0.14


def _columns(views: list[dict]) -> int:
    n = 0
    for v in views:
        n = max(n, len(v["values"]))
        for r in v["rows"].values():
            n = max(n, r["at"] + len(r["values"]))
    return n


def _rows_used(views: list[dict]) -> list[str]:
    order: list[str] = []
    for v in views:
        for k in v["rows"]:
            if k not in order:
                order.append(k)
    return order


def _heads_deep(views: list[dict]) -> int:
    most = 0
    for v in views:
        per: dict[int, int] = {}
        for i in v["heads"].values():
            per[i] = per.get(i, 0) + 1
        most = max(most, max(per.values(), default=0))
    return most


def _label_w(views: list[dict]) -> float:
    labels = [r["label"] for v in views for r in v["rows"].values() if r.get("label")]
    return (max(text_width(x) for x in labels) + 0.1) if labels else 0.0


def _groups(per_line: int, group: int | None) -> int:
    return 0 if not group else (per_line - 1) // group


def _least_w(views: list[dict]) -> float:
    """The narrowest cell that holds the widest symbol at the audit's minimum font (28): bits fit narrower cells
    than capital letters."""
    symbols = {s for v in views for s in v["values"] + [x for r in v["rows"].values() for x in r["values"]] if s}
    widest = max((text_width(s) for s in symbols), default=0.15)
    return max(TAPE_MIN_W, widest * 28 / 30 + 0.025)


def tape_shape(views: list[dict], width: float) -> tuple[int, int, float]:
    """Cells per line, lines, and the cell width at this band width."""
    n = _columns(views)
    group = views[0]["group"]
    room = width - 0.05 - _label_w(views)
    least = _least_w(views)
    w = (room - GROUP_GAP * _groups(n, group)) / n
    if w >= least - 1e-9:
        return n, 1, min(TAPE_MAX_W, w)
    if _rows_used(views):
        most = int((room + GROUP_GAP) / (least + (GROUP_GAP / group if group else 0.0)))
        raise PictureError(f"a tape with rows aligned under it stays on one line: {n} columns, and about {most} fit "
                           "across; use a shorter text, or no rows under it")
    per = n
    while per > 1:
        per -= 1
        if group and per % group and per > group:
            continue
        w = (room - GROUP_GAP * _groups(per, group)) / per
        if w >= least - 1e-9:
            break
    lines = math.ceil(n / per)
    return per, lines, min(TAPE_MAX_W, (room - GROUP_GAP * _groups(per, group)) / per)


FIELD_ROW = 0.32  # a second row of field labels, when two would touch


def _fields(views: list[dict]) -> dict[str, list]:
    """Every field any snapshot shows, as last defined."""
    out: dict[str, list] = {}
    for v in views:
        out.update(v["fields"])
    return out


def _field_label_spots(views, per: int, w: float, group, left: float, x_lo: float, x_hi: float):
    """Each field label's (line, row, centre x): under its bracket's first line, in the first of two rows where it
    clears the labels already there; (None for one that clears neither: left out)."""
    def x(j):
        k = j % per
        return left + w * (k + 0.5) + GROUP_GAP * (k // group if group else 0)

    placed: list[tuple[int, int, float, float]] = []  # line, row, centre, half width
    out = {}
    for key, (a, b, label, _s) in sorted(_fields(views).items(), key=lambda kv: kv[1][0]):
        if not label:
            continue
        line = a // per
        end = min(b, (line + 1) * per)
        half = text_width(label) / 2 + 0.03
        cx = min(max((x(a) + x(end - 1)) / 2, x_lo + half), x_hi - half)
        spot = None
        for row in (0, 1):
            if not any(pl == line and pr == row and abs(cx - pc) < half + ph + 0.06 for pl, pr, pc, ph in placed):
                spot = (line, row, cx)
                placed.append((line, row, cx, half))
                break
        out[(key, label)] = spot
    return out


def _label_rows(views, per, w) -> int:
    spots = _field_label_spots(views, per, w, views[0]["group"], 0.0, -1e9, 1e9)
    return 2 if any(s is not None and s[1] == 1 for s in spots.values()) else 1


def _line_h(views: list[dict], h: float, label_rows: int = 1) -> float:
    extra = len(_rows_used(views)) * (h + ROW_GAP)
    index = INDEX_H if views[0]["index"] else 0.0
    heads = HEAD_H * _heads_deep(views)
    fields = (FIELD_H + FIELD_ROW * (label_rows - 1)) if any(v["fields"] for v in views) else 0.0
    return h + extra + index + heads + fields


def tape_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    per, lines, w = tape_shape(views, width)
    rows = _label_rows(views, per, w)
    lo = title + lines * _line_h(views, TAPE_H, rows) + LINE_GAP * (lines - 1)
    big = max(TAPE_H, min(TAPE_MAX_H, w))
    return lo, title + lines * _line_h(views, big, rows) + LINE_GAP * (lines - 1)


@dataclass
class TapeLayout:
    per_line: int
    lines: int
    w: float  # a cell's width
    h: float  # a cell's height
    left: float  # the first cell's left edge
    top: float  # the first line's top
    line_h: float
    group: int | None
    rows: list[str]  # the rows under the tape, in order
    label_x: float  # the rows' labels' right edge
    index: bool
    heads_deep: int
    fields: bool
    field_spots: dict = field(default_factory=dict)  # (key, label): label centre

    def x(self, j: int) -> float:
        k = j % self.per_line
        return self.left + self.w * (k + 0.5) + GROUP_GAP * (k // self.group if self.group else 0)

    def line(self, j: int) -> int:
        return j // self.per_line

    def y(self, j: int, row: int = -1) -> float:
        """The centre of column j's cell in the main row (row -1) or row `row` under it."""
        top = self.top - self.line(j) * (self.line_h + LINE_GAP)
        return top - self.h / 2 - (row + 1) * (self.h + ROW_GAP)

    def below(self, j: int) -> float:
        """The top of what sits under column j's cells (its index, heads and field brackets)."""
        top = self.top - self.line(j) * (self.line_h + LINE_GAP)
        return top - self.h - len(self.rows) * (self.h + ROW_GAP)


def tape_layout(views: list[dict], region) -> TapeLayout:
    title = _title(views)
    per, lines, w = tape_shape(views, region.w)
    label_rows = _label_rows(views, per, w)
    room = region.h - title
    h = TAPE_H
    for cand in (min(TAPE_MAX_H, max(TAPE_H, w)), TAPE_H):
        if lines * _line_h(views, cand, label_rows) + LINE_GAP * (lines - 1) <= room + 1e-9:
            h = cand
            break
    else:
        need = lines * _line_h(views, TAPE_H, label_rows) + LINE_GAP * (lines - 1)
        raise PictureError(f"the tape takes {lines} lines and needs {need:.1f} units of height; it gets {room:.1f}: "
                           "use fewer cells")
    line_h = _line_h(views, h, label_rows)
    used = lines * line_h + LINE_GAP * (lines - 1)
    label_w = _label_w(views)
    group = views[0]["group"]
    span = w * per + GROUP_GAP * _groups(per, group)
    left = region.cx - (span - label_w) / 2
    top = region.top - title - (room - used) / 2
    lay = TapeLayout(per, lines, w, h, left, top, line_h, group, _rows_used(views), left - 0.08,
                     bool(views[0]["index"]), _heads_deep(views), any(v["fields"] for v in views))
    spots = _field_label_spots(views, per, w, group, left, region.cx - region.w / 2, region.cx + region.w / 2)
    for (key, label), spot in spots.items():
        if spot is not None:
            line, row, cx = spot
            y = field_segments(lay, line * per, line * per + 1)[0][2]
            lay.field_spots[(key, label)] = (cx, field_label_y(y) - row * FIELD_ROW)
    return lay


def field_segments(lay: TapeLayout, a: int, b: int) -> list[tuple[float, float, float]]:
    """A field over columns a to b - 1 as one bracket per line it spans: (x0, x1, y)."""
    out = []
    j = a
    while j < b:
        end = min(b, (lay.line(j) + 1) * lay.per_line)
        y = lay.below(j) - (INDEX_H if lay.index else 0.0) - HEAD_H * lay.heads_deep - 0.1
        out.append((lay.x(j) - lay.w / 2 + 0.03, lay.x(end - 1) + lay.w / 2 - 0.03, y))
        j = end
    return out


def head_spot(lay: TapeLayout, j: int, stack: int) -> np.ndarray:
    y = lay.below(j) - (INDEX_H if lay.index else 0.0) - HEAD_H * (stack + 0.5)
    return np.array([lay.x(j), y])


def index_y(lay: TapeLayout, j: int) -> float:
    return lay.below(j) - INDEX_H / 2


def field_label_y(y: float) -> float:
    return y - 0.06 - TEXT_H / 2


# ---- formula (plan/visual-coverage-plan.md, after runs/cov1) ------------------------------------------------
# In runs/cov1 a formula of 4 lines at 0.9 units a line needed 3.6-4.0 of the frame's 4.7 by itself, so 3D scenes
# and axes couldn't share the frame and three videos lost their pictures. A line now takes only the height its
# TeX needs (a fraction or a sum is tall, a + b = c is not), and when room is short the formula shows its newest
# lines, the older ones scrolled up out of view, so the diagram gets the room.

FORMULA_TALL = 0.75  # a line with a fraction, a matrix
FORMULA_TALLER = 0.9  # a line with limits above and below (a sum, an integral): the tallest at font 28
FORMULA_FLAT = 0.52  # a line of plain symbols
_TALL = re.compile(r"\\(d?frac|t?frac|binom|begin|over|underbrace|overbrace|matrix|bmatrix|pmatrix|cases|sqrt\[)")
# TeX command names end before '_' as well as braces or spaces. A regex word boundary
# misses the usual integral/sum with limits (\int_0, \sum_i) and underestimates its height.
_TALLER = re.compile(r"\\(sum|int|iint|iiint|oint|prod|lim)(?![A-Za-z])")


def formula_pitch(tex: str) -> float:
    if _TALLER.search(tex):
        return FORMULA_TALLER
    return FORMULA_TALL if _TALL.search(tex) or "^{" in tex and "_{" in tex else FORMULA_FLAT


def _pitches(views: list[dict]) -> list[float]:
    """Each line index's height: the tallest any snapshot writes there, so lines never jump."""
    n = max((len(v["lines"]) for v in views), default=0)
    return [max((formula_pitch(v["lines"][i]) for v in views if i < len(v["lines"])), default=FORMULA_FLAT)
            for i in range(n)]


def formula_heights(views: list[dict], width: float, title: float) -> tuple[float, float]:
    p = _pitches(views)
    if not p:
        return title + FORMULA_FLAT, title + FORMULA_FLAT
    least = max((sum(p[max(0, len(v["lines"]) - 2):len(v["lines"])]) for v in views), default=p[0])
    scroll = MORE_H if least < sum(p) - 1e-9 else 0.0
    return title + least + scroll, title + sum(p)


def formula_min_height(views: list[dict], title: float) -> float:
    """A compact supporting formula: keep the newest line and any explicitly emphasized working visible.
    Scroll older working instead of shrinking TeX below its readable pitch. The normal allocation still
    prefers two lines; this lower bound is used only when the composition otherwise overflows."""
    p = _pitches(views)
    if not p:
        return title + FORMULA_FLAT
    required = 0.0
    for v in views:
        n = len(v["lines"])
        if not n:
            continue
        focus = [int(i) for i, style in v["styles"].items() if style]
        focus += [int(i) for i, terms in v["terms"].items() if terms]
        focus += v["boxed"]
        first = min([n - 1, *focus])
        required = max(required, sum(p[first:n]))
    scroll = MORE_H if required < sum(p) - 1e-9 else 0.0
    return title + required + scroll


@dataclass
class FormulaLayout:
    pitch: list[float]  # each line's height
    start: list[int]  # each snapshot's first line shown
    end: list[int]  # each snapshot's line after the last shown
    top: float  # the first shown line's top
    scrolled: bool


def formula_layout(views: list[dict], region) -> FormulaLayout:
    title = _title(views)
    p = _pitches(views)
    room = region.h - title
    scrolled = sum(p) > room + 1e-9
    if scrolled:
        room -= MORE_H
    start, end = [], []
    for v in views:
        n = len(v["lines"])
        s = n
        while s > 0 and sum(p[s - 1:n]) <= room + 1e-9:
            s -= 1
        if s == n and n:
            raise PictureError(f"the formula gets {room:.1f} units of height, too little for one line; drop a view")
        start.append(s)
        end.append(n)
    shown = max((sum(p[s:e]) for s, e in zip(start, end)), default=0.0)
    top = region.top - title - (MORE_H if scrolled else 0.0) - max(0.0, (room - shown) / 2)
    return FormulaLayout(p, start, end, top, scrolled)


def formula_row(lay: FormulaLayout, i: int, snap: int) -> tuple[float, float]:
    """Line i's centre y and its height in snapshot `snap`."""
    y = lay.top - sum(lay.pitch[lay.start[snap]:i])
    return y - lay.pitch[i] / 2, lay.pitch[i]
