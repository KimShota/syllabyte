# Scene grammar: a picture for any CS or Math topic (plan, 2026-11-11)

## Goal

Every video gets a picture that is made for it, whatever the topic: no slide images, no "formula only" fallback for
a topic we never built a template for. Templates per topic can't get there: the 2026-11-11 audit found that every
picture *family* now has a template, but inside the families a third of COS 226 has no computed picture (union-find,
2-3 and red-black trees, k-d trees, Bellman-Ford, max flow, cycle detection, shellsort, a code panel), and math has the
same tail (Riemann sums, level curves, vector fields, ODE systems, 3-set Venn diagrams, probability trees). Each new
course brings more. The long tail never ends, so the drawing layer has to compose pictures, not pick them.

## The idea: content, computation and drawing kept apart

Pictures in CS and Math are built from a few visual forms, though the topics are endless:

| Form | Covers |
|---|---|
| **node-link** | trees of any arity (BST, 2-3, red-black, tries, k-d, union-find forests, recursion trees, factor trees, probability trees), graphs and digraphs, flow networks, automata, pipelines, adjacency lists, pointer diagrams |
| **cells** | arrays, strings, stacks, queues (incl. circular), hash buckets, DP tables, matrices, truth tables, pixel images (heat maps) |
| **axes** | functions of any form, regions, Riemann sums, tangents, vector fields, level curves, slope fields, data plots, 3D surfaces |
| **space** | geometric constructions, Venn regions (any number of sets), physical objects: containers with levels, a balance, cards, coins, icons |
| **text** | formulas, code with the current line lit, labels, notes |

Vega-Lite (any chart from a grammar), Graphviz (any graph from a description) and Penrose (math diagrams from
"what the objects are" kept apart from "how they look", with an optimiser doing the layout) show this works. So:

1. **The LLM writes only content.** The objects, and the algorithm or the math as a short program. It never places
   anything on screen or picks a colour by number.
2. **Code computes everything shown.** The program runs (in a sandbox) and the state is recorded at each `snap()`:
   the steps come from executing the real algorithm, so they are right by construction. Math values come from
   numpy/sympy, never from the model.
3. **The engine draws.** It lays out each snapshot automatically (tidy trees of any arity, layered or force layout
   for graphs, rows and grids for cells, axes for plots), keeps to the layout audit's rules, and animates the
   change between snapshots by object identity: a node that moved slides, a recoloured cell recolours, a new link
   grows, a removed one fades.

A new kind of picture is then a few lines of content, not a new template.

## The program the writer writes

A short Python program against a small API (prototype names):

```python
id = cells("id", list(range(8)))          # an array, one cell per index
f = forest("f", nodes=range(8))           # node-link, any arity, parents drawn above children
code = code_panel("code", ["root(p): while p != id[p]: p = id[p]", "union(p, q): id[root(p)] = root(q)"])

def root(p):
    while p != id[p]:
        code.line(0); f.mark(p, "current"); snap(f"{p} is not its own parent, so go up")
        p = id[p]
    return p

def union(p, q):
    i, j = root(p), root(q)
    id[i] = j; f.link(i, j); code.line(1)
    snap(f"union({p}, {q}): root {i} goes under root {j}")

union(4, 3); union(3, 8)
```

Each `snap(caption)` is one picture state; the storyboard's beats step through them (`p.step()`), so the
existing beat timing, line matching and checks keep working. Views a program can make: `cells`, `grid`, `forest`/
`tree`, `graph` (directed, weighted, edge labels like `3/10`), `code_panel`, `axes` (functions, regions, fields,
points), `container`, `balance`, `icon`, `venn`. Styles are semantic (`current`, `visited`, `found`, `red`,
`compare`), mapped to the colours that already pass the contrast rules.

## Layers, tried in order

1. **Grammar program** (above): most pictures.
2. **Checked code against the grammar's primitives** when no view fits: the LLM writes drawing code that may only
   use the engine's building blocks (never raw Manim), checked by running it, by the layout audit and by one frame
   shown to the critic. This brings back the proposal's LLM-codegen Component 4 in a narrow, checked form (a step
   back toward the proposal; note it in the report).
3. **Formulas and text** only if both fail, and every such miss is logged: each one becomes a new primitive in the
   grammar (never a one-topic template), so the tail shrinks.

No slide images at any layer (user decision, 2026-11-11). Physical and metaphor pictures (water jugs, a balance
scale, playing cards, an agent and its environment) are drawn: their state is usually computable (fill levels,
tilt from weights, a hand of cards is an array), and objects come from an open-licensed SVG icon set placed by the
grammar. No AI-generated images: slow, inconsistent in style, and wrong on text and counts.

## How it fits the pipeline

The grammar is one more template to the storyboard: `p = Picture(program="...")` then `p.step()` (next snapshot)
or `p.step(to="label")`. The writer sees the API and worked examples instead of N template specs. The program runs
when the script is written (calls.check_segment already simulates calls with no Manim), so a program that errors,
loops (time limit) or makes too many objects for the frame is refused there and sent back once with the error, as
call errors are today. Today's templates stay as presets while the grammar grows; nothing breaks.

Sandbox: the program runs in a subprocess with a time and memory limit, no imports, no file or network access,
builtins limited to pure ones; it returns snapshots as JSON.

## Proof: a held-out benchmark

"Any" can't be proven, so it is measured: about 300 topics from CS and Math courses we never developed on (spread
over the ACM CS2023 knowledge areas and a standard undergraduate math sequence). Score: the share with a correct
picture from layers 1-2, by the critic plus a hand check of a sample; also the share that fell to layer 3. That
number goes in the report.

## Phases

- **P0 prototype (now):** snapshot model, sandbox runner, node-link (tidy layout, any arity), cells, code panel,
  container; change animation by id; hand-written programs (no LLM) for three topics with no template today:
  union-find, a left-leaning red-black tree insert, the water-jug problem. Rendered in the dialogue frame with no
  layout findings. Question answered: can one generic engine draw these as well as a hand-made template?
  **Done 2026-11-11** (branch `scene-grammar`, uncommitted): `animation_agent/scene/` (api, sandbox, layout, draw,
  examples), `scripts/scene_demo.py`, `tests/test_scene_grammar.py` (17 tests; suite 648 pass). All three render in
  the dialogue frame with no layout findings; program 0.02 s, render 2-6 s. The red-black tree is checked valid
  after every fix; the jugs are drawn to scale. Limits found: the portrait frame fits 8 nodes or cells across,
  about 4 tree levels under a code panel and an array, and about 14 monospace characters per code line at the
  minimum font (code must be short pseudo-code); the layout refuses past these with a reason the writer can act on.
- **P1:** `Picture` template in the storyboard (step through snapshots, captions to lines), writer prompt with the
  API and examples; 3 COS 226 topics end to end, timed (cut from 10 to save spend, 2026-11-12).
  **Round 1, 2026-11-12** (`SYLLABYTE_PICTURES=grammar`, runs/picture-p1; KUs from the elementary-sorts and
  shortest-paths decks, $0.57 to extract): Bellman-Ford, stability, decrease-key all made videos (94, 79, 134 s
  from a cold process; about $0.3 each), every program ran, but visual alignment was 2, 2 and 3. Causes, all in the
  wiring, not the idea: (1) `p.step()` means "the next snapshot", so when code moved or dropped a step (a reveal
  held off a question line, a refused call) every later picture landed on the wrong line, and in one video every
  step vanished; (2) problem messages quoted the whole program first, so the reason was cut off for the planner
  and the log; (3) a Picture sharing the frame with a formula gets two thirds of it, and the graph layout refused
  the slide's 8-node, 15-edge digraph there, so the planner pruned it to the tree and dropped `distTo[]`, then lost
  the Picture altogether; (4) cells stayed at their minimum size in an empty frame. Fixed: snapshots are named and
  shown by name (`snap('...', name='swap1')`, `p.show(snap='swap1')`); long calls are cut in problem messages; the
  graph layout tries 50 arrangements stretched to the band, places each weight label clear of nodes and labels,
  keeps the fewest crossings, and refuses with what to change; cells grow with their font; INF draws as ∞; plans
  are saved with `SYLLABYTE_PLAN_DUMP` and the log counts Picture calls after each stage.
  **Round 2, 2026-11-12** (round 1 kept in runs/picture-p1/round1; about $0.9): visual alignment 2, 4, 5
  (Bellman-Ford, stability, decrease-key; was 2, 2, 3), 139, 66, 135 s. Decrease-key's picture now plays the
  whole swim with `qp[]` kept in step (10 shows, one still line), though its first half only marks v2. Stability
  lost 6 of 10 shows in the fix pass (a top_half area that didn't fit, a name the program never snapped).
  Bellman-Ford's first plan was the slide's full graph (8 nodes, 16 edges, distTo 0 5 14 17 9 13 25 8, right),
  refused for a bug of ours: calls are read as raw strings (for TeX), so the writer's `\'` reached the program
  as a backslash and a SyntaxError. The redraw then cut the graph to 5 nodes with an invented 3->4 edge, added
  formulas (so two thirds of the frame), and was refused for an 18+ character title and the string 'INF'; the
  Picture was dropped and the critic marked the invented values (accuracy 2). Fixed: escaped quotes are
  unescaped in program lines, the string 'INF' draws as ∞, and the brief states the title limit. The first
  program now passes as written and renders with no layout findings. **Bellman-Ford rerun** (109 s, about $0.3; round 2's in
  runs/picture-p1/round2): visual alignment 3, accuracy 3. The Picture reached the video this time (4 shows), but
  the plan again put formulas beside the full 8-node, 16-edge graph; refused in two thirds of the frame, the fix
  pass cut it to 6 nodes and 7 edges with its own weights while the lines and the formula box kept the slide's
  (8 vertices, 16 edges, 7*16), which the critic marked. Three plans out of three paired a big graph with
  formulas despite the brief, so this needs a rule in code, not in the prompt. Rule (user's choice, 2026-11-12): the picture wins.
  `normalize.make_room` drops every formula and note on screen with a Picture whose program fits the whole frame
  but no shared area, before the lines are written (and again after each fix), so the lines say the formula. On
  the rerun's plan it keeps all 10 shows (the run kept 4) with nothing refused. The graph looked tiny for the same
  reason (a 1-unit band beside the formula), so no separate scaling change was needed. **Rerun with the rule** (79 s, about $0.2;
  the previous one in runs/picture-p1/round3): visual alignment 5, accuracy 6 (was 3 and 3); all 11 shows reached
  the video, one still line, and the relaxations play one edge at a time beside a code panel. The rule didn't
  fire: the planner chose no formulas and its own 4-node, 5-edge graph instead of the slide's, which the critic
  marked as invented; the rest of its issues are the explanation (why V-1 passes is never answered). **Layout
  rework (user: "nothing should overlap ... always prioritize making visuals larger", 2026-11-12; no LLM spend):**
  the graph had been squeezed into a 1.6-unit band (0.8 for its nodes) above an array and a code panel that had
  grown into theirs, and the audit had seen nothing because links and their labels were marked background.
  Now (scene/layout.py): (1) arrays and code take their compact size first, the main picture (nodes, container)
  the rest up to what it can use, then arrays grow; (2) a graph tries node radii 0.32 to 0.2 and is kept only
  when nodes stand 0.22 apart, links pass 0.1 clear of other nodes, links leave a node at least 22 degrees apart,
  a->b and b->a are drawn side by side, and every weight sits beside its link or set into it (the link drawn
  with a gap), clear of every node, link and other label, 0.1 from other labels and no nearer another link;
  fewest crossings, then largest nodes, win; (3) when no arrangement passes, the best 8 are refined by an
  optimiser (a penalty over node positions, Penrose-style, keeping room for labels at link middles); (4) a
  title gives way when the main picture is short or can't be drawn (the slide's full Bellman-Ford graph with
  all 16 weights fits beside its array untitled); (5) nodes are sized to hold their labels; pointers on one cell
  stack; (6) a refusal names what took the room ("the other views take an array 1.1, the code panel 1.4: drop a
  view ... before making the example smaller"); (7) links and labels are no longer background, so the render
  audit checks them. All 7 programs (3 examples, 4 from the runs) render with no findings; the Bellman-Ford
  video re-rendered from its script with 0 findings in all 5 segments, its graph about twice the size. Cost:
  a dense graph takes up to about 4 s to check (cached); the test suite went from 18 to 40 s. Limits: three
  views in the portrait frame still leave the array at its compact size; union-find's single-node trees sit
  close.
- **P2:** axes and space views for Math (regions, Riemann sums, fields, level curves, 3D, any-set Venn) with sympy.
  **Built 2026-11-12** (no LLM spend; videos not yet made): `axes` (plot, which breaks where f is undefined; area;
  riemann, returning the total; tangent, returning the slope; line; point; field; contour by marching squares),
  `venn` (1-3 sets, regions as expressions such as `(A|B)-C`, elements in their regions) and `geometry`
  (points, segments, circles, polygons, angle arcs returning degrees, one scale for x and y); math helpers in the
  sandbox (sin ... gcd, derivative, integral by Simpson's rule, root by bisection, Fraction). All values come
  from running the program. Layout in `scene/math_layout.py`, with the same rules as graphs: tick labels outside
  the plot, labels clear of everything on screen with them (a curve's label set into the curve when there is no
  room beside it, contour-plot style; vector-field arrows give way to labels), Venn elements tested inside their
  own region, titles clear of axis names. Things keep their keys, so a Riemann sum going from 4 to 8 rectangles
  morphs. Six worked examples (Riemann sums, secants to tangent, level curves with a gradient field, 3-set
  Venn, a triangle's angles, a probability tree with Fractions) render with 0 audit findings; 12 new tests.
  Deviations: no sympy (pure Python numerics in the sandbox keep it import-free; exact symbolic forms are not
  available yet); Venn diagrams stop at 3 sets (4 or more need ellipses or a membership table); 3D surfaces
  are deferred (a 3D camera in the portrait frame is its own piece of work).
  **First run, 2026-11-12** (runs/picture-p2; MIT 18.01 lecture 15 and 18.02 week 7; about $0.85 in all): linear
  approximation of 65^(1/3) 64 s, visual alignment 3; exchanging the order of integration 101 s, 5; the polar
  area element 93 s, 3. The planner wrote sound programs every time (the tangent at 64 beside x^(1/3), the region
  between y = x and y = sqrt x with its slices, polar patches), but three things lost them: (1) one label with
  no clear place refused the whole picture, so the planner dropped the formulas (linear approximation) or drew
  again (exchange order); (2) the polar program passed a coordinate pair where geometry wanted a point's key,
  then lost its closing ')' on the redraw, so the segment fell back to written code and the rest showed only
  formulas; (3) the audit compared a label with a curved region's bounding box. Fixed: a label with no clear
  place is left out (never drawn over anything) and the picture kept; geometry takes (x, y) wherever it takes a
  point, and gains arc() and sector() (a polar patch, returning its area); a call missing only its closing
  brackets is closed; blank labels count as none; the audit tests a filled shape's outline; 65^1/3 is no longer
  shown as a power. Every planned program from the run is now accepted and renders with 0 findings.
  **Rerun of the two weak ones** (about $0.34; round 1 in runs/picture-p2/round1): linear approximation 60 s,
  visual alignment 3 -> 5 (accuracy 7), the picture now beside its formulas throughout; the polar area element
  69 s, 3 -> 4 (accuracy 8), the Picture drawn this time, but all its steps lost: one beat removed a formula and
  made the next, and the layout counted both on screen at once, so the new one got no area, was refused, and the
  fix call that followed took the picture's shows; its formulas were also drawn broken ("r\\, dr": a doubled
  backslash before a spacing command is a TeX line break). Fixed: objects are timed by their call's place in the
  beat, so a removal frees its area for what comes after it; a show of the snapshot already on screen is dropped
  by code, not sent to the fix call; a doubled backslash before \, \; \: \! is undoubled like one before a
  letter. The polar plan now settles in code with all its shows (5) and formulas (23). The subtitle font
  (Montserrat) has no Greek beyond pi, Delta and mu, so theta showed as a box: captions now draw any character it
  lacks in DejaVu Sans Bold (bundled, with its licence), and capitalise only Latin letters (delta stays delta).
  **Polar rerun** (73 s, about $0.38; the previous one in runs/picture-p2/round2): visual alignment 3 -> 4 -> 6,
  accuracy 8; the picture changes on 5 lines (the ray r, theta; a patch near the origin, one farther out), the
  formulas draw whole, and the captions show theta. P2 so far: 3 topics, visual alignment 5, 5, 6, about $1.38.
- **P4-lite coverage run, 2026-11-12** (runs/picture-p4; brought forward to decide P3; $5.35): 30 topics drawn at
  random (seed 20261112) from 8 courses the grammar was never developed on (MIT 6.006, 6.042, 6.0002, a machine
  learning course, 18.01, 18.02, 18.03, 18.650), 17 CS-side and 13 math-side; 29 videos made (one failed to
  assemble), 53-106 s each with 4 running at once. A computed Picture reached 23 of 30 videos (77%). By hand:
  13 good (the right picture, changing with the idea: DFS cost, finishing order, cycle witness, error bars,
  confidence intervals, sampling distributions, tower functions, a perceptron, XOR, two antiderivatives, a
  centroid, a quarter disc in polar, resonance), 10 partial (present but weak: a number line forced onto axes for
  gcd and division, a short array for a factorisation, a 2D square for a volume, a picture shown on one line
  only), 7 none: 3 algebra topics planned as formulas only (substitution, guess-and-check, an ODE worked
  example), 2 that needed a bar chart (stratified sampling, explained variance) and fell back to written code,
  1 whose formula's bad TeX failed every segment (the Hessian), 1 whose Picture call was cut off inside a string
  (components; no video). Critic visual alignment 5.5 with a Picture, 4.2 without (5.24 over all, accuracy
  6.1). No layout finding came from a Picture: all 8 findings were in formulas, notes or written code. Gaps,
  most common first: bars and histograms (data science, statistics), a number line (number theory, intervals),
  robustness (a too-long title refuses the picture; one bad formula takes its whole segment, picture included;
  a call cut off inside a string), 3D surfaces, and pictures shown on too few lines.
  **Gaps closed, 2026-11-13** (no LLM spend; not yet rerun): (1) charts on axes: bars (categorical names on the
  x-axis, on two rows when crowded, never dropped; values above each bar with headroom sized on screen, or white
  inside a tall bar), histogram (counts computed), points (a scatter as one thing); axes fit x to the data when
  no range is given; (2) a number line view: points, intervals with open or closed ends, jumps as arcs; (3)
  robustness: a too-long title or math label is left out, not refused; a formula LaTeX can't compile is drawn
  without the isolations that cut a command (h in \\theta, the Hessian's failure), then as plain text, so the
  segment and its picture survive; a call cut off inside a string, or ending in the wrong quote, is closed; (4)
  3D: a surface view drawn flat from one fixed angle (z = f(x, y) as shaded patches, columns under it for a
  double integral's sum returning their volume, points), faces painted far to near, opaque, kept out of the
  audit's shape overlap rule since they overlap by design, labels clear of every face edge; a solid cross-fades
  between snapshots rather than morphing; (5) a plan whose Picture changes on fewer than 5 beats (of 10 or
  more) is drawn again once, and the brief asks for a snapshot on most beats from first segment to last. Three
  new worked examples (a stratified-sample bar chart, division on a number line, volume under a surface); all 9
  math and 3 CS examples and the run's CS programs render with 0 findings; 686 tests pass.
  **Fix check, 2026-11-13** (5 topics, one per fix, instead of rerunning 17; $1.78, more than the $1 estimated:
  two plans were drawn again by the new check; old outputs in runs/picture-p4/before-fixes): every fix worked in
  a real video. Stratified sampling drew two bar charts (population, then the sample) instead of falling back to
  written code: visual alignment 2 -> 5. Division drew a number line with -11 = (-2)7 + 3 as a jump. The Hessian
  drew a 3D dome with its slices and kept every segment (no formula sank it). The double integral drew a surface
  and columns. The thin-picture check sent the MLE and Hessian plans back; MLE went from 1 to 8 shows. But
  visual alignment fell for three (division 5 -> 4, Hessian 5 -> 3, volume 6 -> 3), and the critic's reasons are
  the script, not the views: the volume video used 2 - x^2 - y^2 where the slide has 1 - x^2 - y^2 (accuracy 3),
  the Hessian's second function is never drawn, and key algebra steps are skipped. One finding came from a
  Picture (a label touching a tick mark): tick marks are now obstacles too.
- **P3:** layer 2 (checked codegen on primitives), icon set, miss log.
- **P4:** benchmark; templates kept only where they beat the grammar.

## Risks

- Layout quality in a 4.5-unit-wide portrait frame is the hard part (trees wider than the frame, dense graphs).
  Mitigation: tidy layout + scale-to-fit with a minimum size; refuse (and ask for a smaller example) past it.
- Object identity across snapshots, so things move instead of blinking: every object has an id the program gives
  or the engine derives (node keys, cell indices).
- Writer quality: a program can be correct and still a poor example. The critic and line matching stay.
- Effort: a rewrite of the drawing layer, several weeks; phases keep the current videos working throughout.
