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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from animation_agent.visuals.families import DRAWN_BY, FAMILIES, is_gap, main_template, templates_for
from animation_agent.visuals.specs import TEMPLATES_VERSION
from syllabyte_common.llm import DEFAULT_MODEL, structured, text_block
from syllabyte_common.models import KnowledgeUnit, RunManifest

Family = Literal[tuple(FAMILIES) + ("none",)]  # type: ignore[valid-type]

CACHE = Path(os.environ.get("PICTURE_PLAN_CACHE", "runs/picture-plans.json"))
# Part of the cache key: a new family list classifies every KU again.
# a new template (or family) changes saved picture plans, so they are made again
FAMILIES_VERSION = hashlib.sha256(json.dumps([FAMILIES, DRAWN_BY, TEMPLATES_VERSION], sort_keys=True).encode()).hexdigest()[:8]
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


@dataclass(frozen=True)
class GrammarPlan:
    """The picture plan when a program draws the picture (the scene grammar, plan/scene-grammar-plan.md, P1;
    the default, unless SYLLABYTE_PICTURES=templates): Picture, with formulas and notes beside it, and no traced example."""

    templates: tuple[str, ...] = ("Picture", "EquationSteps", "Note")
    main: str = "Picture"
    family: None = None
    also: tuple = ()
    gap: bool = False


GRAMMAR_PLAN = GrammarPlan()


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


# --------------------------------------------------------------------------
# The worked example, for a KU that steps through an algorithm (animation_agent.visuals.trace)
# --------------------------------------------------------------------------

# The families whose main template runs an algorithm code can trace.
TRACED_FAMILIES = ("array_bars", "merge_sort", "tree", "graph", "linked_list")

EXAMPLE_SYSTEM = """\
You pick the worked example for a short educational video (about a minute). Code will run the algorithm on it \
step by step, and the video narrates those steps, so pick the algorithm the video is about and an example small \
enough to show.

algorithm: the one the video runs step by step on the example, or none when the idea isn't one of these (e.g. \
indexing, a cost discussed in words, a comparison of several algorithms, a definition with no operation run, or \
any other algorithm):
- on a list: linear_search, bisection (binary search), bubble_sort, selection_sort, insertion_sort, merge_sort, \
merge (two sorted lists merged into one);
- bst: operations on a binary search tree (insert, search, delete, traversals), given as `ops`;
- heap: operations on a binary heap (push, pop, heapify, traversals), given as `ops`, with `heap` min or max;
- on a graph: dfs, bfs, dijkstra (shortest paths), prim, kruskal (minimum spanning trees), topological_sort;
- linked_list: operations on a linked list (insert or delete at a position, find node by node, the in-place \
reversal), given as `ops`.

The example: use the slides' own example if it fits, copied exactly: every value, and for a graph every node, \
edge, direction and weight in its figure (the slide images show it; the critic checks the video against them). \
Only when the slides have none that fits, make one up. Small numbers are easiest to follow. Cover what the idea \
is about: if it is an insert and then a search, give both ops.
- A list: 4-8 whole numbers from 0 to 99, at most 7 if any has two digits (one-digit numbers are easiest). \
Bisection needs the values sorted; pick a target it takes at least three checks to find (or one that isn't there, \
if the idea is about a failed search). A linear search's target sits a few cells in, not first. A sort's values \
start out of order, so every step does something. merge takes `runs`: two sorted lists, 2-8 numbers in all.
- bst: `values` are the tree's values in the order inserted (5-8, distinct, 0-99; the first is the root, so pick \
a middle value first and keep it at most 4 levels deep); then 1-2 `ops`, e.g. insert a value that lands 3 \
levels down, then search for one that is (or isn't) there. One traverse op visits every node, one per step.
- heap: `values` are its array (5-8 numbers; code makes it a heap first, unless the first op is heapify); then \
1-2 `ops`, e.g. push a value that rises two levels, then pop. heapify alone shows building a heap from an array.
- a graph: 4-7 `nodes` with 1-2 character names, at most 10 `edges`, `start` the first node; dijkstra, prim and \
kruskal need every edge's weight (a whole number 1-9) as its third item, and an example where the cheapest \
first choice isn't the final answer (a shorter path through another node, a skipped edge). topological_sort \
needs `directed` and no cycle.
- linked_list: 3-5 one-digit `values` from the head; then 1-3 `ops`: insert (`index`, `value`; index 0 links a \
new head), delete (`index`), find (`value`, a few nodes in, or missing), reverse."""


def _example_key(ku: KnowledgeUnit, slides: str) -> str:
    raw = json.dumps([ku.title, ku.summary, ku.visual_idea, slides[:4000], EXAMPLE_SYSTEM, "images"])
    return f"example:{ku.id}:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def plan_example(ku: KnowledgeUnit, plan: PicturePlan, slides: str, *, model: str = DEFAULT_MODEL,
                 manifest: RunManifest | None = None, use_cache: bool = True, images: list | None = None):
    """The KU's traced worked example (animation_agent.visuals.trace.Trace), or None when its picture doesn't
    step through an algorithm code can trace. One short call, cached like the picture plan. `images` are the
    slides' image blocks: a graph or tree is often only drawn there (in runs/dsa-trace the call, given the text
    alone, rebuilt the Dijkstra slide's graph from its table and left out two of its edges)."""
    from animation_agent.visuals.trace import Example, build_trace

    if plan.family not in TRACED_FAMILIES:
        return None
    key = _example_key(ku, slides)
    example = None
    if use_cache and (hit := _load().get(key)):
        example = Example.model_validate(hit)
    if example is None:
        listing = (f"title: {ku.title}\nsummary: {ku.summary[:500]}\nplanned visual: {ku.visual_idea}\n\n"
                   f"slides:\n{slides[:4000]}")
        try:
            example = structured(schema=Example, content=[text_block(listing), *(images or [])],
                                 system=EXAMPLE_SYSTEM,
                                 stage="example_plan", ku_id=ku.id, model=model, max_tokens=1500,
                                 manifest=manifest)
        except Exception as e:  # best effort: without an example the writer calls the steps, as before
            print(f"[example_plan] {ku.id}: the call failed: {e}", file=sys.stderr, flush=True)
            return None
        with _LOCK:
            cache = _load()
            cache[key] = example.model_dump()
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(cache, indent=1))
            tmp.replace(CACHE)
    trace = build_trace(example)
    shown = example.values or example.runs or example.nodes
    print(f"[example_plan] {ku.id}: {example.algorithm} {shown}"
          + (f" for {example.target}" if example.target is not None else "")
          + (f" ({trace.task})" if trace and trace.task else "")
          + (f": {len(trace.steps)} steps" if trace else ": not traced"), file=sys.stderr, flush=True)
    return trace


__all__ = ["GRAMMAR_PLAN", "GrammarPlan", "PicturePlan", "TRACED_FAMILIES", "plan_example", "plan_picture"]
