"""
Coverage study for the visual template library (plan/visual-template-library-plan.md, phase 0).

Sorts every KU's planned visual (KnowledgeUnit.visual_idea) into one of the template families below, or "none",
with an LLM, then reports how often each family comes up and how much of the course set the first k families
would cover. That ranks which templates to build next, and the curve goes in the report.

    uv run python scripts/visual_coverage.py --courses runs/stem-cs runs/stem-math ... --out runs/visual-coverage

Writes coverage.json (one row per KU), coverage.md (the tables) and sample.md (a random sample to check by hand;
the plan asks for >= 90% agreement before trusting the ranking). Classifications are cached per course in
coverage.json, so re-running after adding a course only classifies the new one.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from animation_agent.visuals.specs import REGISTRY  # noqa: E402
from syllabyte_common.llm import DEFAULT_MODEL, structured, text_block  # noqa: E402
from syllabyte_common.models import KUList, RunManifest  # noqa: E402

# The plan's families (plan/visual-template-library-plan.md, "Template families"), with what each draws.
FAMILIES: dict[str, str] = {
    # CS
    "array_bars": "a list/array as cells or bars: searching, sorting, pointers, halves, swaps",
    "code_trace": "code with a line-by-line highlight and a panel of variable values",
    "call_tree": "recursion trees, the call stack, memoisation",
    "growth_curves": "growth of running time: O(1)..O(c^n) curves, operation counters, Big-O comparison",
    "linked_list": "linked lists: nodes and next-pointers, insert, delete, reverse",
    "stack_queue": "stacks and queues: push/pop, enqueue/dequeue",
    "hash_table": "hash tables: buckets, hashing, collisions, chaining, probing",
    "tree": "trees as data structures: BST, heap, trie; insert, search, traversals",
    "graph": "graphs: nodes and edges, BFS, DFS, shortest paths, spanning trees, topological sort",
    "dp_table": "a dynamic-programming table filled in order, with arrows to the cells each depends on",
    "memory_refs": "variables, references, aliasing, mutation, memory boxes",
    "state_machine": "state machines and automata: states, transitions, DFAs, regular expressions",
    "bits_logic": "binary and hex numbers, bitwise operations, logic gates, circuits, truth tables",
    "flowchart": "boxes and arrows: pipelines, control flow, system or process diagrams",
    "ml_basics": "machine-learning pictures: network diagram, loss curve with gradient descent, decision boundary, clusters",
    # Mathematics
    "equation_steps": "a derivation or calculation shown one formula per step",
    "number_line": "a number line: intervals, inequalities, points, sequences converging",
    "function_plot": "axes with plotted functions: transformations, limits, tangents, areas, Riemann sums",
    "linear_map_2d": "a 2D coordinate grid with vectors transformed by a matrix: linear maps, eigenvectors, bases",
    "vectors_3d": "3D vectors, planes, surfaces, cross products, span in 3D",
    "matrix_ops": "matrices written out: multiplication, row operations, block matrices, factorisations",
    "series": "sequences and series: partial sums, convergence",
    "probability": "probability: trees, sample spaces, distributions, sampling, Bayes",
    "stats_plots": "data plots: histograms, scatter plots, regression lines, confidence intervals",
    "counting": "counting: grids of outcomes, Pascal's triangle, permutations, combinations",
    "proof_steps": "a proof's structure: induction steps, contradiction, chains of implications",
    "sets_logic": "sets and logic: Venn diagrams, set operations, quantifiers",
    "geometry": "geometric figures: constructions, triangles, circles, angles, transformations",
    "complex_plane": "the complex plane: complex numbers as points, roots of unity",
    "polar_parametric": "polar and parametric curves",
    "slope_field": "differential equations: slope fields and solution curves",
    "bar_meter": "a bar chart, meter or dial for a few quantities",
    "note": "only words: a key term, a list of points, a question (no diagram)",
}
Family = Literal[tuple(FAMILIES) + ("none",)]  # type: ignore[valid-type]

BUILT = {spec.family for spec in REGISTRY.values()}
BATCH = 15
SAMPLE = 50


class KUVisual(BaseModel):
    ku_id: str
    family: Family = Field(description="the family whose template would draw the main picture, or none")
    also: list[Family] = Field(default_factory=list,
                               description="up to 2 other families the picture also needs (e.g. a formula beside a plot)")
    reason: str = Field(description="one short sentence")


class KUVisuals(BaseModel):
    items: list[KUVisual]


SYSTEM = """\
You sort the planned visuals of short educational videos into template families. Each video explains one \
idea from a course; its planned visual is one sentence. A family is a reusable animation template; pick the one \
that would draw the main picture. Use "none" when no family fits well enough to draw that picture faithfully \
(e.g. a physical object, a metaphor such as a balance scale, a photograph). Use "note" only when the picture is \
just words. List in `also` any other families the picture needs on screen at the same time (at most 2).

Families:
""" + "\n".join(f"- {name}: {what}" for name, what in FAMILIES.items())


def classify(course: str, kus: list, model: str, manifest: RunManifest) -> list[dict]:
    rows = []
    for start in range(0, len(kus), BATCH):
        batch = kus[start:start + BATCH]
        listing = "\n\n".join(
            f"id: {ku.id}\ntitle: {ku.title}\nsummary: {ku.summary[:300]}\nplanned visual: {ku.visual_idea}"
            for ku in batch
        )
        out = structured(schema=KUVisuals, content=[text_block(listing)], system=SYSTEM, stage="visual_coverage",
                         model=model, max_tokens=16000, manifest=manifest)
        by_id = {item.ku_id: item for item in out.items}
        for ku in batch:
            item = by_id.get(ku.id)
            rows.append({
                "course": course, "ku_id": ku.id, "title": ku.title, "visual_idea": ku.visual_idea,
                "family": item.family if item else "none", "also": item.also[:2] if item else [],
                "reason": item.reason if item else "not classified",
            })
    return rows


def covered(row: dict, families: set[str]) -> bool:
    return row["family"] in families and all(f in families for f in row["also"])


def report(rows: list[dict]) -> str:
    n = len(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["family"]] = counts.get(r["family"], 0) + 1
    order = sorted((f for f in counts if f != "none"), key=lambda f: -counts[f])
    courses = sorted({r["course"] for r in rows})
    lines = [
        "# Visual coverage study", "",
        f"{n} KUs from {len(courses)} courses: {', '.join(courses)}.", "",
        f"Built so far: {', '.join(sorted(BUILT))}. "
        f"They cover **{sum(covered(r, BUILT) for r in rows) / n:.0%}** of KUs fully (main picture and everything "
        f"in `also`), and are the main family of {sum(r['family'] in BUILT for r in rows) / n:.0%}.", "",
        "## Families by how often they are the main picture", "",
        "| # | family | KUs | share | cumulative (main only) | cumulative (fully covered) | built |",
        "|---|---|---|---|---|---|---|",
    ]
    chosen: set[str] = set()
    main = 0
    for k, f in enumerate(order, 1):
        chosen.add(f)
        main += counts[f]
        full = sum(covered(r, chosen) for r in rows)
        lines.append(f"| {k} | {f} | {counts[f]} | {counts[f] / n:.0%} | {main / n:.0%} | {full / n:.0%} | "
                     f"{'yes' if f in BUILT else ''} |")
    lines += ["", f"No family fits: {counts.get('none', 0)} KUs ({counts.get('none', 0) / n:.0%}).", "",
              "## By course", "", "| course | KUs | fully covered by the built templates |", "|---|---|---|"]
    for c in courses:
        cr = [r for r in rows if r["course"] == c]
        lines.append(f"| {c} | {len(cr)} | {sum(covered(r, BUILT) for r in cr) / len(cr):.0%} |")
    also = {}
    for r in rows:
        for f in r["also"]:
            also[f] = also.get(f, 0) + 1
    lines += ["", "## Families needed alongside the main picture", "",
              ", ".join(f"{f} ({c})" for f, c in sorted(also.items(), key=lambda kv: -kv[1])) or "none"]
    return "\n".join(lines) + "\n"


def sample(rows: list[dict], seed: int = 0) -> str:
    picked = random.Random(seed).sample(rows, min(SAMPLE, len(rows)))
    lines = ["# Hand check: is each family right?", "",
             "Mark each row ok or wrong (and the right family). The plan needs >= 90% ok.", "",
             "| # | course | planned visual | family | also | ok? |", "|---|---|---|---|---|---|"]
    for k, r in enumerate(picked, 1):
        lines.append(f"| {k} | {r['course']} | {r['visual_idea'].replace('|', '/')} | {r['family']} | "
                     f"{', '.join(r['also'])} | |")
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--courses", nargs="+", required=True, help="run directories with kus.json")
    parser.add_argument("--out", default="runs/visual-coverage")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache_path = out / "coverage.json"
    cached = json.loads(cache_path.read_text()) if cache_path.exists() else []
    manifest = RunManifest(run_id="visual-coverage")
    rows = []
    for course_dir in map(Path, args.courses):
        kus = KUList.model_validate_json((course_dir / "kus.json").read_text()).knowledge_units
        name = course_dir.name
        have = [r for r in cached if r["course"] == name]
        if {r["ku_id"] for r in have} == {ku.id for ku in kus}:
            rows += have
            continue
        print(f"classifying {len(kus)} KUs from {name}", flush=True)
        rows += classify(name, kus, args.model, manifest)
        cache_path.write_text(json.dumps(rows + [r for r in cached if r["course"] not in {x["course"] for x in rows}],
                                         indent=2))
    cache_path.write_text(json.dumps(rows, indent=2))
    (out / "coverage.md").write_text(report(rows))
    (out / "sample.md").write_text(sample(rows))
    (out / "manifest.json").write_text(manifest.model_dump_json(indent=2))
    print(report(rows))


if __name__ == "__main__":
    main()
