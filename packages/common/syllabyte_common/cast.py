"""
The two characters of dialogue videos (research_notes/dialogue-framework.md): who explains, who learns, what they
look and sound like.

Read from `cast.json` in the characters directory: `media/characters/` at the repo root (gitignored, since the
images are not ours to publish), or the directory in $SYLLABYTE_CAST_DIR. Swapping the characters means editing
that one file and its images:

    {
      "explainer": {"name": "Peter",  "image": "peter.png",  "voice": "am_michael", "side": "right"},
      "peer":      {"name": "Stewie", "image": "stewie.png", "voice": "bm_george",  "side": "left"}
    }

`voice` is a Kokoro voice id; its first letter is its accent ("a" American, "b" British).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from syllabyte_common.models import Speaker

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAST_DIR = REPO_ROOT / "media" / "characters"
CAST_FILE = "cast.json"


class Character(BaseModel):
    name: str
    image: str  # file in the cast directory: a PNG with a transparent background
    voice: str  # Kokoro voice id
    side: Literal["left", "right"]


class Cast(BaseModel):
    explainer: Character
    peer: Character

    def of(self, speaker: Speaker) -> Character:
        return self.explainer if speaker == "explainer" else self.peer


class CastError(Exception):
    pass


def cast_dir() -> Path:
    return Path(os.environ.get("SYLLABYTE_CAST_DIR", DEFAULT_CAST_DIR))


def load_cast(directory: Path | None = None) -> Cast:
    directory = directory or cast_dir()
    path = directory / CAST_FILE
    if not path.exists():
        raise CastError(f"dialogue videos need {path} (see syllabyte_common/cast.py for its format)")
    cast = Cast.model_validate_json(path.read_text())
    for role in ("explainer", "peer"):
        image = directory / getattr(cast, role).image
        if not image.exists():
            raise CastError(f"{path}: the {role}'s image {image} does not exist")
    if cast.explainer.side == cast.peer.side:
        raise CastError(f"{path}: the two characters need different sides")
    return cast


def image_path(character: Character, directory: Path | None = None) -> Path:
    return (directory or cast_dir()) / character.image


def cast_fingerprint(directory: Path | None = None) -> str:
    """Changes when the cast file or either image changes, so cached dialogue videos are remade."""
    directory = directory or cast_dir()
    cast = load_cast(directory)
    h = hashlib.sha256((directory / CAST_FILE).read_bytes())
    for character in (cast.explainer, cast.peer):
        h.update(image_path(character, directory).read_bytes())
    return h.hexdigest()
