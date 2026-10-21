"""The upload worker's loop against a fake server (httpx.MockTransport). No network, no LLM calls."""

import json
from pathlib import Path

import httpx
import pymupdf
from ingestion_agent import uploads
from ingestion_agent.uploads import SyllabusSchedule
from ingestion_agent.worker import Worker

SYLLABUS = "\n".join(["Course syllabus for causal inference in the social sciences."] * 2 + ["Week %d: topic number %d" % (i, i) for i in range(1, 12)])


def pdf_bytes(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 700), text, fontsize=11)
    return doc.tobytes()


class FakeServer:
    def __init__(self, jobs: list[dict], files: dict[str, bytes], known_keys: set[str] = frozenset()):
        self.jobs = list(jobs)
        self.files = files
        self.known_keys = known_keys
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.url.path, body))
        assert request.headers["Authorization"] == "Bearer t"
        path = request.url.path
        if path == "/api/worker/claim":
            return httpx.Response(200, json={"job": self.jobs.pop(0) if self.jobs else None})
        if path.endswith("/file"):
            return httpx.Response(200, content=self.files[path.split("/")[-2]])
        if path.endswith("/syllabus-key"):
            return httpx.Response(200, json={"is_new": body["key"] not in self.known_keys})
        return httpx.Response(200, json={"ok": True})

    def posted(self, suffix: str) -> list[dict]:
        return [b for p, b in self.calls if p.endswith(suffix)]


def worker(server: FakeServer, tmp_path: Path) -> Worker:
    client = httpx.Client(base_url="http://server", transport=httpx.MockTransport(server), headers={"Authorization": "Bearer t"})
    return Worker(client, tmp_path / "work")


def test_reads_a_deck_and_posts_its_key(tmp_path):
    server = FakeServer([{"id": "j1", "kind": "deck_read", "payload": {"deck_name": "up-1"}, "file_name": "lecture1.pdf"}], {"j1": pdf_bytes(["Alpha intro", "Beta"])})
    w = worker(server, tmp_path)
    assert w.run_once() is True
    [result] = server.posted("/j1/result")
    assert result["result"]["page_count"] == 2 and result["result"]["first_title"] == "Alpha intro"
    assert len(result["result"]["content_key"]) == 64
    assert w.run_once() is False
    assert not (tmp_path / "work" / "j1").exists()  # the file is not kept


def test_a_known_syllabus_joins_without_reading_the_lecture_list(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(uploads, "structured", lambda **kw: calls.append(1))
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), SYLLABUS, fontsize=10)
    key = uploads.syllabus_key(uploads.read_syllabus(_save(tmp_path, "s.pdf", doc.tobytes())).text)
    server = FakeServer([{"id": "j2", "kind": "syllabus", "payload": {}, "file_name": "s.pdf"}], {"j2": doc.tobytes()}, known_keys={key})
    worker(server, tmp_path).run_once()
    assert server.posted("/syllabus-key") == [{"key": key}]
    assert server.posted("/j2/result") == [] and calls == []


def test_a_new_syllabus_posts_its_lecture_list(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "structured", lambda **kw: SyllabusSchedule(course_code="CS", course_name="Causal", lectures=[]))
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), SYLLABUS, fontsize=10)
    server = FakeServer([{"id": "j3", "kind": "syllabus", "payload": {}, "file_name": "s.pdf"}], {"j3": doc.tobytes()})
    worker(server, tmp_path).run_once()
    [result] = server.posted("/j3/result")
    assert result["result"]["schedule"]["course_name"] == "Causal"


def test_a_file_problem_is_reported_for_the_student_and_other_errors_for_a_retry(tmp_path):
    server = FakeServer(
        [
            {"id": "j4", "kind": "deck_read", "payload": {"deck_name": "up-2"}, "file_name": "deck.key"},
            {"id": "j5", "kind": "deck_read", "payload": {"deck_name": "up-3"}, "file_name": "broken.pdf"},
        ],
        {"j4": b"x", "j5": b"not a pdf"},
    )
    w = worker(server, tmp_path)
    w.run_once()
    w.run_once()
    [keynote] = server.posted("/j4/fail")
    assert "Export To > PDF" in keynote["user_message"]
    [broken] = server.posted("/j5/fail")
    assert broken["user_message"] == "This slide file could not be opened."


def _save(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_runs_jobs_side_by_side_with_concurrency(tmp_path, monkeypatch):
    import threading
    import time

    from ingestion_agent import worker as worker_mod

    running, most = [0], [0]
    lock = threading.Lock()

    def slow_read(path, work, name, **kw):
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.2)
        with lock:
            running[0] -= 1
        return {"deck_name": name}

    monkeypatch.setattr(worker_mod, "run_deck_read_job", slow_read)
    jobs = [{"id": f"j{i}", "kind": "deck_read", "payload": {"deck_name": f"d{i}"}, "file_name": "x.pdf"} for i in range(3)]
    server = FakeServer(jobs, {f"j{i}": b"%PDF" for i in range(3)})
    started = time.monotonic()
    worker(server, tmp_path).serve(concurrency=3, once=True)
    assert most[0] == 3 and time.monotonic() - started < 0.5
    assert sorted(b["result"]["deck_name"] for b in server.posted("/result")) == ["d0", "d1", "d2"]


def test_two_questions_on_one_deck_render_it_once(tmp_path, monkeypatch):
    import threading

    from ingestion_agent import worker as worker_mod

    renders = []

    def fake_read(path, work_dir, name):
        renders.append(name)
        return None, f"deck {name}"

    monkeypatch.setattr(worker_mod, "read_deck", fake_read)
    w = worker(FakeServer([], {}), tmp_path)
    threads = [threading.Thread(target=lambda: w._deck("d1", tmp_path / "d1.pdf")) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert renders == ["d1"]
