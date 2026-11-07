"""Data structures and algorithms: what each new template and action computes, against known answers, and what it
refuses. No Manim, no LLM. Their examples render (both frames, no layout findings) in test_visual_templates.py with
SYLLABYTE_RENDER_TESTS=1."""

from __future__ import annotations

import pytest

from animation_agent.visuals.calls import check_segment, describe_segment, live_after
from animation_agent.visuals.families import main_template


def said(*beats):
    assert check_segment(list(beats)) == []
    return describe_segment(list(beats))


def state(*calls, name):
    """The object's state after these calls, one beat each."""
    return live_after([[[c] for c in calls]])[name].state


# ---- LinkedList --------------------------------------------------------------------------------------------------

LL = "l = LinkedList(values=[3, 8, 5, 1])"


def test_a_list_reverses_in_place_one_link_at_a_time():
    out = said([LL], *[["l.reverse_step()"]] * 4)
    assert out[1] == "The node holding 3 now points back to null; prev moves to 3, curr to 8."
    assert out[4].endswith("head moves to 1: the list reads 1 -> 5 -> 8 -> 3 -> null.")


def test_insert_delete_find_and_pointers_rewire_the_links():
    out = said(["l = LinkedList(values=[1, 4, 9])"], ["l.insert(index=1, value=7)"], ["l.delete(index=0)"],
               ['l.point(name="p", index=0)', 'l.advance(name="p")'], ["l.find_step(value=9)"] * 3)
    assert out[1] == "A new node 7 is linked in at position 1: 1 -> 7 -> 4 -> 9 -> null."
    assert out[2] == "The node holding 1 is unlinked: 7 -> 4 -> 9 -> null."
    assert out[3].endswith('"p" moves from 7 to 4.')
    assert out[4].endswith("it matches 9 and turns green.")
    assert '"p" is null' in check_segment([[LL], ['l.point(name="p", index=None)', 'l.advance(name="p")']])[0]
    assert "1-5" in check_segment([["l = LinkedList(values=[1, 2, 3, 4, 5, 6])"]])[0]


# ---- StackQueue -------------------------------------------------------------------------------------------------

def test_stacks_queues_and_call_stacks_give_what_they_should():
    out = said(['s = StackQueue(kind="stack", values=[1, 2])'], ['s.push(value=3)'], ["s.pop()"], ["s.peek()"])
    assert out[2] == "Pop takes 3 off the top; bottom to top: 1, 2."
    assert out[3].startswith("Peek shows 2 without removing it")
    q = said(['q = StackQueue(kind="queue", values=[4, 7])'], ["q.enqueue(value=9)"], ["q.dequeue()"])
    assert q[2] == "Dequeue takes 4 from the front; front to rear: 7, 9."
    c = said(['c = StackQueue(kind="call_stack", values=["f(2)"])'], ['c.push(value="f(1)")'], ["c.pop(returns=1)"])
    assert c[2].startswith("The call f(1) returns 1 to the frame below")
    assert "empty" in check_segment([['s = StackQueue(kind="stack")'], ["s.pop()"]])[0]
    assert "has no dequeue" in check_segment([['s = StackQueue(kind="stack", values=[1])'], ["s.dequeue()"]])[0]


# ---- HashTable -------------------------------------------------------------------------------------------------

def test_hashing_chains_and_probes_are_computed():
    out = said(["h = HashTable(size=7, keys=[10, 22])"], ["h.insert(key=31)"], ["h.find(key=24)"], ["h.load()"])
    assert out[1] == "The hash h(31) = 31 mod 7 = 3; bucket 3 already holds 10, so 31 joins its chain."
    assert out[2].endswith("not there, after 2 checks.")
    assert "0.43 keys per bucket" in out[3]
    p = said(['h = HashTable(size=5, mode="probing", keys=[5, 10])'], ["h.insert(key=15)"], ["h.find(key=15)"])
    assert p[1].endswith("buckets 0, 1 are taken, so 15 goes in bucket 2.")
    assert p[2].endswith("found in bucket 2 after 3 checks.")
    assert "tombstone" in check_segment([['h = HashTable(size=5, mode="probing", keys=[5])'],
                                         ["h.delete(key=5)"]])[0]


# ---- BinaryTree ------------------------------------------------------------------------------------------------

BST = 't = BinaryTree(kind="bst", values=[8, 3, 10, 1, 6, 14, 4, 7])'


def test_bst_insert_search_and_the_three_delete_cases():
    out = said([BST], ["t.insert(value=5)"], ["t.search(value=7)"], ["t.delete(value=3)"], ["t.delete(value=1)"],
               ["t.delete(value=10)"])
    assert out[1] == "5 < 8, go left; 5 > 3, go right; 5 < 6, go left; 5 > 4, go right; 5 becomes 4's right child."
    assert out[2].endswith("7 is found after 4 comparisons.")
    assert out[3].startswith("3 has two children, so its in-order successor 4")
    assert out[4] == "1 is a leaf and is simply removed."
    assert out[5] == "10 has one child, 14, which takes its place."
    assert "levels deep" in check_segment([['t = BinaryTree(kind="bst", values=[1, 2, 3, 4, 5, 6])']])[0]


def test_traversals_visit_in_their_orders():
    st = state(BST, *['t.traverse_step(order="inorder")'] * 8, name="t")
    assert st["trav"]["seq"] == [1, 3, 4, 6, 7, 8, 10, 14]
    from animation_agent.visuals.specs import bt_new, bt_order

    tree = bt_new("bst", [8, 3, 10, 1, 6])
    assert bt_order(tree, "preorder") == [8, 3, 1, 6, 10] and bt_order(tree, "postorder") == [1, 6, 3, 10, 8]
    assert bt_order(tree, "level") == [8, 3, 10, 1, 6]


def test_heaps_rise_sink_and_heapify():
    out = said(['h = BinaryTree(kind="min_heap", values=[2, 5, 4, 9])'], ["h.push(value=1)"], ["h.pop()"])
    assert out[1].endswith("the array reads 1, 2, 4, 9, 5.")
    assert out[2].startswith("The root 1, the smallest, comes out") and out[2].endswith("2, 5, 4, 9.")
    heap = state('h = BinaryTree(kind="max_heap", values=[3, 1, 6, 5, 2, 4])', "h.heapify()", name="h")["heap"]
    assert heap[0] == 6 and all(heap[i] >= heap[c] for i in range(len(heap)) for c in (2 * i + 1, 2 * i + 2)
                                if c < len(heap))
    assert "already" in check_segment([['t = BinaryTree(kind="bst", values=[8, 3, 1])'],
                                       ['t.ghost(parent=3, side="left", value=2, text="x")']])[0]


# ---- Graph algorithms --------------------------------------------------------------------------------------------

G = ('g = Graph(nodes=["A", "B", "C", "D", "E"], edges=[["A", "B", "4"], ["A", "C", "1"], ["C", "B", "2"], '
     '["B", "D", "5"], ["C", "D", "8"], ["D", "E", "3"]])')


def test_dijkstra_settles_nodes_in_distance_order():
    st = state(G, *['g.dijkstra_step(start="A")'] * 5, name="g")
    assert st["algo"]["dist"] == {"A": 0, "B": 3, "C": 1, "D": 8, "E": 11}
    assert st["algo"]["settled"] == ["A", "C", "B", "D", "E"]


def test_prim_and_kruskal_find_the_same_minimum_spanning_tree():
    prim = state(G, *['g.prim_step(start="A")'] * 5, name="g")["algo"]
    kruskal = state(G, *["g.kruskal_step()"] * 5, name="g")["algo"]
    assert prim["total"] == kruskal["total"] == 11
    assert "would close a cycle" in said([G], *[["g.kruskal_step()"]] * 4)[4]
    assert "needs a weight on every edge" in check_segment([['g = Graph(nodes=["a", "b"], edges=[["a", "b"]])'],
                                                            ['g.dijkstra_step(start="a")']])[0]


def test_topological_order_and_a_cycle():
    dag = 'g = Graph(nodes=["a", "b", "c", "d"], edges=[["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]], directed=True)'
    assert state(dag, *["g.topo_step()"] * 4, name="g")["algo"]["order"] == ["a", "b", "c", "d"]
    cyc = 'g = Graph(nodes=["a", "b"], edges=[["a", "b"], ["b", "a"]], directed=True)'
    assert "form a cycle" in said([cyc], ["g.topo_step()"])[1]


# ---- Quicksort's partition and DP tables -----------------------------------------------------------------------

def test_lomuto_partition_places_the_pivot_between_the_sides():
    st = state('a = ArrayBars(values=[7, 2, 9, 4, 5])', *["a.partition_step()"] * 5, name="a")
    assert st["values"] == [2, 4, 5, 7, 9] and 2 in st["found"]


@pytest.mark.parametrize("create, last, expected", [
    ('t = Table(rule="lcs", s="ABCB", t="BDCB")', (4, 4), "3"),
    ('t = Table(rule="edit_distance", s="kitten", t="sitin")', (6, 5), "3"),
    ('t = Table(rule="knapsack", weights=[1, 3, 4], values=[15, 20, 30], capacity=4)', (3, 4), "35"),
    ('t = Table(rule="coin_change", coins=[1, 3, 4], amount=5)', (0, 5), "2"),
])
def test_dp_tables_fill_to_the_known_answer(create, last, expected):
    cells = state(create, *["t.fill_row()"] * 8, name="t")["cells"]
    assert cells[last[0]][last[1]] == expected


def test_the_picture_kinds_go_to_their_structure():
    for family, template in {"linked_list": "LinkedList", "stack_queue": "StackQueue", "hash_table": "HashTable",
                             "tree": "BinaryTree"}.items():
        assert main_template(family) == template
