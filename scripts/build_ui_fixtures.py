#!/usr/bin/env python
"""
Build the Phase 0 UI fixtures (plan §10) from a finished pipeline run.

    uv run python scripts/build_ui_fixtures.py --run runs/dev --out apps/web/fixtures
    cd apps/web && npm run fixtures        # copies the media into public/fixtures/

What it does
  1. UI manifest per rendered video (poster, VTT, segment spans, checkpoint time,
     transcript) — no LLM (animation_agent/ui_manifest.py).
  2. Course structure: the topic grouping and the invented 3-lecture schedule are
     AUTHOR DECISIONS written below (TOPICS / LECTURES), not LLM output.
  3. Items and claims via the LLM, grounded only in the cited slides, then checked by
     a critic pass; one regeneration if the critic objects:
       per topic  -> onboarding items + re-check items
       per video  -> checkpoint, next-session and prove-it items, a sentence
                     frame for screen 7, and one claim per deliver/end segment.
     Results are cached in <run>/ui_cache/ so re-running costs nothing (--regen to redo).
  4. Writes apps/web/fixtures/{course,items,videos,slides}.json and _review.md.

The persona's history (levels, calibration, Week 7 story) is hand-written in the web
app (lib/api/persona.ts). READ _review.md before any usability session: every item
and claim is listed there with its keyed answer and any critic flags.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))

from animation_agent.ui_manifest import build_ui_manifest, checkpoint_for
from syllabyte_common.learner import (
    MCQ,
    Claim,
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
    structured,
    text_block,
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

# topic id -> (title, blurb, [KU ids]). Onboarding: 2 items per topic. Re-check: 6 total.
TOPICS: dict[str, tuple[str, str, list[str]]] = {
    "causal-questions": (
        "Causal questions", "Turning a question about cause into something you can measure.",
        ["ku-random-assignment-origin", "ku-health-insurance-question",
         "ku-outcome-measure-health-index", "ku-treatment-control-sample",
         "ku-reading-difference-table", "ku-apples-oranges-confounders"],
    ),
    "potential-outcomes": (
        "Potential outcomes", "The two worlds behind every cause-and-effect claim.",
        ["ku-potential-outcomes", "ku-individual-causal-effect",
         "ku-fundamental-problem-observable-outcome", "ku-naive-comparison-timmy-spike"],
    ),
    "selection-bias": (
        "Selection bias", "Why comparing the insured with the uninsured misleads.",
        ["ku-selection-bias-decomposition", "ku-selection-bias-general-formula",
         "ku-law-of-large-numbers", "ku-lln-eliminates-selection-bias"],
    ),
    "randomization": (
        "Randomization in practice", "How a coin toss fixes selection bias, and how to check it did.",
        ["ku-coin-toss-average-causal-effect", "ku-balance-checking", "ku-rand-hie-design",
         "ku-rand-hie-balance-tables", "ku-rand-hie-results", "ku-summary-avoiding-selection-bias"],
    ),
}
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

RECHECK_PER_TOPIC = {"causal-questions": 1, "potential-outcomes": 2, "selection-bias": 2, "randomization": 1}
ONBOARDING_PER_TOPIC = 2

# Invented schedule: the single deck is split into three "lectures".
LECTURES = [
    Lecture(n=1, title="Causal questions and potential outcomes", week=1, slide_start=1, slide_end=16),
    Lecture(n=2, title="Selection bias", week=2, slide_start=17, slide_end=24),
    Lecture(n=3, title="Randomization", week=3, slide_start=25, slide_end=34),
]
UPCOMING_LECTURE_OVERRIDE = 3  # Phase 0 pretends Lecture 3 is next, so all 4 videos qualify

PACE_WPM = {1: 140, 2: 155, 3: 165}  # plan §7.4

# --------------------------------------------------------------------------
# LLM schemas + prompts
# --------------------------------------------------------------------------

ITEM_SYSTEM = """You write short multiple-choice questions for a university course's micro-learning app. Students see one question at a time on a phone.

Rules:
- Ground every question ONLY in the supplied slides and narration. Never use outside facts.
- Exactly 3 options. Exactly one is correct. The two wrong options must be plausible (a common misconception) but clearly wrong given the material. Never use "all of the above" or "none of the above".
- The stem is one sentence, under 28 words, and self-contained. Do not say "according to the slide" or "in the video".
- Vary which option is correct (correct_index 0, 1 and 2 should all appear across a batch).
- explanation: one or two plain sentences saying why the right option is right.
- hint: a nudge toward the idea that does not reveal the answer, or null.
- difficulty_prior: your estimate on a logit scale, -2 (very easy) to 2 (hard); 0 is medium.
- Write math as plain text (for example "Y1 - Y0"), never LaTeX.
- Keep options short (under 14 words each)."""


class TopicMCQ(MCQ):
    ku_id: str
    slides: list[int]


class TopicGen(BaseModel):
    onboarding: list[TopicMCQ]
    recheck: list[TopicMCQ]


class ClaimGen(BaseModel):
    segment_idx: int
    text: str


class VideoGen(BaseModel):
    checkpoint: MCQ
    next_session: MCQ
    prove_it: MCQ
    sentence_frame_template: str  # one sentence with exactly two blanks written ___
    sentence_frame_answers: list[str]
    claims: list[ClaimGen]


class Verdict(BaseModel):
    id: str
    ok: bool
    issue: str = ""


class Verdicts(BaseModel):
    verdicts: list[Verdict]


CRITIC_SYSTEM = """You check quiz items and factual claims against course material. Be strict but fair.
For every item verify: (1) the keyed answer is correct according to the material; (2) no other option is also defensible; (3) the wrong options are not secretly correct; (4) the stem is self-contained and unambiguous.
For every claim verify it is a statement the cited narration actually makes and the slides support, with no added facts.
Return one verdict per id. Set ok=false only for a real problem and say what it is in one sentence."""


def topic_prompt(topic_id: str, kus: list[KnowledgeUnit], slide_text: str, extra: str = "") -> str:
    title = TOPICS[topic_id][0]
    ku_lines = "\n".join(f"- {k.id}: {k.title} — {k.summary} (slides {[r.slide_number for r in k.source_refs]})" for k in kus)
    return f"""Topic: "{title}".

Knowledge units in this topic:
{ku_lines}

Return exactly {ONBOARDING_PER_TOPIC} questions in the `onboarding` list and exactly {RECHECK_PER_TOPIC[topic_id]} question(s) in the `recheck` list. The `recheck` list must not be empty.
- Onboarding questions find out what a student might already know BEFORE the lecture: the first is foundational, the second a little harder. They must be answerable by someone who has seen the idea before, not trick questions.
- Re-check questions come mid-semester, after the videos: they test understanding of this topic and must not repeat an onboarding question.
- For each question set ku_id (the knowledge unit it is grounded in) and slides (the slide numbers that support it).

Slides (text and images follow):
{slide_text}{extra}"""


def video_prompt(ku: KnowledgeUnit, script: dict, slide_text: str, claim_segments: list[int], last_deliver: int, extra: str = "") -> str:
    seg_lines = "\n".join(f"[segment {i} · {s['phase']}] {s['narration'] if 'narration' in s else ' '.join(b['narration'] for b in s['beats'])}" for i, s in enumerate(script["segments"]))
    return f"""A 70-second explainer video was made for this knowledge unit.

Knowledge unit: {ku.title}
Summary: {ku.summary}

Narration by segment:
{seg_lines}

Write:
1. checkpoint: a question about the main idea taught in segment {last_deliver} (the last deliver segment). The video pauses on it right after that segment.
2. next_session: a DIFFERENT question on the same idea, asked a day later to test memory. It must not reuse the checkpoint's wording or options.
3. prove_it: one question a student who already knows this topic would answer correctly, but a student who does not would likely miss. It tests the core concept, not trivia.
4. sentence_frame_template: ONE sentence that captures the core idea, with exactly two blanks written as ___ (three underscores). sentence_frame_answers: the two words/phrases that fill them, in order.
5. claims: EXACTLY ONE entry per segment index in {claim_segments} — {len(claim_segments)} entries in total, never two for the same segment. Each is ONE self-contained factual statement (under 22 words) that the narration makes in that segment. Paraphrase, add nothing, no hedging; keep concrete numbers if the narration gives them.
{extra}
Slides (text and images follow):
{slide_text}"""


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


def critic_pass(items_text: str, material_text: str, images: list[dict], ids: list[str], *, stage: str, model: str, manifest: RunManifest) -> list[Verdict]:
    prompt = (
        f"Course material (slides):\n{material_text}\n\nItems and claims to check "
        f"(ids: {', '.join(ids)}):\n{items_text}"
    )
    result = structured(
        schema=Verdicts, content=[text_block(prompt), *images], system=CRITIC_SYSTEM,
        stage=stage, model=model, max_tokens=4000, manifest=manifest,
    )
    return result.verdicts


def mcq_text(id_: str, m: MCQ) -> str:
    opts = "\n".join(f"   {'ABC'[i]}. {o}{'  <-- keyed' if i == m.correct_index else ''}" for i, o in enumerate(m.options))
    return f"[{id_}] {m.stem}\n{opts}\n   explanation: {m.explanation}"


def generate_with_critic(*, make, describe, ids_of, material: tuple[str, list[dict]], stage: str, model: str, manifest: RunManifest):
    """make(extra) -> generated; describe(gen) -> text for the critic; ids_of(gen) -> ids.
    Returns (gen, remaining_flags)."""
    gen = make("")
    verdicts = critic_pass(describe(gen), material[0], material[1], ids_of(gen), stage=f"{stage}_critic", model=model, manifest=manifest)
    bad = [v for v in verdicts if not v.ok]
    if bad:
        log(f"  {stage}: critic objected to {[v.id for v in bad]} — regenerating once")
        feedback = "\n\nA reviewer found problems in your previous attempt. Fix them:\n" + "\n".join(f"- {v.id}: {v.issue}" for v in bad)
        gen = make(feedback)
        verdicts = critic_pass(describe(gen), material[0], material[1], ids_of(gen), stage=f"{stage}_critic2", model=model, manifest=manifest)
        bad = [v for v in verdicts if not v.ok]
    return gen, [{"id": v.id, "issue": v.issue} for v in bad]


def balance_positions(items: list[Item]) -> None:
    """The model favours some answer slots (in one run every prove-it key was option C).
    Rotate the correct answer through A/B/C deterministically by swapping options; nothing
    in the explanations or hints refers to option positions."""
    for idx, it in enumerate(sorted(items, key=lambda i: i.id)):
        target = idx % 3
        c = it.correct_index
        if c != target:
            it.options[c], it.options[target] = it.options[target], it.options[c]
            it.correct_index = target


# --------------------------------------------------------------------------
# tailoring skeletons (deterministic; plan §7.4)
# --------------------------------------------------------------------------


def tailoring_for(ku: KnowledgeUnit, topic_id: str, kus: dict[str, KnowledgeUnit], ku_topic: dict[str, str]) -> dict[str, list[TailoringSkeleton]]:
    prereq = kus.get(ku.prerequisites[0]) if ku.prerequisites else None
    prereq_topic = ku_topic.get(prereq.id, topic_id) if prereq else topic_id
    recap = f"The full recap of “{SHORT_TITLES[prereq.id]}”" if prereq else "A recap of the basics"
    short_recap = f"A short recap of “{SHORT_TITLES[prereq.id]}”" if prereq else "A short recap of the basics"
    S = TailoringSkeleton
    return {
        "1": [
            S(kind="added", what=short_recap, dimension="recap", evidence_topic_id=prereq_topic),
            S(kind="added", what="A full, step-by-step worked example", dimension="example", evidence_topic_id=topic_id),
            S(kind="set_to", what=f"Hint shown with the question, about {PACE_WPM[1]} words a minute", dimension="support"),
        ],
        "2": [
            S(kind="left_out", what=recap, dimension="recap", evidence_topic_id=prereq_topic),
            S(kind="added", what="One worked example", dimension="example", evidence_topic_id=topic_id),
            S(kind="set_to", what=f"Hints on request, about {PACE_WPM[2]} words a minute", dimension="support"),
        ],
        "3": [
            S(kind="left_out", what=recap, dimension="recap", evidence_topic_id=prereq_topic),
            S(kind="left_out", what="The worked example, replaced by a “what if” question", dimension="example", evidence_topic_id=topic_id),
            S(kind="set_to", what=f"No hints, about {PACE_WPM[3]} words a minute", dimension="support"),
        ],
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="runs/dev")
    ap.add_argument("--out", default="apps/web/fixtures")
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
    ku_topic: dict[str, str] = {}
    for tid, (_, _, ids) in TOPICS.items():
        for kid in ids:
            if kid not in kus:
                sys.exit(f"TOPICS references unknown KU {kid}")
            ku_topic[kid] = tid
    missing = set(kus) - set(ku_topic)
    if missing:
        sys.exit(f"KUs not assigned to a topic: {sorted(missing)}")
    no_short = set(kus) - set(SHORT_TITLES)
    if no_short:
        sys.exit(f"KUs without a short title: {sorted(no_short)}")

    def lecture_of(ku: KnowledgeUnit) -> int:
        first = min(r.slide_number for r in ku.source_refs)
        return next(l.n for l in LECTURES if l.slide_start <= first <= l.slide_end)

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

    topic_gen: dict[str, tuple[TopicGen, list[dict]]] = {}
    for tid, (title, _, ku_ids) in TOPICS.items():
        path = cache / f"topic-{tid}.json"
        need_llm(path)

        def make_topic(tid=tid, ku_ids=ku_ids):
            tkus = [kus[i] for i in ku_ids]
            slides = sorted({r.slide_number for k in tkus for r in k.source_refs})
            material = slide_material(corpus, slides)
            log(f"topic {tid}: generating (slides {slides[0]}–{slides[-1]})")

            def make(extra: str) -> TopicGen:
                want = (ONBOARDING_PER_TOPIC, RECHECK_PER_TOPIC[tid])
                for _ in range(2):
                    g = structured(
                        schema=TopicGen, content=[text_block(topic_prompt(tid, tkus, material[0], extra)), *material[1]],
                        system=ITEM_SYSTEM, stage="ui_topic_items", model=args.model, max_tokens=16000, manifest=manifest,
                    )
                    got = (len(g.onboarding), len(g.recheck))
                    if got == want:
                        return g
                    log(f"  topic {tid}: got {got[0]} onboarding / {got[1]} recheck, need {want[0]} / {want[1]} — retrying")
                    extra += f"\n\nYour previous answer had {got[0]} onboarding and {got[1]} recheck questions. I need exactly {want[0]} onboarding and {want[1]} recheck."
                sys.exit(f"topic {tid}: could not get the requested item counts")

            def describe(g: TopicGen) -> str:
                return "\n\n".join(
                    [mcq_text(f"ob-{tid}-{i+1}", m) for i, m in enumerate(g.onboarding)]
                    + [mcq_text(f"rc-{tid}-{i+1}", m) for i, m in enumerate(g.recheck)]
                )

            def ids_of(g: TopicGen) -> list[str]:
                return [f"ob-{tid}-{i+1}" for i in range(len(g.onboarding))] + [f"rc-{tid}-{i+1}" for i in range(len(g.recheck))]

            gen, flags = generate_with_critic(make=make, describe=describe, ids_of=ids_of, material=material,
                                              stage=f"topic_{tid}", model=critic_model, manifest=manifest)
            if len(gen.onboarding) != ONBOARDING_PER_TOPIC or len(gen.recheck) != RECHECK_PER_TOPIC[tid]:
                sys.exit(f"topic {tid}: wrong item counts ({len(gen.onboarding)}/{len(gen.recheck)})")
            return {"gen": gen.model_dump(), "flags": flags}

        data = cached(path, args.regen, make_topic)
        topic_gen[tid] = (TopicGen.model_validate(data["gen"]), data["flags"])

    video_gen: dict[str, tuple[VideoGen, list[dict]]] = {}
    for dirname in video_kus:
        ku = kus[dirname]
        path = cache / f"video-{ku.id}.json"
        need_llm(path)
        script = json.loads((run / dirname / "script.json").read_text())
        m = manifests[dirname]
        last_deliver = m["checkpoint_times"]["segment_idx"]
        claim_segments = [i for i, s in enumerate(script["segments"]) if s["phase"] in ("deliver", "end")]

        def make_video(ku=ku, script=script, last_deliver=last_deliver, claim_segments=claim_segments, m=m):
            material = slide_material(corpus, m["source_slides"])
            log(f"video {ku.id}: generating")

            def make(extra: str) -> VideoGen:
                for _ in range(2):
                    g = structured(
                        schema=VideoGen,
                        content=[text_block(video_prompt(ku, script, material[0], claim_segments, last_deliver, extra)), *material[1]],
                        system=ITEM_SYSTEM, stage="ui_video_items", ku_id=ku.id, model=args.model, max_tokens=16000, manifest=manifest,
                    )
                    # keep the first claim per wanted segment; drop claims for other segments
                    first: dict[int, ClaimGen] = {}
                    for c in g.claims:
                        if c.segment_idx in claim_segments and c.segment_idx not in first:
                            first[c.segment_idx] = c
                    if sorted(first) == claim_segments:
                        g.claims = [first[i] for i in claim_segments]
                        return g
                    log(f"  video {ku.id}: claims cover segments {sorted(first)}, need {claim_segments} — retrying")
                    extra += f"\n\nYour previous answer did not give exactly one claim for each of the segments {claim_segments}. Do that."
                sys.exit(f"{ku.id}: could not get one claim per segment")

            def describe(g: VideoGen) -> str:
                narr = {i: (s["narration"] if "narration" in s else " ".join(b["narration"] for b in s["beats"])) for i, s in enumerate(script["segments"])}
                items = [mcq_text(f"cp-{ku.id}", g.checkpoint), mcq_text(f"ns-{ku.id}", g.next_session), mcq_text(f"pi-{ku.id}", g.prove_it)]
                claims = [f"[claim-{ku.id}-{c.segment_idx}] {c.text}\n   narration in segment {c.segment_idx}: {narr[c.segment_idx]}" for c in g.claims]
                return "\n\n".join(items + claims) + f"\n\nsentence frame: {g.sentence_frame_template} -> {g.sentence_frame_answers}"

            def ids_of(g: VideoGen) -> list[str]:
                return [f"cp-{ku.id}", f"ns-{ku.id}", f"pi-{ku.id}"] + [f"claim-{ku.id}-{c.segment_idx}" for c in g.claims]

            gen, flags = generate_with_critic(make=make, describe=describe, ids_of=ids_of, material=material,
                                              stage=f"video_{ku.id}", model=critic_model, manifest=manifest)
            got = sorted(c.segment_idx for c in gen.claims)
            if got != claim_segments:
                sys.exit(f"{ku.id}: claims for segments {got}, expected {claim_segments}")
            if gen.sentence_frame_template.count("___") != 2 or len(gen.sentence_frame_answers) != 2:
                sys.exit(f"{ku.id}: sentence frame must have exactly two blanks")
            return {"gen": gen.model_dump(), "flags": flags}

        data = cached(path, args.regen, make_video)
        video_gen[ku.id] = (VideoGen.model_validate(data["gen"]), data["flags"])

    # -- 4. assemble -------------------------------------------------------------
    items: list[Item] = []
    flags_by_id: dict[str, str] = {}

    def refs(slides: list[int]) -> list[SlideRef]:
        return [SlideRef(deck_name="slides", slide_number=n) for n in slides]

    for tid, (g, flags) in topic_gen.items():
        for kind, ctx, allow in (("onboarding", "onboarding", True), ("recheck", "recheck", True)):
            prefix = "ob" if kind == "onboarding" else "rc"
            for i, m in enumerate(getattr(g, kind), 1):
                items.append(Item(id=f"{prefix}-{tid}-{i}", ku_id=m.ku_id, topic_id=tid, context=ctx, stem=m.stem,
                                  options=m.options, correct_index=m.correct_index, allows_not_sure=allow,
                                  explanation=m.explanation, hint=m.hint, difficulty_prior=m.difficulty_prior,
                                  source_refs=refs(m.slides)))
        for f in flags:
            flags_by_id[f["id"]] = f["issue"]

    videos: list[VideoFixture] = []
    for dirname in video_kus:
        ku = kus[dirname]
        tid = ku_topic[ku.id]
        g, flags = video_gen[ku.id]
        m = manifests[dirname]
        script = json.loads((run / dirname / "script.json").read_text())
        src_refs = refs(m["source_slides"])
        for ctx, prefix, mcq, allow in (("checkpoint", "cp", g.checkpoint, False), ("next_session", "ns", g.next_session, False), ("prove_it", "pi", g.prove_it, True)):
            items.append(Item(id=f"{prefix}-{ku.id}", ku_id=ku.id, topic_id=tid, context=ctx, stem=mcq.stem,
                              options=mcq.options, correct_index=mcq.correct_index, allows_not_sure=allow,
                              explanation=mcq.explanation, hint=mcq.hint, difficulty_prior=mcq.difficulty_prior,
                              source_refs=src_refs))
        for f in flags:
            flags_by_id[f["id"]] = f["issue"]
        claims = [
            Claim(idx=i, text=c.text.strip(), segment_idx=c.segment_idx,
                  slide_refs=[SlideRef(**r) for r in script["segments"][c.segment_idx]["source_refs"]])
            for i, c in enumerate(sorted(g.claims, key=lambda c: c.segment_idx))
        ]
        videos.append(VideoFixture(
            id=ku.id, ku_id=ku.id, title=ku.title, short_title=SHORT_TITLES[ku.id], topic_id=tid, lecture_n=lecture_of(ku),
            duration_s=m["duration_s"], segments=m["segments"],
            video_src=str(run / dirname / "final.mp4"), poster_src=str(run / dirname / "ui" / "poster.jpg"),
            vtt_src=str(run / dirname / "ui" / "captions.vtt"),
            video_url=f"/fixtures/{ku.id}/video.mp4", poster_url=f"/fixtures/{ku.id}/poster.jpg", vtt_url=f"/fixtures/{ku.id}/captions.vtt",
            checkpoint=checkpoint_for(m, f"cp-{ku.id}"),
            next_session_item_id=f"ns-{ku.id}", prove_it_item_id=f"pi-{ku.id}",
            sentence_frame=SentenceFrame(template=g.sentence_frame_template, answers=g.sentence_frame_answers),
            claims=claims, tailoring={k: v for k, v in tailoring_for(ku, tid, kus, ku_topic).items()},
            transcript=[TranscriptRow(**r) for r in m["transcript"]], source_slides=m["source_slides"],
            prerequisite_titles=[SHORT_TITLES[p] for p in ku.prerequisites if p in kus],
        ))

    balance_positions(items)

    topics = [
        Topic(id=tid, title=title, blurb=blurb, ku_ids=ids, first_lecture=min(lecture_of(kus[i]) for i in ids))
        for tid, (title, blurb, ids) in TOPICS.items()
    ]
    video_by_ku = {v.ku_id: v.id for v in videos}
    ku_entries = [
        KuEntry(id=k.id, title=k.title, short_title=SHORT_TITLES[k.id], topic_id=ku_topic[k.id], lecture_n=lecture_of(k), video_id=video_by_ku.get(k.id))
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
