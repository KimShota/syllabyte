"""The scene file for a segment drawn from template calls: the calls as data, end_beat after each beat."""

from __future__ import annotations

from animation_agent.visuals.calls import check_segment, segment_draws


def build_spec_scene(segment, class_name: str) -> str | None:
    """Manim source that replays what the earlier segments left on screen (`segment.carried`), then plays the
    segment's calls, or None when the segment isn't drawn from templates or its calls don't pass
    calls.check_segment (the segment is then drawn by LLM code as before)."""
    carried = list(getattr(segment, "carried", None) or [])
    draws = segment_draws(segment)
    if draws is None and getattr(segment, "templates", False) and carried:
        draws = [[] for _ in segment.beats]  # every line keeps the carried picture
    if draws is None or check_segment(draws, carried=carried):
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
        run = SpecRunner(self, {draws!r}, carried={carried!r})
        run.setup()
{body}
"""
