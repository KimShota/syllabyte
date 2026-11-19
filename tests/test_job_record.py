"""The worker's record of each video job (ingestion_agent/job_record.py): lines, steps, calls, costs, errors, files."""

import json
import runpy
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from ingestion_agent import job_record
from ingestion_agent import worker as worker_mod
from syllabyte_common.llm import call_cost_usd
from syllabyte_common.models import LLMCallRecord

from test_worker import FakeServer, worker


def test_a_job_keeps_its_own_lines_and_those_of_the_threads_it_starts(tmp_path):
    rec = job_record.JobRecorder(tmp_path, "video", "job-a", {"ku": {"id": "ku-a"}, "level": 2})
    other = threading.Thread(target=lambda: print("someone else's line", flush=True))
    with rec:
        print("[generate_shorts] [3/6] script: writing", flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda i: print(f"segment {i}: tier=spec_template attempts=1 (3.0s)", flush=True), range(2)))
        other.start()
        other.join()
    print("after the job", flush=True)
    lines = [line for _, _, line in rec.lines]
    assert "[generate_shorts] [3/6] script: writing" in lines
    assert sorted(line for line in lines if line.startswith("segment")) == [
        "segment 0: tier=spec_template attempts=1 (3.0s)", "segment 1: tier=spec_template attempts=1 (3.0s)"]
    assert "someone else's line" not in lines and "after the job" not in lines


def test_cache_reads_on_sonnet_5_5_cost_a_twentieth_of_input():
    call = LLMCallRecord(stage="s", model="claude-sonnet-5-5", input_tokens=1_000_000, output_tokens=0, cache_read_tokens=1_000_000)
    assert call_cost_usd(call) == pytest.approx(2.0 + 0.10)


def fake_video_job(payload, deck, work, upload, *, manifest, **kw):
    """What a video job prints and leaves behind, without the pipeline: steps, a redraw, segments, calls and files."""
    ku_dir = work / f"{payload['ku']['id']}-L{payload['level']}"
    (ku_dir / "ui").mkdir(parents=True)
    print("[storyboard] ku-a: program 1: 40 lines; snapshots no snapshots", file=sys.stderr, flush=True)
    print("[storyboard] ku-a: the program is written again: the program failed: PictureError: label 'top' is longer than 2 characters", file=sys.stderr, flush=True)
    print("[storyboard] ku-a: program 2: 41 lines; snapshots prepare 2, initiate 1, deliver_1 4, deliver_2 4, end 1", file=sys.stderr, flush=True)
    print("[generate_shorts] [3/6] script: writing + critiquing script for ku-a", flush=True)
    for stage, (i, o) in {"storyboard_program_l2": (5000, 1500), "storyboard_write_l2": (4000, 900)}.items():
        manifest.llm_calls.append(LLMCallRecord(stage=stage, model="claude-sonnet-5-5", input_tokens=i, output_tokens=o, cache_read_tokens=8000, wall_seconds=12.5))
    print("[generate_shorts] [4/6] tts: speaking", flush=True)
    print("[generate_shorts] [5/6] animate: rendering 5 segment(s), quality=low", flush=True)
    print("[generate_shorts]     segment 0: tier=spec_template attempts=1 (3.0s)", flush=True)
    print("[generate_shorts] [6/6] assemble: syncing + concatenating", flush=True)
    (ku_dir / "script.json").write_text(json.dumps({"title": "Stacks", "segments": [{"phase": "prepare", "beats": [{"narration": "One two three."}]}]}))
    (ku_dir / "assembly_diagnostics.json").write_text("{}")
    (ku_dir / "final.mp4").write_bytes(b"not a real video")
    print(f"[generate_shorts]     -> {ku_dir / 'final.mp4'} (max drift 0.04s)", flush=True)
    upload("video.mp4", ku_dir / "final.mp4")
    return {"video": {"ku_id": "ku-a"}, "items": [], "flags": []}


PAYLOAD = {"deck_id": "d1", "ku": {"id": "ku-a"}, "level": 2, "lecture_n": 1, "course_name": "Algorithms"}


def test_a_video_job_leaves_a_record_of_its_steps_calls_costs_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(worker_mod, "read_deck", lambda path, work_dir, name: (None, "deck"))
    monkeypatch.setattr(worker_mod, "run_video_job", fake_video_job)
    server = FakeServer([{"id": "job-123456789", "kind": "video", "payload": PAYLOAD, "file_name": "x.pdf"}], {"job-123456789": b"%PDF"})
    w = worker(server, tmp_path)
    # the files go up as bytes, which the shared fake server doesn't read; the record still times the real _put_file
    monkeypatch.setattr(w.client, "put", lambda url, content: httpx.Response(200, request=httpx.Request("PUT", url)))
    assert w.run_once() is True

    records = tmp_path / "work" / "records"
    [folder] = [p for p in records.iterdir() if p.is_dir()]
    assert folder.name.endswith("_video_ku-a_L2_job-1234")
    r = json.loads((folder / "record.json").read_text())
    assert r["status"] == "done" and r["llm_calls"] == 2 and r["errors"] == []
    assert [s["step"] for s in r["steps"]] == ["3/6 script", "4/6 tts", "5/6 animate", "6/6 assemble"]
    assert [p["phase"] for p in r["phases"]] == ["download the slides", "render the deck", "run the job", "send the result"]
    expected = sum(call_cost_usd(LLMCallRecord(stage="s", model="claude-sonnet-5-5", input_tokens=i, output_tokens=o, cache_read_tokens=8000))
                   for i, o in [(5000, 1500), (4000, 900)])
    assert r["cost_usd"] == pytest.approx(expected, abs=1e-5)
    assert [s["stage"] for s in r["cost_by_stage"]] == ["storyboard_program_l2", "storyboard_write_l2"]
    assert len(r["programs"]["attempts"]) == 2 and "longer than 2 characters" in r["programs"]["redraws"][0]["why"]
    assert r["segments"] == [{"segment": 0, "tier": "spec_template", "attempts": 1, "seconds": 3.0}]
    assert r["uploads"][0]["file"] == "video.mp4" and r["uploads"][0]["bytes"] == len(b"not a real video")
    assert r["video"]["title"] == "Stacks" and r["video"]["words"] == 3
    assert "ku-a-L2/script.json" in r["artifacts"] and not any(a.endswith(".mp4") for a in r["artifacts"])
    assert (folder / "artifacts" / "ku-a-L2" / "script.json").exists()
    log = (folder / "log.txt").read_text()
    assert "program 2: 41 lines" in log and "[worker] video job-123456789" in log
    [line] = (records / "index.jsonl").read_text().splitlines()
    assert json.loads(line)["redraws"] == 1 and json.loads(line)["status"] == "done"
    assert not (tmp_path / "work" / "job-123456789").exists()  # the work folder still goes

    # the summary prints it
    monkeypatch.setattr(sys, "argv", ["video_records.py", str(records)])
    runpy.run_path("scripts/video_records.py", run_name="__main__")
    monkeypatch.setattr(sys, "argv", ["video_records.py", str(folder)])
    runpy.run_path("scripts/video_records.py", run_name="__main__")


def test_a_failed_video_job_is_recorded_with_its_traceback(tmp_path, monkeypatch):
    def broken(payload, deck, work, upload, *, manifest, **kw):
        manifest.llm_calls.append(LLMCallRecord(stage="storyboard_program_l2", model="claude-sonnet-5-5", input_tokens=100, output_tokens=10))
        raise RuntimeError("a segment fell back to the caption template")

    monkeypatch.setattr(worker_mod, "read_deck", lambda path, work_dir, name: (None, "deck"))
    monkeypatch.setattr(worker_mod, "run_video_job", broken)
    server = FakeServer([{"id": "job-bad", "kind": "video", "payload": PAYLOAD, "file_name": "x.pdf"}], {"job-bad": b"%PDF"})
    assert worker(server, tmp_path).run_once() is True
    [folder] = [p for p in (tmp_path / "work" / "records").iterdir() if p.is_dir()]
    r = json.loads((folder / "record.json").read_text())
    assert r["status"] == "failed" and r["llm_calls"] == 1 and r["cost_usd"] > 0
    assert "caption template" in r["errors"][0]["error"] and "Traceback" in r["errors"][0]["traceback"]
    assert server.posted("/job-bad/fail")  # the server is still told


def test_other_jobs_keep_no_record(tmp_path, monkeypatch):
    server = FakeServer([{"id": "j1", "kind": "placement", "payload": {"course_name": "c", "topics": [], "lectures": [], "new": []}, "file_name": None}], {})
    w = worker(server, tmp_path)
    w._run = lambda *a, **kw: {}
    assert w.run_once() is True
    assert not (tmp_path / "work" / "records").exists()
