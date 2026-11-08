"""The worker's video job (plan/participant-ready-plan.md S2): the pipeline is a stand-in and the model calls are faked,
but the manifest is the real build_ui_manifest on a real (tiny) mp4. No network, no LLM calls."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from assessment_agent.video_app_data import ClaimGen, VideoGen
from ingestion_agent import video_job
from ingestion_agent.worker import Worker
from syllabyte_common.learner import MCQ
from syllabyte_common.models import Slide, SlideDeck

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed to make the tiny mp4")

# What apps/server/src/uploads.ts videoResult stores and the phone's `Video` (packages/core/src/types.ts) needs, minus urls.
VIDEO_KEYS = {
    "id", "ku_id", "title", "short_title", "topic_id", "lecture_n", "file_level", "duration_s", "segments", "checkpoint",
    "next_session_item_id", "prove_it_item_id", "sentence_frame", "claims", "tailoring", "transcript", "captions_burned_in",
    "source_slides", "prerequisite_titles", "review_status",
}
GOLDEN = Path(__file__).parent.parent / "apps" / "server" / "tests" / "fixtures" / "video-result.json"

KU = {
    "id": "ku-bst-insert", "title": "Inserting into a binary search tree", "summary": "Compare down from the root.", "bloom_level": "apply",
    "cognitive_load": "medium", "prerequisites": ["ku-bst"], "source_refs": [{"deck_name": "deck-1", "slide_number": 1}, {"deck_name": "deck-1", "slide_number": 2}],
    "visual_idea": "a tree", "short_worthiness": 4, "short_worthiness_reason": "core", "short_title": "BST insert", "difficulty": 0.0,
}
PAYLOAD = {
    "deck_id": "deck-1", "ku": KU, "level": 2, "lecture_n": 3, "topic_id": "lecture-3", "short_title": "BST insert", "course_name": "Data structures",
    "syllabus_text": "Syllabus", "prereqs": [{"id": "ku-bst", "title": "Binary search trees", "short_title": "BSTs"}],
}
DECK = SlideDeck(name="deck-1", source_path="x.pdf", slides=[Slide(deck_name="deck-1", slide_number=n, text=f"slide {n}") for n in (1, 2, 3)])
PHASES = ["prepare", "initiate", "deliver", "deliver", "end"]


def fake_pipeline(calls: list):
    """Writes what make_ku_video leaves in a KU's folder: final.mp4, script.json and the audio files build_ui_manifest reads."""

    def make_video(ku, corpus, ku_dir, **kw):
        calls.append({"ku": ku.id, "deck": [d.name for d in corpus.decks], **{k: v for k, v in kw.items() if k != "manifest"}})
        (ku_dir / "audio").mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=2:d=60", "-pix_fmt", "yuv420p", str(ku_dir / "final.mp4")], check=True)
        segments = [
            {"phase": p, "source_refs": [{"deck_name": "deck-1", "slide_number": 1 + i % 2}], "drawn": "templates",
             "beats": [{"narration": f"Line {i}a.", "visual": "v", "speaker": "explainer"}, {"narration": f"Line {i}b.", "visual": "v", "speaker": "peer"}]}
            for i, p in enumerate(PHASES)
        ]
        (ku_dir / "script.json").write_text(json.dumps({"ku_id": ku.id, "title": ku.title, "segments": segments, "style": "dialogue", "visuals": "templates"}))
        audio = [{"segment_index": i, "srt_start": 10.0 * i, "srt_end": 10.0 * (i + 1), "beat_durations": [5.0, 5.0]} for i in range(len(PHASES))]
        (ku_dir / "audio" / "segment_audio.json").write_text(json.dumps({"items": audio}))
        (ku_dir / "audio" / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:04,000\nLine 0a.\n")
        return ku_dir / "final.mp4"

    return make_video


def mcq(stem: str, correct: int) -> MCQ:
    return MCQ(stem=stem, options=["a", "b", "c"], correct_index=correct, explanation="because", hint="think", difficulty_prior=0.2)


def fake_gen(claim_segments=(2, 3, 4)):
    gen = VideoGen(
        checkpoint=mcq("Where does it go?", 0), next_session=mcq("A day later?", 0), prove_it=mcq("Prove it?", 0),
        sentence_frame_template="Compare ___ then go ___.", sentence_frame_answers=["down", "left or right"],
        claims=[ClaimGen(segment_idx=i, text=f"Claim for segment {i}.") for i in claim_segments],
    )
    return lambda *a, **kw: (gen, [{"id": "cp-ku-bst-insert", "issue": "hint is close to the answer"}])


@pytest.fixture
def job(monkeypatch, tmp_path):
    monkeypatch.setattr(video_job, "generate_video_gen", fake_gen())
    monkeypatch.setattr("animation_agent.ui_manifest.ffprobe_duration", lambda path: 60.0)  # pinned: ffprobe's rounding differs by version

    def run(payload=PAYLOAD, **kw):
        sent, calls = {}, []
        make = kw.pop("make_video", fake_pipeline(calls))
        result = video_job.run_video_job(payload, DECK, tmp_path / "work", lambda name, f: sent.update({name: f.read_bytes()}), make_video=make, log=lambda m: None, **kw)
        return result, sent, calls

    return run


def test_the_job_runs_the_pipeline_on_the_kus_slides_at_its_level(job):
    _, _, calls = job()
    assert calls == [{"ku": "ku-bst-insert", "deck": ["deck-1"], "level": 2, "prereq_titles": ["Binary search trees"], "style": "dialogue", "visuals": "templates"}]


def test_it_sends_the_three_files_the_server_keeps(job):
    _, sent, _ = job()
    assert set(sent) == {"video.mp4", "poster.jpg", "captions.vtt"}
    assert all(sent.values())
    assert sent["captions.vtt"].startswith(b"WEBVTT")


def test_the_video_has_everything_the_phone_needs_but_urls(job):
    result, _, _ = job()
    v = result["video"]
    assert set(v) == VIDEO_KEYS
    assert (v["id"], v["ku_id"], v["file_level"], v["lecture_n"], v["topic_id"]) == ("ku-bst-insert", "ku-bst-insert", 2, 3, "lecture-3")
    assert v["checkpoint"] == {"t": 40.0, "rewatch_from": 30.0, "item_id": "cp-ku-bst-insert"}  # right after the last deliver segment
    assert [s["phase"] for s in v["segments"]] == PHASES and v["duration_s"] == 60.0
    assert [(c["segment_idx"], c["slide_refs"][0]["deck_name"]) for c in v["claims"]] == [(2, "deck-1"), (3, "deck-1"), (4, "deck-1")]
    assert set(v["tailoring"]) == {"1", "2", "3"}
    assert "BSTs" in v["tailoring"]["2"][0]["what"]  # the first prerequisite's short title
    assert v["prerequisite_titles"] == ["BSTs"] and v["captions_burned_in"] is True and v["source_slides"] == [1, 2]
    assert {r["speaker"] for r in v["transcript"]} == {"Peter", "Stewie"} and len(v["transcript"]) == 10
    assert v["sentence_frame"]["template"].count("___") == 2


def test_it_returns_the_three_items_the_video_asks_with_their_keys_spread(job):
    result, _, _ = job()
    items = {i["id"]: i for i in result["items"]}
    assert set(items) == {"cp-ku-bst-insert", "ns-ku-bst-insert", "pi-ku-bst-insert"}
    assert {i["context"] for i in items.values()} == {"checkpoint", "next_session", "prove_it"}
    assert items["pi-ku-bst-insert"]["allows_not_sure"] and not items["cp-ku-bst-insert"]["allows_not_sure"]
    assert sorted(i["correct_index"] for i in items.values()) == [0, 1, 2]  # not always option A
    assert all(i["options"][i["correct_index"]] == "a" for i in items.values())  # swapped with the key, never lost
    assert all(r["deck_name"] == "deck-1" for i in items.values() for r in i["source_refs"])
    assert result["video"]["checkpoint"]["item_id"] in items and result["flags"] == [{"id": "cp-ku-bst-insert", "issue": "hint is close to the answer"}]


def test_a_video_whose_pipeline_fell_back_to_captions_is_a_failure_not_a_result(job):
    with pytest.raises(RuntimeError, match="caption template"):
        job(make_video=lambda *a, **kw: None)


def test_a_job_with_claims_for_the_wrong_segments_fails_here_not_on_the_server(job, monkeypatch):
    def refuse(*a, **kw):
        raise ValueError("ku-bst-insert: claims for segments [2], expected [2, 3, 4]")

    monkeypatch.setattr(video_job, "generate_video_gen", refuse)
    with pytest.raises(ValueError, match="claims for segments"):
        job()


def test_the_result_is_the_one_the_server_tests_post(job):
    """apps/server/tests/fixtures/video-result.json is this result: the server's tests feed it through the real routes,
    so the two sides can't drift apart. Run with UPDATE_GOLDEN=1 to rewrite it after changing the result on purpose."""
    result, _, _ = job()
    result.pop("cost_usd")
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_GOLDEN") or not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(text)
    assert GOLDEN.read_text() == text, "the video result changed: re-run with UPDATE_GOLDEN=1 and check apps/server/tests/videos.test.ts"


class FakeVideoServer:
    """claim -> the deck file -> the three files (PUT) -> the result, in order."""

    def __init__(self):
        self.events: list[tuple[str, str]] = []
        self.sent: dict[str, int] = {}
        self.claimed = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/worker/claim":
            job = None if self.claimed else {"id": "j9", "kind": "video", "payload": PAYLOAD, "file_name": "slides.pdf"}
            self.claimed = True
            return httpx.Response(200, json={"job": job})
        if path.endswith("/file"):
            return httpx.Response(200, content=b"%PDF")
        if request.method == "PUT":
            name = path.rsplit("/", 1)[1]
            self.events.append(("put", name))
            self.sent[name] = len(request.content)
            return httpx.Response(200, json={"ok": True})
        self.events.append(("post", path.rsplit("/", 1)[1]))
        return httpx.Response(200, json={"ok": True})


def test_the_worker_sends_the_files_before_the_result(tmp_path, monkeypatch, job):
    monkeypatch.setattr(Worker, "_deck", lambda self, deck_id, path: DECK)
    from ingestion_agent import worker as worker_mod

    server = FakeVideoServer()
    real = worker_mod.run_video_job
    monkeypatch.setattr(worker_mod, "run_video_job", lambda *a, **kw: real(*a, make_video=fake_pipeline([]), **kw))
    w = Worker(httpx.Client(base_url="http://server", transport=httpx.MockTransport(server)), tmp_path / "work")
    assert w.run_once() is True
    assert server.events == [("put", "video.mp4"), ("put", "poster.jpg"), ("put", "captions.vtt"), ("post", "result")]
    assert all(n > 0 for n in server.sent.values())
    assert not (tmp_path / "work" / "j9").exists()  # nothing is kept after the job
