"""
Manim rendering + repair ladder — Component 4, Week-1 scope.

IMPORTANT Manim quirk this module works around: passing `--resolution W,H`
(or `-ql`/`-qh`) on the `manim render` CLI only overrides pixel_width /
pixel_height — it does NOT recompute the camera's `frame_width`, so a
portrait `--resolution` produces a badly distorted (stretched) coordinate
frame (confirmed empirically: frame_height came out as ~25 units instead of
8). The fix is to never pass -q/-r on the CLI and instead write a
`manim.cfg` file next to the scene — manim's config-file digestion path
correctly derives frame_width = frame_height * aspect_ratio from the pixel
dimensions, giving the intended 4.5 x 8.0 unit portrait frame at any pixel
resolution, as long as the width:height ratio is kept at 9:16.

Repair ladder (ScopeRefine-inspired, per the proposal's response to the
LLM+Manim paper's 38% render-failure finding):
  Tier 1 (llm_repaired):    feed the error back to Claude for a targeted fix, x2
  Tier 2 (llm_regenerated): regenerate the whole segment's code from scratch, x1
  Tier 3 (template_fallback): deterministic template (always renders)
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from syllabyte_common.models import RenderResult, RunManifest, Segment

from animation_agent.manim_codegen import UnsafeCodeError, generate_scene, repair_scene
from animation_agent.manim_config import write_manim_cfg
from animation_agent.templates import build_template_scene

RENDER_TIMEOUT_SECONDS = 180
MAX_TIER1_REPAIRS = 2


def _run_manim(render_dir: Path, scene_file: Path, class_name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["manim", "render", str(scene_file.name), class_name],
        cwd=render_dir,
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT_SECONDS,
    )


def _find_output_mp4(render_dir: Path, class_name: str) -> Path | None:
    matches = [
        p for p in (render_dir / "media" / "videos").rglob(f"{class_name}.mp4")
        if "partial_movie_files" not in p.parts
    ]
    return matches[0] if matches else None


def _try_render(render_dir: Path, code: str, class_name: str, quality: str) -> tuple[bool, str, Path | None]:
    """Writes code to disk and attempts a render. Returns (ok, error_text, mp4_path)."""
    scene_file = render_dir / f"{class_name}.py"
    scene_file.write_text(code)
    write_manim_cfg(render_dir, quality)

    try:
        result = _run_manim(render_dir, scene_file, class_name)
    except subprocess.TimeoutExpired:
        return False, f"render timed out after {RENDER_TIMEOUT_SECONDS}s", None

    if result.returncode != 0:
        # Manim's Rich-formatted traceback is on stderr; keep it bounded.
        return False, result.stderr[-4000:], None

    mp4_path = _find_output_mp4(render_dir, class_name)
    if mp4_path is None:
        return False, "manim exited 0 but no output .mp4 was found", None

    return True, "", mp4_path


def render_segment(
    segment: Segment,
    segment_index: int,
    duration: float,
    render_dir: Path,
    *,
    quality: str = "low",
    model: str = "claude-opus-5",
    manifest: RunManifest | None = None,
) -> RenderResult:
    render_dir.mkdir(parents=True, exist_ok=True)
    class_name = f"Seg{segment_index}"
    start = time.monotonic()
    attempts = 0
    last_error = ""

    # --- First attempt -----------------------------------------------------
    try:
        code = generate_scene(segment, duration, class_name, model=model, manifest=manifest)
    except UnsafeCodeError as e:
        code, last_error = "", str(e)
    else:
        attempts += 1
        ok, last_error, mp4_path = _try_render(render_dir, code, class_name, quality)
        if ok:
            return RenderResult(
                segment_index=segment_index, tier="llm_first_try", attempts=attempts,
                render_seconds=time.monotonic() - start, video_path=str(mp4_path),
            )

    # --- Tier 1: targeted repair, up to MAX_TIER1_REPAIRS times ------------
    for _ in range(MAX_TIER1_REPAIRS):
        try:
            code = repair_scene(code, last_error, duration, class_name, model=model, manifest=manifest)
        except UnsafeCodeError as e:
            last_error = str(e)
            continue
        attempts += 1
        ok, last_error, mp4_path = _try_render(render_dir, code, class_name, quality)
        if ok:
            return RenderResult(
                segment_index=segment_index, tier="llm_repaired", attempts=attempts,
                render_seconds=time.monotonic() - start, video_path=str(mp4_path),
            )

    # --- Tier 2: full regeneration from the original spec, once -----------
    try:
        code = generate_scene(segment, duration, class_name, model=model, manifest=manifest)
        attempts += 1
        ok, last_error, mp4_path = _try_render(render_dir, code, class_name, quality)
        if ok:
            return RenderResult(
                segment_index=segment_index, tier="llm_regenerated", attempts=attempts,
                render_seconds=time.monotonic() - start, video_path=str(mp4_path),
            )
    except UnsafeCodeError as e:
        last_error = str(e)
        attempts += 1

    # --- Tier 3: deterministic template fallback (always renders) ---------
    template_code = build_template_scene(segment.visual, duration, class_name)
    ok, template_error, mp4_path = _try_render(render_dir, template_code, class_name, quality)
    attempts += 1
    if ok:
        return RenderResult(
            segment_index=segment_index, tier="template_fallback", attempts=attempts,
            render_seconds=time.monotonic() - start, video_path=str(mp4_path),
            error=f"LLM tiers failed; last LLM error: {last_error[:500]}",
        )

    # Even the template failed — this should only happen for an
    # environment problem (Manim/LaTeX/ffmpeg misconfigured), not a content
    # problem. Surface it clearly rather than silently returning no video.
    return RenderResult(
        segment_index=segment_index, tier="template_fallback", attempts=attempts,
        render_seconds=time.monotonic() - start, video_path=None,
        error=f"template fallback also failed: {template_error[:1000]}",
    )
