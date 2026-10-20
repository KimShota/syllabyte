"""
The upload worker (plan/slide-uploads-plan.md): claims jobs from the server, runs them (ingestion_agent/upload_jobs.py)
and posts the results. Until the worker has a host of its own it runs on a laptop:

    SYLLABYTE_WORKER_TOKEN=... uv run python -m ingestion_agent.worker --server https://api.syllabyte.app

A job whose file is the problem (a scan, a damaged file, Keynote) fails with a message the student sees and is not
retried; any other error is reported and the server queues the job once more.
"""

from __future__ import annotations

import argparse
import os
import shutil
import time
import traceback
from pathlib import Path

import httpx
from syllabyte_common.llm import DEFAULT_MODEL, PRICE_PER_MTOK
from syllabyte_common.models import RunManifest

from ingestion_agent.upload_jobs import run_deck_job, run_deck_read_job, run_link_pass_job, run_syllabus_job
from ingestion_agent.uploads import UploadError


def log(msg: str) -> None:
    print(f"[worker] {msg}", flush=True)


class Worker:
    def __init__(self, client: httpx.Client, work_dir: str | Path, *, model: str = DEFAULT_MODEL, critic_model: str | None = None):
        self.client = client
        self.work_dir = Path(work_dir)
        self.model = model
        self.critic_model = critic_model
        self.spent_usd = 0.0

    def _post(self, path: str, body: dict) -> dict:
        r = self.client.post(path, json=body)
        r.raise_for_status()
        return r.json()

    def run_once(self) -> bool:
        """Claims and runs one job; False when there was nothing to do."""
        job = self._post("/api/worker/claim", {})["job"]
        if not job:
            return False
        job_id, kind, payload = job["id"], job["kind"], job["payload"]
        log(f"{kind} {job_id}")
        work = self.work_dir / job_id
        work.mkdir(parents=True, exist_ok=True)
        try:
            path = None
            if job.get("file_name"):
                r = self.client.get(f"/api/worker/jobs/{job_id}/file")
                r.raise_for_status()
                path = work / Path(job["file_name"]).name
                path.write_bytes(r.content)
            manifest = RunManifest(run_id=f"{kind}-{job_id}")
            result = self._run(job_id, kind, payload, path, work, manifest)
            if result is not None:
                self._post(f"/api/worker/jobs/{job_id}/result", {"result": result})
            cost = manifest.total_cost_usd(PRICE_PER_MTOK)
            self.spent_usd += cost
            log(f"{kind} {job_id}: done ({len(manifest.llm_calls)} LLM calls, ${cost:.3f}; ${self.spent_usd:.2f} this session)")
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
            return run_deck_read_job(path, work, payload["deck_name"])
        if kind == "deck":
            return run_deck_job(payload, path, work, model=self.model, critic_model=self.critic_model, manifest=manifest, log=log)
        if kind == "link_pass":
            return run_link_pass_job(payload, model=self.model, manifest=manifest)
        raise ValueError(f"unknown job kind {kind}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default=os.environ.get("SYLLABYTE_SERVER", "http://localhost:8788"))
    parser.add_argument("--token", default=os.environ.get("SYLLABYTE_WORKER_TOKEN"), help="the server's SYLLABYTE_WORKER_TOKEN")
    parser.add_argument("--work-dir", default="runs/uploads", help="where files are read (emptied after each job)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--critic-model", default=None)
    parser.add_argument("--poll", type=float, default=5.0, help="seconds between checks when there is nothing to do")
    parser.add_argument("--once", action="store_true", help="run the queued jobs, then stop")
    args = parser.parse_args()
    if not args.token:
        parser.error("set --token or SYLLABYTE_WORKER_TOKEN")

    with httpx.Client(base_url=args.server, headers={"Authorization": f"Bearer {args.token}"}, timeout=120) as client:
        worker = Worker(client, args.work_dir, model=args.model, critic_model=args.critic_model)
        log(f"polling {args.server}")
        while True:
            try:
                did = worker.run_once()
            except httpx.HTTPError as e:
                log(f"server unreachable: {e!r}")
                did = False
            if not did:
                if args.once:
                    return
                time.sleep(args.poll)


if __name__ == "__main__":
    main()
