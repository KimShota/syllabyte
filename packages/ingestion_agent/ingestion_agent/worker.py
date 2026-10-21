"""
The upload worker (plan/slide-uploads-plan.md): claims jobs from the server, runs them (ingestion_agent/upload_jobs.py)
and posts the results. Until the worker has a host of its own it runs on a laptop:

    SYLLABYTE_WORKER_TOKEN=... uv run python -m ingestion_agent.worker --server https://api.syllabyte.app

A job whose file is the problem (a scan, a damaged file, Keynote) fails with a message the student sees and is not
retried; any other error is reported and the server queues the job once more.

Question jobs (a student's check is waiting for them, plan/slide-uploads-plan.md V4) come before anything else the
server has queued. A long deck job still holds a lone worker, so a second worker that only writes questions keeps
checks moving:

    uv run python -m ingestion_agent.worker --kinds question

`--concurrency N` runs N jobs at once in one worker (threads; the work is waiting on the model). Deck jobs still go one
after another: the server hands out a deck only once every earlier lecture's deck is done, so each sees their KUs.
Reading files, placing them and writing questions run side by side.
"""

from __future__ import annotations

import argparse
import os
import shutil
import threading
import time
import traceback
from pathlib import Path

import httpx
from syllabyte_common.llm import DEFAULT_MODEL, PRICE_PER_MTOK
from syllabyte_common.models import RunManifest

from ingestion_agent.upload_jobs import (
    run_deck_job, run_deck_read_job, run_link_pass_job, run_placement_job, run_question_job, run_syllabus_job,
)
from ingestion_agent.uploads import UploadError, read_deck
from syllabyte_common.models import SlideDeck

KINDS = ("syllabus", "deck_read", "placement", "deck", "question", "link_pass")


def log(msg: str) -> None:
    print(f"[worker] {msg}", flush=True)


class Worker:
    def __init__(
        self, client: httpx.Client, work_dir: str | Path, *, model: str = DEFAULT_MODEL, critic_model: str | None = None,
        kinds: list[str] | None = None,
    ):
        self.client = client
        self.work_dir = Path(work_dir)
        self.model = model
        self.critic_model = critic_model
        self.kinds = kinds
        self.spent_usd = 0.0
        # decks rendered for question jobs, kept between jobs so a check's next question does not render it again
        self.decks: dict[str, SlideDeck] = {}
        self._lock = threading.Lock()
        self._deck_locks: dict[str, threading.Lock] = {}

    def _post(self, path: str, body: dict) -> dict:
        r = self.client.post(path, json=body)
        r.raise_for_status()
        return r.json()

    def run_once(self) -> bool:
        """Claims and runs one job; False when there was nothing to do."""
        job = self._post("/api/worker/claim", {"kinds": self.kinds} if self.kinds else {})["job"]
        if not job:
            return False
        job_id, kind, payload = job["id"], job["kind"], job["payload"]
        log(f"{kind} {job_id}")
        work = self.work_dir / job_id
        work.mkdir(parents=True, exist_ok=True)
        try:
            path = None
            if job.get("file_name") and not (kind == "question" and payload["deck_id"] in self.decks):
                r = self.client.get(f"/api/worker/jobs/{job_id}/file")
                r.raise_for_status()
                path = work / Path(job["file_name"]).name
                path.write_bytes(r.content)
            manifest = RunManifest(run_id=f"{kind}-{job_id}")
            result = self._run(job_id, kind, payload, path, work, manifest)
            if result is not None:
                self._post(f"/api/worker/jobs/{job_id}/result", {"result": result})
            cost = manifest.total_cost_usd(PRICE_PER_MTOK)
            with self._lock:
                self.spent_usd += cost
                total = self.spent_usd
            log(f"{kind} {job_id}: done ({len(manifest.llm_calls)} LLM calls, ${cost:.3f}; ${total:.2f} this session)")
        except UploadError as e:
            log(f"{kind} {job_id}: the file can't be used: {e}")
            self._post(f"/api/worker/jobs/{job_id}/fail", {"error": str(e), "user_message": str(e)})
        except Exception as e:  # reported; the server retries once
            log(f"{kind} {job_id}: failed: {e!r}")
            self._post(f"/api/worker/jobs/{job_id}/fail", {"error": "".join(traceback.format_exception(e))[-2000:]})
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return True

    def _run(self, job_id: str, kind: str, payload: dict, path: Path | None, work: Path, manifest: RunManifest) -> dict | None:
        if kind == "syllabus":
            joined = []

            def is_new(key: str) -> bool:
                new = self._post(f"/api/worker/jobs/{job_id}/syllabus-key", {"key": key})["is_new"]
                joined.append(not new)
                return new

            out = run_syllabus_job(path, is_new=is_new, model=self.model, manifest=manifest)
            # a known course is joined when its key arrives; there is nothing more to send
            return None if joined and joined[0] else out
        if kind == "deck_read":
            return run_deck_read_job(path, work, payload["deck_name"], payload=payload, manifest=manifest)
        if kind == "placement":
            return run_placement_job(payload, manifest=manifest)
        if kind == "question":
            return run_question_job(payload, self._deck(payload["deck_id"], path), model=self.model, critic_model=self.critic_model, manifest=manifest, log=log)
        if kind == "deck":
            return run_deck_job(payload, path, work, model=self.model, critic_model=self.critic_model, manifest=manifest, log=log)
        if kind == "link_pass":
            return run_link_pass_job(payload, model=self.model, manifest=manifest)
        raise ValueError(f"unknown job kind {kind}")


    def _deck(self, deck_id: str, path: Path | None) -> SlideDeck:
        with self._lock:
            lock = self._deck_locks.setdefault(deck_id, threading.Lock())
        # two questions on one deck at once: the second waits for the first to render it
        with lock:
            if deck_id not in self.decks:
                if path is None:
                    raise RuntimeError("a question job's deck was not sent")
                _, deck = read_deck(path, self.work_dir / "decks" / deck_id, deck_id)
                self.decks[deck_id] = deck
            return self.decks[deck_id]

    def serve(self, *, concurrency: int = 1, poll: float = 5.0, once: bool = False) -> None:
        """Runs jobs on `concurrency` threads until stopped; with `once`, until a thread finds the queue empty and every
        other thread has finished its job (a job can queue the next, e.g. placement after the last read)."""

        def loop() -> None:
            while True:
                try:
                    did = self.run_once()
                except httpx.HTTPError as e:
                    log(f"server unreachable: {e!r}")
                    did = False
                if not did:
                    if once:
                        return
                    time.sleep(poll)

        threads = [threading.Thread(target=loop, name=f"worker-{i}", daemon=True) for i in range(concurrency)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default=os.environ.get("SYLLABYTE_SERVER", "http://localhost:8788"))
    parser.add_argument("--token", default=os.environ.get("SYLLABYTE_WORKER_TOKEN"), help="the server's SYLLABYTE_WORKER_TOKEN")
    parser.add_argument("--work-dir", default="runs/uploads", help="where files are read (emptied after each job)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--critic-model", default=None)
    parser.add_argument("--poll", type=float, default=5.0, help="seconds between checks when there is nothing to do")
    parser.add_argument("--once", action="store_true", help="run the queued jobs, then stop")
    parser.add_argument("--kinds", default=None, help=f"only these job kinds, comma-separated ({', '.join(KINDS)})")
    parser.add_argument("--concurrency", type=int, default=1, help="jobs at once (deck jobs still run in lecture order)")
    args = parser.parse_args()
    if not args.token:
        parser.error("set --token or SYLLABYTE_WORKER_TOKEN")

    with httpx.Client(base_url=args.server, headers={"Authorization": f"Bearer {args.token}"}, timeout=120) as client:
        kinds = [k.strip() for k in args.kinds.split(",")] if args.kinds else None
        if kinds and set(kinds) - set(KINDS):
            parser.error(f"unknown kinds: {', '.join(sorted(set(kinds) - set(KINDS)))}")
        worker = Worker(client, args.work_dir, model=args.model, critic_model=args.critic_model, kinds=kinds)
        log(f"polling {args.server}" + (f" with {args.concurrency} jobs at once" if args.concurrency > 1 else ""))
        worker.serve(concurrency=max(1, args.concurrency), poll=args.poll, once=args.once)


if __name__ == "__main__":
    main()
