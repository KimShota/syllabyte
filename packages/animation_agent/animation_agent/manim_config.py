"""
Vertical (9:16) Manim render configuration — shared by renderer.py and
templates.py's smoke test.

See renderer.py's module docstring for why this exists: `manim render
--resolution W,H` (and -ql/-qh) do NOT correctly recompute the camera's
frame_width for a portrait aspect ratio in Manim 0.21 — only a manim.cfg
file, digested through manim's normal config-file path, does. Every quality
preset here is kept at exactly 9:16 so the camera frame always digests to
4.5 x 8.0 units (matching manim_prompt.py's FRAME_WIDTH/FRAME_HEIGHT).
"""

from __future__ import annotations

from pathlib import Path

QUALITY_PRESETS = {
    "low": (540, 960, 24),  # (pixel_width, pixel_height, frame_rate)
    "high": (1080, 1920, 30),
}


def write_manim_cfg(render_dir: Path, quality: str) -> None:
    width, height, fps = QUALITY_PRESETS[quality]
    (render_dir / "manim.cfg").write_text(
        f"[CLI]\npixel_width = {width}\npixel_height = {height}\n"
        f"frame_rate = {fps}\ndisable_caching = True\n"
    )
