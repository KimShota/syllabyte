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

Once any LLM tier produces a rendering video, one Code2Video-inspired
Visual Critic pass (visual_critic.py) checks its grid-anchored layout and,
if it finds an issue, asks Claude for a targeted fix and re-renders. This
never risks the tier's already-working video: if the repaired code fails to
render, the original render is kept and the remaining issues are just
logged on the RenderResult for the report. Template-fallback renders skip
this pass — they're deterministic and don't use the LLM's grid placements.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from syllabyte_common.models import RenderResult, RunManifest, Segment

from animation_agent.assemble import ffprobe_duration
from animation_agent.layout import BEATS_FILE
from animation_agent.manim_codegen import (
    UnsafeCodeError,
    check_beat_structure,
    generate_scene,
    repair_scene,
)
from animation_agent.manim_config import write_manim_cfg
from animation_agent.templates import build_template_scene
from animation_agent.visual_critic import apply_visual_repair, critique_render

RENDER_TIMEOUT_SECONDS = 180
MAX_TIER1_REPAIRS = 2
# A render whose length is further than this from its narration audio is
# treated as a failure (e.g. a beat's visuals were dropped), not padded over.
MAX_DURATION_MISMATCH_SECONDS = 0.5


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


def _try_render(
    render_dir: Path, code: str, class_name: str, quality: str, n_beats: int, duration: float,
) -> tuple[bool, str, Path | None]:
    """Checks the beat structure, writes code to disk, and attempts a
    render, rejecting one whose length doesn't match the narration.
    Returns (ok, error_text, mp4_path)."""
    try:
        problem = check_beat_structure(code, n_beats)
    except SyntaxError as e:
        problem = f"SyntaxError: {e}"
    if problem:
        return False, problem, None

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

    video_duration = ffprobe_duration(mp4_path)
    if abs(video_duration - duration) > MAX_DURATION_MISMATCH_SECONDS:
        return False, (
            f"The rendered scene is {video_duration:.2f}s long but its narration is "
            f"{duration:.2f}s. Nothing may play or wait after the final "
            f"self.end_beat({n_beats})."
        ), None

    return True, "", mp4_path


def _visual_critic_pass(
    render_dir: Path,
    code: str,
    class_name: str,
    n_beats: int,
    duration: float,
    quality: str,
    mp4_path: Path,
    *,
    model: str,
    manifest: RunManifest | None,
) -> tuple[Path, bool, list[str]]:
    """One critique + (at most one) repair round on an already-successful
    LLM render. Returns (final_mp4_path, repair_applied, issues_remaining)."""
    try:
        critique = critique_render(mp4_path, code, model=model, manifest=manifest)
    except Exception as e:  # critic is best-effort — never fail the segment over it
        return mp4_path, False, [f"visual critic call failed: {e}"]

    if critique is None:  # e.g. empty/unparseable structured-output response
        return mp4_path, False, ["visual critic returned no result"]

    if not critique.has_issues:
        return mp4_path, False, []

    issues = [f"{i.object_affected}: {i.problem}" for i in critique.improvements]
    try:
        repaired_code = apply_visual_repair(
            code, critique, n_beats, class_name, model=model, manifest=manifest,
        )
    except (UnsafeCodeError, SyntaxError):
        return mp4_path, False, issues

    ok, _, repaired_mp4 = _try_render(
        render_dir, repaired_code, class_name, quality, n_beats, duration,
    )
    if ok:
        return repaired_mp4, True, []
    # The failed re-render overwrote the scene file; restore the code that
    # produced the kept video so the run dir stays consistent with it.
    (render_dir / f"{class_name}.py").write_text(code)
    return mp4_path, False, issues


def render_segment(
    segment: Segment,
    segment_index: int,
    beat_durations: list[float],
    render_dir: Path,
    *,
    quality: str = "low",
    model: str = "claude-opus-5",
    manifest: RunManifest | None = None,
) -> RenderResult:
    n_beats = len(segment.beats)
    if len(beat_durations) != n_beats:
        raise ValueError(
            f"segment {segment_index} has {n_beats} beats but {len(beat_durations)} beat "
            "durations — the audio predates this script; re-run with --from-stage tts"
        )
    duration = sum(beat_durations)
    render_dir.mkdir(parents=True, exist_ok=True)
    (render_dir / BEATS_FILE).write_text(json.dumps(beat_durations))
    class_name = f"Seg{segment_index}"
    start = time.monotonic()
    attempts = 0
    last_error = ""

    def try_render(code: str) -> tuple[bool, str, Path | None]:
        return _try_render(render_dir, code, class_name, quality, n_beats, duration)

    def critic_pass(code: str, mp4_path: Path) -> tuple[Path, bool, list[str]]:
        return _visual_critic_pass(
            render_dir, code, class_name, n_beats, duration, quality, mp4_path,
            model=model, manifest=manifest,
        )

    # --- First attempt -----------------------------------------------------
    try:
        code = generate_scene(segment, beat_durations, class_name, model=model, manifest=manifest)
    except (UnsafeCodeError, SyntaxError) as e:
        code, last_error = "", str(e)
    else:
        attempts += 1
        ok, last_error, mp4_path = try_render(code)
        if ok:
            mp4_path, repaired, issues = critic_pass(code, mp4_path)
            return RenderResult(
                segment_index=segment_index, tier="llm_first_try", attempts=attempts,
                render_seconds=time.monotonic() - start, video_path=str(mp4_path),
                visual_repair_applied=repaired, visual_issues_remaining=issues,
            )

    # --- Tier 1: targeted repair, up to MAX_TIER1_REPAIRS times ------------
    for _ in range(MAX_TIER1_REPAIRS):
        try:
            code = repair_scene(
                code, last_error, segment, beat_durations, class_name, model=model, manifest=manifest,
            )
        except (UnsafeCodeError, SyntaxError) as e:
            last_error = str(e)
            continue
        attempts += 1
        ok, last_error, mp4_path = try_render(code)
        if ok:
            mp4_path, repaired, issues = critic_pass(code, mp4_path)
            return RenderResult(
                segment_index=segment_index, tier="llm_repaired", attempts=attempts,
                render_seconds=time.monotonic() - start, video_path=str(mp4_path),
                visual_repair_applied=repaired, visual_issues_remaining=issues,
            )

    # --- Tier 2: full regeneration from the original spec, once -----------
    try:
        code = generate_scene(segment, beat_durations, class_name, model=model, manifest=manifest)
        attempts += 1
        ok, last_error, mp4_path = try_render(code)
        if ok:
            mp4_path, repaired, issues = critic_pass(code, mp4_path)
            return RenderResult(
                segment_index=segment_index, tier="llm_regenerated", attempts=attempts,
                render_seconds=time.monotonic() - start, video_path=str(mp4_path),
                visual_repair_applied=repaired, visual_issues_remaining=issues,
            )
    except (UnsafeCodeError, SyntaxError) as e:
        last_error = str(e)
        attempts += 1

    # --- Tier 3: deterministic template fallback (always renders) ---------
    template_code = build_template_scene(segment, class_name)
    ok, template_error, mp4_path = try_render(template_code)
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
