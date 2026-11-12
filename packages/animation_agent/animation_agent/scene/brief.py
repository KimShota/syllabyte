"""What the storyboard planner is told about Picture (plan/scene-grammar-plan.md, P1): the program's API, its rules,
and the hand-written programs (scene/examples.py) as worked examples. No Manim."""

from __future__ import annotations

from animation_agent.scene.examples import MATH_PROGRAMS, PROGRAMS

_EXAMPLE_TOPICS = {
    "union_find": "quick-union (union-find): the id[] array, the forest it encodes and the code line, kept in step",
    "llrb": "inserting S E A R C H X M into a left-leaning red-black BST: each insert, then its rotations and flips",
    "water_jugs": "the water-jug puzzle: measure 4 gallons with a 3 and a 5",
    "riemann": "left Riemann sums with 2, 4, 8, 16 rectangles climbing toward the exact area",
    "tangent": "secant lines through P and Q as Q slides to P, then the tangent",
    "level_curves": "level curves of F(x, y) = x^2 + 2y^2, then its gradient field",
    "venn3": "three sets, their elements, and regions shaded one at a time",
    "triangle": "the angles of a triangle, measured and summed",
    "probability_tree": "two draws without replacement as a probability tree",
}

BRIEF = """\
This idea's picture
Draw it with Picture: you write a short Python program that runs the idea on the views below and calls \
snap('caption', name='...') after every state the viewer should see. Code runs the program, lays everything out \
and animates each change, so every step shown is the real algorithm's. Create the Picture in the first beat with \
the whole program (p = Picture(program=[...]), one string per line); it opens on the first snapshot. Then a beat \
shows a snapshot by its name, p.show(snap='swap1'), on the line that talks about it (two or three show calls in \
one beat play one after another). Plan the program from the beats: write the beats' points first, then give \
each point-making beat the snapshot it talks about, named for it (10-25 in all). A question or predict line \
keeps the picture as it is ([]); the line that answers shows the answer. Every name you show must be one the \
program snaps.

Views (at most 3, stacked top to bottom in the order the program makes them; a title is at most 18 characters, \
and it gives way to the picture when room is short, so the lines say what it names). The main picture (nodes, a \
container, axes, a Venn diagram or a figure) gets the room, so every other view makes it smaller: a 3-line code panel takes a third of the frame. \
Use one only when the video is about the code's lines, and use the slide's own example over a smaller made-up one:
  - cells(name, values, title=None, index=True): a row of up to 8 cells, each value at most 2 characters (INF \
or 'INF' shows as ∞). Use it like a list: a[i], a[i] = v, len(a), for v in a. a.mark(i, style), a.unmark(i=None), a.point(label, i) (a label \
of at most 2 characters under cell i, e.g. 'lo', 'i'), a.unpoint(label).
  - nodes(name, nodes=(), layout='tree', directed=False, title=None): up to 15 nodes, each keyed by a name of at \
most 2 characters. n.add(key, label=None, style=None), n.remove(key), n.link(a, b, style=None, label=None, \
slot=None), n.unlink(a, b), n.restyle_link(a, b, style), n.parent(key), n.mark(key, style), n.unmark(key=None). \
layout 'tree': a link goes parent -> child, and linking a node under a new parent moves it; 'binary': the same \
with slot=0 for a left child and slot=1 for a right one; 'graph': laid out once for every node and link the \
program ever shows, a link's label (up to 6 characters) is its weight, directed=True draws arrows.
  - code(name, lines, title=None): up to 6 lines of pseudo-code, each at most 14 characters; c.line(i) lights \
line i (None: none).
  - container(name, capacity, level=0, title=None): a vessel drawn to scale with the others; .level, .capacity, \
.style, x.pour_into(y) (returns the amount poured).
  - axes(name, x=(lo, hi), y=None, title=None, xlabel='x', ylabel='y', equal=False): math on axes over x in \
(lo, hi) (y fitted to what is drawn unless given; equal=True keeps one scale for x and y, for shapes and fields). \
Each thing has a key, and drawing it again under the same key changes it in place: a.plot(key, f, style=None, \
label=None, x=None) a curve of f (a lambda or def; it breaks where f is undefined); a.area(key, f, a, b, g=None, \
style='visited', label=None) the region between f and g (or the x-axis); a.riemann(key, f, a, b, n, rule='left', \
style='visited') n rectangles (rule 'left', 'right' or 'mid'), returning their total; a.tangent(key, f, x0, \
half=None, style='current', label=None), returning the slope; a.line(key, p, q, style=None, label=None) a segment \
between two (x, y) points; a.point(key, x, y, label=None, style='current'); a.field(key, F, n=7) arrows of \
F(x, y) -> (u, v); a.contour(key, F, level, label=None) the curve F(x, y) = level; a.mark(key, style), \
a.remove(key). At most 12 things; a label is at most 8 characters (x^2 shows as x²) and goes beside its thing, \
so label a level curve with just its level ('4'). A label with no clear place is left out, so let the lines say \
what matters and keep labels few.
  - venn(name, sets, universe=None, title=None): 1-3 sets as circles, sets a dict of a letter or two to a set (at \
most 16 elements in all, each at most 2 characters; universe adds elements in none of them). v.shade(region, \
style='found') shades a region written with the set names and & | - ~ ( ): 'A&B', '(A|B)-C', '~A' (outside A); \
v.unshade(region=None); v.show_elements() writes each element in its region; v.region(expr) returns its elements.
  - geometry(name, title=None): a figure in your own coordinates, scaled to fit with one scale for x and y. \
g.point(key, x, y, label=None, style=None) (the label defaults to the key; label='' for none), g.at(key) its \
(x, y); wherever a point is wanted, give its key or an (x, y) pair. g.segment(key, a, b, style=None, label=None), \
g.circle(key, center, r, style=None), g.polygon(key, [points], style=None, fill=False), g.arc(key, center, r, t1, \
t2) (angles in radians), g.sector(key, center, r1, r2, t1, t2, style='current') the patch between two radii and \
two angles (r1=0: a pie slice), returning its area; g.angle(key, a, vertex, b, style='current', label=None) an \
arc at vertex from a to b, returning the angle in degrees; g.mark(key, style), g.remove(key).
  - Math you can call: sin cos tan asin acos atan atan2 exp log log2 log10 sqrt floor ceil hypot radians degrees \
pi e factorial comb perm gcd; derivative(f, x), integral(f, a, b), root(f, a, b) (f(a), f(b) of opposite signs); \
Fraction(p, q) for exact probabilities (str(Fraction(3, 10)) is '3/10'). A probability tree is nodes() with each \
link's label its probability.
  - snap(caption, name=None): records every view as it is now, under a short unique name (in a loop, build it: \
name='pass' + str(k)). The caption says in a few plain words what this state shows, with its values ("relax \
0->2: distTo[2] is now 5"): the line writer reads it as what the picture shows, so make it exact and complete.
Styles are words: current (yellow: being looked at), visited (teal), found (green: final, done, sorted), compare \
(orange: two things compared), red (a red link, or the wrong idea), grey (out of play), new (just added), blue.

Rules:
  - Run the real algorithm or the real math in the program and let it compute every value shown (distances, \
orders, areas, slopes, probabilities); never type a result.
  - Plain Python: def, class, loops, lists, dicts, f-strings. No imports, no names starting with _, no print. \
Write the program's strings in single quotes (each line sits inside double quotes in the call). At most 80 lines.
  - What fits: about 8 nodes or cells across, a tree about 4 levels deep below one other view, a graph of 8 \
nodes and about 16 weighted links above an array (the whole frame). The Picture has the whole frame only while nothing else is on \
screen: with a formula or note anywhere in the video it gets two thirds of the frame, where a big graph won't \
fit. A picture that needs the whole frame wins: code then removes the formulas and notes, so for a big graph \
plan none and let the lines say the formula. Use the slide's own \
example when it fits, else a smaller one the lines name as such. If the program fails or doesn't fit, the \
checker says why and you fix it.
  - The wrong idea is a snapshot of the wrong state (a wrong value in a cell marked red, the wrong order); the \
next snapshot shows what holds instead.
  - Formulas (EquationSteps) and short notes (Note) can sit beside the Picture.

Worked examples (programs for other ideas):
"""


def brief() -> str:
    parts = [BRIEF]
    for name, topic in _EXAMPLE_TOPICS.items():
        parts.append(f"# {topic}\n{({**PROGRAMS, **MATH_PROGRAMS})[name].strip()}\n")
    return "\n".join(parts) + "\n"
