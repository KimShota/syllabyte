"""The slide's own example and each step of the working said (script_generation_agent/fidelity.py)."""

from __future__ import annotations

from script_generation_agent.fidelity import SlideExample, example_problem, same_function, step_tokens, unsaid_steps

# the double integral video (runs/picture-p4): the slide's z = 1 - x^2 - y^2, the program's 2 - x^2 - y^2
VOLUME_PLAN = [[["p = Picture(program=[\"s = surface('s', x=(0, 1), y=(0, 1))\", "
                 "\"f = lambda x, y: 2 - x * x - y * y\", \"s.plot('f', f)\", \"snap('surface', name='s')\"])"],
                ["p.show(snap='s')"]]]
SLIDE = "Example: z = 1 - x2 - y2 over the unit square 0 <= x <= 1, 0 <= y <= 1; the volume is 1/3"


def test_a_plan_that_draws_another_function_than_the_slides_is_sent_back():
    p = example_problem(SlideExample(slide=3, functions=["1 - x^2 - y^2"], numbers=["1/3"], own=False),
                        VOLUME_PLAN, SLIDE)
    assert p is not None and "1 - x^2 - y^2" in p.message and "1/3 is not in the picture" in p.message


def test_a_plan_that_draws_the_slides_function_or_its_own_example_passes():
    ok = [[["p = Picture(program=[\"f = lambda x, y: 1 - x**2 - y**2\", \"s = surface('s', x=(0, 1), y=(0, 1))\", "
            "\"s.plot('f', f)\", \"snap('volume 1/3', name='s')\"])"]]]
    assert example_problem(SlideExample(slide=3, functions=["z = 1 - x^2 - y^2"], numbers=["1/3"], own=False),
                           ok, SLIDE) is None
    assert example_problem(SlideExample(slide=None, own=True), VOLUME_PLAN, SLIDE) is None


def test_a_number_the_slides_dont_have_is_caught():
    p = example_problem(SlideExample(slide=3, functions=[], numbers=["7"], own=False), VOLUME_PLAN, SLIDE)
    assert p is not None and "7 is not on the slides" in p.message


def test_functions_are_compared_by_value_and_never_run():
    import ast

    body = ast.Expression(ast.parse("2 - x * x - y * y", mode="eval").body)
    assert same_function(ast.parse("2 - x**2 - y**2", mode="eval"), ["x", "y"], ["x", "y"], body)
    assert not same_function(ast.parse("1 - x**2 - y**2", mode="eval"), ["x", "y"], ["x", "y"], body)
    evil = ast.Expression(ast.parse("__import__('os').system('true')", mode="eval").body)
    assert not same_function(ast.parse("x", mode="eval"), ["x"], ["x"], evil)  # not evaluated: refused


# the polar video (runs/picture-p2): (1 - r^2) r became r - r^3 on screen, and the line never said so
POLAR = [[["w = EquationSteps(tex=\"\\int_0^1 (1-r^2)\\,r\\,dr\")"],
          ["w.then(tex=\"\\int_0^1 (r - r^3)\\,dr = ?\")"],
          ["w.then(tex=\"\\left[\\frac{r^2}{2}-\\frac{r^4}{4}\\right]_0^1=\\frac{1}{4}\")"]]]


def test_a_step_of_the_working_its_line_doesnt_say_is_marked():
    roles = [[("explainer_build", False), ("explainer_predict", False), ("peer_build", False)]]
    lines = [["Now the integral of one minus r squared, times r.", "Pause: what does the inner integral give?",
              "It's one half minus one quarter, so one quarter."]]
    notes = unsaid_steps(POLAR, lines, roles)
    assert list(notes) == [(0, 1)] and "say the step" in notes[(0, 1)]
    said = [[lines[0][0], "Expand it: r minus r cubed. What does the inner integral give?", lines[0][2]]]
    assert unsaid_steps(POLAR, said, roles) == {}


def test_questions_objectives_and_revealing_predicts_are_not_held_to_it():
    roles = [[("peer_question", False), ("explainer_objective", False), ("peer_answer", True)]]
    assert unsaid_steps(POLAR, [["What is this?", "You'll learn it.", "Is it a half?"]], roles) == {}


def test_spoken_forms_of_numbers_fractions_and_decimals():
    tokens = step_tokens(r"\frac12-\frac14=\frac14 \quad 24 \quad 0.5 \quad x^3")
    assert "half" in tokens["1/2"] and "twenty-four" in tokens["24"] and "point five" in tokens["0.5"]
    assert "cubed" in tokens["^3"]


def test_a_fraction_written_in_tex_counts_as_its_numbers():
    plan = [[["eq = EquationSteps(tex=\"\\int_0^{\\pi/2}\\frac14 d\\theta=\\frac{\\pi}{8}\")"]]]
    decl = SlideExample(slide=3, functions=[], numbers=["1/4", "pi/8"], own=False)
    assert example_problem(decl, plan, "the inner integral is 1/4, so the area is pi/8") is None


def test_a_segment_spoken_wholly_from_the_line_cache_is_still_written(tmp_path):
    import numpy as np
    from types import SimpleNamespace

    from animation_agent import tts

    class Never:  # every line is cached, so nothing is synthesized
        def synthesize_words(self, *a, **k):
            raise AssertionError("synthesized a cached line")

    seg = SimpleNamespace(beats=[SimpleNamespace(narration="Hi there."), SimpleNamespace(narration="Bye.")])
    for text in ("Hi there.", "Bye."):
        tts._BEAT_CACHE[("Never", "v", text)] = (np.zeros(2400, dtype="float32"), 24000, [])
    out = tmp_path / "new" / "seg_0.wav"  # its folder doesn't exist yet
    durations, _words = tts._synthesize_beats(Never(), seg, out, ["v", "v"], [0.1, 0.1])
    assert out.exists() and len(durations) == 2


def test_a_handout_slide_number_finds_the_page_that_prints_it():
    # runs/p5: a 5-page handout (4 slides a page) and a KU citing slide 25 crashed the video before it started
    from syllabyte_common.models import CourseCorpus, KnowledgeUnit, Slide, SlideDeck, SlideRef
    from script_generation_agent.script_writer import gather_source_material

    pages = [Slide(deck_name="os", slide_number=i + 1, text=f"{6 * i + 1}\nslide text {i}") for i in range(5)]
    pages[4].text = "25\nExample of RR with Time Quantum = 20\nP1 53"
    corpus = CourseCorpus(course_name="OS", syllabus_path="s.pdf", syllabus_text="",
                          decks=[SlideDeck(name="os", source_path="os.pdf", slides=pages)])
    ku = KnowledgeUnit.model_construct(id="ku-rr", source_refs=[SlideRef(deck_name="os", slide_number=25)])
    text, _images = gather_source_material(corpus, ku)
    assert "Time Quantum = 20" in text and "slide text 0" not in text
    ku = KnowledgeUnit.model_construct(id="ku-x", source_refs=[SlideRef(deck_name="os", slide_number=99)])
    text, _images = gather_source_material(corpus, ku)
    assert text.count("[os — page") == 5  # nothing resolves: the short deck stands in whole


def test_a_truth_table_row_written_a_digit_a_column_is_on_the_slides():
    from script_generation_agent.fidelity import _bits_in

    assert _bits_in("011", "a b cin cout\n0 1 1 1\n")
    assert _bits_in("101", "t = grid('t', [[1, 0, 1]])")
    assert not _bits_in("011", "0110") and not _bits_in("25", "2 5")
