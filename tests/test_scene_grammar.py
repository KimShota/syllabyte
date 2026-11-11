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
