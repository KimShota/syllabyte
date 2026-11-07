"""The right picture for each idea (plan/one-shot-storyboard-plan.md, "Pictures that fit"): code picks the templates,
computes the algorithms, and keeps a question or predict line from showing its answer. No LLM calls."""

from __future__ import annotations

import random

import pytest

from animation_agent.visuals.calls import check_script, check_segment, describe_segment, parse_call
from animation_agent.visuals.families import DRAWN_BY, FAMILIES, templates_for
from animation_agent.visuals.normalize import hold_reveals, normalize_script
from animation_agent.visuals.specs import (
    REGISTRY,
    bfs_new,
    bfs_next,
    dfs_new,
    dfs_next,
    graph_adjacency,
    ms_merge,
    ms_new,
    ms_split,
    parse_fn,
    sort_events,
)
from script_generation_agent.picture_plan import PicturePlan
from script_generation_agent.prompts import picture_brief, storyboard_system_prompt

# --------------------------------------------------------------------------
# Algorithms are computed, so the picture is always what they really do
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["bubble", "selection", "insertion"])
def test_every_sort_ends_sorted_and_counts_comparisons(kind):
    rng = random.Random(1)
    for _ in range(50):
        values = [rng.randint(0, 9) for _ in range(rng.randint(2, 8))]
        row, sort, steps = list(values), None, 0
        while sort is None or not sort["done"]:
            sort, events = sort_events(row, sort, kind)
            steps += len(events)
            assert steps < 100
        assert row == sorted(values)
        assert sort["comparisons"] <= len(values) * (len(values) - 1) // 2


def test_bubble_marks_the_largest_in_place_at_the_end_of_a_pass():
    row = [3, 5, 2, 6, 4]
    sort, events = sort_events(row, None, "bubble", whole_pass=True)
    assert row == [3, 2, 5, 4, 6] and events[-1]["pass_done"] and events[-1]["placed"] == [4]


def test_a_sort_step_reads_what_it_did():
    draws = [["a = ArrayBars(values=[3, 1, 2])"], ["a.selection_step()"]]
    assert check_segment(draws) == []
    said = describe_segment(draws)[1]
    assert "smallest unsorted value, 1" in said and "row reads 1, 3, 2" in said


def test_merge_sort_counts_its_comparisons():
    st = ms_new([5, 2, 4, 7, 1, 3, 8, 6], None)
    while ms_split(st) is None:
        pass
    while not isinstance(events := ms_merge(st, whole_level=True), str):
        assert events
    assert st["values"] == [1, 2, 3, 4, 5, 6, 7, 8] and st["comparisons"] == 16


def test_merging_needs_sorted_runs():
    draws = [["ms = MergeSort(values=[5, 2, 4, 7])"], ["ms.split()", "ms.merge_step()"]]
    assert any("isn't sorted" in p for p in check_segment(draws))
    two = [["ms = MergeSort(runs=[[1, 5, 12], [2, 3, 17]])"], ["ms.merge()"]]
    assert check_segment(two) == [] and "1, 2, 3, 5, 12, 17" in describe_segment(two)[1]


def test_dfs_and_bfs_follow_the_algorithm():
    adj = graph_adjacency(["s", "a", "b", "c", "d"], [["s", "a"], ["s", "b"], ["a", "c"], ["b", "c"], ["c", "d"]],
                          directed=False)
    st, order = dfs_new("s"), []
    while not st["done"]:
        if (ev := dfs_next(adj, st))["visit"]:
            order.append(ev["visit"])
    assert order == ["s", "a", "c", "b", "d"]
    st, levels = bfs_new("s"), []
    while not st["done"]:
        if (ev := bfs_next(adj, st))["level"] is not None:
            levels.append(ev["nodes"])
    assert levels == [["s"], ["a", "b"], ["c"], ["d"]]


def test_a_graph_lesson_cannot_draw_an_edge_that_is_not_there():
    draws = [['g = Graph(nodes=["s", "a"], edges=[["s", "a"]])'], ['g.path(nodes=["a", "s", "a", "b"])']]
    assert any("no node 'b'" in p for p in check_segment(draws))


@pytest.mark.parametrize("expr", ["__import__('os')", "x.real", "open('f')", "[x]", "lambda: 1", "x if x else 1"])
def test_a_formula_is_parsed_never_run(expr):
    with pytest.raises(ValueError):
        parse_fn(expr)


def test_plot_values_are_computed():
    draws = [['p = FunctionPlot(x_range=[0, 4], y_range=[0, 5], curves=[{"name": "L", "fn": "4*x - x^2"}])'],
             ['p.tangent(curve="L", x=1)', 'p.peak(curve="L")', 'p.shade(curve="L", a=0, b=3)']]
    assert check_segment(draws) == []
    said = describe_segment(draws)[1]
    assert "slope 2" in said and "x = 2, L = 4" in said and "about 9" in said


def test_a_point_off_the_axes_is_rejected():
    peak = [['p = FunctionPlot(x_range=[0, 4], y_range=[0, 10], curves=[{"name": "f", "fn": "x^2"}])'],
            ['p.peak(curve="f")']]
    assert any("off the axes" in p for p in check_segment(peak))  # x^2 reaches 16 at x = 4
    curve = [['p = FunctionPlot(x_range=[0, 10], y_range=[0, 5], curves=[{"name": "g", "fn": "x^3"}])']]
    assert any("off the axes" in p for p in check_segment(curve))  # on the axes for under a fifth of x


# --------------------------------------------------------------------------
# Code picks the templates
# --------------------------------------------------------------------------


def test_every_template_draws_a_family_and_every_drawn_family_has_a_template():
    drawn = {t for names in DRAWN_BY.values() for t in names}
    assert drawn == set(REGISTRY)
    assert set(DRAWN_BY) <= set(FAMILIES)


def test_a_dfs_lesson_gets_the_graph_not_the_list():
    plan = PicturePlan(family="graph", also=["equation_steps"], reason="DFS on a graph")
    assert plan.templates == ["Graph", "EquationSteps", "Note"] and plan.main == "Graph"
    system = storyboard_system_prompt(2, None, explainer="P", peer="S", lexicon="-", example="",
                                      templates=plan.templates, family=plan.family)
    assert "Graph(" in system and "ArrayBars(" not in system and "LinearMap2D(" not in system
    assert "main picture is graphs" in system


def test_a_missing_template_is_said_and_nothing_is_borrowed():
    assert templates_for("probability") == ["EquationSteps", "Note"]
    brief = picture_brief("probability", templates_for("probability"))
    assert "No template draws" in brief and "wrong picture" in brief


def test_a_template_the_plan_did_not_choose_is_rejected():
    segments = [[['a = ArrayBars(values=[1, 2, 3])']]]
    problems = check_script(segments, allowed={"Graph", "EquationSteps", "Note"})
    assert [p.kind for p in problems] == ["wrong_template"]


def test_finish_asks_for_the_main_picture_when_it_is_missing(monkeypatch):
    from script_generation_agent import storyboard
    from test_storyboard import KU, example_board

    sent = []

    def fake(**kw):
        sent.append(kw["content"][0]["text"])
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(storyboard, "structured", fake)
    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)  # linear search, drawn with ArrayBars
    storyboard.finish(script, ku_id="ku-x", allowed={"ArrayBars", "Graph", "EquationSteps", "Note"}, main="Graph")
    assert sent and "no segment draws Graph" in sent[0]


# --------------------------------------------------------------------------
# A question or predict line doesn't show its answer; a highlight shows what the line names
# --------------------------------------------------------------------------


def test_a_result_moves_from_the_predict_line_to_the_answer():
    segments = [[['a = ArrayBars(values=[4, 9, 2, 7])'],
                 ['a.scan(index=0, target=7)', 'a.scan(index=3, target=7)'],
                 ['a.note(text="4 checks")']]]
    steps = [[("build", False), ("predict", False), ("build", False)]]
    out, log = hold_reveals(segments, steps)
    assert out[0][1] == ["a.scan(index=0, target=7)"]  # a scan that misses gives nothing away
    assert out[0][2] == ["a.scan(index=3, target=7)", 'a.note(text="4 checks")'] and log


def test_the_wrong_idea_line_never_gets_the_answer():
    segments = [[['g = LinearMap2D(matrix=[[2, 0], [0, 1]])'], ["g.apply()"], [], ["g.reset()"]]]
    steps = [[("build", False), ("question", False), ("answer", True), ("feedback", False)]]
    out, _ = hold_reveals(segments, steps)
    assert out[0][1] == [] and out[0][2] == [] and out[0][3] == ["g.apply()", "g.reset()"]


def test_a_highlight_the_line_never_names_is_dropped():
    segments = [[['a = ArrayBars(values=[4, 9, 2, 7])'], ['a.highlight(indices=[1])'], ['a.highlight(indices=[2])']]]
    lines = [["Here is a list.", "You'll be able to count checks.", "Two is the one we want."]]
    fixed = normalize_script(segments, lines)
    calls = [c for beat in fixed.segments[0] for c in beat]
    assert not any("indices=[1]" in c for c in calls) and any("indices=[2]" in c for c in calls)


def test_reveal_flags_are_declared_for_results():
    for name, action in (("ArrayBars", "found"), ("ArrayBars", "bubble_step"), ("MergeSort", "merge_step"),
                         ("Graph", "dfs_step"), ("FunctionPlot", "peak"), ("LinearMap2D", "apply"),
                         ("EquationSteps", "uncover")):
        assert REGISTRY[name].all_actions()[action].reveals, (name, action)
    assert not REGISTRY["ArrayBars"].all_actions()["highlight"].reveals
    assert parse_call('a.highlight(indices=[0])', {"a": "ArrayBars"}).action == "highlight"


# --------------------------------------------------------------------------
# The numbers a line says are on screen, and a merge line compares the fronts the picture compares
# --------------------------------------------------------------------------

MERGE = ['ms = MergeSort(runs=[[1, 5, 6, 8, 9], [2, 3, 4, 7]])']


def _kinds(draws, lines):
    return [(p.kind, p.beat) for p in check_script([draws], [lines])
            if p.kind in ("unshown_number", "wrong_front")]


def test_a_line_naming_numbers_the_picture_lacks_is_flagged():
    # runs/course-test-2: the fix call drew smaller numbers, and the lines kept the slide's
    draws = [MERGE, ["ms.merge_step()"], ["ms.merge()"]]
    lines = ["Two sorted lists.", "Twelve beats seventeen, so twelve moves.", "Copy eighteen, nineteen, twenty."]
    assert _kinds(draws, lines) == [("unshown_number", 2), ("unshown_number", 3)]


@pytest.mark.parametrize("line", [
    "That took twelve comparisons in all.",  # a count
    "Four plus six is ten, halved is five.",  # working something out
    "Two lists, and the first one is longer.",  # small numbers: counts, positions
    "In 1945 von Neumann wrote it down.",  # a year
    "Now search for 15.",  # a target the picture draws later in the segment
])
def test_numbers_that_are_not_values_pass(line):
    draws = [['a = ArrayBars(values=[1, 3, 4, 6, 8, 9, 12])'], [], ['a.scan(index=6, target=15)']]
    assert _kinds(draws, ["A sorted list.", line, "Every cell checked."]) == []


def test_a_merge_line_compares_the_fronts_on_screen():
    draws = [MERGE, [], ["ms.merge_step()"], ["ms.merge_step()"], []]
    lines = ["Two sorted lists.",
             "The result holds one. Now we compare five and two.",  # nothing has moved: the fronts are 1 and 2
             "One is smaller than two, so one moves.",
             "Two beats five, so two moves.",
             "We compared one and two, then five and two."]  # a recap of this segment's steps
    assert _kinds(draws, lines) == [("wrong_front", 2)]


def test_a_merge_step_that_sets_up_the_question_stays_in_it():
    segments = [[MERGE, ["ms.merge_step()"], ["ms.merge_step()"]]]
    steps = [[("build", False), ("question", False), ("answer", False)]]
    lines = [["Two lists.", "The result holds one. Now we compare five and two. Which moves?",
              "Two is smaller than five, so two moves."]]
    out, log = hold_reveals(segments, steps, lines)
    assert out == segments and "kept" in log[0]
    out, _ = hold_reveals(segments, steps)  # without the lines it would move, and the line would run ahead
    assert out[0][1] == []


def _board_with_line(segment: str, field: str, line: str):
    from test_storyboard import example_board

    board = example_board()
    beat = getattr(getattr(board, segment), field)
    beat.narration = line
    return board


def test_a_storyboard_whose_lines_and_picture_disagree_is_written_again(monkeypatch):
    from script_generation_agent import storyboard
    from test_storyboard import KU, example_board

    sent = []
    boards = [_board_with_line("deliver_1", "b5_explainer_build", "Right, not seventeen: seven matched after four checks."),
              example_board()]

    def fake(**kw):
        sent.append(kw["content"][0]["text"])
        return boards[len(sent) - 1]

    monkeypatch.setattr(storyboard, "structured", fake)
    monkeypatch.setattr("script_generation_agent.script_writer.gather_source_material", lambda c, k: ("slides", []))
    picture = PicturePlan(family="array_bars", also=[], reason="a list searched cell by cell")
    script = storyboard.write_storyboard(KU, None, level=2, picture=picture)
    assert len(sent) == 2 and "lines and the pictures disagree" in sent[1] and "17" in sent[1]
    assert "seventeen" not in " ".join(b.narration for s in script.segments for b in s.beats)


def test_the_first_draft_is_kept_when_the_redo_breaks_the_dialogue(monkeypatch):
    from script_generation_agent import script_writer, storyboard
    from test_storyboard import KU

    first = _board_with_line("deliver_1", "b5_explainer_build", "Right, not seventeen: seven matched after four checks.")
    calls = []

    def fake(**kw):
        if kw["stage"] == "storyboard_fix":  # the line left over still goes to the fix call
            raise RuntimeError("no network in tests")
        calls.append(1)
        return first

    monkeypatch.setattr(storyboard, "structured", fake)
    monkeypatch.setattr(script_writer, "gather_source_material", lambda c, k: ("slides", []))
    real = script_writer.validate_dialogue
    monkeypatch.setattr(script_writer, "validate_dialogue",
                        lambda s: real(s) if len(calls) == 1 else ["segment 2 is too short"])
    picture = PicturePlan(family="array_bars", also=[], reason="a list searched cell by cell")
    script = storyboard.write_storyboard(KU, None, level=2, picture=picture)
    assert len(calls) == 2 and "seventeen" in " ".join(b.narration for s in script.segments for b in s.beats)


# --------------------------------------------------------------------------
# A line that makes a point changes the picture
# --------------------------------------------------------------------------


def test_a_still_point_line_naming_cells_gets_them_highlighted():
    from animation_agent.visuals.normalize import fill_still

    segments = [[['a = ArrayBars(values=[4, 9, 2, 7])'], [], [], []]]
    steps = [[("build", False), ("question", False), ("feedback", False), ("check", False)]]
    lines = [["A list.", "Where is seven?", "Seven sits after nine, in the last cell.", "So we check two lists."]]
    out, log = fill_still(segments, steps, lines)
    assert out[0][1] == []  # a question may keep the picture
    assert out[0][2] == ["a.highlight(indices=[1, 3])"] and log
    assert out[0][3] == []  # "two lists" is a count, not a cell


def test_a_still_point_line_goes_to_the_fix_call_and_a_note_only_one_is_kept_for_it(monkeypatch):
    from script_generation_agent import storyboard
    from test_storyboard import KU, example_board

    sent = []

    def fake(**kw):
        sent.append(kw["content"][0]["text"])
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(storyboard, "structured", fake)
    plan = storyboard.skeleton(2)
    board = example_board(plan)
    board.deliver_2.b6_explainer_build.draw = []  # "Yes, six checks for six cells: ..." names no cell
    board.end.b2_explainer_check.draw = ['q = Note(text="every cell")']
    board.initiate.b1_peer_question.draw = ['q = Note(text="why care?")']
    storyboard.finish(storyboard.assemble(board, plan, KU), ku_id="ku-x")
    assert sent and "segment 3: beat 6: the line makes a point" in sent[0]
    assert "segment 4: beat 2: its calls only put text on screen" in sent[0]
    assert "segment 1: beat 1" not in sent[0]  # a question with a note is cleared by code, as before


def test_the_examples_never_keep_the_picture_on_a_point_line():
    from animation_agent.visuals.calls import script_segments
    from animation_agent.visuals.normalize import still_beats
    from script_generation_agent import storyboard
    from test_storyboard import KU, example_board

    for level in (1, 2, 3):
        plan = storyboard.skeleton(level)
        script = storyboard.assemble(example_board(plan, level), plan, KU)
        steps = [[(b.step, b.misconception) for b in seg.beats] for seg in script.segments]
        assert still_beats(script_segments(script), steps) == [], level
