"""Computed diagram semantics and explicit coverage failures, without paid model calls."""
import os

import pytest
from pydantic import ValidationError
from animation_agent.visuals.calls import check_segment, describe_segment
from animation_agent.visuals.specs import MemoryParams, VennParams, BindRefArgs, CopyRefArgs, MutateRefArgs, memory_op, venn_regions, venn_result
from script_generation_agent.picture_plan import PicturePlan


def test_aliases_observe_mutations_but_a_copy_is_independent():
    s = MemoryParams(objects={"o1": "[1]"}, refs={"x": "o1", "y": "o1"}).model_dump()
    assert memory_op("copy", s, CopyRefArgs(source="o1", target="o2")) is None
    memory_op("bind", s, BindRefArgs(variable="y", object="o2"))
    memory_op("mutate", s, MutateRefArgs(object="o1", value="[9]"))
    assert s["objects"][s["refs"]["x"]] == "[9]"
    assert s["objects"][s["refs"]["y"]] == "[1]"
    assert memory_op("bind", s, BindRefArgs(variable="z", object="absent"))
    assert "z" not in s["refs"]


def test_memory_actions_are_described_from_the_updated_state():
    beats = [['m = MemoryRefs(objects={"o": "[1]"}, refs={"x": "o", "y": "o"})'],
             ['m.mutate(object="o", value="[2]")']]
    assert check_segment(beats) == []
    assert "o holds [2]" in describe_segment(beats)[1]
    assert "x points to o, y points to o" in describe_segment(beats)[1]
    assert check_segment(beats + [['m.copy(source="o", target="o")']])


@pytest.mark.parametrize("operation,expected", [
    ("union", ["1", "2", "3"]), ("intersection", ["2"]), ("a_minus_b", ["1"]),
    ("b_minus_a", ["3"]), ("symmetric_difference", ["1", "3"]),
    ("complement_a", ["3", "4"]), ("complement_b", ["1", "4"]),
])
def test_set_operations_are_computed_inside_the_declared_universe(operation, expected):
    s = VennParams(universe=["1", "2", "3", "4"], a=["1", "2"], b=["2", "3"]).model_dump()
    assert venn_regions(s) == [["1"], ["2"], ["3"], ["4"]]
    assert venn_result(s, operation) == expected


def test_empty_intersection_and_invalid_membership():
    s = VennParams(universe=["a", "b"], a=["a"], b=[]).model_dump()
    assert venn_result(s, "intersection") == []
    assert venn_result(s, "complement_b") == ["a", "b"]
    with pytest.raises(ValidationError):
        VennParams(universe=["1"], a=["2"], b=[])
    with pytest.raises(ValidationError):
        VennParams(universe=["1", "1"], a=[], b=[])
    with pytest.raises(ValidationError):
        MemoryParams(objects={"o": "value"}, refs={"x": "unknown"})


def test_a_family_no_template_draws_still_falls_back_to_formulas_and_notes(monkeypatch):
    """The port keeps main's behaviour for a gap: the video is drawn with formulas and notes, it is not stopped."""
    from animation_agent.visuals import families
    from script_generation_agent.prompts import picture_brief
    monkeypatch.delitem(families.DRAWN_BY, "geometry")  # every family has a template now; pretend one has none
    plan = PicturePlan(family="geometry", reason="test")
    assert plan.gap and plan.templates == ["EquationSteps", "Note"]
    assert "Show the idea with formulas" in picture_brief("geometry", plan.templates)


def test_new_families_use_their_real_templates():
    for family, template in [("memory_refs", "MemoryRefs"), ("sets_logic", "VennDiagram")]:
        plan = PicturePlan(family=family, reason="test")
        assert not plan.gap and plan.main == template and template in plan.templates


def test_limits_reject_unreadable_labels_and_too_many_elements():
    with pytest.raises(ValidationError, match="too wide"):
        MemoryParams(objects={"o": "WWWWWWWWWW"}, refs={"x": "o"})
    with pytest.raises(ValidationError, match="each Venn region"):
        VennParams(universe=["1", "2", "3", "4"], a=["1", "2", "3", "4"], b=[])
    assert check_segment([['m = MemoryRefs(objects={"o": "[1]"}, refs={"x": "o"})'],
                          ['m.bind(variable="WWWWWW", object="o")']])


@pytest.mark.skipif(not os.environ.get("SYLLABYTE_RENDER_TESTS"), reason="set SYLLABYTE_RENDER_TESTS=1 to render")
@pytest.mark.parametrize("beats", [
    [['m = MemoryRefs(objects={"o1": "[1,2,3]", "o2": "[2]", "o3": "[3]"}, refs={"x": "o1", "y": "o1", "z": "o3"}, area="top_two_thirds")'],
     ['m.move(area="bottom_two_thirds")', 'm.unbind(variable="y")']],
    [['v = VennDiagram(universe=["1", "2", "3", "4", "5", "6", "7", "8"], a=["1", "2", "3", "4", "5", "6"], b=["4", "5", "6", "7"], area="top_two_thirds")'],
     ['v.shade(operation="symmetric_difference")'], ['v.move(area="bottom_two_thirds")'], ['v.clear()']],
])
def test_dense_diagrams_render_in_the_smallest_supported_area(beats, tmp_path):
    import json
    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render
    from animation_agent.visuals.scene_code import build_spec_scene
    from test_visual_templates import segment
    assert check_segment(beats) == []
    code = build_spec_scene(segment(*beats), "Seg0")
    durations = [2.5] * len(beats)
    (tmp_path / BEATS_FILE).write_text(json.dumps(durations))
    ok, error, _, layout = _try_render(tmp_path, code, "Seg0", "low", len(durations), sum(durations),
                                       check_formulas=False, frame="dialogue")
    assert ok, error
    assert layout.findings == [], layout.findings
