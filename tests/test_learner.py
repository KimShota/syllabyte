"""The learner-facing models: the KU graph is a DAG, and items carry the IRT fields."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from syllabyte_common.learner import Course, CourseConfig, Item, KuEntry, Lecture, Topic

REPO = Path(__file__).resolve().parent.parent


def ku(id_: str, prerequisites: list[str] | None = None, bloom: str = "understand") -> KuEntry:
    return KuEntry(
        id=id_, title=id_, short_title=id_, topic_id="t", lecture_n=1,
        bloom_level=bloom, prerequisites=prerequisites or [],
    )


def course(*kus: KuEntry) -> Course:
    return Course(
        id="c", code="X", name="Course", eyebrow="COURSE", syllabus_summary="", config=CourseConfig(),
        topics=[Topic(id="t", title="T", blurb="", ku_ids=[k.id for k in kus], first_lecture=1)],
        lectures=[Lecture(n=1, title="L1", week=1, slide_start=1, slide_end=10)],
        kus=list(kus),
    )


def item(**extra) -> Item:
    return Item(
        id="i", topic_id="t", context="onboarding", stem="?", options=["a", "b", "c"], correct_index=1,
        allows_not_sure=True, explanation="because", **extra,
    )


class TestKuGraph:
    def test_accepts_a_dag(self):
        c = course(ku("a"), ku("b", ["a"]), ku("c", ["a", "b"]))
        assert [k.id for k in c.kus] == ["a", "b", "c"]

    def test_rejects_an_unknown_prerequisite(self):
        with pytest.raises(ValidationError, match="unknown prerequisite ghost"):
            course(ku("a", ["ghost"]))

    def test_rejects_a_self_prerequisite(self):
        with pytest.raises(ValidationError, match="itself"):
            course(ku("a", ["a"]))

    def test_rejects_a_cycle(self):
        with pytest.raises(ValidationError, match="cycle"):
            course(ku("a", ["c"]), ku("b", ["a"]), ku("c", ["b"]))

    def test_requires_a_bloom_level(self):
        with pytest.raises(ValidationError):
            KuEntry(id="a", title="a", short_title="a", topic_id="t", lecture_n=1)


class TestItemIrtFields:
    def test_defaults_to_alpha_one_and_no_tier(self):
        i = item()
        assert i.discrimination == 1.0
        assert i.tier is None

    @pytest.mark.parametrize("tier", ["basic", "applied", "advanced"])
    def test_accepts_the_three_tiers(self, tier):
        assert item(tier=tier).tier == tier

    def test_rejects_an_unknown_tier(self):
        with pytest.raises(ValidationError):
            item(tier="expert")

    @pytest.mark.parametrize("alpha", [0, -1.0])
    def test_rejects_non_positive_discrimination(self, alpha):
        with pytest.raises(ValidationError):
            item(discrimination=alpha)


def test_generated_fixtures_validate():
    """The fixtures are local-only (course material); skip on a fresh clone."""
    path = REPO / "apps/web/fixtures/course.json"
    if not path.exists():
        pytest.skip("no generated fixtures")
    c = Course.model_validate_json(path.read_text())
    assert all(k.bloom_level for k in c.kus)
