"""
Manim code generation prompt — Component 4 (Animation Agent), Week-1 scope.

Constrains Claude to a curated Manim Community Edition API subset (per the
proposal's response to the LLM+Manim paper's 38% render-failure finding),
targets a vertical 9:16 frame, and requires the scene's total runtime to
match the segment's narration duration exactly (audio drives video, not the
other way around — see tts.py).
"""

from __future__ import annotations

from pathlib import Path

from syllabyte_common.models import Segment

EXAMPLES_DIR = Path(__file__).parent / "examples"


def _load_examples() -> str:
    """Loads the few-shot example scenes in examples/ (title card, bullet
    reveal, equation+plot) as a single formatted block for the system
    prompt. These use their own example class names — the model is told
    explicitly that its own output must use the class name it's given, not
    one of these."""
    names = ["title_card.py", "bullet_reveal.py", "equation_and_plot.py"]
    blocks = []
    for name in names:
        path = EXAMPLES_DIR / name
        if path.exists():
            blocks.append(f"# --- example: {name} ---\n{path.read_text().strip()}")
    return "\n\n".join(blocks)


_FEW_SHOT_EXAMPLES = _load_examples()

# Manim's default camera frame is 8 units tall; for a 1080x1920 (9:16)
# render Manim keeps frame_height=8 and derives frame_width = 8 * (9/16) = 4.5.
FRAME_WIDTH = 4.5
FRAME_HEIGHT = 8.0
SAFE_WIDTH = FRAME_WIDTH - 0.6  # ~0.3 margin each side
SAFE_HEIGHT = FRAME_HEIGHT - 0.8  # ~0.4 margin top/bottom

# Code2Video-style layout grid (github.com/showlab/Code2Video): discretizing
# the canvas into named anchors turns "where does this go" into a token an
# LLM/VLM can state unambiguously, instead of a continuous (x, y) neither
# can reliably reason about. See layout.py for the runtime implementation.
GRID_DIAGRAM = """\
6x6 layout grid over the safe frame area (A1 = top-left, F6 = bottom-right):
      1    2    3    4    5    6
  A   A1   A2   A3   A4   A5   A6
  B   B1   B2   B3   B4   B5   B6
  C   C1   C2   C3   C4   C5   C6
  D   D1   D2   D3   D4   D5   D6
  E   E1   E2   E3   E4   E5   E6
  F   F1   F2   F3   F4   F5   F6
"""

ALLOWED_API = """\
Allowed imports: `from manim import *` and \
`from animation_agent.layout import GridLayoutScene` — nothing else. No os, \
sys, subprocess, requests, open(), eval(), exec(), or __import__.

Allowed Mobjects: Text, MarkupText, MathTex, Tex, Axes, NumberPlane, \
NumberLine, Dot, Line, Arrow, Rectangle, Square, Circle, Polygon, VGroup, \
BraceLabel, SurroundingRectangle, Brace.

Allowed animations: Write, FadeIn, FadeOut, Create, Uncreate, Transform, \
ReplacementTransform, Indicate, Circumscribe, GrowArrow, DrawBorderThenFill.

Allowed scene methods: self.play(...), self.wait(...), self.add(...), \
self.remove(...), self.setup_grid(...), self.place_at_grid(...), \
self.place_in_area(...) (the last three come from GridLayoutScene — see \
Layout below).

Forbidden: any external file/network access, any Manim plugin, custom \
LaTeX preambles, ImageMobject (no image assets are available), \
ThreeDScene / 3D mobjects (this is a 2D short-form format).\
"""

def _build_system_prompt(duration: float, class_name: str) -> str:
    # Built directly as an f-string per call (rather than a stored template
    # + .format()) because the few-shot example source code contains its
    # own curly braces (dict literals, e.g. Axes' axis_config={...}), which
    # would collide with str.format()'s field syntax.
    return f"""\
You are the Animation and Video Synthesis Agent in SyllaByte. You write \
Manim Community Edition Python code for ONE segment of a 9:16 vertical \
educational short. Output ONLY the Python source code — no markdown code \
fences, no explanation, no comments about what you're about to do.

Frame geometry (CRITICAL — this is a vertical 9:16 video, not the Manim \
default 16:9):
  - The camera frame is {FRAME_WIDTH} units wide x {FRAME_HEIGHT} units tall.
  - Keep all mobjects within x in [-{SAFE_WIDTH/2:.2f}, {SAFE_WIDTH/2:.2f}] \
and y in [-{SAFE_HEIGHT/2:.2f}, {SAFE_HEIGHT/2:.2f}] — this is a NARROW \
frame, so prefer stacking content vertically over spreading it horizontally.
  - Every Text/MathTex/Tex object must render legibly: never use font_size \
below 36, and pick a `scale_factor` on the grid call below that keeps the \
object's rendered width comfortably inside its cell(s).
  - Use at most 2-3 mobjects on screen at once — this is a phone screen, \
not a lecture hall projector. Clear old content (FadeOut) before adding new
content when moving between distinct ideas within the segment.

Layout (CRITICAL — do not use raw .move_to()/.to_edge() coordinates):
  - The class MUST subclass `GridLayoutScene` (not `Scene` directly) and \
call `self.setup_grid()` as the first line of `construct()`.
  - Every mobject you place must be positioned with exactly one of:
      `self.place_at_grid(obj, 'B2', scale_factor=0.8)` — point-level, for \
small elements (short labels, single icons/symbols).
      `self.place_in_area(obj, 'A1', 'C3', scale_factor=0.7)` — region-level, \
for larger elements (paragraphs, equations, plots, VGroups).
  - This is the same grid the Critic will later use to describe layout \
fixes, so consistent use of it is what makes those fixes possible.

{GRID_DIAGRAM}
{ALLOWED_API}

Here are 3 example scenes showing the expected style, API usage, and \
frame-fitting discipline (their class names and durations are just for \
illustration — use the class name and duration you're given below, not \
theirs):

{_FEW_SHOT_EXAMPLES}

Content fidelity (CRITICAL): if the visual spec below includes \
`animation_steps`, you MUST render each step literally, in order, using \
only the allowed Mobjects — do not substitute a different concept (e.g. \
do not draw a generic function plot/equation/graph unless a step \
explicitly describes one). Immediately before the code implementing each \
step, add a comment `# === Step N ===` (matching that step's number in \
the spec) so every block of code traces back to the exact step it \
renders. If there are no `animation_steps` (e.g. kind is title/bullets/\
equation/plot), render the given fields directly instead.

Timing (CRITICAL): the class MUST run for EXACTLY {duration:.2f} seconds \
total, matching pre-recorded narration audio that will be muxed in \
afterward — not shorter, not longer. Sum every self.play(..., run_time=X) \
and self.wait(Y) call and make sure they total {duration:.2f} seconds. \
Pad with self.wait() at the end if your animations finish early.

Output format: `from manim import *` and \
`from animation_agent.layout import GridLayoutScene`, then a single Python \
class named `{class_name}(GridLayoutScene)` with a `construct(self)` \
method. No other top-level code.
"""


def build_generation_prompt(segment: Segment, duration: float, class_name: str) -> str:
    visual = segment.visual
    visual_desc = f"kind={visual.kind}\n"
    for field in (
        "title", "bullets", "equation_latex", "plot_description",
        "diagram_description", "code_snippet", "compare_left", "compare_right",
    ):
        value = getattr(visual, field)
        if value:
            visual_desc += f"{field}: {value}\n"
    if visual.animation_steps:
        numbered = "\n".join(f"  {i}. {step}" for i, step in enumerate(visual.animation_steps, 1))
        visual_desc += f"animation_steps (render each one literally, in order):\n{numbered}\n"

    system = _build_system_prompt(duration, class_name)
    user = f"""\
Segment phase: {segment.phase}
Narration (for timing/context only — do NOT render this text verbatim \
unless it's part of the visual spec below): "{segment.narration}"

Visual spec to render:
{visual_desc}
Target duration: {duration:.2f} seconds exactly.
Class name: {class_name}
"""
    return system, user


def build_repair_prompt(code: str, traceback_text: str, duration: float, class_name: str) -> str:
    return f"""\
The following Manim scene raised an error when rendered. Fix ONLY what's \
necessary to make it render successfully, keeping the same visual intent, \
class name `{class_name}`, and total runtime of {duration:.2f} seconds. \
Output ONLY the corrected Python source code, no explanation.

--- CODE ---
{code}

--- ERROR ---
{traceback_text}
"""
