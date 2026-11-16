"""Casual phrases: the list, which phrase each slot gets, putting a missing one in, and the spread over a course.
No LLM calls."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from script_generation_agent import slang, storyboard
from script_generation_agent import snapshot_beats as sb
from script_generation_agent.storyboard_example import EXAMPLES, SEGMENT_KEYS
from script_generation_agent.storyboard_modules import MODULES

KU_IDS = [f"ku-{k:02d}-some-idea" for k in range(48)]  # a course's worth


def _slots(plan):
    return [b for seg in plan for b in seg.beats if b.slang]


def _snapshot_plan(level):
    snaps = [{"name": f"s{k}", "caption": f"step {k}", "part": p, "wrong": p == "deliver_1" and k == 3, "views": {}}
             for k, p in enumerate(["prepare", "initiate", "deliver_1", "deliver_1", "deliver_1", "deliver_2",
                                    "deliver_2", "deliver_2", "end"])]
    return sb.build_beats(snaps, level)[0]


# --------------------------------------------------------------------------
# The list
# --------------------------------------------------------------------------


def test_every_phrase_has_a_known_move_and_every_move_has_three_phrases():
    for p in slang.phrases():
        assert p["moves"] and set(p["moves"]) <= set(slang.MOVES), p["phrase"]
    for move in slang.MOVES:
        assert len(slang.for_move(move)) >= 3, move


def test_each_phrase_is_found_alone_in_its_own_example():
    # no phrase contains another (find_slang would count both), and each example uses its phrase once
    for p in slang.phrases():
        assert slang.find_slang(p["phrase"]) == [p["phrase"]]
        assert slang.find_slang(p["example"]) == [p["phrase"]], p["example"]


# --------------------------------------------------------------------------
# Which phrase each slot gets
# --------------------------------------------------------------------------


def test_each_slot_gets_a_phrase_for_its_move_and_none_twice():
    moves = ["hook", "commit", "followup", "result"]
    for key in KU_IDS:
        picked = slang.pick_phrases(moves, key)
        assert len(set(picked)) == len(picked)
        assert all(p in slang.for_move(m) for p, m in zip(picked, moves))
    assert slang.pick_phrases(moves, "ku-a") == slang.pick_phrases(moves, "ku-a")  # a KU made again: the same


@pytest.mark.parametrize("make", [storyboard.skeleton, _snapshot_plan], ids=["skeleton", "snapshots"])
@pytest.mark.parametrize("level", [1, 2, 3])
def test_over_a_course_no_phrase_takes_over(make, level):
    counts = Counter(b.phrase for key in KU_IDS for b in _slots(storyboard.with_phrases(make(level), key)))
    assert len(counts) >= 10  # the old list in practice: three phrases were 89% of uses
    assert slang.overused(counts) == [], counts.most_common(3)


@pytest.mark.parametrize("make", [storyboard.skeleton, _snapshot_plan], ids=["skeleton", "snapshots"])
def test_the_slots_mark_learning_moments_not_only_questions(make):
    for level in (1, 2, 3):
        moves = [b.move for b in _slots(make(level))]
        assert moves[:2] == ["hook", "commit"] and "followup" in moves
    assert "result" in [b.move for b in _slots(make(2))]  # the peer reacting to the answer, not asking


def test_the_writer_is_told_which_phrase_goes_where():
    plan = storyboard.with_phrases(storyboard.skeleton(2), "ku-x")
    hook = plan[0].beats[0]
    assert hook.phrase and f'Casual phrase here: "{hook.phrase}"' in storyboard._describe(hook)
    assert "Casual phrase" not in storyboard._describe(plan[1].beats[1])  # the objective


def test_a_misconception_clip_gets_its_own_phrases():
    plan = storyboard.skeleton(2)
    keys = [f"ku-{k}" for k in range(20)]
    same = sum([b.phrase for b in _slots(storyboard.with_phrases(plan, k))]
               == [b.phrase for b in _slots(storyboard.with_phrases(plan, k + "focus: the wrong idea"))] for k in keys)
    assert same < len(keys)


# --------------------------------------------------------------------------
# Putting a missing phrase in
# --------------------------------------------------------------------------


def test_a_missing_phrase_goes_in_as_planned():
    add = storyboard._add_phrase
    assert add("Eight comparisons.", "that tracks", closer=True) == "Eight comparisons, that tracks."
    assert add("How does it stop?", "real question", closer=False) == "Real question, how does it stop?"
    assert add("Why eight?", "plot twist", closer=True) == "Plot twist, why eight?"  # no closer on a question
    assert add("I'd say four.", "hear me out", closer=False) == "Hear me out, I'd say four."


def test_fix_slang_uses_the_slots_phrase():
    from test_storyboard import KU, example_board

    plan = storyboard.with_phrases(storyboard.skeleton(2), "ku-x")
    script = storyboard.assemble(example_board(plan), plan, KU)
    for seg in script.segments:  # no casual phrase anywhere
        for b in seg.beats:
            for phrase in slang.find_slang(b.narration):
                b.narration = storyboard._strip(b.narration, slang._pattern(phrase)) or "Plain line here now."
    storyboard.fix_slang(script, plan)
    slots = [(b, p) for seg, sp in zip(script.segments, plan) for b, p in zip(seg.beats, sp.beats) if p.slang]
    filled = [(b, p) for b, p in slots if slang.find_slang(b.narration)]
    assert len(filled) == slang.MIN_SLANG and all(slang.has_phrase(b.narration, p.phrase) for b, p in filled)


# --------------------------------------------------------------------------
# The worked examples the writer copies, and a course's spread
# --------------------------------------------------------------------------


def _example_lines():
    examples = [example for _ku, example in EXAMPLES.values()] + [m.example for m in MODULES.values() if m.example]
    for example in examples:
        for key in SEGMENT_KEYS:
            yield from (beat[-1] for beat in example.get(key, []) if isinstance(beat[-1], str))


def test_the_examples_dont_teach_one_phrase_at_the_start_of_every_line():
    lines = [line for line in _example_lines() if slang.find_slang(line)]
    counts = slang.spread(lines)
    assert len(counts) >= 10 and counts.most_common(1)[0][1] <= len(lines) // 4
    openers = Counter(slang.find_slang(line)[0] for line in lines
                      if slang._pattern(slang.find_slang(line)[0]).match(line))
    assert len(lines) - sum(openers.values()) >= len(lines) // 4  # many inside or after the line


def test_the_spread_report_flags_a_phrase_that_takes_over(tmp_path, capsys):
    lines = ["Lowkey, why?"] * 5 + ["Bet. How?", "That tracks.", "No cap, four."]
    (tmp_path / "ku-1").mkdir()
    (tmp_path / "ku-1" / "script.json").write_text(json.dumps(
        {"segments": [{"beats": [{"narration": line} for line in lines]}]}))
    assert slang.main([str(tmp_path)]) == 1
    assert "over 15% of uses: lowkey" in capsys.readouterr().out


def test_the_writers_beats_and_example_name_the_phrase():
    from script_generation_agent.storyboard_plan import beats_listing, write_example
    from test_storyboard import KU, example_board

    plan = storyboard.with_phrases(storyboard.skeleton(2), "ku-x")
    script = storyboard.assemble(example_board(plan), plan, KU)
    listing = beats_listing(script, plan, [[] for _ in plan])
    assert all(f'casual phrase: "{b.phrase}"' in listing for b in _slots(plan))
    example = write_example(2, None, explainer="Peter", peer="Stewie")
    assert example.count("casual phrase:") == sum(bool(slang.find_slang(line)) for line in example.splitlines()
                                                  if line.strip().startswith("line:"))


def test_a_slot_using_another_phrase_is_logged_not_rewritten():
    from test_storyboard import KU, example_board

    plan = storyboard.with_phrases(storyboard.skeleton(2), "ku-x")
    script = storyboard.assemble(example_board(plan), plan, KU)
    hook = script.segments[0].beats[0]
    other = next(p for p in slang.for_move("hook") if p != plan[0].beats[0].phrase)
    hook.narration = storyboard._add_phrase("How does a program find one number?", other, closer=False)
    before = hook.narration
    assert any("but uses" in line for line in storyboard.fix_slang(script, plan)) and hook.narration == before


# --------------------------------------------------------------------------
# Never cheering a wrong answer
# --------------------------------------------------------------------------


def test_only_the_it_adds_up_phrases_affirm():
    assert set(slang.affirming("Eight. That tracks, the math is mathing, it clicked.")) == {
        "that tracks", "the math is mathing", "it clicked"}
    assert slang.affirming("Hear me out, I'm calling it: four. Plot twist.") == []
    assert all(p in slang.for_move("result") for p in slang.affirming("That tracks. Hits different."))


@pytest.mark.parametrize("line, picture, wrong", [
    # runs/slang2, ku-dfa-intro: the peer's result contradicted the picture and ended "The math is mathing."
    ("A zero takes q2 to q3 and the one keeps us in q3. We end in q3, accept. The math is mathing.",
     "The diagram moves on to 00101 ends in q2: reject (in shapes).", True),
    ("We end in q2, so it's rejected. The math is mathing.", "The diagram moves on to 00101 ends in q2: reject.", False),
    ("X bar is 0.34. That tracks.", "x bar = 0.34, left of 0.424", False),
    ("X bar is 0.42. That tracks.", "x bar = 0.34", True),
    ("Eight comparisons. That tracks.", "eight comparisons: 1, 3, 4, 7, 9, 11, 12, 15 checked", False),
    ("Seven comparisons. That tracks.", "8 comparisons", True),
    ("It's stable now. It clicked.", "the system is unstable", True),
    ("Minus one! So y flips. The math is mathing.", "y = (1, -1) goes to (-1, 1): eigenvalue -1", False),
])
def test_a_line_whose_answer_isnt_its_pictures_is_caught(line, picture, wrong):
    assert (storyboard.disagrees(line, picture) is not None) == wrong


def _dfa_script(result_line: str, picture: str):
    from test_storyboard import KU, example_board

    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)
    k = next(i for i, b in enumerate(plan[3].beats) if b.move == "result")
    script.segments[3].beats[k].narration = result_line
    said = [[""] * len(seg.beats) for seg in script.segments]
    said[3][k] = picture
    return script, said, (3, k)


def test_a_cheer_on_a_result_the_picture_contradicts_is_taken_out():
    script, said, (s, k) = _dfa_script("We end in q3, so 00101 is accepted. The math is mathing.",
                                       "00101 ends in q2: reject")
    log = storyboard.drop_false_cheers(script, said)
    assert script.segments[s].beats[k].narration == "We end in q3, so 00101 is accepted."
    assert len(log) == 1 and "accept" in log[0]
    right, said, (s, k) = _dfa_script("We end in q2, so 00101 is rejected. The math is mathing.",
                                      "00101 ends in q2: reject")
    assert storyboard.drop_false_cheers(right, said) == []
    assert right.segments[s].beats[k].narration.endswith("The math is mathing.")


def test_a_cheer_on_the_wrong_idea_or_a_corrected_line_is_taken_out():
    from test_storyboard import KU, example_board

    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)
    wrong = script.segments[2].beats[1]  # the wrong idea
    wrong.narration = "Just one: we jump straight to seven. That tracks."
    k = next(i for i, b in enumerate(plan[3].beats) if b.move == "result")
    result, after = script.segments[3].beats[k], script.segments[3].beats[k + 1]
    result.narration = "It takes four checks. It clicked."
    after.narration = "Not quite: it takes five, one per cell up to seven."
    log = storyboard.fix_slang(script, plan)
    assert wrong.narration == "Just one: we jump straight to seven."
    assert result.narration == "It takes four checks."
    assert sum("cheered a wrong answer" in line for line in log) == 2


def test_the_checker_rejects_a_cheer_on_the_wrong_idea():
    from script_generation_agent.script_writer import validate_dialogue
    from test_storyboard import KU, example_board

    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)
    script.segments[2].beats[1].narration = "That tracks: we jump straight to seven."
    assert any("cheers it" in p for p in validate_dialogue(script))
