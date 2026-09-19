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

from manim import (
    BLUE,
    DOWN,
    UP,
    WHITE,
    YELLOW,
    FadeIn,
    FadeOut,
    MathTex,
    Scene,
    Text,
    VGroup,
    Write,
)

from syllabyte_common.models import VisualSpec

FRAME_WIDTH = 4.5
FRAME_HEIGHT = 8.0
SAFE_WIDTH = FRAME_WIDTH - 0.6


def _fit(mobject, max_width: float = SAFE_WIDTH):
    if mobject.width > max_width:
        mobject.scale_to_fit_width(max_width)
    return mobject


def build_template_scene(visual: VisualSpec, duration: float, class_name: str) -> str:
    """Returns Manim Python source (as text) for a deterministic scene
    matching the given VisualSpec kind. Used both as a live fallback
    (written to disk and rendered by renderer.py) and importable directly
    for the smoke test below."""
    kind = visual.kind

    if kind == "equation" and visual.equation_latex:
        body = f"""
        eq = MathTex(r"{visual.equation_latex}", color=WHITE)
        eq.scale_to_fit_width(min(eq.width, {SAFE_WIDTH:.2f}))
        self.play(Write(eq), run_time=min(2.0, {duration:.2f} * 0.4))
        self.wait({duration:.2f} - min(2.0, {duration:.2f} * 0.4))
"""
    elif kind == "bullets" and visual.bullets:
        lines = "\n".join(f'            Text("{b}", font_size=40, color=WHITE),' for b in visual.bullets[:4])
        title_line = f'Text("{visual.title}", font_size=48, color=YELLOW)' if visual.title else 'Text("", font_size=1)'
        body = f"""
        title = {title_line}
        title.scale_to_fit_width(min(title.width, {SAFE_WIDTH:.2f}))
        title.to_edge(UP)
        bullets = VGroup(
{lines}
        ).arrange(DOWN, buff=0.4)
        bullets.scale_to_fit_width(min(bullets.width, {SAFE_WIDTH:.2f}))
        bullets.next_to(title, DOWN, buff=0.8)
        self.play(FadeIn(title), run_time=0.8)
        self.play(Write(bullets), run_time=min(2.5, {duration:.2f} * 0.5))
        self.wait(max(0.1, {duration:.2f} - 3.3))
"""
    else:
        # Generic title/text card — safe fallback for any kind we don't
        # have a dedicated template for (diagram, code, compare, plot).
        title_text = visual.title or "..."
        body = f"""
        card = Text("{title_text}", font_size=44, color=WHITE)
        card.scale_to_fit_width(min(card.width, {SAFE_WIDTH:.2f}))
        self.play(FadeIn(card), run_time=0.8)
        self.wait(max(0.1, {duration:.2f} - 0.8))
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

    spec = VisualSpec(kind="equation", equation_latex=r"O(n) = c \cdot n \text{ for } n \geq n_0")
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
