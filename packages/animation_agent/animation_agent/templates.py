"""
Deterministic Manim scene templates — Component 4, Week-1 scope.

Built directly from a VisualSpec without any LLM call. Two roles:
  1. The final tier of the repair ladder in renderer.py: if LLM-generated
     code fails after every repair attempt, a template guarantees the
     segment still produces *some* usable video instead of a hard failure.
  2. The Day-1 smoke test that Manim + LaTeX + Cairo + ffmpeg all work
     together, independent of any LLM call — run:
         uv run python -m animation_agent.templates --smoke
"""

from __future__ import annotations

from manim import DOWN, WHITE, YELLOW, FadeIn, Scene, Text, VGroup, Write

from syllabyte_common.models import VisualSpec

FRAME_WIDTH = 4.5
FRAME_HEIGHT = 8.0
SAFE_WIDTH = FRAME_WIDTH - 0.6


def _fit(mobject, max_width: float = SAFE_WIDTH):
    if mobject.width > max_width:
        mobject.scale_to_fit_width(max_width)
    return mobject


def build_template_scene(visual: VisualSpec, duration: float, class_name: str) -> str:
    """Returns Manim Python source (as text) for a deterministic scene, used
    as the final tier of the repair ladder when every LLM attempt fails.
    Since VisualSpec has no "kind" to dispatch on (Code2Video-style: every
    segment is just a title + free-text animation_steps), this can't
    specialize per content type — it just shows the title plus up to 3
    steps as plain text, guaranteeing *some* video instead of a hard
    failure."""
    title_run_time = 0.6 if visual.title else 0.0
    steps_run_time = min(2.0, duration * 0.4)
    title_block = ""
    if visual.title:
        title_block = f"""
        title = Text("{visual.title}", font_size=44, color=YELLOW)
        title.scale_to_fit_width(min(title.width, {SAFE_WIDTH:.2f}))
        self.play(FadeIn(title), run_time={title_run_time:.2f})
"""
    step_lines = "\n".join(
        f'            Text("{step[:60]}", font_size=28, color=WHITE),'
        for step in visual.animation_steps[:3]
    )
    body = title_block + f"""
        steps = VGroup(
{step_lines}
        ).arrange(DOWN, buff=0.3)
        steps.scale_to_fit_width(min(steps.width, {SAFE_WIDTH:.2f}))
        self.play(Write(steps), run_time={steps_run_time:.2f})
        self.wait(max(0.1, {duration:.2f} - {title_run_time:.2f} - {steps_run_time:.2f}))
"""

    return f"""from manim import *


class {class_name}(Scene):
    def construct(self):
{body}
"""


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

    from animation_agent.manim_config import write_manim_cfg

    spec = VisualSpec(
        title="Smoke Test",
        animation_steps=[
            r"Write the equation O(n) = c \cdot n \text{ for } n \geq n_0",
            "Fade out after a short pause",
        ],
    )
    code = build_template_scene(spec, duration=5.0, class_name="SmokeTest")
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
