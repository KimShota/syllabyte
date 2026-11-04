"""
The Gen-Z phrases a dialogue script may use (slang.json), and finding them in a line.

Slang is a delivery style, never content: conversational wording helps (personalization principle; Ginns, Martin
& Marsh 2013), but jokes and asides that pull away from the idea hurt (seductive details; Rey 2012), and many
viewers are not native English speakers. So the writer gets a short list, a cap, and lines where slang is not
allowed (script_writer.validate_dialogue).
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

SLANG_FILE = Path(__file__).with_name("slang.json")

# At most one slang phrase per this many beats, over the whole script, and at least MIN_SLANG in it.
BEATS_PER_SLANG = 2.5
MIN_SLANG = 2


@cache
def phrases() -> tuple[dict, ...]:
    return tuple(json.loads(SLANG_FILE.read_text())["phrases"])


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


def max_slang(n_beats: int) -> int:
    return max(MIN_SLANG, int(n_beats / BEATS_PER_SLANG))


def lexicon_for_prompt() -> str:
    return "\n".join(f'      - "{p["phrase"]}" ({p["meaning"]}), e.g. "{p["example"]}"' for p in phrases())
