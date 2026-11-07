"""The storyboard's per-picture modules: each worked example is one the pipeline would accept as it is, and the
prompt carries the module the picture plan's family picks. No LLM calls."""

from __future__ import annotations

import pytest

from animation_agent.visuals.calls import check_script, script_segments
from animation_agent.visuals.highlights import fix_highlights
from animation_agent.visuals.normalize import fill_still, hold_reveals, normalize_script, still_beats
from script_generation_agent import storyboard
from script_generation_agent.script_writer import validate_dialogue
from script_generation_agent.storyboard_example import SEGMENT_KEYS
from script_generation_agent.storyboard_modules import MODULES, module_for, render_module_example
from test_storyboard import KU, REFS


def module_board(module, plan):
    ex = module.example
    data = {"title": ex["title"], "colour_key": ex["colour_key"]}
    for key in SEGMENT_KEYS:
        seg = {"source_refs": REFS, "sketches": []}
        for field, draw, line in ex[key]:
            seg[field] = {"draw": list(draw), "narration": line.format(explainer="Peter", peer="Stewie")}
        data[key] = seg
    return storyboard.storyboard_model(plan).model_validate(data)


@pytest.mark.parametrize("name", sorted(MODULES))
def test_each_module_example_is_one_the_pipeline_accepts_as_it_is(name):
    module = MODULES[name]
    plan = storyboard.skeleton(2)
    for seg in plan:
        assert [f for f, *_ in module.example[seg.key]] == [b.key(k) for k, b in enumerate(seg.beats, 1)]
    script = storyboard.assemble(module_board(module, plan), plan, KU)
    assert storyboard.fix_slang(script, plan) == []
    assert validate_dialogue(script) == []
    for seg, sp in zip(script.segments, plan):  # every line within its word range, give or take two
        for beat, bp in zip(seg.beats, sp.beats):
            assert bp.words[0] - 2 <= len(beat.narration.split()) <= bp.words[1] + 2, (beat.narration, bp.words)
    segments = script_segments(script)
    lines = [[b.narration for b in seg.beats] for seg in script.segments]
    steps = [[(b.step, b.misconception) for b in seg.beats] for seg in script.segments]
    assert check_script(segments, lines) == []  # numbers on screen, every change said, no text-only beat
    assert hold_reveals(segments, steps, lines)[1] == []  # no question or predict line shows its answer
    assert fill_still(segments, steps, lines)[1] == [] and still_beats(segments, steps) == []
    key = {t["term"]: t["colour"] for t in module.example["colour_key"]}
    assert fix_highlights(segments, steps, lines, key)[1] == []  # no false green, no answer lit, key colours
    fixed = normalize_script(segments, lines)
    assert fixed.log == [] and fixed.left == []


def test_every_family_with_a_template_gets_a_module_or_keeps_the_generic_example():
    from animation_agent.visuals.families import DRAWN_BY

    assert module_for("flowchart").name == "boxes" and module_for("series").name == "bars"
    assert module_for("equation_steps").name == "formulas" and module_for("array_bars") is None
    covered = {f for m in MODULES.values() for f in m.families}
    assert set(DRAWN_BY) - covered == {"array_bars", "merge_sort", "linear_map_2d", "note"}  # the generic example
    assert all(len({id(m) for m in MODULES.values() if f in m.families}) == 1 for f in covered)


def test_the_prompt_carries_the_module_the_family_picks():
    from script_generation_agent.prompts import storyboard_system_prompt
    from script_generation_agent.storyboard import _example

    ex = _example("Peter", "Stewie", 2, "series")
    assert "Expected value: counting outcomes" in ex and "Linear search" not in ex
    assert "Linear search" in _example("Peter", "Stewie", 2, "array_bars")
    assert "Insertion sort" in _example("Peter", "Stewie", 3, "series")  # Level 3 keeps its own beat plan
    system = storyboard_system_prompt(2, None, explainer="P", peer="S", lexicon="-", example=ex,
                                      templates=["BarChart", "EquationSteps", "Note"], family="series")
    assert "Drawing this kind of picture (bars)" in system and "never every bar" in system
    assert "Drawing this kind of picture" not in storyboard_system_prompt(
        2, None, explainer="P", peer="S", lexicon="-", example="", templates=["ArrayBars", "Note"], family="array_bars")


def test_module_examples_render_in_the_prompts_form():
    text = render_module_example(MODULES["table"], explainer="Peter", peer="Stewie")
    assert text.startswith("Knowledge Unit: Tracing a loop") and "Stewie, after all three passes" in text


@pytest.mark.skipif(not __import__("os").environ.get("SYLLABYTE_RENDER_TESTS"), reason="set SYLLABYTE_RENDER_TESTS=1")
@pytest.mark.parametrize("name", sorted(MODULES))
@pytest.mark.parametrize("segment", [0, 2, 3])
def test_each_module_example_renders_with_no_layout_findings(name, segment, tmp_path):
    import json
    from pathlib import Path

    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render
    from animation_agent.visuals.scene_code import build_spec_scene
    from test_storyboard import _render_segment_for

    plan = storyboard.skeleton(2)
    script = storyboard.finish(storyboard.assemble(module_board(MODULES[name], plan), plan, KU), ku_id="ku-x")
    seg = _render_segment_for(script, segment)
    code = build_spec_scene(seg, f"Seg{segment}")
    durations = [2.5] * len(seg.beats)
    (tmp_path / BEATS_FILE).write_text(json.dumps(durations))
    ok, error, _, layout = _try_render(Path(tmp_path), code, f"Seg{segment}", "low", len(durations), sum(durations),
                                       check_formulas=False, frame="dialogue")
    assert ok, error
    assert layout.findings == [], layout.findings
