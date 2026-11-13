"""
Text-to-speech backends — Component 4 (Animation Agent), Week-1 scope.

Three interchangeable backends, selected with --tts on the CLI:
  - "kokoro" (default): Kokoro-82M, local, offline, no API key, good
    quality. Runs on CPU fine for short clips.
  - "say": macOS's built-in `say` command — zero-install fallback, lower
    quality, useful if Kokoro/espeak-ng aren't set up yet.
  - "elevenlabs": highest quality, requires ELEVENLABS_API_KEY and the
    `elevenlabs` extra (`uv sync --extra elevenlabs`).

Each backend implements synthesize(text, out_wav_path, voice=None) ->
duration_seconds. Kokoro also gives each word's timing (synthesize_words),
which the burned-in captions of dialogue videos follow; for the other
backends the timings are estimated from word length. In a dialogue script
each beat is read in its speaker's voice (syllabyte_common/cast.py).
Audio is synthesized BEFORE animation, one clip per beat (sentence): each
beat's duration is what that beat's animations are padded to fill (see
layout.GridLayoutScene.end_beat), so audio/video sync is driven by
narration length, sentence by sentence, not the other way around.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Protocol

import soundfile as sf

from syllabyte_common.models import DialogueScript, Script, Segment, SegmentAudio, WordTiming

KOKORO_SAMPLE_RATE = 24000
DEFAULT_KOKORO_VOICE = "af_heart"
# Silence between beats (sentences) within a segment: a natural pause, and
# a moment for the viewer to take in the visual before the next one starts.
BEAT_GAP_SECONDS = 0.25
# In a dialogue, the pause when the other character starts talking: short, so the back-and-forth stays snappy.
SPEAKER_GAP_SECONDS = 0.12

_kokoro_pipelines: dict[str, object] = {}  # one per accent; loading the model takes a few seconds


class TTSBackend(Protocol):
    def synthesize(self, text: str, out_wav_path: Path, voice: str | None = None) -> float: ...


def estimate_words(text: str, duration: float) -> list[WordTiming]:
    """Word timings spread over `duration` in proportion to each word's length: for backends that give none."""
    words = text.split()
    total = sum(len(w) for w in words) or 1
    timings, t = [], 0.0
    for w in words:
        end = t + duration * len(w) / total
        timings.append(WordTiming(word=w, start=t, end=end))
        t = end
    return timings


def _attach_punctuation(tokens: list[tuple[str, float | None, float | None]]) -> list[WordTiming]:
    """Kokoro's tokens with punctuation joined onto the word before it ("Peter" + "," -> "Peter,"), and tokens
    without a timestamp given the previous token's end."""
    words: list[WordTiming] = []
    last_end = 0.0
    for text, start, end in tokens:
        start = last_end if start is None else start
        end = start if end is None else end
        if words and not any(ch.isalnum() for ch in text):
            words[-1].word += text
            words[-1].end = max(words[-1].end, end)
        elif text.strip():
            words.append(WordTiming(word=text, start=start, end=end))
        last_end = end
    return words


class KokoroBackend:
    def __init__(self, voice: str = DEFAULT_KOKORO_VOICE):
        self.voice = voice

    @staticmethod
    def _pipeline(voice: str):
        # A Kokoro voice id starts with its accent's language code ("a" American, "b" British).
        lang_code = voice[0]
        if lang_code not in _kokoro_pipelines:
            from kokoro import KPipeline

            # one model for every accent: each pipeline loaded its own copy (the cast speaks American and British)
            shared = next((p.model for p in _kokoro_pipelines.values() if p.model is not None), True)
            _kokoro_pipelines[lang_code] = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M", model=shared)
        return _kokoro_pipelines[lang_code]

    def synthesize_words(self, text: str, out_wav_path: Path, voice: str | None = None) -> tuple[float, list[WordTiming]]:
        import numpy as np

        voice = voice or self.voice
        chunks, tokens = [], []
        offset = 0.0
        for result in self._pipeline(voice)(text, voice=voice):
            if result.audio is None:
                continue
            audio = result.audio.numpy()
            for tok in result.tokens or []:
                start = None if tok.start_ts is None else offset + tok.start_ts
                end = None if tok.end_ts is None else offset + tok.end_ts
                tokens.append((tok.text, start, end))
            chunks.append(audio)
            offset += len(audio) / KOKORO_SAMPLE_RATE
        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        out_wav_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_wav_path), audio, KOKORO_SAMPLE_RATE)
        duration = len(audio) / KOKORO_SAMPLE_RATE
        words = _attach_punctuation(tokens)
        return duration, words if words else estimate_words(text, duration)

    def synthesize(self, text: str, out_wav_path: Path, voice: str | None = None) -> float:
        return self.synthesize_words(text, out_wav_path, voice)[0]


class SayBackend:
    """macOS `say` -> AIFF -> ffmpeg -> WAV. Zero extra installs."""

    def __init__(self, voice: str = "Samantha"):
        self.voice = voice
        if shutil.which("say") is None:
            raise RuntimeError("`say` is only available on macOS")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg is required to convert `say`'s AIFF output to WAV")

    def synthesize(self, text: str, out_wav_path: Path, voice: str | None = None) -> float:
        # `voice` is a Kokoro id, which `say` doesn't have: both characters get this backend's voice.
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

    def synthesize(self, text: str, out_wav_path: Path, voice: str | None = None) -> float:
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


def _synthesize_beat(backend: TTSBackend, text: str, path: Path, voice: str | None) -> list[WordTiming]:
    if isinstance(backend, KokoroBackend):
        return backend.synthesize_words(text, path, voice)[1]
    return estimate_words(text, backend.synthesize(text, path, voice))


# Each line's audio by (backend, voice, words): a script whose lines changed after its voices started (the line
# check rewrote one) is spoken again only where it changed.
_BEAT_CACHE: dict[tuple, tuple] = {}
_BEAT_CACHE_MAX = 400


def _synthesize_beats(
    backend: TTSBackend, seg: Segment, wav_path: Path,
    voices: list[str | None] | None = None, gaps: list[float] | None = None,
) -> tuple[list[float], list[list[WordTiming]]]:
    """Synthesizes each beat's sentence as its own clip (in `voices[j]`, when
    given), then joins them, with `gaps[j]` seconds of silence after beat j
    (BEAT_GAP_SECONDS by default; none after the last), into one segment WAV.
    Returns each beat's duration, gap included, so the scene can end beat
    N's animations exactly when sentence N finishes, and each beat's word
    timings from the start of that beat."""
    import numpy as np

    chunks, durations, words = [], [], []
    sample_rate = None
    for j, beat in enumerate(seg.beats):
        voice = voices[j] if voices else None
        key = (type(backend).__name__, voice, beat.narration)
        if key in _BEAT_CACHE:  # spoken already (the voices start before the line check; it rewrites few lines)
            audio, sample_rate, beat_words = _BEAT_CACHE[key]
            words.append(beat_words)
        else:
            beat_path = wav_path.with_name(f"{wav_path.stem}_beat_{j}.wav")
            words.append(_synthesize_beat(backend, beat.narration, beat_path, voice))
            audio, sample_rate = sf.read(str(beat_path), dtype="float32")
            beat_path.unlink(missing_ok=True)
            _BEAT_CACHE[key] = (audio, sample_rate, words[-1])
            while len(_BEAT_CACHE) > _BEAT_CACHE_MAX:
                _BEAT_CACHE.pop(next(iter(_BEAT_CACHE)))
        if j < len(seg.beats) - 1:
            gap_seconds = gaps[j] if gaps else BEAT_GAP_SECONDS
            gap = np.zeros((int(gap_seconds * sample_rate), *audio.shape[1:]), dtype="float32")
            audio = np.concatenate([audio, gap])
        chunks.append(audio)
        durations.append(len(audio) / sample_rate)
    wav_path.parent.mkdir(parents=True, exist_ok=True)  # every line may have come from the cache
    sf.write(str(wav_path), np.concatenate(chunks), sample_rate)
    return durations, words


def _dialogue_voices_and_gaps(script: DialogueScript, i: int) -> tuple[list[str], list[float]]:
    """Segment i's beats in their speakers' voices, with a short pause where the other character takes over."""
    from syllabyte_common.cast import load_cast

    cast = load_cast()
    beats = script.segments[i].beats
    voices = [cast.of(b.speaker).voice for b in beats]
    gaps = [
        SPEAKER_GAP_SECONDS if j + 1 < len(beats) and beats[j + 1].speaker != b.speaker else BEAT_GAP_SECONDS
        for j, b in enumerate(beats)
    ]
    return voices, gaps


# One synthesis at a time per process: Kokoro's phonemizer (espeak-ng) isn't thread-safe, and two threads
# initialising it at once abort the whole process (seen with two video_jobs workers starting their voices together).
_SYNTH_LOCK = threading.Lock()


_WARM: set[tuple[str, str]] = set()


def _offline_if_cached(repo_id: str = "hexgrad/Kokoro-82M") -> None:
    """Skips the Hub's network checks once Kokoro's model is cached: each voice file's first use in a process
    asked the Hub over HTTP (about 5 s of HEAD requests per video, runs/picture-p2 timing)."""
    import os

    try:
        from huggingface_hub import constants, try_to_load_from_cache

        if isinstance(try_to_load_from_cache(repo_id, "config.json"), str):
            os.environ["HF_HUB_OFFLINE"] = "1"
            constants.HF_HUB_OFFLINE = True
    except Exception:  # best effort: online still works
        pass


def warm_voices(voices: list[str], backend_name: str = "kokoro") -> None:
    """Loads the voice model, its phonemizer and each voice by speaking one short word in it, so the narration
    starts speaking at once when the lines are ready (in a timed run the model, its files and its phonemizer took
    about 8 s of the voices' 19 s). Under the synthesis lock, so a synthesis that starts meanwhile waits for it."""
    if backend_name != "kokoro":
        return
    with _SYNTH_LOCK:
        _offline_if_cached()
        backend = get_backend(backend_name)
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            for v in dict.fromkeys(voices):
                if ("kokoro", v) in _WARM:
                    continue
                try:
                    backend.synthesize_words("Hi.", Path(tmp) / "warm.wav", voice=v)
                    _WARM.add(("kokoro", v))
                except Exception as e:  # the real synthesis reports any problem
                    print(f"[tts] warming voice {v} failed: {e}", flush=True)


def start_warming(voices: list[str], backend_name: str = "kokoro") -> threading.Thread:
    """warm_voices in a background thread (while the storyboard is planned and written)."""
    t = threading.Thread(target=warm_voices, args=(voices, backend_name), daemon=True, name="warm-voices")
    t.start()
    return t


def synthesize_segments(
    script: Script, audio_dir: Path, backend_name: str = "kokoro", on_segment=None,
) -> list[SegmentAudio]:
    """Every segment's narration. `on_segment(i, audio)` is called as each one is done, so its render can start
    while the rest are spoken."""
    with _SYNTH_LOCK:
        return _synthesize_segments(script, audio_dir, backend_name, on_segment)


def _synthesize_segments(script: Script, audio_dir: Path, backend_name: str, on_segment=None) -> list[SegmentAudio]:
    backend = get_backend(backend_name)
    results: list[SegmentAudio] = []
    t = 0.0
    for i, seg in enumerate(script.segments):
        wav_path = audio_dir / f"seg_{i}.wav"
        voices, gaps = _dialogue_voices_and_gaps(script, i) if isinstance(script, DialogueScript) else (None, None)
        beat_durations, beat_words = _synthesize_beats(backend, seg, wav_path, voices, gaps)
        duration = sum(beat_durations)
        results.append(
            SegmentAudio(
                segment_index=i,
                wav_path=str(wav_path),
                duration_seconds=duration,
                srt_start=t,
                srt_end=t + duration,
                beat_durations=beat_durations,
                beat_words=beat_words,
            )
        )
        t += duration
        if on_segment is not None:
            on_segment(i, results[-1])
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
