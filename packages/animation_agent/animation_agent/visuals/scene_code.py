"""The scene file for a segment drawn from template calls: the calls as data, end_beat after each beat."""

from __future__ import annotations

from animation_agent.visuals.calls import check_segment, segment_draws


def build_spec_scene(segment, class_name: str) -> str | None:
    """Manim source that plays the segment's calls, or None when the segment has no calls or they don't pass
    calls.check_segment (the segment is then drawn by LLM code as before)."""
    draws = segment_draws(segment)
    if draws is None or check_segment(draws):
        return None
    beats = []
    for n, calls in enumerate(draws, 1):
        beats.append(f"        run.beat({n}, {calls!r})\n        self.end_beat({n})")
    body = "\n".join(beats)
    return f"""from manim import *

from animation_agent.layout import GridLayoutScene
from animation_agent.visuals.runner import SpecRunner


class {class_name}(GridLayoutScene):
    def construct(self):
        self.setup_grid()
        run = SpecRunner(self, {draws!r})
{body}
"""
