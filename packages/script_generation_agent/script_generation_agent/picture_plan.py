"""
The picture plan: which kind of picture a KU needs (its family), and so which templates its storyboard may use.

One short LLM call sorts the KU's planned visual into a family (animation_agent.visuals.families), the classifier
of the coverage study (scripts/visual_coverage.py, 46/50 agreement by hand). Code then gives the storyboard only the
templates that draw that family, plus formulas and notes: in the course test (runs/course-test-1) the writer, shown
every template, borrowed one drawn for something else whenever none fitted (DFS as a row of cells, XOR's points as
vectors on a linear-map grid), and never used its way out (sketches for an animator).

Plans are cached in runs/picture-plans.json by KU and planned visual, so a KU is classified once.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from animation_agent.visuals.families import FAMILIES, is_gap, main_template, templates_for
from syllabyte_common.llm import DEFAULT_MODEL, structured, text_block
from syllabyte_common.models import KnowledgeUnit, RunManifest

Family = Literal[tuple(FAMILIES) + ("none",)]  # type: ignore[valid-type]

CACHE = Path(os.environ.get("PICTURE_PLAN_CACHE", "runs/picture-plans.json"))
# Part of the cache key: a new family list classifies every KU again.
FAMILIES_VERSION = hashlib.sha256(json.dumps(FAMILIES, sort_keys=True).encode()).hexdigest()[:8]
_LOCK = threading.Lock()


class PicturePlan(BaseModel):
    family: Family = Field(description="the family whose template would draw the main picture, or none")
    also: list[Family] = Field(default_factory=list,
                               description="up to 2 other families the picture also needs on screen (e.g. a "
                                           "formula beside a plot)")
    reason: str = Field(description="one short sentence")

    @property
    def templates(self) -> list[str]:
        return templates_for(self.family, self.also[:2])

    @property
    def main(self) -> str | None:
        """The template that must draw the main picture, if one does."""
        return main_template(self.family)

    @property
    def gap(self) -> bool:
        return is_gap(self.family)


SYSTEM = """\
You sort the planned visual of a short educational video into a template family. The video explains one idea \
from a course; its planned visual is one sentence, and its summary says what the idea is. A family is a reusable \
animation template; pick the one that would draw the main picture of THIS idea faithfully (judge by the idea, \
not only the sentence: a lesson on DFS needs a graph even if the sentence mentions a list). Use "none" when no \
family fits well enough (a physical object, a metaphor such as a balance scale, a photograph). Use "note" only \
when the picture is just words. List in `also` any other families the picture needs on screen at the same time \
(at most 2).

Families:
""" + "\n".join(f"- {name}: {what}" for name, what in FAMILIES.items())


def _key(ku: KnowledgeUnit) -> str:
    raw = json.dumps([ku.title, ku.summary, ku.visual_idea, FAMILIES_VERSION])
    return f"{ku.id}:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _load() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def plan_picture(ku: KnowledgeUnit, *, model: str = DEFAULT_MODEL, manifest: RunManifest | None = None,
                 use_cache: bool = True) -> PicturePlan:
    """The KU's picture plan, from the cache or one classifier call."""
    key = _key(ku)
    if use_cache and (hit := _load().get(key)):
        return PicturePlan.model_validate(hit)
    listing = (f"title: {ku.title}\nsummary: {ku.summary[:500]}\nplanned visual: {ku.visual_idea}")
    plan = structured(schema=PicturePlan, content=[text_block(listing)], system=SYSTEM, stage="picture_plan",
                      ku_id=ku.id, model=model, max_tokens=2000, manifest=manifest)
    plan.also = [f for f in plan.also if f != plan.family][:2]
    with _LOCK:
        cache = _load()
        cache[key] = plan.model_dump()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, indent=1))
        tmp.replace(CACHE)
    print(f"[picture_plan] {ku.id}: {plan.family} (also {plan.also}) -> {plan.templates}"
          + (" [no template draws this yet]" if plan.gap else ""), file=sys.stderr, flush=True)
    return plan


__all__ = ["PicturePlan", "plan_picture"]
