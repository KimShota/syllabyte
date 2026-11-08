#!/usr/bin/env python
"""
Build the Phase 0 UI fixtures (plan §10) from a finished pipeline run.

    uv run python scripts/build_ui_fixtures.py --run runs/dev --out packages/core/fixtures
    cd apps/web && npm run fixtures        # copies the media into public/fixtures/

What it does
  1. UI manifest per rendered video (poster, VTT, segment spans, checkpoint time,
     transcript) — no LLM (animation_agent/ui_manifest.py).
  2. Course structure: the invented 3-lecture schedule (LECTURES below) is an AUTHOR DECISION, not LLM output.
     A topic is a lecture (plan/per-ku-profiling-plan.md D2): one per lecture, holding that lecture's KUs.
  3. Video items and claims via the LLM, grounded only in the cited slides, then checked by a critic pass;
     one regeneration if the critic objects:
       per video  -> checkpoint, next-session and prove-it items, a sentence
                     frame for screen 7, and one claim per deliver/end segment.
     Results are cached in <run>/ui_cache/ so re-running costs nothing (--regen to redo).
     The adaptive-assessment items (three per KU) are made by scripts/build_item_bank.py into bank.json.
  4. Writes packages/core/fixtures/{course,items,videos,slides}.json and _review.md.

The persona's history (levels, calibration, Week 7 story) is hand-written in the web
app (lib/api/persona.ts). READ _review.md before any usability session: every item
and claim is listed there with its keyed answer and any critic flags.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from animation_agent.ui_manifest import build_ui_manifest, checkpoint_for
from assessment_agent.video_app_data import (
    VideoGen,
    balance_positions,
    generate_video_gen,
    tailoring_for as _tailoring_for,
    video_claims,
    video_items,
)
from syllabyte_common.learner import (
    Course,
    CourseConfig,
    Item,
    KuEntry,
    Lecture,
    SentenceFrame,
    TailoringSkeleton,
    Topic,
    TranscriptRow,
    VideoFixture,
)
from syllabyte_common.llm import (
    DEFAULT_MODEL,
    PRICE_PER_MTOK,
    image_block,
)
from syllabyte_common.models import CourseCorpus, KnowledgeUnit, KUList, RunManifest, SlideRef

# --------------------------------------------------------------------------
# Author decisions (computational-ss). Change here, then re-run with --regen.
# --------------------------------------------------------------------------

COURSE_ID = "cs-uh-2219e"
COURSE_NAME = "Computational Social Science"
COURSE_CODE = "CS-UH 2219E"
SYLLABUS_SUMMARY = (
    "Computational Social Science (CS-UH 2219E), Fall 2026. The class meets Tuesdays and "
    "Thursdays, 1:55 to 3:10 PM, in A5-018. SyllaByte's videos follow the lecture slides "
    "and are meant to sit alongside the lectures, not replace them."
)

# Short names for cards, headers and receipts (the full KU title is a sentence).
SHORT_TITLES: dict[str, str] = {
    "ku-random-assignment-origin": "Random assignment",
    "ku-health-insurance-question": "Does insurance improve health?",
    "ku-outcome-measure-health-index": "The NHIS health index",
    "ku-treatment-control-sample": "Treatment and control groups",
    "ku-reading-difference-table": "Reading a difference table",
    "ku-apples-oranges-confounders": "Apples and oranges",
    "ku-potential-outcomes": "Potential outcomes",
    "ku-individual-causal-effect": "The individual causal effect",
    "ku-fundamental-problem-observable-outcome": "The fundamental problem",
    "ku-naive-comparison-timmy-spike": "Comparing Timmy and Spike",
    "ku-selection-bias-decomposition": "Splitting out selection bias",
    "ku-selection-bias-general-formula": "The selection bias formula",
    "ku-law-of-large-numbers": "The law of large numbers",
    "ku-lln-eliminates-selection-bias": "Large samples and selection bias",
    "ku-coin-toss-average-causal-effect": "The coin-toss example",
    "ku-balance-checking": "Checking balance",
    "ku-rand-hie-design": "The RAND experiment: design",
    "ku-rand-hie-balance-tables": "RAND balance tables",
    "ku-rand-hie-results": "RAND results",
    "ku-summary-avoiding-selection-bias": "Avoiding selection bias: summary",
}

# Invented schedule: the single deck is split into three "lectures".
LECTURES = [
    Lecture(n=1, title="Causal questions and potential outcomes", week=1, slide_start=1, slide_end=16),
    Lecture(n=2, title="Selection bias", week=2, slide_start=17, slide_end=24),
    Lecture(n=3, title="Randomization", week=3, slide_start=25, slide_end=34),
]
UPCOMING_LECTURE_OVERRIDE = 3  # Phase 0 pretends Lecture 3 is next, so all 4 videos qualify

# --------------------------------------------------------------------------
# LLM schemas + prompts
# --------------------------------------------------------------------------




# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[build_ui_fixtures] {msg}", flush=True)


def slide_material(corpus: CourseCorpus, slide_numbers: list[int]) -> tuple[str, list[dict]]:
    parts, images, seen = [], [], set()
    for n in slide_numbers:
        if n in seen:
            continue
        seen.add(n)
        slide = corpus.slide_by_ref("slides", n) or next(
            (s for d in corpus.decks for s in d.slides if s.slide_number == n), None
        )
        if slide is None:
            continue
        parts.append(f"[slide {n}]\n{slide.text}")
        if slide.image_path and Path(slide.image_path).exists():
            images.append(image_block(slide.image_path))
    return "\n\n".join(parts), images


def cached(path: Path, regen: bool, make):
    if path.exists() and not regen:
        return json.loads(path.read_text())
    data = make()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return data


# --------------------------------------------------------------------------
# tailoring skeletons (deterministic; plan §7.4)
# --------------------------------------------------------------------------


def tailoring_for(ku: KnowledgeUnit, kus: dict[str, KnowledgeUnit]) -> dict[str, list[TailoringSkeleton]]:
    """What differs at each level (assessment_agent.video_app_data), naming the first prerequisite by its short title."""
    prereq = kus.get(ku.prerequisites[0]) if ku.prerequisites else None
    return _tailoring_for(ku.id, (prereq.id, SHORT_TITLES[prereq.id]) if prereq else None)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="runs/dev")
    ap.add_argument("--out", default="packages/core/fixtures")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--critic-model", default=None, help="defaults to --model")
    ap.add_argument("--regen", action="store_true", help="ignore the cache and regenerate all LLM output")
    ap.add_argument("--skip-llm", action="store_true", help="fail rather than call the LLM if a cache entry is missing")
    args = ap.parse_args()
    critic_model = args.critic_model or args.model

    run = Path(args.run)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = RunManifest(run_id="ui-fixtures", course_name=COURSE_ID)

    corpus = CourseCorpus.model_validate_json((run / "corpus.json").read_text())
    kus_list = KUList.model_validate_json((run / "kus.json").read_text()).knowledge_units
    kus = {k.id: k for k in kus_list}

    # -- structure checks ------------------------------------------------------
    no_short = set(kus) - set(SHORT_TITLES)
    if no_short:
        sys.exit(f"KUs without a short title: {sorted(no_short)}")

    def lecture_of(ku: KnowledgeUnit) -> int:
        first = min(r.slide_number for r in ku.source_refs)
        return next(l.n for l in LECTURES if l.slide_start <= first <= l.slide_end)

    def topic_of(ku: KnowledgeUnit) -> str:
        return f"lecture-{lecture_of(ku)}"  # a topic is a lecture (plan D2)

    # -- 1. manifests ----------------------------------------------------------
    video_kus = sorted(p.parent.name for p in run.glob("ku-*/final.mp4"))
    log(f"videos found: {video_kus}")
    manifests = {}
    for dirname in video_kus:
        manifests[dirname] = build_ui_manifest(run / dirname)

    # -- 2/3. LLM items --------------------------------------------------------
    cache = run / "ui_cache"

    def need_llm(path: Path):
        if args.skip_llm and not path.exists():
            sys.exit(f"--skip-llm but no cache at {path}")

    video_gen: dict[str, tuple[VideoGen, list[dict]]] = {}
    for dirname in video_kus:
        ku = kus[dirname]
        path = cache / f"video-{ku.id}.json"
        need_llm(path)
        script = json.loads((run / dirname / "script.json").read_text())
        m = manifests[dirname]

        def make_video(ku=ku, script=script, m=m):
            log(f"video {ku.id}: generating")
            gen, flags = generate_video_gen(ku, script, m, slide_material(corpus, m["source_slides"]), model=args.model,
                                            critic_model=critic_model, manifest=manifest, log=log)
            return {"gen": gen.model_dump(), "flags": flags}

        data = cached(path, args.regen, make_video)
        video_gen[ku.id] = (VideoGen.model_validate(data["gen"]), data["flags"])

    # -- 4. assemble -------------------------------------------------------------
    items: list[Item] = []
    flags_by_id: dict[str, str] = {}

    def refs(slides: list[int]) -> list[SlideRef]:
        return [SlideRef(deck_name="slides", slide_number=n) for n in slides]

    videos: list[VideoFixture] = []
    for dirname in video_kus:
        ku = kus[dirname]
        tid = topic_of(ku)
        g, flags = video_gen[ku.id]
        m = manifests[dirname]
        script = json.loads((run / dirname / "script.json").read_text())
        src_refs = refs(m["source_slides"])
        items.extend(video_items(ku.id, tid, g, src_refs))
        for f in flags:
            flags_by_id[f["id"]] = f["issue"]
        claims = video_claims(g, script)
        videos.append(VideoFixture(
            id=ku.id, ku_id=ku.id, title=ku.title, short_title=SHORT_TITLES[ku.id], topic_id=tid, lecture_n=lecture_of(ku),
            duration_s=m["duration_s"], segments=m["segments"],
            video_src=str(run / dirname / "final.mp4"), poster_src=str(run / dirname / "ui" / "poster.jpg"),
            vtt_src=str(run / dirname / "ui" / "captions.vtt"),
            video_url=f"/fixtures/{ku.id}/video.mp4", poster_url=f"/fixtures/{ku.id}/poster.jpg", vtt_url=f"/fixtures/{ku.id}/captions.vtt",
            checkpoint=checkpoint_for(m, f"cp-{ku.id}"),
            next_session_item_id=f"ns-{ku.id}", prove_it_item_id=f"pi-{ku.id}",
            sentence_frame=SentenceFrame(template=g.sentence_frame_template, answers=g.sentence_frame_answers),
            claims=claims, tailoring=tailoring_for(ku, kus),
            transcript=[TranscriptRow(**r) for r in m["transcript"]], source_slides=m["source_slides"],
            captions_burned_in=m.get("captions_burned_in", False),
            prerequisite_titles=[SHORT_TITLES[p] for p in ku.prerequisites if p in kus],
        ))

    balance_positions(items)

    topics = [
        Topic(id=f"lecture-{l.n}", title=l.title, ku_ids=[k.id for k in kus_list if lecture_of(k) == l.n], first_lecture=l.n)
        for l in LECTURES
    ]
    video_by_ku = {v.ku_id: v.id for v in videos}
    ku_entries = [
        KuEntry(
            id=k.id, title=k.title, short_title=SHORT_TITLES[k.id], topic_id=topic_of(k), lecture_n=lecture_of(k),
            video_id=video_by_ku.get(k.id), bloom_level=k.bloom_level,
            # the pipeline's graph can name a KU that was dropped from the run; the Course validator rejects those
            prerequisites=list(k.prerequisites),
        )
        for k in sorted(kus_list, key=lambda k: min(r.slide_number for r in k.source_refs))
    ]
    course = Course(
        id=COURSE_ID, code=COURSE_CODE, name=COURSE_NAME, eyebrow=COURSE_NAME.upper(),
        syllabus_summary=SYLLABUS_SUMMARY, config=CourseConfig(upcoming_lecture_override=UPCOMING_LECTURE_OVERRIDE),
        topics=topics, lectures=LECTURES, kus=ku_entries,
    )

    cited = sorted({n for v in videos for n in v.source_slides} | {r.slide_number for it in items for r in it.source_refs})
    slides = {str(n): (corpus.slide_by_ref("slides", n).text if corpus.slide_by_ref("slides", n) else "") for n in cited}

    (out / "course.json").write_text(course.model_dump_json(indent=2))
    (out / "items.json").write_text(json.dumps([i.model_dump() for i in items], indent=2, ensure_ascii=False))
    (out / "videos.json").write_text(json.dumps([v.model_dump() for v in videos], indent=2, ensure_ascii=False))
    (out / "slides.json").write_text(json.dumps(slides, indent=2, ensure_ascii=False))

    # -- review sheet ------------------------------------------------------------
    lines = ["# Fixture review sheet", "",
             "Generated by `scripts/build_ui_fixtures.py`. **Read every item and claim before a usability session.**",
             "A ⚠ means the critic still objected after one regeneration.", ""]
    for it in items:
        flag = f"  ⚠ {flags_by_id[it.id]}" if it.id in flags_by_id else ""
        lines += [f"### `{it.id}` · {it.context} · topic `{it.topic_id}`{flag}", f"**{it.stem}**"]
        lines += [f"- {'✅' if i == it.correct_index else '▫️'} {o}" for i, o in enumerate(it.options)]
        lines += [f"_Why:_ {it.explanation}", f"_Hint:_ {it.hint or '—'}", ""]
    for v in videos:
        lines += [f"## Video `{v.id}` — {v.title}", f"Checkpoint at {v.checkpoint.t:.1f}s (rewatch from {v.checkpoint.rewatch_from:.1f}s)",
                  f"Sentence frame: {v.sentence_frame.template}  →  {v.sentence_frame.answers}"]
        for c in v.claims:
            key = f"claim-{v.id}-{c.segment_idx}"
            flag = f"  ⚠ {flags_by_id[key]}" if key in flags_by_id else ""
            lines.append(f"- claim {c.idx} (segment {c.segment_idx}, slides {[r.slide_number for r in c.slide_refs]}): {c.text}{flag}")
        lines.append("")
    (out / "_review.md").write_text("\n".join(lines))

    cost = manifest.total_cost_usd(PRICE_PER_MTOK)
    log(f"wrote {len(items)} items, {len(videos)} videos, {len(topics)} topics -> {out}  (LLM cost this run ≈ ${cost:.2f})")
    if flags_by_id:
        log(f"⚠ {len(flags_by_id)} item(s) still flagged by the critic — see _review.md: {sorted(flags_by_id)}")


if __name__ == "__main__":
    main()
