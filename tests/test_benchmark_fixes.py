"""
The fixes for the pictures runs/bench1 lost (scripts/visual_benchmark.py, plan/visual-coverage-plan.md): each test
is a shortened copy of a refused program, which now draws.
"""

from __future__ import annotations

import numpy as np
import pytest

from animation_agent.scene import diagram_layout as D
from animation_agent.scene import layout as L
from animation_agent.scene.sandbox import run_program

DIALOGUE = (3.9, 4.8, 2.4)


def run(source: str) -> list[dict]:
    result = run_program(source)
    assert result.ok, result.error
    return result.snapshots


def fits(source: str) -> L.Layout:
    return L.plan(run(source), *DIALOGUE)


@pytest.mark.parametrize("colour,style", [("teal", "visited"), ("green", "found"), ("purple", "blue"),
                                          ("Orange", "compare")])
def test_a_colour_word_is_drawn_as_its_style(colour, style):
    snaps = run(f"c = cells('c', [1, 2]); c.mark(0, '{colour}'); snap()")
    assert snaps[0]["views"]["c"]["marks"]["0"] == style


MERGE_SORT = """t = nodes('t')
t.add('r', 'all')
t.add('A', keys=[38, 27, 43]); t.link('r', 'A')
t.add('B', keys=[3, 9, 82, 10]); t.link('r', 'B')
t.add('A1', keys=[38, 27]); t.link('A', 'A1'); t.add('A2', keys=[43]); t.link('A', 'A2')
t.add('B1', keys=[3, 9]); t.link('B', 'B1'); t.add('B2', keys=[82, 10]); t.link('B', 'B2')
for k, v, p in (('a1', 38, 'A1'), ('a2', 27, 'A1'), ('b1', 3, 'B1'), ('b2', 9, 'B1'), ('b3', 82, 'B2'),
                ('b4', 10, 'B2')):
    t.add(k, keys=[v]); t.link(p, k)
snap()
"""


def test_a_tree_gives_each_node_its_own_width():
    # every leaf used to get the 4-key node's width: "a tree is 2 nodes wide; at most 1 fit across the frame"
    lay = fits(MERGE_SORT)
    view = run(MERGE_SORT)[0]["views"]["t"]
    pos = L.layout_nodes(view, lay.regions["t"], None, lay.nodes["t"])
    region = lay.regions["t"]
    for k, n in view["nodes"].items():  # inside the band
        half = max(L.node_w(n), 2 * lay.nodes["t"].r) / 2
        assert region.cx - region.w / 2 - 1e-6 <= pos[k][0] - half
        assert pos[k][0] + half <= region.cx + region.w / 2 + 1e-6
    by_level: dict[float, list[str]] = {}
    for k, p in pos.items():
        by_level.setdefault(round(float(p[1]), 3), []).append(k)
    for keys in by_level.values():  # no two nodes of a level touch
        keys.sort(key=lambda k: pos[k][0])
        for a, b in zip(keys, keys[1:]):
            room = (max(L.node_w(view["nodes"][a]), 0.4) + max(L.node_w(view["nodes"][b]), 0.4)) / 2
            assert pos[b][0] - pos[a][0] >= room + 0.05


def test_a_wide_parent_centres_its_children_under_it():
    snaps = run("t = nodes('t'); t.add('p', keys=[1, 2, 3, 4]); t.add('c', 'x'); t.link('p', 'c'); snap()")
    lay = L.plan(snaps, *DIALOGUE)
    pos = L.layout_nodes(snaps[0]["views"]["t"], lay.regions["t"], None, lay.nodes["t"])
    assert abs(pos["p"][0] - pos["c"][0]) < 1e-6


def test_a_dom_tree_with_word_labels_fits():
    fits("""t = nodes('t')
for k, lab, p in (('h', 'html', None), ('hd', 'head', 'h'), ('b', 'body', 'h'), ('t1', 'title', 'hd'),
                  ('h1', 'h1', 'b'), ('ul', 'ul', 'b'), ('l1', 'li', 'ul'), ('l2', 'li', 'ul')):
    t.add(k, lab)
    if p:
        t.link(p, k)
snap()""")


def test_actor_names_that_dont_fit_side_by_side_are_staggered():
    xs, ws, drop = D.actor_boxes(["Browser", "DNS", "Server"], 3.7)
    assert drop == [0.0, D.STAGGER, 0.0]
    assert xs[2] - xs[0] >= (ws[0] + ws[2]) / 2 + D.ACTOR_GAP - 1e-9  # the top row's boxes apart
    for i, j in ((0, 1), (1, 0), (1, 2), (2, 1)):  # no lifeline through another row's box
        assert abs(xs[i] - xs[j]) >= ws[j] / 2 + D.LIFE_ROOM - 1e-9
    assert D.actor_boxes(["a", "b"], 3.7)[2] == [0.0, 0.0]
    fits("s = sequence('s', ['Browser', 'DNS', 'Server'])\ns.message('q', 0, 1, 'lookup')\n"
         "s.message('r', 1, 0, 'IP', dashed=True)\ns.message('g', 0, 2, 'GET /')\nsnap()")


UML = """f = flow('f', title='class diagram')
f.box('animal', 'Animal', fields=['- name: String', '+ speak()'], layer=0)
f.box('dog', 'Dog', fields=['+ speak(): String', '+ fetch(): void'], layer=1)
f.box('cat', 'Cat', fields=['+ speak(): String', '+ purr(): void'], layer=1)
f.arrow('dog', 'animal', kind='inherit')
f.arrow('cat', 'animal', kind='inherit')
snap()
"""


def test_a_layer_too_wide_for_the_frame_takes_two_rows():
    snaps = run(UML)
    lay = L.plan(snaps, *DIALOGUE)
    flow = lay.math["f"]
    ys = {k: round(float(flow.boxes[k][0][1]), 3) for k in ("animal", "dog", "cat")}
    assert ys["animal"] > ys["dog"] > ys["cat"]
    region = lay.regions["f"]
    for c, w, _h in flow.boxes.values():
        assert region.cx - region.w / 2 - 1e-6 <= c[0] - w / 2 and c[0] + w / 2 <= region.cx + region.w / 2 + 1e-6


def test_boxes_never_on_screen_together_share_a_place():
    source = """f = flow('f')
f.box('date', 'Date: free text', layer=0); f.box('pw', 'Password rules hidden', layer=1)
snap()
f.remove('date'); f.box('date2', 'Date picker', layer=0)
snap()"""
    snaps = run(source)
    flow = L.plan(snaps, *DIALOGUE).math["f"]
    assert np.allclose(flow.boxes["date"][0], flow.boxes["date2"][0])


def test_a_memory_diagram_too_wide_side_by_side_is_stacked():
    source = """m = memory('m', title='aliasing')
m.frame('g', title='globals')
m.obj('L', title='list obj'); m.set('L', 'item0', 'apple'); m.set('L', 'item1', 'banana')
m.set('g', 'mylist', m.ref('L'))
m.obj('C', title='list copy'); m.set('C', 'item0', 'apple'); m.set('C', 'item1', 'banana')
m.set('g', 'copy', m.ref('C'))
snap()"""
    snaps = run(source)
    side, stacked, _s, _h = D._memory_widths([snaps[0]["views"]["m"]])
    assert side > 3.9 > stacked
    lay = L.plan(snaps, *DIALOGUE).math["m"]
    assert lay.stacked
    assert lay.boxes["g"][1] > lay.boxes["L"][1] > lay.boxes["C"][1]  # the frame above the objects
    arrows = D.memory_arrows(snaps[0]["views"]["m"], lay)
    lanes = {round(path[1][0], 3) for path in arrows.values()}
    assert len(lanes) == len(arrows)  # each pointer in a lane of its own


def test_a_table_may_use_the_spare_edge_of_its_band():
    # runs/bench1: a stack table 3.71 units wide in a band whose usual spare left 3.70
    rows = [["buf[8]", "8 bytes"], ["sv FP", "8 bytes"], ["ret ad", "8 bytes"]]
    view = {"title": None, "values": rows, "row_names": ["low", "mid", "high"], "col_names": ["slot", "bytes"],
            "matrix": False, "marks": {}, "heat": None}
    total = D._grid_width([view])
    lay = D.grid_layout([view], L.Region(0.0, 1.0, total + 0.06, 3.0))
    assert lay.right - lay.left <= total + 0.02
    with pytest.raises(Exception, match="units wide"):
        D.grid_layout([view], L.Region(0.0, 1.0, total + 0.02, 3.0))


def test_longer_words_are_allowed_where_the_layout_measures_them():
    run("g = grid('g', [['saved FP', 'ret addr']]); snap()")
    run("m = memory('m'); m.frame('f', title='make_counter()'); m.set('f', 'count', '[1, 2, 3]'); snap()")
    run("t = nodes('t'); t.add('a', 'title'); snap()")
    run("f = flow('f'); f.box('a', 'Account', fields=['- id: int', '- owner: String', '- balance: float', "
        "'+ deposit(x)', '+ withdraw(x)', '+ statement()']); snap()")


def test_a_snapshot_before_the_trees_first_node_lays_out():
    # runs/bench2: a DOM tree whose first snapshot showed the empty view crashed the render
    snaps = run("t = nodes('t')\nsnap()\nt.add('a', 'html')\nsnap()")
    lay = L.plan(snaps, *DIALOGUE)
    assert L.layout_nodes(snaps[0]["views"]["t"], lay.regions["t"], None, lay.nodes["t"]) == {}


def test_a_picture_of_space_is_never_turned_on_its_side():
    plate = [[100] * 5] + [[0] * 5 for _ in range(4)]
    view = {"title": None, "values": [[str(x) for x in r] for r in plate], "row_names": None, "col_names": None,
            "matrix": False, "marks": {}, "heat": None}
    assert D._turned([view], 1.0) == [view]  # square
    wide = {**view, "values": [["10"] * 8] * 4, "turn": False}
    assert D._turned([wide], 1.0) == [wide]
    assert D._turned([{**wide, "turn": True}], 1.0) != [{**wide, "turn": True}]
    assert run("g = grid('g', [[1, 2]], turn=False); snap()")[0]["views"]["g"]["turn"] is False


def test_labels_left_out_are_sent_back_to_the_planner():
    from script_generation_agent.snapshot_beats import dropped_labels

    snaps = run("tl = timeline('tl', ['A', 'B'], t=(0, 6))\n"
                "for k, (lane, a, lab) in enumerate([('A', 0, 'load 5'), ('B', 1, 'load 5'), ('A', 2, 'add 6'),\n"
                "                                    ('A', 3, 'store 6'), ('B', 4, 'add 6'), ('B', 5, 'store 6')]):\n"
                "    tl.block('b' + str(k), lane, a, a + 1, lab)\nsnap()")
    problems = dropped_labels(snaps)
    assert problems and "'store 6'" in problems[0]
    assert dropped_labels(run("c = cells('c', [1, 2]); snap()")) == []


def test_a_snapshot_before_a_flow_diagrams_first_box_lays_out():
    # runs/bench3: a flow view snapped empty raised ValueError out of the checker and ended the whole run
    snaps = run("f = flow('f')\nsnap()\nf.box('a', 'start')\nsnap()")
    groups = L.plan_groups(snaps, *DIALOGUE)
    assert len(groups) >= 1


def test_a_layout_bug_is_a_refusal_not_a_crash(monkeypatch):
    from animation_agent.visuals import specs

    def boom(*_a, **_k):
        raise ValueError("max() iterable argument is empty")

    monkeypatch.setattr("animation_agent.scene.layout.plan_groups", boom)
    specs._picture_problem.cache_clear()
    problem = specs._picture_problem("c = cells('c', [1, 2])\nsnap()", "full")
    specs._picture_problem.cache_clear()
    assert problem is not None and "can't be laid out" in problem
