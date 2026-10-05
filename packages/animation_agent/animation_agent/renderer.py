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

A render only counts as a success if it also passes the layout audit
(layout_audit.py, run inside the scene by GridLayoutScene): nothing off
screen, overlapping, too small to read, or too low in contrast. A render
that fails it goes up the same ladder, with the audit's findings as the
"error". If every LLM tier still has findings, the render with the fewest
is kept (its findings are logged) rather than dropping to the template,
which shows no visuals at all.

Once an LLM tier produces a video, one Code2Video-inspired Visual Critic
pass (visual_critic.py) checks one frame per beat and, if it finds an
issue, asks Claude for a targeted fix and re-renders. This never risks the
tier's already-working video: if the repaired code fails to render, or
adds layout findings, the original render is kept and the remaining
issues are just logged on the RenderResult for the report. Template-
fallback renders skip this pass — they're deterministic and don't use the
LLM's grid placements.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from syllabyte_common.models import RenderResult, RenderTier, RunManifest, Segment

from animation_agent.assemble import ffprobe_duration
from animation_agent.layout import BEATS_FILE, LAYOUT_REPORT_FILE, LayoutReport
from animation_agent.manim_codegen import (
    UnsafeCodeError,
    check_beat_structure,
    generate_scene,
    repair_layout,
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
) -> tuple[bool, str, Path | None, LayoutReport]:
    """Checks the beat structure, writes code to disk, and attempts a
    render, rejecting one whose length doesn't match the narration.
    Returns (ok, error_text, mp4_path, layout_report); the layout report is
    only meaningful when ok."""
    no_report = LayoutReport([], [])
    try:
        problem = check_beat_structure(code, n_beats)
    except SyntaxError as e:
        problem = f"SyntaxError: {e}"
    if problem:
        return False, problem, None, no_report

    scene_file = render_dir / f"{class_name}.py"
    scene_file.write_text(code)
    write_manim_cfg(render_dir, quality)
    (render_dir / LAYOUT_REPORT_FILE).unlink(missing_ok=True)

    try:
        result = _run_manim(render_dir, scene_file, class_name)
    except subprocess.TimeoutExpired:
        return False, f"render timed out after {RENDER_TIMEOUT_SECONDS}s", None, no_report

    if result.returncode != 0:
        # Manim's Rich-formatted traceback is on stderr; keep it bounded.
        return False, result.stderr[-4000:], None, no_report

    mp4_path = _find_output_mp4(render_dir, class_name)
    if mp4_path is None:
        return False, "manim exited 0 but no output .mp4 was found", None, no_report

    video_duration = ffprobe_duration(mp4_path)
    if abs(video_duration - duration) > MAX_DURATION_MISMATCH_SECONDS:
        return False, (
            f"The rendered scene is {video_duration:.2f}s long but its narration is "
            f"{duration:.2f}s. Nothing may play or wait after the final "
            f"self.end_beat({n_beats})."
        ), None, no_report

    return True, "", mp4_path, LayoutReport.read(render_dir)


def _visual_critic_pass(
    render_dir: Path,
    code: str,
    class_name: str,
    beat_durations: list[float],
    quality: str,
    mp4_path: Path,
    layout: LayoutReport,
    *,
    model: str,
    manifest: RunManifest | None,
) -> tuple[Path, bool, list[str]]:
    """One critique + (at most one) repair round on an already-successful
    LLM render. The repair is kept only if it renders and doesn't add
    layout findings. Returns (final_mp4_path, repair_applied, issues_remaining)."""
    n_beats, duration = len(beat_durations), sum(beat_durations)
    try:
        critique = critique_render(mp4_path, code, beat_durations, model=model, manifest=manifest)
    except Exception as e:  # critic is best-effort — never fail the segment over it
        return mp4_path, False, layout.issues() + [f"visual critic call failed: {e}"]

    if critique is None:  # e.g. empty/unparseable structured-output response
        return mp4_path, False, layout.issues() + ["visual critic returned no result"]

    if not critique.has_issues:
        return mp4_path, False, layout.issues()

    issues = layout.issues() + [f"{i.object_affected}: {i.problem}" for i in critique.improvements]
    try:
        repaired_code = apply_visual_repair(
            code, critique, n_beats, class_name, model=model, manifest=manifest,
        )
    except (UnsafeCodeError, SyntaxError):
        return mp4_path, False, issues

    # The re-render overwrites the kept video, so set it aside first.
    kept = mp4_path.with_name(f"{mp4_path.stem}_before_critic.mp4")
    shutil.copy(mp4_path, kept)
    ok, _, repaired_mp4, repaired_layout = _try_render(
        render_dir, repaired_code, class_name, quality, n_beats, duration,
    )
    if ok and len(repaired_layout.findings) <= len(layout.findings):
        kept.unlink()
        return repaired_mp4, True, repaired_layout.issues()
    # Restore the code, video and layout report that the kept render produced.
    (render_dir / f"{class_name}.py").write_text(code)
    shutil.move(kept, mp4_path)
    _write_layout_report(render_dir, layout)
    return mp4_path, False, issues


def _write_layout_report(render_dir: Path, layout: LayoutReport) -> None:
    (render_dir / LAYOUT_REPORT_FILE).write_text(json.dumps(
        {"findings": layout.findings, "autofits": layout.autofits}, indent=2,
    ))


@dataclass
class _Candidate:
    """An LLM render that works but still has layout findings."""

    tier: RenderTier
    code: str
    mp4_path: Path  # where manim wrote it (later renders overwrite this)
    stash: Path  # a copy that survives later attempts
    layout: LayoutReport


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
    # Set when the latest code rendered but failed the layout audit; the
    # next repair then fixes layout instead of a crash.
    last_layout: LayoutReport | None = None
    best: _Candidate | None = None

    def finish(tier: RenderTier, code: str, mp4_path: Path, layout: LayoutReport) -> RenderResult:
        mp4_path, repaired, issues = _visual_critic_pass(
            render_dir, code, class_name, beat_durations, quality, mp4_path, layout,
            model=model, manifest=manifest,
        )
        return RenderResult(
            segment_index=segment_index, tier=tier, attempts=attempts,
            render_seconds=time.monotonic() - start, video_path=str(mp4_path),
            visual_repair_applied=repaired, visual_issues_remaining=issues,
        )

    def attempt(code: str, tier: RenderTier) -> RenderResult | None:
        """Renders `code`; returns the finished result if it renders and
        passes the layout audit, else records why not and returns None."""
        nonlocal attempts, last_error, last_layout, best
        attempts += 1
        ok, error, mp4_path, layout = _try_render(
            render_dir, code, class_name, quality, n_beats, duration,
        )
        if not ok:
            last_error, last_layout = error, None
            return None
        if not layout.findings:
            (render_dir / f"{class_name}_best.mp4").unlink(missing_ok=True)
            return finish(tier, code, mp4_path, layout)
        if best is None or len(layout.findings) < len(best.layout.findings):
            stash = render_dir / f"{class_name}_best.mp4"
            shutil.copy(mp4_path, stash)
            best = _Candidate(tier, code, mp4_path, stash, layout)
        last_error, last_layout = layout.format_for_prompt(), layout
        return None

    # --- First attempt -----------------------------------------------------
    try:
        code = generate_scene(segment, beat_durations, class_name, model=model, manifest=manifest)
    except (UnsafeCodeError, SyntaxError) as e:
        code, last_error = "", str(e)
    else:
        if (result := attempt(code, "llm_first_try")) is not None:
            return result

    # --- Tier 1: targeted repair, up to MAX_TIER1_REPAIRS times ------------
    for _ in range(MAX_TIER1_REPAIRS):
        try:
            if last_layout is not None:
                code = repair_layout(
                    code, last_layout.format_for_prompt(), segment, beat_durations, class_name,
                    model=model, manifest=manifest,
                )
            else:
                code = repair_scene(
                    code, last_error, segment, beat_durations, class_name, model=model, manifest=manifest,
                )
        except (UnsafeCodeError, SyntaxError) as e:
            last_error = str(e)
            continue
        if (result := attempt(code, "llm_repaired")) is not None:
            return result

    # --- Tier 2: full regeneration from the original spec, once -----------
    try:
        code = generate_scene(segment, beat_durations, class_name, model=model, manifest=manifest)
    except (UnsafeCodeError, SyntaxError) as e:
        last_error = str(e)
        attempts += 1
    else:
        if (result := attempt(code, "llm_regenerated")) is not None:
            return result

    # --- Best LLM render that still has layout findings -------------------
    if best is not None:
        (render_dir / f"{class_name}.py").write_text(best.code)
        shutil.move(best.stash, best.mp4_path)
        _write_layout_report(render_dir, best.layout)
        return finish(best.tier, best.code, best.mp4_path, best.layout)

    # --- Tier 3: deterministic template fallback (always renders) ---------
    template_code = build_template_scene(segment, class_name)
    ok, template_error, mp4_path, _ = _try_render(
        render_dir, template_code, class_name, quality, n_beats, duration,
    )
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
