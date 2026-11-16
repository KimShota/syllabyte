# Visual coverage: can the pictures draw any CS or Math topic? (2026-11-15)

Goal: every CS or Math topic gets a computed Picture (scene grammar) that shows the idea, not written Manim code
(codegen) as a fallback. P4 measured the gap: critic visual alignment 5.5 with a Picture, 4.2 without.

## 1. What the grammar can draw today

15 views, at most 3 stacked top to bottom (scene/api.py, scene/brief.py):

| View | Draws | Hard limits |
|---|---|---|
| cells | arrays, strings, pointers into them | 12 cells (8 fit), 2 characters each |
| nodes | trees, binary trees, graphs (weights, arrows) | 15 nodes, labels 2 characters; layouts tree, binary, graph only |
| code | pseudo-code, one line lit | 6 lines of 14 characters |
| container | vessels to scale | puzzles only |
| axes | curves, areas, Riemann sums, tangents, fields, contours, bars, histograms, scatter, vectors, polygons, parametric and polar curves, a 2x2 linear map of the grid | 12 things, labels 8 characters, 2D only, linear maps only |
| venn | 1-3 sets, regions shaded | 16 elements |
| geometry | points, segments, circles, arcs, sectors, polygons, angles | 12 things |
| numberline | points, intervals, jumps | |
| surface | z = f(x, y) from one fixed angle, columns under it | no rotation, no vectors or planes in space |
| grid | tables, matrices, DP, truth tables | 8 x 8, entries 6 characters |
| flow | boxes and arrows in layers, shapes, pictograms | 12 boxes, 2 lines of 14 characters |
| timeline | lanes of blocks over time | 6 lanes, 24 blocks; blocks only, no signal levels |
| sequence | actors and messages | 4 actors, about 7 messages fit |
| circuit | combinational gates, values computed | 14 parts, about 3 levels; no feedback, no blocks (MUX, register) |
| memory | stack frames, heap objects, pointers | 4 frames, 4 objects of 5 fields |
| formula | up to 4 TeX lines worked step by step | 22 symbols a line |

Tested in real videos so far (P4 30 random topics, P5 7 views, va4 10 topics, head-to-head 10): MIT 6.006, 6.042,
6.0002, an ML course, 18.01, 18.02, 18.03, 18.650, 18.404, 18.06, COS 226, Michigan EECS 489 (networks), LSU CSC
4103 (OS), Cambridge Digital Electronics.

## 2. Desk audit: 41 areas (ACM CS2023 knowledge areas, and undergraduate maths)

Strong = the views fit the area's usual pictures and real videos drew them. Drawable = the views fit, never run.
Partial = some of the area's usual pictures have no view. Weak = most of them have none.

| Area | Rating | Missing (what the usual pictures need) |
|---|---|---|
| Single-variable calculus | Strong | |
| Ordinary differential equations | Strong | |
| Discrete maths, logic, proofs | Strong | bipartite arrow diagrams for functions and relations |
| Probability | Strong | |
| Statistics | Strong | box plots, error bars, stacked bars |
| Algorithms | Strong | strings longer than 12 (KMP, Rabin-Karp); recursion trees labelled fib(3); NP reductions |
| Data structures | Strong | B-trees (several keys a node), tries untested, hash chaining, skip lists |
| Theory of computation | Strong | Turing machine tapes longer than 12 |
| Operating systems | Strong | paging and inodes untested |
| Machine learning | Strong | layered neural-network diagrams (more than 12 units) |
| Real analysis | Drawable | |
| Euclidean and analytic geometry | Drawable | |
| Numerical analysis | Drawable | floating-point bits (32 or 64) |
| Optimisation, linear programming | Drawable | 3D feasible regions |
| Fourier analysis, signals | Drawable | |
| Dynamical systems | Drawable | dense bifurcation diagrams |
| AI (search, games, Bayes nets, RL) | Drawable | |
| Systems fundamentals | Drawable | |
| Multivariable calculus | Partial | vectors, lines, planes and curves in 3D; a rotating view; change of variables (nonlinear grid map) |
| Partial differential equations | Partial | heat maps of a 2D domain |
| Linear algebra | Partial | span, planes, null space, cross product in R3 |
| Complex analysis | Partial | conformal maps (a nonlinear map of the grid) |
| Abstract algebra | Partial | cyclic groups on a circle; symmetries of a polygon as moves |
| Number theory | Partial | modular arithmetic on a clock (circular layout) |
| Combinatorics | Partial | lattice paths, balls into bins |
| Graph theory | Partial | bipartite, circular and fixed layouts (K5, Petersen); more than 15 nodes |
| Set theory, cardinality | Partial | bijection diagrams |
| Differential geometry | Partial | surfaces in 3D |
| Computer architecture | Partial | latches and flip-flops (feedback), clocked steps, waveforms, MUX/ALU/register blocks, 32-bit words |
| Networking | Partial | more than 7 messages (TCP fell back in va4); header bit fields; subnet masks |
| Databases | Partial | joins (3 tables), B+ trees, ER diagrams (attributes, cardinalities), SQL longer than 6 x 14 |
| Programming languages, compilers | Partial | token streams, type derivations, any code longer than 6 x 14 |
| Security, cryptography | Partial | byte-level stack layouts (buffer overflow), bit strings |
| Graphics | Partial | 3D projection and cameras, colour spaces |
| Parallel and distributed computing | Partial | rings (consistent hashing, Chord); 5 nodes in a consensus protocol |
| Topology | Weak | continuous deformation, surfaces (Möbius strip, torus) |
| Programming fundamentals | Weak | code itself: variables, loops, functions need 10-15 lines of 30-40 characters beside their state |
| Software engineering | Weak | UML class boxes with compartments, git commit graphs in lanes |
| HCI | Weak | screens and wireframes |
| Specialised platforms (web, mobile) | Weak | DOM trees with tag names, request flows with code |
| Society, ethics, professionalism | Not visual | flow and pictograms are enough |

Count: 10 strong, 8 drawable but never run, 17 partial, 5 weak, 1 not visual. Most gaps trace to a few shared
causes, not to one view per topic.

## 3. The causes, and what would close them

Ranked by how many areas each one opens up and how often those areas are taught.

A. **The code view is too small** (6 lines of 14 characters). Hurts programming fundamentals, PL and compilers,
   software engineering, SQL, security, web, and algorithm code traces: intro programming is the most taught
   CS course. Build: a code view of up to 14 lines of about 36 characters when it is the main view, lines lit,
   a value written beside a line (x = 3), and a variables panel kept in step with memory or cells.
B. **No overflow strategy.** Every view refuses past its cap, so a big textbook example falls back (TCP's
   handshake, long arrays, big graphs). Build, per view: a window that shows part of a long array or string
   with an ellipsis, a sequence whose old messages scroll up, collapsed subtrees, a circuit drawn as named
   blocks; longer node labels (5 characters at a smaller size: fib(3), "cat").
C. **No long strings or bit fields.** Build a tape view: up to 32 characters or bits, grouped (bytes, nibbles),
   a head, a pattern aligned under a text and shifted, brackets naming fields (tag/index/offset,
   sign/exponent/mantissa, network/host). Opens string algorithms, Turing machines, encodings, floating point,
   subnetting, caches, ciphers.
D. **No 3D.** Build a space view: points, vectors, lines, planes, parametric curves and surfaces, a camera
   that turns between snapshots. Opens R3 linear algebra, multivariable calculus, graphics, differential
   geometry, part of topology. The most work, and renders are slower.
E. **Only linear maps of the plane, and no colour scale.** Build axes.grid with any f(x, y) (complex maps,
   polar and other coordinates, Jacobians), and a heat map (a 2D grid or region coloured by value: PDEs,
   images, attention, confusion matrices, densities).
F. **Few layouts and box shapes.** nodes: circle, bipartite, layered and fixed-position layouts, and nodes
   holding several keys (B-trees). flow: record boxes with compartments (UML classes, ER entities, structs,
   packet headers). Opens number theory, groups, graph theory, functions, neural nets, databases, SE, rings.
G. **Combinational logic only.** Build feedback with clocked snapshots (latches, flip-flops, counters),
   blocks (MUX, decoder, register, ALU) and a waveform lane on the timeline.
H. **Small chart gaps.** Box plots, error bars, grouped and stacked bars on axes.
I. **Conceptual topics** (ethics, process models, HCI principles): keep flow, pictograms and words. Not worth
   a view; the plan should say so honestly instead of forcing a picture.

Two things every new view needs, or coverage won't turn into good videos:
- **A brief that scales.** The planner's brief is already about 27k characters with 20 worked examples; each
  new view adds its rules and an example. Load only the views and examples a topic's area needs (as the old
  storyboard_modules.py did for templates), so the prompt stays short and the planner picks well.
- **A fixed benchmark**, so coverage is measured, not guessed: section 4.

## 4. Measuring it: a coverage benchmark

- About 2 topics per area, so roughly 80 topics, each a short knowledge-unit stub (title, summary, the
  example a lecture would use) written by hand, with no slide extraction (that cost $0.80 a course in P5).
- Planner only: the program call (up to 3 tries), the sandbox, layout and still frames of each snapshot. No
  voices, lines or video. Measures, per topic: a Picture drawn or not, which view, number of snapshots, refused
  for size, and whether the stills show the idea (checked by hand on a sample, or by the visual critic).
- Cost: a program call is about $0.027 (va4: 5.3k input, 1.3k output, 16k cached), about 1.9 tries a topic,
  so about $0.05 a topic: **about $4-5 for 80 topics**, plus about $1 if the visual critic judges the stills.
- Run it once now for a baseline, then after each group of views below.

## 5. Order of work

1. Benchmark baseline (section 4).
2. A + C: bigger code view and the tape view (most of the CS gap: programming, PL, security, strings, bits).
3. B: overflow in each view and longer node labels (the fallbacks seen in real runs).
4. F: layouts, multi-key nodes, record boxes.
5. E: nonlinear plane maps and heat maps.
6. Brief routing by area (needed by step 4, when the brief would pass about 35k characters).
7. D: the 3D view.
8. G and H: sequential logic and waveforms; chart extras.

Rerun the benchmark after steps 3, 5 and 7. The success bar to agree on: a Picture drawn for at least 90% of
benchmark topics, and the strong-or-drawable rating reached in at least 35 of the 41 areas.

## Built (2026-11-15, branch visual-coverage, uncommitted; no LLM spend)

User skipped the baseline (section 4) and asked for steps 2-8 straight away.

- **2. Code and tape.** code(): up to 30 lines, each wrapped onto rows of about 14 characters (a leading space
  counts half; font 28 when it saves a wrap), the window scrolls to keep the lit line in view (grey arrows mark
  more above or below), c.mark/c.unmark, c.set(i, text), c.watch(name, value) chips under the code.
  **Deviation:** the plan said "14 lines of about 36 characters"; the dialogue frame is 3.9 units wide and the
  audit's minimum font is 28, so a row holds about 14-15 characters whatever we do. Wrapping and short-line
  instructions are the answer, not a wider panel. New tape(): up to 64 one-character cells, wrapping by groups
  (bytes, nibbles), cells sized by their widest symbol, heads, field brackets (labels drop to a second row
  rather than touch), up to 3 aligned rows (a pattern slid along a text, carries). Sandbox gains bin, hex, oct,
  format, chr, ord, complex, iter, next.
- **3. Too big for the frame.** Arrays up to 32 (a window follows the marked and pointed-at cells, "…" on the
  cut side, real indices); sequence diagrams up to 16 messages (the oldest scroll up; the va4 TCP fallback case
  now draws all 10 messages); node labels up to 4 characters (a pill in trees: fib(4)'s 5 leaves fit); caps
  raised where the layout already refuses what doesn't fit (20 nodes, 16 boxes, 12x10 tables, 6 frames and
  objects). **Not done:** folding a subtree into a "…" marker.
- **4. Layouts and shapes.** nodes layouts 'circle', 'bipartite', 'layered', 'fixed' (placed by rule, fitted
  to the band, never moved to get clear; refused with the reason when links pass too near nodes); B-tree nodes
  (keys=[...], set_keys, children hang from the gap by slot); flow records (fields=[...], font 28) and arrow
  kinds (line, dashed, inherit).
- **5. Maps and heat.** axes.grid(f=..., over=...) sends a grid through any map, a pair or a complex number;
  axes.heat(F) colours the plane under everything; grid.heat() colours a table's numbers, the text black or white
  by contrast.
- **6. Brief by area.** scene/brief.py split into per-view rules; five areas (algorithms, systems, calculus,
  discrete/probability/statistics, linear algebra) each get their views in full, a one-line index of the rest
  and their worked examples (17-24k characters against 37k for the whole brief); a topic is placed by phrases in
  its title and summary (snapshot_beats.picture_area), the whole brief when no area clearly leads, or with
  SYLLABYTE_BRIEF=full. On 557 extracted topics from 14 earlier runs: OS 48/56 systems, linear algebra 36/39
  linear, algorithms courses mostly algorithms, the rest mostly the whole brief; few clear misroutes, and a
  misrouted topic still has every view in the index.
- **7. 3D.** space(): points, vectors, segments, planes cut to the box, polygons, space curves, z = f(x, y) and
  parametric surfaces, one true scale, shaded faces far to near, s.turn(azimuth, elevation) between snapshots
  (one scale for every camera so nothing grows). **Limit:** a solid cross-fades when the camera turns rather
  than rotating smoothly.
- **8. Hardware and charts.** circuit blocks MUX, MUX4, DEC, HA, FA, DFF with 'key.port' outputs; c.tick();
  a DFF's D may come from a later gate, its wire looping up a lane of its own at the right; timeline signals
  (square waves: timing diagrams); axes.boxplot (computed, named), axes.errors, stacked bars (base=).

Checks: 24 new worked examples (scene/examples.py COVERAGE_PROGRAMS) and the 24 old ones render in the dialogue
frame with no layout findings; tests/test_visual_coverage.py (55 tests); whole suite 812 passed, 102 skipped.
Not checked: whether the planner uses the new views well in real videos (needs an LLM run).

## First LLM run (2026-11-15, runs/cov1, 12 topics from courses already extracted)

Topics picked to need the new views (COS 226, digital logic, networks, linear algebra, multivariable, 6.042,
ML, data science, statistics). Routing put 11 of 12 in an area brief (one got every area).
- 7 of 12 built from snapshots (VA 5, 5, 6, 6, 6, 4, 6: mean 5.4); 5 fell back after three programs (VA 5, 5, 5,
  1, 4: mean 4.0). All 12: VA 4.83, accuracy 5.67, coherence 5.42, appropriateness 5.83 (new, harder topics:
  not comparable with va4's 6.0 on other topics).
- New calls used in real videos: circle layout (sequence-number space), tape with rows (ripple-carry adder),
  errors() (error bars), space() (twice, both lost to fit), layered layout (lost to fit).
- Why the 5 fell back: a formula of 4 lines needs 3.6-4.0 of the 4.7 units by itself, so it can't share the frame
  with a 3D scene or axes (3 topics: complex eigenvalues, slicing a solid, the Hessian); an 8-row truth table took
  the frame from a layered network (DNF); fib's call tree passed 20 nodes, then a 7-character table entry.
- Not used where they fit: TCP header drawn as a grid (not tape fields), ripple-carry not FA blocks, circular
  queue as plain cells (not a circle).
- Cost: $2.66 recorded; two runs per course at once overwrite each other's manifest, so about $0.35 more
  (circular queue, TCP header) went unrecorded: about $3.00 against the $2.20 estimated. Most of the extra is the
  fallbacks (three programs plus the old planner: fib $0.52, DNF $0.42).

## Sizing so the diagram wins (2026-11-15, after runs/cov1; no LLM spend)

User's direction: adjust sizes automatically, diagrams larger and formulas smaller.
- A formula line takes the height its TeX needs: 0.52 units plain, 0.75 with a fraction or matrix, 0.9 with a
  sum or integral (limits above and below); it was 0.9 for every line. Short of room, the formula shows its
  newest lines and the older ones scroll up (a grey arrow marks them). A line is never drawn below font 28.
- One layout per run of snapshots that show the same views (layout.plan_groups): a 3D scene or graph has the
  whole frame until a formula or code panel joins it, then shrinks, animated. The fit check uses the same groups.
- A 3D scene keeps one true scale only when its x, y, z ranges match; otherwise each axis fills the box (the
  Hessian's dome over a small square was a spike).
- Tall tables scroll a window of rows that follows the marked rows (a truth table beside a network).
- Bug fixed: a view made after the first snapshot indexed its per-snapshot layout by the whole video's snapshot
  number and read past the end; any formula or code panel appearing mid-video would have crashed the render.
Result on cov1's own refused programs, re-laid out offline: 3 of the 5 fallbacks now fit and render clean
(complex eigenvalues, slicing a solid, the Hessian). The other two are planner mistakes (a network squeezed under
a table and a diagram; fib's tree 8 leaves wide). 813 tests pass; all 48 worked examples render with no findings.
Next: commit; rerun the 5 fallback topics (about $1) to see the planner use the room.

## Responsive composition (2026-11-15, after runs/cov2)

The slicing topic spent about 83 seconds across three refused picture programs and two fallback plans. Its
3D scene, axes and formula did not fit together; two program attempts repeated the same oversized composition.

- Layout can reclaim space from a supporting formula before refusing the composition: older working scrolls,
  down to one readable line when necessary, without reducing the diagram's minimum size or the formula's pitch.
  Compaction retains explicitly marked, highlighted or boxed working and the newest line. Normal layouts
  still prefer two formula lines.
- Every view supports hide() and show(). Hidden views retain their contents and identity; snapshots include
  only visible views. At most three views are visible at once, with at most twelve created over the program.
  The existing renderer reallocates space and animates transitions when the set of visible views changes.
- Fit errors identify the failing snapshot group and named views, include inter-view gaps in required height,
  and suggest splitting the composition with hide()/show(). Planner instructions distinguish fit failures
  from runtime errors and preserve the slide's example, snapshot order and wrong-answer steps.
- Added a worked solid/cross-section example to the calculus and full briefs. Positioning and sizes remain
  computed by code; switching the teaching view remains an explicit planner decision.

Validation: 819 tests passed, 102 skipped; two unrelated retry tests cannot bind local sockets in this sandbox.
The solid/cross-section/solid transition and a compact-formula scene both rendered with no layout findings
(runs/layout-solver-check). No API spend. Planner retry rate and teaching quality need a later live comparison.

Regression check against cov2's actual refused slicing program: inserting s.hide() before its cross-section
preserves all 15 snapshots and passes layout. Rendering caught a separate formula-spacing bug: the height
classifier's regex word boundary missed operators followed by an underscore (such as \\int_0 and \\sum_i), so
integrals were allocated plain-symbol rows. TeX command detection now treats underscores as command boundaries.
The same saved program then rendered without layout findings (runs/layout-fix-test/offline-render).
The fresh single-topic comparison runner at runs/layout-fix-test/live.py records time, cost, program and
fallback attempts, layout findings and critique scores in a new timestamped directory on each invocation.
After the operator-spacing fix: 823 tests passed, 102 skipped, with the two sandbox-blocked socket tests
explicitly deselected.

Live check run from the user's terminal (runs/layout-fix-test/live-20261115-222607-293394): the slicing video
completed in 50.28 seconds for $0.1654 recorded, versus about 114 seconds and $0.3287 in cov2. The planner used
hide() to switch views; two program attempts (first refused an empty formula line), no fallback planning calls,
and no layout findings or remaining render issues. Critic visual alignment rose from 5 to 6 and accuracy from
7 to 8, but the overall critique still failed. The graph also clips the negative part of S(x) because its
vertical range starts at zero. This single run supports the layout improvement, not overall teaching quality.

## The benchmark, run (2026-11-16, runs/bench1)

80 hand-written topics, 2 for each of the 40 visual areas (benchmarks/visual-coverage/topics.json), through
the real picture planner only (scripts/visual_benchmark.py: plan, render, judge, report; it resumes). $4.84 in all
($4.14 planning, $0.70 for the critic judging contact sheets of the stills).

- Picture drawn for **70/80 (88%)**, on the first program only 16/80. Critic: good 17, partial 53, none 10; mean 5.6.
- 8 of the 10 lost were too wide for the 3.7-3.8-unit band (trees, a UML diagram, a form, actor names, a memory
  diagram, a table beside code); 2 were a colour name ('teal', 'green') on the last try.
- Partial pictures: the topic's standard picture not drawn though a view has it (a box plot without a box, Euler
  without a slope field); numbers only in the captions; a picture that contradicts its caption; cramped axes.
- The desk audit (section 2) was too kind: statistics, algorithms, data structures and AI scored 2.0-3.5 of 10.

## Fixes (2026-11-16, no API spend)

The width is the phone's: the 9:16 frame is 4.5 units across whatever the characters do (they sit in the band
below), so the fixes use height and stop wasting width.
- Colour words map to styles (teal -> visited, green -> found, purple -> blue...), not a refusal.
- Trees: each node takes its own width (a wide parent widens only its own subtree), with a tighter pad only when the
  usual one doesn't fit; B-tree key nodes no longer size the circles. Merge sort, a B-tree, a DOM tree and a game
  tree now fit.
- Sequence: each actor box as wide as its name; when they still don't fit, every other box drops half a row.
- Flow: boxes never on screen together in one layer share a place (a removed box and its replacement); a layer too
  wide splits onto rows, the arrows passing through slots. Record widths 6% wider (a field ran past its box).
- Memory: too wide side by side -> stack frames above heap objects, each pointer in its own lane at the right.
- Tables may use the band's spare edge (0.04, not 0.1) when only the spare is in the way.
- Caps the layouts already measure were relaxed: table entries and memory values 10 characters (was 6), tree node
  labels 6 (graph nodes stay 4), memory titles 14, records 6 fields of 20.
- Brief: the topic's standard picture by topic (box plot, slope field, hash chains as a fixed layout, a ring, z and
  w planes, address fields on a tape...), every number the caption relies on drawn, each snapshot showing its
  change, at most 6-8 ticks.
Offline on bench1's 30 refused programs: 18 now draw (was 0); 9 of the 10 lost topics have a program that draws
(the closure's memory diagram stacked needs 5.6 units of height, 4.2 fit). 872 tests pass (13 new in
tests/test_benchmark_fixes.py); all 49 worked examples render with no layout findings. Not yet measured live.

## Targeted rerun (2026-11-16, runs/bench2, $1.49)

The 10 lost topics and the 10 lowest scorers (all five 3s; of the ten 4s, the five the new brief names: hash
chains, z^2, D4, IEEE, the heat map, so the choice favours the fixes).
- Lost 10: drawn 0 -> 9, good 0 -> 2 (alpha-beta 7, B-tree 8), mean of drawn 5.8. Still lost: the closure (stacked
  memory needs 5.1 of 4.2 units).
- Low 10: all drawn both times, mean 3.5 -> 4.6, still no good. Hash chaining first fell back (the new advice drew
  all 10 buckets down the frame; advice now says the buckets used, at most 6) and redrawn: partial 6.
- Found and fixed after: (1) an empty tree snapshot crashed the render (old bug, the DOM topic); (2) a wide grid was
  turned on its side even when it is a picture of space (the plate's hot top edge became the left column, bench1's
  pixel grid too): square grids, heat maps and grid(..., turn=False) are never turned; (3) labels the layout leaves
  out were silent: 36 of bench1's 118 drawable programs lost labels the captions rely on (Euler's 1.5 and 3.375, the
  LP's constraint names, t=.05); they now go back to the planner as a problem (one redraw), except bare axis names.
These three are not yet measured live. 876 tests pass.
