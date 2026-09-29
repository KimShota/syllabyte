"""
Manim code generation prompt — Component 4 (Animation Agent), Week-1 scope.

Constrains Claude to a curated Manim Community Edition API subset (per the
proposal's response to the LLM+Manim paper's 38% render-failure finding),
targets a vertical 9:16 frame, and structures every scene as one block per
beat (narration sentence), each ending in `self.end_beat(N)`, which pads to
that sentence's exact audio length (audio drives video, not the other way
around — see tts.py and layout.py).
"""

from __future__ import annotations

from pathlib import Path

from syllabyte_common.models import Segment

EXAMPLES_DIR = Path(__file__).parent / "examples"


def _load_examples() -> str:
    """Loads the few-shot example scenes in examples/ (a beat-synced
    evolving diagram, and an equation+plot) as a single formatted block for
    the system prompt. Both are deliberately visual-first — few-shot
    examples of title cards / bullet lists made the model default to
    text-on-screen. These use their own example class names — the model is
    told explicitly that its own output must use the class name it's
    given, not one of these."""
    names = ["beat_diagram.py", "equation_and_plot.py"]
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

# How far a beat's animations may run past the end of its narration
# sentence before layout.GridLayoutScene.end_beat fails the render (which
# feeds the repair ladder an actionable error). Small overruns are
# absorbed: end_beat waits to absolute sentence boundaries, so the next
# beat catches back up.
BEAT_OVERRUN_TOLERANCE_SECONDS = 0.4

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

Allowed Mobjects: Text, MathTex, Tex, Axes, NumberPlane, NumberLine, Dot, \
Line, DashedLine, Arrow, CurvedArrow, DoubleArrow, Rectangle, \
RoundedRectangle, Square, Circle, Triangle, Polygon, Arc, VGroup, \
BraceLabel, SurroundingRectangle, Brace.

Allowed animations: Write, FadeIn, FadeOut, Create, Uncreate, Transform, \
ReplacementTransform, Indicate, Circumscribe, Flash, GrowArrow, \
GrowFromCenter, GrowFromEdge, DrawBorderThenFill, MoveAlongPath, Rotate, \
LaggedStart, AnimationGroup, and the `.animate` syntax (e.g. \
`dot.animate.move_to(...)`, `box.animate.set_fill(GREEN, opacity=0.6)`, \
`bar.animate.stretch_to_fit_height(2, about_edge=DOWN)`).

Allowed scene methods: self.play(...), self.wait(...), self.add(...), \
self.remove(...), self.setup_grid(...), self.place_at_grid(...), \
self.place_in_area(...), self.end_beat(...) (the last four come from \
GridLayoutScene — see Layout and Timing below).

Forbidden: any external file/network access, any Manim plugin, custom \
LaTeX preambles, ImageMobject (no image assets are available), \
ThreeDScene / 3D mobjects (this is a 2D short-form format).\
"""

def _build_system_prompt(class_name: str) -> str:
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
  - Keep at most 2-3 distinct visual groups on screen at once — this is a \
phone screen, not a lecture hall projector. Within a segment, prefer \
evolving one diagram across beats (move, recolor, highlight, extend its \
parts) over clearing the screen; FadeOut only what the next beat no \
longer needs.

Layout (CRITICAL — do not use raw .move_to()/.to_edge() coordinates):
  - The class MUST subclass `GridLayoutScene` (not `Scene` directly) and \
call `self.setup_grid()` as the first line of `construct()`.
  - Every mobject you place must be positioned with exactly one of:
      `self.place_at_grid(obj, 'B2', scale_factor=0.8)` — point-level, for \
small elements (short labels, single icons/symbols).
      `self.place_in_area(obj, 'A1', 'C3', scale_factor=0.7)` — region-level, \
for larger elements (paragraphs, equations, plots, VGroups).
  - Parts of one diagram may be positioned relative to each other \
(.arrange(), .next_to(), axes.c2p()) — compose the diagram as a VGroup, \
then grid-place the whole group once and reveal/change its parts across \
beats.
  - This is the same grid the Critic will later use to describe layout \
fixes, so consistent use of it is what makes those fixes possible.

{GRID_DIAGRAM}
{ALLOWED_API}

Here are 2 example scenes showing the expected style, API usage, beat \
structure, and frame-fitting discipline (their class names, beats, and \
durations are just for illustration — use the ones you're given below):

{_FEW_SHOT_EXAMPLES}

Visual-first (CRITICAL): the viewer should understand each beat from the \
picture alone. Explain with shapes, arrows, dots, bars, and motion — \
objects moving, growing, changing color, transforming, being highlighted \
(Indicate / Circumscribe / SurroundingRectangle / Flash). Text is only for \
short labels attached to shapes (at most 3 words each) and for formulas. \
NEVER write the narration, a sentence, a bullet list, or a title card on \
screen.

Beats and timing (CRITICAL): the segment is a list of beats; each beat is \
one narration sentence plus the visual shown while it is spoken, and its \
duration is the exact length of that sentence's recorded audio.
  - Implement the beats in order. Start each with a comment \
`# === Beat N ===` and end each with `self.end_beat(N)`.
  - `self.end_beat(N)` waits until sentence N finishes, so beat N+1's \
animations start exactly when sentence N+1 does. Do not add your own \
padding waits — end_beat does that.
  - Keep each beat's self.play(..., run_time=X) calls (plus any short \
self.wait) totalling about 60-85% of that beat's duration. If they run \
more than {BEAT_OVERRUN_TOLERANCE_SECONDS}s past the beat's duration the \
render fails.
  - Only animate beat N's visual inside beat N — never show something \
before the sentence that talks about it.
  - `self.end_beat(<last beat>)` must be the final statement of \
construct(): nothing may play or wait after it.

Content fidelity (CRITICAL): render every beat's visual literally, using \
only the allowed Mobjects — do not substitute a different concept (e.g. \
do not draw a generic function plot/equation/graph unless a visual \
explicitly describes one).

Output format: `from manim import *` and \
`from animation_agent.layout import GridLayoutScene`, then a single Python \
class named `{class_name}(GridLayoutScene)` with a `construct(self)` \
method. No other top-level code.
"""


def format_beats(segment: Segment, beat_durations: list[float]) -> str:
    return "\n".join(
        f"Beat {n} ({duration:.2f}s)\n"
        f'  narrator says (context only — do NOT put this on screen): "{beat.narration}"\n'
        f"  visual to render: {beat.visual}"
        for n, (beat, duration) in enumerate(zip(segment.beats, beat_durations), 1)
    )


def build_generation_prompt(
    segment: Segment, beat_durations: list[float], class_name: str
) -> tuple[str, str]:
    system = _build_system_prompt(class_name)
    user = f"""\
Segment phase: {segment.phase}

Beats to render, in order ({len(segment.beats)} beats, \
{sum(beat_durations):.2f}s total):
{format_beats(segment, beat_durations)}

Class name: {class_name}
"""
    return system, user


def build_repair_prompt(
    code: str, traceback_text: str, segment: Segment, beat_durations: list[float], class_name: str,
) -> str:
    n_beats = len(beat_durations)
    return f"""\
The following Manim scene failed to render. Fix ONLY what's necessary to \
make it render successfully. Keep every beat's visual as specified below \
— never replace them with generic or placeholder content (no "Segment N" \
titles, no filler shapes). Keep class `{class_name}(GridLayoutScene)` \
(do NOT subclass Scene and do NOT define your own end_beat: it is inherited \
and does the audio sync). It must keep exactly {n_beats} beats: each beat \
block ends with `self.end_beat(N)` for N = 1..{n_beats} in order, and \
`self.end_beat({n_beats})` is the last statement of construct(). If the \
error says a beat overran, shorten that beat's run_time values. Output \
ONLY the corrected Python source code, no explanation.

The beats this scene must depict:
{format_beats(segment, beat_durations)}

--- CODE ---
{code}

--- ERROR ---
{traceback_text}
"""
