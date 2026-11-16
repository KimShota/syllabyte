"""
The Gen-Z phrases a dialogue script may use (slang.json), which one each slot gets, and finding them in a line.

Slang is a delivery style, never content: conversational wording helps (personalization principle; Ginns, Martin
& Marsh 2013), but jokes and asides that pull away from the idea hurt (seductive details; Rey 2012), and many
viewers are not native English speakers. In an educational chatbot Gen-Z slang raised engagement and also
perceived difficulty (d = 0.33; Liew et al. 2025). So the writer gets a short list, a cap, and lines where slang is
not allowed (script_writer.validate_dialogue).

Each phrase marks a learning moment (a move), not just a line: the puzzled hook, committing to a guess, the next
question after a correction, the result clicking, a surprise. Humor tied to the content is the kind linked to
learning (Ziv 1988; Banas et al. 2011), a phrase that reacts to something reads as natural where one stuck on
every line reads as trying too hard, and a joke heard over and over wears out. Left to choose, the writer and
the old fixer put the same three phrases at the start of the same three lines (runs/ to 2026-11-16: "not gonna
lie", "lowkey" and "for real" were 89% of 880 uses, 97% of them opening the line). So code picks each slot's
phrase (pick_phrases): one that fits the slot's move, different from the video's other slots, and spread evenly
over a course by a stable hash of the video's key, so videos made in parallel need no shared state and a KU made
again gets the same phrases (its cached calls still match).

    python -m script_generation_agent.slang runs/<course>   # how often each phrase is used over its scripts
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable
from functools import cache
from pathlib import Path

SLANG_FILE = Path(__file__).with_name("slang.json")

# At most one slang phrase per this many beats, over the whole script, and at least MIN_SLANG in it.
BEATS_PER_SLANG = 2.5
MIN_SLANG = 2

# The learning moments a phrase can mark, by the line it goes in.
MOVES = {
    "hook": "the peer's puzzled opening question",
    "commit": "the peer stating a guess with confidence (the wrong idea)",
    "followup": "the peer's next question, after hearing an explanation",
    "result": "the peer giving the result, or getting it",
    "surprise": "the peer reacting to an answer that isn't what they expected",
}

# Over a course, no phrase should be more than this share of the slang used (spread(); the tests check
# pick_phrases keeps to it).
MAX_SHARE = 0.15


@cache
def phrases() -> tuple[dict, ...]:
    return tuple(json.loads(SLANG_FILE.read_text())["phrases"])


def for_move(move: str) -> list[str]:
    """The phrases that can mark `move`, in list order."""
    return [p["phrase"] for p in phrases() if move in p.get("moves", ())]


def _hash(*parts: object) -> int:
    return int.from_bytes(hashlib.sha256("\x1f".join(map(str, parts)).encode()).digest()[:8], "big")


def pick_phrases(moves: list[str], key: str) -> list[str]:
    """One phrase per slot, for slots marking `moves` in a video whose key (its KU id) is `key`: each fits its
    move, none repeats in the video, and over many keys each phrase of a move comes up about equally often."""
    picked: list[str] = []
    for i, move in enumerate(moves):
        options = [p for p in for_move(move) if p not in picked] or for_move(move)
        if not options:
            raise ValueError(f"slang.json has no phrase for the move {move!r}")
        picked.append(options[_hash(key, i, move) % len(options)])
    return picked


def meaning(phrase: str) -> str:
    return next(p["meaning"] for p in phrases() if p["phrase"] == phrase)


@cache
def _pattern(phrase: str) -> re.Pattern:
    words = [re.escape(w) for w in phrase.replace("'", "’").split()]
    # Either apostrophe; whole words only, so "bet" doesn't match "between".
    body = r"\s+".join(w.replace("’", "['’]") for w in words)
    return re.compile(rf"(?<![\w'’]){body}(?![\w'’])", re.IGNORECASE)


def find_slang(text: str) -> list[str]:
    """Each listed phrase the line uses (or one of its listed spellings, e.g. "low-key"), once per use."""
    found = []
    for p in phrases():
        for spelling in (p["phrase"], *p.get("also", [])):
            found += [p["phrase"]] * len(_pattern(spelling).findall(text))
    return found


def affirming(text: str) -> list[str]:
    """The phrases in the line that say its answer is right ("that tracks"): never on a wrong answer."""
    marks = {p["phrase"] for p in phrases() if p.get("affirms")}
    return [s for s in find_slang(text) if s in marks]


# How a line correcting the one before it opens ("Not quite. A zero loops q1 back ...").
CORRECTION = re.compile(r"^\W*(not quite|not exactly|not really|close|almost|actually|careful|nope|no\b|hmm)",
                        re.IGNORECASE)


def has_phrase(text: str, phrase: str) -> bool:
    return phrase in find_slang(text)


def max_slang(n_beats: int) -> int:
    return max(MIN_SLANG, int(n_beats / BEATS_PER_SLANG))


def lexicon_for_prompt() -> str:
    return "\n".join(f'      - "{p["phrase"]}" ({p["meaning"]}), e.g. "{p["example"]}"' for p in phrases())


# --------------------------------------------------------------------------
# Over a course
# --------------------------------------------------------------------------


def spread(lines: Iterable[str]) -> Counter:
    """How often each listed phrase is used in `lines` (every line of a course's scripts)."""
    return Counter(s for line in lines for s in find_slang(line))


def overused(counts: Counter, max_share: float = MAX_SHARE) -> list[str]:
    total = sum(counts.values())
    return [p for p, n in counts.most_common() if total and n / total > max_share]


def _course_lines(root: Path) -> list[str]:
    out = []
    for f in sorted(root.rglob("script.json")):
        try:
            data = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        out += [b["narration"] for seg in data.get("segments", []) for b in seg.get("beats", [])
                if isinstance(b, dict) and isinstance(b.get("narration"), str)]
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m script_generation_agent.slang <dir with script.json files>", file=sys.stderr)
        return 2
    counts = spread(_course_lines(Path(args[0])))
    total = sum(counts.values())
    print(f"{total} slang uses")
    for p in phrases():
        n = counts[p["phrase"]]
        print(f"{n:5d}  {n / total if total else 0:5.1%}  {p['phrase']}")
    if over := overused(counts):
        print(f"over {MAX_SHARE:.0%} of uses: {', '.join(over)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
