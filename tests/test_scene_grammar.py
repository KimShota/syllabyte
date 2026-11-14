"""The scene grammar prototype (plan/scene-grammar-plan.md, P0): picture programs run in the sandbox, record
snapshots, and the layout refuses what can't be drawn legibly. No Manim, no LLM. Rendering is checked by
scripts/scene_demo.py."""

from __future__ import annotations

import pytest

from animation_agent.scene import layout as L
from animation_agent.scene.api import PictureError
from animation_agent.scene.examples import PROGRAMS
from animation_agent.scene.sandbox import check_source, run_program

DIALOGUE = (3.9, 4.8, 2.4)  # the dialogue frame's safe width, height, top


def run(source: str) -> list[dict]:
    result = run_program(source)
    assert result.ok, result.error
    return result.snapshots


@pytest.mark.parametrize("source, why", [
    ("import os", "no imports"),
    ("x = ().__class__", "names starting with _"),
    ("open('/etc/passwd')", "NameError"),
    ("while True: pass", "longer than"),
    ("x = 1", "never called snap"),
    ("cells('a', [1, 2]); cells('a', [3])", "already a view"),
    ("cells('a', [123]); snap()", "longer than 2 characters"),
    ("n = nodes('t'); n.add(1); n.mark(1, 'purple')", "unknown style"),
])
def test_the_sandbox_refuses(source, why):
    result = run_program(source)
    assert not result.ok and why in result.error, result.error


def test_check_source_points_at_the_line():
    assert "line 2" in check_source("x = 1\nimport sys")


def test_union_find_ends_with_the_id_array_quick_union_gives():
    last = run(PROGRAMS["union_find"])[-1]["views"]
    assert last["id"]["values"] == ["0", "1", "2", "7", "3", "5", "5", "5"]
    links = {(a, b) for a, b, *_ in last["f"]["links"]}
    assert links == {("3", "4"), ("7", "3"), ("5", "6"), ("5", "7")}


def _black_height(view: dict) -> int:
    """Checks the left-leaning red-black rules on a drawn tree and returns its black height."""
    kids = {}
    red = {}
    for a, b, style, _label, slot in view["links"]:
        kids.setdefault(a, {})[slot] = b
        red[b] = style == "red"
    nodes = set(view["nodes"])
    root = next(k for k in nodes if k not in red)

    def walk(k, lo, hi, parent_red):
        if k is None:
            return 1
        assert (lo is None or k > lo) and (hi is None or k < hi), "BST order"
        assert not (red.get(k) and parent_red), "two reds in a row"
        right = kids.get(k, {}).get(1)
        assert not red.get(right, False), "a right-leaning red link"
        left_h = walk(kids.get(k, {}).get(0), lo, k, red.get(k, False))
        right_h = walk(right, k, hi, red.get(k, False))
        assert left_h == right_h, "unequal black height"
        return left_h + (0 if red.get(k) else 1)

    return walk(root, None, None, False)


def test_the_red_black_tree_is_valid_after_every_fix():
    snaps = run(PROGRAMS["llrb"])
    fixed = [s for s in snaps if not s["caption"].startswith("insert")]
    assert fixed and all(_black_height(s["views"]["t"]) >= 1 for s in fixed)
    assert sorted(snaps[-1]["views"]["t"]["nodes"]) == sorted("SEARCHXM")


def test_the_jugs_end_with_four_gallons():
    last = run(PROGRAMS["water_jugs"])[-1]["views"]
    assert last["b"]["level"] == 4 and last["b"]["style"] == "found"


def test_every_example_lays_out_in_the_dialogue_frame():
    for source in PROGRAMS.values():
        L.plan(run(source), *DIALOGUE)


def test_a_tree_too_deep_for_the_frame_is_refused_with_a_reason():
    chain = "t = nodes('t', range(12))\nfor i in range(11):\n    t.link(i, i + 1)\nsnap()"
    with pytest.raises(PictureError, match="levels deep"):
        L.plan(run(chain), *DIALOGUE)


def test_too_many_cells_are_refused():
    with pytest.raises(PictureError, match="cells don't fit"):
        L.plan(run("cells('a', list(range(12))); snap()"), *DIALOGUE)


def test_a_forest_shrinks_its_gaps_before_it_wraps():
    snaps = run("nodes('f', range(8)); snap()")
    layout = L.plan(snaps, *DIALOGUE)
    pos = L.layout_nodes(snaps[0]["views"]["f"], layout.regions["f"], None, layout.nodes["f"])
    assert len({round(p[1], 3) for p in pos.values()}) == 1  # one row


def test_a_tree_cycle_is_an_error_not_a_hang():
    snaps = run("t = nodes('t', layout='graph')\nt.add(1); t.add(2); t.link(1, 2); t.link(2, 1)\nsnap()")
    L.plan(snaps, *DIALOGUE)  # a graph may have cycles


# ---- P1: Picture, the template a storyboard draws a program with ----------------------------------------------


def picture_call(source: str, name: str = "p") -> str:
    lines = ", ".join(f'"{line}"' for line in source.strip("\n").splitlines())
    return f"{name} = Picture(program=[{lines}])"


def test_a_picture_call_is_checked_and_described_from_its_captions():
    from animation_agent.visuals.calls import check_segment, describe_segment

    draws = [[picture_call(PROGRAMS["water_jugs"])], ["p.step()"], ["p.step()", "p.step()"]]
    assert check_segment(draws) == []
    said = describe_segment(draws)
    assert "measure exactly 4 gallons" in said[0]
    assert "fill the 5 gallons" in said[1] and "pour 3 from the 5 gallons" in said[2]


def test_stepping_past_the_last_snapshot_is_refused():
    from animation_agent.visuals.calls import check_segment

    draws = [[picture_call("a = cells('a', [1, 2])\nsnap('one')\nsnap('two')")], ["p.step()"], ["p.step()"]]
    problems = check_segment(draws)
    assert len(problems) == 1 and "all are shown" in problems[0]


@pytest.mark.parametrize("source, why", [
    ("a = cells('a', [1, 2])\nsnap()\nx = 1 / 0", "ZeroDivisionError"),
    ("cells('a', list(range(12)))\nsnap()", "doesn't fit"),
    ("import os", "no imports"),
])
def test_a_broken_picture_program_is_sent_back_with_its_error(source, why):
    from animation_agent.visuals.calls import check_segment

    problems = check_segment([[picture_call(source)]])
    assert problems and why in problems[0], problems


def test_the_card_and_brief_render():
    from animation_agent.scene.brief import brief
    from animation_agent.visuals.specs import template_card, REGISTRY

    assert "p.show(snap='min')" in template_card(REGISTRY["Picture"], auto_layout=True)
    assert "red-black" in brief() and "snap(" in brief()


def test_a_beat_shows_a_snapshot_by_name_and_an_unknown_name_is_refused():
    from animation_agent.visuals.calls import check_segment, describe_segment

    prog = "a = cells('a', [3, 1])\nsnap('start', name='s')\na.mark(1, 'found')\nsnap('1 is smaller', name='min')"
    good = [[picture_call(prog)], ["p.show(snap='min')"]]
    assert check_segment(good) == [] and "1 is smaller" in describe_segment(good)[1]
    problems = check_segment([[picture_call(prog)], ["p.show(snap='max')"]])
    assert problems and "no snapshot named 'max'" in problems[0] and "Picture(program" not in problems[0][150:]


# The slide's Bellman-Ford digraph (runs/picture-p1): fits the whole frame, not two thirds of it.
BIG_GRAPH = """\
E = [(0,1,5),(0,4,9),(0,7,8),(1,3,12),(1,7,5),(1,2,10),(2,3,3),(2,6,11),(4,5,4),(4,7,2),(4,6,20),(5,2,1),(5,6,14),(7,2,7),(7,5,6),(3,6,9)]
g = nodes('g', [str(i) for i in range(8)], layout='graph', directed=True)
for a, b, w in E:
    g.link(str(a), str(b), label=str(w))
d = cells('d', [INF] * 8, title='distTo[]')
snap('start', name='start')
d[0] = 0
snap('the source', name='src')"""


def test_escaped_quotes_in_a_program_line_are_read_as_quotes():
    from animation_agent.visuals.calls import check_segment

    call = r"""p = Picture(program=['a = cells(\'a\', [1, 2])', 'snap(\'two cells\', name=\'s\')'])"""
    assert check_segment([[call]]) == []


def test_the_string_inf_draws_as_infinity():
    snaps = run_program("a = cells('a', ['INF', 3])\nsnap()").snapshots
    assert snaps[0]["views"]["a"]["values"][0] == "∞"


def test_a_picture_that_needs_the_whole_frame_drops_the_formulas_beside_it():
    from animation_agent.visuals.normalize import normalize_script

    segs = [[[picture_call(BIG_GRAPH), 'eq = EquationSteps(steps=["(V-1) E"])'], ["p.show(snap='src')"]],
            [["eq.highlight(index=0)", "p.show(snap='start')"]]]
    fixed = normalize_script(segs, keep_echo=True)
    calls = [c for seg in fixed.segments for beat in seg for c in beat]
    assert not any("eq" in c.split("(")[0] for c in calls), calls
    assert sum(c.startswith("p.show") for c in calls) == 2 and "area='full'" in calls[0].replace('"', "'")
    assert any("whole frame" in line for line in fixed.log)


def test_a_small_picture_keeps_its_formula():
    from animation_agent.visuals.normalize import normalize_script

    segs = [[[picture_call("a = cells('a', [3, 1])\nsnap('two', name='s')"), 'eq = EquationSteps(steps=["n^2"])']]]
    calls = [c for seg in normalize_script(segs, keep_echo=True).segments for beat in seg for c in beat]
    assert any(c.startswith("eq = EquationSteps") for c in calls)


def _graph_geometry(source: str, width=3.8, height=4.7, top=2.35):
    snaps = run(source)
    lay = L.plan(snaps, width, height, top)
    name = next(n for n in snaps[-1]["views"] if snaps[-1]["views"][n]["kind"] == "nodes")
    return snaps, lay, name


def test_the_slides_dense_graph_lays_out_with_every_label_clear():
    import numpy as np

    snaps, lay, name = _graph_geometry(BIG_GRAPH)
    pos, r, spots = lay.graph_pos[name], lay.nodes[name].r, lay.labels[name]
    links = list(dict.fromkeys((a, b) for s in snaps for a, b, *_ in s["views"][name]["links"]))
    segments = L._link_segments(pos, links, r, True)
    text = {f"{a}>{b}": str(label) for s in snaps for a, b, _s, label, _slot in s["views"][name]["links"]}
    assert len(spots) == 16
    keys = list(pos)
    assert all(np.linalg.norm(pos[a] - pos[b]) >= 2 * r + L.NODE_ROOM for i, a in enumerate(keys) for b in keys[i + 1:])
    for key, c in spots.items():
        a, b = key.split(">")
        half = np.array([L.LABEL_CHAR_W * len(text[key]) / 2, L.LABEL_H / 2])
        lo, hi = c[:2] - half, c[:2] + half
        assert not any(L._box_near_node(lo, hi, n, r - L.LABEL_ROOM) for n in pos.values())
        set_in = L._seg_dist(*segments[(a, b)], c) < 1e-3
        assert not any(L._seg_hits_box(*seg, lo, hi) for k, seg in segments.items() if not (set_in and k == (a, b)))


def test_the_main_picture_gets_the_room_before_an_array_or_code_panel():
    source = ("g = nodes('g', ['0', '1', '2'], layout='graph', directed=True, title='a graph')\n"
              "g.link('0', '1', label='5')\ng.link('1', '2', label='2')\ng.link('0', '2', label='9')\n"
              "d = cells('d', [0, INF, INF], title='distTo[]')\n"
              "c = code('c', ['init distTo', 'repeat V-1:', ' relax all E'])\nsnap('start')")
    snaps, lay, name = _graph_geometry(source)
    regions = lay.regions
    assert abs(regions["g"].h - (4.7 - regions["d"].h - regions["c"].h - 2 * L.GAP)) < 1e-6  # all that is left
    assert lay.cell["d"] == pytest.approx(L.CELL)  # the array stays compact while the graph could use more


def test_a_short_main_picture_loses_its_title_first():
    source = ("g = nodes('g', ['0', '1', '2', '3'], layout='graph', directed=True, title='digraph, s = 0')\n"
              "for a, b, w in [('0','1',5), ('0','2',9), ('1','2',2), ('2','3',4), ('1','3',8)]:\n"
              "    g.link(a, b, label=str(w))\n"
              "d = cells('d', [0, INF, INF, INF], title='distTo[]')\n"
              "c = code('c', ['init distTo', 'repeat V-1:', ' relax all E'])\nsnap('start')")
    _snaps, lay, _name = _graph_geometry(source)
    assert lay.untitled == {"g"}  # the array keeps its name


def test_a_node_is_big_enough_for_its_label():
    snaps = run("t = nodes('t', ['v3', 'v5'])\nt.link('v3', 'v5')\nsnap()")
    lay = L.plan(snaps, 3.8, 4.7, 2.35)
    assert lay.nodes["t"].r >= L.node_r([snaps[0]["views"]["t"]]) > L.NODE_R


def test_pointers_under_one_cell_stack():
    snaps = run("a = cells('a', [1, 2, 3])\na.point('lo', 1)\na.point('hi', 1)\nsnap()")
    assert L.pointer_rows([snaps[0]["views"]["a"]]) == 2


# ---- math views (P2) ---------------------------------------------------------------------------------------

from animation_agent.scene.examples import MATH_PROGRAMS  # noqa: E402


def _captions(source):
    return {s["name"]: s["caption"] for s in run(source)}


def test_riemann_sums_are_computed_and_climb_to_the_integral():
    caps = _captions(MATH_PROGRAMS["riemann"])
    # f = x^2/2 + 1 on [0, 4], left ends: n = 4 gives 1 + 1.5 + 3 + 5.5 = 11
    assert caps["n4"] == "4 left rectangles: 11.00 in all"
    assert "14.67" in caps["exact"]  # 32/3 + 4
    totals = [float(caps[f"n{n}"].split(": ")[1].split()[0]) for n in (2, 4, 8, 16)]
    assert totals == sorted(totals) and totals[-1] < 14.67


def test_the_tangent_slope_and_the_triangle_and_the_tree_are_computed():
    assert "settles at 2" in _captions(MATH_PROGRAMS["tangent"])["tangent"]
    assert _captions(MATH_PROGRAMS["triangle"])["sum"].endswith("= 180 degrees")
    assert _captions(MATH_PROGRAMS["probability_tree"])["rr"].endswith("= 3/10")


def test_a_level_curve_lies_on_its_level():
    snaps = run("a = axes('a', x=(-2, 2), y=(-2, 2), equal=True)\na.contour('c', lambda x, y: x*x + y*y, 1)\nsnap()")
    pts = [p for piece in snaps[0]["views"]["a"]["items"]["c"]["pieces"] for p in piece]
    assert len(pts) > 40 and all(abs(x * x + y * y - 1) < 0.02 for x, y in pts)


def test_a_curve_breaks_where_it_is_undefined():
    snaps = run("a = axes('a', x=(-2, 2))\na.plot('f', lambda x: 1 / x)\nsnap()")
    pieces = snaps[0]["views"]["a"]["items"]["f"]["pieces"]
    assert len(pieces) == 2 and all(x < 0 for x, _ in pieces[0]) and all(x > 0 for x, _ in pieces[1])


def test_venn_regions_are_set_operations():
    caps = _captions(MATH_PROGRAMS["venn3"])
    assert caps["and"] == "A and B share [3, 4]"
    assert caps["minus"] == "in A or B but not C: [1, 2, 3, 5]"
    assert caps["none"] == "outside all three: [8]"
    snaps = run(MATH_PROGRAMS["venn3"])
    assert snaps[1]["views"]["v"]["shaded"] == [[["110", "111"], "found"]]  # A&B: in A and B, in or out of C
    assert snaps[2]["views"]["v"]["shaded"] == [[["010", "100", "110"], "found"]]  # (A|B)-C


@pytest.mark.parametrize("source, why", [
    ("a = axes('a')\nroot(lambda x: x * x + 1, -1, 1)\nsnap()", "same sign"),
    ("v = venn('v', {'A': {1}, 'B': {2}, 'C': {3}, 'D': {4}})\nsnap()", "1-3 sets"),
    ("v = venn('v', {'A': {1}})\nv.shade('A; 1')\nsnap()", "use set names"),
])
def test_math_mistakes_are_sent_back_with_a_reason(source, why):
    assert why in run_program(source).error


def test_every_math_example_lays_out_in_the_dialogue_frame():
    for source in MATH_PROGRAMS.values():
        L.plan(run(source), *DIALOGUE)


def test_axes_labels_stay_clear_of_every_line_on_screen_with_them():
    import numpy as np
    from animation_agent.scene import math_layout as M

    for key in ("riemann", "tangent", "level_curves"):
        snaps = run(MATH_PROGRAMS[key])
        lay = L.plan(snaps, 3.8, 4.7, 2.35).math["a"]
        x0, x1, y0, y1 = lay.box
        for (thing, text), c in lay.labels.items():
            half = M.text_half(text) - M.ROOM
            for s in snaps:
                items = s["views"]["a"]["items"]
                if thing not in items or items[thing].get("label") != text:
                    continue
                for other, it in items.items():
                    if it["type"] == "field" or (other == thing and (thing, text) in lay.inline):
                        continue
                    for line in M.item_polylines(it, lay):
                        for piece in M.clip_polyline(line, (x0, y0), (x1, y1)):
                            assert not any(M.seg_hits_box(p, q, c - half, c + half) for p, q in zip(piece, piece[1:])), \
                                (key, thing, other)


def test_titles_and_names_show_powers_as_superscripts():
    from animation_agent.scene.math_layout import pretty

    assert pretty("x^2") == "x²" and pretty("slope of x^2 at 1") == "slope of x² at 1" and pretty("e^-x") == "e⁻x"


def test_a_title_or_label_too_long_is_left_out_not_refused():
    snaps = run_program("a = axes('a', x=(0, 1), title='a title far too long to fit')\na.plot('f', lambda x: x, "
                        "label='a long label')\nsnap()").snapshots
    view = snaps[0]["views"]["a"]
    assert view["title"] is None and view["items"]["f"]["label"] is None


# ---- the coverage run's gaps (runs/picture-p4) ---------------------------------------------------------------

def test_bars_and_histograms_are_computed_and_named():
    snaps = run("a = axes('a')\nt = a.bars('b', [3, 5, 2], labels=['A', 'B', 'C'])\n"
                "c = a.histogram('h', [1, 2, 2, 3, 3, 3, 9], bins=4)\nsnap(str(t) + ' ' + str(c))")
    assert snaps[0]["caption"] == "10.0 [3, 3, 0, 1]"  # bins [1,3) [3,5) [5,7) [7,9]
    bars = snaps[0]["views"]["a"]["items"]["b"]
    assert bars["names"] == ["A", "B", "C"] and [round(h) for *_x, h in bars["bars"]] == [3, 5, 2]


def test_a_bar_chart_shows_every_name_and_value_clear_of_each_other():
    lay = L.plan(run(MATH_PROGRAMS["bar_chart"]), 3.8, 4.7, 2.35)
    for m in lay.math.values():
        assert [text for _t, text, _c in m.xticks] == ["Arch", "Engin", "HSS", "Mgmt", "Sci"]  # two rows, none dropped
        assert m.dropped == []


def test_a_number_line_places_points_intervals_and_jumps():
    snaps = run(MATH_PROGRAMS["division"])
    items = snaps[-1]["views"]["n"]["items"]
    assert items["x"]["x"] == 17 and items["r"]["closed"] == [True, False] and items["j"]["a"] == 14
    lay = L.plan(snaps, 3.8, 4.7, 2.35).math["n"]
    assert lay.dropped == [] and [t for _v, t, _c in lay.ticks][0] == "-21"
    assert "off the line" in run_program("n = numberline('n', 0, 10)\nn.point('p', 12)\nsnap()").error


def test_columns_under_a_surface_approach_its_volume():
    caps = _captions(MATH_PROGRAMS["volume"])
    v = [float(caps[k].split("about ")[-1].split()[0].rstrip(";")) if "about" in caps[k]
         else float(caps[k].split(": ")[0].split()[-1]) for k in ("n2", "n4")]
    assert v[0] > v[1] > 1.5  # f falls away from the corner each column is measured at the middle of
    assert caps["n8"].startswith("64 columns: 1.50")
    lay = L.plan(run(MATH_PROGRAMS["volume"]), 3.8, 4.7, 2.35).math["s"]
    assert {name for name, _c in lay.names} == {"x", "y", "z"}


def test_a_formula_latex_cannot_compile_is_drawn_simpler_not_lost():
    pytest.importorskip("manim")
    from animation_agent.visuals.base import _isolable, tex

    assert not _isolable("h", r"h(\theta_1,\theta_2)")  # isolating h would split \theta
    assert tex(r"h(\theta_1,\theta_2)", isolate=["h"]) is not None
    assert tex(r"\frac{1}{2", isolate=[]) is not None  # broken TeX: shown as text instead of failing the segment


def test_a_cut_off_picture_call_is_closed():
    from animation_agent.visuals.calls import parse_call

    cut = "p = Picture(program=['a = cells(\\'a\\', [1])', 'snap(\\'one\\', name=\\'one\\')\""
    assert parse_call(cut, {}).args["program"][-1].startswith("snap(")


def test_a_plan_whose_picture_barely_changes_is_sent_back():
    from script_generation_agent.storyboard_plan import _thin_picture

    still = [[["p = Picture(program=['x = 1', 'snap()'])"], ["p.show(snap='0')"]]] + [[["eq.box()"]] * 4] * 4
    assert "changes on only 1" in _thin_picture(still).message
    lively = [[["p = Picture(program=['x = 1', 'snap()'])"]] + [["p.show(snap='0')"]] * 6] + [[["eq.box()"]] * 4] * 3
    assert _thin_picture(lively) is None


def test_a_fix_call_that_breaks_the_picture_keeps_the_calls_from_before_it(monkeypatch):
    # runs/h2h: the fix call sent back a program that failed, so code dropped the Picture and all its shows
    from script_generation_agent import storyboard
    from test_storyboard import KU, example_board

    good = "a = cells('a', [3, 1, 2])\nsnap('three', name='s0')\na.mark(0, 'current')\nsnap('first', name='s1')"
    broken = "a = cells('a', [3, 1, 2])\nsnap('three', name='s0')\nb.mark(0, 'current')\nsnap('first', name='s1')"
    plan = storyboard.skeleton(2)
    script = storyboard.assemble(example_board(plan), plan, KU)
    for s, seg in enumerate(script.segments):
        for b, beat in enumerate(seg.beats):
            beat.draw = [picture_call(good)] if (s, b) == (2, 0) else []
    sent = []

    def fake(**kw):
        sent.append(kw["stage"])
        draws = [[picture_call(broken)], ["p.show(snap='s1')"], [], [], []]
        return storyboard._Fixes(segments=[storyboard._SegmentFix(
            segment_index=2, beats=[storyboard._BeatDraw(draw=d) for d in draws])])

    monkeypatch.setattr(storyboard, "structured", fake)
    out = storyboard.settle_picture(script, ku_id="ku-x")
    assert sent == ["storyboard_fix"]
    assert out[2][0] and out[2][0][0].startswith("p = Picture(") and "a.mark(0" in out[2][0][0]
    assert "p.show(snap='s1')" in [c for calls in out[2] for c in calls]


# ---- P5: diagrams (tables, flows, timelines, messages, circuits, memory) and vectors -------------------------

from animation_agent.scene import diagram_layout as DL  # noqa: E402
from animation_agent.scene import math_layout as M2  # noqa: E402
from animation_agent.scene.examples import DIAGRAM_PROGRAMS  # noqa: E402
from animation_agent.visuals.specs import _dialogue_area  # noqa: E402

FULL = _dialogue_area("full")


def test_every_diagram_example_lays_out_in_the_dialogue_frame():
    for name, source in DIAGRAM_PROGRAMS.items():
        L.plan(run(source), *FULL)


def test_a_dp_table_and_a_matrix_product_are_computed():
    assert _captions(DIAGRAM_PROGRAMS["lcs"])["done"] == "the LCS has length 3"
    last = run(DIAGRAM_PROGRAMS["matmul"])[-1]["views"]["C"]
    assert last["values"] == [["19", "22"], ["43", "50"]] and last["matrix"]


@pytest.mark.parametrize("source, why", [
    ("g = grid('g', [[1234567]]); snap()", "longer than 6"),
    ("g = grid('g', [[1, 2], [3]]); snap()", "same number"),
    ("g = grid('g', [[1]]); g[2][0] = 1", "no entry"),
    ("f = flow('f'); f.box('a', shape='star')", "unknown shape"),
    ("f = flow('f'); f.box('a'); f.arrow('a', 'b')", "no box 'b'"),
    ("c = circuit('c'); c.input('a'); c.gate('g', 'NAND', ['a'])", "two or more inputs"),
    ("c = circuit('c'); c.gate('g', 'AND', ['x', 'y'])", "not an input or gate"),
    ("m = memory('m'); m.frame('f'); m.set('f', 'p', m.ref('f')); snap()", "not a heap object"),
    ("s = sequence('s', ['a']); snap()", "2-4 actors"),
    ("t = timeline('t', ['cpu']); t.block('b', 'gpu', 0, 1)", "no lane 'gpu'"),
])
def test_diagram_mistakes_are_sent_back_with_a_reason(source, why):
    result = run_program(source)
    assert not result.ok and why in result.error, result.error


def test_a_table_too_wide_for_the_frame_is_refused_with_the_reason():
    snaps = run("g = grid('g', [['abcdef'] * 8] * 8); snap()")
    with pytest.raises(PictureError, match="wide"):
        L.plan(snaps, *FULL)


def test_a_table_too_wide_across_but_not_on_its_side_is_turned():
    # runs/p5: house painting's DP table, 7 columns of two-digit numbers and three named rows, was 4.6 units wide
    src = ("t = grid('t', [[10, 9, 13, 20, 30, 25, 18], [10, 19, 23, 39, 53, 64, 71], ['P', 'S', 'P', 'P', 'S', 'P', 'P']], "
           "row_names=['pf', 'OPT', 'ch'], col_names=[1, 2, 3, 4, 5, 6, 7])\nt.mark(1, 6, 'found')\nsnap()")
    lay = L.plan(run(src), *FULL).math["t"]
    assert lay.transposed and len(lay.y) == 7 and len(lay.x) == 3
    view = DL.transpose(run(src)[0]["views"]["t"])
    assert view["values"][6][1] == "71" and view["marks"] == {"6,1": "found"} and view["col_names"][0] == "pf"


def test_a_label_too_long_is_left_out_and_a_long_box_text_wraps():
    snaps = run("s = sequence('s', ['A', 'B'])\ns.message('m', 'A', 'B', 'SYN ISN=Y ACK X+1, then a lot more')\n"
                "f = flow('f')\nf.box('a', 'accept the connection')\nf.box('b')\nf.arrow('a', 'b', 'a label far too long')\nsnap()")
    v = snaps[0]["views"]
    assert v["s"]["messages"]["m"]["label"] is None and v["f"]["arrows"][0][3] is None
    assert v["f"]["boxes"]["a"]["text"] == "accept the\nconnection"


def test_seven_messages_fit_the_whole_frame():
    pairs = [("client", "server") if k % 2 == 0 else ("server", "client") for k in range(7)]
    src = "s = sequence('s', ['client', 'server'])\n" + "".join(
        f"s.message('m{k}', '{a}', '{b}', 'SYN {k}')\n" for k, (a, b) in enumerate(pairs)) + "snap()"
    L.plan(run(src), *FULL)


def test_a_long_arrow_passes_the_layers_between_at_a_slot_of_its_own():
    snaps = run(DIAGRAM_PROGRAMS["process"])
    lay = L.plan(snaps, *FULL).math["f"]
    path = lay.arrows["waiting>ready"]
    assert len(path) > 2  # waiting -> ready skips the layer of running: it bends round it
    for key, (c, w, h) in lay.boxes.items():
        if key not in ("waiting", "ready"):
            assert not any(DL._rect_hit(p, q, c, w, h, margin=0.0) for p, q in zip(path, path[1:])), key


def test_an_arrows_label_sits_nearer_its_own_arrow_than_any_other_and_clear_of_every_box():
    for name in ("process", "web", "dfa"):
        lay = L.plan(run(DIAGRAM_PROGRAMS[name]), *FULL).math["f"]
        for (key, text), c in lay.labels.items():
            half = DL.text_half(text) - M2.ROOM
            for box, (bc, w, h) in lay.boxes.items():
                assert not (abs(c[0] - bc[0]) < half[0] + w / 2 and abs(c[1] - bc[1]) < half[1] + h / 2), (name, text, box)
            if key.split(">")[0] != key.split(">")[1]:
                own = DL._path_dist(lay.arrows[key], c)
                assert all(DL._path_dist(p, c) > own for k, p in lay.arrows.items() if k != key), (name, text)


def test_a_state_machine_has_loops_and_an_accepting_state():
    snaps = run(DIAGRAM_PROGRAMS["dfa"])
    lay = L.plan(snaps, *FULL).math["f"]
    assert set(lay.loops) == {"q0>q0", "q2>q2"}
    assert snaps[0]["views"]["f"]["boxes"]["q0"]["shape"] == "double"
    assert _captions(DIAGRAM_PROGRAMS["dfa"])["end"] == "110 is 6: accepted"


def test_round_robin_is_computed_and_drawn_on_its_lanes():
    caps = _captions(DIAGRAM_PROGRAMS["rr"])
    finished = [c for c in caps.values() if "finishes" in c]
    assert finished == ["P3 finishes at t = 5", "P2 finishes at t = 8", "P1 finishes at t = 9"]
    lay = L.plan(run(DIAGRAM_PROGRAMS["rr"]), *FULL).math["tl"]
    assert lay.t == (0.0, 9.0) and not lay.dropped


def test_a_message_label_wider_than_its_lifelines_breaks_them_instead_of_crossing():
    snaps = run("s = sequence('s', ['a', 'b', 'c'])\ns.message('m', 'a', 'c', 'a long label!')\nsnap()")
    lay = L.plan(snaps, *FULL).math["s"]
    c = lay.labels["m"]
    half = DL.text_half("a long label!")
    for i, x in enumerate(lay.x):
        if c[0] - half[0] < x < c[0] + half[0]:
            assert any(g0 <= c[1] - half[1] + M2.ROOM and c[1] + half[1] - M2.ROOM <= g1 for g0, g1 in lay.gaps[i])


def test_a_full_adder_adds_every_row_of_its_truth_table():
    for a in (0, 1):
        for b in (0, 1):
            for ci in (0, 1):
                src = DIAGRAM_PROGRAMS["adder"].split("for bits")[0] + (
                    f"c.set('A', {a}); c.set('B', {b}); c.set('Ci', {ci})\n"
                    "snap(str(c.value('Co')) + str(c.value('S')), name='r')")
                assert _captions(src)["r"] == format(a + b + ci, "02b")


def test_no_circuit_wire_crosses_a_part_or_runs_along_another():
    lay = L.plan(run(DIAGRAM_PROGRAMS["adder"]), *FULL).math["c"]
    for key, path in lay.wires.items():
        src, dst = key.split(">")[0], key.split(">")[1].split("#")[0]
        for part, c in lay.pos.items():
            if part in (src, dst):
                continue
            w, h = lay.size[part]
            assert not any(DL._rect_hit(p, q, c, w, h, margin=0.0) for p, q in zip(path, path[1:])), (key, part)


def test_a_circuit_too_deep_for_the_frame_is_refused_with_the_reason():
    chain = "c = circuit('c')\nc.input('a')\nprev = 'a'\nfor k in range(9):\n    c.gate('g' + str(k), 'NOT', [prev])\n    prev = 'g' + str(k)\nc.output('y', prev)\nsnap()"
    with pytest.raises(PictureError, match="levels"):
        L.plan(run(chain), *FULL)


def test_a_pointer_is_an_arrow_from_its_field_to_the_object():
    snaps = run(DIAGRAM_PROGRAMS["linked"])
    lay = L.plan(snaps, *FULL).math["m"]
    last = snaps[-1]["views"]["m"]
    arrows = DL.memory_arrows(last, lay)
    assert set(arrows) == {"main.head", "n0.next", "n2.next"}
    left, top, w, _h = lay.boxes["n2"]
    assert arrows["main.head"][-1] == (left, top - DL.BOX_TITLE_H / 2)  # into the new node's title row


def test_a_vector_is_labelled_past_its_tip_and_a_grid_is_sent_through_its_matrix():
    snaps = run(DIAGRAM_PROGRAMS["eigen"])
    lay = L.plan(snaps, *FULL).math["a"]
    assert {t for _k, t in lay.labels} == {"v", "w", "Av", "Aw"}
    before, after = (s["views"]["a"]["items"]["g"]["pieces"] for s in snaps)
    assert after[0] == [[2 * p[0] + p[1], p[0] + 2 * p[1]] for p in before[0]]


def test_text_widths_count_capitals_wider_than_small_letters():
    assert M2.text_width("SYN-ACK") > M2.text_width("syn-ack") > M2.text_width("iiiiiii")
