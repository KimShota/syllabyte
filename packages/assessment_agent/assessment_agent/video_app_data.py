"""
What the phone needs about a video besides the mp4: its questions, claims, sentence frame, tailoring rows and the
manifest of spans, transcript and checkpoint (plan/participant-ready-plan.md S2).

This was the body of scripts/build_ui_fixtures.py's main(), which can only run over a finished `runs/dev` folder. It
is here so the same code makes one video's data in the worker (ingestion_agent/video_job.py) and the fixtures script.
Nothing here renders or touches the network except the model calls in `generate_video_gen`.
"""

from __future__ import annotations

import zlib
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from animation_agent.ui_manifest import checkpoint_for
from assessment_agent.item_writing import ITEM_SYSTEM, mcq_text
from assessment_agent.item_writing import generate_with_critic as _generate_with_critic
from syllabyte_common.learner import (
    MCQ,
    Claim,
    Item,
    SentenceFrame,
    TailoringSkeleton,
    TranscriptRow,
)
from syllabyte_common.llm import image_block, structured, text_block
from syllabyte_common.models import KnowledgeUnit, RunManifest, Slide, SlideRef

PACE_WPM = {1: 140, 2: 155, 3: 165}  # plan §7.4

Log = Callable[[str], None]


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


def slides_material(slides: list[Slide]) -> tuple[str, list[dict]]:
    """The slides' text and images, as the video prompt and its critic read them."""
    parts, images, seen = [], [], set()
    for slide in slides:
        if slide.slide_number in seen:
            continue
        seen.add(slide.slide_number)
        parts.append(f"[slide {slide.slide_number}]\n{slide.text}")
        if slide.image_path and Path(slide.image_path).exists():
            images.append(image_block(slide.image_path))
    return "\n\n".join(parts), images


def claim_segments_of(script: dict) -> list[int]:
    """The segments a claim is written for: the deliver and end phases."""
    return [i for i, s in enumerate(script["segments"]) if s["phase"] in ("deliver", "end")]


def generate_video_gen(
    ku: KnowledgeUnit, script: dict, manifest_ui: dict, material: tuple[str, list[dict]], *, model: str, critic_model: str,
    manifest: RunManifest, log: Log = print,
) -> tuple[VideoGen, list[dict]]:
    """The video's three questions, sentence frame and one claim per deliver/end segment, written from the slides and
    checked by a critic pass (flags are returned, not fatal). Raises ValueError if the claims or the frame are unusable."""
    last_deliver = manifest_ui["checkpoint_times"]["segment_idx"]
    claim_segments = claim_segments_of(script)

    def make(extra: str) -> VideoGen:
        for _ in range(2):
            g = structured(
                schema=VideoGen,
                content=[text_block(video_prompt(ku, script, material[0], claim_segments, last_deliver, extra)), *material[1]],
                system=ITEM_SYSTEM, stage="ui_video_items", ku_id=ku.id, model=model, max_tokens=16000, manifest=manifest,
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
        raise ValueError(f"{ku.id}: could not get one claim per segment")

    narr = {i: (s["narration"] if "narration" in s else " ".join(b["narration"] for b in s["beats"])) for i, s in enumerate(script["segments"])}

    def describe(g: VideoGen) -> str:
        items = [mcq_text(f"cp-{ku.id}", g.checkpoint), mcq_text(f"ns-{ku.id}", g.next_session), mcq_text(f"pi-{ku.id}", g.prove_it)]
        claims = [f"[claim-{ku.id}-{c.segment_idx}] {c.text}\n   narration in segment {c.segment_idx}: {narr[c.segment_idx]}" for c in g.claims]
        return "\n\n".join(items + claims) + f"\n\nsentence frame: {g.sentence_frame_template} -> {g.sentence_frame_answers}"

    def ids_of(g: VideoGen) -> list[str]:
        return [f"cp-{ku.id}", f"ns-{ku.id}", f"pi-{ku.id}"] + [f"claim-{ku.id}-{c.segment_idx}" for c in g.claims]

    gen, flags = _generate_with_critic(make=make, describe=describe, ids_of=ids_of, material=material, stage=f"video_{ku.id}",
                                       model=critic_model, manifest=manifest, log=log)
    got = sorted(c.segment_idx for c in gen.claims)
    if got != claim_segments:
        raise ValueError(f"{ku.id}: claims for segments {got}, expected {claim_segments}")
    if gen.sentence_frame_template.count("___") != 2 or len(gen.sentence_frame_answers) != 2:
        raise ValueError(f"{ku.id}: sentence frame must have exactly two blanks")
    return gen, flags


def balance_positions(items: list[Item], offset: int = 0) -> None:
    """The model favours some answer slots (in one run every prove-it key was option C).
    Rotate the correct answer through A/B/C deterministically by swapping options; nothing
    in the explanations or hints refers to option positions. `offset` shifts the rotation, so one video's three items
    don't always put the checkpoint's key in A."""
    for idx, it in enumerate(sorted(items, key=lambda i: i.id)):
        target = (idx + offset) % 3
        c = it.correct_index
        if c != target:
            it.options[c], it.options[target] = it.options[target], it.options[c]
            it.correct_index = target


def position_offset(ku_id: str) -> int:
    """A stable 0-2 per KU for balance_positions."""
    return zlib.crc32(ku_id.encode()) % 3


def video_items(ku_id: str, topic_id: str, g: VideoGen, src_refs: list[SlideRef]) -> list[Item]:
    """The video's checkpoint, next-session and prove-it items."""
    items = []
    for ctx, prefix, mcq, allow in (("checkpoint", "cp", g.checkpoint, False), ("next_session", "ns", g.next_session, False), ("prove_it", "pi", g.prove_it, True)):
        items.append(Item(id=f"{prefix}-{ku_id}", ku_id=ku_id, topic_id=topic_id, context=ctx, stem=mcq.stem,
                          options=mcq.options, correct_index=mcq.correct_index, allows_not_sure=allow,
                          explanation=mcq.explanation, hint=mcq.hint, difficulty_prior=mcq.difficulty_prior,
                          source_refs=src_refs))
    return items


def video_claims(g: VideoGen, script: dict) -> list[Claim]:
    return [
        Claim(idx=i, text=c.text.strip(), segment_idx=c.segment_idx,
              slide_refs=[SlideRef(**r) for r in script["segments"][c.segment_idx]["source_refs"]])
        for i, c in enumerate(sorted(g.claims, key=lambda c: c.segment_idx))
    ]


def tailoring_for(ku_id: str, prereq: tuple[str, str] | None) -> dict[str, list[TailoringSkeleton]]:
    """What differs at each level. The evidence is per KU (plan D2): the first prerequisite for the recap rows, the
    KU itself for the example rows, so the receipt can cite the student's own answers about exactly those concepts.
    `prereq`: the first prerequisite's (id, short title), or None."""
    prereq_ku = prereq[0] if prereq else ku_id
    recap = f"The full recap of “{prereq[1]}”" if prereq else "A recap of the basics"
    short_recap = f"A short recap of “{prereq[1]}”" if prereq else "A short recap of the basics"
    S = TailoringSkeleton
    return {
        "1": [
            S(kind="added", what=short_recap, dimension="recap", evidence_ku_id=prereq_ku),
            S(kind="added", what="A full, step-by-step worked example", dimension="example", evidence_ku_id=ku_id),
            S(kind="set_to", what=f"Hint shown with the question, about {PACE_WPM[1]} words a minute", dimension="support"),
        ],
        "2": [
            S(kind="left_out", what=recap, dimension="recap", evidence_ku_id=prereq_ku),
            S(kind="added", what="One worked example", dimension="example", evidence_ku_id=ku_id),
            S(kind="set_to", what=f"Hints on request, about {PACE_WPM[2]} words a minute", dimension="support"),
        ],
        "3": [
            S(kind="left_out", what=recap, dimension="recap", evidence_ku_id=prereq_ku),
            S(kind="left_out", what="The worked example, replaced by a “what if” question", dimension="example", evidence_ku_id=ku_id),
            S(kind="set_to", what=f"No hints, about {PACE_WPM[3]} words a minute", dimension="support"),
        ],
    }


def video_record(
    *, ku: KnowledgeUnit, short_title: str, topic_id: str, lecture_n: int, level: int, manifest_ui: dict, g: VideoGen,
    claims: list[Claim], prereq_short_titles: list[str], first_prereq: tuple[str, str] | None,
) -> dict:
    """The app's Video for this KU at this level, as JSON without its urls (the server adds those): everything in
    core's `Video` but video_url, poster_url and vtt_url."""
    return {
        "id": ku.id, "ku_id": ku.id, "title": ku.title, "short_title": short_title, "topic_id": topic_id, "lecture_n": lecture_n,
        "file_level": level, "duration_s": manifest_ui["duration_s"], "segments": manifest_ui["segments"],
        "checkpoint": checkpoint_for(manifest_ui, f"cp-{ku.id}").model_dump(mode="json"),
        "next_session_item_id": f"ns-{ku.id}", "prove_it_item_id": f"pi-{ku.id}",
        "sentence_frame": SentenceFrame(template=g.sentence_frame_template, answers=g.sentence_frame_answers).model_dump(mode="json"),
        "claims": [c.model_dump(mode="json") for c in claims],
        "tailoring": {k: [t.model_dump(mode="json") for t in v] for k, v in tailoring_for(ku.id, first_prereq).items()},
        "transcript": [TranscriptRow(**r).model_dump(mode="json") for r in manifest_ui["transcript"]],
        "captions_burned_in": manifest_ui.get("captions_burned_in", False),
        "source_slides": manifest_ui["source_slides"], "prerequisite_titles": prereq_short_titles, "review_status": "unreviewed",
    }


__all__ = [
    "ClaimGen", "VideoGen", "balance_positions", "claim_segments_of", "generate_video_gen", "position_offset",
    "slides_material", "tailoring_for", "video_claims", "video_items", "video_prompt", "video_record",
]
