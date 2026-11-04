"""
The part of the 9:16 video Manim draws (RenderSegment.frame).

"full" is the whole 9:16 frame. "dialogue" is its top 70%: the bottom 30% is the band where the speaking character
and the burned-in captions go (dialogue_band.py). Both are 4.5 units wide, so a font size looks the same in either;
the dialogue frame is just shorter. Pixel sizes keep the frame's aspect ratio exactly: manim.cfg sets
pixel_width/pixel_height and frame_height, and Manim derives frame_width = 4.5 from them (manim_config.py).

Inside a render (the manim subprocess), layout.py and layout_audit.py read the frame from Manim's own config, so
they match whatever manim.cfg said.
"""

from __future__ import annotations

from dataclasses import dataclass

from syllabyte_common.models import FrameName

MARGIN_X = 0.6  # 0.3 each side
MARGIN_Y = 0.8  # 0.4 top and bottom


@dataclass(frozen=True)
class Frame:
    name: FrameName
    width: float
    height: float
    pixels: dict[str, tuple[int, int]]  # quality -> (pixel_width, pixel_height)
    # The full video's pixel height at each quality (the band fills the rest).
    video_heights: dict[str, int]

    @property
    def safe_width(self) -> float:
        return self.width - MARGIN_X

    @property
    def safe_height(self) -> float:
        return self.height - MARGIN_Y


FULL = Frame("full", 4.5, 8.0, {"low": (540, 960), "high": (1080, 1920)}, {"low": 960, "high": 1920})
# 1344 = 70% of 1920; 4.5 * 1344 / 1080 = 5.6 units.
DIALOGUE = Frame("dialogue", 4.5, 5.6, {"low": (540, 672), "high": (1080, 1344)}, {"low": 960, "high": 1920})

FRAMES: dict[str, Frame] = {"full": FULL, "dialogue": DIALOGUE}


def frame_of(segment) -> Frame:
    """The frame a segment is drawn in (a plain Segment has no `frame`: the full one)."""
    return FRAMES[getattr(segment, "frame", "full")]


def scene_frame_size() -> tuple[float, float]:
    """Inside a render: the camera frame's (width, height), from Manim's config."""
    from manim import config

    return config.frame_width, config.frame_height


def scene_safe_size() -> tuple[float, float]:
    width, height = scene_frame_size()
    return width - MARGIN_X, height - MARGIN_Y
