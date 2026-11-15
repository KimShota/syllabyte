"""Snapshot-led beats (plan/snapshot-led-beats-plan.md): the formula view, snapshots tagged with their part, the band,
and the beats built from the snapshots. No LLM calls: the planner and the writer are faked."""

from __future__ import annotations

import pytest

from animation_agent.scene import api
from animation_agent.scene.examples import GEOMETRIC
from animation_agent.scene.layout import plan as lay_out
from animation_agent.scene.sandbox import run_program
from animation_agent.visuals.calls import check_script, describe_script
from animation_agent.visuals.specs import _dialogue_area, picture_snapshots
from script_generation_agent import snapshot_beats as sb
from script_generation_agent import storyboard, storyboard_plan
from script_generation_agent.script_writer import validate_dialogue
from syllabyte_common.models import TemplatedDialogueScript
from test_storyboard import KU, REFS

PROGRAM = GEOMETRIC.strip("\n").splitlines()


@pytest.fixture(autouse=True)
def _clean_api():
    api.reset()
    yield
    api.reset()


# ---- the formula view ----------------------------------------------------------------------------------------


def test_a_formula_is_worked_one_step_at_a_time():
    f = api.formula("f")
    f.add(r"S = 1 + \frac{1}{2} S")
    f.add(r"S - \frac{1}{2} S = 1")
    f.highlight(1, r"\frac{1}{2} S", "compare")
    f.set(0, "S = 2")
    f.box(0)
    f.mark(-1, "found")
    state = f.state()
    assert state["lines"] == ["S = 2", r"S - \frac{1}{2} S = 1"]
    assert state["terms"] == {"1": [[r"\frac{1}{2} S", "compare"]]} and state["boxed"] == [0]
    assert state["styles"] == {"1": "found"}
    f.remove(0)
    assert f.state()["lines"] == [r"S - \frac{1}{2} S = 1"] and f.state()["boxed"] == []


def test_a_backslash_a_plain_string_swallowed_is_put_back():
    f = api.formula("f")
    f.add("\frac{1}{2} + \nabla f \times \beta")  # a form feed, a newline, a tab and a backspace, as a program has them
    assert f.state()["lines"] == [r"\frac{1}{2} + \nabla f \times \beta"]


def test_a_formula_too_long_to_read_or_a_term_not_in_it_is_refused():
    f = api.formula("f")
    with pytest.raises(api.PictureError, match="symbols"):
        f.add("a + b + c + d + e + f + g + h + i + j + k + l")
    f.add("a + b = c")
    with pytest.raises(api.PictureError, match="isn't in line 0"):
        f.highlight(0, "d")
    for k in range(3):
        f.add(f"x_{k} = {k}")
    with pytest.raises(api.PictureError, match="at most 4"):
        f.add("y = 1")


def test_a_formula_takes_a_band_under_the_picture():
    result = run_program(GEOMETRIC)
    assert result.ok, result.error
    layout = lay_out(result.snapshots, *_dialogue_area("full"))
    axes, formula = layout.regions["a"], layout.regions["f"]
    assert axes.top > formula.top and axes.h > formula.h  # the picture gets the room
    lay = layout.math["f"]
    for i in range(len(result.snapshots)):  # the newest two lines (or all) always show
        assert lay.end[i] - lay.start[i] >= min(2, lay.end[i])


# ---- snapshots tagged with their part -------------------------------------------------------------------------


def test_a_snapshot_records_its_part_and_whether_it_is_the_wrong_idea():
    snaps = picture_snapshots(PROGRAM)
    assert [s["part"] for s in snaps][:4] == ["prepare", "prepare", "initiate", "deliver_1"]
    assert [s["name"] for s in snaps if s["wrong"]] == ["wrong"]
    api.cells("a", [1, 2])
    with pytest.raises(api.PictureError, match="not one of"):
        api.snap("x", name="x", part="middle")


def test_the_band_passes_a_whole_videos_program():
    assert sb.band_problems(picture_snapshots(PROGRAM), 2) == []


def _snaps(parts: list[str], wrong: tuple[int, ...] = ()) -> list[dict]:
    return [{"name": f"s{k}", "caption": f"step {k}", "part": p, "wrong": k in wrong, "views": {}}
            for k, p in enumerate(parts)]


def test_the_band_says_what_is_wrong_with_a_thin_or_untagged_program():
    thin = _snaps(["prepare", "deliver_1", "deliver_1", "end"])
    problems = sb.band_problems(thin, 2)
    assert "initiate has 0 snapshots; it needs 1-2" in problems
    assert "deliver_1 has 2 snapshots; it needs 3-6" in problems and "deliver_2 has 0 snapshots; it needs 3-6" in problems
    assert any("second snapshot is the wrong idea" in p for p in problems)
    untagged = _snaps(["prepare", None, "initiate"])
    assert any("name no part" in p for p in sb.band_problems(untagged, 2))
    backwards = _snaps(["prepare", "deliver_1", "initiate"])
    assert any("out of order" in p for p in sb.band_problems(backwards, 2))
    long = _snaps(["prepare", "initiate"] + ["deliver_1"] * 6 + ["deliver_2"] * 6, wrong=(3,))
    assert any("at most 10" in p for p in sb.band_problems(long, 2))


# ---- the beats --------------------------------------------------------------------------------------------------


def _script(plan, segments) -> TemplatedDialogueScript:
    return TemplatedDialogueScript.model_validate({
        "ku_id": "x", "title": "t", "style": "dialogue", "visuals": "templates", "colour_key": [],
        "segments": [{"phase": sp.phase, "source_refs": REFS, "drawn": "templates", "beats": [
            {"narration": " ".join(["word"] * b.words[0]) + ".", "speaker": b.speaker, "step": b.step,
             "misconception": b.misconception, "draw": calls, "visual": "v"} for b, calls in zip(sp.beats, seg)]}
            for sp, seg in zip(plan, segments)]})


@pytest.mark.parametrize("level", [1, 2, 3])
def test_every_snapshot_gets_its_own_line_in_order(level):
    snaps = picture_snapshots(PROGRAM)
    plan, shown, log = sb.build_beats(snaps, level)
    assert log == []
    flat = [n for seg in shown for n in seg if n]
    assert flat == [s["name"] for s in snaps]  # every one, once, in the program's order
    assert [sp.key for sp in plan] == list(sb.PARTS) and 14 <= sum(len(sp.beats) for sp in plan) <= 18
    for sp, names in zip(plan, shown):
        for k, (beat, name) in enumerate(zip(sp.beats, names)):
            if beat.step == "predict" or (beat.step == "question" and k > 0):
                assert name is None, (sp.key, beat)  # a question past the part's first line keeps the picture
    segments = sb.calls_for(PROGRAM, shown, snaps[0]["name"])
    assert segments[0][0][0].startswith("p = Picture(program=[") and len(segments[0][0]) == 1
    assert check_script(segments, None, {"Picture"}) == []
    assert [p for p in validate_dialogue(_script(plan, segments)) if "casual" not in p and "slang" not in p] == []
    said = describe_script(segments)
    assert said[2][1] == "The diagram moves on to the wrong idea: the sums keep growing, past 2 (in shapes)."


def test_the_wrong_idea_and_the_predicted_result_go_to_their_lines():
    plan, shown, _ = sb.build_beats(picture_snapshots(PROGRAM), 2)
    d1, d2 = plan[2], plan[3]
    assert [(b.speaker, b.step, b.misconception) for b in d1.beats][:3] == [
        ("explainer", "question", False), ("peer", "answer", True), ("explainer", "feedback", False)]
    assert shown[2][:3] == ["four", "wrong", "gap"]
    assert [b.step for b in d2.beats][-2:] == ["predict", "build"] and shown[3][-2:] == [None, "total"]


def test_more_steps_make_more_build_lines_taking_turns():
    snaps = _snaps(["prepare", "initiate"] + ["deliver_1"] * 6 + ["deliver_2"] * 4 + ["end"], wrong=(3,))
    plan, shown, _ = sb.build_beats(snaps, 2)
    d1 = plan[2].beats
    assert len(d1) == 6 and [b.speaker for b in d1[3:]] == ["explainer", "peer", "explainer"]
    assert d1[-1].does == sb.LAST_BUILD
    assert len(plan[3].beats) == 6 and shown[3] == ["s8", None, "s9", "s10", None, "s11"]
    assert [p for p in validate_dialogue(_script(plan, [[[] for _ in sp.beats] for sp in plan]))
            if "casual" not in p and "slang" not in p and "visual" not in p] == []


def test_a_program_outside_the_band_is_still_built_when_the_redraw_misses_it():
    thin = _snaps(["prepare", "deliver_1", "deliver_1"])
    plan, shown, log = sb.build_beats(thin, 2)
    assert [n for seg in shown for n in seg if n] == ["s0", "s1", "s2"]
    assert [len(sp.beats) for sp in plan] == [2, 2, 3, 5, 2]  # the roles stay; their lines keep the picture
    many = _snaps(["prepare"] * 4 + ["initiate"] + ["deliver_1"] * 8 + ["deliver_2"] * 3, wrong=(5,))
    plan, shown, log = sb.build_beats(many, 2)
    assert "prepare: 2 of its 4 snapshots passed over" in log and "s3" in shown[0]  # the part's last one stays
    assert sum(len([n for n in seg if n]) for seg in shown[2:4]) <= sb.MAX_DELIVER


def test_untagged_snapshots_join_the_part_before_them():
    parts, log = sb.by_part(_snaps([None, "initiate", None, "deliver_1"]))
    assert [s["name"] for s in parts["prepare"]] == ["s0"] and [s["name"] for s in parts["initiate"]] == ["s1", "s2"]
    assert len(log) == 2


# ---- the planner ------------------------------------------------------------------------------------------------


def _board(program: list[str]):
    return sb.program_model().model_validate({
        "title": "Why the halves add up to 2", "colour_key": [{"term": "partial sums", "colour": "TEAL"}],
        "slide_example": {"slide": None, "functions": [], "numbers": [], "own": True},
        "program": program, "source_refs": REFS})


def _run(monkeypatch, programs: list[list[str]], *, lines_prefix: str = ""):
    seen = []

    def fake(**kw):
        seen.append((kw["stage"], kw["content"][0]["text"], kw["system"]))
        stage = kw["stage"]
        if stage.startswith("storyboard_program"):
            return _board(programs.pop(0))
        if stage.startswith("storyboard_write"):
            schema = kw["schema"]
            data = {}
            for key, field in schema.model_fields.items():
                seg = {"source_refs": REFS}
                for name in field.annotation.model_fields:
                    if name != "source_refs":
                        seg[name] = {"narration": lines_prefix + "Stewie, one of these lines says the step it shows."}
                data[key] = seg
            return schema.model_validate(data)
        if stage == "storyboard_lines":
            return storyboard._LineFixes(fixes=[])
        raise AssertionError(stage)

    monkeypatch.setattr(sb, "structured", fake)
    monkeypatch.setattr(storyboard_plan, "structured", fake)
    monkeypatch.setattr(storyboard, "structured", fake)
    monkeypatch.setattr("script_generation_agent.script_writer.gather_source_material", lambda c, k: ("slides", []))
    monkeypatch.setattr(storyboard_plan, "validate_dialogue", lambda s: [], raising=False)
    monkeypatch.setattr("script_generation_agent.script_writer.validate_dialogue", lambda s: [])
    monkeypatch.setenv("SYLLABYTE_STORYBOARD", "plan")
    monkeypatch.delenv("SYLLABYTE_PICTURES", raising=False)
    monkeypatch.delenv("SYLLABYTE_BEATS", raising=False)
    script = storyboard.write_storyboard(KU, None, level=2)
    return script, seen


def test_the_planner_writes_the_program_and_code_builds_the_beats(monkeypatch):
    script, seen = _run(monkeypatch, [PROGRAM])
    stages = [s for s, _, _ in seen]
    assert stages == ["storyboard_program_l2", "storyboard_write_l2", "storyboard_lines"]
    system = seen[0][2]
    assert "deliver_1 (3-6)" in system and "formula(name" in system and "p.show" not in system
    assert [len(seg.beats) for seg in script.segments] == [2, 2, 4, 5, 2]
    shows = [c for seg in script.segments for b in seg.beats for c in b.draw if ".show(" in c]
    assert shows[0] == "p.show(snap='first')" and len(shows) == 10
    write_prompt = seen[1][1]
    assert "picture: The diagram moves on to the wrong idea: the sums keep growing, past 2" in write_prompt


def test_a_program_outside_the_band_is_sent_back_once_with_the_counts(monkeypatch):
    thin = [line for line in PROGRAM if "part='deliver_2'" not in line]
    script, seen = _run(monkeypatch, [thin, PROGRAM])
    assert [s for s, _, _ in seen][:2] == ["storyboard_program_l2", "storyboard_program_l2"]
    assert "deliver_2 has 0 snapshots; it needs 3-6" in seen[1][1] and "Your previous program:" in seen[1][1]
    assert [len(seg.beats) for seg in script.segments] == [2, 2, 4, 5, 2]


def test_a_program_that_never_runs_falls_back_to_the_planned_beats(monkeypatch):
    plan = storyboard.skeleton(2)
    calls = {"n": 0}

    def fallback(*a, **k):
        calls["n"] += 1
        return None

    monkeypatch.setattr(sb, "plan_by_snapshots", fallback)
    with pytest.raises(Exception):  # the planned path then runs (its fake answers aren't given here)
        _run(monkeypatch, [])
    assert calls["n"] == 1 and len(plan) == 5


def test_the_planned_beats_can_still_be_chosen(monkeypatch):
    monkeypatch.delenv("SYLLABYTE_BEATS", raising=False)
    assert sb.beats_mode() == "snapshots"
    monkeypatch.setenv("SYLLABYTE_BEATS", "planned")
    assert sb.beats_mode() == "planned"


def test_a_broken_program_is_refused_with_its_reason():
    snaps, problems = sb.program_problems(["a = cells('a', [1, 2])", "a[5] = 3", "snap('x', part='prepare')"], 2)
    assert snaps == [] and "IndexError" in problems[0] or "index" in problems[0].lower()


def test_a_program_that_cant_be_drawn_gets_one_more_redraw_but_one_outside_the_band_doesnt(monkeypatch):
    broken = ["a = cells('a', [1, 2])", "a[5] = 3", "snap('x', part='prepare')"]
    script, seen = _run(monkeypatch, [broken, broken, PROGRAM])
    programs = [text for stage, text, _ in seen if stage.startswith("storyboard_program")]
    assert len(programs) == 3 and "Fix the program error" in programs[2]
    assert [len(seg.beats) for seg in script.segments] == [2, 2, 4, 5, 2]
    thin = [line for line in PROGRAM if "part='deliver_2'" not in line]
    script, seen = _run(monkeypatch, [thin, thin])
    programs = [text for stage, text, _ in seen if stage.startswith("storyboard_program")]
    assert len(programs) == 2 and "Make the drawing smaller" not in programs[1]  # built as it is after one
