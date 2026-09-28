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

import re
from dataclasses import dataclass

import numpy as np
from manim import Scene

from animation_agent.manim_prompt import GRID_DIAGRAM, SAFE_HEIGHT, SAFE_WIDTH

GRID_ROWS = ["A", "B", "C", "D", "E", "F"]
GRID_COLS = ["1", "2", "3", "4", "5", "6"]

__all__ = [
    "GridLayoutScene", "GridCall", "parse_grid_calls", "format_occupancy_table",
    "GRID_DIAGRAM", "GRID_ROWS", "GRID_COLS",
]


class GridLayoutScene(Scene):
    """Base class for every LLM-generated segment. `setup_grid()` maps each
    of the 36 cell names above to a fixed point in the safe frame area;
    `place_at_grid`/`place_in_area` are the only placement primitives the
    codegen prompt allows, so every mobject's position is always
    expressible as a small set of named anchors."""

    def setup_grid(self) -> None:
        self.grid: dict[str, np.ndarray] = {}
        for i, row in enumerate(GRID_ROWS):
            for j, col in enumerate(GRID_COLS):
                x = -SAFE_WIDTH / 2 + (j + 0.5) * (SAFE_WIDTH / len(GRID_COLS))
                y = SAFE_HEIGHT / 2 - (i + 0.5) * (SAFE_HEIGHT / len(GRID_ROWS))
                self.grid[f"{row}{col}"] = np.array([x, y, 0.0])

    def place_at_grid(self, mobject, grid_pos: str, scale_factor: float = 1.0):
        """Point-level placement — small elements (short labels, icons)."""
        mobject.scale(scale_factor)
        mobject.move_to(self.grid[grid_pos])
        return mobject

    def place_in_area(self, mobject, top_left: str, bottom_right: str, scale_factor: float = 1.0):
        """Region-level placement — larger elements (paragraphs, groups,
        equations, plots) centered in the bounding box spanned by the two
        corner anchors."""
        tl, br = self.grid[top_left], self.grid[bottom_right]
        center = np.array([(tl[0] + br[0]) / 2, (tl[1] + br[1]) / 2, 0.0])
        mobject.scale(scale_factor)
        mobject.move_to(center)
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
