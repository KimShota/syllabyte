"""
The worked examples in the storyboard prompt: one whole storyboard per level, each on an idea that is not one of
the pilots, filled in the way the writer should fill that level's plan:

  - Level 1 (Foundations): a matrix times a vector, a full step-by-step worked example, plain words, one analogy;
  - Level 2 (Core): linear search, one worked example with the key steps;
  - Level 3 (Advanced): insertion sort, a "what if the input is already sorted?" with no worked example.

They use different templates (a grid with a formula, a list of cells, bars), so the writer sees each in use.
tests/test_storyboard.py checks that each matches skeleton(level), passes validate_dialogue and the call checker
with nothing for code to fix, so the prompt never shows a storyboard the pipeline would reject.

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
         "You'll be able to count the checks linear search makes, from the first cell to the last."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         ["lst.clear()", "lst.scan(index=0, target=7)"],
         "{peer}, if seven is here, how many cells do we check?"),
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
         "Pause: how many checks to reach the last cell?"),
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

EXAMPLE_L1_KU = "Multiplying a matrix by a vector: each row of the matrix gives one part of the result"

EXAMPLE_L1 = {
    "title": "Where a matrix sends a vector",
    "colour_key": [{"term": "vector", "colour": "GOLD"}, {"term": "matrix", "colour": "BLUE"}],
    "prepare": [
        ("b1_peer_question",
         ['grid = LinearMap2D(matrix=[[2, 0], [1, 1]], vectors=[{"name": "v", "x": 1, "y": 2, "colour": "GOLD"}], extent=4)'],
         "Lowkey, what happens when you multiply a grid of numbers by an arrow?"),
        ("b2_explainer_build",
         ["grid.apply(keep_ghost=True)"],
         "It moves the arrow somewhere new, like a machine that reshapes the whole grid."),
    ],
    "initiate": [
        ("b1_peer_question",
         ["grid.reset()"],
         "Okay, but why would I ever work that out by hand?"),
        ("b2_explainer_objective",
         ["grid.show_matrix()"],
         "You'll be able to work out where a matrix sends a vector, one step at a time."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         ['grid.highlight_vector(name="v", colour="YELLOW")'],
         "{peer}, a matrix is a number grid. Does it just stretch arrows?"),
        ("b2_peer_answer_wrong_idea",
         ['grid.ghost_vector(x=1.5, y=3, name="v?")'],
         "Not gonna lie, I'd guess it only stretches the arrow, same direction."),
        ("b3_explainer_feedback",
         ["grid.clear_ghosts()", "grid.apply()"],
         "Not always, because the matrix mixes the arrow's two parts, so its direction can change too."),
        ("b4_peer_build",
         [r'grid.note(tex="(1, 2) \to (2, 3)")'],
         "So the arrow at one, two landed at two, three: a new direction."),
        ("b5_explainer_build",
         ["grid.reset()", "grid.apply(keep_ghost=True)"],
         "Right: a matrix moves every vector, changing its length, its direction, or both."),
    ],
    "deliver_2": [
        ("b1_explainer_build",
         ["grid.reset()", 'grid.remove_vector(name="v")', 'grid.add_vector(name="u", x=2, y=1, colour="GOLD")'],
         "Let's work it out for the vector two, one, with the same matrix."),
        ("b2_peer_question",
         [r'eq = EquationSteps(tex="A u = (?, ?)")'],
         "For real, how do we even start on the first number?"),
        ("b3_explainer_build",
         [r'eq.then(tex="2 \cdot 2 + 0 \cdot 1 = 4")'],
         "Top row, two and zero, times two and one: four plus zero, four."),
        ("b4_peer_question",
         [r'eq.highlight(part="2 \cdot 2 + 0 \cdot 1")'],
         "Why does the top row give us the top number?"),
        ("b5_explainer_feedback",
         ['grid.highlight_vector(name="u", colour="YELLOW")'],
         "Because each row of the matrix builds one part of the answer, in order."),
        ("b6_explainer_predict",
         [r'eq.then(tex="1 \cdot 2 + 1 \cdot 1 = ?")'],
         "Pause: bottom row is one and one. What's the bottom number?"),
        ("b7_peer_build",
         [r'eq.rewrite(tex="1 \cdot 2 + 1 \cdot 1 = 3")', "grid.apply()"],
         "One times two plus one times one is three: u lands at four, three."),
    ],
    "end": [
        ("b1_peer_check",
         ["eq.box()"],
         "So a matrix moves a vector, and each row gives one part of the result."),
        ("b2_explainer_check",
         ['grid.highlight_vector(name="u", colour="GOLD")'],
         "Exactly: one row times the vector for each part of the answer."),
    ],
}

EXAMPLE_L3_KU = "Insertion sort: its cost depends on how sorted the input already is"

EXAMPLE_L3 = {
    "title": "Insertion sort's cost follows the input",
    "colour_key": [{"term": "values", "colour": "BLUE"}, {"term": "comparisons", "colour": "TEAL"}],
    "prepare": [
        ("b1_peer_question",
         ['bars = ArrayBars(values=[5, 2, 4, 1, 3], style="bars", title="unsorted")'],
         "Lowkey, why does insertion sort feel instant on some lists and slow on others?"),
        ("b2_explainer_build",
         ["bars.insertion_step()"],
         "Its work depends on how far each value travels left to reach its place."),
    ],
    "initiate": [
        ("b1_peer_question",
         [],
         "Okay, so what should I be able to judge after this?"),
        ("b2_explainer_objective",
         ["bars.highlight(indices=[3])"],
         "You'll be able to predict insertion sort's cost from how far a value like one must travel."),
    ],
    "deliver_1": [
        ("b1_explainer_question",
         ["bars.highlight(indices=[2])"],
         "{peer}, does insertion sort compare four with every value before it?"),
        ("b2_peer_answer_wrong_idea",
         ['bars.ghost(indices=[0, 1], text="compare with all?")'],
         "Not gonna lie, I'd say yes, every earlier value, no matter what."),
        ("b3_explainer_feedback",
         ["bars.clear()", "bars.insertion_step()"],
         "No: four moves left only past larger values, and stops at the first smaller one."),
        ("b4_peer_build",
         ["bars.insertion_step()"],
         "So one goes all the way to the front: it's smaller than all of them."),
        ("b5_explainer_build",
         ["bars.insertion_step()"],
         "Right: comparisons count how far values travel, so the input's order sets the cost."),
    ],
    "deliver_2": [
        ("b1_peer_question",
         ['bars = ArrayBars(values=[1, 2, 3, 4, 5], style="bars", title="already sorted")'],
         "For real, what if the list arrives already sorted?"),
        ("b2_peer_answer_wrong_idea",
         ['bars.ghost(indices=[0, 1, 2, 3, 4], text="every pair anyway?")'],
         "Then I'd guess it still compares every pair, just without swapping."),
        ("b3_explainer_predict",
         ["bars.clear()", 'bars.point(name="i", index=1)'],
         "Pause: how many comparisons does it make on five sorted values?"),
        ("b4_explainer_feedback",
         ['bars.unpoint(name="i")', "bars.insertion_step()", "bars.insertion_step()", "bars.insertion_step()",
          "bars.insertion_step()"],
         "Only four: each new value meets a smaller left neighbour at once, so it stops."),
        ("b5_peer_build",
         ['bars.highlight(indices=[0, 1, 2, 3, 4], colour="TEAL")'],
         "So sorted input costs one comparison per new value, and not a single move."),
        ("b6_explainer_build",
         ['bars = ArrayBars(values=[5, 4, 3, 2, 1], style="bars", title="reversed")'],
         "Exactly: nearly sorted lists take linear time, while reversed ones need about n squared."),
    ],
    "end": [
        ("b1_peer_check",
         ["bars.insertion_step()"],
         "So insertion sort's cost tracks how far its input is from sorted."),
        ("b2_explainer_check",
         ["bars.insertion_step()"],
         "Yes, which is why it suits data that is already nearly in order."),
    ],
}

EXAMPLES = {1: (EXAMPLE_L1_KU, EXAMPLE_L1), 2: (EXAMPLE_KU, EXAMPLE), 3: (EXAMPLE_L3_KU, EXAMPLE_L3)}

SEGMENT_KEYS = ["prepare", "initiate", "deliver_1", "deliver_2", "end"]


def render_example(*, explainer: str, peer: str, level: int = 2) -> str:
    """The level's example as the prompt shows it: each beat's field, its calls, then its line."""
    ku, example = EXAMPLES[level]
    lines = [f"Knowledge Unit: {ku}", f"title: {example['title']}",
             "colour_key: " + ", ".join(f"{t['term']} = {t['colour']}" for t in example["colour_key"])]
    for key in SEGMENT_KEYS:
        lines.append(f"{key}:")
        for field, draw, narration in example[key]:
            lines.append(f"  {field}:")
            lines.append(f"    draw: {draw}")
            lines.append(f"    narration: {narration.format(explainer=explainer, peer=peer)}")
    return "\n".join(lines) + "\n"
