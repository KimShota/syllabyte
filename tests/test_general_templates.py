"""The general-purpose templates: boxes and arrows (Graph), BarChart, NumberLine, Table, polar and parametric curves.
What each computes, and what it refuses before anything renders. No Manim, no LLM.

Their examples are rendered (both frames, no layout findings) by test_visual_templates.py with
SYLLABYTE_RENDER_TESTS=1."""

from __future__ import annotations

import pytest

from animation_agent.visuals.calls import check_segment, describe_segment
from animation_agent.visuals.families import DRAWN_BY, main_template
from animation_agent.visuals.specs import graph_positions, label_lines, nice_top, nl_terms, nl_ticks, truth_fn

FLOW = ('g = Graph(nodes=["s", "r", "d", "y", "n"], labels={"s": "start", "r": "read x", "d": "x > 0?", '
        '"y": "print x", "n": "stop"}, edges=[["s", "r"], ["r", "d"], ["d", "y", "yes"], ["d", "n", "no"]], '
        'directed=True, layout="tree")')
DFA = ('m = Graph(nodes=["q0", "q1", "q2"], edges=[["q0", "q1", "a"], ["q1", "q1", "a"], ["q1", "q2", "b"], '
       '["q2", "q0", "b"]], directed=True, layout="flow")')


def said(*beats):
    assert check_segment(list(beats)) == []
    return describe_segment(list(beats))


# --------------------------------------------------------------------------
# Boxes and arrows
# --------------------------------------------------------------------------


def test_a_flowchart_is_boxes_with_words_and_a_marker_walks_its_edges():
    out = said([FLOW], ['g.walk(to="s")', 'g.walk(to="r")'], ['g.walk(to="d")'], ['g.walk(to="y")'])
    assert out[0].startswith('A tree of boxes "start", "read x"')
    assert out[3] == 'The marker moves from "x > 0?" to "print x" along the edge marked "yes".'
    assert "no edge from r to y" in check_segment([[FLOW], ['g.walk(to="r")', 'g.walk(to="y")']])[0]


def test_a_state_machine_run_is_computed_from_the_edge_labels():
    out = said([DFA], ['m.feed(symbol="a")', 'm.feed(symbol="a")'], ['m.feed(symbol="b")'])
    assert out[1].endswith('from q1 to q1; input read so far: "aa".')
    assert out[2] == 'Reading "b", the marker follows the edge from q1 to q2; input read so far: "aab".'
    assert "no edge out of q2 is labelled 'a'" in check_segment(
        [[DFA], ['m.feed(symbol="a")', 'm.feed(symbol="b")', 'm.feed(symbol="a")']])[0]


def test_box_diagrams_keep_to_what_fits_a_portrait_screen():
    too_wide = ('g = Graph(nodes=["r", "a", "b", "c", "d"], labels={"r": "root", "a": "a", "b": "b", "c": "c", '
                '"d": "d"}, edges=[["r", "a"], ["r", "b"], ["r", "c"], ["r", "d"]], layout="tree")')
    assert "4 boxes side by side" in check_segment([[too_wide]])[0]
    long_words = ('g = Graph(nodes=["r", "a", "b", "c"], labels={"r": "root", "a": "partitioning", "b": "b", '
                  '"c": "c"}, edges=[["r", "a"], ["r", "b"], ["r", "c"]], layout="tree")')
    assert "doesn't fit a box" in check_segment([[long_words]])[0]
    assert label_lines("merge the halves", 1.7) == ["merge the", "halves"]
    assert label_lines("partitioning", 1.4) is None
    assert "only in a directed graph" in check_segment([['g = Graph(nodes=["a", "b"], edges=[["a", "a"]])']])[0]


def test_tree_and_flow_layouts():
    tree = graph_positions(["r", "a", "b", "c", "d"], [["r", "a"], ["r", "b"], ["a", "c"], ["a", "d"]], "tree")
    assert tree["r"][1] == 1 and tree["c"][1] == 0
    assert tree["a"][0] == pytest.approx((tree["c"][0] + tree["d"][0]) / 2)  # a parent over its children
    chain = graph_positions(["q0", "q1", "q2"], [["q0", "q1"], ["q1", "q2"], ["q2", "q0"]], "flow", directed=True)
    assert chain["q0"][0] < chain["q1"][0] < chain["q2"][0]  # along the arrows, the back edge aside


# --------------------------------------------------------------------------
# BarChart
# --------------------------------------------------------------------------

BARS = 'b = BarChart(labels=["1", "2", "3"], values=[2, 6, 2])'


def test_bar_totals_shares_and_expected_values_are_computed():
    out = said([BARS], ["b.total()"], ["b.normalize()"], ["b.expected()"], ['b.compare(a="2", b="1")'])
    assert out[1] == "The total of the bars, 10, is noted."
    assert out[2] == "Each bar becomes its share of the total: 1: 0.2, 2: 0.6, 3: 0.2."
    assert out[3] == "The expected value, 2, is noted."
    assert out[4].startswith("Bars 2 and 1 light up: 2 (0.6) is taller than 1 (0.2)")
    assert said([BARS], ["b.cumulative()"])[1] == "Each bar becomes the running total: 1: 2, 2: 8, 3: 10."


def test_bar_charts_refuse_what_would_not_read():
    assert "1 bars; use" not in " ".join(check_segment([[BARS]]))
    assert "3 labels but 2 values" in check_segment([['b = BarChart(labels=["a", "b", "c"], values=[1, 2])']])[0]
    eight = 'b = BarChart(labels=["Mon", "b", "c", "d", "e", "f", "g", "h"], values=[1, 1, 1, 1, 1, 1, 1, 1])'
    assert "too wide under one of 8 bars" in check_segment([[eight]])[0]
    words = 'b = BarChart(labels=["H", "T"], values=[3, 5])'
    assert "expected value needs numbers" in check_segment([[words], ["b.expected()"]])[0]
    assert nice_top(6) == 8 and nice_top(0.25) == 0.3


# --------------------------------------------------------------------------
# NumberLine
# --------------------------------------------------------------------------


def test_a_sequence_and_the_terms_inside_a_band_are_computed():
    line = 'l = NumberLine(x_range=[0, 1.2], step=0.2)'
    out = said([line], ['l.sequence(fn="1/n", n_from=1, n_to=8)'], ["l.band(center=0, eps=0.15)"])
    assert "dots at 1, 0.5, 0.33, 0.25, 0.2, 0.17, 0.14, 0.12" in out[1]
    assert out[2].endswith("2 of the 8 terms lie inside, every one from a_7 on.")
    assert nl_terms("(1 + 1/n)**n", 1, 2) == [(1, 2.0), (2, 2.25)]
    assert nl_ticks(0, 1, None) == [0, 0.2, 0.4, 0.6, 0.8, 1.0] or len(nl_ticks(0, 1, None)) >= 5


def test_intervals_points_and_jumps_say_what_they_show():
    line = 'l = NumberLine(x_range=[-3, 6])'
    out = said([line], ["l.interval(lo=-1, hi=None, lo_closed=False)"], ['l.jump(from_x=2, to_x=5, label="+3")'],
               ['l.point(name="x", x=2)'], ['l.slide(name="x", x=4.5)'])
    assert out[1] == "The interval (-1, ∞) is shaded teal."
    assert out[4] == "Point x slides from 2 to 4.5."
    assert "off the line" in check_segment([[line], ['l.point(name="x", x=9)']])[0]


# --------------------------------------------------------------------------
# Table
# --------------------------------------------------------------------------


def _filled(rule_call: str, *calls: str) -> list[list[str]]:
    from animation_agent.visuals.calls import live_after

    return live_after([[[rule_call], list(calls)]])["t"].state["cells"]


def test_rule_tables_are_filled_by_code():
    cells = _filled('t = Table(rule="pascal", size=[6])', *["t.fill_row()"] * 6)
    assert cells[5] == ["1", "5", "10", "10", "5", "1"]
    assert _filled('t = Table(rule="grid_paths", size=[3, 3])', *["t.fill_row()"] * 3)[2] == ["1", "3", "6"]
    assert _filled('t = Table(rule="fibonacci", size=[6])', "t.fill_row()")[0] == ["0", "1", "1", "2", "3", "5"]
    assert "8 columns" in check_segment([['t = Table(rule="fibonacci", size=[7])']])[0]  # its label column counts
    xor = _filled('t = Table(rule="truth_table", expr="A xor B")', *["t.fill_row()"] * 4)
    assert [row[-1] for row in xor] == ["0", "1", "1", "0"]
    out = said(['t = Table(rule="pascal", size=[4])'], ["t.fill_row()", "t.fill_row()", "t.fill_row()"],
               ["t.fill_next()", "t.fill_next()"])
    assert out[2].endswith("row 3, column 1 is filled with 3 = 1 + 2, arrows from the cells it adds.")


def test_tables_refuse_what_would_not_fit():
    assert "the table is full" in check_segment([['t = Table(rule="fibonacci", size=[2])'],
                                                 ["t.fill_row()", "t.fill_next()"]])[0]
    assert "cells are computed" in check_segment([['t = Table(rule="pascal", size=[3])'],
                                                  ["t.fill(row=0, col=0, value=1)"]])[0]
    wide = 't = Table(columns=["a", "b", "c", "d", "e", "f", "g", "h"], rows=[[1, 2, 3, 4, 5, 6, 7, 8]])'
    assert "8 columns" in check_segment([[wide]])[0]
    with pytest.raises(ValueError, match="variables are A, B and C"):
        truth_fn("A and D")


# --------------------------------------------------------------------------
# Polar and parametric curves
# --------------------------------------------------------------------------

PLOT = 'p = FunctionPlot(x_range=[-1, 2.5], y_range=[-1.5, 1.5])'


def test_polar_and_parametric_curves_and_points_on_them_are_computed():
    out = said([PLOT], ['p.polar(name="r", r="1 + cos(t)")'], ['p.dot_t(curve="r", t=0)'])
    assert out[2] == "A dot on r at t = 0, the point (2, 0)."
    assert "leaves the axes" in check_segment([[PLOT], ['p.parametric(name="c", x_t="3*cos(t)", y_t="sin(t)")']])[0]
    points = said([PLOT], ['p.points(xs=[1], ys=[1], labels=["1+i"])'])
    assert points[1].endswith("at (1, 1) named 1+i.")


def test_the_picture_kinds_the_templates_now_draw():
    for family, template in {"flowchart": "Graph", "state_machine": "Graph", "tree": "BinaryTree", "bar_meter": "BarChart",
                             "probability": "BarChart", "number_line": "NumberLine", "dp_table": "Table",
                             "bits_logic": "Table", "polar_parametric": "FunctionPlot"}.items():
        assert main_template(family) == template, family
    assert main_template("vectors_3d") == "Scene3D"
    assert main_template("geometry") == "GeometryConstruction"
    assert main_template("slope_field") == "SlopeField"


def test_bars_from_a_formula_and_a_whole_deck():
    out = said(['b = BarChart(labels=["x"], values=[1])'], ['b.series(fn="8*0.5**(n-1)", n_from=1, n_to=4, label="R")'],
               ["b.cumulative()"])
    assert out[1] == "The bars become the terms of 8*0.5**(n-1): R1: 8, R2: 4, R3: 2, R4: 1."
    assert out[2] == "Each bar becomes the running total: R1: 8, R2: 12, R3: 14, R4: 15."
    deck = said(['b = BarChart(labels=["A", "2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K"], '
                 'values=[4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4])'])
    assert deck[0].endswith("the bars are too narrow to carry their numbers (filling the frame).")
    assert "too wide" in check_segment([['b = BarChart(labels=["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", '
                                         '"J", "Q", "K"], values=[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])']])[0]


def test_a_five_by_five_grid_of_decimals_fits_and_a_polar_cell_is_computed():
    rows = ('rows=[[3.3, 8.8, 4.4, 5.3, 1.5], [1.5, 3.0, 2.3, 1.9, 0.5], [0.1, 0.7, 0.7, 0.4, -0.4], [-1.0, -0.4, '
            '-0.4, -0.6, -1.2], [-1.9, -1.3, -1.2, -1.4, -2.0]]')
    assert check_segment([[f't = Table(columns=["1", "2", "3", "4", "5"], {rows})']]) == []
    labelled = f't = Table(columns=["1", "2", "3", "4", "5"], row_labels=["1", "2", "3", "4", "5"], {rows})'
    assert "no row_labels" in check_segment([[labelled]])[0]  # "-0.4" is 0.63 wide, a sixth column leaves 0.57
    out = said([PLOT], ['p.sector(r_from=1, r_to=1.5, t_from=0.5, t_to=1.0, label="dA")'])
    assert "sides are dr = 0.5 and an arc r dtheta = 0.62 long, its area 0.31" in out[1]


def test_the_writer_is_told_to_draw_what_the_lines_name_and_let_code_compute():
    from script_generation_agent.prompts import storyboard_system_prompt

    system = storyboard_system_prompt(2, None, explainer="P", peer="S", lexicon="-", example="",
                                      templates=["BarChart", "EquationSteps", "Note"], family="series")
    for rule in ("Plan the diagram from what the lines will name", "Never type a value code can compute",
                 "at its real size", "The wrong idea is drawn as the wrong picture", "A line that works something out"):
        assert rule in system, rule


def test_a_polar_cell_drawn_again_is_relabelled_not_stacked():
    import os

    if not os.environ.get("SYLLABYTE_RENDER_TESTS"):
        pytest.skip("set SYLLABYTE_RENDER_TESTS=1 to render")
    import json
    from pathlib import Path as _Path
    from types import SimpleNamespace

    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render
    from animation_agent.visuals.scene_code import build_spec_scene

    beats = [['plot = FunctionPlot(x_range=[-3, 3], y_range=[-3, 3], equal_scale=True)'],
             ['plot.sector(r_from=1, r_to=1.5, t_from=0.6, t_to=1.0, label="dA")'],
             ['plot.sector(r_from=1, r_to=1.5, t_from=0.6, t_to=1.0, label="cell")',
              'plot.sector(r_from=2, r_to=2.5, t_from=0.6, t_to=1.0, label="far")'],
             ['plot.sector(r_from=1, r_to=1.5, t_from=0.6, t_to=1.0, label="r=1")',
              'plot.sector(r_from=2, r_to=2.5, t_from=0.6, t_to=1.0, label="r=2")']]
    seg = SimpleNamespace(beats=[SimpleNamespace(narration="x", visual="y", draw=b) for b in beats])
    tmp = _Path(os.environ.get("TMPDIR", "/tmp")) / "sector-render-test"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / BEATS_FILE).write_text(json.dumps([2.0] * len(beats)))
    ok, error, _, layout = _try_render(tmp, build_spec_scene(seg, "Seg0"), "Seg0", "low", len(beats), 2.0 * len(beats),
                                       check_formulas=False, frame="dialogue")
    assert ok, error
    assert layout.findings == [], layout.findings
