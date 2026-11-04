"""
The worked example in the storyboard prompt: a whole Level 2 storyboard, on an idea that is not one of the pilots
(linear search), filled in the way the writer should fill its plan. tests/test_storyboard.py checks that it
matches skeleton(2), passes validate_dialogue and the call checker with nothing for code to fix, so the prompt
never shows a storyboard the pipeline would reject.

{explainer} and {peer} are the cast's names.
"""

from __future__ import annotations

EXAMPLE_KU = "Linear search: checking a list one cell at a time, and counting the checks"

EXAMPLE = {
    "title": "Linear search, one check at a time",
    "colour_key": [{"term": "list", "colour": "BLUE"}, {"term": "target", "colour": "GOLD"}],
    "prepare": [
        ("b1_peer_question",
         ['lst = ArrayBars(values=[4, 9, 2, 7, 5, 1], title="unsorted list")', 'q = Note(text="where is 7?", colour="GOLD")'],
         "Lowkey, how does a program find one number in a list it can't see?"),
        ("b2_explainer_build",
         ["q.remove()", 'lst.point(name="i", index=0)'],
         "It looks at one cell at a time, starting from the very first one."),
    ],
    "initiate": [
        ("b1_peer_question",
         [],
         "Okay, but why should I care how many cells it looks at?"),
        ("b2_explainer_objective",
         ['lst.highlight(indices=[0, 5], colour="TEAL")'],
         "You'll be able to count the checks linear search makes, in the best and worst case."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         ["lst.clear()", "lst.scan(index=0, target=7)"],
         "{peer}, if seven is somewhere in this list, how many cells do we check?"),
        ("b2_peer_answer_wrong_idea",
         ['lst.ghost(indices=[3], text="jump straight to 7?")'],
         "Not gonna lie, just one: we jump straight to seven."),
        ("b3_explainer_feedback",
         ["lst.clear()", "lst.scan(index=1, target=7)", "lst.scan(index=2, target=7)"],
         "We can't jump, because nothing tells us where seven is, so we check each cell in order."),
        ("b4_peer_build",
         ["lst.scan(index=3, target=7)"],
         "So we keep checking until a cell matches seven, right here."),
        ("b5_explainer_build",
         ["lst.found(index=3)"],
         "Right, that took four checks: one for each cell up to the match."),
    ],
    "deliver_2": [
        ("b1_explainer_build",
         ["lst.restore()", "lst.clear()", 'lst.counter(label="checks", value=0)', 'lst.point(name="i", index=0)'],
         "Now search the same list for one, which sits in the last cell."),
        ("b2_peer_question",
         ['lst.highlight(indices=[5], colour="GOLD")'],
         "For real, why can't the search just skip ahead to the end?"),
        ("b3_explainer_feedback",
         ["lst.scan(index=0, target=1)", "lst.scan(index=1, target=1)", "lst.scan(index=2, target=1)"],
         "Because any cell could hold it, and a skipped cell might be the match."),
        ("b4_explainer_predict",
         ["lst.scan(index=3, target=1)", "lst.scan(index=4, target=1)"],
         "Pause here: how many checks will it take to reach the last cell?"),
        ("b5_peer_build",
         ["lst.scan(index=5, target=1)"],
         "Six checks, one per cell, because one is at the very end."),
        ("b6_explainer_build",
         ["lst.found(index=5)"],
         "Yes, six checks for six cells: the worst case looks at every cell."),
    ],
    "end": [
        ("b1_peer_check",
         ['lst.highlight(indices=[0, 1, 2, 3, 4, 5], colour="TEAL")'],
         "So linear search checks the cells one by one, each at most once."),
        ("b2_explainer_check",
         ['lst.point(name="i", index=5)'],
         "Exactly, and in the worst case it checks every cell before it finds the target."),
    ],
}

SEGMENT_KEYS = ["prepare", "initiate", "deliver_1", "deliver_2", "end"]


def render_example(*, explainer: str, peer: str) -> str:
    """The example as the prompt shows it: each beat's field, its calls, then its line."""
    lines = [f"Knowledge Unit: {EXAMPLE_KU}", f"title: {EXAMPLE['title']}",
             "colour_key: " + ", ".join(f"{t['term']} = {t['colour']}" for t in EXAMPLE["colour_key"])]
    for key in SEGMENT_KEYS:
        lines.append(f"{key}:")
        for field, draw, narration in EXAMPLE[key]:
            lines.append(f"  {field}:")
            lines.append(f"    draw: {draw}")
            lines.append(f"    narration: {narration.format(explainer=explainer, peer=peer)}")
    return "\n".join(lines) + "\n"
