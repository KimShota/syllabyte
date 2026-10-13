"""
On-demand video jobs (plan/per-student-video-plan.md, step 3).

A student's video for a KU is made at that student's level once the level is
known. The same video serves every student whose course has the same slides
for that KU and who is at the same level, so a video is identified by what it
is made from (`video_key`): the slides the KU cites, the KU, its
prerequisites' titles, the level, and PIPELINE_VERSION.

`VideoStore` keeps one job per key under a directory:

    <root>/jobs/<key>.json      # VideoJob: state, priority, attempts, error
    <root>/videos/<key>/        # the generator's working dir; final.mp4 lands here

A request returns the cached video if it is ready, otherwise queues it (or
moves it up the queue). Workers take the queued job with the lowest priority
number first (the app passes the video's playlist position), oldest first on
ties. Every read-modify-write holds an exclusive file lock, so requests from
the app and any number of worker threads/processes see one consistent queue.
File-based for now; the Phase 1 backend can keep this interface over Mongo and
Celery.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from syllabyte_common.models import CourseCorpus, KnowledgeUnit

# Bump when a change should remake videos already in the cache (a new prompt,
# model or effort); everything made under an older version is then made again
# on its next request.
PIPELINE_VERSION = "2026-10-13"

# A failed video is retried on a later request until it has been tried this
# many times; after that it stays failed and the app shows it as unavailable.
MAX_ATTEMPTS = 2

JobState = Literal["queued", "making", "ready", "failed"]


def cited_slide_content(corpus: CourseCorpus, ku: KnowledgeUnit) -> str:
    """What the script writer reads for `ku`: each cited slide's text and
    notes, and a hash of its image's bytes (a re-uploaded deck gets new image
    paths but the same images)."""
    parts = []
    for ref in ku.source_refs:
        slide = corpus.slide_by_ref(ref.deck_name, ref.slide_number)
        if slide is None:
            parts.append(f"[{ref.deck_name} {ref.slide_number}] missing")
            continue
        image = Path(slide.image_path) if slide.image_path else None
        image_hash = hashlib.sha256(image.read_bytes()).hexdigest() if image and image.exists() else ""
        parts.append(f"[{ref.deck_name} {ref.slide_number}]\n{slide.text}\n{slide.notes}\n{image_hash}")
    return "\n\n".join(parts)


def video_key(
    corpus: CourseCorpus,
    ku: KnowledgeUnit,
    level: int,
    prereq_titles: list[str],
    version: str = PIPELINE_VERSION,
) -> str:
    payload = json.dumps(
        {
            "slides": cited_slide_content(corpus, ku),
            "ku": ku.model_dump(mode="json"),
            "prerequisites": prereq_titles,
            "level": level,
            "version": version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class VideoJob(BaseModel):
    key: str
    ku_id: str
    level: int = Field(ge=1, le=3)
    # Where the generator finds the course: a directory with corpus.json and kus.json.
    course_dir: str
    state: JobState = "queued"
    # Lower is made sooner: the video's position in the student's playlist.
    priority: int = 0
    attempts: int = 0
    error: str | None = None
    video_path: str | None = None
    requested_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


# Makes the video for a job inside `work_dir` and returns the final video's
# path; raises if it can't.
Generator = Callable[[VideoJob, Path], Path]


class VideoStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "jobs").mkdir(parents=True, exist_ok=True)
        (self.root / "videos").mkdir(parents=True, exist_ok=True)
        self._lock_path = self.root / ".lock"
        self._lock_path.touch()

    # -- storage -------------------------------------------------------------

    @contextmanager
    def _locked(self) -> Iterator[None]:
        # A fresh open per acquisition: flock then excludes other threads of
        # this process as well as other processes.
        with open(self._lock_path) as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _job_path(self, key: str) -> Path:
        return self.root / "jobs" / f"{key}.json"

    def work_dir(self, key: str) -> Path:
        return self.root / "videos" / key

    def _load(self, key: str) -> VideoJob | None:
        path = self._job_path(key)
        return VideoJob.model_validate_json(path.read_text()) if path.exists() else None

    def _save(self, job: VideoJob) -> VideoJob:
        job.updated_at = time.time()
        path = self._job_path(job.key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(job.model_dump_json(indent=2))
        tmp.replace(path)  # atomic: a reader never sees half a file
        return job

    def _all(self) -> list[VideoJob]:
        return [VideoJob.model_validate_json(p.read_text()) for p in (self.root / "jobs").glob("*.json")]

    # -- the app's side --------------------------------------------------------

    def request(self, key: str, *, ku_id: str, level: int, course_dir: str | Path, priority: int = 0) -> VideoJob:
        """The video for `key`: ready from the cache, or queued (moved up the
        queue when asked for sooner than before). A failed video is queued
        again until it has been tried MAX_ATTEMPTS times."""
        with self._locked():
            job = self._load(key)
            if job is None:
                return self._save(VideoJob(
                    key=key, ku_id=ku_id, level=level, course_dir=str(course_dir), priority=priority,
                ))
            if job.state == "ready":
                if job.video_path and Path(job.video_path).exists():
                    return job
                job.state, job.video_path, job.attempts = "queued", None, 0  # the file was deleted: make it again
            elif job.state == "failed":
                if job.attempts >= MAX_ATTEMPTS:
                    return job
                job.state = "queued"
            if job.state == "queued":
                job.priority = min(job.priority, priority)
            return self._save(job)

    def status(self, key: str) -> VideoJob | None:
        with self._locked():
            return self._load(key)

    def jobs(self) -> list[VideoJob]:
        with self._locked():
            return sorted(self._all(), key=lambda j: (j.priority, j.requested_at))

    # -- the worker's side -----------------------------------------------------

    def claim_next(self) -> VideoJob | None:
        """Marks the most urgent queued job as being made and returns it."""
        with self._locked():
            queued = [j for j in self._all() if j.state == "queued"]
            if not queued:
                return None
            job = min(queued, key=lambda j: (j.priority, j.requested_at))
            job.state = "making"
            job.attempts += 1
            job.error = None
            return self._save(job)

    def finish(self, key: str, video_path: Path) -> VideoJob:
        with self._locked():
            job = self._load(key)
            assert job is not None, key
            job.state, job.video_path, job.error = "ready", str(video_path), None
            return self._save(job)

    def fail(self, key: str, error: str) -> VideoJob:
        with self._locked():
            job = self._load(key)
            assert job is not None, key
            job.state, job.error = "failed", error[-2000:]
            return self._save(job)

    def recover(self) -> int:
        """Puts jobs left "making" by a worker that died back in the queue.
        Call once when the (single) worker process starts, before any thread
        claims a job; returns how many were put back."""
        with self._locked():
            stuck = [j for j in self._all() if j.state == "making"]
            for job in stuck:
                job.state = "queued"
                job.attempts = max(job.attempts - 1, 0)  # the interrupted try doesn't count
                self._save(job)
            return len(stuck)

    def run_one(self, generate: Generator) -> VideoJob | None:
        """Claims the most urgent job and makes it. Returns the finished (ready
        or failed) job, or None when the queue is empty."""
        job = self.claim_next()
        if job is None:
            return None
        work_dir = self.work_dir(job.key)
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            video = generate(job, work_dir)
        except (Exception, SystemExit) as e:  # SystemExit: the pipeline's own "can't continue" (e.g. no LaTeX)
            return self.fail(job.key, f"{type(e).__name__}: {e}")
        if not Path(video).exists():
            return self.fail(job.key, f"generator returned {video}, which does not exist")
        return self.finish(job.key, Path(video))

    def run_worker(
        self,
        generate: Generator,
        *,
        workers: int = 1,
        until_idle: bool = True,
        poll_seconds: float = 2.0,
        stop: threading.Event | None = None,
    ) -> list[VideoJob]:
        """Makes queued videos, `workers` at a time, most urgent first. With
        `until_idle`, returns once the queue is empty; otherwise polls for new
        requests until `stop` is set. Returns the jobs it finished."""
        stop = stop or threading.Event()
        done: list[VideoJob] = []
        done_lock = threading.Lock()

        def loop() -> None:
            while not stop.is_set():
                job = self.run_one(generate)
                if job is not None:
                    with done_lock:
                        done.append(job)
                elif until_idle:
                    return
                else:
                    stop.wait(poll_seconds)

        self.recover()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in [pool.submit(loop) for _ in range(workers)]:
                future.result()
        return done
