"""
Grid-anchored layout — Component 4, Code2Video-inspired addition.

Code2Video (https://github.com/showlab/Code2Video) found that free-form
(x, y) placement is a poor interface for both the codegen LLM and the
visual Critic: a VLM can reliably *see* that "the label overlaps the
formula", but it cannot reliably say *how far* to move it in continuous
coordinates. Their fix — discretize the canvas into a named 6x6 grid, so
"move it to C2" is a single unambiguous token — carries over directly to
SyllaByte's vertical frame, even though our layout (no fixed left-hand
lecture column, single full-canvas frame) differs from their split
lecture-notes/animation layout.

`GridLayoutScene` is imported by name into every LLM-generated segment
(see manim_prompt.py's system prompt) rather than being textually
prepended to the generated file, so line numbers in generated code — which
the Critic's occupancy table and repair prompts reference — stay stable.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

import numpy as np
from manim import Mobject, Scene

from animation_agent.layout_audit import RULE_ORDER, audit_scene
from animation_agent.manim_prompt import (
    BEAT_OVERRUN_TOLERANCE_SECONDS,
    GRID_DIAGRAM,
    SAFE_HEIGHT,
    SAFE_WIDTH,
)

GRID_ROWS = ["A", "B", "C", "D", "E", "F"]
GRID_COLS = ["1", "2", "3", "4", "5", "6"]

# Written by renderer.py into the render dir (manim's cwd) before every
# render: the per-beat narration durations. Read here, by trusted code,
# rather than baked into the LLM's source, so the model can't get the
# numbers wrong — it only has to call end_beat(n) at the right places.
BEATS_FILE = "beats.json"

# Written by GridLayoutScene into the same dir after every beat: what the
# layout audit (layout_audit.py) found, and what placement auto-fixed.
# renderer.py reads it after a successful render.
LAYOUT_REPORT_FILE = "layout_report.json"

__all__ = [
    "GridLayoutScene", "GridCall", "parse_grid_calls", "format_occupancy_table",
    "GRID_DIAGRAM", "GRID_ROWS", "GRID_COLS", "BEATS_FILE", "LAYOUT_REPORT_FILE",
    "BeatOverrunError", "LayoutReport",
]

# How many findings a repair prompt lists; the rest wait for the next round.
MAX_FINDINGS_IN_PROMPT = 12


class BeatOverrunError(Exception):
    pass


@dataclass
class LayoutReport:
    """What GridLayoutScene's layout audit wrote for one render."""

    findings: list[dict]
    autofits: list[str]

    @classmethod
    def read(cls, render_dir: Path) -> LayoutReport:
        path = render_dir / LAYOUT_REPORT_FILE
        if not path.exists():
            return cls([], [])
        data = json.loads(path.read_text())
        return cls(data.get("findings", []), data.get("autofits", []))

    def issues(self) -> list[str]:
        """One line per finding, for RenderResult.visual_issues_remaining."""
        return [f"layout (beat {f['beat']}): {f['message']}" for f in self.findings]

    def format_for_prompt(self) -> str:
        lines = []
        for f in self.findings[:MAX_FINDINGS_IN_PROMPT]:
            where = f"beat {f['beat']}" + (f", after the animation ending on line {f['line']}" if f["line"] else "")
            lines.append(f"- [{where}] {f['message']}")
        if len(self.findings) > MAX_FINDINGS_IN_PROMPT:
            lines.append(f"- ...and {len(self.findings) - MAX_FINDINGS_IN_PROMPT} more of the same kinds.")
        if self.autofits:
            lines.append(
                "\nThe placement helper also had to rescue these placements because they didn't "
                "fit the frame. That shrank their labels too, so lay these diagrams out to fit "
                "(narrower, stacked vertically) instead of relying on it:"
            )
            lines += [f"- {a}" for a in self.autofits]
        return "\n".join(lines)


class GridLayoutScene(Scene):
    """Base class for every LLM-generated segment. `setup_grid()` maps each
    of the 36 cell names above to a fixed point in the safe frame area;
    `place_at_grid`/`place_in_area` are the only placement primitives the
    codegen prompt allows, so every mobject's position is always
    expressible as a small set of named anchors. `end_beat(n)` keeps each
    beat's animations aligned with its narration sentence.

    It also keeps every frame legible: placement shrinks anything bigger
    than the safe area to fit (and pulls it back inside), and the scene's
    end state after every animation is run through layout_audit, with
    findings written to LAYOUT_REPORT_FILE for renderer.py."""

    def setup(self) -> None:
        # Manim calls setup() before construct(), so the audit state exists
        # even if generated code animates before calling setup_grid().
        super().setup()
        self._beat = 1
        self._beat_has_content = False
        self._findings: dict[tuple, dict] = {}
        self._autofits: list[str] = []

    def play(self, *args, **kwargs) -> None:
        super().play(*args, **kwargs)  # wait() goes through here too
        self._audit()

    def _construct_frame(self) -> FrameType | None:
        frame = sys._getframe(1)
        while frame is not None and frame.f_code.co_name != "construct":
            frame = frame.f_back
        return frame

    def _variable_names(self, frame: FrameType | None) -> dict[int, str]:
        """id(mobject) -> its variable name in construct(), plus `name[i]`
        for the direct parts of named groups."""
        names: dict[int, str] = {}
        if frame is None:
            return names
        for name, value in frame.f_locals.items():
            if name == "self" or not isinstance(value, Mobject):
                continue
            names.setdefault(id(value), name)
            for i, sub in enumerate(value.submobjects):
                names.setdefault(id(sub), f"{name}[{i}]")
        return names

    def _audit(self) -> None:
        frame = self._construct_frame()
        findings, in_frame = audit_scene(
            self.mobjects, self._variable_names(frame), self.camera.background_color,
        )
        self._beat_has_content |= in_frame
        line = frame.f_lineno if frame is not None else None
        for f in findings:
            self._findings.setdefault(f.key, {"rule": f.rule, "beat": self._beat, "line": line, "message": f.message})

    def _write_layout_report(self) -> None:
        findings = sorted(self._findings.values(), key=lambda f: (RULE_ORDER.index(f["rule"]), f["beat"]))
        Path(LAYOUT_REPORT_FILE).write_text(json.dumps(
            {"findings": findings, "autofits": self._autofits}, indent=2,
        ))

    def setup_grid(self) -> None:
        self.grid: dict[str, np.ndarray] = {}
        for i, row in enumerate(GRID_ROWS):
            for j, col in enumerate(GRID_COLS):
                x = -SAFE_WIDTH / 2 + (j + 0.5) * (SAFE_WIDTH / len(GRID_COLS))
                y = SAFE_HEIGHT / 2 - (i + 0.5) * (SAFE_HEIGHT / len(GRID_ROWS))
                self.grid[f"{row}{col}"] = np.array([x, y, 0.0])

        beats_path = Path(BEATS_FILE)
        self.beat_durations: list[float] = (
            json.loads(beats_path.read_text()) if beats_path.exists() else []
        )

    def end_beat(self, n: int) -> None:
        """Ends beat `n` (1-indexed): waits until the moment narration
        sentence n finishes, so beat n+1's animations start exactly when
        sentence n+1 does. Raises if beat n's animations ran noticeably
        past its sentence (they'd push every later visual out of sync)."""
        if not 1 <= n <= len(self.beat_durations):
            raise ValueError(f"end_beat({n}) but this segment has {len(self.beat_durations)} beats")
        beat_end = sum(self.beat_durations[:n])
        remaining = beat_end - self.time
        if remaining < -BEAT_OVERRUN_TOLERANCE_SECONDS:
            raise BeatOverrunError(
                f"Beat {n}'s animations end at {self.time:.2f}s, but its narration "
                f"ends at {beat_end:.2f}s ({-remaining:.2f}s over). Shorten the "
                f"run_time values in beat {n} so they total under "
                f"{self.beat_durations[n - 1]:.2f}s."
            )
        if remaining > 0.01:
            self.wait(remaining)
        else:
            self._audit()

        if not self._beat_has_content:
            self._findings[("empty_beat", n)] = {
                "rule": "empty_beat", "beat": n, "line": None,
                "message": f"Beat {n} shows nothing on screen for its whole sentence. Make sure "
                           "its objects are added/animated in and placed inside the frame.",
            }
        self._beat = n + 1
        self._beat_has_content = False
        self._write_layout_report()

    def _fit_to_safe_area(self, mobject) -> None:
        """Shrinks `mobject` to the safe area if it's bigger, then shifts it
        back inside — the cheapest fix for the most common layout bug (a
        grid call whose scale_factor overflows the narrow frame)."""
        if mobject.width <= 0 and mobject.height <= 0:
            return
        factor = min(SAFE_WIDTH / max(mobject.width, 1e-6), SAFE_HEIGHT / max(mobject.height, 1e-6))
        if factor < 1:
            mobject.scale(factor)
        dx = max(-SAFE_WIDTH / 2 - mobject.get_left()[0], 0) - max(mobject.get_right()[0] - SAFE_WIDTH / 2, 0)
        dy = max(-SAFE_HEIGHT / 2 - mobject.get_bottom()[1], 0) - max(mobject.get_top()[1] - SAFE_HEIGHT / 2, 0)
        if factor < 1 or dx or dy:
            frame = self._construct_frame()
            name = next(
                (k for k, v in (frame.f_locals.items() if frame else []) if v is mobject and k != "self"),
                type(mobject).__name__,
            )
            fixes = []
            if factor < 1:
                fixes.append(f"scaled by {factor:.2f} to fit the safe area")
            if dx or dy:
                fixes.append(f"moved by ({dx:.2f}, {dy:.2f}) to stay inside it")
            self._autofits.append(f"line {frame.f_lineno if frame else '?'}: `{name}` {' and '.join(fixes)}")
            mobject.shift(np.array([dx, dy, 0.0]))

    def place_at_grid(self, mobject, grid_pos: str, scale_factor: float = 1.0):
        """Point-level placement — small elements (short labels, icons)."""
        mobject.scale(scale_factor)
        mobject.move_to(self.grid[grid_pos])
        self._fit_to_safe_area(mobject)
        return mobject

    def place_in_area(self, mobject, top_left: str, bottom_right: str, scale_factor: float = 1.0):
        """Region-level placement — larger elements (paragraphs, groups,
        equations, plots) centered in the bounding box spanned by the two
        corner anchors."""
        tl, br = self.grid[top_left], self.grid[bottom_right]
        center = np.array([(tl[0] + br[0]) / 2, (tl[1] + br[1]) / 2, 0.0])
        mobject.scale(scale_factor)
        mobject.move_to(center)
        self._fit_to_safe_area(mobject)
        return mobject


# --------------------------------------------------------------------------
# Occupancy table — lets the Critic point at a specific line/object instead
# of describing a layout problem in prose (see visual_critic.py).
# --------------------------------------------------------------------------

_POINT_RE = re.compile(
    r"self\.place_at_grid\(\s*([^,]+),\s*['\"]([A-F][1-6])['\"](?:,\s*scale_factor=([0-9.]+))?\s*\)"
)
_AREA_RE = re.compile(
    r"self\.place_in_area\(\s*([^,]+),\s*['\"]([A-F][1-6])['\"],\s*['\"]([A-F][1-6])['\"]"
    r"(?:,\s*scale_factor=([0-9.]+))?\s*\)"
)


@dataclass
class GridCall:
    object_name: str
    method: str  # "place_at_grid" | "place_in_area"
    position: str  # "B2" or "A1-C3"
    scale_factor: float | None
    line_number: int


def parse_grid_calls(code: str) -> list[GridCall]:
    """Extracts every place_at_grid/place_in_area call in `code`, in source
    order, with its 1-indexed line number — so a Critic-reported line
    number can be matched straight back to the object it concerns."""
    calls: list[GridCall] = []
    for line_number, line in enumerate(code.splitlines(), start=1):
        if m := _POINT_RE.search(line):
            calls.append(GridCall(
                object_name=m.group(1).strip(), method="place_at_grid", position=m.group(2),
                scale_factor=float(m.group(3)) if m.group(3) else None, line_number=line_number,
            ))
        elif m := _AREA_RE.search(line):
            calls.append(GridCall(
                object_name=m.group(1).strip(), method="place_in_area",
                position=f"{m.group(2)}-{m.group(3)}",
                scale_factor=float(m.group(4)) if m.group(4) else None, line_number=line_number,
            ))
    return calls


def format_occupancy_table(calls: list[GridCall]) -> str:
    if not calls:
        return "(no place_at_grid/place_in_area calls found in this code)"
    rows = [
        f"| {c.line_number} | {c.object_name} | {c.method} | {c.position} | {c.scale_factor or 'default'} |"
        for c in calls
    ]
    return "\n".join(["| line | object | method | position | scale |", "|---|---|---|---|---|", *rows])
