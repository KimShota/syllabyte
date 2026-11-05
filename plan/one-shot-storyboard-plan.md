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
