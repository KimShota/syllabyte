"""
Text-to-speech backends — Component 4 (Animation Agent), Week-1 scope.

Three interchangeable backends, selected with --tts on the CLI:
  - "kokoro" (default): Kokoro-82M, local, offline, no API key, good
    quality. Runs on CPU fine for short clips.
  - "say": macOS's built-in `say` command — zero-install fallback, lower
    quality, useful if Kokoro/espeak-ng aren't set up yet.
  - "elevenlabs": highest quality, requires ELEVENLABS_API_KEY and the
    `elevenlabs` extra (`uv sync --extra elevenlabs`).

Each backend implements synthesize(text, out_wav_path) -> duration_seconds.
Audio is synthesized BEFORE animation, one clip per beat (sentence): each
beat's duration is what that beat's animations are padded to fill (see
layout.GridLayoutScene.end_beat), so audio/video sync is driven by
narration length, sentence by sentence, not the other way around.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

import soundfile as sf

from syllabyte_common.models import Script, Segment, SegmentAudio

KOKORO_SAMPLE_RATE = 24000
DEFAULT_KOKORO_VOICE = "af_heart"
# Silence between beats (sentences) within a segment: a natural pause, and
# a moment for the viewer to take in the visual before the next one starts.
BEAT_GAP_SECONDS = 0.25

_kokoro_pipeline = None  # lazy singleton — loading the model takes a few seconds


class TTSBackend(Protocol):
    def synthesize(self, text: str, out_wav_path: Path) -> float: ...


class KokoroBackend:
    def __init__(self, voice: str = DEFAULT_KOKORO_VOICE, lang_code: str = "a"):
        self.voice = voice
        self.lang_code = lang_code

    def _pipeline(self):
        global _kokoro_pipeline
        if _kokoro_pipeline is None:
            from kokoro import KPipeline

            _kokoro_pipeline = KPipeline(lang_code=self.lang_code)
        return _kokoro_pipeline

    def synthesize(self, text: str, out_wav_path: Path) -> float:
        import numpy as np

        pipeline = self._pipeline()
        chunks = []
        for result in pipeline(text, voice=self.voice):
            if result.audio is not None:
                chunks.append(result.audio.numpy())
        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        out_wav_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_wav_path), audio, KOKORO_SAMPLE_RATE)
        return len(audio) / KOKORO_SAMPLE_RATE


class SayBackend:
    """macOS `say` -> AIFF -> ffmpeg -> WAV. Zero extra installs."""

    def __init__(self, voice: str = "Samantha"):
        self.voice = voice
        if shutil.which("say") is None:
            raise RuntimeError("`say` is only available on macOS")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg is required to convert `say`'s AIFF output to WAV")

    def synthesize(self, text: str, out_wav_path: Path) -> float:
        out_wav_path.parent.mkdir(parents=True, exist_ok=True)
        aiff_path = out_wav_path.with_suffix(".aiff")
        subprocess.run(["say", "-v", self.voice, "-o", str(aiff_path), text], check=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(aiff_path), str(out_wav_path)],
            check=True, capture_output=True,
        )
        aiff_path.unlink(missing_ok=True)
        info = sf.info(str(out_wav_path))
        return info.frames / info.samplerate


class ElevenLabsBackend:
    def __init__(self, voice_id: str | None = None):
        import os

        from elevenlabs.client import ElevenLabs  # requires `uv sync --extra elevenlabs`

        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")
        self.client = ElevenLabs(api_key=api_key)
        self.voice_id = voice_id or "21m00Tcm4TlvDq8ikWAM"  # "Rachel", a default stock voice

    def synthesize(self, text: str, out_wav_path: Path) -> float:
        out_wav_path.parent.mkdir(parents=True, exist_ok=True)
        audio_bytes = b"".join(
            self.client.text_to_speech.convert(
                voice_id=self.voice_id, text=text, output_format="pcm_24000"
            )
        )
        import numpy as np

        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype("float32") / 32768.0
        sf.write(str(out_wav_path), audio, 24000)
        info = sf.info(str(out_wav_path))
        return info.frames / info.samplerate


def get_backend(name: str) -> TTSBackend:
    if name == "kokoro":
        return KokoroBackend()
    if name == "say":
        return SayBackend()
    if name == "elevenlabs":
        return ElevenLabsBackend()
    raise ValueError(f"Unknown TTS backend: {name!r}")


# --------------------------------------------------------------------------
# Segment-level orchestration
# --------------------------------------------------------------------------


def _synthesize_beats(backend: TTSBackend, seg: Segment, wav_path: Path) -> list[float]:
    """Synthesizes each beat's sentence as its own clip, then joins them
    (with BEAT_GAP_SECONDS of silence between beats) into one segment WAV.
    Returns each beat's duration, gap included, so the scene can end beat
    N's animations exactly when sentence N finishes."""
    import numpy as np

    chunks, durations = [], []
    sample_rate = None
    for j, beat in enumerate(seg.beats):
        beat_path = wav_path.with_name(f"{wav_path.stem}_beat_{j}.wav")
        backend.synthesize(beat.narration, beat_path)
        audio, sample_rate = sf.read(str(beat_path), dtype="float32")
        beat_path.unlink(missing_ok=True)
        if j < len(seg.beats) - 1:
            gap = np.zeros((int(BEAT_GAP_SECONDS * sample_rate), *audio.shape[1:]), dtype="float32")
            audio = np.concatenate([audio, gap])
        chunks.append(audio)
        durations.append(len(audio) / sample_rate)
    sf.write(str(wav_path), np.concatenate(chunks), sample_rate)
    return durations


def synthesize_segments(
    script: Script, audio_dir: Path, backend_name: str = "kokoro"
) -> list[SegmentAudio]:
    backend = get_backend(backend_name)
    results: list[SegmentAudio] = []
    t = 0.0
    for i, seg in enumerate(script.segments):
        wav_path = audio_dir / f"seg_{i}.wav"
        beat_durations = _synthesize_beats(backend, seg, wav_path)
        duration = sum(beat_durations)
        results.append(
            SegmentAudio(
                segment_index=i,
                wav_path=str(wav_path),
                duration_seconds=duration,
                srt_start=t,
                srt_end=t + duration,
                beat_durations=beat_durations,
            )
        )
        t += duration
    return results


def concat_wavs(segment_audios: list[SegmentAudio], out_path: Path) -> Path:
    """Concatenate segment WAVs into one narration track via ffmpeg's
    concat demuxer (all Kokoro/say/ElevenLabs outputs share sample format,
    so a simple concat is safe)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{Path(sa.wav_path).resolve()}'" for sa in segment_audios)
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), str(out_path)],
        check=True, capture_output=True,
    )
    list_file.unlink(missing_ok=True)
    return out_path


def _split_into_cues(text: str, start: float, end: float, max_chars: int = 42) -> list[tuple[float, float, str]]:
    """Split one segment's narration into SRT-sized cues, splitting at
    sentence boundaries and allotting time proportional to character count."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return [(start, end, text)]

    total_chars = sum(len(s) for s in sentences)
    duration = end - start
    cues: list[tuple[float, float, str]] = []
    t = start
    for sentence in sentences:
        frac = len(sentence) / total_chars if total_chars else 1 / len(sentences)
        seg_end = t + duration * frac
        # Further wrap long sentences into <=max_chars chunks for on-screen legibility.
        words = sentence.split()
        line, lines = "", []
        for w in words:
            if len(line) + len(w) + 1 > max_chars:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        if line:
            lines.append(line)
        cues.append((t, seg_end, "\n".join(lines)))
        t = seg_end
    return cues


def _fmt_srt_time(seconds: float) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    ms = int((s - int(s)) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def build_srt(script: Script, segment_audios: list[SegmentAudio], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    cue_num = 1
    for seg, sa in zip(script.segments, segment_audios):
        if len(sa.beat_durations) == len(seg.beats):
            # Exact per-sentence timing from the per-beat clips.
            cues, t = [], sa.srt_start
            for beat, duration in zip(seg.beats, sa.beat_durations):
                cues += _split_into_cues(beat.narration, t, t + duration)
                t += duration
        else:
            cues = _split_into_cues(seg.narration, sa.srt_start, sa.srt_end)
        for start, end, text in cues:
            lines.append(str(cue_num))
            lines.append(f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}")
            lines.append(text)
            lines.append("")
            cue_num += 1
    out_path.write_text("\n".join(lines))
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", required=True, help="Text to synthesize")
    parser.add_argument("--backend", default="kokoro", choices=["kokoro", "say", "elevenlabs"])
    parser.add_argument("--out", default="/tmp/tts_demo.wav")
    args = parser.parse_args()

    backend = get_backend(args.backend)
    duration = backend.synthesize(args.demo, Path(args.out))
    print(f"Wrote {args.out} ({duration:.2f}s) via {args.backend}")
