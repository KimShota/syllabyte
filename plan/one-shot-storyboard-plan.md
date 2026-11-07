# One-shot storyboards: the script and its pictures right the first time (2026-11-05)

Goal: each video's script and visuals come out of one LLM call, with no repair loop, in under a minute.

## Why the template pilots needed repairs

Counted from every template run so far (`runs/template-videos-2` to `-8`, about 12 videos):

| Where | What | Count |
|---|---|---|
| Writer, rejected and rewritten | slang count | 8 |
| | word count | 2 |
| | the explainer speaks more than 3 beats in a row | 2 |
| Draw calls, sent to a fix call (33 calls; 7 segments fell back to LLM code) | note repeats the line | 19 |
| | object not created in this segment | 9 |
| | text too long | 9 |
| | area too small | 8 |
| | too many calls in a beat | 6 |
| | name reused, zero vector, off the grid, overlap, hidden guess | ~14 |
| Critic issues (169 in all, grouped by keyword, so rough) | text on screen instead of a picture | 58 |
| | who speaks / the tutoring steps | 52 |
| | picture doesn't match the words | 34 |
| | slang hard for non-native speakers | 26 |

Three causes:

1. **The model was asked to count and track what code can guarantee:** word totals, slang counts, speaker runs,
   text lengths, layout areas, object names across segments.
2. **The rules contradicted each other, and the writer never saw them.** The format required at least 2 slang
   phrases while the critic marked slang down. The critic counted a formula as "text", and capped any beat
   that was only text at 4. Neither rule was in the writer's prompt.
3. **The lines were written first and the pictures fitted afterwards,** so pictures fell back on notes and
   didn't match the words.

## What changed

| | Before | Now |
|---|---|---|
| Beat plan | the writer invents it; `validate_dialogue` rejects it | code builds it (`storyboard.skeleton`): speaker, step, misconception and predict positions, word range per line, which lines carry a casual phrase; it passes `validate_dialogue` by construction |
| Script + pictures | writer call, then 5 parallel draw calls, then fix calls | one call (`storyboard.write_storyboard`): every beat's picture, then its line. The plan is the schema: one required field per beat, named for speaker and step (`b3_explainer_feedback`) |
| Layout | the writer picks areas | code (`normalize.lay_out`): one area per object for its life, diagrams first |
| Between segments | every segment starts empty | the picture carries over: the renderer replays the earlier segments' calls instantly before beat 1 (`SpecRunner.setup`); creating a name again replaces it |
| Mechanical mistakes | an LLM fix call | code (`normalize.normalize_script`): drop a note that is too long or repeats the line, a text-only beat's calls, a zero vector, a hidden guess, a call on a missing object; widen a grid a vector falls off |
| What code can't fix | another fix call per segment, then codegen | one fix call for the whole script, then code drops whatever is still rejected; no codegen fallback |
| Slang | rewrite until the count is right | code puts a phrase in each planned slot, removes any from objective/check lines, and keeps the total under the cap (`fix_slang`) |
| Rubric | critic only | one rubric (`prompts.SHARED_RUBRIC`) in both the writer's and the critic's prompt. Approved slang in its slots isn't marked down; a formula being written, rewritten, highlighted or boxed counts as a picture |
| Example | none | one hand-checked Level 2 storyboard (`storyboard_example.py`, linear search); a test keeps it passing every checker with nothing to fix |
| Critic | up to two rounds, rewrites, on the waiting path | one critique, beside the voices and the render; recorded, nothing rewritten |
| Effort | low everywhere | medium for the storyboard call (`STORYBOARD_EFFORT`), low for the rest |

## Deviation from the proposal (state it in the report)

- The proposal's Component 3 has the script writer plan the script freely, with a critic loop that rewrites it.
  Here code fixes the tutoring-frame plan, and the critic scores once without rewriting.
- Component 4 has the LLM write Manim code with a repair ladder. Here the LLM chooses template calls in the same
  call as the lines, and code fixes them.
- The critic's rubric changed in two places: approved slang, and formulas counting as pictures.
- **Evidence for the report:** the counts above, and the time and score comparison from `runs/storyboard-*`.

## Open

- Measure whether medium effort on the storyboard call is worth the time over low.
- High-quality (1080 px) renders of carried pictures: the instant replay is only render-tested at low quality.

## Results (2026-11-05, Sonnet 5.5, eigenvectors and bisection at L2)

| Run | Eigenvectors | Bisection | LLM calls | Cost per video | Critic (coherence, accuracy, appropriateness, visual) |
|---|---|---|---|---|---|
| Before: per-segment draws, critic rounds (`runs/template-videos-8`) | 83 s | – | 18 | $0.38 | 6, 4, 6, 3 |
| Storyboard, first run (`runs/storyboard-1`) | 58 s | 69 s | 3-4 | $0.12-0.15 | 6, 6, 6, 6 / 6, 6, 6, 4 |
| Storyboard, tighter word budgets (`runs/storyboard-2`) | 48 s | 37 s | 3-4 | $0.10-0.13 | 6, 6, 6, 5 / 6, 7, 6, 5 |

- Every segment was drawn from templates. No segment fell back to LLM code.
- The 48 s eigenvectors video includes one rewrite of about 13 s, for a script at 251 words. A script over the
  limit is now kept and logged, not rewritten (see the course test below); too short is still rewritten.
- **Not passing yet: the critic scores.** The remaining issues are about content, not bookkeeping:
  - a picture showing the answer before its line (or before the predict line);
  - shallow questions;
  - claims the slides don't support;
  - eigen-lines and values appearing before the narration explains them.
- Next levers: a worked example per level, effort high on the storyboard call (measure the time), and an
  Opus storyboard call if quality has to beat speed.

### Worked examples for every level (2026-11-05)

- **The three examples:** Level 1 is a matrix times a vector (a grid with a formula); Level 2 is linear search
  (cells); Level 3 is insertion sort on already-sorted input (bars). A test holds each to its plan, its word
  ranges and the checkers, and render tests draw a carried segment from each.
- **The examples were part of why writers ran long.** All three broke their own word ranges until rewritten. The
  ranges now sum to about 225 words, plus 2 for each line that carries a casual phrase.
- **Template bugs the examples found:** `ArrayBars.ghost` ran through the note above full-height bars, and
  `LinearMap2D.show_matrix`'s backing box failed the contrast check.

| Run (`runs/storyboard-3`) | Time | Storyboard calls | Critic |
|---|---|---|---|
| Eigenvectors, Level 1 | 47 s | 1 | 6, 6, 6, 4 |
| Bisection, Level 3 | 55 s | 2 (first at 265 words) | 6, 6, 7, 6 |

### Opus for the storyboard call (tried 2026-11-05, set aside for now)

| Storyboard call | Videos (eigenvectors / bisection, L2) | Call time | Cost per video | Critic (lowest) |
|---|---|---|---|---|
| Sonnet 5.5, medium (`runs/storyboard-2`) | 48 s / 37 s | 12-19 s | $0.10-0.13 | 5 / 5 |
| Opus 5.5, medium (`runs/storyboard-opus-1`) | 72 s / 81 s | 39-43 s | $0.17-0.18 | 5 / 5 |
| Opus 5.5, low (`runs/storyboard-opus-2`) | 45 s / 56 s | 16-17 s | $0.12-0.13 | 5 / 3 |

- Opus at medium broke the under-a-minute goal. At low it was about as fast as Sonnet at medium.
- No setting scored better in two videos each, and the critic's noise is unmeasured.
- Opus kept to the word budget in all four of its videos.
- Back on Sonnet at medium (`STORYBOARD_MODEL`, `STORYBOARD_EFFORT`).
- The Opus runs also exposed a bug: removing a casual phrase from a build line could break the sentence. Code now
  removes phrases only from objective and check lines, and only when the sentence stays whole.

## Course test (2026-11-05, `runs/course-test-1`, 48 KUs at Level 2)

All 38 KUs of the CS and Math decks, plus 10 from the coverage courses whose topics have no template (DFS,
tangent line, substitution, sample means, resonance, Euclid, XOR, double integral, KL divergence, MLE).

| | Result |
|---|---|
| Made | 42 of 48. Failed: 3 API connection drops, 3 scripts still over the word limit after the rewrite |
| Time | median 43 s (29-91 s); 37 of 42 under a minute |
| Cost | $5.06 in all; median $0.11 a video ($0.07-$0.41) |
| Storyboard calls | 1 for 24 videos, 2 for 18 (every rewrite was for length); a fix call for 13 |
| Video length | median 99 s (85-121 s) |
| Critic | none passed (all four at 7+); visual alignment median 4, 12 videos at 2-3; the off-template KUs scored about the same as the rest |

- **Word limit:** 24 first drafts ran 264-319 words. A storyboard over the limit is now kept and logged, not
  rewritten (`storyboard._over_limit`); too short is still rewritten.
- **Render bug:** `EquationSteps.highlight(part="b")` passed the checker but found no piece at render. Because the
  picture carries over, every later segment replayed the call and crashed, so all 5 segments of the XOR video fell
  back to generated code ($0.37). A LaTeX error did the same to segments of the SVD statement ($0.41).
- **Fixed after the test** (no LLM spend; both videos' segments now render from their templates):
  - a piece inside an isolated piece: the newest wins (`EquationSteps._part`), else the whole line is underlined;
  - a doubled backslash before a letter (`\\Sigma`) is read as one (`calls._undouble`);
  - an action that fails at render is skipped and logged, not fatal (`SpecRunner._run`), so a carried call can't
    send every later segment to code; a create that fails still does;
  - a call that fails on the network is made again after 10, 30, 60 and 120 s (`llm.OUTAGE_WAITS`), including a
    stream cut off midway;
  - `TEMPLATES_VERSION` 5, so cached videos drawn before the fixes are made again.
- **Still open:** the visual-alignment scores.

## Pictures that fit (2026-11-05)

What the critic said about the course test's pictures (299 picture issues in 42 videos, grouped by keyword):

| Issue | Issues | Videos |
|---|---|---|
| the picture shows the answer before or during the line that asks | 51 | 31 |
| something the line talks about is never drawn | 50 | 29 |
| the picture's state is wrong (a sort's row, a merge) | 42 | 25 |
| text instead of a picture | 28 | 23 |
| a highlight the line never mentions | 27 | 21 |

The cause is the same as before the storyboards: the model was left to do what code can guarantee.

1. **It picked the template.** It saw every template and, when none fitted, borrowed one: DFS as a row of cells, XOR's
   points as vectors on a linear-map grid, "recursive thinking" as a rotation matrix. It never used its way out
   (sketches). Videos whose picture had a template scored 4.5 on visual alignment on average; those without, 3.8.
2. **It ran the algorithms by hand,** with swap and set_value, and lost track: selection sort swapped the wrong cells;
   bubble sort called a pass done with 5 before 2. Bisection was right every time, because code computes it.
3. **Nothing kept a question line from showing its answer.**
4. **The worked examples taught some of it:** the Level 2 objective lit up two cells the line never named, and the
   Level 3 example ran insertion sort with compare and swap.

What changed:

| | Before | Now |
|---|---|---|
| Which templates | the writer picks from all of them | code: one classifier call per KU (`picture_plan.plan_picture`, the coverage study's classifier, cached in `runs/picture-plans.json`) picks the family; the storyboard sees only the templates that draw it, plus EquationSteps and Note (`families.templates_for`). Another template is a problem for the fix call, then dropped; the main template never drawn is a problem too |
| No template for the family | the writer borrows one | the prompt says so and gives formulas and notes only; the gap is logged |
| Sorts, merges, searches | swap and set_value by hand | computed steps: `bubble_step`, `bubble_pass`, `selection_step`, `insertion_step` (ArrayBars), `split`/`merge_step`/`merge`/`merge_level` (MergeSort), `dfs_step`/`bfs_level` (Graph), with the checker and the drawing running the same functions |
| Plots | none | FunctionPlot: curves from formulas (parsed, never run), dots, tangents and slopes, areas, maxima, a sliding dot, data points, lines |
| A result during a question or predict line | allowed | code moves it to the next line that answers (`normalize.hold_reveals`, from `ActionSpec.reveals`) |
| A highlight the line doesn't name | allowed | dropped by code (ArrayBars, MergeSort) |
| Worked examples | the habits above | rewritten: the objective's highlight matches its words; Level 3 uses insertion_step |

New templates, by the families of the course test's KUs that had none: MergeSort (6 of the CS deck's 23 KUs are
merge sort), FunctionPlot (function_plot, growth_curves, stats_plots and ml_basics: 15% of the coverage study's
KUs), Graph (graph, 6%). With them, the families drawn by a template are the main picture of 51% of the coverage
study's 207 KUs, up from 22% (merge sort KUs were classified before the merge_sort family existed, so slightly
more).

Measured on 12 of the 48 KUs (`runs/course-test-2`, 2026-11-06, $1.20): mostly the worst scorers and those that had
borrowed a template, re-run once each. Visual alignment rose from a mean of 3.25 to 4.25; the three that had borrowed
a template rose most (DFS 2 to 5, merge sort 2 to 5, growth classes 2 to 4). None passed (every score at least 7).
The two "controls" got new pictures too (sample means is now a FunctionPlot, Euclid formulas only), so this run
can't separate the gain from the critic's noise (about a point between runs).

### Lines that match the picture (2026-11-06)

The merge-step video in that run drew 1, 5, 6, 8, 9 and 2, 3, 4, 7 while every line said the slide's numbers ("twelve
beats seventeen"): the slide's ten two-digit numbers don't fit MergeSort (rendered: they overlap in the vertical
frame, so the cap stays), the fix call swapped in smaller ones, and the lines were already final. And a merge_step
that set up a question ("the result holds one; now, five or two?") was moved by hold_reveals to the answer, so the
picture ran a step behind the lines from there on.

| | Now |
|---|---|
| A line names a number that no call of its segment writes, while a list or merge is on screen | problem `unshown_number` (counts like "four checks", numbers up to the list's length, arithmetic lines and years pass) |
| A line compares two of a merge's values that aren't the fronts as it starts or ends, nor a pair the segment compared | problem `wrong_front` |
| Either, or a rejected creation call, in the first draft | the storyboard is written once more with them (before the lines are final); a redo that breaks the dialogue keeps the first draft |
| Left over after that | the fix call, told the lines are final |
| hold_reveals | doesn't make a move that adds a `wrong_front` line |

Over the 54 finished scripts of both runs, the checks flag 5 lines, all real (both merge-step videos).

### Static pictures (2026-11-06)

The critic's "the picture doesn't change while the line makes a new point" (32 of 615 issues, in 25 of 55 videos).
Of the 100 drawn beats with no picture change, about 57 were emptied by code: a note-only beat was cleared as
text_only. The complaints fell on objective, explaining and recap lines; a still question or predict line is fine
(the critic says so itself).

| | Now |
|---|---|
| A point-making line (build, feedback, objective, check, the right answer) draws nothing | code highlights the list cells the line names (`normalize.fill_still`), else problem `still` for the fix call |
| A point-making line draws only a note | kept for the fix call (`keep_text`) instead of cleared; cleared only if still text-only after it |
| A question, predict or wrong-idea line | may keep the picture, as before |
| Prompt | `[]` only for a question, a predict line or the wrong idea; the Level 3 example's objective now highlights the value it names |

Measured on 4 KUs (`runs/still-fix-1`, $0.37): still point-making lines 6 to 0, the critic's still-picture
complaints 6 to 3 (two of them on question or predict lines), visual alignment unchanged but for selection sort (4 to
5). The fix call mostly adds highlights, which are honest but weak; a `replay()` for recap lines is the next step if
this matters. What holds the scores down now is the line and the picture disagreeing about state (bisection: found
shown early, pointers reset while the line says "one cell left", the counter at 2 while the line says three checks).
