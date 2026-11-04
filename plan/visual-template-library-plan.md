# Visual template library: the script picks the picture, tested code draws it (planned 2026-11-04)

Today the script writer describes each line's visual in a sentence, and a second LLM turns that sentence into
Manim code for each segment. A visual critic then looks at frames and asks for repairs. This plan replaces most of
that with a library of tested, data-driven Manim templates.
- **Script:** for each line, the writer chooses a template and fills in its parameters, in the same JSON it
  already returns.
- **Render:** the template draws the line with no code generation and no repair loop.
- **Fallback:** free-form code generation stays for lines no template fits.

Scope: CS and mathematics only, the subjects SyllaByte targets.

## Why

### Time
The two dialogue test videos (`runs/dialogue-videos/`, L2, low quality):

| Step | Eigenvectors | Bisection |
|---|---|---|
| Script (writer + critic) | 133 s | 81 s |
| Voices | 12 s | 21 s |
| Manim render (5 segments in parallel) | 135 s | 99 s |
| Assembly + band | 2 s | 2 s |
| Total | 294 s | 212 s |

Drawing frames took about 1–2 s per segment. The rest of the render step was LLM work:
- codegen, 4–6 calls;
- the visual critic and visual repair;
- layout repairs;
- eigenvectors segment 3 needed four code attempts.

Together that's 16–18 of the 19–21 LLM calls in each video, and roughly half the $1.3–1.6 it cost.

### Correctness
A free-form scene draws what the LLM believes the algorithm does. A template computes it:
- `ArrayBars.bisect(values, target)` runs bisection;
- `LinearMap2D(A)` gets the eigenvectors from numpy.

So the picture can't contradict the maths. That's an error a viewer can't spot and the critic often misses.

### Layout
Layout is the most common failure in published Manim agents:
- TheoremExplainAgent (Ku et al., ACL 2025, arXiv 2502.19400) reports that most of its videos have layout issues.
- Code2Video (arXiv 2510.01174) adds a critic just to fix element placement.

Each template is built and tested for the frames it renders into, so layout is right by construction:
- the dialogue frame: 4.5 × 5.6 units;
- the full frame: 4.5 × 8 units.

### Consistency
The same idea always looks the same: a list is always the same bars, and a pointer is always the same arrow.
Students learn to read the pictures once (signalling; lower extraneous load).

## Design

### Three layers
1. **Primitives** (`animation_agent/visuals/primitives.py`, about 10), shared by every template:
   - labelled box, arrow, pointer with label, highlight ring, counter;
   - split-screen comparison;
   - the faded "ghost" version of a wrong answer (for misconception lines);
   - colour-key colouring;
   - step-by-step reveal;
   - placement in grid areas that keeps everything inside the frame (wraps `layout.GridLayoutScene`).
2. **Templates** (`animation_agent/visuals/templates/<family>.py`, target 35–45). Each one:
   - takes data and works out its own steps;
   - offers named actions, one per line;
   - declares its parameters as a Pydantic model;
   - is built from primitives (about 100–200 lines each);
   - builds on `manim_dsa` where it already draws the structure (arrays, graphs, trees).
3. **Composition:** a line's spec may hold two templates placed in named areas, for example a code panel on top
   and an array below. Composition covers far more lessons than the template count suggests.

### The spec on each line
Each line keeps its `visual` sentence, which the critic reads and free-form codegen falls back on, and gains an
optional `spec`:

```json
{
  "narration": "Check the middle one first, it's seven.",
  "visual": "The middle cell lights up; the left half greys out.",
  "spec": {"template": "array_bars", "id": "list", "action": "bisect_step",
           "params": {"values": [1, 3, 4, 7, 9, 11, 15], "target": 9}}
}
```

- **State:** a template object is created on its first line (`id`) and persists across the segment. Later lines
  call actions on it (`"action": "grey_out", "params": {"side": "left"}`).
- **Timing:** comes from `beats.json` at render time, not from the writer. Each action's animations are scaled to
  60–85% of the line's recorded length, the same rule the codegen prompt uses now.
- **Validation:** every spec is checked against its template's Pydantic model, and every action against the
  template's action list, before rendering. A bad spec goes back to the writer with the error, the same way
  `validate_dialogue` works.

### The registry, and keeping the writer prompt short
The writer can't be shown 40 template definitions on every call. Instead:
- `visuals/registry.py` lists each template with:
  - its family;
  - a one-line purpose;
  - its parameter and action schema;
  - one worked example.
- A short selection step before writing shows the writer only the 3–6 templates that fit the KU. It's one small
  LLM call over the KU's text and `visual_idea`, or an embedding lookup.

### Fallbacks
Each line uses the first rung of this ladder that works:
1. **Template spec:** the expected path for most lines.
2. **Short codegen that calls the library:** the LLM writes a few lines using templates and primitives, for
   unusual combinations. This is shorter code with fewer layout bugs than today.
3. **Today's free-form codegen with repairs:** unchanged.
4. **The text-only scene** (`templates.build_template_scene`): unchanged.

The visual critic still runs, but only on rungs 2–3.

## Template families (initial list, to be reordered by the coverage study)

**CS**
| Family | Covers |
|---|---|
| `array_bars` | linear/bisection search, bubble, selection, insertion, merge, quick sort; pointers, swaps, halves |
| `code_trace` | code with a step-by-step line highlight and a variables panel; pairs with any other template |
| `call_tree` | recursion trees, the call stack, memoisation |
| `growth_curves` | O(1)…O(cⁿ) curves, operation counters, Big-O comparison |
| `linked_list` | insert, delete, reverse, pointer re-wiring |
| `stack_queue` | push/pop, enqueue/dequeue, BFS frontier |
| `hash_table` | buckets, hashing, collisions, chaining, probing |
| `tree` | BST insert/search/delete, heap sift, tree traversals, tries |
| `graph` | BFS, DFS, Dijkstra, minimum spanning tree, topological sort, connectivity |
| `dp_table` | filling a table in order with arrows to the cells each one depends on |
| `memory_refs` | variables, references, aliasing, mutation |
| `state_machine` | DFAs/NFAs, regular expressions, protocol states |
| `bits_logic` | binary/hex, two's complement, bitwise ops, logic gates, truth tables |
| `flowchart` | pipelines, control flow, system diagrams |
| `ml_basics` | network diagram, gradient descent on a loss curve, decision boundary, k-means |

**Mathematics**
| Family | Covers |
|---|---|
| `equation_steps` | algebraic rewrites, highlight a term, substitute, reveal |
| `number_line` | intervals, inequalities, sequences converging |
| `function_plot` | plots, transformations, limits, tangent lines, area under a curve, Riemann sums |
| `linear_map_2d` | vectors, grids, applying a matrix, eigen-lines, change of basis, determinant as area |
| `vectors_3d` | 3D vectors, planes, cross product, span |
| `matrix_ops` | multiplication, row operations, block matrices, factorisations (LU, QR, SVD) |
| `series` | partial sums, convergence, geometric series |
| `probability` | probability trees, sample spaces, distributions, sampling, Bayes as area |
| `stats_plots` | histogram, scatter, regression line, confidence interval |
| `counting` | counting grids, Pascal's triangle, permutations, combinations |
| `proof_steps` | induction (base case, step), contradiction, chains of implications |
| `sets_logic` | Venn diagrams, set operations, quantifiers, truth tables |
| `geometry` | constructions, triangles, circles, angles, transformations |
| `complex_plane` | complex numbers, roots of unity, eigenvalues in the plane |
| `polar_parametric` | polar and parametric curves |
| `slope_field` | ODE slope fields and solution curves |
| `bar_meter` | bar charts, meters and dials for any quantity |

That's 32 families. Several will split into more than one template (e.g. `tree` into BST and heap) once their
action lists are written.

## Coverage study: what "all" means

Our 38 KUs (`runs/stem-cs`, `runs/stem-math`) come from two courses, which is too few to rank families. So:
1. **Build a course set.** 10–15 public CS and Math courses with slides:
   - CS: MIT OCW 6.0001, 6.006, 6.042 (discrete maths), an intro ML course, a computer-systems course;
   - Maths: 18.01, 18.02, 18.03, 18.05, 18.06.
   Record each course's licence in `research_notes/`.
2. **Extract KUs.** Run `generate_shorts.py --n-videos 0` on each course.
3. **Classify.** Put every KU's `visual_idea` into a family, or "none fits", with a short LLM classification
   step (`scripts/visual_coverage.py`).
4. **Check the classifier.** Hand-check a random sample of 50 for accuracy.
5. **Report.** The output is a frequency table and a cumulative coverage curve: share of KUs covered against the
   number of templates built, in frequency order.
6. **Stop rule.** Stop adding templates when the next one adds less than 2 points of coverage. The rest goes to
   the fallback ladder.
7. **Track real usage.** Re-run the study as templates are built, using the share of lines that actually render
   on rung 1, not just the KU classification.

## Phases

| Phase | Work | Done when |
|---|---|---|
| 0. Coverage study | Course set, KU extraction, classifier, frequency table | Ranked family list; classifier ≥ 90% on the hand-checked sample |
| 1. Primitives + spec | `primitives.py`, `spec` on `Beat`/`DialogueBeat`, registry, validator, spec renderer, fallback to codegen per line | A hand-written spec renders inside both frames, with a render test |
| 2. Three pilots | `array_bars`, `linear_map_2d`, `equation_steps` | Bisection and eigenvectors L2 re-made from specs |
| 3. Pilot comparison | Same KUs, template pipeline against today's pipeline | See "Evaluation"; go/no-go for phase 4 |
| 4. Expansion | Templates in coverage order, about 1 day each, with a render test each | Coverage curve reaches the stop rule |
| 5. Selection + prompt | Template-selection step; writer prompt shows only the picked templates | Writer prompt stays ≤ its current length |

Phases 0 and 1 can run in parallel. Do phase 4 only if phase 3 shows a clear gain.

## Evaluation (phase 3, and again after phase 4)

Run on the same KUs and levels, both pipelines, low quality, with three runs each to see the spread:
- **Time:** wall time per video and per step.
- **Cost:** LLM cost per video.
- **Layout:** layout issues from `layout_audit` and the visual critic.
- **Quality:** the semantic critic's scores (the visual-alignment score in particular).
- **Coverage:** share of lines rendered from a spec (rung 1).
- **Correctness:** hand check of whether each visual matches the maths, on a sample of lines.

Expected, to be confirmed:
- total time about 1.5 min instead of 3.5–5 min;
- cost about half of today's;
- fewer layout issues, with alignment scores no worse.

## Risks

- **Effort.** 35–45 templates at roughly a day each, render test included, is several weeks. Mitigated by the
  pilot go/no-go and the stop rule.
- **Rigidity.** The writer has to fit its lines to what templates can show. Watch the critic's visual-alignment
  score, and keep the `visual` sentence so the fallback can draw anything.
- **Prompt growth.** Handled by the selection step (phase 5).
- **Upkeep.** Every template gets a render test (`SYLLABYTE_RENDER_TESTS=1`, like `tests/test_plugins.py`), so a
  Manim or `manim_dsa` upgrade can't quietly break one.
- **Caching.** Template code changes what a video looks like, so bump `PIPELINE_VERSION` when a template's
  drawing changes, and only then.

## Deviation from the proposal (state it in the report)

The proposal's Component 4 has the LLM write Manim code, with a repair ladder. Here the LLM chooses tested
templates and fills in their data, and generated code becomes a fallback. The visuals are still made per KU and
per level by the LLM; what changes is how much code it writes. Report the phase 3 comparison and the coverage
curve as the evidence for the change.

## Phase 0 result (2026-11-04)

**Course set.** 207 KUs from 12 CS and maths courses:
- the four extracted before: 6.0001, 18.S096, an advanced AI/ML course, computational social science;
- eight added for the study: 6.006, 6.0002, 18.01, 6.042J, 18.03, 18.02, 18.650, and an ML course.
Each OCW course is one mid-course lecture, picked by position, not by how drawable it looked. Sources and
licences are in `data/courses/*/SOURCE.txt`.

**Classifier check.** 46/50 agree (`runs/visual-coverage/hand-check.md`).

**Coverage** (`runs/visual-coverage/coverage.md`):
- The four templates built so far are the main picture for 22% of KUs, and cover 15% fully (with everything
  drawn beside it).
- No family fits about 10-12%.

**Revised build order**, by how often each family is the main picture:

| Order | Family | Share |
|---|---|---|
| 1 | `function_plot` | 11% |
| 2 | `flowchart` | 6% |
| 3 | `bar_meter` | 6% |
| 4 | `graph` | 6% |
| 5 | `probability` | 5% |
| 6 | `number_line` | 4% |
| 7 | `stats_plots` | 4% |
| 8 | `matrix_ops` | 3% |
| 9 | `ml_basics` | 2% |

With these, the main-picture share reaches about 69% (57% fully covered). After that, each family adds under
2 points, which is the stop rule. So the realistic target is about 12-13 templates covering about 70% of main
pictures, not 35-45. The rest goes to the fallback ladder.

## Open questions

- Should monologue videos get specs too? They share the pipeline, so probably yes, after the dialogue pilot.
- Selection step: an LLM call or an embedding lookup? Decide from the classifier's accuracy in phase 0.
- High quality (1080 px) renders: test each template at both qualities, or only at release?
