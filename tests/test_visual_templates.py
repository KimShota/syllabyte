"""The visual template library (animation_agent/visuals, plan/visual-template-library-plan.md). No LLM calls.

Set SYLLABYTE_RENDER_TESTS=1 to also render every template's example segment, in the dialogue frame and the
full frame, through the real render path, and require no layout findings."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from animation_agent.manim_codegen import check_beat_structure
from animation_agent.visuals.calls import CallError, check_segment, parse_call, segment_draws
from animation_agent.visuals.runner import CLASSES
from animation_agent.visuals.scene_code import build_spec_scene
from animation_agent.visuals.specs import REGISTRY, bisect_next, real_eigenvectors, template_cards
from script_generation_agent.prompts import storyboard_system_prompt
from syllabyte_common.models import RenderSegment, TemplatedDialogueScript, load_script

ARR = 'a = ArrayBars(values=[1, 3, 4, 7, 9], area="bottom_half")'


def segment(*beats: list[str]):
    return SimpleNamespace(beats=[SimpleNamespace(narration="x", visual="y", draw=list(b)) for b in beats])


# --------------------------------------------------------------------------
# Specs and drawing classes agree
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_every_action_has_a_method_and_back(name):
    cls, spec = CLASSES[name], REGISTRY[name]
    methods = {n for n, f in inspect.getmembers(cls, inspect.isfunction)
               if inspect.isgeneratorfunction(f) and n != "create" and not n.startswith("_")}
    assert methods == set(spec.all_actions())


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_each_example_passes_and_is_in_the_prompt(name):
    spec = REGISTRY[name]
    assert check_segment(spec.example) == []
    prompt = storyboard_system_prompt(2, None, explainer="P", peer="S", lexicon="-", example="")
    assert f"{name}(" in template_cards() and f"{name}(" in prompt and "area=" not in prompt


# --------------------------------------------------------------------------
# Parsing: a tiny language, never executed
# --------------------------------------------------------------------------


def test_strings_are_raw_so_tex_keeps_backslashes():
    call = parse_call(r'eq.rewrite(tex="\frac{1}{2} \theta \nabla")', {"eq": "EquationSteps"})
    assert call.args["tex"] == r"\frac{1}{2} \theta \nabla"


@pytest.mark.parametrize("text, why", [
    ("__import__('os').system('ls')", "either name = Template"),
    ("a = open(file='x')", "unknown template"),
    ('a = ArrayBars([1, 2])', "keyword arguments only"),
    ("a = ArrayBars(values=list(range(3)))", "plain value"),
    ("a = ArrayBars(values=[1]); b = Note(text='x')", "one statement"),
    ("a.highlight(indices=[0])", "hasn't been created"),
])
def test_anything_outside_the_language_is_rejected(text, why):
    with pytest.raises(CallError, match=why):
        parse_call(text, {})


# --------------------------------------------------------------------------
# Checking a segment by simulating it
# --------------------------------------------------------------------------


@pytest.mark.parametrize("beats, why", [
    ([[]], "beat 1 has no calls"),
    ([[ARR], ["a.highlight(indices=[7])"]], "index 7 is outside"),
    ([['a = ArrayBars(values=[3, 1, 2])'], ["a.bisect_check(target=2)"]], "sorted"),
    ([[ARR], ["a.bisect_discard()"]], "needs a bisect_check"),
    ([[ARR], ['b = Note(text="hi", area="bottom_third")']], "overlaps a"),
    ([[ARR] + ["a.clear()"] * 6], "at most 6"),
    ([[ARR], ["a.remove()"], ["a.clear()"]], "hasn't been created"),
    ([[ARR], ['a = Note(text="again", area="bottom_half")'], ["a.highlight(indices=[0])"]], "has no action"),
    ([['a = ArrayBars(values=[1, 2], area="bottom_third")']], "at least half"),
    ([['g = LinearMap2D(matrix=[[3, 0], [0, 3]], vectors=[{"name": "v", "x": 2, "y": 0}])']], "off the grid"),
    ([['g = LinearMap2D(matrix=[[1, 2, 3], [0, 1]])']], "2x2"),
    ([['e = EquationSteps(tex="x + 1")'], ['e.highlight(part="y")']], "not in the current line"),
    ([['e = EquationSteps(tex="x + 1")'], ['e.cover(part="1")'], ['e.highlight(part="x")']], "uncover it first"),
])
def test_check_segment_finds(beats, why):
    problems = check_segment(beats)
    assert any(why in p for p in problems), problems


def test_bisection_is_simulated_to_its_end():
    beats = [[ARR], ["a.bisect_step(target=9)"], ["a.bisect_step(target=9)"], ["a.bisect_step(target=9)"]]
    assert check_segment(beats) == []  # 4 -> mid 2 (4<9, go right), then mid 3 (7<9), then mid 4 found
    assert check_segment(beats + [["a.bisect_step(target=9)"]]) == []  # after it ends, a new search starts
    assert "needs a bisect_check" in check_segment(beats + [["a.bisect_discard()"]])[0]


def test_bisect_next_and_eigenvectors():
    values = [1, 3, 4, 7, 9, 11, 15]
    assert bisect_next(values, 0, 6, 9) == (3, 4, 6, False)
    assert bisect_next(values, 4, 6, 9) == (5, 4, 4, False)
    assert bisect_next(values, 4, 4, 9) == (4, 4, 4, True)
    pairs = sorted(real_eigenvectors([[2, 1], [1, 2]]))
    assert [round(v, 6) for v, _ in pairs] == [1, 3]
    assert real_eigenvectors([[0, -1], [1, 0]]) == []  # a rotation has none
    assert len(real_eigenvectors([[2, 0], [0, 2]])) == 2  # every direction; two lines drawn


# --------------------------------------------------------------------------
# Scenes, schema, the writer
# --------------------------------------------------------------------------


def test_spec_scene_passes_the_renderers_beat_check():
    code = build_spec_scene(segment([ARR], [], ["a.bisect_step(target=9)"]), "Seg2")
    assert code is not None and check_beat_structure(code, 3) is None


def test_no_spec_scene_without_calls_or_with_bad_ones():
    assert build_spec_scene(segment([], []), "Seg0") is None
    assert build_spec_scene(segment([ARR], ["a.highlight(indices=[9])"]), "Seg0") is None


def _templated(draws: list[list[str]]) -> TemplatedDialogueScript:
    beat = {"narration": "Why does it halve?", "visual": "a list", "speaker": "peer", "step": "question",
            "misconception": False}
    segs = [{"phase": "deliver", "source_refs": [{"deck_name": "d", "slide_number": 1}],
             "beats": [beat | {"draw": d} for d in draws]}]
    return TemplatedDialogueScript.model_validate(
        {"ku_id": "ku-x", "title": "X", "style": "dialogue", "visuals": "templates", "segments": segs})


def test_templated_scripts_load_and_keep_their_calls_for_the_renderer():
    script = _templated([[ARR], ["a.bisect_step(target=9)"]])
    loaded = load_script(script.model_dump_json())
    assert isinstance(loaded, TemplatedDialogueScript)
    render_seg = RenderSegment(**loaded.segments[0].model_dump(), frame="dialogue")
    assert segment_draws(render_seg) == [[ARR], ["a.bisect_step(target=9)"]]


def test_visual_sentences_are_computed_from_the_calls():
    from animation_agent.visuals.calls import describe_segment

    said = describe_segment([[ARR], ["a.bisect_step(target=9)"], [], ["a.remove()"]])
    assert said[0] == "A row of 5 blue cells: 1, 3, 4, 7, 9 (bottom half)."
    assert said[1] == ("Lo, mid, hi point at the cells holding 1, 4, 9; the middle value 4 is compared with the "
                       "target 9; 4 < 9, so the cells holding 1, 3, 4 grey out; the cells holding 7, 9 stay in play.")
    assert said[2] == "The picture stays as it is."
    assert said[3] == "The list fades out."
    grid = describe_segment([['g = LinearMap2D(matrix=[[2, 1], [1, 2]], vectors=[{"name": "v", "x": 1, "y": 1}])'],
                             ["g.apply()", "g.eigenlines()"]])
    assert "v (1, 1) -> (3, 3)" in grid[1] and "along (1, 1) labelled lambda = 3" in grid[1]
    eq = describe_segment([[r'e = EquationSteps(tex="A v = \lambda v")']])
    assert eq == [r"The formula A v = \lambda v (filling the frame)."]  # TeX keeps its case


def test_every_action_says_what_it_shows():
    for spec in REGISTRY.values():
        assert spec.describe is not None, spec.name
        for name, action in spec.all_actions().items():
            assert action.says is not None, f"{spec.name}.{name}"


def test_the_calls_are_checked_against_the_words():
    lines = ["Here are eight cells.", "Check the middle."]
    problems = check_segment([[ARR], ["a.bisect_check(target=9)"]], lines)
    assert any('says "eight cells" but the list on screen has 5 cells' in p for p in problems)
    assert check_segment([[ARR], []], ["Five numbers, sorted.", "ok"]) == []
    assert check_segment([[ARR], []], ["A million items.", "ok"]) == []  # nothing to count against
    only_notes = check_segment([['n = Note(text="hi")'], ['n.say(text="bye")']], ["a", "b"])
    assert any("only Notes" in p for p in only_notes)
    assert check_segment([['n = Note(text="hi")']]) == []  # the renderer's check stays structural
    echo = check_segment([[ARR, 'a.note(text="does v leave its line?")']], ["Pause: does v leave its line?"])
    assert any("repeats the line's own words" in p for p in echo)
    assert check_segment([[ARR, 'a.note(text="mid = 4")']], ["Check the middle one."]) == []
    text_only = check_segment([[ARR], ['a.note(text="mid = 4")', "a.unpoint(name=\"lo\")"], []], ["a", "b", "c"])
    assert any("beat 2: its calls only put text on screen" in p for p in text_only)
    assert not any("beat 3" in p for p in text_only)  # [] keeps the picture: fine
    on_top = check_segment([['g = LinearMap2D(matrix=[[2, 0], [0, 1]], vectors=[{"name": "v", "x": 1, "y": 0}])',
                             'g.ghost_vector(x=1, y=0)']])
    assert any("sits exactly on vector v" in p for p in on_top)


def test_template_visuals_change_the_video_key_only_when_used():
    from syllabyte_common.models import CourseCorpus, KnowledgeUnit
    from syllabyte_common.video_jobs import video_key

    corpus = CourseCorpus(course_name="c", syllabus_path="s.pdf", syllabus_text="", decks=[], slides=[])
    ku = KnowledgeUnit(id="ku-x", title="X", summary="s", bloom_level="understand", cognitive_load="low",
                       visual_idea="v", short_worthiness=3, short_worthiness_reason="r")
    base = video_key(corpus, ku, 2, [])
    assert video_key(corpus, ku, 2, [], visuals="codegen") == base
    assert video_key(corpus, ku, 2, [], visuals="templates") != base


# --------------------------------------------------------------------------
# Rendering (opt-in)
# --------------------------------------------------------------------------


@pytest.mark.skipif(not os.environ.get("SYLLABYTE_RENDER_TESTS"), reason="set SYLLABYTE_RENDER_TESTS=1 to render")
@pytest.mark.parametrize("frame", ["dialogue", "full"])
@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_each_example_renders_with_no_layout_findings(name, frame, tmp_path):
    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render

    example = REGISTRY[name].example
    code = build_spec_scene(segment(*example), "Seg0")
    durations = [2.5] * len(example)
    (tmp_path / BEATS_FILE).write_text(json.dumps(durations))
    ok, error, _, layout = _try_render(Path(tmp_path), code, "Seg0", "low", len(durations), sum(durations),
                                       check_formulas=False, frame=frame)
    assert ok, error
    assert layout.findings == [], layout.findings


def test_early_voices_are_used_only_for_the_same_lines(tmp_path, monkeypatch):
    import sys

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    sys.modules.pop("generate_shorts", None)
    import generate_shorts
    from test_dialogue import make_script
    from syllabyte_common.models import SegmentAudio

    def fake_tts(script, out, backend):
        out.mkdir(parents=True)
        (out / "seg_0.wav").write_bytes(b"RIFF")
        return [SegmentAudio(segment_index=0, wav_path=str(out / "seg_0.wav"), duration_seconds=1.0,
                             srt_start=0.0, srt_end=1.0, beat_durations=[1.0])]

    monkeypatch.setattr(generate_shorts, "synthesize_segments", fake_tts)
    voices = generate_shorts.EarlyVoices(tmp_path / "audio", "kokoro")
    script = make_script()
    voices.start(script)
    redrawn = script.model_copy(deep=True)
    redrawn.segments[0].beats[0].visual = "something else"  # pictures change, words don't
    audios = voices.take(redrawn)
    assert audios is not None and Path(audios[0].wav_path) == tmp_path / "audio" / "seg_0.wav"
    assert Path(audios[0].wav_path).exists()
    rewritten = script.model_copy(deep=True)
    rewritten.segments[0].beats[0].narration = "New words."
    assert voices.take(rewritten) is None
    voices.close()


# --------------------------------------------------------------------------
# Render crashes found by the course test (runs/course-test-1)
# --------------------------------------------------------------------------


def test_a_doubled_backslash_before_a_letter_is_read_as_one():
    call = parse_call(r'eq.then(tex="A = U\\Sigma V^T \\ x")', {"eq": "EquationSteps"})
    assert call.args["tex"] == r"A = U\Sigma V^T \\ x"  # a doubled one before a non-letter stays
    call = parse_call(r'eq = EquationSteps(tex="\\frac{1}{2}", colours=[{"part": "\\frac", "colour": "GOLD"}])', {})
    assert call.args["tex"] == r"\frac{1}{2}" and call.args["colours"][0]["part"] == r"\frac"


def test_a_failing_action_is_skipped_and_the_segment_goes_on(capsys):
    from manim import VGroup

    from animation_agent.visuals.runner import SpecRunner

    class Broken:
        group = VGroup()

        def box(self, args):
            raise ValueError("no such piece")
            yield

    runner = SpecRunner(SimpleNamespace(mobjects=[]))
    runner.objects["eq"] = Broken()
    runner._run(parse_call('eq.box(colour="GOLD")', {"eq": "EquationSteps"}), 1.0)
    assert "skipped eq.box: ValueError: no such piece" in capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("SYLLABYTE_RENDER_TESTS"), reason="set SYLLABYTE_RENDER_TESTS=1 to render")
@pytest.mark.parametrize("beats", [
    # A piece inside a coloured piece (the XOR video): MathTex can't isolate both.
    [['eq = EquationSteps(tex="w_1 x_1 + w_2 x_2 + b", colours=[{"part": "w_1 x_1 + w_2 x_2 + b", '
      '"colour": "TEAL"}], area="top_third")', 'eq.highlight(part="b")'],
     ['eq.then(tex="\\Phi(w_1 x_1 + w_2 x_2 + b)")', 'eq.highlight(part="\\Phi")']],
    # A doubled backslash with that piece highlighted (the SVD video): LaTeX couldn't convert it.
    [['eq = EquationSteps(tex="A = U \\\\Sigma V^T", area="top_third")', 'eq.highlight(part="\\Sigma")']],
])
def test_course_test_formulas_render(beats, tmp_path):
    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render

    code = build_spec_scene(segment(*beats), "Seg0")
    durations = [2.5] * len(beats)
    (tmp_path / BEATS_FILE).write_text(json.dumps(durations))
    ok, error, _, _ = _try_render(Path(tmp_path), code, "Seg0", "low", len(durations), sum(durations),
                                  check_formulas=False, frame="dialogue")
    assert ok, error
