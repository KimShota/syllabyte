"""Highlights that say what they show, and lines that say their point once. No LLM calls."""

from __future__ import annotations

from animation_agent.visuals.calls import check_script
from animation_agent.visuals.highlights import fix_highlights
from script_generation_agent import storyboard

SEL = 'arr = ArrayBars(values=[5, 2, 8, 1, 9, 3], style="bars")'
BIS = 'arr = ArrayBars(values=[1, 3, 4, 7, 9, 11, 13, 15])'
KEY = {"minimum": "ORANGE", "sorted prefix": "GREEN", "list": "BLUE"}


def _fix(draws, steps, lines, key=None):
    out, log = fix_highlights([draws], [steps], [lines], key)
    return out[0], log


def test_green_only_on_cells_the_steps_sorted_or_found():
    draws = [[SEL], ['arr.highlight(indices=[0, 1, 2], colour="GREEN")'], ["arr.selection_step()"],
             ['arr.highlight(indices=[0], colour="GREEN")']]
    out, log = _fix(draws, [("question", False), ("objective", False), ("build", False), ("build", False)],
                    ["", "You'll check the sorted prefix.", "One goes first.", "The sorted prefix holds one."])
    assert out[1] == [] and "aren't" in log[0]  # 5, 2, 8 aren't sorted
    assert out[3] == ['arr.highlight(indices=[0], colour="GREEN")']  # 1 is, after the first step
    found = [[BIS], ["arr.bisect_step(target=7)"], ['arr.highlight(indices=[3], colour="GREEN")']]
    assert _fix(found, [("build", False)] * 3, ["", "", ""])[0][2] == found[2]


def test_a_question_does_not_highlight_its_answer():
    draws = [[SEL], ["arr.selection_step()"], ['arr.highlight(indices=[1], colour="ORANGE")'],
             ['arr.highlight(indices=[1, 2, 3, 4, 5], colour="ORANGE")'], ["arr.selection_step()"]]
    steps = [("build", False), ("build", False), ("predict", False), ("question", False), ("build", False)]
    out, log = _fix(draws, steps, ["", "", "Pause: which is the minimum now?", "Which cells are left?", "Two."], KEY)
    assert out[2] == [] and "answer" in log[0]  # 2 is the next minimum
    assert out[3] == draws[3]  # the candidates may light up
    bis = [[BIS], ['arr.highlight(indices=[3], colour="GOLD")'], ["arr.bisect_check(target=13)"]]
    assert _fix(bis, [("build", False), ("predict", False), ("build", False)], ["", "Pause: the middle?", "7."])[0][1] == []


def test_off_key_colours_take_the_named_terms_colour_and_ghosts_belong_to_the_wrong_idea():
    draws = [[SEL], ['arr.highlight(indices=[3], colour="YELLOW")'], ['arr.ghost(indices=[4], text="9?")'],
             ['arr.highlight(indices=[0, 1, 2, 3], colour="YELLOW")'], ['arr.ghost(indices=[0], text="5 stays")']]
    steps = [("build", False), ("build", False), ("build", False), ("build", False), ("answer", True)]
    out, log = _fix(draws, steps, ["", "One is the minimum.", "Nine could hide there.", "The minimum is in here.",
                                   "Five stays first."], KEY)
    assert out[1] == ['arr.highlight(indices=[3], colour="ORANGE")']
    assert out[2] == ['arr.highlight(indices=[4], colour="TEAL")']  # a correct line, no wrong idea
    assert out[3] == draws[3]  # four cells: not one role, left as it is
    assert out[4] == draws[4]  # the wrong idea keeps its ghost
    assert check_script([out]) == []


def test_lines_that_correct_themselves_are_marked_for_the_line_call(monkeypatch):
    from test_storyboard import KU, example_board

    assert storyboard.self_corrects("the last four cells... wait, I mean the last three")
    assert not storyboard.self_corrects("Wait, so what happens if the middle is the target?")
    plan = storyboard.skeleton(2)
    board = example_board(plan)
    board.deliver_2.b4_explainer_predict.narration = "Pause: how many checks... I mean, how many to the end?"
    sent = []
    fixes = [storyboard._LineFix(segment_index=3, beat=4, line="Pause: how many checks, wait, I mean to the end?"),
             storyboard._LineFix(segment_index=3, beat=4, line="Pause: how many checks to reach the last cell?")]

    def fake(**kw):
        sent.append(kw["content"][0]["text"])
        return storyboard._LineFixes(fixes=fixes)

    monkeypatch.setattr(storyboard, "structured", fake)
    out = storyboard.match_lines(storyboard.assemble(board, plan, KU), ku_id="ku-x")
    assert "(corrects itself: rewrite it)" in sent[0]
    assert out.segments[3].beats[3].narration == "Pause: how many checks to reach the last cell?"


def test_two_steps_in_one_line_are_counted():
    segs = [[[SEL], ["arr.selection_step()", "arr.selection_step()"], ["arr.selection_step()"]],
            [[BIS], ["arr.bisect_check(target=7)", "arr.bisect_discard()"]]]
    assert storyboard._two_steps(segs) == [(0, 2)]


def test_green_is_left_alone_on_a_list_changed_by_hand():
    draws = [[SEL], ["arr.swap(i=0, j=3)"], ['arr.highlight(indices=[0], colour="GREEN")']]
    out, _ = _fix(draws, [("build", False)] * 3, ["", "One swaps to the front.", "Index zero holds one."])
    assert out[2] == draws[2]


def test_the_answer_rule_looks_into_later_segments_and_recolouring_never_makes_a_false_green():
    out, _ = fix_highlights([[[SEL], ['arr.highlight(indices=[3], colour="ORANGE")']], [["arr.selection_step()"]]],
                            [[("build", False), ("question", False)], [("build", False)]],
                            [["", "How does selection sort work?"], ["One goes first."]], KEY)
    assert out[0][1] == []  # 1 is what the first step, a segment later, finds
    draws = [[SEL], ['arr.highlight(indices=[0, 1], colour="TEAL")']]
    out, _ = _fix(draws, [("build", False), ("objective", False)], ["", "You'll say what the sorted prefix holds."],
                  KEY)
    assert out[1] == draws[1]  # not recoloured green (and then dropped): 5 and 2 aren't sorted
