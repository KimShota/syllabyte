"""Trace-first worked examples, and the order the storyboard settles its picture and matches its lines in. No LLM
calls."""

from __future__ import annotations

from animation_agent.visuals.calls import check_script
from animation_agent.visuals.trace import Example, apply_trace, build_trace, trace_brief
from script_generation_agent import storyboard
from script_generation_agent.picture_plan import PicturePlan

BISECT = Example(algorithm="bisection", values=[1, 3, 4, 7, 9, 11, 13, 15], target=13)
CREATE = 'arr = ArrayBars(values=[1, 3, 4, 7, 9, 11, 13, 15], title="sorted list")'


def test_code_computes_every_step_of_the_example():
    trace = build_trace(BISECT)
    assert trace.steps == [".bisect_check(target=13)", ".bisect_discard()"] * 3
    assert "the middle value 7 is compared with the target 13" in trace.said[0]
    assert trace.said[-1].startswith("13 is the target")
    assert "1. Lo, mid, hi point at the cells holding 1, 7, 15" in trace_brief(trace)


def test_an_example_that_does_not_fit_is_not_traced():
    assert build_trace(Example(algorithm="bisection", values=[5, 1, 3], target=3)) is None  # not sorted
    assert build_trace(Example(algorithm="linear_search", values=[1, 2, 3])) is None  # no target
    assert build_trace(Example(algorithm="selection_sort", values=list(range(12, 0, -1)))) is None  # too many cells
    assert build_trace(Example(algorithm="none")) is None
    for algorithm in ("bubble_sort", "selection_sort", "insertion_sort", "merge_sort"):
        assert build_trace(Example(algorithm=algorithm, values=[5, 2, 4, 1, 3])) is not None
    assert build_trace(Example(algorithm="merge", runs=[[1, 5, 9], [2, 3, 7]])) is not None


def test_next_step_expands_into_the_computed_steps_in_order():
    trace = build_trace(BISECT)
    segments = [[[CREATE], ["arr.next_step()"], ["arr.next_step()", "arr.highlight(indices=[4])"]],
                [["arr.next_step(count=2)"]]]
    out, _, problems = apply_trace(segments, trace)
    assert out == [[[CREATE], ["arr.bisect_check(target=13)"], ["arr.bisect_discard()", "arr.highlight(indices=[4])"]],
                   [["arr.bisect_check(target=13)", "arr.bisect_discard()"]]]
    assert problems == [] and check_script(out) == []


def test_steps_off_the_example_are_brought_onto_it_and_reported():
    trace = build_trace(BISECT)
    segments = [[[CREATE], ["arr.bisect_check(target=9)"], ["other.next_step()"]]]
    out, _, problems = apply_trace(segments, trace)
    assert out[0][1] == ["arr.bisect_check(target=13)"]  # its own search for 9 would restart the story
    assert out[0][2] == []
    assert [b for _, b, _ in problems] == [2, 3] and "computed" in problems[0][2]
    past = [[[CREATE], ["arr.next_step(count=3)"], ["arr.next_step(count=3)"], ["arr.next_step()"]]]
    out, _, problems = apply_trace(past, trace)
    assert sum(len(c) for c in out[0]) == 1 + 6 and "all shown already" in problems[0][2]
    _, _, problems = apply_trace([[['arr = ArrayBars(values=[2, 4, 6])'], ['arr.highlight(indices=[0])']]], trace)
    assert "never created" in problems[0][2]


def test_a_draft_off_the_example_is_written_again_with_the_steps(monkeypatch):
    from test_storyboard import KU, example_board

    trace = build_trace(Example(algorithm="linear_search", values=[4, 9, 2, 7, 5, 1], target=7))
    sent = []

    def fake(**kw):
        if kw["stage"] == "storyboard_lines":
            return storyboard._LineFixes(fixes=[])
        if kw["stage"] == "storyboard_fix":
            raise RuntimeError("no network in tests")
        sent.append(kw["content"][0]["text"])
        return example_board()  # the worked example runs its own scans, for 7 and then for 1

    monkeypatch.setattr(storyboard, "structured", fake)
    monkeypatch.setattr("script_generation_agent.script_writer.gather_source_material", lambda c, k: ("slides", []))
    picture = PicturePlan(family="array_bars", also=[], reason="a list searched cell by cell")
    script = storyboard.write_storyboard(KU, None, level=2, picture=picture, example=trace)
    assert len(sent) == 2 and "The worked example" in sent[0] and "next_step" in sent[1]
    draws = [c for seg in script.segments for b in seg.beats for c in b.draw]
    assert [c for c in draws if ".scan(" in c] == [f"lst.scan(index={i}, target=7)" for i in range(4)]


def test_the_picture_is_settled_before_the_lines_are_matched(monkeypatch):
    from test_storyboard import KU, example_board

    order = []
    real_settle = storyboard.settle_picture

    def settle(*a, **kw):
        order.append("settle")
        return real_settle(*a, **kw)

    def fake(**kw):
        order.append(kw["stage"])
        if kw["stage"] == "storyboard_lines":
            return storyboard._LineFixes(fixes=[])
        return example_board()

    monkeypatch.setattr(storyboard, "settle_picture", settle)
    monkeypatch.setattr(storyboard, "structured", fake)
    monkeypatch.setattr("script_generation_agent.script_writer.gather_source_material", lambda c, k: ("slides", []))
    picture = PicturePlan(family="array_bars", also=[], reason="a list searched cell by cell")
    storyboard.write_storyboard(KU, None, level=2, picture=picture, example=None,
                                on_lines_ready=lambda s: order.append("voices"))
    assert order == ["storyboard_l2", "settle", "storyboard_lines", "voices"]


def test_the_lines_call_reads_the_settled_picture(monkeypatch):
    from test_storyboard import KU, example_board

    sent = []

    def fake(**kw):
        sent.append(kw["content"][0]["text"])
        return storyboard._LineFixes(fixes=[])

    monkeypatch.setattr(storyboard, "structured", fake)
    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)
    segments = storyboard.settle_picture(script, ku_id="ku-x")
    segments[2][4] = ['lst.highlight(indices=[1], colour="TEAL")']  # as if the fix call had changed it
    storyboard.match_lines(script, ku_id="ku-x", segments=segments)
    assert "picture: The cell holding 9 turns teal." in sent[0]


def test_the_fix_call_cannot_change_the_examples_steps():
    from animation_agent.visuals.trace import keep_steps

    trace = build_trace(BISECT)
    before = [[[CREATE], ["arr.note(text=\"why?\")"]],
              [["arr.bisect_check(target=13)"], ["arr.bisect_discard()"], ['arr.highlight(indices=[2])']]]
    after = [[[CREATE], ["arr.bisect_check(target=13)", "arr.bisect_discard()"]],  # ran its own steps
             [["arr.bisect_check(target=13)", "arr.point(name=\"p\", index=3)"], [],  # dropped the discard
              ["arr.restore()", "arr.bisect_step(target=15)"]]]  # restarted the search
    out, log = keep_steps(before, after, trace)
    assert out == [[[CREATE], []],
                   [["arr.bisect_check(target=13)", "arr.point(name=\"p\", index=3)"], ["arr.bisect_discard()"], []]]
    assert len(log) == 3
