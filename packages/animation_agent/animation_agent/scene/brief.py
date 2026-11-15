"""What the storyboard planner is told about Picture (plan/scene-grammar-plan.md, P1): the program's API, its rules,
and the hand-written programs (scene/examples.py) as worked examples. No Manim.

The views cover most of CS and Math (plan/visual-coverage-plan.md), and documenting all of them with their worked
examples would make the brief long and the planner's choice harder. So a topic gets the brief for its area (step
6): every view's rules in full for the views that area draws with, a one-line index of the rest (still usable),
and that area's worked examples. Each area's brief is fixed text, so the prompt cache still serves every video of
a course. A topic whose area is unclear gets the whole brief."""

from __future__ import annotations

import re

from animation_agent.scene.examples import COVERAGE_PROGRAMS, DIAGRAM_PROGRAMS, MATH_PROGRAMS, PROGRAMS

ALL_PROGRAMS = {**PROGRAMS, **MATH_PROGRAMS, **DIAGRAM_PROGRAMS, **COVERAGE_PROGRAMS}

_EXAMPLE_TOPICS = {
    "geometric": "a whole video: why 1 + 1/2 + 1/4 + ... adds up to 2 (partial sums, then the algebra)",
    "union_find": "quick-union (union-find): the id[] array, the forest it encodes and the code line, kept in step",
    "llrb": "inserting S E A R C H X M into a left-leaning red-black BST: each insert, then its rotations and flips",
    "water_jugs": "the water-jug puzzle: measure 4 gallons with a 3 and a 5",
    "bar_chart": "a population by group as a bar chart, then a stratified sample in proportion",
    "division": "division with remainder on a number line: 17 = 2 x 7 + 3",
    "volume": "volume under a surface: columns under z = f(x, y), more of them each time",
    "slicing_views": "a solid and its cross-section: hide and restore views so each diagram has room",
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
    "matmul": "a matrix product, each entry from a row and a column",
    "match": "naive string matching: the pattern slides along the text, matches green, the mismatch red",
    "binary_add": "adding two bytes bit by bit, with the carries in a row of their own",
    "float32": "-6.25 as a 32-bit float: the bits, then the sign, exponent and fraction fields",
    "bsearch_code": "binary search as code: the current line, the variables watched under it",
    "long_array": "binary search in 20 keys: the window follows mid",
    "fib_tree": "the calls fib(4) makes, labelled f(4), f(3)..., the repeated fib(2) in red",
    "btree": "a full B-tree node splits: the middle key moves up",
    "uml": "a class diagram: Savings and Checking inherit from Account",
    "tcp_full": "a whole TCP connection, 10 messages: the oldest scroll up",
    "counter": "a 2-bit counter from two D flip-flops, ticked three times",
    "mux": "a 2-to-1 multiplexer: the select input picks d0 or d1",
    "timing": "a D flip-flop's timing diagram: Q copies D at each rising clock edge",
    "mod12": "adding 5 again and again mod 12, round a circle",
    "matching": "a perfect matching of workers to jobs, as a bipartite graph",
    "neural": "a 3-4-2 neural network, one hidden unit's inputs lit",
    "petersen": "the Petersen graph, each vertex where the slide draws it",
    "boxplot": "two classes' scores as box plots, an outlier past the whisker",
    "stacked": "two products' sales stacked by quarter",
    "attention": "an attention matrix as a heat map, one row lit",
    "heat_map": "f = x^2 + 2y^2 as a heat map, its level curves, gradient descent walking down",
    "z_squared": "w = z^2 bending the unit square's grid into a half-disc",
    "span": "the span of two vectors in R3 is a plane; their cross product is normal to it; the camera turns",
    "saddle": "z = x^2 - y^2: a saddle point and its tangent plane, in 3D",
    "torus": "a torus as a parametric surface, a loop round its hole",
}

INTRO = """\
This idea's picture
Draw it with Picture: you write a short Python program that runs the idea on the views below and calls \
snap('caption', name='...', part='...') after every state the viewer should see. Code runs the program, lays \
everything out and animates each change, so every step shown is the real algorithm's. The video is built from \
your snapshots: each one gets its own line, in the program's order, and is on screen while that line is spoken, \
so the picture moves on every line that makes a point.

Views (at most 3, stacked top to bottom in the order the program makes them; a title is at most 18 characters, \
and it gives way to the picture when room is short, so the lines say what it names). The frame is narrow (about \
3.9 units across: 14 characters of code, 15 one-character cells, 8 two-character cells). The main picture (every \
view but cells, code and tape) gets the room, so every other view makes it smaller: a 3-line code panel takes a \
third of the frame. Use one only when the video is about the code's lines, and use the slide's own example over a \
smaller made-up one. A view too big for the frame is refused with the reason, except where it says it scrolls.
Every view supports v.hide() and v.show(): hiding keeps its contents but removes it from later snapshots; \
showing restores it in creation order. Hide a view BEFORE creating its replacement. Up to 12 views may be \
created over a program, with at most 3 visible at once. The engine computes positions and sizes before \
rendering, keeps text readable, and scrolls supporting formulas when necessary. You choose which views must \
be seen together. A 3D scene plus axes plus a formula usually needs separate steps in the dialogue frame \
(about 3.9 wide by 4.7 high): show the solid with its formula, then hide the solid before showing the slice \
on axes. Keep the same worked example and all teaching steps; do not squeeze all three into every snapshot.
"""

# each view's rules, in the order the full brief lists them; INDEX is one line each, for the views an area's brief
# doesn't spell out (the planner may still use them)
VIEW_DOCS = {
    "cells": """\
  - cells(name, values, title=None, index=True): a row of cells, each value at most 2 characters (INF or 'INF' \
shows as ∞). Up to 32: past about 8, a window onto the array follows the cells you mark or point at, with "…" on \
the side it goes on (indices stay the real ones). Use it like a list: a[i], a[i] = v, len(a), for v in a. \
a.mark(i, style), a.unmark(i=None), a.point(label, i) (a label of at most 2 characters under cell i, e.g. 'lo', \
'i'), a.unpoint(label).""",
    "tape": """\
  - tape(name, symbols, title=None, group=None, index=False): a long row of ONE-character cells (a string, a \
Turing machine's tape, the bits of a word): up to 64; about 15 fit on a line and a longer tape wraps onto more \
lines (group=4 or 8 sets the cells in nibbles or bytes; index=True numbers them). t[i], t[i] = 'x', len(t), \
t.append(s), t.text(). t.mark(i, style), t.mark_range(a, b, style) (cells a to b - 1), t.unmark(i=None); \
t.head(label, i) a caret and a label of 1-3 characters under cell i ('q0', 'i'), t.unhead(label=None); \
t.field(key, a, b, label=None, style=None) a bracket under cells a to b - 1 naming a field ('sign', 'exponent', \
'tag', 'host'), t.unfield(key=None); t.row(key, symbols, at=0, label=None) another row under it, its first \
symbol under column `at` (call it again with a new `at` to slide it: a pattern along a text; a second number to \
add; the carries), label at most 3 characters, at most 3 rows, t.mark_row(key, j, style) marks the row's symbol \
j, t.unrow(key=None). A tape with rows under it stays on one line (about 15 columns).""",
    "nodes": """\
  - nodes(name, nodes=(), layout='tree', directed=False, title=None): up to 20 nodes, each keyed by a short name \
with a label of at most 4 characters (a label of 3-4 characters, f(3) or 'cat', is drawn in a pill, so fewer fit \
across). n.add(key, label=None, style=None), n.remove(key), n.link(a, b, style=None, label=None, slot=None), \
n.unlink(a, b), n.restyle_link(a, b, style), n.parent(key), n.mark(key, style), n.unmark(key=None). \
layout 'tree': a link goes parent -> child, and linking a node under a new parent moves it; 'binary': the same \
with slot=0 for a left child and slot=1 for a right one; a tree node may hold keys instead of a label, \
n.add(key, keys=[10, 20]) (a B-tree's, up to 4 of 2 characters; n.set_keys(key, keys) after an insert or a \
split), its children linked with slot=j hanging from the gap before key j. 'graph': laid out once for every node \
and link the program ever shows, a link's label (up to 6 characters) is its weight, directed=True draws arrows. \
Graphs placed by rule: 'circle' puts the nodes round a ring in the order added, from the top clockwise (residues \
mod n, a ring of servers, a cycle); 'bipartite' in two columns, n.add(key, layer=0 or 1) (a matching, a function \
from A to B); 'layered' in columns by n.add(key, layer=k) (a neural network, a DAG's levels); 'fixed' where \
n.add(key, at=(x, y)) puts each node in your own coordinates (the slide's own drawing: K5, Petersen, a map).""",
    "code": """\
  - code(name, lines, title=None): pseudo-code, up to 30 lines of at most 40 characters, but a row shows about \
14 (a leading space counts half): a longer line wraps onto the next row, so write short lines (l, h, m for lo, \
hi, mid; '//' not 'floor'). c.line(i) lights line i (None: none); a program taller than its band scrolls to keep \
the lit line in view. c.mark(i, style) colours a line that stays (run: 'visited'; the bug: 'red'), c.unmark(i=None); \
c.set(i, text) rewrites a line (a fix, a compiler's step); c.watch(name, value) shows a variable's value under the \
code (name and value at most 6 characters each, up to 6), c.unwatch(name=None).""",
    "container": """\
  - container(name, capacity, level=0, title=None): a vessel drawn to scale with the others; .level, .capacity, \
.style, x.pour_into(y) (returns the amount poured).""",
    "axes": """\
  - axes(name, x=None, y=None, title=None, xlabel='x', ylabel='y', equal=False): math, data and charts on axes \
over x in (lo, hi) (a range is needed for curves; x and y are fitted to what is drawn unless given; equal=True \
keeps one scale for x and y, for shapes and fields). \
Each thing has a key, and drawing it again under the same key changes it in place: a.plot(key, f, style=None, \
label=None, x=None) a curve of f (a lambda or def; it breaks where f is undefined); a.area(key, f, a, b, g=None, \
style='visited', label=None) the region between f and g (or the x-axis); a.riemann(key, f, a, b, n, rule='left', \
style='visited') n rectangles (rule 'left', 'right' or 'mid'), returning their total; a.tangent(key, f, x0, \
half=None, style='current', label=None), returning the slope; a.line(key, p, q, style=None, label=None) a segment \
between two (x, y) points; a.point(key, x, y, label=None, style='current'); a.field(key, F, n=7) arrows of \
F(x, y) -> (u, v); a.contour(key, F, level, label=None) the curve F(x, y) = level; a.vector(key, x, y, \
origin=(0, 0), style=None, label=None) an arrow; a.polygon(key, points, style=None, fill=True, label=None); \
a.curve(key, fx, fy, t=(0, 1)) the curve (fx(t), fy(t)); a.polar(key, r, t=(0, 2*pi)) the curve r = r(theta). \
The plane itself: a.grid(key, matrix=None, step=1, f=None, over=None) the grid lines, sent through a 2x2 matrix \
(a linear map; draw it again with the matrix and it moves) or through any map f(x, y) returning (u, v) or a \
complex number (lambda x, y: complex(x, y) ** 2: a conformal map; polar coordinates), over=(x0, x1, y0, y1) the \
square whose lines it sends; a.heat(key, F, n=16) the plane coloured by F(x, y), dark low and bright high, under \
everything else (a temperature, a density, a loss surface from above), returning (lowest, highest). \
Data: a.bars(key, heights, x=None, labels=None, style='visited', values=False, base=None) a bar chart (labels \
names each bar on the x-axis, at most 8 characters; values=True writes each height on its bar; base=[...] stands \
each bar on top of another series: stacked bars), returning the total; a.histogram(key, data, bins=8, \
range=None) bars counting the data in equal bins, returning the counts; a.points(key, xs, ys, style='current', \
label=None) a scatter (one thing however many points); a.boxplot(key, data, x=1, name=None) a box plot computed \
from the data (quartiles, whiskers, outliers; name labels it on the x-axis), returning (q1, median, q3); \
a.errors(key, xs, ys, err) points with error bars (a confidence interval). a.mark(key, style), a.remove(key). \
At most 12 things; a label is at most 8 characters (x^2 shows as x²) and goes beside its thing, so label a \
level curve with just its level ('4'). A label with no clear place is left out, so let the lines say what matters \
and keep labels few.""",
    "space": """\
  - space(name, x=(-2, 2), y=(-2, 2), z=(-2, 2), title=None, view=(-55, 24)): a 3D scene with x, y, z axes, one \
scale for all three (angles and lengths are true), seen from a camera at (azimuth, elevation) in degrees; \
s.turn(azimuth, elevation) moves the camera for the snapshots after (the scene turns between them). \
s.point(key, x, y, z, label=None, style='current'); s.vector(key, x, y, z, origin=(0, 0, 0), style=None, \
label=None); s.line(key, p, q) a segment between two (x, y, z) points; s.plane(key, normal, d=0) the plane \
normal . (x, y, z) = d cut to the box (a span, a constraint, a tangent plane), translucent; s.polygon(key, \
points); s.curve(key, fx, fy, fz, t=(0, 1)) a space curve; s.surface(key, f, n=12) z = f(x, y) over the box's x \
and y; s.param(key, fx, fy, fz, u=(0, 1), v=(0, 1), n=12) a parametric surface, each of fx, fy, fz a function of \
(u, v) (a sphere, a cylinder, a torus, a Mobius strip); s.mark(key, style), s.remove(key). At most 14 things; \
surfaces are shaded and drawn far to near, and lines, vectors and points are drawn over them.""",
    "venn": """\
  - venn(name, sets, universe=None, title=None): 1-3 sets as circles, sets a dict of a letter or two to a set (at \
most 16 elements in all, each at most 2 characters; universe adds elements in none of them). v.shade(region, \
style='found') shades a region written with the set names and & | - ~ ( ): 'A&B', '(A|B)-C', '~A' (outside A); \
v.unshade(region=None); v.show_elements() writes each element in its region; v.region(expr) returns its elements.""",
    "geometry": """\
  - geometry(name, title=None): a figure in your own coordinates, scaled to fit with one scale for x and y. \
g.point(key, x, y, label=None, style=None) (the label defaults to the key; label='' for none), g.at(key) its \
(x, y); wherever a point is wanted, give its key or an (x, y) pair. g.segment(key, a, b, style=None, label=None), \
g.circle(key, center, r, style=None), g.polygon(key, [points], style=None, fill=False), g.arc(key, center, r, t1, \
t2) (angles in radians), g.sector(key, center, r1, r2, t1, t2, style='current') the patch between two radii and \
two angles (r1=0: a pie slice), returning its area; g.angle(key, a, vertex, b, style='current', label=None) an \
arc at vertex from a to b, returning the angle in degrees; g.mark(key, style), g.remove(key).""",
    "numberline": """\
  - numberline(name, lo, hi, step=None, title=None): a number line (ticks every step, or at round numbers), for \
integers, multiples, remainders, intervals and sequences. n.point(key, x, label=None, style='current'), \
n.interval(key, a, b, closed=(True, True), style='visited', label=None) (an open end is a hollow dot), n.jump(key, \
a, b, label=None) an arc from a to b (a step of +7, a remainder), n.mark(key, style), n.remove(key).""",
    "surface": """\
  - surface(name, x=(lo, hi), y=(lo, hi), z=None, title=None, xlabel='x', ylabel='y', zlabel='z'): z = f(x, y) \
seen in 3D from one fixed angle. s.plot(key, f, n=12) the surface; s.columns(key, f, n=4) n x n boxes under it \
(a double integral's sum), returning their total volume; s.point(key, x, y, z, label=None); s.mark(key, style), \
s.remove(key). (For vectors, planes, curves in space or a turning camera, use space.)""",
    "grid": """\
  - grid(name, rows, row_names=None, col_names=None, title=None, matrix=False): a table of up to 12 rows and 10 \
columns (a DP table, a truth table, a database table, an adjacency matrix), or with matrix=True a matrix in \
brackets; rows is a list of lists, each entry at most 6 characters (None: blank). About 3.7 units across in all, \
so short entries and names when there are many columns (a table too wide across is drawn on its side). g[r][c] \
reads and writes an entry; g.row(r), g.col(c), g.rows, g.cols; g.mark(r, c, style), g.mark_row(r, style), \
g.mark_col(c, style), g.unmark(r=None, c=None); g.heat(lo=None, hi=None) colours each number by its value, dark \
low and bright high (an attention or confusion matrix, an image's pixels, costs), g.heat(on=False) stops.""",
    "flow": """\
  - flow(name, direction='down', title=None): labelled boxes joined by arrows, in layers ('down': top to bottom; \
'right': left to right): a flowchart, a pipeline, a system's parts, a state machine with named states, a call or \
parse tree with words, a class or ER diagram. f.box(key, text=None, shape='box', style=None, layer=None, \
fields=None) (up to 2 lines of 14 characters: a longer line wraps at its spaces; shapes: box, round, diamond for a \
decision, circle, double for an accepting state, cylinder for a database, document, cloud, and with a pictogram \
beside the text: person, chip for a CPU, monitor for a computer, lock, server; fields=[...] makes a record: its \
name over up to 5 fields of 16 characters, for a class 'id: int', 'deposit()', an entity, a struct, and \
f.fields(key, fields) changes them); f.text(key, text); f.arrow(a, b, label=None, style=None, kind='arrow') \
(kind 'line' for no head (an ER relationship), 'dashed' (a dependency), 'inherit' a hollow head (UML's "is a"); \
a label of a word or two; a == b draws a loop); f.unarrow(a, b), f.restyle(a, b, style) colours an arrow, \
f.mark(key, style), f.unmark(key=None), f.remove(key). At most 16 boxes; about two 8-character boxes (or two \
short records) side by side and 5 layers fit. An arrow label with no clear room is left out, so keep labels to a \
word.""",
    "timeline": """\
  - timeline(name, lanes, t=None, step=None, title=None): up to 6 lanes (names at most 8 characters) along a \
time axis (t=(lo, hi), or fitted): tl.block(key, lane, start, end, label=None, style=None) a block in a lane (its \
label written inside when it fits), tl.marker(key, t, label=None) a line at time t, tl.signal(key, lane, values, \
t0=0, step=1, style=None) a digital signal, values of 0 and 1 each `step` long, drawn as a square wave (a clock, a \
flip-flop's D and Q: a timing diagram), tl.mark(key, style), tl.remove(key). For CPU schedules, Gantt charts, \
pipelines, timing diagrams, anything over time.""",
    "sequence": """\
  - sequence(name, actors, title=None): 2-4 actors side by side (names at most 8 characters), each with a \
lifeline; s.message(key, a, b, label=None, style=None, dashed=False) an arrow from a to b below the messages \
before it (a == b: to itself; dashed for a reply; a short label, longer than 22 characters is left out), \
s.mark(key, style), s.remove(key). Up to 16 messages: about 7 fit the whole frame (5 above a formula), and past \
that the oldest scroll up out of view, so a whole connection fits. For protocols, a client and a server, threads \
and locks.""",
    "circuit": """\
  - circuit(name, title=None): a logic circuit drawn top to bottom, every wire showing the value code works out \
(1 lit). c.input(key, value=0, label=None), c.gate(key, kind, inputs) (AND OR NOT NAND NOR XOR XNOR BUF, its \
inputs made before it), c.block(key, kind, inputs) a block with ports, its inputs listed in port order: MUX (d0, \
d1, s -> y), MUX4 (d0-d3, s1, s0 -> y), DEC (a1, a0 -> y0-y3), HA (a, b -> s, c), FA (a, b, ci -> s, co), DFF (D -> \
Q); a later part names one output of a block with several as 'key.port' ('fa.co'). A DFF holds its bit (shown in \
it; c.set(key, v) sets it) until c.tick(), a clock edge that copies every DFF's D into its Q at once, and its D \
may come from a gate made after it (the wire loops back up the right side): counters, registers, state machines. \
c.output(key, source, label=None) (labels at most 4 characters); c.set(key, value) changes an input, \
c.value(key) returns a computed value, c.mark(key, style). At most 14 parts; about 3 levels of gates fit, and a \
circuit of 3 levels (a full adder) takes the whole frame: draw it as the only view, and let the lines give the \
truth table (or use one FA block).""",
    "memory": """\
  - memory(name, title=None): stack frames down the left, heap objects down the right, each a list of fields. \
m.frame(key, title=None) (a call: 'main()', 'f(3)'), m.obj(key, title=None) (titles at most 10 characters), \
m.set(box, name, value) (a value of at most 6 characters, None for blank, or m.ref(key) for an arrow to that heap \
object), m.get(box, name), m.unset(box, name), m.remove(key) pops a frame or frees an object, m.mark(box, \
name=None, style). At most 6 frames and 6 objects of 5 fields, as height allows; about 3 objects of 2 fields fit \
beside a frame.""",
    "formula": """\
  - formula(name, lines=(), title=None): up to 4 lines of TeX, worked one step at a time, each at most about 22 \
symbols. f.add(tex) writes the next line (returns its index); f.set(i, tex) rewrites line i (a step of the \
working); f.mark(i, style) colours a line; f.highlight(i, term, style='current') colours one term of line i, \
written as it is in the line; f.box(i) boxes a result; f.unmark(i=None); f.remove(i). Write the TeX in raw \
strings (r'\\frac{1}{2}'), and put computed numbers in with + and str(), not an f-string (its braces clash with \
TeX's). It takes a band under the picture like a code panel (about 0.9 units a line), so a formula the lines work \
through (a sum, a recurrence, a cost such as O(1) x deg(u) summed to O(|E|)) is a view, and each of its steps a \
snapshot with its own line.""",
}

INDEX = {
    "cells": "cells(name, values): an array of short values (a window follows the marks past 8)",
    "tape": "tape(name, symbols): a string or bits, one character a cell, with heads, fields and aligned rows",
    "nodes": "nodes(name, layout=...): trees, B-trees, graphs, and graphs on a circle, in layers, two columns or fixed",
    "code": "code(name, lines): pseudo-code with the current line lit, scrolling, and watched variables",
    "container": "container(name, capacity): a vessel to scale",
    "axes": "axes(name, x, y): curves, areas, fields, contours, grids and maps of the plane, heat maps, bars, "
            "histograms, scatters, box plots, error bars",
    "space": "space(name, x, y, z): a turning 3D scene: points, vectors, planes, curves, surfaces",
    "venn": "venn(name, sets): 1-3 sets as circles, regions shaded",
    "geometry": "geometry(name): points, segments, circles, arcs, sectors, polygons, angles",
    "numberline": "numberline(name, lo, hi): points, intervals, jumps",
    "surface": "surface(name, x, y): z = f(x, y) from a fixed angle, columns under it",
    "grid": "grid(name, rows): a table or matrix, cells marked or coloured by value",
    "flow": "flow(name): boxes (and records with fields) joined by arrows, in layers",
    "timeline": "timeline(name, lanes): blocks, markers and square-wave signals over time",
    "sequence": "sequence(name, actors): messages between 2-4 actors (scrolls past about 7)",
    "circuit": "circuit(name): gates, MUX/DEC/adder blocks and D flip-flops, every wire's value computed",
    "memory": "memory(name): stack frames and heap objects, pointers as arrows",
    "formula": "formula(name): up to 4 TeX lines worked a step at a time",
}

WHICH = """\
  - Which view: an array -> cells; a string, bits or a tape -> tape; trees, B-trees, graphs, heaps -> nodes (a \
cycle or residues -> circle, a matching -> bipartite, a network -> layered, the slide's drawing -> fixed); a table, \
a matrix, dynamic programming, a truth table, rows of data -> grid; a process, a pipeline, layers, an \
architecture, a state machine, a flowchart, a class or ER diagram -> flow; a schedule or a timing diagram -> \
timeline; messages between parties -> sequence; logic, blocks and flip-flops -> circuit; pointers, references, \
the call stack -> memory; code being traced -> code; functions, data, 2D vectors, linear and nonlinear maps, heat \
maps -> axes; vectors, planes, curves and surfaces in 3D -> space; sets -> venn; shapes and angles -> geometry; \
integers and intervals -> numberline.
  - Math you can call: sin cos tan asin acos atan atan2 exp log log2 log10 sqrt floor ceil hypot radians degrees \
pi e factorial comb perm gcd; derivative(f, x), integral(f, a, b), root(f, a, b) (f(a), f(b) of opposite signs); \
Fraction(p, q) for exact probabilities (str(Fraction(3, 10)) is '3/10'); complex(x, y) and 1j for complex numbers; \
bin, hex, oct, format, chr, ord for encodings and ciphers. A probability tree is nodes() with each link's label \
its probability.
  - snap(caption, name=None, part=None, wrong=False): records every visible view as it is now, under a short unique name \
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
"""

# the areas a topic's brief is chosen by: the views it spells out, the worked examples it shows (the first, a
# whole tagged video, in every one), and the words that place a topic there
AREAS = {
    "algorithms": (
        ["cells", "nodes", "grid", "code", "tape", "memory", "axes", "formula"],
        ["geometric", "union_find", "llrb", "lcs", "match", "bsearch_code", "fib_tree", "btree", "long_array"],
        "algorithm, sort, search, tree, heap, hash, array, linked list, stack, queue, graph, dijkstra, bfs, dfs, "
        "traversal, dynamic programming, recursion, recursive, complexity, big-o, asymptotic, greedy, string, "
        "pattern, automaton, automata, dfa, nfa, turing, grammar, regular language, decidab, reduction, np-complete, "
        "loop, variable, program, code, pointer, insert, delete, balanced, bst, b-tree, trie, minimax, "
        "shortest path, spanning, union-find, amortized, symbol table, priority queue, binary search"),
    "systems": (
        ["flow", "sequence", "timeline", "memory", "circuit", "grid", "tape", "code", "cells", "nodes", "formula"],
        ["geometric", "tcp", "tcp_full", "rr", "process", "counter", "timing", "float32", "uml", "linked"],
        "process, thread, schedul, cache, virtual memory, paging, page table, tcp, ip address, packet, protocol, "
        "network, router, routing, circuit, gate, flip-flop, latch, register, cpu, pipelin, instruction, "
        "architecture, database, sql, query, transaction, relational, join, compiler, parser, lexer, token, "
        "class, object, inheritance, uml, encryption, cipher, rsa, signature, certificate, deadlock, lock, mutex, "
        "semaphore, file system, disk, bits, byte, binary number, floating point, two's complement, interrupt, "
        "kernel, distributed, consensus, server, client, http, dns, multiplexer, decoder, adder, boolean, "
        "logic gate, karnaugh, sequential, combinational, clock"),
    "calculus": (
        ["axes", "space", "surface", "numberline", "geometry", "grid", "formula"],
        ["geometric", "riemann", "tangent", "level_curves", "volume", "slicing_views", "saddle", "heat_map", "z_squared"],
        "derivative, integral, limit, series, converge, differential equation, ode, pde, gradient, surface, volume, "
        "vector field, curve, polar, taylor, complex number, complex plane, newton's method, optimization, "
        "optimisation, convex, fourier, epsilon, continuity, continuous function, tangent, area under, "
        "rate of change, partial derivative, multivariable, parametric, jacobian, heat equation, wave equation, "
        "curl, divergence, triangle, circle, angle, centroid, double integral"),
    "discrete": (
        ["venn", "nodes", "grid", "numberline", "cells", "tape", "axes", "formula"],
        ["geometric", "venn3", "probability_tree", "division", "bar_chart", "mod12", "matching", "boxplot"],
        "set, logic, proof, induction, counting, permutation, combination, probability, random, distribution, "
        "expect, variance, statistic, sample, hypothesis, regression, modular, prime, gcd, divisib, congruen, "
        "number theory, group, relation, bijection, pigeonhole, coloring, matching, bayes, conditional, binomial, "
        "normal distribution, confidence interval, histogram, mean, median, estimat"),
    "linear": (
        ["axes", "space", "grid", "geometry", "formula", "nodes"],
        ["geometric", "eigen", "matmul", "span", "z_squared"],
        "matrix, matrices, vector space, eigen, linear map, linear transformation, span, basis, determinant, rank, "
        "null space, orthogonal, projection, inner product, dimension, subspace, row reduction, "
        "gaussian elimination, cross product, dot product, linear system, linear combination"),
}
FULL_EXAMPLES = ["geometric", "union_find", "llrb", "lcs", "match", "fib_tree", "bar_chart", "division", "riemann",
                 "level_curves", "venn3", "probability_tree", "process", "tcp", "rr", "adder", "linked", "eigen",
                 "span", "counter", "uml", "mod12", "slicing_views"]


def area_of(text: str) -> str | None:
    """The area whose words a topic's text uses most (title and summary), or None when no area clearly leads."""
    t = text.lower()
    scores = {}
    for area, (_v, _e, words) in AREAS.items():
        scores[area] = sum(len(re.findall(r"\b" + re.escape(w), t)) for w in words.split(", "))
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (best, top), (_second, next_) = ranked[0], ranked[1]
    return best if top >= 1 and top >= 1.5 * next_ else None


def brief(area: str | None = None) -> str:
    """The picture brief: for an area, its views in full, the rest as an index, and its worked examples; with no
    area, everything."""
    if area is None or area not in AREAS:
        views, examples, rest = list(VIEW_DOCS), FULL_EXAMPLES, []
    else:
        views, examples, _w = AREAS[area]
        rest = [v for v in VIEW_DOCS if v not in views]
    parts = [INTRO, "\n".join(VIEW_DOCS[v] for v in VIEW_DOCS if v in views)]
    if rest:
        parts.append("  - Also available (the checker explains any mistake): " + "; ".join(INDEX[v] for v in rest) + ".")
    parts.append(WHICH)
    parts.append("Worked examples (programs for other ideas; the first is a whole video's, every snapshot tagged with "
                 "its part, and the others show the views at work):\n")
    for name in examples:
        parts.append(f"# {_EXAMPLE_TOPICS[name]}\n{ALL_PROGRAMS[name].strip()}\n")
    return "\n".join(parts) + "\n"
