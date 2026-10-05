"""
UI manifest per video — plan §7.1. Pure post-processing of a finished KU
directory, no LLM:

    <ku>/ui/poster.jpg      frame at 25% of the video
    <ku>/ui/captions.vtt    WebVTT converted from audio/captions.srt
    <ku>/ui_manifest.json   duration, segment spans, checkpoint time,
                            transcript rows, cited slides

The web player renders the sidecar VTT itself (captions are never burned in),
pauses at `checkpoint.t`, and seeks to `checkpoint.rewatch_from` on
"Rewatch this part".
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from syllabyte_common.learner import Checkpoint, SegmentSpan, TranscriptRow

# Checkpoint rule (plan Q29/D5): exactly one per video, at the end of the LAST
# deliver segment, so it tests the main content and "Rewatch this part" jumps
# to the start of that same segment.
CHECKPOINT_PHASE = "deliver"


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def make_poster(video: Path, out: Path, at_fraction: float = 0.25) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    t = ffprobe_duration(video) * at_fraction
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", "scale=540:-1", "-q:v", "4", str(out)],
        check=True,
    )
    return out


_SRT_TIME = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")


def srt_to_vtt(srt_text: str) -> str:
    """SRT -> WebVTT: header, '.' instead of ',' in timestamps, cue numbers dropped."""
    blocks = [b for b in re.split(r"\n\s*\n", srt_text.strip()) if b.strip()]
    out = ["WEBVTT", ""]
    for block in blocks:
        lines = block.strip().splitlines()
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines:
            continue
        timing = _SRT_TIME.sub(r"\1.\2", lines[0])
        out.append(timing)
        out.extend(lines[1:])
        out.append("")
    return "\n".join(out)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'“(])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _clean_latex(s: str) -> str:
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\(quad|ldots|cdot|,|;)", " ", s)
    s = s.replace("\\", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def describe_visual(visual: dict | str | None) -> str | None:
    """Plain-text description of what is on screen, for the described transcript.
    Handles the new per-beat string and the legacy structured visual dict."""
    if not visual:
        return None
    if isinstance(visual, str):
        return visual.strip() or None
    title = (visual.get("title") or "").strip()
    kind = visual.get("kind") or "visual"
    body = None
    if visual.get("diagram_description"):
        body = visual["diagram_description"]
    elif visual.get("plot_description"):
        body = visual["plot_description"]
    elif visual.get("bullets"):
        body = "; ".join(visual["bullets"])
    elif visual.get("equation_latex"):
        body = "Equation: " + _clean_latex(visual["equation_latex"])
    elif visual.get("compare_left") or visual.get("compare_right"):
        body = f"Comparison. Left: {visual.get('compare_left') or ''}. Right: {visual.get('compare_right') or ''}"
    elif visual.get("code_snippet"):
        body = "Code snippet"
    label = kind.capitalize()
    pieces = [p for p in (title, body) if p]
    return f"{label}: " + " — ".join(pieces) if pieces else None


def _segment_rows(seg: dict, start: float, end: float, beat_durations: list[float]) -> list[TranscriptRow]:
    beats = seg.get("beats")
    if beats:  # current format: one sentence + one visual per beat
        rows: list[TranscriptRow] = []
        t = start
        for i, beat in enumerate(beats):
            rows.append(TranscriptRow(
                t=round(t, 2), narration=beat["narration"].strip(),
                visual=describe_visual(beat.get("visual")),
            ))
            t += beat_durations[i] if i < len(beat_durations) else (end - start) / len(beats)
        return rows

    # Legacy format: one narration paragraph + one structured visual per segment.
    # Time each sentence by its share of the characters, as tts._split_into_cues does.
    sentences = split_sentences(seg["narration"]) or [seg["narration"].strip()]
    total_chars = sum(len(s) for s in sentences) or 1
    rows, t = [], start
    for i, sentence in enumerate(sentences):
        rows.append(TranscriptRow(
            t=round(t, 2), narration=sentence,
            visual=describe_visual(seg.get("visual")) if i == 0 else None,
        ))
        t += (end - start) * len(sentence) / total_chars
    return rows


def build_ui_manifest(ku_dir: Path) -> dict:
    ku_dir = Path(ku_dir)
    video = ku_dir / "final.mp4"
    if not video.exists():
        raise FileNotFoundError(f"{video} — render this KU first")

    script = json.loads((ku_dir / "script.json").read_text())
    audio = json.loads((ku_dir / "audio" / "segment_audio.json").read_text())["items"]
    audio.sort(key=lambda a: a["segment_index"])
    segments_raw = script["segments"]
    if len(audio) != len(segments_raw):
        raise ValueError(f"{ku_dir.name}: {len(segments_raw)} script segments vs {len(audio)} audio clips")

    spans = [
        SegmentSpan(phase=seg["phase"], start=round(a["srt_start"], 3), end=round(a["srt_end"], 3))
        for seg, a in zip(segments_raw, audio)
    ]
    deliver = [i for i, s in enumerate(spans) if s.phase == CHECKPOINT_PHASE]
    if not deliver:
        raise ValueError(f"{ku_dir.name}: no deliver segment to place the checkpoint after")
    last = deliver[-1]

    transcript: list[TranscriptRow] = []
    for seg, span, a in zip(segments_raw, spans, audio):
        transcript.extend(_segment_rows(seg, span.start, span.end, a.get("beat_durations") or []))

    slides = sorted({r["slide_number"] for seg in segments_raw for r in seg["source_refs"]})

    ui = ku_dir / "ui"
    ui.mkdir(exist_ok=True)
    make_poster(video, ui / "poster.jpg")
    srt = ku_dir / "audio" / "captions.srt"
    (ui / "captions.vtt").write_text(srt_to_vtt(srt.read_text()))

    manifest = {
        "ku_id": script["ku_id"],
        "title": script["title"],
        "duration_s": round(ffprobe_duration(video), 2),
        "segments": [s.model_dump() for s in spans],
        "checkpoint_times": {
            "t": spans[last].end,
            "rewatch_from": spans[last].start,
            "segment_idx": last,
        },
        "transcript": [r.model_dump() for r in transcript],
        "source_slides": slides,
        "poster": "ui/poster.jpg",
        "vtt": "ui/captions.vtt",
    }
    (ku_dir / "ui_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def checkpoint_for(manifest: dict, item_id: str) -> Checkpoint:
    c = manifest["checkpoint_times"]
    return Checkpoint(t=c["t"], rewatch_from=c["rewatch_from"], item_id=item_id)


if __name__ == "__main__":  # python -m animation_agent.ui_manifest runs/dev/ku-x
    import sys

    for arg in sys.argv[1:]:
        m = build_ui_manifest(Path(arg))
        print(arg, "->", m["duration_s"], "s, checkpoint", m["checkpoint_times"])
