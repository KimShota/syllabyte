"""
File-based run storage for the Week-1 pipeline. No Mongo/Celery/Docker
needed — each run lives under runs/<run_id>/ and every stage's output is a
JSON file (validated against the Pydantic models in models.py), so the CLI
can resume from any stage without recomputation.

Layout:
    runs/<run_id>/
        manifest.json          # RunManifest (token usage / cost)
        corpus.json             # CourseCorpus
        kus.json                 # KUList
        <ku_id>/
            script.json          # Script
            critique.json        # CritiqueResult
            audio/
                seg_0.wav ...
                narration.wav
                captions.srt
            render/
                seg_0.py, seg_0.mp4 ...
                render_results.json  # list[RenderResult]
            final.mp4
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


class RunDir:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- generic JSON helpers ---------------------------------------------

    def save_json(self, relative_path: str, model: BaseModel) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(model.model_dump_json(indent=2))
        return path

    def load_json(self, relative_path: str, schema: type[T]) -> T:
        path = self.root / relative_path
        return schema.model_validate_json(path.read_text())

    def exists(self, relative_path: str) -> bool:
        return (self.root / relative_path).exists()

    def path(self, relative_path: str) -> Path:
        p = self.root / relative_path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # -- per-KU convenience -------------------------------------------------

    def ku_dir(self, ku_id: str) -> Path:
        d = self.root / ku_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def stage_done(self, ku_id: str | None, filename: str) -> bool:
        """Used by the CLI's --from-stage resume logic: has this stage
        already produced output for this KU (or globally, if ku_id=None)?"""
        base = self.root / ku_id if ku_id else self.root
        return (base / filename).exists()

    def raw_json(self, relative_path: str) -> dict:
        path = self.root / relative_path
        return json.loads(path.read_text())
