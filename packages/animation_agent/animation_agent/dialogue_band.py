"""
The bottom band of a dialogue video: the speaking character and burned-in captions under the Manim animation.

Manim draws the top 70% of the 9:16 video (frame.py). This adds the bottom 30%:
  - only the character who is speaking, on their side (cast.json), cut in when they start a line;
  - the line as captions, 2-4 words at a time, timed to the spoken words (tts.py), on the other side. ALL CAPS,
    heavy white text with a black outline. A word that names something in the script's colour key is drawn in
    that colour, the same colour the diagram above gives it, so the caption points at the picture (signalling).
Captions show exactly the words spoken, so a viewer reading along never sees words they don't hear.

Each caption state is drawn as one PNG with Pillow and the PNGs are played with ffmpeg's concat demuxer for their
durations, then stacked under the animation (this ffmpeg has no libass to draw styled subtitles).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from syllabyte_common.cast import Cast, image_path, load_cast
from syllabyte_common.models import DialogueScript, SegmentAudio, Speaker, WordTiming

from animation_agent.frame import DIALOGUE

FONT_PATH = Path(__file__).parent / "fonts" / "Montserrat-ExtraBold.ttf"
MAX_CHUNK_WORDS = 3
MAX_CHUNK_CHARS = 18
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
FPS = {"low": 24, "high": 30}


@dataclass
class CaptionWord:
    text: str
    colour: tuple[int, int, int] = WHITE


@dataclass
class BandState:
    start: float
    end: float
    speaker: Speaker
    words: list[CaptionWord]


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------


def _stem(word: str) -> str:
    w = re.sub(r"[^\w]", "", word.lower())
    for suffix in ("es", "s"):
        if len(w) > 3 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


@cache
def _manim_rgb(name: str) -> tuple[int, int, int]:
    import manim

    hex_ = getattr(manim, name).to_hex().lstrip("#")
    return tuple(int(hex_[i: i + 2], 16) for i in (0, 2, 4))


MIN_HEAD_CHARS = 5  # a term's leading word alone must be at least this long to count ("eigenvector", not "zero")


def _term_phrases(term: str) -> list[list[str]]:
    """The word sequences that name a colour-key term in speech, longest first: the whole term, then its leading
    words ("eigenvalue λ scaling" -> "eigenvalue λ", "eigenvalue"), since terms are often longer than how the
    lines say them."""
    tokens = [s for s in (_stem(t) for t in re.split(r"[\s/]+", term)) if s]
    phrases = [tokens[:n] for n in range(len(tokens), 0, -1)]
    return [p for p in phrases if len(p) > 1 or len(p[0]) >= MIN_HEAD_CHARS]


def colour_words(words: list[str], colour_key: list) -> list[tuple[int, int, int]]:
    """Each word's caption colour: its colour-key term's colour where the words name a term, else white."""
    colours = [WHITE] * len(words)
    taken = [False] * len(words)
    stems = [_stem(w) for w in words]
    candidates = sorted(
        ((phrase, term.colour) for term in colour_key for phrase in _term_phrases(term.term)),
        key=lambda pc: -len(pc[0]),
    )
    for phrase, colour in candidates:
        n = len(phrase)
        for i in range(len(words) - n + 1):
            if stems[i: i + n] == phrase and not any(taken[i: i + n]):
                colours[i: i + n] = [_manim_rgb(colour)] * n
                taken[i: i + n] = [True] * n
    return colours


def chunk_words(words: list[WordTiming]) -> list[list[int]]:
    """Indices of the words shown together: at most MAX_CHUNK_WORDS words and MAX_CHUNK_CHARS letters, breaking
    after punctuation so a caption never runs across a sentence break."""
    chunks: list[list[int]] = []
    current: list[int] = []
    for i, w in enumerate(words):
        chars = sum(len(words[k].word) + 1 for k in current) + len(w.word)
        if current and (len(current) == MAX_CHUNK_WORDS or chars > MAX_CHUNK_CHARS):
            chunks.append(current)
            current = []
        current.append(i)
        if re.search(r"[.,?!;:—]$", w.word):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def band_timeline(script: DialogueScript, audios: list[SegmentAudio]) -> list[BandState]:
    """What the band shows, from 0 to the end of the narration, with no gaps."""
    from animation_agent.tts import estimate_words

    states: list[BandState] = []
    for seg, audio in zip(script.segments, audios):
        t = audio.srt_start
        for j, (beat, duration) in enumerate(zip(seg.beats, audio.beat_durations)):
            words = (audio.beat_words[j] if j < len(audio.beat_words) else []) or estimate_words(beat.narration, duration)
            colours = colour_words([w.word for w in words], script.colour_key)
            chunks = chunk_words(words)
            for k, chunk in enumerate(chunks):
                # The first chunk shows from the start of the line (the character cuts in), the others when their
                # first word is spoken; each stays until the next one, the last until the line ends.
                start = t if k == 0 else t + words[chunk[0]].start
                end = t + words[chunks[k + 1][0]].start if k + 1 < len(chunks) else t + duration
                states.append(BandState(
                    start=start, end=max(end, start), speaker=beat.speaker,
                    words=[CaptionWord(words[i].word.upper(), colours[i]) for i in chunk],
                ))
            if not chunks:
                states.append(BandState(start=t, end=t + duration, speaker=beat.speaker, words=[]))
            t += duration
    return states


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------


@cache
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


@cache
def _character_image(path: str, max_w: int, max_h: int) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    scale = min(max_w / img.width, max_h / img.height)
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def _pieces(words: list[CaptionWord]) -> list[CaptionWord]:
    """Hyphenated words split after each hyphen ("DIVIDE-", "AND-", "CONQUER"), so a long one can wrap."""
    out = []
    for w in words:
        parts = re.findall(r"[^-]+-|[^-]+$", w.text) or [w.text]
        out += [CaptionWord(part, w.colour) for part in parts]
    return out


def _wrap(words: list[CaptionWord], font: ImageFont.FreeTypeFont, max_w: int) -> list[list[CaptionWord]] | None:
    """Words in lines no wider than max_w, or None if one word alone is wider. A piece ending in a hyphen joins
    the next one on its line without a space."""
    space = font.getlength(" ")
    lines: list[list[CaptionWord]] = [[]]
    width = 0.0
    for w in words:
        ww = font.getlength(w.text)
        if ww > max_w:
            return None
        gap = 0.0 if not lines[-1] or lines[-1][-1].text.endswith("-") else space
        if lines[-1] and width + gap + ww > max_w:
            lines.append([])
            width, gap = 0.0, 0.0
        width += gap + ww
        lines[-1].append(w)
    return lines


def draw_band(state: BandState, cast: Cast, width: int, height: int, cast_dir: Path | None = None) -> Image.Image:
    band = Image.new("RGB", (width, height), BLACK)
    character = cast.of(state.speaker)
    margin = round(width * 0.03)
    img = _character_image(str(image_path(character, cast_dir)), round(width * 0.36), round(height * 0.94))
    x = margin if character.side == "left" else width - margin - img.width
    band.paste(img, (x, height - img.height), img)

    if not state.words:
        return band
    # Captions on the side away from the character.
    left, right = (x + img.width + margin, width - margin) if character.side == "left" else (margin, x - margin)
    box_w, box_h = right - left, round(height * 0.84)
    size, floor = round(height * 0.16), round(height * 0.11)
    words = _pieces(state.words)
    while True:
        font = _font(size)
        lines = _wrap(words, font, box_w)
        line_h = round(size * 1.15)
        if lines is not None and len(lines) <= 3 and line_h * len(lines) <= box_h or size <= floor:
            break
        size -= 2
    if lines is None:  # one piece is wider than the box even at the floor size: shrink just enough for it
        widest = max(font.getlength(w.text) for w in words)
        size = max(10, int(size * box_w / widest))
        font, line_h = _font(size), round(size * 1.15)
        lines = _wrap(words, font, box_w) or [words]
    draw = ImageDraw.Draw(band)
    stroke = max(2, round(size * 0.12))
    space = font.getlength(" ")
    y = (height - line_h * len(lines)) / 2
    for line in lines:
        gaps = [0.0 if w.text.endswith("-") else space for w in line[:-1]]
        line_w = sum(font.getlength(w.text) for w in line) + sum(gaps)
        cx = left + (box_w - line_w) / 2
        for k, w in enumerate(line):
            draw.text((cx, y), w.text, font=font, fill=w.colour, stroke_width=stroke, stroke_fill=BLACK)
            cx += font.getlength(w.text) + (gaps[k] if k < len(gaps) else 0)
        y += line_h
    return band


# --------------------------------------------------------------------------
# Composing
# --------------------------------------------------------------------------


def band_size(quality: str) -> tuple[int, int]:
    width, manim_h = DIALOGUE.pixels[quality]
    return width, DIALOGUE.video_heights[quality] - manim_h


def compose_dialogue_video(
    animation_path: Path, out_path: Path, script: DialogueScript, audios: list[SegmentAudio], quality: str,
    *, work_dir: Path, cast: Cast | None = None, cast_dir: Path | None = None,
) -> Path:
    """Stacks the band under `animation_path` (the Manim video with its narration) and writes `out_path`."""
    cast = cast or load_cast(cast_dir)
    width, height = band_size(quality)
    states = band_timeline(script, audios)
    frames_dir = work_dir / "band"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True)

    lines = ["ffconcat version 1.0"]
    for i, state in enumerate(states):
        png = frames_dir / f"{i:04d}.png"
        draw_band(state, cast, width, height, cast_dir).save(png)
        lines += [f"file '{png.name}'", f"duration {max(state.end - state.start, 0.001):.3f}"]
    lines.append(f"file '{len(states) - 1:04d}.png'")  # the concat demuxer drops the last entry's duration
    playlist = frames_dir / "band.ffconcat"
    playlist.write_text("\n".join(lines) + "\n")

    tmp = out_path.with_name(out_path.stem + ".composing.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(playlist), "-i", str(animation_path),
            "-filter_complex",
            f"[0:v]fps={FPS[quality]},format=yuv420p,setsar=1[band];"
            f"[1:v]fps={FPS[quality]},format=yuv420p,setsar=1[top];[top][band]vstack=inputs=2[v]",
            "-map", "[v]", "-map", "1:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-shortest", str(tmp),
        ],
        check=True, capture_output=True,
    )
    tmp.replace(out_path)
    return out_path
