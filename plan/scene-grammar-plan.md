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
  API and examples; 10 COS 226 topics end to end, timed (keep <= ~60-75 s per video).
- **P2:** axes and space views for Math (regions, Riemann sums, fields, level curves, 3D, any-set Venn) with sympy.
- **P3:** layer 2 (checked codegen on primitives), icon set, miss log.
- **P4:** benchmark; templates kept only where they beat the grammar.

## Risks

- Layout quality in a 4.5-unit-wide portrait frame is the hard part (trees wider than the frame, dense graphs).
  Mitigation: tidy layout + scale-to-fit with a minimum size; refuse (and ask for a smaller example) past it.
- Object identity across snapshots, so things move instead of blinking: every object has an id the program gives
  or the engine derives (node keys, cell indices).
- Writer quality: a program can be correct and still a poor example. The critic and line matching stay.
- Effort: a rewrite of the drawing layer, several weeks; phases keep the current videos working throughout.
