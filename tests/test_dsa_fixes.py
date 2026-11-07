"""The four fixes from runs/dsa-trace-2's critique: no answer lit on a question line of a data structure, wrong
ideas drawn the way the line says them, steps a line names pulled onto it, and steps spread through their line.
No Manim (the timing test stubs the scene), no LLM."""

from __future__ import annotations

from types import SimpleNamespace

from animation_agent.visuals.calls import check_segment, describe_segment
from animation_agent.visuals.highlights import fix_highlights
from animation_agent.visuals.trace import Example, Op, align_steps, build_trace

BST = 't = BinaryTree(kind="bst", values=[50, 30, 70, 20, 40, 60])'


def _fix(beats, roles, lines=None):
    segments = [beats]
    lines = [lines or ["x"] * len(beats)]
    out, log = fix_highlights(segments, [roles], lines, {})
    return out[0], log


# ---- 1. Highlights on the data structures ----------------------------------------------------------------------

def test_a_question_line_does_not_light_where_the_coming_step_lands():
    beats = [[BST], ['t.highlight(values=[50, 70, 60], colour="YELLOW")'], ["t.search_step(value=60)"]]
    out, log = _fix(beats, [("build", False), ("question", False), ("feedback", False)])
    assert out[1] == [] and "lights [60, 70]" in log[0]
    beats[1] = ['t.highlight(values=[50], colour="YELLOW")']  # the root a search starts at gives nothing away
    assert _fix(beats, [("build", False), ("question", False), ("feedback", False)])[0][1] == beats[1]
    traverse = [[BST], ['t.highlight(values=[20], colour="YELLOW")'], ['t.traverse_step(order="inorder")']]
    assert _fix(traverse, [("build", False), ("predict", False), ("build", False)])[0][1] == []


def test_a_wide_highlight_is_context_unless_it_is_all_answer():
    heap = 'h = BinaryTree(kind="max_heap", values=[50, 30, 40, 10, 20, 35, 25])'
    leaves = [[heap], ['h.highlight(values=[10, 20, 35, 25], colour="YELLOW")'], ["h.push_step(value=45)"]]
    assert _fix(leaves, [("build", False), ("question", False), ("feedback", False)])[0][1] == leaves[1]
    lst = "lst = LinkedList(values=[9, 3, 7, 2, 5])"
    path = [[lst], ["lst.find_step(value=5)"], ['lst.highlight(indices=[2, 3, 4], colour="YELLOW")'],
            ["lst.find_step(value=5)"]]
    out, _ = _fix(path, [("build", False), ("build", False), ("predict", False), ("build", False)])
    assert out[2] == []  # every node it lights is one the search lands on


def test_green_is_only_for_found_and_a_stray_ghost_becomes_a_highlight():
    beats = [[BST], ["t.search(value=40)"], ['t.highlight(values=[40], colour="GREEN")'],
             ['t.highlight(values=[20, 30], colour="GREEN")'], ['t.ghost_mark(values=[50], text="50 first?")']]
    out, log = _fix(beats, [("build", False)] * 5)
    assert out[2] == beats[2]
    assert out[3] == ['t.highlight(values=[20, 30], colour="TEAL")']
    assert out[4] == ['t.highlight(values=[50], colour="TEAL")'] and len(log) == 2


# ---- 2. Wrong ideas drawn as the line says them ----------------------------------------------------------------

def test_a_wrong_turn_and_a_wrong_order_have_their_own_ghosts():
    said = describe_segment([[BST], ['t.ghost_turn(at=50, side="left", text="go left to 30?")'],
                             ['t.ghost_turn(at=70, side="right", text="under 70?")'],
                             ['t.ghost_mark(values=[50], text="50 listed first?")']])
    assert said[1] == 'A wrong idea: a red dashed arrow from 50 down its left side to 30, noted "go left to 30?".'
    assert "into the empty place" in said[2] and said[3].startswith("A wrong idea: red dashed rings round 50")
    taken = check_segment([[BST], ['t.ghost(parent=50, side="left", value=60, text="x")']])
    assert "ghost_turn(at=50" in taken[0]
    g = 'g = Graph(nodes=["s", "a", "b"], edges=[["s", "a", "4"], ["a", "b", "1"]])'
    assert check_segment([[g], ['g.ghost_mark(nodes=["a"], text="4 is final?")']]) == []
    assert check_segment([[g], ['g.ghost_mark(nodes=["z"], text="x")']])


# ---- 3. Lines ahead of the steps -------------------------------------------------------------------------------

DIJKSTRA = Example(algorithm="dijkstra", nodes=["s", "a", "b", "c"], start="s",
                   edges=[["s", "a", "4"], ["s", "b", "1"], ["b", "a", "2"], ["a", "c", "1"], ["b", "c", "5"]])
G = ('g = Graph(nodes=["s", "a", "b", "c"], edges=[["s", "a", "4"], ["s", "b", "1"], ["b", "a", "2"], '
     '["a", "c", "1"], ["b", "c", "5"]])')
STEP = 'g.dijkstra_step(start="s")'


def test_a_step_a_line_names_moves_onto_it():
    trace = build_trace(DIJKSTRA)  # s 0 (a 4, b 1); b 1 (a 3, c 6); a 3 (c 4); c 4
    segments = [[[G, STEP], [], [STEP]]]
    lines = [["We settle s first.", "Now we remove b, the closest.", "Then b's edges."]]
    roles = [[("build", False), ("build", False), ("build", False)]]
    out, log, notes = align_steps(segments, lines, roles, trace)
    assert out[0] == [[G, STEP], [STEP], []] and notes == {} and "step 2" in log[0]
    unplaced = [[[G, STEP], [STEP], []]]
    lines = [["We settle s first.", "b is settled at one.", "Then we remove a, at three."]]
    out, _, _ = align_steps(unplaced, lines, roles, trace)
    assert out[0][2] == [STEP]  # the planner never placed it: it is added where the line says it


def test_a_question_or_arithmetic_line_is_not_given_the_step():
    trace = build_trace(DIJKSTRA)
    segments = [[[G, STEP], [], [], [STEP]]]
    roles = [[("build", False), ("question", False), ("feedback", False), ("build", False)]]
    lines = [["s goes first.", "Do we remove b next?", "One plus two is three, so a drops to three.",
              "Yes, b is settled."]]
    out, _, notes = align_steps(segments, lines, roles, trace)
    assert out == segments and list(notes) == [(0, 1)]  # the question is noted, the sum is left alone
    ahead = [["s goes first. Then we remove b and a drops to three.", "Why three?", "Because b is settled at one.",
              "Right."]]
    out, _, notes = align_steps([[[G, STEP], [], [STEP], []]], ahead,
                                [[("build", False), ("question", False), ("feedback", False), ("build", False)]],
                                trace)
    assert (0, 0) in notes and "question after" in notes[(0, 0)]  # moving it would answer the question early
    wrong = [["s goes first.", "I'd remove a next."]]
    _, _, notes = align_steps([[[G, STEP], []]], wrong, [[("build", False), ("answer", True)]], trace)
    assert notes == {}  # a wrong idea names what isn't so


# ---- 4. Steps spread through their line -------------------------------------------------------------------------

def test_a_beats_steps_start_into_its_line_and_fit_it(monkeypatch):
    from animation_agent.visuals import runner

    events = []
    scene = SimpleNamespace(time=0.0, beat_durations=[8.0])

    def wait(t):
        events.append(("wait", round(t, 2)))
        scene.time += t

    scene.wait = wait
    run = runner.SpecRunner(scene)
    run.templates_of = {"t": "BinaryTree"}

    def fake_run(call, seconds, instant=False):
        events.append((call.action, round(seconds, 2)))
        scene.time += seconds

    monkeypatch.setattr(run, "_run", fake_run)
    run.beat(1, ["t.clear()", "t.search_step(value=45)", 't.highlight(values=[30])', "t.search_step(value=45)"])
    assert [e[0] for e in events] == ["clear", "wait", "search_step", "wait", "highlight", "search_step"]
    assert events[1][1] == round(2.4 - events[0][1], 2)  # the first step starts 30% into the line
    assert scene.time <= 0.8 * 8.0 + 1e-9
    events.clear()
    scene.time = 0.0
    run.beat(1, ["t.clear()", 't.highlight(values=[30])'])  # no step: as before, nothing waits
    assert [e[0] for e in events] == ["clear", "highlight"]
