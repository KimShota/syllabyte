"""Storyboards: the code-built beat plan, the one-call schema, code fixes for calls, carried pictures. No LLM calls.

Set SYLLABYTE_RENDER_TESTS=1 to also render a segment that continues the picture of the one before it."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from animation_agent.visuals.calls import check_script, describe_script, script_segments
from animation_agent.visuals.normalize import hold_reveals, lay_out, normalize_script
from animation_agent.visuals.scene_code import build_spec_scene
from script_generation_agent import storyboard
from script_generation_agent.picture_plan import PicturePlan
from script_generation_agent.script_writer import validate_dialogue
from script_generation_agent.slang import find_slang
from script_generation_agent.storyboard_example import EXAMPLES, SEGMENT_KEYS, render_example
from syllabyte_common.models import KnowledgeUnit, RenderSegment

KU = KnowledgeUnit(id="ku-x", title="X", summary="s", bloom_level="understand", cognitive_load="low",
                   visual_idea="v", short_worthiness=3, short_worthiness_reason="r",
                   source_refs=[{"deck_name": "d", "slide_number": 1}])
REFS = [{"deck_name": "d", "slide_number": 1}]
ARR = 'a = ArrayBars(values=[1, 3, 4, 7, 9])'


def example_board(plan=None, level=2, **changes):
    plan = plan or storyboard.skeleton(level)
    example = EXAMPLES[level][1]
    data = {"title": example["title"], "colour_key": example["colour_key"]}
    for key in SEGMENT_KEYS:
        seg = {"source_refs": REFS, "sketches": []}
        for field, draw, line in example[key]:
            seg[field] = {"draw": list(draw), "narration": line.format(explainer="Peter", peer="Stewie")}
        data[key] = seg
    data.update(changes)
    return storyboard.storyboard_model(plan).model_validate(data)


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", [1, 2, 3])
@pytest.mark.parametrize("prereqs", [False, True])
def test_the_plan_passes_the_dialogue_checks_by_construction(level, prereqs):
    plan = storyboard.skeleton(level, prereqs)
    lo = sum(b.words[0] for seg in plan for b in seg.beats)
    hi = sum(b.words[1] for seg in plan for b in seg.beats)
    assert storyboard.DIALOGUE_MIN_WORDS <= lo and hi <= storyboard.DIALOGUE_MAX_WORDS
    data = {"title": "t", "colour_key": []}
    for seg in plan:
        beats = {}
        for k, b in enumerate(seg.beats, 1):
            words = " ".join(["word"] * b.words[0])
            beats[b.key(k)] = {"draw": [], "narration": ("No cap, " if b.slang else "") + words}
        data[seg.key] = {"source_refs": REFS, "sketches": ["x"] * len(seg.beats), **beats}
    script = storyboard.assemble(storyboard.storyboard_model(plan).model_validate(data), plan, KU)
    assert validate_dialogue(script) == []


def test_every_planned_beat_is_a_required_field():
    data = example_board().model_dump()
    del data["deliver_1"]["b3_explainer_feedback"]
    with pytest.raises(ValidationError):
        storyboard.storyboard_model(storyboard.skeleton(2)).model_validate(data)


@pytest.mark.parametrize("level", [1, 2, 3])
def test_each_example_matches_its_plan_and_needs_no_fixing(level):
    plan = storyboard.skeleton(level)
    for seg in plan:
        assert [f for f, *_ in EXAMPLES[level][1][seg.key]] == [b.key(k) for k, b in enumerate(seg.beats, 1)]
    script = storyboard.assemble(example_board(plan, level), plan, KU)
    assert storyboard.fix_slang(script, plan) == []
    assert validate_dialogue(script) == []
    for seg, sp in zip(script.segments, plan):  # every line within its word range, give or take two
        for beat, bp in zip(seg.beats, sp.beats):
            assert bp.words[0] - 2 <= len(beat.narration.split()) <= bp.words[1] + 2, (beat.narration, bp.words)
    lines = [[b.narration for b in seg.beats] for seg in script.segments]
    steps = [[(b.step, b.misconception) for b in seg.beats] for seg in script.segments]
    assert hold_reveals(script_segments(script), steps)[1] == []  # no question or predict line shows its answer
    fixed = normalize_script(script_segments(script), lines)
    assert fixed.log == [] and fixed.left == []
    assert all(not b.draw or "area" not in c for seg in script.segments for b in seg.beats for c in b.draw)


def test_each_level_gets_its_own_example():
    texts = {level: render_example(explainer="Peter", peer="Stewie", level=level) for level in (1, 2, 3)}
    assert "matrix by a vector" in texts[1] and "Linear search" in texts[2] and "Insertion sort" in texts[3]
    assert all("{peer}" not in t and "Stewie" in t for t in texts.values())


def test_slang_goes_where_the_plan_says():
    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)
    hook = script.segments[0].beats[0]
    hook.narration = "How does a program find one number in a list?"
    script.segments[2].beats[1].narration = "Just one: we jump straight to seven."  # a second slot loses its phrase
    script.segments[4].beats[0].narration = "No cap, linear search checks each cell once."  # a check line
    log = storyboard.fix_slang(script, plan)
    assert hook.narration.startswith("Lowkey, how does") and find_slang(hook.narration)
    assert script.segments[4].beats[0].narration == "Linear search checks each cell once."
    assert script.segments[2].beats[1].narration == "Just one: we jump straight to seven."  # minimum reached
    assert len(log) == 2
    named = storyboard.assemble(example_board(plan), plan, KU)
    named.segments[0].beats[0].narration = "Peter, how does a program find one number?"
    named.segments[2].beats[1].narration = "Just one: we jump straight to seven."
    storyboard.fix_slang(named, plan, ("Peter", "Stewie"))
    assert named.segments[0].beats[0].narration == "Lowkey, Peter, how does a program find one number?"


# --------------------------------------------------------------------------
# Calls: layout, code fixes, carrying the picture over
# --------------------------------------------------------------------------


def test_code_lays_out_what_is_on_screen_together():
    segs = lay_out([[[ARR, 'n = Note(text="mid?")'], ["n.remove()"], ["a.highlight(indices=[0])"]],
                    [['e = EquationSteps(tex="x + 1")']]])
    assert 'area="bottom_two_thirds"' in segs[0][0][0] and 'area="top_third"' in segs[0][0][1]
    assert check_script(segs) == []
    alone = lay_out([[[ARR], ["a.remove()"]], [['g = LinearMap2D(matrix=[[2, 0], [0, 1]])']]])
    assert 'area="full"' in alone[1][0][0]


def test_the_picture_carries_into_the_next_segment():
    segs = [[[ARR]], [["a.bisect_check(target=9)"], ["a.bisect_discard()"]]]
    assert check_script(lay_out(segs)) == []
    said = describe_script(lay_out(segs))
    assert said[1][0].startswith("Lo, mid, hi point at the cells holding 1, 4, 9")
    replaced = check_script(lay_out([[[ARR]], [['a = Note(text="hi")'], ["a.say(text=\"yo\")"]]]))
    assert replaced == []  # creating a name again replaces the object


def test_mechanical_problems_are_fixed_in_code():
    lines = [["Look at the list.", "Is seven there?", "Check.", "Grid."]]
    segs = [[
        [ARR, 'a.note(text="a note far too long to fit on the screen")'],
        ['a.note(text="is seven there")'],  # repeats the line
        ["b.highlight(indices=[1])", "a.highlight(indices=[1])"],  # b doesn't exist
        ['g = LinearMap2D(matrix=[[2, 0], [0, 2]], vectors=[{"name": "v", "x": 2, "y": 1}], extent=3)',
         'g.add_vector(name="z", x=0, y=0)'],
    ]]
    fixed = normalize_script(segs, lines)
    assert fixed.left == [], fixed.left
    calls = [c for beat in fixed.segments[0] for c in beat]
    assert not any("note" in c for c in calls) and not any(c.startswith("b.") for c in calls)
    assert any("extent=4" in c for c in calls) and not any("x=0, y=0" in c for c in calls)


def test_what_code_cannot_fix_goes_to_one_call_then_is_dropped(monkeypatch):
    plan = storyboard.skeleton(2)
    board = example_board(plan)
    board.deliver_1.b4_peer_build.draw = ["lst.scan(index=9, target=7)"]  # outside the list
    script = storyboard.assemble(board, plan, KU)
    calls = []

    def fake(**kw):
        calls.append(kw["stage"])
        assert "index 9 is outside" in kw["content"][0]["text"]
        beats = [{"draw": list(b.draw)} for b in script.segments[2].beats]
        beats[3]["draw"] = ["lst.scan(index=3, target=7)"]
        return storyboard._Fixes.model_validate({"segments": [{"segment_index": 2, "beats": beats}]})

    monkeypatch.setattr(storyboard, "structured", fake)
    done = storyboard.finish(script, ku_id="ku-x")
    assert calls == ["storyboard_fix"] and done.segments[2].beats[3].draw == ["lst.scan(index=3, target=7)"]
    assert done.segments[2].beats[3].visual.startswith("Pointer i moves to the cell holding 7")

    def broken(**kw):
        raise RuntimeError("down")

    monkeypatch.setattr(storyboard, "structured", broken)
    dropped = storyboard.finish(storyboard.assemble(board, plan, KU), ku_id="ku-x")
    assert dropped.segments[2].beats[3].draw == []
    assert check_script(script_segments(dropped)) == []


def test_write_storyboard_is_one_call(monkeypatch):
    stages, ready = [], []

    def fake(**kw):
        stages.append(kw["stage"])
        assert "Fill in the storyboard" in kw["content"][0]["text"] and kw["effort"] == "medium"
        assert kw["model"] == "claude-sonnet-5-5"
        return example_board()

    monkeypatch.setattr(storyboard, "structured", fake)
    monkeypatch.setattr("script_generation_agent.script_writer.gather_source_material", lambda c, k: ("slides", []))
    picture = PicturePlan(family="array_bars", also=[], reason="a list searched cell by cell")
    script = storyboard.write_storyboard(KU, None, level=2, on_lines_ready=ready.append, picture=picture)
    assert stages == ["storyboard_l2"] and len(ready) == 1
    assert script.visuals == "templates" and all(s.drawn_by == "templates" for s in script.segments)
    assert script.segments[0].beats[0].visual.startswith("A row of 6 blue cells")


def _render_segment_for(script, i):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from generate_shorts import render_segment_for

    return render_segment_for(script, i, "dialogue")


def test_render_segments_carry_the_calls_before_them():
    plan = storyboard.skeleton(2)
    script = storyboard.finish(storyboard.assemble(example_board(plan), plan, KU), ku_id="ku-x")
    seg = _render_segment_for(script, 2)
    assert isinstance(seg, RenderSegment) and seg.templates
    assert seg.carried == [c for s in script.segments[:2] for b in s.beats for c in b.draw]
    code = build_spec_scene(seg, "Seg2")
    assert code is not None and "run.setup()" in code


@pytest.mark.skipif(not os.environ.get("SYLLABYTE_RENDER_TESTS"), reason="set SYLLABYTE_RENDER_TESTS=1 to render")
@pytest.mark.parametrize("level", [1, 2, 3])
def test_a_carried_picture_renders_with_no_layout_findings(tmp_path, level):
    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render

    plan = storyboard.skeleton(level)
    script = storyboard.finish(storyboard.assemble(example_board(plan, level), plan, KU), ku_id="ku-x")
    seg = _render_segment_for(script, 3)
    code = build_spec_scene(seg, "Seg3")
    durations = [2.5] * len(seg.beats)
    (tmp_path / BEATS_FILE).write_text(json.dumps(durations))
    ok, error, _, layout = _try_render(Path(tmp_path), code, "Seg3", "low", len(durations), sum(durations),
                                       check_formulas=False, frame="dialogue")
    assert ok, error
    assert layout.findings == [], layout.findings


def test_over_the_word_limit_is_kept_but_too_short_is_not():
    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)
    script.segments[3].beats[0].narration += " word" * (storyboard.DIALOGUE_MAX_WORDS + 70 - script.word_count)
    word = [p for p in validate_dialogue(script) if p.startswith("word_count=")]
    assert word and storyboard._over_limit(word[0], script)

    short = storyboard.assemble(example_board(plan), plan, KU)
    for seg in short.segments:
        for beat in seg.beats:
            beat.narration = "Yes."
    word = [p for p in validate_dialogue(short) if p.startswith("word_count=")]
    assert word and not storyboard._over_limit(word[0], short)


@pytest.mark.parametrize("line, phrase, expected", [
    ("No cap, linear search checks each cell once.", "no cap", "Linear search checks each cell once."),
    ("Linear search checks each cell once, no cap.", "no cap", "Linear search checks each cell once."),
    ("Wait, for real? But v stayed on its own line.", "for real", None),  # a clause of its own
    ("Okay, the math is mathing.", "the math is mathing", None),  # nothing left
])
def test_taking_a_phrase_out_never_breaks_the_line(line, phrase, expected):
    from script_generation_agent.slang import _pattern

    assert storyboard._strip(line, _pattern(phrase)) == expected


def test_a_phrase_off_its_slot_stays_unless_the_step_forbids_it():
    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)
    script.segments[2].beats[3].narration = "Wait, for real? So we keep checking until it matches."  # a build line
    assert storyboard.fix_slang(script, plan) == []
    assert script.segments[2].beats[3].narration == "Wait, for real? So we keep checking until it matches."
