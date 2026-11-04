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
from script_generation_agent import script_writer
from script_generation_agent.prompts import templates_prompt
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
               if inspect.isgeneratorfunction(f) and n != "create"}
    assert methods == set(spec.all_actions())


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_each_example_passes_and_is_in_the_prompt(name):
    spec = REGISTRY[name]
    assert check_segment(spec.example) == []
    assert f"{name}(" in template_cards() and spec.example[0][0] in templates_prompt()


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
    ([[ARR, "a.clear()", "a.clear()", "a.clear()", "a.clear()"]], "at most 4"),
    ([[ARR], ["a.remove()"], ["a.clear()"]], "hasn't been created"),
    ([[ARR], ['a = Note(text="again")']], "already used"),
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
    assert check_segment(beats + [["a.bisect_step(target=9)"]])[0].endswith("the search already ended "
                                                                           "(found, or nothing left to check)")


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


def test_fix_draws_repairs_then_falls_back_to_code(monkeypatch):
    script = _templated([[ARR], ["a.highlight(indices=[9])"]])
    BD = script_writer._BeatDraw
    fixed = script_writer._DrawFixes(segments=[script_writer._SegmentDraws(
        segment_index=0, beats=[BD(draw=[ARR], visual="a list"), BD(draw=["a.highlight(indices=[2])"],
                                                                     visual="cell 2 lights up")])])
    monkeypatch.setattr(script_writer, "structured", lambda **kw: fixed)
    assert script_writer.fix_draws(script, ku_id="ku-x") == {}
    assert script.segments[0].beats[1].draw == ["a.highlight(indices=[2])"]
    assert script.segments[0].beats[1].visual == "cell 2 lights up"

    broken = _templated([[ARR], ["a.highlight(indices=[9])"]])

    def fail(**kw):
        raise RuntimeError("no")

    monkeypatch.setattr(script_writer, "structured", fail)
    left = script_writer.fix_draws(broken, ku_id="ku-x")
    assert 0 in left and all(b.draw == [] for b in broken.segments[0].beats)


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


def test_add_draws_fills_each_segment_and_survives_a_failed_call(monkeypatch):
    from test_dialogue import make_script  # tests/ is on sys.path (no __init__.py)

    script = make_script()

    def fake(**kw):
        text = kw["content"][0]["text"]
        if "Draw segment 1" in text:
            raise RuntimeError("timeout")
        # one entry: padded with empty ones to the beat count
        return script_writer._Draws(beats=[script_writer._BeatDraw(draw=['n = Note(text="hi")'], visual="hi")])

    monkeypatch.setattr(script_writer, "structured", fake)
    out = script_writer.add_draws(script, ku_id="ku-eigen")
    assert isinstance(out, TemplatedDialogueScript) and out.visuals == "templates"
    assert [len(s.beats) for s in out.segments] == [len(s.beats) for s in script.segments]
    assert out.segments[0].beats[0].draw == ['n = Note(text="hi")'] and out.segments[0].beats[0].visual == "hi"
    assert out.segments[1].beats[0].visual == script.segments[1].beats[0].visual  # left to the animator
    assert all(b.draw == [] for b in out.segments[1].beats)
    assert all(b.draw == [] for b in out.segments[2].beats[1:])


def test_feedback_redraws_only_the_flagged_segments(monkeypatch):
    from test_dialogue import make_script

    calls = []

    def fake(**kw):
        calls.append(kw["content"][0]["text"])
        return script_writer._Draws(beats=[script_writer._BeatDraw(draw=['n = Note(text="new")'], visual="new")])

    monkeypatch.setattr(script_writer, "structured", fake)
    first = script_writer.add_draws(make_script(), ku_id="ku-eigen")
    calls.clear()
    again = script_writer.add_draws(first, ku_id="ku-eigen", feedback={2: ["the arrow never moves"]})
    assert len(calls) == 1 and "the arrow never moves" in calls[0] and "Draw segment 2" in calls[0]
    assert again.segments[0].beats[0].draw == first.segments[0].beats[0].draw
