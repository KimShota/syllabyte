"""Hand-written facts in templates are checked where they can be computed: formula lines, number-line labels and
jumps, formula-headed table columns, probability bars. Each check rejects only what it can prove wrong."""
import pytest
from pydantic import ValidationError

from animation_agent.visuals.arith import evaluate, false_relation, matches
from animation_agent.visuals.calls import check_script, check_segment
from animation_agent.visuals.specs import BarParams, NumberLineParams, TableParams, table_column_problem


@pytest.mark.parametrize("tex", [
    r"\gcd(18, 24) = 6", r"2^{10} = 1024", r"\binom{5}{2} = 10", r"\frac{1}{2} + \frac{1}{3} = \frac{5}{6}",
    r"\sqrt{2} = 1.414", r"\frac{2}{3} = 0.67", r"\frac{2}{3} = 0.66", r"17 \equiv 2 \pmod{5}", r"5! = 120",
    r"\log_2 1024 = 10", r"\operatorname{lcm}(4, 6) = 12", r"\text{lcm}(4, 6) = 12", r"1\,000 = 10^3",
    r"\left(\frac{1}{2}\right)^2 = \frac{1}{4}", r"\lfloor 7/2 \rfloor = 3", r"3 \cdot 4 = 12 \Rightarrow 12 \bmod 5 = 2",
    r"65^{1/3}=[64(1+\frac{1}{64})]^{1/3}",
    # not closed numeric statements: left alone
    r"T(n) = 2T(n/2) + n", r"A v = \lambda v", r"x = 5", r"\sum_{i=1}^{10} i = 55", r"\pi \approx 3",
    r"\log 8 = 3", r"2 = 17 \bmod 5 + 0", r"f'(x) = \frac{1}{3}x^{-2/3}", r"O(n^2)",
])
def test_true_or_unknown_formulas_pass(tex):
    assert false_relation(tex) is None


@pytest.mark.parametrize("tex, says", [
    (r"\gcd(18, 24) = 4", r"\gcd(18, 24) is 6, not 4"),
    (r"2^{10} = 1000", "is 1024, not 1000"),
    (r"x = 2 + 3 = 6", "2 + 3 is 5, not 6"),
    (r"\sqrt{2} = 1.5", "not 1.5"),
    (r"17 \equiv 3 \pmod{5}", "remainders 2 and 3"),
    (r"1 + 2 + 4 + 8 = 16", "is 15"),
    (r"\boxed{\gcd(48, 18) = 7}", "is 6, not 7"),
    (r"\frac{1}{2} = \frac{2}{3}", "but"),
    (r"2 < 1", "doesn't hold"),
])
def test_false_formulas_are_found(tex, says):
    assert says in (false_relation(tex) or "")


def test_a_rounded_decimal_matches_but_a_wrong_one_does_not():
    assert matches(evaluate("2/3"), "0.67") and matches(evaluate("2/3"), "0.66")
    assert not matches(evaluate("2/3"), "0.65")
    assert evaluate("n log n", {"n": 8}, log_base=2) == 24 and evaluate("2n", {"n": 3}) == 6


def test_a_false_formula_left_on_screen_is_a_problem():
    problems = check_script([[['eq = EquationSteps(tex="\\\\gcd(18, 24) = 4")'], ['eq.box()']]])
    assert [p.kind for p in problems] == ["false_formula"] and problems[0].beat == 1
    assert "cross_out()" in problems[0].message


@pytest.mark.parametrize("beats", [
    # a deliberate wrong step, crossed out in the same beat or the next
    [['eq = EquationSteps(tex="x")'], ['eq.then(tex="(64+1)^{1/3} = 64^{1/3} + 1")', 'eq.cross_out()']],
    [['eq = EquationSteps(tex="(64+1)^{1/3} = 64^{1/3} + 1")'], ['eq.cross_out()']],
    # or corrected on screen
    [['eq = EquationSteps(tex="2 + 2 = 5")'], ['eq.rewrite(tex="2 + 2 = 4")']],
])
def test_a_wrong_step_crossed_out_or_rewritten_is_fine(beats):
    assert check_script([beats]) == []


def test_a_false_line_written_later_and_kept_to_the_end_is_found():
    problems = check_script([[['eq = EquationSteps(tex="x = 3")'], ['eq.then(tex="x^2 = 9")', 'eq.then(tex="3^2 = 6")']]])
    assert [(p.kind, p.beat) for p in problems] == [("false_formula", 2)]
    assert "3^2 is 9, not 6" in problems[0].message


def test_a_crossed_out_line_far_too_late_is_still_found():
    beats = [['eq = EquationSteps(tex="2 + 2 = 5")'], ['eq.note(text="hmm")'], ['eq.note(text="so")'], ['eq.cross_out()']]
    assert [p.kind for p in check_script([beats])] == ["false_formula"]


def test_a_number_line_point_sits_at_its_number():
    NumberLineParams(x_range=[-1, 4], points=[{"name": "1/2", "x": 0.5}, {"name": "√2", "x": 1.41},
                                              {"name": "a", "x": 3}])
    with pytest.raises(ValidationError, match='point "3" is at 4, but 3 is 3'):
        NumberLineParams(x_range=[0, 5], points=[{"name": "3", "x": 4}])
    line = 'line = NumberLine(x_range=[0, 5], points=[{"name": "2", "x": 2}])'
    assert 'but 1/2 is 1/2: put it at 0.5' in check_segment([[line], ['line.point(name="1/2", x=1.5)']])[0]
    assert 'point "2" is at 3' in check_segment([[line], ['line.slide(name="2", x=3)']])[0]
    assert check_segment([[line], ['line.point(name="p", x=1.5)', 'line.slide(name="p", x=3)']]) == []


def test_a_jump_lands_where_its_label_says():
    """plan-1's remainder video: a jump from -14 to -7 marked "x7" (it is +7)."""
    line = 'line = NumberLine(x_range=[-15, 0])'
    assert check_segment([[line], ['line.jump(from_x=-14, to_x=-7, label="+7")']]) == []
    problems = check_segment([[line], ['line.jump(from_x=-14, to_x=-7, label="x7")']])
    assert len(problems) == 1 and "lands on -98, not -7" in problems[0]
    assert check_segment([[line], ['line.jump(from_x=-14, to_x=-11, label="r=3")']]) == []


def test_a_formula_headed_column_holds_that_formula():
    TableParams(columns=["n", "n^2", "2^n"], rows=[[4, 16, 16], [8, 64, 256], [10, 100, 1024]])
    rows = [["4", "16", "8", "16"], ["8", "64", "24", "256"], ["10", "100", "33", "1024"]]  # 33: n log n rounded
    assert table_column_problem(["n", "n^2", "n log n", "2^n"], rows) is None
    with pytest.raises(ValidationError, match=r'column "n\^2" in row 1 should be 64 \(n = 8\), not 60'):
        TableParams(columns=["n", "n^2"], rows=[[4, 16], [8, 60]])
    # unknown functions, empty cells and text are left alone
    assert table_column_problem(["n", "T(n)"], [["1", "1"], ["2", "7"]]) is None
    assert table_column_problem(["n", "n(n+1)/2"], [["10", "55"], ["4", ""]]) is None
    assert table_column_problem(["i", "x", "total"], [["0", "5", ""], ["1", "3", "8"]]) is None
    # a log without a base may be any base, as long as one fits the whole column
    assert table_column_problem(["n", "log n"], [["100", "2"], ["1000", "3"]]) is None
    assert table_column_problem(["n", "log n"], [["8", "3"], ["16", "5"]])


def test_filling_a_formula_column_is_checked():
    table = 'tb = Table(columns=["n", "n^2"], rows=[[3, ""], [4, ""]])'
    assert check_segment([[table], ['tb.fill(row=0, col=1, value=9)']]) == []
    problems = check_segment([[table], ['tb.fill(row=1, col=1, value=8)']])
    assert len(problems) == 1 and "should be 16" in problems[0]


def test_probability_bars():
    BarParams(labels=["1", "2", "3"], values=[0.2, 0.3, 0.5], y_label="P(x)")
    BarParams(labels=["A", "B"], values=[0.6, 0.7], y_label="P(A)")  # events may overlap
    BarParams(labels=["H", "T"], values=[7, 3], y_label="count")
    with pytest.raises(ValidationError, match="add up to 1.2"):
        BarParams(labels=["1", "2"], values=[0.6, 0.6], y_label="P(X = k)")
    with pytest.raises(ValidationError, match="each is at most 1"):
        BarParams(labels=["A", "B"], values=[3, 1], y_label="probability")
