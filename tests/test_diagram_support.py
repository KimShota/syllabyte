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
        VennParams(universe=["1", "2", "3", "4", "5"], a=["1", "2", "3", "4", "5"], b=[])
    assert check_segment([['m = MemoryRefs(objects={"o": "[1]"}, refs={"x": "o"})'],
                          ['m.bind(variable="WWWWWW", object="o")']])


@pytest.mark.skipif(not os.environ.get("SYLLABYTE_RENDER_TESTS"), reason="set SYLLABYTE_RENDER_TESTS=1 to render")
@pytest.mark.parametrize("beats", [
    [['m = MemoryRefs(objects={"o1": "[1,2,3]", "o2": "[2]", "o3": "[3]"}, refs={"x": "o1", "y": "o1", "z": "o3"}, area="top_two_thirds")'],
     ['m.move(area="bottom_two_thirds")', 'm.unbind(variable="y")']],
    [['v = VennDiagram(universe=["1", "2", "3", "4", "5", "6", "7", "8"], a=["1", "2", "3", "4", "5", "6"], b=["4", "5", "6", "7"], area="top_two_thirds")'],
     ['v.shade(operation="symmetric_difference")'], ['v.move(area="bottom_two_thirds")'], ['v.clear()']],
    # the slides' own gcd example: divisors of 18 and 24, four in common
    [['v = VennDiagram(universe=["1", "2", "3", "4", "6", "8", "9", "12", "18", "24"], a=["1", "2", "3", "6", "9", "18"], b=["1", "2", "3", "4", "6", "8", "12", "24"], area="top_two_thirds")'],
     ['v.shade(operation="intersection")'], ['v.move(area="bottom_two_thirds")']],
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


def test_a_rule_defined_set_is_computed_from_the_universe():
    from animation_agent.visuals.specs import set_rule_members
    universe = ["1", "2", "3", "4", "6", "8", "9", "12", "18", "24"]
    v = VennParams(universe=universe, a_rule="divisors of 18", b_rule="Factors of 24")
    assert v.a == ["1", "2", "3", "6", "9", "18"] and v.b == ["1", "2", "3", "4", "6", "8", "12", "24"]
    assert set_rule_members("primes", universe) == ["2", "3"]
    assert set_rule_members("multiples of 3", universe) == ["3", "6", "9", "12", "18", "24"]
    assert set_rule_members("at most 4", universe) == ["1", "2", "3", "4"]
    assert set_rule_members("odd numbers", universe) == ["1", "3", "9"]


def test_listed_members_that_contradict_their_rule_are_rejected_with_the_right_ones():
    """The gcd video drew 'divisors of 24' without 12 and 24; with the rule beside them, that can't render."""
    universe = ["1", "2", "3", "4", "6", "8", "9", "12", "18", "24"]
    with pytest.raises(ValidationError, match=r"B should be the divisors of 24 in the universe, \['1', '2', '3', '4', '6', '8', '12', '24'\]"):
        VennParams(universe=universe, a_rule="divisors of 18", b=["1", "2", "3", "4", "6", "8"], b_rule="divisors of 24")
    # agreeing lists are fine
    assert VennParams(universe=["1", "2", "3", "6", "9", "18"], a=["1", "2", "3", "6", "9", "18"], a_rule="divisors of 18",
                      b=["2", "3"]).a_rule


def test_a_divisor_rule_needs_every_divisor_in_the_universe():
    with pytest.raises(ValidationError, match="universe is missing 12, 24, which are divisors of 24"):
        VennParams(universe=["1", "2", "3", "4", "6", "8"], a_rule="divisors of 24", b=["2"])


@pytest.mark.parametrize("kw, message", [
    ({"a_rule": "nice numbers", "b": ["1"]}, "unknown set rule"),
    ({"b": ["1"]}, "give a .its elements. or a_rule"),
])
def test_a_set_needs_members_or_a_known_rule(kw, message):
    with pytest.raises(ValidationError, match=message):
        VennParams(universe=["1", "2", "3"], **kw)


def test_rules_need_whole_number_elements():
    with pytest.raises(ValidationError, match="whole-number elements"):
        VennParams(universe=["a", "b", "c"], a_rule="even", b=["a"])


def test_the_rule_reaches_the_picture_description_and_the_writer():
    from animation_agent.visuals.specs import VENN_DIAGRAM, template_card
    v = VennParams(universe=["1", "2", "3", "4", "6", "8"], a_rule="divisors of 6", b_rule="even")
    assert "divisors of 6 = ['1', '2', '3', '6']" in VENN_DIAGRAM.describe(v)
    card = template_card(VENN_DIAGRAM)
    assert "a_rule" in card and 'a_rule="divisors of 6"' in card
    assert check_segment(VENN_DIAGRAM.example) == []


def test_a_listed_set_that_is_not_the_set_its_line_names_is_flagged():
    """The real gcd storyboard: the line says 'divide 24', B was listed without 12 and 24."""
    from animation_agent.visuals.calls import check_script
    venn = ('v = VennDiagram(universe=["1", "2", "3", "4", "6", "8", "9", "12", "18", "24"], '
            'a=["1", "2", "3", "6", "9", "18"], b=["1", "2", "3", "4", "6", "8"], area="bottom_two_thirds")')
    problems = check_script([[[venn]]], [["Lowkey, some numbers divide 18, some divide 24. So what does common mean here?"]])
    wrong = [p for p in problems if p.kind == "wrong_set"]
    assert len(wrong) == 1 and "v.b" in wrong[0].message and "missing 12, 24" in wrong[0].message
    assert 'b_rule="divisors of 24"' in wrong[0].message


def test_a_universe_that_leaves_a_divisor_out_is_caught_too():
    from animation_agent.visuals.calls import check_script
    venn = 'v = VennDiagram(universe=["1", "2", "3", "4", "6", "8", "9"], a=["1", "2", "3", "6", "9"], b=["1", "2", "3", "4", "6", "8"])'
    problems = check_script([[[venn]]], [["These are the divisors of 24 and of 18."]])
    assert {p.kind for p in problems} >= {"wrong_set"}


@pytest.mark.parametrize("venn, line", [
    # correct listed sets
    ('v = VennDiagram(universe=["1", "2", "3", "4", "6", "8", "9", "12", "18", "24"], a=["1", "2", "3", "6", "9", "18"], '
     'b=["1", "2", "3", "4", "6", "8", "12", "24"])', "Some numbers divide 18, some divide 24."),
    # rule-defined sets are computed, so never flagged
    ('v = VennDiagram(universe=["1", "2", "3", "4", "6", "8", "9", "12", "18", "24"], a_rule="divisors of 18", '
     'b_rule="divisors of 24")', "Some numbers divide 18, some divide 24."),
    # a line naming a different, unrelated set
    ('v = VennDiagram(universe=["1", "2", "3", "4", "5", "6"], a=["2", "4", "6"], b=["1", "2", "3"])', "The primes are 2, 3 and 5."),
])
def test_matching_or_rule_defined_sets_are_not_flagged(venn, line):
    from animation_agent.visuals.calls import check_script
    assert not [p for p in check_script([[[venn]]], [[line]]) if p.kind == "wrong_set"]


def test_a_later_venn_is_checked_against_sets_named_anywhere_in_the_script():
    """The gcd video redrew the wrong set in its recap, whose line ('divides both, like 6 for 18 and 24') names no set."""
    from animation_agent.visuals.calls import check_script
    good = ('v = VennDiagram(universe=["1", "2", "3", "4", "6", "8", "9", "12", "18", "24"], a_rule="divisors of 18", '
            'b_rule="divisors of 24")')
    bad = ('v2 = VennDiagram(universe=["1", "2", "3", "4", "6", "8", "9", "12", "18", "24"], a=["1", "2", "3", "6", "9", "18"], '
           'b=["1", "2", "3", "4", "6", "8"])')
    problems = check_script([[[good], []], [["v.remove()", bad]]],
                            [["Some numbers divide 18, some divide 24.", "Which sit in both?"],
                             ["So the gcd is the greatest number that divides both, like 6 for 18 and 24."]])
    wrong = [p for p in problems if p.kind == "wrong_set"]
    assert [(p.segment, p.beat) for p in wrong] == [(1, 1)] and "v2.b" in wrong[0].message
