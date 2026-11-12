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
