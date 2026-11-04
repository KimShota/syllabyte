"""
Vertical Manim render configuration — shared by renderer.py and
templates.py's smoke test.

See renderer.py's module docstring for why this exists: `manim render
--resolution W,H` (and -ql/-qh) do NOT correctly recompute the camera's
frame_width for a portrait aspect ratio in Manim 0.21 — only a manim.cfg
file, digested through manim's normal config-file path, does. Each frame
(frame.py) keeps its pixel sizes at its exact aspect ratio, and the file sets
frame_height, so the camera frame digests to 4.5 x 8.0 units for the full
9:16 frame and 4.5 x 5.6 for a dialogue video's top 70%.
"""

from __future__ import annotations

from pathlib import Path

from animation_agent.frame import FRAMES

FRAME_RATES = {"low": 24, "high": 30}
# The full frame's sizes, kept for callers that predate frames.
QUALITY_PRESETS = {q: (*FRAMES["full"].pixels[q], FRAME_RATES[q]) for q in FRAME_RATES}


def write_manim_cfg(render_dir: Path, quality: str, frame: str = "full") -> None:
    spec = FRAMES[frame]
    width, height = spec.pixels[quality]
    (render_dir / "manim.cfg").write_text(
        f"[CLI]\npixel_width = {width}\npixel_height = {height}\n"
        f"frame_height = {spec.height}\n"
        f"frame_rate = {FRAME_RATES[quality]}\ndisable_caching = True\n"
    )
