"""
The video job (plan/participant-ready-plan.md S2): one KU's video at one level, made for a course the server holds.

The server queues a `video` job for each video a student needs (apps/server/src/uploads.ts syncVideoJobs). This runs
the video pipeline (scripts/generate_shorts.py make_ku_video: script, voices, animation, assembly) on the KU's slides,
builds the data the phone needs besides the mp4 (assessment_agent/video_app_data.py: the manifest of spans and
transcript, three questions, a sentence frame, a claim per segment), sends the three files, and returns the rest for the
server to store. A KU's video is made once per course and level and shared by everyone with that course (U8).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from animation_agent.ui_manifest import build_ui_manifest
from assessment_agent.video_app_data import (
    balance_positions,
    generate_video_gen,
    position_offset,
    slides_material,
    video_claims,
    video_items,
    video_record,
)
from curriculum_alignment_agent.deck_kus import UploadKU
from syllabyte_common.llm import DEFAULT_MODEL, PRICE_PER_MTOK
from syllabyte_common.models import CourseCorpus, RunManifest, SlideDeck, SlideRef

Log = Callable[[str], None]
# the files the server keeps for a video (apps/server/src/uploads.ts VIDEO_FILES), and where the pipeline wrote them
FILES = {"video.mp4": "final.mp4", "poster.jpg": "ui/poster.jpg", "captions.vtt": "ui/captions.vtt"}


def pipeline_make_video() -> Callable[..., Path | None]:
    """scripts/generate_shorts.make_ku_video, loaded from the repository's scripts folder (it is a script, not a package;
    scripts/video_jobs.py does the same)."""
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from generate_shorts import make_ku_video  # noqa: PLC0415

    return make_ku_video


def run_video_job(
    payload: dict, deck: SlideDeck, work_dir: str | Path, upload: Callable[[str, Path], None], *, model: str = DEFAULT_MODEL,
    critic_model: str | None = None, manifest: RunManifest | None = None, log: Log = print,
    make_video: Callable[..., Path | None] | None = None,
) -> dict:
    """payload (apps/server/src/uploads.ts videoPayload): deck_id, ku (an UploadKU dict), level, lecture_n, topic_id,
    short_title, course_name, syllabus_text, prereqs ({id, title, short_title} in the order the KU had at its first
    request). `deck`: the KU's deck, rendered. `upload(name, path)` sends one of FILES to the server. Returns the
    result the server stores: {video, items, flags, cost_usd}."""
    manifest = manifest or RunManifest(run_id=f"video-{payload['ku']['id']}-{payload['level']}")
    critic_model = critic_model or model
    ku = UploadKU.model_validate(payload["ku"])
    level, prereqs = int(payload["level"]), payload.get("prereqs", [])
    ku_dir = Path(work_dir) / f"{ku.id}-L{level}"
    ku_dir.mkdir(parents=True, exist_ok=True)

    corpus = CourseCorpus(course_name=payload["course_name"], syllabus_path="", syllabus_text=payload.get("syllabus_text", ""), decks=[deck])
    if make_video is None:
        from animation_agent.renderer import missing_latex_tools

        if missing := missing_latex_tools():
            raise RuntimeError(f"LaTeX is missing on this machine ({', '.join(missing)}), so formulas can't render")
        make_video = pipeline_make_video()
    log(f"video {ku.id} at level {level}: making it")
    final = make_video(
        ku, corpus, ku_dir, manifest=manifest, level=level, prereq_titles=[p["title"] for p in prereqs], style="dialogue",
        visuals="templates",
    )
    if final is None:
        raise RuntimeError(f"{ku.id}: a segment fell back to the caption template, so the video was not assembled")

    manifest_ui = build_ui_manifest(ku_dir)
    script = json.loads((ku_dir / "script.json").read_text())
    by_n = {s.slide_number: s for s in deck.slides}
    slides = [by_n[n] for n in manifest_ui["source_slides"] if n in by_n]
    log(f"video {ku.id}: writing its questions and claims")
    gen, flags = generate_video_gen(ku, script, manifest_ui, slides_material(slides), model=model, critic_model=critic_model, manifest=manifest, log=log)

    refs = [SlideRef(deck_name=deck.name, slide_number=n) for n in manifest_ui["source_slides"]]
    items = video_items(ku.id, payload["topic_id"], gen, refs)
    balance_positions(items, position_offset(ku.id))
    first = (prereqs[0]["id"], prereqs[0]["short_title"]) if prereqs else None
    record = video_record(
        ku=ku, short_title=payload["short_title"], topic_id=payload["topic_id"], lecture_n=int(payload["lecture_n"]), level=level,
        manifest_ui=manifest_ui, g=gen, claims=video_claims(gen, script), prereq_short_titles=[p["short_title"] for p in prereqs],
        first_prereq=first,
    )
    for name, relative in FILES.items():
        upload(name, ku_dir / relative)
    return {
        "video": record,
        "items": [i.model_dump(mode="json") for i in items],
        "flags": flags,
        "cost_usd": round(manifest.total_cost_usd(PRICE_PER_MTOK), 4),
    }
