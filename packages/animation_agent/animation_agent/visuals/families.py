"""
The kinds of picture a lesson needs (families), and which templates draw each one. No Manim import.

A KU's planned visual is sorted into one family (script_generation_agent.picture_plan, the same classifier as the
coverage study, scripts/visual_coverage.py). The storyboard is then given only the templates that draw that family,
plus formulas and notes, which sit beside any picture. In the course test (runs/course-test-1) the writer saw every
template and, when none fitted, borrowed one drawn for something else: DFS as a row of cells, XOR's four points as
vectors on a linear-map grid, "recursive thinking" as a rotation matrix. Choosing the templates in code stops that.
"""

from __future__ import annotations

# What each family draws (plan/visual-template-library-plan.md, "Template families"), as the classifier reads it.
FAMILIES: dict[str, str] = {
    # CS
    "array_bars": "a list/array as cells or bars: searching, sorting, pointers, halves, swaps",
    "merge_sort": "merge sort and merging: a list split into halves, sorted runs merged front by front, its levels",
    "code_trace": "code with a line-by-line highlight and a panel of variable values",
    "call_tree": "recursion trees (other than merge sort), the call stack, memoisation",
    "growth_curves": "growth of running time: O(1)..O(c^n) curves, operation counters, Big-O comparison",
    "linked_list": "linked lists: nodes and next-pointers, insert, delete, reverse",
    "stack_queue": "stacks and queues: push/pop, enqueue/dequeue",
    "hash_table": "hash tables: buckets, hashing, collisions, chaining, probing",
    "tree": "trees as data structures: BST, heap, trie; insert, search, traversals",
    "graph": "graphs: nodes and edges, BFS, DFS, shortest paths, spanning trees, topological sort",
    "dp_table": "a dynamic-programming table filled in order, with arrows to the cells each depends on",
    "memory_refs": "variables, references, aliasing, mutation, memory boxes",
    "state_machine": "state machines and automata: states, transitions, DFAs, regular expressions",
    "bits_logic": "binary and hex numbers, bitwise operations, logic gates, circuits, truth tables",
    "flowchart": "boxes and arrows: pipelines, control flow, system or process diagrams",
    "ml_basics": "machine-learning pictures: points and a decision boundary, loss curve with gradient descent, "
                 "network diagram, clusters",
    # Mathematics
    "equation_steps": "a derivation or calculation shown one formula per step",
    "number_line": "a number line: intervals, inequalities, points, sequences converging",
    "function_plot": "axes with plotted functions: transformations, limits, tangents, areas, maxima, Riemann sums",
    "linear_map_2d": "a 2D coordinate grid with vectors transformed by a matrix: linear maps, eigenvectors, bases",
    "vectors_3d": "3D vectors, planes, surfaces, cross products, span in 3D",
    "matrix_ops": "matrices written out: multiplication, row operations, block matrices, factorisations",
    "series": "sequences and series: partial sums, convergence",
    "probability": "probability: trees, sample spaces, distributions, sampling, Bayes",
    "stats_plots": "data plots: scatter plots, density curves, regression lines, confidence intervals, histograms",
    "counting": "counting: grids of outcomes, Pascal's triangle, permutations, combinations",
    "proof_steps": "a proof's structure: induction steps, contradiction, chains of implications",
    "sets_logic": "sets and logic: Venn diagrams, set operations, quantifiers",
    "geometry": "geometric figures: constructions, triangles, circles, angles, transformations",
    "complex_plane": "the complex plane: complex numbers as points, roots of unity",
    "polar_parametric": "polar and parametric curves",
    "slope_field": "differential equations: slope fields and solution curves",
    "bar_meter": "a bar chart, meter or dial for a few quantities",
    "note": "only words: a key term, a list of points, a question (no diagram)",
}

# The templates that draw each family's main picture. A family missing here has no template yet: its videos are
# drawn with formulas (and the gap is logged, so templates get built in the order they are needed).
DRAWN_BY: dict[str, tuple[str, ...]] = {
    "array_bars": ("ArrayBars",),
    "merge_sort": ("MergeSort",),
    "growth_curves": ("FunctionPlot",),
    "function_plot": ("FunctionPlot",),
    "stats_plots": ("FunctionPlot",),
    "ml_basics": ("FunctionPlot",),
    "graph": ("Graph",),
    "linear_map_2d": ("LinearMap2D",),
    "equation_steps": ("EquationSteps",),
    "proof_steps": ("EquationSteps",),
    "matrix_ops": ("EquationSteps",),
    "note": ("Note",),
}

# Beside any picture: a formula, and a short note.
ALWAYS = ("EquationSteps", "Note")


def templates_for(family: str, also: list[str] | tuple[str, ...] = ()) -> list[str]:
    """The templates a storyboard on this family may use: the main family's first, then those of `also`, then
    formulas and notes."""
    out: list[str] = []
    for f in (family, *also):
        for name in DRAWN_BY.get(f, ()):
            if name not in out:
                out.append(name)
    return out + [n for n in ALWAYS if n not in out]


def main_template(family: str) -> str | None:
    """The template that draws the main picture, or None when no template draws this family (or it is only
    words or a formula, which every storyboard has anyway)."""
    names = DRAWN_BY.get(family, ())
    return names[0] if names and names[0] not in ALWAYS else None


def is_gap(family: str) -> bool:
    """No template draws this family's picture yet."""
    return family not in DRAWN_BY and family != "none"
