"""The views and calls added to cover the rest of CS and Math (plan/visual-coverage-plan.md): a code panel that
wraps, scrolls and watches variables; a tape of characters or bits; windows and scrolling for examples too big for
the frame; graph layouts by rule, B-tree nodes, records and arrow kinds; nonlinear maps and heat maps; a 3D scene;
circuit blocks and flip-flops, signals, box plots, error bars and stacked bars; and the brief chosen by area. No
Manim, no LLM."""

from __future__ import annotations

import numpy as np
import pytest

from animation_agent.scene import diagram_layout as D
from animation_agent.scene import layout as L
from animation_agent.scene import math_layout as M
from animation_agent.scene import text_layout as T
from animation_agent.scene.examples import COVERAGE_PROGRAMS
from animation_agent.scene.sandbox import run_program

DIALOGUE = (3.9, 4.8, 2.4)


def run(source: str) -> list[dict]:
    result = run_program(source)
    assert result.ok, result.error
    return result.snapshots


@pytest.mark.parametrize("name", list(COVERAGE_PROGRAMS))
def test_every_coverage_example_lays_out_in_the_dialogue_frame(name):
    L.plan(run(COVERAGE_PROGRAMS[name]), *DIALOGUE)


# ---- code and tape -----------------------------------------------------------------------------------------


def test_a_long_code_line_wraps_under_itself_and_the_window_follows_the_current_line():
    lines = ["def f(a):"] + [f"  x{k} = a + {k}" for k in range(14)] + ["  return x0 + x1 + x2 + x3 + x4"]
    src = f"c = code('c', {lines!r})\nfor i in (1, 8, 15):\n    c.line(i)\n    snap(str(i))"
    snaps = run(src)
    lay = L.plan(snaps, *DIALOGUE).math["c"]
    assert lay.scrolled and lay.window < len(lay.rows[0])
    for i, line in zip(range(3), (1, 8, 15)):
        rows = [k for k, (j, _t, _c) in enumerate(lay.rows[i]) if j == line]
        assert lay.start[i] <= rows[0] and rows[-1] < lay.start[i] + lay.window
    last = [t for j, t, _c in lay.rows[0] if j == 15]
    assert len(last) > 1 and all(len(t) <= lay.chars + 2 for t in last)  # wrapped (a leading space counts half)


def test_watched_variables_keep_their_place_and_values_are_short():
    snaps = run("c = code('c', ['x = 1'])\nc.watch('x', 1)\nsnap()\nc.watch('y', 22)\nc.watch('x', 3)\nsnap()")
    assert snaps[-1]["views"]["c"]["watch"] == {"x": "3", "y": "22"}
    lay = L.plan(snaps, *DIALOGUE).math["c"]
    assert set(lay.watch) == {"x", "y"}
    assert "longer than 6" in run_program("c = code('c', ['x'])\nc.watch('x', 1234567)\nsnap()").error


def test_a_bit_tape_wraps_by_bytes_and_its_field_labels_never_touch():
    snaps = run(COVERAGE_PROGRAMS["float32"])
    lay = L.plan(snaps, *DIALOGUE).math["t"]
    assert lay.lines >= 2 and lay.per_line % 4 == 0
    spots = list(lay.field_spots.items())
    for i, ((_k1, t1), c1) in enumerate(spots):
        for (_k2, t2), c2 in spots[i + 1:]:
            apart = abs(c1[0] - c2[0]) >= (M.text_width(t1) + M.text_width(t2)) / 2 or abs(c1[1] - c2[1]) > 0.2
            assert apart, (t1, t2)


def test_a_pattern_slides_along_its_text_and_a_tape_too_long_for_rows_is_refused():
    snaps = run(COVERAGE_PROGRAMS["match"])
    assert [s["views"]["t"]["rows"]["p"]["at"] for s in snaps][:3] == [0, 0, 1]
    long = "t = tape('t', 'ABCDEFGHIJKLMNOPQRST')\nt.row('p', 'ABC')\nsnap()"
    with pytest.raises(Exception, match="stays on one line"):
        L.plan(run(long), *DIALOGUE)


def test_tape_cells_are_one_character():
    assert "one character" in run_program("tape('t', ['10', '1'])\nsnap()").error


def test_the_sandbox_has_encodings_and_complex_numbers():
    snaps = run("t = tape('t', bin(5)[2:] + format(2, '03b') + chr(ord('a') + 1))\nz = complex(1, 2) * 1j\n"
                "snap(str(z.real))")
    assert snaps[0]["views"]["t"]["values"] == list("101010b") and snaps[0]["caption"] == "-2.0"


# ---- layouts and shapes ------------------------------------------------------------------------------------


def _positions(source: str, name: str):
    snaps = run(source)
    lay = L.plan(snaps, *DIALOGUE)
    return lay.graph_pos[name]


def test_a_circle_layout_puts_its_nodes_round_a_ring_in_order_from_the_top():
    pos = _positions("c = nodes('c', layout='circle')\nfor k in range(8):\n    c.add(k)\nsnap()", "c")
    pts = np.array([pos[str(k)][:2] for k in range(8)])
    centre = pts.mean(0)
    radii = np.hypot(*(pts - centre).T)
    assert np.ptp(radii) < 1e-6  # round, not stretched
    assert pts[0][1] == pts[:, 1].max()  # 0 at the top
    assert pts[2][0] > centre[0]  # clockwise: 2 is to the right


def test_bipartite_and_layered_layouts_keep_each_layer_in_a_column():
    pos = _positions(COVERAGE_PROGRAMS["neural"], "n")
    xs = {k[0]: {round(p[0], 6) for kk, p in pos.items() if kk[0] == k[0]} for k in pos}
    assert all(len(v) == 1 for v in xs.values()) and len({next(iter(v)) for v in xs.values()}) == 3
    assert "layer" in run_program("g = nodes('g', layout='bipartite')\ng.add('a')\nsnap()").error


def test_a_fixed_layout_keeps_the_programs_drawing_to_one_scale():
    pos = _positions("g = nodes('g', layout='fixed')\ng.add('a', at=(0, 0))\ng.add('b', at=(2, 0))\n"
                     "g.add('c', at=(0, 1))\ng.link('a', 'b')\nsnap()", "g")
    ab = np.hypot(*(pos["b"][:2] - pos["a"][:2]))
    ac = np.hypot(*(pos["c"][:2] - pos["a"][:2]))
    assert ab == pytest.approx(2 * ac)


def test_a_b_tree_node_holds_keys_and_its_children_hang_by_slot():
    snaps = run(COVERAGE_PROGRAMS["btree"])
    v = snaps[-1]["views"]["t"]
    assert v["nodes"]["r"]["keys"] == ["20"] and v["nodes"]["b"]["keys"] == ["25", "30"]
    assert {(a, b, slot) for a, b, _s, _l, slot in v["links"]} == {("r", "a", 0), ("r", "b", 1)}
    L.plan(snaps, *DIALOGUE)
    assert "1-4 keys" in run_program("t = nodes('t')\nt.add('r', keys=[1, 2, 3, 4, 5])\nsnap()").error


def test_a_record_is_sized_for_its_fields_and_arrows_keep_their_kind():
    snaps = run(COVERAGE_PROGRAMS["uml"])
    v = snaps[0]["views"]["f"]
    assert v["boxes"]["acct"]["shape"] == "record" and len(v["boxes"]["acct"]["fields"]) == 3
    assert {a[4] for a in v["arrows"]} == {"inherit"}
    w1, h1 = D.bsize(v["boxes"]["acct"])
    w2, h2 = D.bsize({**v["boxes"]["acct"], "fields": []})
    assert h1 > h2 + 3 * D.LINE_H - 0.01


# ---- maps, heat, 3D ----------------------------------------------------------------------------------------


def test_a_grid_sent_through_z_squared_bends_and_a_heat_map_spans_its_values():
    snaps = run(COVERAGE_PROGRAMS["z_squared"])
    before, after = (s["views"]["a"]["items"]["g"]["pieces"] for s in snaps)
    corner = max((p for piece in after for p in piece), key=lambda p: p[1])
    assert corner[1] == pytest.approx(2.0)  # (1 + i)^2 = 2i
    snaps = run("a = axes('a', x=(-1, 1), y=(-1, 1))\nlo, hi = a.heat('h', lambda x, y: x * x + y * y, n=8)\n"
                "snap(str(round(lo, 3)) + ' ' + str(round(hi, 3)))")
    lo, hi = map(float, snaps[0]["caption"].split())
    assert 0 < lo < 0.1 and 1.5 < hi < 2


def test_a_heat_table_colours_each_number_by_its_place_on_the_scale():
    snaps = run(COVERAGE_PROGRAMS["attention"])
    heat = snaps[0]["views"]["g"]["heat"]
    assert heat["0,0"] == pytest.approx(0.7) and heat["0,1"] == pytest.approx(0.1)


def test_a_plane_is_cut_to_the_box_and_every_corner_lies_on_it():
    snaps = run("s = space('s')\ns.plane('p', (1, 1, 1), 1)\nsnap()")
    pts = snaps[0]["views"]["s"]["items"]["p"]["points"]
    assert len(pts) >= 3 and all(abs(sum(p) - 1) < 1e-9 for p in pts)
    assert all(-2 - 1e-9 <= c <= 2 + 1e-9 for p in pts for c in p)


def test_turning_the_camera_moves_the_scene_but_keeps_its_scale():
    snaps = run(COVERAGE_PROGRAMS["span"])
    lay = L.plan(snaps, *DIALOGUE).math["s"]
    assert lay.views[0] != lay.views[-1]
    a, b = lay.to_screen((1, 0, 1), 0), lay.to_screen((1, 0, 1), len(snaps) - 1)
    assert np.hypot(a[0] - b[0], a[1] - b[1]) > 0.05
    region = L.plan(snaps, *DIALOGUE).regions["s"]
    for i in range(len(snaps)):
        for it in snaps[i]["views"]["s"]["items"].values():
            for line in M.space_lines(it, lay, i):
                for x, y in line:
                    assert region.cx - region.w / 2 - 1e-6 <= x <= region.cx + region.w / 2 + 1e-6


# ---- circuits, signals, charts -----------------------------------------------------------------------------


def test_a_two_bit_counter_counts_on_each_tick():
    snaps = run(COVERAGE_PROGRAMS["counter"])
    assert [s["caption"][-2:] for s in snaps] == ["00", "01", "10", "11"]


def test_a_wire_back_to_a_flip_flop_runs_up_the_right_and_into_its_top():
    snaps = run(COVERAGE_PROGRAMS["counter"])
    lay = L.plan(snaps, *DIALOGUE).math["c"]
    region = L.plan(snaps, *DIALOGUE).regions["c"]
    back = lay.wires["n0>f0#0"]
    parts = snaps[0]["views"]["c"]["parts"]
    right_of_parts = max(lay.pos[k][0] + lay.size[k][0] / 2 for k in parts)
    assert max(x for x, _y in back) > right_of_parts  # its own lane, past every part
    assert back[-1][1] > lay.pos["f0"][1]  # into the flip-flop's top
    assert max(x for x, _y in back) <= region.cx + region.w / 2


@pytest.mark.parametrize("src, out", [
    ("c = circuit('c')\nc.input('a', 1)\nc.input('b', 0)\nc.input('s', 1)\nc.block('m', 'MUX', ['a', 'b', 's'])\n"
     "c.output('y', 'm')\nsnap(str(c.value('y')))", "0"),
    ("c = circuit('c')\nc.input('a', 1)\nc.input('b', 1)\nc.input('ci', 1)\nc.block('f', 'FA', ['a', 'b', 'ci'])\n"
     "c.output('s', 'f.s')\nc.output('co', 'f.co')\nsnap(str(c.value('co')) + str(c.value('s')))", "11"),
    ("c = circuit('c')\nc.input('a1', 1)\nc.input('a0', 0)\nc.block('d', 'DEC', ['a1', 'a0'])\n"
     "c.output('y', 'd.y2')\nsnap(str(c.value('y')))", "1"),
])
def test_blocks_compute_their_outputs(src, out):
    snaps = run(src)
    assert snaps[0]["caption"] == out
    L.plan(snaps, *DIALOGUE)


def test_a_block_with_several_outputs_needs_one_named():
    error = run_program("c = circuit('c')\nc.input('a')\nc.input('b')\nc.block('h', 'HA', ['a', 'b'])\n"
                        "c.output('o', 'h')\nsnap()").error
    assert "h.s" in error and "h.c" in error


def test_a_signal_is_a_square_wave_in_its_lane_and_widens_the_time_axis():
    snaps = run("tl = timeline('tl', ['clk'])\ntl.signal('c', 'clk', [1, 0, 1, 0], t0=0, step=2)\nsnap()")
    lay = L.plan(snaps, *DIALOGUE).math["tl"]
    assert lay.t == (0.0, 8.0)


def test_a_box_plot_is_computed_and_an_outlier_lies_past_its_whisker():
    snaps = run("a = axes('a')\nq = a.boxplot('b', [1, 2, 3, 4, 5, 6, 7, 30])\nsnap(str(q))")
    it = snaps[0]["views"]["a"]["items"]["b"]
    assert it["out"] == [30.0] and it["q"][4] == 7.0 and it["q"][2] == pytest.approx(4.5)


def test_stacked_bars_stand_on_the_bars_below_them():
    snaps = run(COVERAGE_PROGRAMS["stacked"])
    lay = L.plan(snaps, *DIALOGUE).math["a"]
    assert lay.y[1] >= 10 + 8  # the tallest stack fits
    top = M.item_polylines(snaps[-1]["views"]["a"]["items"]["y"], lay)[0]
    bottom = M.item_polylines(snaps[-1]["views"]["a"]["items"]["x"], lay)[0]
    assert top[0][1] == pytest.approx(bottom[1][1])  # Y's bottom is X's top


# ---- the brief by area -------------------------------------------------------------------------------------


@pytest.mark.parametrize("text, area", [
    ("Round-robin CPU scheduling with a time quantum", "systems"),
    ("Dijkstra's shortest path algorithm on a weighted graph", "algorithms"),
    ("Eigenvectors and eigenvalues of a matrix", "linear"),
    ("The derivative as the slope of the tangent line", "calculus"),
    ("Conditional probability and Bayes' rule", "discrete"),
    ("Professional ethics", None),
])
def test_a_topic_gets_its_areas_brief(text, area):
    from animation_agent.scene.brief import area_of

    assert area_of(text) == area


def test_an_areas_brief_spells_out_its_views_indexes_the_rest_and_is_shorter():
    from animation_agent.scene.brief import brief

    full, systems = brief(), brief("systems")
    assert len(systems) < 0.75 * len(full)
    assert "c.block(key, kind, inputs)" in systems and "tl.signal(" in systems
    assert "space(name, x, y, z): a turning 3D scene" in systems  # indexed, still usable
    assert "s.param(key, fx, fy, fz" not in systems and "s.param(key, fx, fy, fz" in full


def test_a_view_made_after_the_first_snapshot_reads_its_own_snapshots():
    """Per-snapshot layouts (a scrolling formula, a code window) count only the snapshots their view is in; the
    drawing must too (runs/cov1: a formula made after the first snapshot read past its layout's end)."""
    src = ("a = axes('a', x=(0, 1))\nsnap('axes')\nf = formula('f')\nfor k in range(4):\n    f.add('x_' + str(k) + ' = ' + "
           "str(k))\n    snap('line ' + str(k))\n")
    snaps = run(src)
    lay = L.plan(snaps, *DIALOGUE)
    assert len(lay.math["f"].start) == len(snaps) - 1
