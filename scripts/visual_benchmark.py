#!/usr/bin/env python
"""
Visual coverage benchmark (plan/visual-coverage-plan.md, section 4): can the scene grammar draw a picture for any
CS or Math topic?

80 hand-written topic stubs (benchmarks/visual-coverage/topics.json, 2 for each of 40 areas) go through the
real picture planner only (snapshot_beats.plan_by_snapshots: up to 3 programs, the sandbox, the fit check), with no
lines, voices or video. Each drawn program is rendered locally in the dialogue frame and one still per snapshot is
kept; a critic then judges the stills against the slide.

    uv run python scripts/visual_benchmark.py plan   --out runs/bench1 [--workers 6] [--budget 7] [--only id ...]
    uv run python scripts/visual_benchmark.py render --out runs/bench1
    uv run python scripts/visual_benchmark.py judge  --out runs/bench1 [--budget 2]
    uv run python scripts/visual_benchmark.py report --out runs/bench1

Every step resumes: a topic with a result already written is skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
load_dotenv(ROOT / ".env")

from syllabyte_common import llm  # noqa: E402
from syllabyte_common.models import CourseCorpus, KnowledgeUnit, RunManifest, Slide, SlideDeck, SlideRef  # noqa: E402

TOPICS = ROOT / "benchmarks/visual-coverage/topics.json"
SECONDS_PER_SNAP = 1.6
MAX_STILLS = 12


def load_topics(only: list[str] | None = None) -> list[dict]:
    topics = json.loads(TOPICS.read_text())
    return [t for t in topics if not only or t["id"] in only]


def corpus_and_ku(t: dict) -> tuple[CourseCorpus, KnowledgeUnit]:
    slide = Slide(deck_name=t["id"], slide_number=1, text=t["slide"])
    corpus = CourseCorpus(course_name="visual-benchmark", syllabus_path="", syllabus_text="",
                          decks=[SlideDeck(name=t["id"], source_path="", slides=[slide])])
    ku = KnowledgeUnit(id=t["id"], title=t["title"], summary=t["summary"], bloom_level="understand",
                       cognitive_load="medium", source_refs=[SlideRef(deck_name=t["id"], slide_number=1)],
                       visual_idea=t["visual_idea"], short_worthiness=4, short_worthiness_reason="benchmark stub")
    return corpus, ku


class Spend:
    """One manifest for the run; every request checks the budget first."""

    def __init__(self, path: Path, budget: float):
        self.path, self.budget, self.lock = path, budget, threading.Lock()
        self.manifest = (RunManifest.model_validate_json(path.read_text()) if path.exists()
                         else RunManifest(run_id=path.parent.name))
        original = llm._final_message

        def guarded(*args, **kwargs):
            self.save()
            if self.cost() >= self.budget:
                raise RuntimeError(f"budget stop: ${self.cost():.3f} recorded")
            return original(*args, **kwargs)

        llm._final_message = guarded

    def cost(self, ku_id: str | None = None, stage: str | None = None) -> float:
        m = RunManifest(run_id="x", llm_calls=[c for c in list(self.manifest.llm_calls)
                                               if (ku_id is None or c.ku_id == ku_id)
                                               and (stage is None or c.stage.startswith(stage))])
        return m.total_cost_usd(llm.PRICE_PER_MTOK)

    def save(self):
        with self.lock:
            self.path.write_text(self.manifest.model_dump_json(indent=1))


# ---------------------------------------------------------------- plan


def snapshot_views(snaps: list[dict]) -> list[str]:
    kinds = Counter()
    for s in snaps:
        for v in s["views"].values():
            kinds[v["kind"]] += 1
    return [k for k, _ in kinds.most_common()]


def plan_one(t: dict, out: Path, spend: Spend) -> dict:
    from script_generation_agent.prompts import build_script_prompt
    from script_generation_agent.script_writer import gather_source_material
    from script_generation_agent.snapshot_beats import picture_area, plan_by_snapshots, program_problems
    from script_generation_agent.storyboard import STORYBOARD_MODEL
    from syllabyte_common.cast import load_cast

    corpus, ku = corpus_and_ku(t)
    text_context, image_blocks = gather_source_material(corpus, ku)
    head = build_script_prompt(ku, text_context).replace(
        "Write the 5-segment CLT-bLM script for this Knowledge Unit now.", "")
    cast = load_cast()
    start = time.monotonic()
    error, built = None, None
    try:
        built = plan_by_snapshots(ku, head=head, image_blocks=image_blocks, text_context=text_context, level=2,
                                  prereq_titles=None, explainer=cast.explainer.name, peer=cast.peer.name,
                                  model=STORYBOARD_MODEL, manifest=spend.manifest)
    except Exception as e:  # recorded, the run goes on
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    programs = sorted((out / "plans").glob(f"{t['id']}-program*.json"))
    last = json.loads(programs[-1].read_text()) if programs else None
    snaps, problems = program_problems(last["program"], 2) if last else ([], [])
    row = {
        "id": t["id"], "area": t["area"], "title": t["title"],
        "brief_area": picture_area(ku) or "every area",
        "drawn": built is not None,
        "attempts": len(programs),
        "snapshots": len(snaps),
        "views": snapshot_views(snaps),
        "last_problems": problems,
        "error": error,
        "seconds": round(time.monotonic() - start, 1),
        "cost_usd": round(spend.cost(t["id"]), 4),
    }
    return row


def cmd_plan(args):
    out = Path(args.out)
    (out / "results").mkdir(parents=True, exist_ok=True)
    os.environ["SYLLABYTE_PLAN_DUMP"] = str((out / "plans").resolve())
    spend = Spend(out / "manifest.json", args.budget)
    todo = [t for t in load_topics(args.only) if not (out / "results" / f"{t['id']}.json").exists()]
    print(f"{len(todo)} topics to plan; ${spend.cost():.3f} spent so far", flush=True)

    def job(t):
        if spend.cost() >= args.budget:
            print(f"SKIP {t['id']}: budget", flush=True)
            return
        print(f"START {t['id']}", flush=True)
        row = plan_one(t, out, spend)
        if row["error"] and "budget stop" in row["error"]:
            print(f"STOP {t['id']}: {row['error']}", flush=True)
            return
        (out / "results" / f"{t['id']}.json").write_text(json.dumps(row, indent=1))
        spend.save()
        print(f"END {t['id']}: drawn={row['drawn']} attempts={row['attempts']} views={row['views']} "
              f"${row['cost_usd']:.3f}; total ${spend.cost():.3f}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(job, todo))
    spend.save()
    print(f"TOTAL ${spend.cost():.3f}", flush=True)


# ---------------------------------------------------------------- render


def scene_code(snaps: list[dict]) -> str:
    beats = "\n".join(f"        run.show({i}, {0.6 * SECONDS_PER_SNAP})\n        self.end_beat({i + 1})"
                      for i in range(len(snaps)))
    return f"""import json
from manim import *

from animation_agent.layout import GridLayoutScene
from animation_agent.scene.draw import PictureRunner

SNAPS = json.loads(r'''{json.dumps(snaps)}''')


class Seg0(GridLayoutScene):
    def construct(self):
        self.setup_grid()
        run = PictureRunner(self, SNAPS)
{beats}
"""


def pick(n: int, k: int) -> list[int]:
    if n <= k:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def contact_sheet(stills: list[Path], numbers: list[int], dest: Path):
    from PIL import Image, ImageDraw

    ims = [Image.open(p).convert("RGB") for p in stills]
    w = 300
    ims = [im.resize((w, round(im.height * w / im.width))) for im in ims]
    h = max(im.height for im in ims)
    cols = min(4, len(ims))
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 8) + 8, rows * (h + 30) + 8), "white")
    d = ImageDraw.Draw(sheet)
    for i, (im, n) in enumerate(zip(ims, numbers)):
        x, y = 8 + (i % cols) * (w + 8), 8 + (i // cols) * (h + 30)
        d.text((x, y), f"snapshot {n + 1}", fill="black")
        sheet.paste(im, (x, y + 18))
    sheet.save(dest)


def render_one(row: dict, out: Path) -> dict:
    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render
    from animation_agent.scene.sandbox import run_program
    from animation_agent.visuals.specs import PictureParams, picture_source

    programs = sorted((out / "plans").glob(f"{row['id']}-program*.json"))
    program = PictureParams(program=json.loads(programs[-1].read_text())["program"]).program
    result = run_program(picture_source(program))
    if not result.ok:
        return {"rendered": False, "render_error": f"program: {result.error}"[:500]}
    snaps = result.snapshots
    work = out / "render" / row["id"]
    shutil.rmtree(work, ignore_errors=True)
    (work / "seg").mkdir(parents=True)
    durations = [SECONDS_PER_SNAP] * len(snaps)
    (work / "seg" / BEATS_FILE).write_text(json.dumps(durations))
    ok, error, mp4, layout = _try_render(work / "seg", scene_code(snaps), "Seg0", "low", len(durations),
                                         sum(durations), check_formulas=False, frame="dialogue")
    if not ok:
        return {"rendered": False, "render_error": str(error)[-800:]}
    shutil.copy(mp4, work / "picture.mp4")
    idx = pick(len(snaps), MAX_STILLS)
    stills = []
    for i in idx:
        p = work / f"still_{i + 1:02d}.png"
        t = (i + 1) * SECONDS_PER_SNAP - 0.15
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(work / "picture.mp4"),
                        "-frames:v", "1", str(p)], check=True)
        stills.append(p)
    contact_sheet(stills, idx, work / "sheet.png")
    (work / "captions.json").write_text(json.dumps([s["caption"] for s in snaps], indent=1))
    return {"rendered": True, "layout_findings": [str(f) for f in layout.findings], "stills": len(stills)}


def cmd_render(args):
    out = Path(args.out)
    rows = [json.loads(p.read_text()) for p in sorted((out / "results").glob("*.json"))]
    for row in rows:
        if not row["drawn"] or "rendered" in row:
            continue
        t0 = time.monotonic()
        try:
            row.update(render_one(row, out))
        except Exception as e:
            row.update({"rendered": False, "render_error": f"{type(e).__name__}: {e}"[:800]})
        print(f"{row['id']}: rendered={row['rendered']} findings={len(row.get('layout_findings', []))} "
              f"{time.monotonic() - t0:.0f}s {row.get('render_error', '')[:200]}", flush=True)
        (out / "results" / f"{row['id']}.json").write_text(json.dumps(row, indent=1))


# ---------------------------------------------------------------- judge


class Judgement(BaseModel):
    shows: str = Field(description="one sentence: what the stills actually show")
    missing_or_wrong: str = Field(description="what the topic's usual picture needs that is missing, wrong, cut "
                                              "off or unreadable; empty if nothing")
    score: int = Field(ge=1, le=10, description="how well the pictures show this topic's idea and the slide's "
                                                "example: 1 nothing useful, 5 half of it, 8 clearly, 10 textbook")
    verdict: Literal["good", "partial", "none"] = Field(description=(
        "good: the main idea and the slide's example are drawn correctly and readably; partial: some of it, or "
        "generic, cramped, wrong numbers or a key part missing; none: nothing that helps"))


JUDGE_SYSTEM = """You judge the pictures of a short teaching video for a CS or Math topic. You see the lecture slide,
the topic, the caption written for each step of the picture, and still frames of the picture (the last frame of
selected steps, numbered). Judge only the pictures: would a student, watching these steps with the captions read
aloud, SEE the idea and the slide's worked example? A correct but generic picture (a few boxes with words, a
formula alone where the topic has a standard diagram) is partial. Text that is cut off, overlapping or too small
to read counts against it. Be strict and concrete."""


def judge_one(row: dict, topic: dict, out: Path, spend: Spend) -> dict:
    work = out / "render" / row["id"]
    captions = json.loads((work / "captions.json").read_text())
    text = (f"Topic: {topic['title']}\nSummary: {topic['summary']}\n\nSlide:\n{topic['slide']}\n\n"
            "Step captions:\n" + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(captions))
            + "\n\nThe contact sheet follows: still frames of the numbered steps.")
    j = llm.structured(schema=Judgement, content=[llm.text_block(text), llm.image_block(work / "sheet.png")],
                       system=JUDGE_SYSTEM, stage="bench_judge", ku_id=row["id"], max_tokens=1500,
                       manifest=spend.manifest)
    return j.model_dump()


def cmd_judge(args):
    out = Path(args.out)
    spend = Spend(out / "judge_manifest.json", args.budget)
    topics = {t["id"]: t for t in load_topics()}
    rows = [json.loads(p.read_text()) for p in sorted((out / "results").glob("*.json"))]
    todo = [r for r in rows if r.get("rendered") and "judge" not in r]

    def job(row):
        try:
            row["judge"] = judge_one(row, topics[row["id"]], out, spend)
        except Exception as e:
            print(f"{row['id']}: judge failed: {e}", flush=True)
            return
        (out / "results" / f"{row['id']}.json").write_text(json.dumps(row, indent=1))
        print(f"{row['id']}: {row['judge']['verdict']} {row['judge']['score']}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(job, todo))
    spend.save()
    print(f"judge spend ${spend.cost():.3f}", flush=True)


# ---------------------------------------------------------------- report


def cmd_report(args):
    out = Path(args.out)
    rows = [json.loads(p.read_text()) for p in sorted((out / "results").glob("*.json"))]
    order = [t["id"] for t in load_topics()]
    rows.sort(key=lambda r: order.index(r["id"]))
    n = len(rows)

    def verdict(r):
        if not r["drawn"]:
            return "none (fell back)"
        if not r.get("rendered"):
            return "none (render failed)"
        return r.get("judge", {}).get("verdict", "unjudged")

    drawn = sum(r["drawn"] for r in rows)
    v = Counter(verdict(r) for r in rows)
    first_try = sum(r["drawn"] and r["attempts"] == 1 for r in rows)
    scores = [r["judge"]["score"] for r in rows if "judge" in r]
    plan_cost = sum(r["cost_usd"] for r in rows)
    judge_m = out / "judge_manifest.json"
    judge_cost = (RunManifest.model_validate_json(judge_m.read_text()).total_cost_usd(llm.PRICE_PER_MTOK)
                  if judge_m.exists() else 0.0)
    by_area = defaultdict(list)
    for r in rows:
        by_area[r["area"]].append(r)
    views = Counter(k for r in rows if r["drawn"] for k in r["views"])
    lines = [
        "# Visual coverage benchmark", "",
        f"{n} topics, {len(by_area)} areas (benchmarks/visual-coverage/topics.json). Planner only: up to 3 "
        "picture programs a topic; drawn programs rendered in the dialogue frame; stills judged by the critic.", "",
        f"- **Picture drawn: {drawn}/{n} ({100 * drawn / n:.0f}%)**, on the first program {first_try}/{n}",
        f"- **Good: {v['good']}/{n} ({100 * v['good'] / n:.0f}%)**, partial {v['partial']}, "
        f"none {n - v['good'] - v['partial']} (fell back {v['none (fell back)']}, render failed "
        f"{v['none (render failed)']}, judged none {v['none']}, unjudged {v['unjudged']})",
        f"- Mean critic score of drawn pictures: {sum(scores) / len(scores):.1f}/10" if scores else "- No scores",
        f"- Layout findings in renders: {sum(len(r.get('layout_findings', [])) for r in rows)}",
        f"- Cost: planning ${plan_cost:.2f}, judging ${judge_cost:.2f}; planning time "
        f"{sum(r['seconds'] for r in rows) / n:.0f} s a topic",
        "", "## By area", "", "| Area | Topic | Drawn | Tries | Views | Verdict | Score | Missing or wrong |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for area, rs in by_area.items():
        for r in rs:
            j = r.get("judge", {})
            note = j.get("missing_or_wrong") or ("; ".join(r["last_problems"])[:160] if not r["drawn"] else "")
            if not r["drawn"] and r.get("error"):
                note = r["error"][:160]
            if r.get("render_error"):
                note = r["render_error"][:160]
            lines.append(f"| {area} | {r['title']} | {'yes' if r['drawn'] else 'no'} | {r['attempts']} | "
                         f"{', '.join(r['views'][:3])} | {verdict(r)} | {j.get('score', '')} | "
                         f"{note.replace('|', '/').replace(chr(10), ' ')} |")
    lines += ["", "## Views used by drawn pictures", "",
              ", ".join(f"{k} {c}" for k, c in views.most_common()), ""]
    (out / "report.md").write_text("\n".join(lines))
    print("\n".join(lines[:12]))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["plan", "render", "judge", "report"])
    p.add_argument("--out", default="runs/bench1")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--budget", type=float, default=7.0)
    p.add_argument("--only", nargs="*")
    args = p.parse_args()
    {"plan": cmd_plan, "render": cmd_render, "judge": cmd_judge, "report": cmd_report}[args.step](args)


if __name__ == "__main__":
    main()
