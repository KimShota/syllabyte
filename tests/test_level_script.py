"""Scripts written for one student's level on one KU (plan/per-student-video-plan.md V1). No LLM calls."""

import hashlib

import pytest

from script_generation_agent import critic, script_writer
from script_generation_agent.critic import write_script_with_critique
from script_generation_agent.prompts import (
    CRITIQUE_SYSTEM_PROMPT,
    SCRIPT_SYSTEM_PROMPT,
    critique_system_prompt,
    level_system_prompt,
)
from script_generation_agent.script_writer import ScriptValidationError, write_script
from syllabyte_common.models import (
    Beat,
    CourseCorpus,
    CritiqueScore,
    KnowledgeUnit,
    Script,
    Segment,
    Slide,
    SlideDeck,
    SlideRef,
)

REF = [SlideRef(deck_name="slides", slide_number=1)]
KU = KnowledgeUnit(
    id="ku-x", title="The thing", summary="S", bloom_level="apply", cognitive_load="medium", prerequisites=["ku-p"],
    source_refs=REF, visual_idea="v", short_worthiness=3, short_worthiness_reason="r",
)
CORPUS = CourseCorpus(
    course_name="c", syllabus_path="s", syllabus_text="t",
    decks=[SlideDeck(name="slides", source_path="p", slides=[Slide(deck_name="slides", slide_number=1, text="Slide text")])],
)


def script(total_words: int = 180, tag: str = "w") -> Script:
    phases = ["prepare", "initiate", "deliver", "deliver", "end"]
    per = total_words // 5
    segs = []
    for k, ph in enumerate(phases):
        n = per if k < 4 else total_words - 4 * per
        half = n // 2
        segs.append(Segment(phase=ph, source_refs=REF, beats=[
            Beat(narration=" ".join(f"{tag}{k}a{i}" for i in range(half)), visual="A box moves"),
            Beat(narration=" ".join(f"{tag}{k}b{i}" for i in range(n - half)), visual="A dot slides"),
        ]))
    return Script(ku_id="ku-x", title="T", segments=segs)


class TestPrompts:
    def test_the_original_prompts_are_unchanged(self):
        assert hashlib.sha256(SCRIPT_SYSTEM_PROMPT.encode()).hexdigest() == "0ad8980b5f76cb7e5cb62e446486908ba3c027c4a0073e608827e7b59692d5ff"
        assert hashlib.sha256(CRITIQUE_SYSTEM_PROMPT.encode()).hexdigest() == "3ccb18d1691f65f7936949b5b4b684d85ecbd29ae6764def0209067d0b349ea8"

    @pytest.mark.parametrize("level", [1, 2, 3])
    def test_a_level_prompt_is_the_whole_script_prompt_with_the_level_written_in(self, level):
        p = level_system_prompt(level)
        assert "exactly 5 segments" in p and "150-220 words" in p  # the same 5-segment video
        assert "Visuals must EXPLAIN" in p and "Beats —" in p
        assert "The viewer's level" in p and f"Level {level}" in p
        assert "Never narrate the animation" in p and "Stay with what the slides state" in p

    def test_the_level_shapes_language_objective_and_the_second_deliver_segment(self):
        l1, l2, l3 = (level_system_prompt(n, ["Earlier idea"]) for n in (1, 2, 3))
        assert "plain, everyday words" in l1 and "simple analogy" in l1 and "Remember/Understand" in l1 and "FULL, step-by-step worked example" in l1
        assert "short gloss" in l2 and "Apply/Analyze" in l2 and "ONE worked example" in l2
        assert "comparatively" in l3 and "Evaluate/Create" in l3 and '"what if" question' in l3 and "do not walk through a worked example" in l3

    def test_only_level_one_recaps_the_prerequisite_and_only_when_there_is_one(self):
        assert "builds on “Earlier idea”: recap it" in level_system_prompt(1, ["Earlier idea"])
        assert "builds on nothing earlier in the course, so do not add a recap" in level_system_prompt(1, [])
        assert level_system_prompt(2, ["Earlier idea"]) == level_system_prompt(2, [])
        assert "Do not recap" in level_system_prompt(2) and "Do not recap" in level_system_prompt(3)

    @pytest.mark.parametrize("level", [1, 2, 3])
    def test_the_critic_judges_appropriateness_against_the_level(self, level):
        p = critique_system_prompt(level)
        assert p.startswith(CRITIQUE_SYSTEM_PROMPT) and f"Level {level}" in p
        assert "Judge learner_appropriateness against that level" in p
        assert ("missing worked example" in p) and ("'what if' question" in critique_system_prompt(3))


class FakeLLM:
    def __init__(self, *objs):
        self.queue = list(objs)
        self.calls: list[dict] = []

    def __call__(self, **kw):
        self.calls.append(kw)
        return self.queue.pop(0)


@pytest.fixture
def llm(monkeypatch):
    def install(*objs, where=script_writer):
        f = FakeLLM(*objs)
        monkeypatch.setattr(where, "structured", f)
        return f

    return install


class TestWriteScript:
    def test_without_a_level_nothing_changes(self, llm):
        f = llm(script())
        write_script(KU, CORPUS)
        assert f.calls[0]["system"] == SCRIPT_SYSTEM_PROMPT and f.calls[0]["stage"] == "write_script"

    def test_without_a_level_a_rejected_script_still_fails_at_once(self, llm):
        f = llm(script(100))
        with pytest.raises(ScriptValidationError, match="word_count"):
            write_script(KU, CORPUS)
        assert len(f.calls) == 1

    @pytest.mark.parametrize("level", [1, 2, 3])
    def test_with_a_level_the_level_prompt_and_stage_are_used(self, llm, level):
        f = llm(script())
        write_script(KU, CORPUS, level=level, prereq_titles=["Earlier idea"])
        assert f.calls[0]["system"] == level_system_prompt(level, ["Earlier idea"])
        assert f.calls[0]["stage"] == f"write_script_l{level}"

    def test_with_a_level_a_rejected_script_is_rewritten_once_with_the_reasons(self, llm):
        f = llm(script(100), script(180))
        out = write_script(KU, CORPUS, level=2)
        assert out.word_count == 180 and len(f.calls) == 2
        assert "rejected by the automatic checker" in f.calls[1]["content"][0]["text"]
        assert "word_count=100" in f.calls[1]["content"][0]["text"]

    def test_with_a_level_two_rejections_raise(self, llm):
        llm(script(100), script(300))
        with pytest.raises(ScriptValidationError, match="word_count=300"):
            write_script(KU, CORPUS, level=3)


GOOD = CritiqueScore(pedagogical_coherence=9, conceptual_accuracy=9, learner_appropriateness=9, visual_alignment=9)
BAD = CritiqueScore(pedagogical_coherence=9, conceptual_accuracy=9, learner_appropriateness=4, visual_alignment=9, issues=["uses 'counterfactual' without defining it"])


class TestWithCritique:
    def test_the_critic_is_told_the_level(self, llm):
        llm(script())
        c = llm(GOOD, where=critic)
        _, result = write_script_with_critique(KU, CORPUS, level=1)
        assert result.passed
        assert c.calls[0]["system"] == critique_system_prompt(1) and c.calls[0]["stage"] == "critique_l1"

    def test_a_low_score_rewrites_the_script_with_the_issues(self, llm):
        w = llm(script(), script(181))
        llm(BAD, GOOD, where=critic)
        out, result = write_script_with_critique(KU, CORPUS, level=1)
        assert result.passed and len(result.rounds) == 2 and out.word_count == 181
        assert "uses 'counterfactual' without defining it" in w.calls[1]["content"][0]["text"]

    def test_without_a_level_the_critic_is_the_original(self, llm):
        llm(script())
        c = llm(GOOD, where=critic)
        write_script_with_critique(KU, CORPUS)
        assert c.calls[0]["system"] == CRITIQUE_SYSTEM_PROMPT and c.calls[0]["stage"] == "critique"

    def test_skipping_the_critic_makes_no_critic_call(self, llm):
        llm(script())
        llm(where=critic)  # an empty queue: any call would fail
        _, result = write_script_with_critique(KU, CORPUS, level=2, skip_critic=True)
        assert result.passed
