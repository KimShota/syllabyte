"""Level-aware scripts: a shared base, one example segment per level, and checks before any critic call. No LLM calls."""

import hashlib

import pytest
from script_generation_agent import leveled
from script_generation_agent.leveled import (
    BaseScript,
    compose,
    validate_base,
    validate_example,
    write_base_script,
    write_base_with_critique,
    write_example,
    write_leveled_script,
)
from script_generation_agent.prompts import (
    BASE_SYSTEM_PROMPT,
    BASE_WORDS,
    CRITIQUE_BASE_SYSTEM_PROMPT,
    CRITIQUE_EXAMPLE_SYSTEM_PROMPT,
    CRITIQUE_SYSTEM_PROMPT,
    EXAMPLE_WORDS,
    LEVEL_EXAMPLE_BRIEF,
    SCRIPT_SYSTEM_PROMPT,
    build_example_prompt,
    example_system_prompt,
)
from script_generation_agent.script_writer import ScriptValidationError, validate_script
from syllabyte_common.models import (
    Beat,
    CourseCorpus,
    CritiqueScore,
    KnowledgeUnit,
    Segment,
    Slide,
    SlideDeck,
    SlideRef,
)

REF = [SlideRef(deck_name="slides", slide_number=1)]


def words(n: int, tag: str = "w") -> str:
    return " ".join(f"{tag}{i}" for i in range(n))


def seg(phase: str, n_words: int, beats: int = 2, tag: str = "w") -> Segment:
    per = max(1, n_words // beats)
    bs = [Beat(narration=words(per if i < beats - 1 else n_words - per * (beats - 1), f"{tag}{i}_"), visual="A box moves") for i in range(beats)]
    return Segment(phase=phase, beats=bs, source_refs=REF)


def base_script(n: int = 125) -> BaseScript:
    # the end segment must stand on its own, so the four shared segments carry no example
    each = [n // 4, n // 4, n // 4, n - 3 * (n // 4)]
    return BaseScript(ku_id="ku-x", title="T", segments=[seg(p, w, tag=p) for p, w in zip(["prepare", "initiate", "deliver", "end"], each)])


def example(level: int, n: int | None = None) -> Segment:
    lo, hi = EXAMPLE_WORDS[level]
    return seg("deliver", n if n is not None else (lo + hi) // 2, beats=4, tag=f"ex{level}")


KU = KnowledgeUnit(
    id="ku-x", title="The thing", summary="S", bloom_level="apply", cognitive_load="medium", prerequisites=["ku-p"],
    source_refs=REF, visual_idea="v", short_worthiness=3, short_worthiness_reason="r",
)
CORPUS = CourseCorpus(
    course_name="c", syllabus_path="s", syllabus_text="t",
    decks=[SlideDeck(name="slides", source_path="p", slides=[Slide(deck_name="slides", slide_number=1, text="Slide text")])],
)


class TestPrompts:
    def test_the_original_script_prompt_is_unchanged_by_splitting_it_into_pieces(self):
        assert hashlib.sha256(SCRIPT_SYSTEM_PROMPT.encode()).hexdigest() == "0ad8980b5f76cb7e5cb62e446486908ba3c027c4a0073e608827e7b59692d5ff"

    def test_the_base_prompt_writes_four_segments_and_a_recap_that_stands_alone(self):
        assert "exactly 4 segments" in BASE_SYSTEM_PROMPT
        assert "differs from viewer to viewer" in BASE_SYSTEM_PROMPT
        assert "do not refer to any example" in BASE_SYSTEM_PROMPT
        assert f"{BASE_WORDS[0]}-{BASE_WORDS[1]} words" in BASE_SYSTEM_PROMPT

    @pytest.mark.parametrize("level", [1, 2, 3])
    def test_each_level_has_its_own_budget_and_the_shared_beat_and_visual_rules(self, level):
        p = example_system_prompt(level)
        lo, hi = EXAMPLE_WORDS[level]
        assert f"{lo}-{hi} words" in p
        assert "Visuals must EXPLAIN" in p and "Beats —" in p

    @pytest.mark.parametrize("level", [1, 2, 3])
    def test_the_example_writer_is_told_to_continue_the_screen_and_not_narrate_the_animation(self, level):
        p = example_system_prompt(level)
        assert "continue from the screen as it ended" in p
        assert "never re-create, re-introduce or re-grow" in p
        assert "Never narrate the animation" in p
        assert "Stay with what the slides state" in p

    def test_the_levels_ask_for_different_things(self):
        u1 = build_example_prompt(KU, "{}", "M", 1, ["Earlier idea"])
        u2 = build_example_prompt(KU, "{}", "M", 2, ["Earlier idea"])
        u3 = build_example_prompt(KU, "{}", "M", 3, ["Earlier idea"])
        assert "recaps, in plain words" in u1 and "“Earlier idea”" in u1 and "FULL, step-by-step" in u1
        assert "ONE worked example" in u2 and "Do not recap" in u2 and "“Earlier idea”" not in u2
        assert "'what if' question" in u3 and "Do not work an example" in u3
        assert len({LEVEL_EXAMPLE_BRIEF[1], LEVEL_EXAMPLE_BRIEF[2], LEVEL_EXAMPLE_BRIEF[3], LEVEL_EXAMPLE_BRIEF["1_no_prerequisite"]}) == 4

    def test_a_level_one_ku_with_no_prerequisite_gets_no_recap(self):
        # recapping would only repeat the core idea the viewer heard one segment earlier
        p = build_example_prompt(KU, "{}", "M", 1, [])
        assert "builds on nothing earlier, so do not recap" in p and "recaps, in plain words" not in p
        assert "FULL, step-by-step" in p

    def test_levels_two_and_three_do_not_depend_on_prerequisites(self):
        for level in (2, 3):
            assert build_example_prompt(KU, "{}", "M", level, []) == build_example_prompt(KU, "{}", "M", level, ["X"])

    def test_budgets_keep_every_composed_script_in_the_150_220_word_window(self):
        for level, (lo, hi) in EXAMPLE_WORDS.items():
            assert 150 <= BASE_WORDS[0] + lo and BASE_WORDS[1] + hi <= 220, level


class TestComposition:
    def test_puts_the_example_between_the_core_idea_and_the_recap(self):
        script = compose(base_script(), example(2))
        assert [s.phase for s in script.segments] == ["prepare", "initiate", "deliver", "deliver", "end"]
        assert script.segments[3].beats[0].narration.startswith("ex20_")

    def test_the_shared_segments_are_identical_across_levels(self):
        base = base_script()
        scripts = [compose(base, example(level)) for level in (1, 2, 3)]
        shared = lambda s: [s.segments[i].model_dump_json() for i in (0, 1, 2, 4)]  # noqa: E731
        assert shared(scripts[0]) == shared(scripts[1]) == shared(scripts[2])
        assert len({s.segments[3].model_dump_json() for s in scripts}) == 3

    @pytest.mark.parametrize("level", [1, 2, 3])
    def test_a_composed_script_passes_the_existing_checks(self, level):
        assert validate_script(compose(base_script(), example(level))) == []


class TestChecks:
    def test_a_good_base_passes(self):
        assert validate_base(base_script()) == []

    def test_a_base_with_the_wrong_phases_or_length_is_rejected(self):
        bad = base_script()
        bad.segments[2] = seg("prepare", 31)
        assert any("phase order" in p for p in validate_base(bad))
        assert any("base word_count" in p for p in validate_base(base_script(60)))
        assert any("base word_count" in p for p in validate_base(base_script(220)))

    def test_a_beat_without_a_visual_or_a_segment_without_sources_is_rejected(self):
        b = base_script()
        b.segments[0].beats[0].visual = " "
        b.segments[1].source_refs = []
        problems = validate_base(b)
        assert any("no visual" in p for p in problems) and any("no source_refs" in p for p in problems)

    @pytest.mark.parametrize("level", [1, 2, 3])
    def test_an_example_must_stay_in_its_levels_budget(self, level):
        assert validate_example(example(level), level) == []
        assert any("words" in p for p in validate_example(example(level, 20), level))
        assert any("words" in p for p in validate_example(example(level, 150), level))

    def test_an_example_has_three_to_five_beats_and_the_deliver_phase(self):
        assert any("beats" in p for p in validate_example(seg("deliver", 55, beats=2), 2))
        assert any("beats" in p for p in validate_example(seg("deliver", 55, beats=6), 2))
        assert any("phase" in p for p in validate_example(seg("end", 55, beats=4), 2))

    def test_the_level_budgets_get_shorter_from_level_one_to_three(self):
        assert EXAMPLE_WORDS[1][1] > EXAMPLE_WORDS[2][1] > EXAMPLE_WORDS[3][1]


class FakeLLM:
    """Stands in for `structured`: hands back queued objects per stage and records what it was asked."""

    def __init__(self, **by_stage):
        self.by_stage = {k: list(v) for k, v in by_stage.items()}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, *, schema, content, system, stage, **_):
        self.calls.append((stage, content[0]["text"]))
        return self.by_stage[stage].pop(0)


@pytest.fixture
def fake(monkeypatch):
    def install(**by_stage):
        f = FakeLLM(**by_stage)
        monkeypatch.setattr(leveled, "structured", f)
        return f

    return install


class TestWriting:
    def test_writes_a_valid_base_in_one_call(self, fake):
        f = fake(write_base_script=[base_script()])
        assert write_base_script(KU, CORPUS).word_count == base_script().word_count
        assert [c[0] for c in f.calls] == ["write_base_script"]

    def test_a_rejected_base_is_retried_once_with_the_reason_fed_back(self, fake):
        f = fake(write_base_script=[base_script(60), base_script()])
        write_base_script(KU, CORPUS)
        assert len(f.calls) == 2
        assert "rejected" in f.calls[1][1] and "base word_count=60" in f.calls[1][1]

    def test_two_rejections_raise_with_the_problems(self, fake):
        fake(write_base_script=[base_script(60), base_script(60)])
        with pytest.raises(ScriptValidationError, match="base word_count"):
            write_base_script(KU, CORPUS)

    def test_an_example_is_written_against_the_base_and_the_levels_brief(self, fake):
        f = fake(write_example_l1=[example(1)])
        write_example(KU, base_script(), 1, CORPUS, prereq_titles=["Earlier idea"])
        text = f.calls[0][1]
        assert '"phase": "prepare"' in text and "“Earlier idea”" in text and "FULL, step-by-step" in text

    def test_a_missing_slide_in_the_corpus_is_reported_clearly(self):
        ku = KU.model_copy(update={"source_refs": [SlideRef(deck_name="slides", slide_number=99)]})
        with pytest.raises(ScriptValidationError, match="don't resolve"):
            write_base_script(ku, CORPUS)


GOOD = CritiqueScore(pedagogical_coherence=9, conceptual_accuracy=9, learner_appropriateness=9, visual_alignment=9)
BAD = CritiqueScore(pedagogical_coherence=9, conceptual_accuracy=4, learner_appropriateness=9, visual_alignment=9, issues=["the example uses a number that is not on the slide"])


class TestLeveledScript:
    def test_the_base_is_written_once_and_reused_for_every_level(self, fake, monkeypatch):
        f = fake(write_base_script=[base_script()], write_example_l1=[example(1)], write_example_l2=[example(2)], write_example_l3=[example(3)])
        monkeypatch.setattr(leveled, "critique", lambda *a, **k: GOOD)
        base = None
        scripts = []
        for level in (1, 2, 3):
            script, base, result = write_leveled_script(KU, CORPUS, level, base=base)
            assert result.passed
            scripts.append(script)
        assert [c[0] for c in f.calls].count("write_base_script") == 1
        assert [c[0] for c in f.calls] == ["write_base_script", "write_example_l1", "write_example_l2", "write_example_l3"]
        assert len({s.segments[3].model_dump_json() for s in scripts}) == 3
        assert len({s.segments[0].model_dump_json() for s in scripts}) == 1

    def test_a_low_score_rewrites_only_the_example_and_feeds_the_critics_issues_back(self, fake, monkeypatch):
        f = fake(write_example_l2=[example(2), example(2, 58)])
        scores = iter([BAD, GOOD])
        monkeypatch.setattr(leveled, "critique", lambda *a, **k: next(scores))
        script, _, result = write_leveled_script(KU, CORPUS, 2, base=base_script())
        assert result.passed and len(result.rounds) == 2
        assert [c[0] for c in f.calls] == ["write_example_l2", "write_example_l2"]
        assert "the example uses a number that is not on the slide" in f.calls[1][1]
        assert script.segments[3].beats[0].narration.startswith("ex20_")

    def test_after_the_last_round_it_returns_the_script_unpassed_rather_than_failing_the_video(self, fake, monkeypatch):
        fake(write_example_l3=[example(3), example(3)])
        monkeypatch.setattr(leveled, "critique", lambda *a, **k: BAD)
        script, _, result = write_leveled_script(KU, CORPUS, 3, base=base_script())
        assert not result.passed and len(result.rounds) == 2 and script is not None

    def test_skipping_the_critic_makes_no_critic_call(self, fake, monkeypatch):
        fake(write_example_l1=[example(1)])
        monkeypatch.setattr(leveled, "critique", lambda *a, **k: pytest.fail("the critic should not run"))
        _, _, result = write_leveled_script(KU, CORPUS, 1, base=base_script(), skip_critic=True)
        assert result.passed

    def test_a_composed_script_outside_the_word_window_is_an_error(self, fake):
        fake(write_example_l3=[example(3)])  # 100 + 47 = 147 words, under the 150 minimum
        with pytest.raises(ScriptValidationError, match="word_count"):
            write_leveled_script(KU, CORPUS, 3, base=base_script(100), skip_critic=True)


class TestBaseCritique:
    def test_the_base_is_critiqued_once_and_rewritten_with_the_issues_fed_back(self, fake, monkeypatch):
        f = fake(write_base_script=[base_script(), base_script(118)])
        scores = iter([BAD, GOOD])
        calls = []
        monkeypatch.setattr(leveled, "critique", lambda *a, **k: (calls.append(k["stage"]), next(scores))[1])
        base, result = write_base_with_critique(KU, CORPUS)
        assert result.passed and len(result.rounds) == 2 and calls == ["critique_base", "critique_base"]
        assert "the example uses a number that is not on the slide" in f.calls[1][1]
        assert base.word_count == base_script(118).word_count

    def test_levels_built_on_an_accepted_base_never_critique_or_rewrite_it(self, fake, monkeypatch):
        f = fake(write_example_l1=[example(1)], write_example_l2=[example(2)])
        seen = []
        monkeypatch.setattr(leveled, "critique", lambda *a, **k: (seen.append((k["stage"], k["system"])), GOOD)[1])
        base = base_script()
        for level in (1, 2):
            write_leveled_script(KU, CORPUS, level, base=base)
        assert [c[0] for c in f.calls] == ["write_example_l1", "write_example_l2"]  # no base writes
        assert [s[0] for s in seen] == ["critique_example_l1", "critique_example_l2"]
        assert all(s[1] == CRITIQUE_EXAMPLE_SYSTEM_PROMPT for s in seen)

    def test_without_a_base_one_is_written_and_critiqued_first(self, fake, monkeypatch):
        f = fake(write_base_script=[base_script()], write_example_l2=[example(2)])
        stages = []
        monkeypatch.setattr(leveled, "critique", lambda *a, **k: (stages.append(k["stage"]), GOOD)[1])
        write_leveled_script(KU, CORPUS, 2)
        assert stages == ["critique_base", "critique_example_l2"]
        assert [c[0] for c in f.calls] == ["write_base_script", "write_example_l2"]

    def test_the_scoped_critic_prompts_keep_the_original_rubric_and_add_their_scope(self):
        for p in (CRITIQUE_BASE_SYSTEM_PROMPT, CRITIQUE_EXAMPLE_SYSTEM_PROMPT):
            assert p.startswith(CRITIQUE_SYSTEM_PROMPT)
        assert "do not penalize the missing example" in CRITIQUE_BASE_SYSTEM_PROMPT
        assert "ONLY for the worked-example segment" in CRITIQUE_EXAMPLE_SYSTEM_PROMPT

    def test_skipping_the_critic_writes_the_base_and_never_asks_for_a_score(self, fake, monkeypatch):
        fake(write_base_script=[base_script()])
        monkeypatch.setattr(leveled, "critique", lambda *a, **k: pytest.fail("the critic should not run"))
        base, result = write_base_with_critique(KU, CORPUS, skip_critic=True)
        assert result.passed and base.word_count == base_script().word_count
