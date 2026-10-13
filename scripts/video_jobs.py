#!/usr/bin/env python
"""
Request per-student videos and make them (plan/per-student-video-plan.md, step 3).

    # A student's playlist: these KUs at these levels, in this order. Ready videos
    # come back from the cache; the rest are queued, first in the playlist first.
    uv run python scripts/video_jobs.py request --course runs/dev \\
        --want ku-potential-outcomes:1 ku-selection-bias-general-formula:2

    # Make what's queued, two videos at a time, then stop.
    uv run python scripts/video_jobs.py work --workers 2

    uv run python scripts/video_jobs.py status

`--course` is a directory with corpus.json and kus.json (a generate_shorts run
directory). Videos live under --store (default runs/videos).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from generate_shorts import log, make_ku_video  # noqa: E402

from animation_agent.renderer import missing_latex_tools  # noqa: E402
from syllabyte_common.models import CourseCorpus, KnowledgeUnit, KUList, RunManifest  # noqa: E402
from syllabyte_common.video_jobs import VideoJob, VideoStore, video_key  # noqa: E402


def load_course(course_dir: Path) -> tuple[CourseCorpus, KUList]:
    corpus = CourseCorpus.model_validate_json((course_dir / "corpus.json").read_text())
    kus = KUList.model_validate_json((course_dir / "kus.json").read_text())
    return corpus, kus


def find_ku(kus: KUList, ku_id: str) -> tuple[KnowledgeUnit, list[str]]:
    """The KU and its prerequisites' titles."""
    by_id = {k.id: k for k in kus.knowledge_units}
    if ku_id not in by_id:
        raise SystemExit(f"{ku_id} is not a KU of this course")
    ku = by_id[ku_id]
    return ku, [by_id[p].title for p in ku.prerequisites if p in by_id]


def make_video(job: VideoJob, work_dir: Path) -> Path:
    """The real generator: one KU at the job's level, through the whole pipeline."""
    corpus, kus = load_course(Path(job.course_dir))
    ku, prereq_titles = find_ku(kus, job.ku_id)
    manifest = RunManifest(run_id=job.key[:12], course_name=corpus.course_name)
    manifest_path = work_dir / "manifest.json"
    start = time.monotonic()
    video = make_ku_video(
        ku, corpus, work_dir, manifest=manifest,
        save_manifest=lambda: manifest_path.write_text(manifest.model_dump_json(indent=2)),
        level=job.level, prereq_titles=prereq_titles,
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2))
    log(f"{job.ku_id} at level {job.level}: {time.monotonic() - start:.0f}s")
    if video is None:
        raise RuntimeError("a segment fell back to the caption template, so the video was not assembled")
    return video


def show(job: VideoJob) -> str:
    where = job.video_path if job.state == "ready" else (job.error or "")
    return f"{job.state:7s} L{job.level} p{job.priority:<3d} {job.ku_id:45s} {where}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", default="runs/videos")
    sub = parser.add_subparsers(dest="command", required=True)
    req = sub.add_parser("request", help="ask for videos (KU:level), in playlist order")
    req.add_argument("--course", required=True, help="directory with corpus.json and kus.json")
    req.add_argument("--want", nargs="+", required=True, metavar="KU:LEVEL")
    work = sub.add_parser("work", help="make queued videos")
    work.add_argument("--workers", type=int, default=1)
    work.add_argument("--keep-polling", action="store_true", help="wait for new requests instead of stopping when idle")
    sub.add_parser("status", help="list every video and its state")
    args = parser.parse_args()

    store = VideoStore(args.store)
    if args.command == "request":
        course = Path(args.course)
        corpus, kus = load_course(course)
        for position, want in enumerate(args.want):
            ku_id, _, level = want.partition(":")
            if level not in ("1", "2", "3"):
                raise SystemExit(f"{want}: expected KU:LEVEL with level 1, 2 or 3")
            ku, prereq_titles = find_ku(kus, ku_id)
            key = video_key(corpus, ku, int(level), prereq_titles)
            print(show(store.request(key, ku_id=ku_id, level=int(level), course_dir=course.resolve(), priority=position)))
    elif args.command == "work":
        if missing := missing_latex_tools():
            raise SystemExit(f"LaTeX is missing ({', '.join(missing)} not on PATH): see README.md step 2.")
        for job in store.run_worker(make_video, workers=args.workers, until_idle=not args.keep_polling):
            print(show(job))
    else:
        for job in store.jobs():
            print(show(job))


if __name__ == "__main__":
    main()
