"""On-demand video jobs: the cache key, the queue, and the worker (plan/per-student-video-plan.md step 3).
The generator is stubbed: no LLM calls, no renders."""

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from syllabyte_common.models import CourseCorpus, KnowledgeUnit, KUList, Slide, SlideDeck, SlideRef
from syllabyte_common.video_jobs import MAX_ATTEMPTS, VideoJob, VideoStore, video_key

ROOT = Path(__file__).resolve().parent.parent


def course(tmp_path: Path, *, text="Slide text", notes="", image_bytes=b"png", image_name="s1.png"):
    image = tmp_path / image_name
    image.write_bytes(image_bytes)
    corpus = CourseCorpus(
        course_name="c", syllabus_path="s", syllabus_text="t",
        decks=[SlideDeck(name="d", source_path="p", slides=[
            Slide(deck_name="d", slide_number=1, text=text, notes=notes, image_path=str(image)),
        ])],
    )
    ku = KnowledgeUnit(
        id="ku-a", title="A", summary="S", bloom_level="apply", cognitive_load="medium", prerequisites=[],
        source_refs=[SlideRef(deck_name="d", slide_number=1)], visual_idea="v", short_worthiness=3,
        short_worthiness_reason="r",
    )
    return corpus, ku


class TestVideoKey:
    def test_the_same_inputs_give_the_same_key(self, tmp_path):
        corpus, ku = course(tmp_path)
        assert video_key(corpus, ku, 2, []) == video_key(corpus, ku, 2, [])

    def test_the_key_changes_with_everything_the_video_is_made_from(self, tmp_path):
        (tmp_path / "base").mkdir()
        corpus, ku = course(tmp_path / "base")
        base = video_key(corpus, ku, 2, ["P"])
        assert video_key(corpus, ku, 3, ["P"]) != base  # level
        assert video_key(corpus, ku, 2, ["Q"]) != base  # prerequisites
        assert video_key(corpus, ku, 2, ["P"], version="later") != base  # pipeline version
        assert video_key(corpus, ku.model_copy(update={"summary": "T"}), 2, ["P"]) != base  # the KU
        for name, kw in {"text": {"text": "Other"}, "notes": {"notes": "n"}, "image": {"image_bytes": b"other"}}.items():
            (tmp_path / name).mkdir()
            other, _ = course(tmp_path / name, **kw)
            assert video_key(other, ku, 2, ["P"]) != base, name

    def test_a_reuploaded_deck_with_the_same_images_keeps_the_key(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        first, ku = course(tmp_path / "a", image_name="one.png")
        again, _ = course(tmp_path / "b", image_name="two.png")
        assert video_key(first, ku, 1, []) == video_key(again, ku, 1, [])


def req(store: VideoStore, key: str, priority: int = 0, level: int = 2) -> VideoJob:
    return store.request(key, ku_id=f"ku-{key}", level=level, course_dir="/course", priority=priority)


class FakeGenerator:
    def __init__(self, fail: set[str] = frozenset()):
        self.fail = set(fail)
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def __call__(self, job: VideoJob, work_dir: Path) -> Path:
        with self.lock:
            self.calls.append(job.key)
        if job.key in self.fail:
            raise RuntimeError(f"could not make {job.key}")
        video = work_dir / "final.mp4"
        video.write_bytes(b"mp4")
        return video


@pytest.fixture
def store(tmp_path):
    return VideoStore(tmp_path / "store")


class TestRequest:
    def test_a_new_request_is_queued(self, store):
        job = req(store, "a", priority=3)
        assert (job.state, job.priority, job.attempts) == ("queued", 3, 0)
        assert store.status("a") == job

    def test_asking_sooner_moves_a_queued_video_up_and_asking_later_does_not(self, store):
        req(store, "a", priority=5)
        assert req(store, "a", priority=1).priority == 1
        assert req(store, "a", priority=9).priority == 1

    def test_a_ready_video_comes_from_the_cache_without_being_made_again(self, store):
        gen = FakeGenerator()
        req(store, "a")
        store.run_worker(gen)
        job = req(store, "a")
        assert job.state == "ready" and Path(job.video_path).read_bytes() == b"mp4"
        store.run_worker(gen)
        assert gen.calls == ["a"]

    def test_a_ready_video_whose_file_is_gone_is_made_again(self, store):
        gen = FakeGenerator()
        req(store, "a")
        store.run_worker(gen)
        Path(store.status("a").video_path).unlink()
        assert req(store, "a").state == "queued"
        store.run_worker(gen)
        assert gen.calls == ["a", "a"] and store.status("a").state == "ready"

    def test_a_failed_video_is_retried_on_request_until_max_attempts(self, store):
        gen = FakeGenerator(fail={"a"})
        req(store, "a")
        for _ in range(MAX_ATTEMPTS):
            store.run_worker(gen)
            req(store, "a")
        job = store.status("a")
        assert job.state == "failed" and job.attempts == MAX_ATTEMPTS and "could not make a" in job.error
        store.run_worker(gen)
        assert len(gen.calls) == MAX_ATTEMPTS


class TestWorker:
    def test_the_most_urgent_job_is_made_first_and_ties_go_oldest_first(self, store):
        for key, priority in [("late", 2), ("first", 0), ("second", 1), ("tie", 2)]:
            req(store, key, priority)
        gen = FakeGenerator()
        store.run_worker(gen, workers=1)
        assert gen.calls == ["first", "second", "late", "tie"]

    def test_success_and_failure_are_recorded(self, store):
        req(store, "ok"), req(store, "bad")
        done = {j.key: j for j in store.run_worker(FakeGenerator(fail={"bad"}))}
        assert done["ok"].state == "ready" and done["ok"].video_path.endswith("ok/final.mp4")
        assert done["bad"].state == "failed" and done["bad"].error == "RuntimeError: could not make bad"

    def test_a_pipeline_exit_fails_the_job_instead_of_killing_the_worker(self, store):
        def exits(job, work_dir):
            raise SystemExit("LaTeX is missing")

        req(store, "a"), req(store, "b")
        done = store.run_worker(exits)
        assert {j.key for j in done} == {"a", "b"} and all("LaTeX is missing" in j.error for j in done)

    def test_a_generator_that_returns_no_file_fails_the_job(self, store, tmp_path):
        req(store, "a")
        [job] = store.run_worker(lambda job, work_dir: tmp_path / "nowhere.mp4")
        assert job.state == "failed" and "does not exist" in job.error

    def test_parallel_workers_make_every_video_exactly_once(self, store):
        for i in range(12):
            req(store, f"k{i}", priority=i)
        gen = FakeGenerator()
        done = store.run_worker(gen, workers=4)
        assert sorted(gen.calls) == sorted(f"k{i}" for i in range(12))
        assert len(done) == 12 and all(j.state == "ready" for j in done)

    def test_jobs_left_making_by_a_dead_worker_go_back_in_the_queue(self, store):
        req(store, "a")
        store.claim_next()  # the worker died here
        assert store.status("a").state == "making"
        assert store.recover() == 1
        job = store.status("a")
        assert job.state == "queued" and job.attempts == 0

    def test_keep_polling_picks_up_a_request_made_while_it_waits(self, store):
        gen, stop = FakeGenerator(), threading.Event()

        def stop_once_made(job, work_dir):
            video = gen(job, work_dir)
            stop.set()
            return video

        worker = threading.Thread(target=store.run_worker, args=(stop_once_made,), kwargs={"until_idle": False, "poll_seconds": 0.05, "stop": stop})
        worker.start()
        req(store, "late-arrival")
        worker.join(timeout=10)
        assert not worker.is_alive() and gen.calls == ["late-arrival"]


def test_the_cli_requests_and_lists_videos(tmp_path):
    (tmp_path / "course").mkdir()
    corpus, ku = course(tmp_path / "course")
    (tmp_path / "course" / "corpus.json").write_text(corpus.model_dump_json())
    (tmp_path / "course" / "kus.json").write_text(KUList(knowledge_units=[ku]).model_dump_json())
    cli = [sys.executable, str(ROOT / "scripts" / "video_jobs.py"), "--store", str(tmp_path / "store")]
    out = subprocess.run([*cli, "request", "--course", str(tmp_path / "course"), "--want", "ku-a:3"], capture_output=True, text=True, check=True).stdout
    assert out.startswith("queued  L3 p0") and "ku-a" in out
    assert subprocess.run([*cli, "status"], capture_output=True, text=True, check=True).stdout == out
    bad = subprocess.run([*cli, "request", "--course", str(tmp_path / "course"), "--want", "ku-a:4"], capture_output=True, text=True)
    assert bad.returncode != 0 and "level 1, 2 or 3" in bad.stderr
