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

### Every change of state is said by its line (2026-11-07)

After the checks above, the critic's state complaints were mostly the picture changing on a line that says nothing of
it: bisection's 15 turning green during "a smaller list, plus simple work", `restore()` putting the pointers back to
the start during a recap, a selection step under "at the i'th step the first i are sorted". Lines that state the
state outright ("three checks", "mid is seven", "two cells left") are rare (14, 5 and 1 lines in 59 scripts), so
checking those claims would catch little; checking the changes catches what the critic saw.

| | Now |
|---|---|
| A call that changes a list's, a merge's or a search's state (a sort, merge or search step, found, scan, grey_out, restore, swap, set_value, split) on a line that names no value or node of the change and no word for it | problem `unsaid_change` for the fix call (lines final: move the step to the line that says it) |
| Left after the fix call | kept and logged, not dropped: dropping a step would change every state after it |
| Worked examples | three lines tripped it (a found, an insertion step, a recap running another step) and were rewritten |

Over the 59 finished scripts: 55 changes in 15 videos (most in course-test-1, before the picture plan); in the 17
videos since, 8 in 4 videos, each one the critic had also marked down.

### The picture first, then the lines; worked examples traced by code (2026-11-07)

Across five runs of the bisection and selection-sort videos (`runs/course-test-1` .. `runs/lines-fix-1`) each fix
did what it targeted, but visual alignment stayed at 3-5: the lines were matched to the picture, then the fix call
changed the picture after them, and the writer's own plan of the algorithm's steps was incoherent (a search
restarted, a target changed half way, a hand-made swap inside a computed sort).

| | Before | Now |
|---|---|---|
| Order | storyboard, match lines, voices start, then code fixes and the fix call change the picture | storyboard, code fixes and the fix call (`settle_picture`), match lines to that picture, voices start, nothing changes either (`with_pictures`) |
| A KU on linear search, bisection, a bubble, selection or insertion sort, merge sort or a merge | the writer chose every step call | one short call picks the example (`picture_plan.plan_example`, cached), code computes every step (`visuals/trace.py`), the writer is shown them as numbered sentences and shows them with `name.next_step()` |
| A step call of the writer's own on the example, or a next_step past the last step | rendered | brought onto the trace and reported; a first draft with any is written again |
| The fix call | could run, restart or rewind the example | told not to; code puts the example's steps back as they were (`trace.keep_steps`) |
| Measure | the critic only | also `lines vs picture: N mismatches` logged per video (`unshown_number`, `wrong_front`, `unsaid_change`) |

The mismatch count is weak on its own: the state-fix-1 bisection video's lines named the wrong middles ("nine",
"thirteen") and it counted 0, since 9 and 13 are on screen. It catches numbers and changes, not wrong claims about
values that are shown.

Measured on the same two KUs (L2), one video each, so within the critic's noise for anything under about 2 points:

| Run | Bisection: all four scores (VA last) | Selection sort | Mismatches (bisection, selection) | Cost |
|---|---|---|---|---|
| `runs/lines-fix-1` (before) | 4, 4, 5, 3 | 5, 4, 6, 4 | 2, 0 | |
| `runs/trace-fix-1` (both steps, fix call unguarded) | 4, 5, 5, 3 | 6, 6, 7, 4 | 4, 0 | $0.22 |
| `runs/trace-fix-2` (fix call kept off the steps) | 6, 6, 6, 5 | 5, 5, 5, 4 | 1, 0 | $0.21 |

In trace-fix-1 the writer's bisection followed the trace, then the fix call (asked to make text-only beats "take a
step") ran two steps of its own in the objective and restarted the search twice, and the line call rewrote right
lines to fit; hence `keep_steps`. In trace-fix-2 every bisection line names the middle the picture compares (21,
then 35, then 42): the first of the six runs to do so, and its first visual alignment above 4. Selection sort's
steps were right in both; what the critic marks down there is the writer's own highlights (an unsorted 5, 2, 8 turned
green under the objective, twice; the predict line highlighting its answer; a colour outside the key) and a line
that corrects itself ("the last four... I mean the last three"). Those are the next thing to check in code: green is
the template's colour for sorted and found, so a highlight may not paint it on cells that aren't.

### Highlights that say what they show; lines that say it once (2026-11-07, branch `highlights-and-lines`)

With the steps traced, what the critic still marked down in selection sort was the writer's own highlights and two
muddled lines. Code rules now run on every list before and after the fix call (`visuals/highlights.py`):

| Rule | Over the 66 earlier scripts |
|---|---|
| GREEN only on cells the steps sorted or found (`specs.green_cells`), else dropped; a list changed by hand with swap or set_value is left alone | 14 times in 8 videos (12 in course-test-1, before computed sorts; the other 3: an objective painting an unsorted 5, 2, 8 green) |
| A question or predict line can't highlight the cell its answer step (in this segment or a later one) lands on | 7 in 6 |
| A highlight of one or two cells in a colour outside the key takes the colour of the one key term its line names (never a false green) | 7 in 6 |
| A ghost outside the wrong-idea line becomes a highlight of the same cells | 4 in 4 |
| A line that corrects itself ("... wait, I mean ...") is marked for the line call, which must rewrite it; a rewrite that still does is refused | 2 in 2 |

The writer is also told: green is sorted or found, no colours outside the key, a question highlights the candidates
and never the answer, one algorithm step per line, no self-corrections. Lines showing two steps are logged.

`runs/highlight-fix-1` (same two KUs and examples, $0.21): selection sort 5, 5, 5, 4 -> 6, 6, 7, 4: no false green,
the predict line lights the candidates (8, 5, 9, 3) instead of its answer, no self-correction, one step per line;
visual alignment unchanged, the critic now naming a hook question highlighting the minimum (caught since by the
rule's look into later segments), a still objective (a recolour to green then dropped, fixed since), the pointer
"i" left under the last cell, and an unexplained comparisons counter. Bisection unchanged at 6, 6, 6, 5: its
complaints are a predict line naming the middle 35 while the check is held for the next line, the objective greying
the left half before any comparison, and lo and mid drawn on the same cell at the end.

### General-purpose templates (2026-11-07, branch `general-templates`)

Students upload any CS or Math course, so templates are built by picture shape, not by topic, in the order the
coverage study (`runs/visual-coverage`, 207 KUs, 12 courses) needs them. Each keeps the template contract: checked
calls, sentences computed from the calls, computed steps where there is something to compute, and an example that
renders in both frames with no layout findings.

| Template | Draws (families) | Computed |
|---|---|---|
| Graph, extended: boxes with words (`labels`), edge labels, `tree` and `flow` layouts, loops, curved edges round nodes | flowchart, call_tree, tree, state_machine, linked_list | `walk` along edges; `feed` a symbol (a state machine run); DFS/BFS as before |
| BarChart | bar_meter, probability, series | total, running totals, shares (`normalize`), mean, expected value, comparisons |
| NumberLine | number_line, series | a sequence's terms from its formula; how many lie within eps of a limit |
| Table | dp_table, code_trace, bits_logic, counting | truth tables, Pascal's triangle, grid paths, Fibonacci, filled in order with arrows from the cells each value came from |
| FunctionPlot, extended: `polar`, `parametric`, `dot_t`, named points, `equal_scale` | polar_parametric, complex_plane | points on the curve at a given t |

The portrait frame is 3.9 units wide, so the specs refuse what wouldn't read: at most 3 boxes side by side, two
lines of words per box, 4 levels of boxes, 8 bars (labels shortened as bars are added), 7 table columns.

Coverage of the study's KUs (main picture): drawn with a diagram template 69 (33%) -> 137 (66%); no template 77
(37%) -> 9 (4%: sets 2, 3D vectors 4, geometry 3); formulas only 34 (16%) and metaphors 24 (12%) unchanged.
"Drawn" means a template exists for the family; how well the writer uses each in real videos is still to test.

First videos (`runs/general-1`, one per template, L2, $0.87 for six): the picture plan picked the intended template
every time and the writer used it.

| KU | Template | Scores (coherence, accuracy, appropriateness, visual) | What held the picture back |
|---|---|---|---|
| Euclid as a state machine | Graph (walk) + BarChart | 6, 6, 6, 4 | a walk on a missing edge (the fix call repaired it); the rule never drawn |
| MDP trajectory and dynamics | Graph (boxes) | 6, 6, 6, 5 | "4 boxes side by side" and then "action" refused: the box limits were too strict, so the boxes read "act", "env" |
| Blackjack probabilities | BarChart + EquationSteps | 4, 3, 5, 3 | 13 ranks but at most 8 bars, so "13 ranks, 8 shown"; the title ran off screen; 8 shares collided |
| Discounted return | BarChart + EquationSteps | 6, 5, 6, 4 | the writer typed the discounted rewards by hand, wrong (8, 4, 4, 4 for 8, 4, 2, 1) |
| Gridworld value function | Table | 7, 6, 6, 5 | a 4x3 corner instead of the slide's 5x5 grid: the cell limit refused "8.8" |
| Polar area element | FunctionPlot (polar) | 6, 6, 6, 3 | no way to draw the polar cell the idea is about |

Fixed since (no new videos yet): text widths estimated per letter, calibrated on measured Text widths ("-0.4" 0.63,
"ABCDEF" 1.67), in place of 0.19 per character, for boxes, bar labels and table cells, and box widths computed from
the same geometry the drawing uses; boxes round a `circle` for a loop of up to 5 steps; up to 13 bars (numbers left
off past 8, said in the sentence); bar numbers staggered when they collide; the title dropped its y label when both
don't fit; `BarChart.series` builds bars from a formula (so a discounted or geometric sequence is computed); and
`FunctionPlot.sector` shades a polar cell with its sides and area computed.

Second videos (`runs/general-2`, the four KUs the fixes touched, $0.53): visual alignment polar 3 -> 5, MDP 5 -> 6,
gridworld 5 -> 5 (now the full 5x5 grid), discounted return 4 -> 4 (now computed with `series`, 8, 4, 2, 1).

Then (2026-11-07):
- FunctionPlot labels (named points, dot_t, sector) keep clear of every word on the plot and of the other cells,
  trying eight sides and then further out; a sector drawn again with the same bounds is relabelled, not stacked
  (one cell had been drawn four times, its labels piling up, "far" landing on the near cell).
- The writer's prompt gets "Using the picture well", from the critic's picture complaints in these ten videos: plan
  the diagram from what the lines will name (the reward and next state of a loop, r and theta); label on the
  diagram what the line measures; let code compute (series, cumulative, normalize, fill_next, feed, dot_t,
  sector), never type a value code can compute; use the slide's example at its real size; start the picture where
  the lines start; draw a thing once and keep acting on it; draw the wrong idea as the wrong picture; write out a
  line that works something out.

Third videos (`runs/general-3`, all six KUs, with the prompt rules, $0.83): visual alignment mean 4.0 -> 4.5, all four
5.25 -> 5.5 against the first run (within the critic's noise). Its renders showed a drawing bug: a cell emptied and
filled again, or bars that left their numbers off, morphed a text into nothing, which stayed on screen at font size
0 (34 findings in one video). `Template.morph` now uses `become` only between mobjects with the same parts, else
fades one out and the other in (Table, BarChart, NumberLine points); the Graph marker sits outside a box's corner.
What holds the scores now is the writer's plan of the picture (a 3-box loop for a trajectory that runs on, all 13
bars lit during a question); the next step is a worked example per new template in the prompt (every Level 2 KU
sees the same linear-search example now).

### Prompt modules per picture kind (2026-11-07)

Research (Anthropic's prompting guidance; similarity-chosen examples in structured generation; prompt routing;
Code2Video's planner-coder-critic for educational video) points the same way as our runs: examples teach more
than rules when they match the task, and specialised prompts beat one general one if routing is reliable. Every
Level 2 KU was shown the same worked example (linear search on cells), so a bar-chart, table or loop storyboard
never saw its own template used well.

So the prompt keeps one shared base (dialogue rules, casual phrases, level, rubric, the KU's template cards) and
the picture plan's family picks a module (`storyboard_modules.py`): a worked Level 2 storyboard drawn with that
kind's templates, which replaces the generic example at Level 2, and a few rules for that kind ("Drawing this
kind of picture"), at every level. Separate full prompts would copy the shared parts and drift.

| Module | Families | Its example |
|---|---|---|
| boxes | graph, flowchart, call_tree, tree, state_machine, linked_list | fib(3)'s call tree: fib(1) is worked out twice |
| bars | bar_meter, probability, series | two coin flips: count the ways, normalize, expected value |
| number_line | number_line | \|x - 2\| < 3 as a distance |
| table | dp_table, code_trace, bits_logic, counting | tracing a loop's running total |
| plot | function_plot, growth_curves, stats_plots, ml_basics, polar_parametric, complex_plane | n against n squared |
| formulas | equation_steps, proof_steps, matrix_ops | why (a + b)^2 has a middle term |

Lists and merges (the generic example's own kind), linear maps and notes keep the prompt as it was. Each example
passes what the generic ones pass and more: the Level 2 plan, the dialogue checks, the call checker with nothing
for code to fix (numbers on screen, every change said, no text-only beat, no answer shown early, no false green),
and three of its segments render with no layout findings (`tests/test_storyboard_modules.py`). Writing them showed
two template layout bugs, fixed: a dot's label on a steep curve was crossed by it (plot labels now keep off every
curve, line and ghost as well as every word), and a NumberLine given a third of the frame stacked its names and
jumps into the title (it now needs half).

Measured on 12 KUs not used before (`runs/modules-base` with the prompt before modules, `runs/modules-1` with
them; $1.67 and $1.49). The live picture plan routed 10 to a module (plot 3, formulas 3, table 2, boxes 1, number
line 1; none to bars) and 2 to the generic example, which serve as controls.

| | Visual alignment | All four scores | Picture complaints per video | Layout findings |
|---|---|---|---|---|
| Module KUs (10) | 4.30 -> 4.70 (5 up, 1 down, 4 same) | 5.65 -> 5.62 | 6.7 -> 5.4 | 26 -> 19 |
| Controls (2) | 4.00 -> 4.00 | 5.25 -> 5.50 | 8.0 -> 6.5 | 11 -> 0 |

A small gain in visual alignment on the module KUs and none on the controls, but within what the critic's noise
allows (5 up and 1 down of 10 is p of about 0.2 by a sign test), and the other scores didn't move; the complaint
counts fell for the controls too. No KU passes all four at 7. Two template bugs the run showed are fixed (a box
that grew to fit two lines pushed into the title row, so box heights now come from the labels, and the marker
sits below a box's corner; a curve name too wide for the right margin was shrunk to font 13, and now goes inside
the plot beside its curve at full size). Not re-run.

### Plan, then write (2026-11-07, `storyboard_plan.py`, `SYLLABYTE_STORYBOARD=plan`)

The storyboard in two calls, as Code2Video plans before it codes: a planner (the KU, slides, beat plan without
word counts or casual phrases, drawing rules, module, template cards) writes each beat's calls and the point its
line will make, and owns the title and colour key; code settles that picture (traced steps, reveals held,
normalize, one fix call, broken calls dropped) and describes each beat's picture; a writer (dialogue rules,
casual phrases, word ranges, level) sees each beat's computed picture and the planner's point and writes only the
lines, once more if the dialogue checks reject them. Then as before: notes that echo the final line dropped (while
the lines were only points they were kept), match_lines, the voices, the visuals. One call stays the default.

Smoke test on two KUs (`runs/plan-smoke`): both render; potential outcomes 6, 6, 6, 5 (one call, modules) ->
7, 7, 6, 5; selection-sort complexity 6, 6, 7, 5 -> 6, 6, 6, 4. LLM time per video about 12 s more (planner 16 s,
writer 9 s, against 12-14 s for one call): 57 and 71 s per video against 56 and 59 s.

The 12 KUs with plan-then-write (`runs/plan-1`, $1.79, against $1.49 for one call with modules), means over all 12:

| | Baseline (one call) | + modules (one call) | + plan, then write |
|---|---|---|---|
| Pedagogical coherence | 5.83 | 5.67 | 6.25 (6 up, 1 down against modules) |
| Conceptual accuracy | 6.17 | 6.08 | 5.92 (3 up, 4 down) |
| Learner appropriateness | 6.08 | 6.08 | 6.00 |
| Visual alignment | 4.25 | 4.58 | 4.83 (5 up, 2 down) |
| Seconds per video | | 61.6 | 64.6 |

A steady small rise in visual alignment over the three runs and a rise in coherence with the split, but each step
is within the critic's noise (6 up and 1 down is p of about 0.13 by a sign test), the critic is the same model as
the writer, and no video passes all four at 7. Cost about 20% more, 3 s more per video.

### Data structure and algorithm templates (2026-11-07)

From the visualisation research (Hundhausen, Douglas and Stasko's meta-study of 24 experiments; Naps et al.'s
engagement taxonomy: how learners engage matters more than what the picture shows; VisuAlgo's catalogue; heap
tools that show the tree and its array together), each template keeps four rules: every operation is computed
(shared by the checker and the drawing), the current operation and named pointers are shown as code names them,
the invariant is visible (the reversed part, the sorted side, the settled nodes, a heap's order), and each result
is a reveal, so a predict line can ask for it first (the closest a video gets to engagement).

| Concept (CS2023 AL, VisuAlgo) | Template, computed actions |
|---|---|
| Linked lists, singly and doubly | **LinkedList**: insert, delete, find_step, in-place reverse_step (prev/curr, links flip), named pointers, advance |
| Stacks, queues, deques, recursion's call stack | **StackQueue**: push/pop/peek, enqueue/dequeue, both ends of a deque, call frames returning values |
| Hashing, chaining, linear probing | **HashTable**: h(k) = k mod m, collisions, probe sequences, find with its checks, delete, load factor |
| BSTs, binary heaps, traversals | **BinaryTree**: BST insert/search/delete (leaf, one child, two children via the in-order successor); min/max heap push, pop, heapify with the array under the tree; inorder, preorder, postorder, level order |
| Searching, elementary sorts, merge sort | ArrayBars (scan, bisection, bubble/selection/insertion), MergeSort (as before) |
| Quicksort | ArrayBars **partition_step** (Lomuto: pivot, small and large sides, the pivot placed green) |
| Graph traversal | Graph dfs_step, bfs_level (as before) |
| Shortest paths, spanning trees, DAG order | Graph **dijkstra_step** (distances as badges), **prim_step**, **kruskal_step** (union-find; a skipped edge flashes red), **topo_step** (Kahn; a cycle is reported) |
| Recursion trees, flowcharts, state machines | Graph (boxes, labels, walk, feed), as before |
| Dynamic programming | Table rules: Fibonacci, grid paths, Pascal, truth tables, and now **lcs**, **edit_distance**, **knapsack**, **coin_change**, each cell filled from the cells it uses (far ones outlined) with why |
| Growth of running time | FunctionPlot (as before) |

Tests: `tests/test_dsa_templates.py` checks each computation against known answers (Dijkstra's distances, Prim and
Kruskal's same tree, edit distance kitten -> sitin = 3, knapsack 35, a valid heap after heapify, BST delete's three
cases); every example renders in both frames with no layout findings. The "structures" module (rules only, no
worked example yet) gives linked lists, stacks and queues, hash tables and trees their drawing rules.

Not built yet (in rough order of how often courses teach them): AVL or red-black rotations, union-find as a forest,
tries, Bellman-Ford and Floyd-Warshall, sliding window and two pointers as computed steps, counting and radix sort,
heapsort as one sequence, backtracking (N-queens), string matching (KMP), segment and Fenwick trees, B-trees,
network flow and matching, suffix structures. Nothing here is tested in real videos yet.

Tested on a real data structures course: MIT OCW 6.006 (Spring 2020) lecture notes 2 (data structures), 4
(hashing), 6 (binary trees), 8 (heaps), 13 (Dijkstra), CC BY-NC-SA 4.0 (`data/courses/ocw-6006-ds`, 55 KUs). Seven
KUs, one per new template; the picture plan routed every one to the intended template, and the writer used the
computed actions (traverse_step 8 times, dijkstra_step 5, search 5, and insert, find, push, pop, enqueue).

| | `runs/dsa-1` | `runs/dsa-2` (after the fixes) |
|---|---|---|
| Visual alignment, mean of 7 | 4.29 | 4.57 |
| All four scores | 5.54 | 5.75 |
| Layout findings | 140 | 20, then 0 when its segments are re-rendered with the later fixes |

Real use showed what the examples hadn't: a heap sized for 12 nodes left two-digit values bursting their circles (98
findings), stack cells in half a frame shorter than a line of text, edge weights on the nodes of a small graph, a
long traversal note off screen, shares of an action's steps adding past 1 (a beat overran), and, from the critic:
a hash table that could only hash k mod m (now (a k + b) mod m, so a bad hash piles every key into one chain), a
linked-list insert that jumped to its result (now the new node points on, then the one before it points to it,
then the row makes room; delete bypasses first), a traversal that jumped between nodes (a cursor now walks the
recursion's route), and Dijkstra's relaxed edges never shown (now lit for that step).

Worked examples for the data structures (2026-11-07): five more modules, each a Level 2 storyboard on an idea that
isn't one of the test KUs, passing every check (dialogue, call checker with nothing to fix, reveals held, no still
point lines, highlight rules) and rendering three segments with no layout findings: linked list (reversing in
place), stack (balanced brackets), hash table (linear probing collisions), tree (BST insert and a missing key),
graph algorithms (Dijkstra with a detour; graph moves from the boxes module). The check that every change is said
by its line now covers the new structures' and algorithms' actions.

On the same seven 6.006 KUs (`runs/dsa-2` -> `runs/dsa-3`, $0.80): visual alignment 4.57 -> 4.14 (3 down a point, 4
the same), all four 5.75 -> 5.54, layout findings 20 -> 0 (the earlier fixes), picture complaints 7.0 -> 7.1 per
video. No gain. The complaints say why: the writer narrates its own run of the slide's example (Dijkstra's lines
say "b drops from eleven to ten" while the computed picture settles a at 7 and updates b to 9), and an operation
the lines narrate in steps runs at once (a heap push plays all its swaps while the lines take one swap each). That
is the failure bisection had before code traced its steps, and the fix is the same: trace-first for these
algorithms (code computes the example's steps, the writer narrates them with next_step), with heap and BST
operations available one comparison or swap per call.

With plan, then write on the same seven KUs (`runs/dsa-plan`, $0.88): visual alignment 4.14 -> 5.00 against one
call with the same prompt (5 up, 2 the same, none down), all four 5.54 -> 6.14; Dijkstra 6, 5, 6, 4 -> 7, 8, 7, 6
(its lines now say the computed distances), linked list -> 7, 8, 7, 5. With the 12-KU comparison it is level or
better on 19 KUs, so it is now the default (`SYLLABYTE_STORYBOARD=one_call` keeps the one call). Still no video
passes all four at 7; next is trace-first for the data-structure algorithms, with heap and BST operations one swap
or comparison per call.
