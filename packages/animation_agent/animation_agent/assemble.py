"""
Final assembly — Component 4, Week-1 scope.

Per segment: sync the rendered Manim clip's duration to its narration
audio's duration (they should already match closely, since manim_prompt.py
told Claude the exact target duration — this step corrects small drift with
ffmpeg rather than trusting the LLM's arithmetic). Then concatenate all
segments and mux in the full narration track.

Outputs, per KU directory:
    final.mp4       — concatenated segments with narration audio
    captions.srt     — sidecar subtitles (not burned into the video)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from syllabyte_common.models import RenderResult, SegmentAudio

DRIFT_TOLERANCE_SECONDS = 0.05


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def sync_segment_to_audio(video_path: Path, target_duration: float, out_path: Path) -> float:
    """Pads (via tpad, cloning the last frame) or trims a rendered clip so
    its duration matches target_duration. Returns the drift (seconds,
    video - audio) BEFORE correction, for the report."""
    video_duration = ffprobe_duration(video_path)
    drift = video_duration - target_duration

    if abs(drift) <= DRIFT_TOLERANCE_SECONDS:
        out_path.write_bytes(video_path.read_bytes())
        return drift

    if video_duration < target_duration:
        pad_seconds = target_duration - video_duration
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-vf", f"tpad=stop_mode=clone:stop_duration={pad_seconds:.3f}",
                "-t", f"{target_duration:.3f}",
                str(out_path),
            ],
            check=True, capture_output=True,
        )
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-t", f"{target_duration:.3f}", str(out_path)],
            check=True, capture_output=True,
        )

    return drift


def concat_videos(video_paths: list[Path], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.with_suffix(".txt")
    list_file.write_text("\n".join(f"file '{p.resolve()}'" for p in video_paths))
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", str(out_path),
        ],
        check=True, capture_output=True,
    )
    list_file.unlink(missing_ok=True)
    return out_path


def mux_audio(video_path: Path, audio_path: Path, out_path: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path),
        ],
        check=True, capture_output=True,
    )
    return out_path


def assemble_ku_video(
    ku_dir: Path,
    render_results: list[RenderResult],
    segment_audios: list[SegmentAudio],
    narration_path: Path,
) -> dict:
    """Runs the full assembly pipeline for one Knowledge Unit's video.
    Returns a small dict of diagnostics (per-segment drift, output paths)
    for the report."""
    sync_dir = ku_dir / "render" / "synced"
    sync_dir.mkdir(parents=True, exist_ok=True)

    synced_paths: list[Path] = []
    drifts: list[float] = []
    for result, audio in zip(render_results, segment_audios):
        if result.video_path is None:
            raise RuntimeError(
                f"segment {result.segment_index} has no rendered video "
                f"(tier={result.tier}, error={result.error})"
            )
        synced_path = sync_dir / f"seg_{result.segment_index}.mp4"
        drift = sync_segment_to_audio(Path(result.video_path), audio.duration_seconds, synced_path)
        synced_paths.append(synced_path)
        drifts.append(drift)

    concatenated = ku_dir / "concatenated.mp4"
    concat_videos(synced_paths, concatenated)

    final = ku_dir / "final.mp4"
    mux_audio(concatenated, narration_path, final)

    concatenated.unlink(missing_ok=True)

    return {
        "final_path": str(final),
        "per_segment_drift_seconds": drifts,
        "max_abs_drift_seconds": max((abs(d) for d in drifts), default=0.0),
    }
