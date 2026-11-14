"""What the storyboard planner is told about Picture (plan/scene-grammar-plan.md, P1): the program's API, its rules,
and the hand-written programs (scene/examples.py) as worked examples. No Manim."""

from __future__ import annotations

from animation_agent.scene.examples import DIAGRAM_PROGRAMS, MATH_PROGRAMS, PROGRAMS

_EXAMPLE_TOPICS = {
    "geometric": "a whole video: why 1 + 1/2 + 1/4 + ... adds up to 2 (partial sums, then the algebra)",
    "union_find": "quick-union (union-find): the id[] array, the forest it encodes and the code line, kept in step",
    "llrb": "inserting S E A R C H X M into a left-leaning red-black BST: each insert, then its rotations and flips",
    "water_jugs": "the water-jug puzzle: measure 4 gallons with a 3 and a 5",
    "bar_chart": "a population by group as a bar chart, then a stratified sample in proportion",
    "division": "division with remainder on a number line: 17 = 2 x 7 + 3",
    "volume": "volume under a surface: columns under z = f(x, y), more of them each time",
    "riemann": "left Riemann sums with 2, 4, 8, 16 rectangles climbing toward the exact area",
    "tangent": "secant lines through P and Q as Q slides to P, then the tangent",
    "level_curves": "level curves of F(x, y) = x^2 + 2y^2, then its gradient field",
    "venn3": "three sets, their elements, and regions shaded one at a time",
    "triangle": "the angles of a triangle, measured and summed",
    "probability_tree": "two draws without replacement as a probability tree",
    "lcs": "the longest common subsequence table filled cell by cell, each from its neighbours",
    "process": "a process's states and the transitions between them, one path through them lit",
    "tcp": "TCP's three-way handshake, then a request and its reply",
    "rr": "round-robin scheduling with a quantum of 2, computed, as a timeline",
    "adder": "a full adder's gates, with each row of inputs computed through them",
    "linked": "a linked list in memory: pushing a node onto the front",
    "eigen": "a 2x2 matrix acting on the plane: the grid and two vectors, before and after",
}

BRIEF = """\
This idea's picture
Draw it with Picture: you write a short Python program that runs the idea on the views below and calls \
snap('caption', name='...', part='...') after every state the viewer should see. Code runs the program, lays \
everything out and animates each change, so every step shown is the real algorithm's. The video is built from \
your snapshots: each one gets its own line, in the program's order, and is on screen while that line is spoken, \
so the picture moves on every line that makes a point.

Views (at most 3, stacked top to bottom in the order the program makes them; a title is at most 18 characters, \
and it gives way to the picture when room is short, so the lines say what it names). The main picture (every view but \
cells and code) gets the room, so every other view makes it smaller: a 3-line code panel takes a third of the frame. \
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
  - axes(name, x=None, y=None, title=None, xlabel='x', ylabel='y', equal=False): math, data and charts on axes \
over x in (lo, hi) (a range is needed for curves; x and y are fitted to what is drawn unless given; equal=True \
keeps one scale for x and y, for shapes and fields). \
Each thing has a key, and drawing it again under the same key changes it in place: a.plot(key, f, style=None, \
label=None, x=None) a curve of f (a lambda or def; it breaks where f is undefined); a.area(key, f, a, b, g=None, \
style='visited', label=None) the region between f and g (or the x-axis); a.riemann(key, f, a, b, n, rule='left', \
style='visited') n rectangles (rule 'left', 'right' or 'mid'), returning their total; a.tangent(key, f, x0, \
half=None, style='current', label=None), returning the slope; a.line(key, p, q, style=None, label=None) a segment \
between two (x, y) points; a.point(key, x, y, label=None, style='current'); a.field(key, F, n=7) arrows of \
F(x, y) -> (u, v); a.contour(key, F, level, label=None) the curve F(x, y) = level; a.bars(key, heights, \
x=None, labels=None, style='visited', values=False) a bar chart (labels names each bar on the x-axis, at most 8 \
characters each; values=True writes each height on its bar), returning the total; a.histogram(key, data, bins=8, \
range=None) bars counting the data in equal bins, returning the counts; a.points(key, xs, ys, style='current', \
label=None) a scatter (one thing however many points); a.mark(key, style), a.remove(key). At most 12 things; a label is at most 8 characters (x^2 shows as x²) and goes beside its thing, \
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
  - numberline(name, lo, hi, step=None, title=None): a number line (ticks every step, or at round numbers), for \
integers, multiples, remainders, intervals and sequences. n.point(key, x, label=None, style='current'), \
n.interval(key, a, b, closed=(True, True), style='visited', label=None) (an open end is a hollow dot), n.jump(key, \
a, b, label=None) an arc from a to b (a step of +7, a remainder), n.mark(key, style), n.remove(key).
  - surface(name, x=(lo, hi), y=(lo, hi), z=None, title=None, xlabel='x', ylabel='y', zlabel='z'): z = f(x, y) \
seen in 3D from one fixed angle. s.plot(key, f, n=12) the surface; s.columns(key, f, n=4) n x n boxes under it \
(a double integral's sum), returning their total volume; s.point(key, x, y, z, label=None); s.mark(key, style), \
s.remove(key).
  - grid(name, rows, row_names=None, col_names=None, title=None, matrix=False): a table of up to 8 rows and 8 \
columns (a DP table, a truth table, a database table, an adjacency matrix), or with matrix=True a matrix in \
brackets; rows is a list of lists, each entry at most 6 characters (None: blank). About 3.7 units across in all, \
so short entries when there are many columns (a table too wide across is drawn on its side). g[r][c] reads and writes an entry; g.row(r), g.col(c), g.rows, \
g.cols; g.mark(r, c, style), g.mark_row(r, style), g.mark_col(c, style), g.unmark(r=None, c=None).
  - flow(name, direction='down', title=None): labelled boxes joined by arrows, in layers ('down': top to bottom; \
'right': left to right): a flowchart, a pipeline, a system's parts, a state machine with named states, a call or \
parse tree with words. f.box(key, text=None, shape='box', style=None, layer=None) (up to 2 lines of 14 \
characters: a longer line wraps at its spaces; shapes: box, round, diamond for a decision, circle, double for an accepting state, \
cylinder for a database, document, cloud, and with a pictogram beside the text: person, chip for a CPU, monitor \
for a computer, lock, server); f.text(key, text); f.arrow(a, b, label=None, style=None) (a label of a word or \
two; a == b draws a loop); f.unarrow(a, b), f.restyle(a, b, style) colours an arrow, f.mark(key, style), \
f.unmark(key=None), f.remove(key). At most 12 boxes; about two 8-character boxes side by side and 5 layers fit. \
An arrow label with no clear room is left out, so keep labels to a word.
  - timeline(name, lanes, t=None, step=None, title=None): up to 6 lanes (names at most 8 characters) along a \
time axis (t=(lo, hi), or fitted): tl.block(key, lane, start, end, label=None, style=None) a block in a lane (its \
label written inside when it fits), tl.marker(key, t, label=None) a line at time t, tl.mark(key, style), \
tl.remove(key). For CPU schedules, Gantt charts, pipelines, anything over time.
  - sequence(name, actors, title=None): 2-4 actors side by side (names at most 8 characters), each with a \
lifeline; s.message(key, a, b, label=None, style=None, dashed=False) an arrow from a to b below the messages \
before it (a == b: to itself; dashed for a reply; a short label, longer than 22 characters is left out), \
s.mark(key, style), s.remove(key). About 7 messages fit the whole frame, 5 above a formula. For protocols, a client and a server, threads and locks.
  - circuit(name, title=None): a logic circuit drawn top to bottom, every wire showing the value code works \
out (1 lit). c.input(key, value=0, label=None), c.gate(key, kind, inputs) (AND OR NOT NAND NOR XOR XNOR BUF, its \
inputs made before it), c.output(key, source, label=None) (labels at most 4 characters); c.set(key, value) \
changes an input, c.value(key) returns a computed value, c.mark(key, style). At most 14 parts; about 3 levels of \
gates fit, and a circuit of 3 levels (a full adder) takes the whole frame: draw it as the only view, and let \
the lines give the truth table.
  - memory(name, title=None): stack frames down the left, heap objects down the right, each a list of fields. \
m.frame(key, title=None) (a call: 'main()', 'f(3)'), m.obj(key, title=None) (titles at most 10 characters), \
m.set(box, name, value) (a value of at most 6 characters, None for blank, or m.ref(key) for an arrow to that heap \
object), m.get(box, name), m.unset(box, name), m.remove(key) pops a frame or frees an object, m.mark(box, \
name=None, style). At most 4 frames and 4 objects of 5 fields; about 3 objects of 2 fields fit beside a frame.
  - Axes also draw: a.vector(key, x, y, origin=(0, 0), style=None, label=None) an arrow; a.polygon(key, points, \
style=None, fill=True, label=None); a.curve(key, fx, fy, t=(0, 1)) the curve (fx(t), fy(t)); a.polar(key, r, \
t=(0, 2*pi)) the curve r = r(theta); a.grid(key, matrix=None, step=1) the grid lines, sent through a 2x2 matrix \
when given (what a linear map does to the plane; draw it again with the matrix and it moves).
  - formula(name, lines=(), title=None): up to 4 lines of TeX, worked one step at a time, each at most about 22 \
symbols. f.add(tex) writes the next line (returns its index); f.set(i, tex) rewrites line i (a step of the \
working); f.mark(i, style) colours a line; f.highlight(i, term, style='current') colours one term of line i, \
written as it is in the line; f.box(i) boxes a result; f.unmark(i=None); f.remove(i). Write the TeX in raw \
strings (r'\\frac{1}{2}'), and put computed numbers in with + and str(), not an f-string (its braces clash with \
TeX's). It takes a band under the picture like a code panel (about 0.9 units a line), so a formula the lines work \
through (a sum, a recurrence, a cost such as O(1) x deg(u) summed to O(|E|)) is a view, and each of its steps a \
snapshot with its own line.
  - Which view: an array or a string -> cells; trees, graphs, heaps -> nodes; a table, a matrix, dynamic \
programming, a truth table, rows of data -> grid; a process, a pipeline, layers, an architecture, a state machine, \
a flowchart, a call tree with words -> flow; a schedule -> timeline; messages between parties -> sequence; logic \
gates -> circuit; pointers, references, the call stack -> memory; functions, data, vectors, linear maps -> axes; \
sets -> venn; shapes and angles -> geometry; integers and intervals -> numberline; z = f(x, y) -> surface.
  - Math you can call: sin cos tan asin acos atan atan2 exp log log2 log10 sqrt floor ceil hypot radians degrees \
pi e factorial comb perm gcd; derivative(f, x), integral(f, a, b), root(f, a, b) (f(a), f(b) of opposite signs); \
Fraction(p, q) for exact probabilities (str(Fraction(3, 10)) is '3/10'). A probability tree is nodes() with each \
link's label its probability.
  - snap(caption, name=None, part=None, wrong=False): records every view as it is now, under a short unique name \
(in a loop, build it: name='pass' + str(k)), as a state of one part of the video (part='prepare', 'initiate', \
'deliver_1', 'deliver_2' or 'end'; wrong=True for the wrong idea's state). The caption says in a few plain words \
what this state shows, with its values ("relax 0->2: distTo[2] is now 5"): the line writer reads it as what the \
picture shows, so make it exact and complete.
Styles are words: current (yellow: being looked at), visited (teal), found (green: final, done, sorted), compare \
(orange: two things compared), red (a red link, or the wrong idea), grey (out of play), new (just added), blue.

Rules:
  - Run the real algorithm or the real math in the program and let it compute every value shown (distances, \
orders, areas, slopes, probabilities); never type a result.
  - Plain Python: def, class, loops, lists, dicts, f-strings. No imports, no names starting with _, no print. \
Write the program's strings in single quotes (each line sits inside double quotes in the call). At most 80 lines.
  - What fits: about 8 nodes or cells across, 10 bars, a tree about 4 levels deep below one other view, a graph of 8 \
nodes and about 16 weighted links above an array (the whole frame). Every view shares the frame, a formula \
too, so a big graph goes without one and the lines say the formula. Draw the slide's own \
example exactly (its functions, numbers, graph, region): declare it in slide_example, and the checker compares \
your program with it. Only when it can't fit, make one of your own (own=true) and let the lines say so. If the program fails or doesn't fit, the \
checker says why and you fix it.
  - The wrong idea is a snapshot of the wrong state, snap(..., wrong=True) (a wrong value in a cell marked red, \
the wrong order, a red line); the next snapshot shows what holds instead.

Worked examples (programs for other ideas; the first is a whole video's, every snapshot tagged with its part, and \
the others show the views at work):
"""


def brief() -> str:
    parts = [BRIEF]
    for name, topic in _EXAMPLE_TOPICS.items():
        parts.append(f"# {topic}\n{({**PROGRAMS, **MATH_PROGRAMS, **DIAGRAM_PROGRAMS})[name].strip()}\n")
    return "\n".join(parts) + "\n"
