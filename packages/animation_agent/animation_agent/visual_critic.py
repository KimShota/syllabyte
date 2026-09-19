"""
Visual Critic — Component 4, Week-1 stretch scope.

Extracts a few frames from a rendered segment and asks Claude (as a
vision-language critic, per the proposal's Code2Video-inspired design) to
flag element overlap, off-screen/clipped content, or illegible text. One
repair round is attempted on failure; if the repaired render still fails
the critic, the segment is kept as-is and the issue is logged in the report
rather than looping indefinitely.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from syllabyte_common.llm import DEFAULT_MODEL, image_block, structured, text_block
from syllabyte_common.models import RunManifest

SYSTEM_PROMPT = """\
You are the Visual Critic in SyllaByte. You are shown 3 frames (at roughly \
25%, 50%, and 90% through a short animated clip meant for a 9:16 phone \
screen). Check for:
  - Text or shapes overlapping each other, or overlapping so closely they \
are hard to read.
  - Content clipped by or extending past the frame edges.
  - Text that would be illegible at phone-screen size (too small, too much \
text crammed into one frame).

Report ok=True only if none of these problems are present in any frame.\
"""


class VisualCritiqueResult(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)


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
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> VisualCritiqueResult:
    frames = _extract_frames(video_path)
    content = [image_block(f) for f in frames] + [
        text_block("These are frames from one rendered clip, in chronological order. Critique them.")
    ]
    result = structured(
        schema=VisualCritiqueResult,
        content=content,
        system=SYSTEM_PROMPT,
        stage="visual_critic",
        model=model,
        max_tokens=1000,
        manifest=manifest,
    )
    for f in frames:
        f.unlink(missing_ok=True)
    return result
