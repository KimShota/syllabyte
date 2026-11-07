"""Plan, then write: the storyboard in two calls (storyboard_plan.py). No LLM calls: the calls are faked."""

from __future__ import annotations

from script_generation_agent import storyboard, storyboard_plan
from script_generation_agent.picture_plan import PicturePlan
from script_generation_agent.storyboard_example import SEGMENT_KEYS
from script_generation_agent.storyboard_modules import MODULES
from test_storyboard import KU, REFS

TABLE = MODULES["table"].example
PICTURE = PicturePlan(family="code_trace", also=[], reason="a loop traced row by row")


def plan_board(plan, ex=TABLE, **change):
    data = {"title": ex["title"], "colour_key": ex["colour_key"]}
    for key in SEGMENT_KEYS:
        seg = {"source_refs": REFS, "sketches": []}
        for field, draw, line in ex[key]:
            seg[field] = {"draw": list(change.get(field + "@" + key, draw)), "point": line.format(peer="Stewie")}
        data[key] = seg
    return storyboard_plan.plan_model(plan).model_validate(data)


def lines_board(plan, ex=TABLE, prefix=""):
    data = {}
    for key in SEGMENT_KEYS:
        seg = {"source_refs": REFS}
        for field, _, line in ex[key]:
            seg[field] = {"narration": prefix + line.format(peer="Stewie")}
        data[key] = seg
    return storyboard_plan.lines_model(plan).model_validate(data)


def _run(monkeypatch, answers):
    seen = []

    def fake(**kw):
        seen.append((kw["stage"], kw["content"][0]["text"], kw["system"]))
        answer = answers[kw["stage"].rsplit("_l", 1)[0] if kw["stage"].startswith("storyboard_") else kw["stage"]]
        return answer.pop(0) if isinstance(answer, list) else answer

    monkeypatch.setattr(storyboard_plan, "structured", fake)
    monkeypatch.setattr(storyboard, "structured", fake)
    monkeypatch.setattr("script_generation_agent.script_writer.gather_source_material", lambda c, k: ("slides", []))
    monkeypatch.setenv("SYLLABYTE_STORYBOARD", "plan")
    ready = []
    script = storyboard.write_storyboard(KU, None, level=2, picture=PICTURE, example=None, on_lines_ready=ready.append)
    return script, seen, ready


def test_the_picture_is_planned_then_the_lines_are_written_to_it(monkeypatch):
    plan = storyboard.skeleton(2)
    script, seen, ready = _run(monkeypatch, {
        "storyboard_plan": plan_board(plan),
        "storyboard_write": lines_board(plan),
        "storyboard_lines": storyboard._LineFixes(fixes=[]),
    })
    stages = [s for s, _, _ in seen]
    assert stages == ["storyboard_plan_l2", "storyboard_write_l2", "storyboard_lines"] and len(ready) == 1
    plan_prompt, plan_system = seen[0][1], seen[0][2]
    assert "Plan the pictures" in plan_prompt and "`point`" in plan_system and "Casual phrases" not in plan_system
    assert "Drawing this kind of picture (table)" in plan_system  # the kind's module reaches the planner
    write_prompt, write_system = seen[1][1], seen[1][2]
    assert "picture: A table, 3 rows by 3 columns" in write_prompt  # computed from the planned calls
    assert "point: Trace it: one row per pass" in write_prompt
    assert "Casual phrases" in write_system and "Template(" not in write_system  # the writer writes lines only
    assert script.segments[2].beats[2].draw == ["t.clear()", "t.fill(row=0, col=2, value=4)"]
    assert script.segments[2].beats[2].narration.startswith("No: total equals total plus x")
    assert script.segments[0].beats[0].visual.startswith("A table, 3 rows by 3 columns")


def test_lines_the_dialogue_checks_reject_are_written_once_more(monkeypatch):
    plan = storyboard.skeleton(2)
    long = lines_board(plan)
    long.deliver_1.b3_explainer_feedback.narration = "word " * 60
    script, seen, _ = _run(monkeypatch, {
        "storyboard_plan": plan_board(plan),
        "storyboard_write": [long, lines_board(plan)],
        "storyboard_lines": storyboard._LineFixes(fixes=[]),
    })
    writes = [t for s, t, _ in seen if s == "storyboard_write_l2"]
    assert len(writes) == 2 and "rejected by the automatic checker" in writes[1]
    assert "word word" not in script.segments[2].beats[2].narration


def _first_stage(monkeypatch) -> list[str]:
    stages = []

    def fake(**kw):
        stages.append(kw["stage"])
        raise RuntimeError("stop after the first call")

    monkeypatch.setattr(storyboard, "structured", fake)
    monkeypatch.setattr(storyboard_plan, "structured", fake)
    monkeypatch.setattr("script_generation_agent.script_writer.gather_source_material", lambda c, k: ("slides", []))
    try:
        storyboard.write_storyboard(KU, None, level=2, picture=PICTURE, example=None)
    except RuntimeError:
        pass
    return stages


def test_plan_then_write_is_the_default_and_one_call_can_be_chosen(monkeypatch):
    monkeypatch.delenv("SYLLABYTE_STORYBOARD", raising=False)
    assert _first_stage(monkeypatch) == ["storyboard_plan_l2"]
    monkeypatch.setenv("SYLLABYTE_STORYBOARD", "one_call")
    assert _first_stage(monkeypatch) == ["storyboard_l2"]


def test_each_call_sees_its_kind_of_example():
    plan_ex = storyboard_plan.planner_example(2, "code_trace", explainer="Peter", peer="Stewie")
    write_ex = storyboard_plan.write_example(2, "code_trace", explainer="Peter", peer="Stewie")
    assert "draw: ['t.clear()', 't.fill(row=0, col=2, value=4)']" in plan_ex  # the planner sees calls and points
    assert "point: Trace it" in plan_ex and "narration" not in plan_ex
    assert 'row 0, column "total" is filled with 4' in write_ex  # the writer sees what they draw, not the calls
    assert "line: Trace it: one row per pass" in write_ex and "draw:" not in write_ex
    assert "Linear search" in storyboard_plan.write_example(2, "array_bars", explainer="P", peer="S")


def test_a_note_is_judged_against_the_line_not_the_planners_point():
    segments = [[['t = Table(columns=["i", "x"], rows=[[1, 4]])', 't.note(text="total is four")']]]
    assert storyboard.drop_echoes(segments, [["So the total is four after one pass."]])[0][0] == [segments[0][0][0]]
    assert storyboard.drop_echoes(segments, [["One pass in, and x was four."]]) == segments
