"""
Deterministic Manim scene templates — Component 4, Week-1 scope.

Built directly from a Segment's beats without any LLM call. Two roles:
  1. The final tier of the repair ladder in renderer.py: if LLM-generated
     code fails after every repair attempt, a template guarantees the
     segment still produces *some* usable video instead of a hard failure.
  2. The Day-1 smoke test that Manim + LaTeX + Cairo + ffmpeg all work
     together, independent of any LLM call — run:
         uv run python -m animation_agent.templates --smoke
"""

from __future__ import annotations

import textwrap

from syllabyte_common.models import Segment

FRAME_WIDTH = 4.5
FRAME_HEIGHT = 8.0
SAFE_WIDTH = FRAME_WIDTH - 0.6
SAFE_HEIGHT = FRAME_HEIGHT - 0.8


def build_template_scene(segment: Segment, class_name: str) -> str:
    """Returns Manim Python source (as text) for a deterministic scene, used
    as the final tier of the repair ladder when every LLM attempt fails.
    Beats' visuals are free text with no "kind" to dispatch on, so this
    can't draw them — it shows each beat's sentence as a caption during
    that beat (still synced via end_beat), guaranteeing *some* video
    instead of a hard failure."""
    blocks = []
    for n, beat in enumerate(segment.beats, 1):
        fade_previous = "self.play(FadeOut(line), run_time=0.3)\n        " if n > 1 else ""
        blocks.append(f"""\
        # === Beat {n} ===
        {fade_previous}line = Text({textwrap.fill(beat.narration, 22)!r}, font_size=36, color=WHITE)
        self.place_in_area(line, "B1", "E6")
        line.scale_to_fit_width(min(line.width, {SAFE_WIDTH:.2f}))
        line.scale_to_fit_height(min(line.height, {SAFE_HEIGHT * 0.6:.2f}))
        self.play(FadeIn(line), run_time=0.4)
        self.end_beat({n})
""")

    return f"""from manim import *

from animation_agent.layout import GridLayoutScene


class {class_name}(GridLayoutScene):
    def construct(self):
        self.setup_grid()

{chr(10).join(blocks)}"""


if __name__ == "__main__":
    import argparse
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Render a smoke-test scene")
    parser.add_argument("--quality", default="low", choices=["low", "high"])
    parser.add_argument("--out", default="runs/smoke")
    args = parser.parse_args()

    if not args.smoke:
        print("Usage: python -m animation_agent.templates --smoke")
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    import json

    from animation_agent.layout import BEATS_FILE
    from animation_agent.manim_config import write_manim_cfg
    from syllabyte_common.models import Beat, SlideRef

    segment = Segment(
        phase="deliver",
        beats=[
            Beat(narration="This is a smoke test.", visual="-"),
            Beat(narration="It checks that Manim, Cairo, and ffmpeg work.", visual="-"),
        ],
        source_refs=[SlideRef(deck_name="smoke", slide_number=1)],
    )
    (out_dir / BEATS_FILE).write_text(json.dumps([2.0, 3.0]))
    code = build_template_scene(segment, class_name="SmokeTest")
    scene_path = out_dir / "smoke_scene.py"
    scene_path.write_text(code)
    print(f"Wrote {scene_path}")

    # NOTE: deliberately not using `-ql`/`-qh`/`--resolution` — see
    # renderer.py's module docstring for why those don't produce a correct
    # portrait camera frame in Manim 0.21. A manim.cfg file does.
    write_manim_cfg(out_dir, args.quality)
    cmd = ["manim", "render", str(scene_path.name), "SmokeTest"]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    print(result.stdout[-3000:])
    if result.returncode != 0:
        print("--- STDERR ---")
        print(result.stderr[-3000:])
        sys.exit(1)
    print("Smoke test render succeeded.")
