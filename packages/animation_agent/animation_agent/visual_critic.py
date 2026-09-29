"""
Visual Critic — Component 4, Code2Video-inspired visual anchor prompt.

The original version of this module asked a VLM for a bare ok/issues verdict
("the label overlaps the formula"). That's a real finding, but it's not
actionable: a text-only critic can see a problem without being able to say
*where* to move the offending object, because it has no reliable way to
reason about continuous (x, y) coordinates from pixels alone. Code2Video
(https://github.com/showlab/Code2Video) solves this by discretizing the
canvas into a named 6x6 grid (see layout.py) and asking the critic to name a
new grid cell instead of a coordinate delta — "move `label` to C2" is a
token the model can commit to; "move it left by 0.4 units" mostly isn't.

We keep their two-part design: (1) an occupancy table built by statically
parsing the code's place_at_grid/place_in_area calls, so every mobject is
indexable back to its source line before the VLM even looks at the frames;
(2) a structured critique — one JSON object per problem, each naming the
line to change and the literal grid call to change it to — which
apply_visual_repair() feeds back to Claude as a to-do list rather than a
vague prose complaint. One repair round is attempted; if the repaired
render still fails (or still has issues), the pre-repair render is kept
rather than looping indefinitely (see renderer.py).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from syllabyte_common.llm import DEFAULT_MODEL, image_block, structured, text, text_block
from syllabyte_common.models import RunManifest

from animation_agent.layout import GRID_DIAGRAM, format_occupancy_table, parse_grid_calls
from animation_agent.manim_codegen import validate_generated_code


class LayoutIssue(BaseModel):
    problem: str = Field(description="Concise description of the visual defect.")
    solution: str = Field(
        description="The literal replacement call, e.g. \"self.place_at_grid(label, 'C2', scale_factor=0.7)\"."
    )
    line_number: int = Field(description="1-indexed line in the given code that this solution replaces.")
    object_affected: str = Field(description="The variable name of the mobject being repositioned.")


class LayoutCritique(BaseModel):
    has_issues: bool
    improvements: list[LayoutIssue] = Field(default_factory=list)


SYSTEM_PROMPT = f"""\
You are the Visual Critic in SyllaByte. You are shown 3 frames (at roughly \
25%, 50%, and 90% through a short animated clip for a 9:16 phone screen), \
plus the clip's current grid occupancy table.

{GRID_DIAGRAM}
Every mobject in this clip was placed with `self.place_at_grid(obj, POS, \
scale_factor=S)` or `self.place_in_area(obj, TOP_LEFT, BOTTOM_RIGHT, \
scale_factor=S)`. The occupancy table below tells you which source line \
placed each object and where.

LAYOUT ASSESSMENT — check for, in order of severity:
  - Overlap: two objects' cells intersect, or they visually collide even in \
adjacent cells.
  - Off-screen / clipped: an object's scale_factor is too large for its \
cell(s), pushing it outside the safe frame.
  - Illegible: text crammed into a cell too small to read at phone-screen \
size.
  - Imbalance: a large empty region while other cells are crowded.

For each issue found (list at most 3, worst first), you MUST give a \
concrete fix: a new grid position and/or scale_factor for the affected \
object, expressed as the exact `self.place_at_grid(...)` or \
`self.place_in_area(...)` call that should replace the line named. Do not \
report a problem without a corresponding grid-based solution — "it's \
misplaced" is not actionable, "move it to C2 at scale_factor=0.7" is. \
Later solutions must not reuse a cell claimed by an earlier one.

Report has_issues=false only if none of the above are present in any frame.\
"""


def _extract_frames(video_path: Path, fractions: tuple[float, ...] = (0.25, 0.5, 0.9)) -> list[Path]:
    duration_result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    duration = float(duration_result.stdout.strip())

    tmp_dir = Path(tempfile.mkdtemp(prefix="visual_critic_"))
    frame_paths = []
    for i, frac in enumerate(fractions):
        ts = max(0.01, duration * frac)
        out_path = tmp_dir / f"frame_{i}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", str(video_path), "-frames:v", "1", "-update", "1", str(out_path)],
            check=True, capture_output=True,
        )
        frame_paths.append(out_path)
    return frame_paths


def critique_render(
    video_path: Path,
    code: str,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> LayoutCritique:
    """Critiques a rendered segment's layout against the grid occupancy
    table statically parsed from its source (`code`)."""
    frames = _extract_frames(video_path)
    occupancy = format_occupancy_table(parse_grid_calls(code))
    content = [image_block(f) for f in frames] + [
        text_block(
            "These are frames from one rendered clip, in chronological order.\n\n"
            f"Current grid occupancy:\n{occupancy}\n\nCritique the layout."
        )
    ]
    try:
        return structured(
            schema=LayoutCritique,
            content=content,
            system=SYSTEM_PROMPT,
            stage="visual_critic",
            model=model,
            max_tokens=1500,
            manifest=manifest,
        )
    finally:
        for f in frames:
            f.unlink(missing_ok=True)


def apply_visual_repair(
    code: str,
    critique: LayoutCritique,
    n_beats: int,
    class_name: str,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> str:
    """Feeds the Critic's line-anchored fixes back to Claude as a
    replacement to-do list, keeping everything else in the scene unchanged
    (see build_generation_prompt's grid rules — the code being repaired was
    already required to use place_at_grid/place_in_area throughout)."""
    todo = "\n".join(
        f"- Line {i.line_number} (`{i.object_affected}`): {i.problem}\n"
        f"  Replace with: {i.solution}"
        for i in critique.improvements
    )
    prompt = f"""\
You are a Manim Community Edition developer fixing layout issues in an \
existing scene. Apply ONLY the fixes listed below, each to the exact line \
number given — do not touch any other line, do not change any run_time, \
the class name (`{class_name}`), any narrative/animation content, or the \
{n_beats} `self.end_beat(N)` calls. Output the COMPLETE corrected Python \
source (every line, not just the changed ones), no explanation.

Fixes to apply:
{todo}

--- CODE ---
{code}
"""
    fixed = text(
        content=prompt, stage="visual_repair", model=model, max_tokens=6000, manifest=manifest,
    )
    return validate_generated_code(fixed)
