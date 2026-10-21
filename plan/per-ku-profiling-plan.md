# Per-KU learner profiling with CAT: plan

Branch: `per-ku-profiling` (from `main` at 2d391ce). Status: **decisions settled (2026-10-12); built (2026-10-13), commits 1–8 done.**
The Figma redesign waits on this; its plan is `plan/ui-redesign-figma-plan.md` on branch `ui-improvement`.

## Why

The capstone proposal is the source of truth. §3.2 says a Computerized Adaptive Test with 2PL IRT yields "a reliable
estimate of prior knowledge for each Knowledge Unit in fewer questions than a fixed-form test", and the profile
"assigns each KU a readiness level (novice, developing, proficient)" mapped to Bloom tiers (novice →
Remember/Understand, developing → Apply/Analyze, proficient → Evaluate/Create). The October timeline lists "per-KU
item banks … at varying Bloom's difficulty levels", "CAT engine using the catsim library with the 2PL IRT model".

The app instead keeps one level per hand-written topic (`ui-ux-implementation-plan.md` §2 rule 1, [Q15]), sets it
from a fixed 8-question check, and changes it only at a student-approved Week 7 check-in.

## What exists today (facts, 2026-10-12)

- The dev fixtures come from **one 34-slide deck** (`runs/dev`), split into 3 invented lectures, with **4 topics
  hand-written** in `scripts/build_ui_fixtures.py` (`TOPICS`, "AUTHOR DECISIONS"). 20 KUs; 4 have a video.
- The pipeline's KU graph (`runs/<id>/kus.json`) has a **Bloom level** and **prerequisite edges** per KU; the
  fixture builder drops both.
- Items: 8 onboarding + 6 re-check (per topic, each tagged with one KU, covering 12 of 20 KUs) and 1 checkpoint,
  1 next-session and 1 prove-it item per video. Items carry an LLM `difficulty_prior`; no discrimination.
- `catsim` 0.21.0 (Python ≥ 3.10) offers `NumericalSearchEstimator` (MLE, with Dodd's heuristic for all-right /
  all-wrong patterns; **no EAP**), `MaxInfoSelector`, `RandomesqueSelector`, stratified selectors,
  `TestLengthStopper`, `MinErrorStopper`, `FixedPointInitializer`. It is not a dependency yet;
  `packages/assessment_agent` is an empty package; there is no backend (FastAPI is Phase 1).
- Generation today: ≈ $1.02 LLM cost and ≈ 8 min 20 s wall time per video (`runs/dev/report.md`,
  `runs/bench-par.log`), dominated by Manim codegen/repair rounds.

## Decisions

| # | Decision |
|---|---|
| D1 | Levels are measured by **CAT with 2PL IRT**, as the proposal says. |
| D2 | **One θ per topic**, and **a topic is a lecture** (from ingestion and the syllabus; no hand-written topics). Each KU's level comes from its own items' parameters at that θ. |
| D3 | `catsim` in `packages/assessment_agent` is the **engine of record**. A TypeScript port runs the static Phase 0 demo; a **parity test** feeds identical response sequences through both and fails on any difference in θ or chosen item. |
| D4 | **Item bank: 3 items per KU**, one per Bloom tier — basic (Remember/Understand), applied (Apply/Analyze), advanced (Evaluate/Create) — generated per course upload, one LLM call per KU plus the existing critic. A sample is hand-validated for the pilot course. Replaces the 14 per-topic onboarding/re-check items. |
| D5 | **Item parameters before calibration:** the LLM rates each **KU** once (`ku_difficulty`, −2…2, first-time learner); β = tier offset (−1 / 0 / +1) + 0.5 × that rating, so the tiers sit one logit apart and a hard KU shifts all three up (a per-item LLM score would count the tier twice and is the noisiest signal); tiers forced into increasing order; **α fixed at 1.0** (Rasch inside the 2PL machinery) until post-pilot calibration. Stated as a limitation. |
| D6 | **KU readiness (tier rule):** proficient if θ ≥ β of the KU's advanced item; developing if θ ≥ β of its applied item; else novice. Shown as Levels 3/2/1. |
| D7 | **CAT settings:** start θ = 0 (`FixedPointInitializer`); next item = most informative unseen item (`MaxInfoSelector`); θ by `NumericalSearchEstimator` (bounded) with Dodd; **fixed length** (`TestLengthStopper`). **"Not sure"** is scored as a wrong answer (changed 2026-10-21 from "toward the length but not the estimate", plan §2 rule 3); a topic answered entirely "Not sure" makes its KUs novice. Limitation: with α = 1, SE(θ) stays ≈ 1 logit after ~4 items, so an SE stopping rule would never fire at these lengths. |
| D8 | **When students are assessed:** a **Week 0 baseline** (≈ 16 items) on the first lectures' KUs and the KU graph's prerequisite roots — gives every KU a provisional level (θ pooled over all Week 0 answers for lectures not yet checked). **Before each lecture's videos**, a check of ≈ 4 items on that lecture plus ≈ 2 **review** items from earlier lectures, aimed where θ is least certain. Every sitting has a fixed length regardless of course size; lengths are config, tuned by simulation before the pilot. |
| D9 | **No going back** inside a CAT: a choice can change until Next, then it is locked; answers are reviewable afterwards. "Pick my own level" sets every KU to one level. |
| D10 | **Continuous evidence:** quick-check, next-day and prove-it answers also feed their lecture's θ. A **hinted** answer counts as the same item made easier (β − 1.0, config, recalibrated from pilot data). Confidence ratings stay for the calibration view only. |
| D11 | **When levels change:** θ re-estimates after every answer, but a KU's level changes **only at lecture boundaries** (when the next lecture's playlist is built), shown on a **"What changed and why"** card with templated reasons. **"Correct this"** works any time and is logged as the student's choice. |
| D12 | **Week 7 is removed from the app**: invite, quiz, results/changes screens, `recheck_*` config, Week 7 events and persona story. (The pilot's Week 7 *study* measurement moves to the instruments roadmap item.) |
| D13 | **Engagement adjusts delivery, never θ:** a video dropped early, skipped without passing prove-it, or replayed several times queues its KU as a refresher. Thresholds are config and go in the traceability table. |
| D14 | **Prerequisite graph orders the playlist** (prerequisites first, templated reason); it does not cap levels. |
| D15 | **Videos are made once, never remade.** A KU's video is made at the KU's level when first needed; later level changes affect only KUs not made yet; refreshers replay the original. The app records the level each video was made at and shows it when it differs ("Made at Level 1 · you're now Level 2"). |
| D16 | **Publishing levels:** each KU's level is published the moment it is set, so on-demand generation can start (roadmap item 4). |
| D17 | **Screens in this branch are minimal and functional**, in today's styling: My levels as lecture cards with KU rows (short title, level bar, tier name, templated reason, "Correct this"); onboarding result by lecture, expandable; a pre-lecture check card in the playlist; the "What changed" card. The Figma branch restyles them later. |
| D18 | **Scope:** measurement only (this document). Other proposal gaps are separate branches (roadmap below). The pilot stays one professor's course as in the proposal; students uploading their own courses is the product direction, and the engine is built to work for any uploaded course. |

## Design

### Data (fixtures and types)
- `Topic` becomes one per lecture (`id: "lecture-<n>"`, title = lecture title, `ku_ids` = that lecture's KUs).
  `build_ui_fixtures.py` derives it from the lecture split; the `TOPICS` dict is deleted.
- `KuEntry` (+ `learner.py`) gains `bloom_level` and `prerequisites: string[]` from `kus.json`.
- `Item` gains `tier: "basic" | "applied" | "advanced"`, `discrimination` (default 1.0) and keeps
  `difficulty_prior` as β. Contexts: `assessment` (Week 0 / pre-lecture / review), `checkpoint`, `next_session`,
  `prove_it`, `retention`; `onboarding` and `recheck` are retired.
- `TailoringSkeleton.evidence_topic_id` → `evidence_ku_id`.

### Engine
- Python: `packages/assessment_agent/assessment_agent/cat.py` (+ `readiness.py`): item matrix from the bank
  (a = α, b = β, c = 0, d = 1), per-lecture θ via `catsim`, selection restricted to a session's eligible items,
  hint shift, tier rule. `pytest` tests. A script writes golden response sequences and expected outputs to
  `apps/web/tests/fixtures/cat-parity.json`.
- TypeScript: `apps/web/lib/logic/cat.ts` (bounded MLE + Dodd, max-information selection, fixed-length stop) and
  `readiness.ts`. A Vitest suite replays `cat-parity.json` and must match within a tolerance of 1e-4 on θ and
  exactly on item choice.

### Profile and delivery (mock API)
- `DemoState.levels: Record<kuId, KuLevel>` (level, source model|student, suggested level, reason, evidence counts,
  made_level, history); `thetas: Record<lectureId, {theta, n_answered}>`. Store version `v: 1 → 2`; old v1 state
  is discarded (Phase 0 has no real participants).
- Week 0 CAT replaces onboarding's fixed list; pre-lecture checks appear as the first playlist card of a lecture;
  in-video/next-day/prove-it answers update θ; levels apply at lecture boundaries with the "What changed" card.
- Playlist: `gap` = the KU is novice; order = prerequisites first, then slide order; engagement refreshers (D13);
  served version = `made_level` once made (D15).
- Events: `{ type: "ku", id }` for level events; new verbs for CAT sessions (`cat_item_shown`, `cat_answered`,
  `cat_finished`), `levels_updated`; Week 7 verbs removed.
- Persona: rewritten as a student mid-course who crosses a lecture boundary with ≥ 1 level up and ≥ 1 down.

### Reasons (plan §2 rule 4: templates over stored answers, true numbers)
- "Based on your 5 answers on Lecture 2 (4 right), you're likely to handle this concept's applied questions but not
  yet its advanced ones."
- "You chose “Not sure” on all 4 questions on Lecture 1, so videos start from the basics."
- "Potential outcomes: Level 1 → 2. You answered 5 of 6 questions on it correctly since Lecture 1. Your next videos
  on it will use Level 2."

### Config (all in `CourseConfig`, all listed in the traceability table)
`cat_week0_length: 16`, `cat_prelecture_new: 4`, `cat_prelecture_review: 2`, `cat_start_theta: 0`,
`irt_default_discrimination: 1.0`, `irt_hint_beta_shift: 1.0`, Bloom-tier β offsets,
`refresher_dropoff_fraction`, `refresher_replay_count`.

## Commits (each: typecheck, unit, parity, e2e incl. axe green)
1. **Fixtures carry the KU graph** *(done)*: Bloom level and prerequisites on KUs (the `Course` model rejects an
   unknown prerequisite, a self-loop or a cycle), `discrimination` and `tier` on items; Python models, builder,
   TS types, tests. Additive only: the app behaves exactly as before. **Lectures-as-topics moved to commit 4**:
   the existing items, levels and tests are keyed to the 4 hand-written topics, so topics can only become lectures
   in the same commit that replaces those items with the per-KU bank.
2. **CAT engine (Python)** *(done)*: `catsim` added; `assessment_agent.cat` / `.readiness`; 49 pytest tests; golden
   file `apps/web/tests/fixtures/cat-parity.json` (26 simulated sessions, 140 steps) written by
   `scripts/make_cat_parity.py`. See "Engine notes" below.
3. **CAT engine (TypeScript)** *(done)*: `lib/logic/cat.ts` (engine + `readinessLevel`), a line-for-line port of scipy's
   bounded Brent search and catsim's response/information/Dodd formulas. 56 new unit tests. Parity: all 140 recorded
   steps pick the same item, with θ within 1.2e-11 and SE within 1.1e-12 of Python (tolerance 1e-6). Mutation-checked:
   reversing the tie order, taking Dodd's range from the answered items only, or ignoring the hint shift each make the
   parity test fail.
4. **Item bank** *(code done; generation awaits approval)*: `assessment_agent.bank` (tier difficulty rules, assembly,
   balancing, validation; LLM-free, tested) and `scripts/build_item_bank.py` (`--estimate` prints the cost with no API
   call; generation is cached per KU in `runs/<id>/ui_cache/bank-<ku>.json`; writes `bank.json` and `_bank-review.md`).
   Additive: `bank.json` sits beside the existing fixtures and the app does not read it yet.
   **Lectures-as-topics and retiring the 14 onboarding/re-check items moved to commit 5**, which rebuilds the flow
   that depends on them. Estimated cost of the full dev bank (20 KUs): ≈ $1.16 on claude-opus-5, ≈ $0.46 on
   claude-sonnet-5; lecture 1 alone (10 KUs) ≈ $0.57 / $0.23.
   **Generated 2026-10-13 on claude-sonnet-5** (user-approved): lecture 1 first ($0.25), reviewed, prompt tightened
   (stay inside the slides, no distractor that restates the claim, tiers need different kinds of thinking), then all
   20 KUs regenerated ($0.56; the estimate runs ~20% low on image-heavy slides). Total spent: $0.81. Review found 9 of
   60 stems with no question (mostly advanced "claim" statements), so the system prompt now allows a setup before the
   question, and `stem_problems` checks every stem and asks once more; the 8 affected KUs are still to be redone
   (`--kus … --regen`, ≈ $0.2). Hand-validation of the bank is still the user's job (plan: ≥ 2 items per topic).
5. **Per-KU profile logic** *(done; pure modules, nothing wired in yet)*: `lib/logic/lectures.ts` (a topic is a
   lecture), `kuProfile.ts` (per-lecture θ from all answers, KU levels, templated reasons, level updates),
   `assessment.ts` (Week 0 and pre-lecture plans, the next item, review aimed at the least certain lecture),
   `prereq.ts` (prerequisite ordering and notes), `engagement.ts` (drop-off and replay signals); the adaptive-assessment
   config on `CourseConfig` (Python and TS); 58 new unit tests, including simulated students on the real bank.
   Split from the wiring so the logic is reviewed on its own and HEAD stays green.
6. **Wiring + screens** *(done, one commit: the screens cannot work without the state and API, so splitting them
   would have left a red commit)*: state v2 (levels keyed by KU, `made` level, watch progress, sittings, pending level
   updates); the mock API (`getSitting`/`answerSitting`/`finishSitting`, per-KU `correctLevel`, boundary-only
   `publishLevels`, "What changed and why", `recordProgress`); lectures as topics in the fixtures, the 14
   onboarding/re-check items retired, tailoring evidence per KU; Week 7 removed (routes, API, config, persona,
   events); the scripted students rebuilt through the real API with a backdated clock; `AdaptiveQuiz` (no going back),
   `/check`, start result and My levels by lecture, the check and level-update cards on the playlist. 186 unit tests
   and all e2e (incl. axe) pass.
7. ~~Screens~~ (folded into 6).
8. **Docs** *(done)*: `ui-ux-implementation-plan.md` (rule 1, rule 2, §3.1, §3.1b, §3.3, §3.8, §3.9–3.10 removed, §4.1,
   §4.3, §4.4 removed, §4.6, §5, §6.1 endpoints, traceability), `apps/web/README.md`.

## Needs the advisor's sign-off (proposed changes to the proposal; OSF pre-registration not filed yet)
- **H3 and the profile-shift heatmap:** from "learning gains after the automatic Week 7 reassessment vs a static
  initial profile" to "continuous per-lecture adaptation vs a static Week 0 profile", with a per-KU readiness
  trajectory across lectures.
- **Week 7** stays only as the study's midterm measurement (retention quiz, NASA-TLX, SUS, Likert, trust scale,
  focus groups), not a level update. **Updated by `study-instruments-plan.md`:** the study's length is not decided, so
  "Week 7 / Week 14" become "end of module 1 / module 2" (configured lecture groups).
- **Instruments (`study-instruments-plan.md`):** the 16-item trust scale is Jian et al.'s 12 plus 4 study-specific
  items (ReelEd's own 4 are unpublished), asked of Condition A only; SUS is asked of both conditions about "this app";
  NASA-TLX is Raw TLX; the efficacy questionnaire is 12 items (ReelEd's comparisons to lectures removed, relevance and
  pacing added); demographics are 8 questions. Check the Jian wording against the original paper before IRB submission.
- **Limitations:** item parameters are LLM priors with α fixed at 1 until calibration; SE(θ) ≈ 1 logit at these test
  lengths; engagement adjusts delivery, not ability.
- **Videos:** generated on demand at the student's level and cached (roadmap 4), instead of "per readiness level"
  ahead of time (§3.3 wording).

## Roadmap after this branch (separate branches, in order)
1. **Study instruments** *(built on `study-instruments`, see `plan/study-instruments-plan.md`)*: consent, demographics,
   and Raw TLX, SUS, learning efficacy and trust at the end of each module, in the app; researcher CSV export.
2. **Condition B:** the control experience ("unmodified lecture recordings uploaded to the LMS") and its logging.
   *Parked 2026-10-15 with study design; decisions B1–B5 so far (slides, since there are no recordings) in
   `plan/condition-b-plan.md`.*
3. **Retention and transfer:** module quizzes immediately and two weeks later (forgetting curve, H1); final-exam
   transfer items; kept separate from the items that set levels.
4. **Pipeline** *(built on `per-student-video`, see `plan/per-student-video-plan.md`)*: on-demand generation at the student's KU level, cached by (slide content, KU, level); replaces
   "three versions per KU" (plan §7.4). Target: first video ≈ 3 min after a check, each later one ready before the
   student needs it (today ≈ 8 min per video). Item banks generated per upload.
5. **Figma UI redesign** (`ui-improvement`): resumes with My Levels grouped by lecture and the Week 7 banner
   dropped.

## Engine notes (found while building commit 2)

These are properties of the `catsim` 0.21.0 / scipy 1.18 behaviour the engine inherits; the TypeScript port must
reproduce them, and the parity file pins them.

- **Selection ties.** catsim's `MaxInfoSelector` sorts with `numpy.argsort`, which is not stable, so equally
  informative items come back in arbitrary order. With α = 1 every item at the same distance from θ ties (b = +0.5
  and −0.5 at θ = 0), so ties are the common case, not an edge case. The engine picks the most informative unseen
  item and breaks ties (within 1e-9 information) by **pool order**. It uses catsim's own information function.
- **Dodd's heuristic uses the whole pool.** For an all-correct (all-wrong) pattern catsim moves θ halfway toward the
  *pool's* hardest (easiest) item, from the previous estimate, so it compounds: after n uniform answers θ is
  (1 − 2⁻ⁿ) of the way from the start to the pool's extreme. After 4 answers that is 94%. The pool therefore needs a
  wide difficulty range (the 3 tiers per KU across a lecture's KUs provide it).
- **Dodd is not an MLE.** With a narrow pool, "all correct" can come out *below* "all but one correct" (observed:
  1.48 vs 2.09 on a 6-item pool spanning −1 … 1.5), and "all wrong" above "one right". The estimate is always finite
  and inside the pool's range. We keep catsim's behaviour (D7); revisit after the pilot with calibrated items.
- **Estimation replays the answers in order**, because Dodd is defined from the previous estimate. A "Not sure" answer
  never enters the estimate; a hinted answer enters as the same item with b − `hint_beta_shift`.
- **Standard error** is 1/√(test information) over the scored answers (infinite before any). With α = 1 and 4 items
  near θ it is ≈ 1.0 logit, which is why the length is fixed (D7) and why "least certain topic" (D8, review items)
  can use it directly.
- catsim prints a blank line on every item-bank validation, so items are validated in `BankItem` and `ItemBank` is
  built with `validate=False`.

## Logic notes (found while building commit 5)

- **One estimation pool per lecture:** the lecture's bank items plus its videos' quick-check, next-day and prove-it
  items (difficulty = the item's `difficulty_prior`, discrimination 1). A repeated item (Watch again) counts once, by
  its latest answer. Items answered in any sitting are never asked again.
- **Provisional levels:** a lecture nobody has asked about borrows the θ pooled over every answer so far, read against
  that KU's own applied/advanced difficulties; the reason says it has not been asked yet. A lecture answered entirely
  "Not sure" is novice; with no answers anywhere a KU is "not checked".
- **Fallback:** when a lecture runs out of unseen items the sitting takes the next item from another lecture rather than
  ending early. (The dev course's lecture 3 has 18 bank items; a lecture with fewer than the baseline asks would show it.)
- **Review items** go to the earlier lecture with the largest standard error (an unmeasured one counts as infinite,
  ties to the earlier lecture); with no earlier lecture left they become one more item on the lecture itself.
- **Simulated students on the real bank** (right exactly when ability ≥ difficulty): θ = −2 → 20 KUs at Level 1;
  θ = 0 → 11/9/0 at Levels 1/2/3; θ = 2 → 0/4/16. A θ = 0 student never reaches Level 3 because advanced items sit up
  to +1.5; that is the tier rule working as designed, and a reason to look at the tier offsets after the pilot.
- **Deferred from D8:** the baseline covers the first `cat_week0_lectures` lectures only. The "prerequisite roots of
  later lectures" part cannot be exercised by the 3-lecture dev course; add it when a longer course exists.
- **Not yet wired:** dropped-early videos go back to the top of the playlist ("pick up where you left off"); replays
  at `refresher_replay_count` queue a refresher; both need the player to record progress (commit 6).

## Wiring notes (found while building commit 6)

- **Prerequisites beat "upcoming lecture first".** The coin-toss video (Lecture 3) builds on two earlier videos, so a
  student who needs all four now sees those two first. This is D14 working, and it changes the old playlist order and
  its "why" text (which now names the pair: "“A” comes first because “B” builds on it").
- **No second check right after the baseline.** A pre-lecture check is skipped when the Week 0 baseline already covered
  that lecture in the same lecture week; it is due from the next week. The facilitator's "Simulate next week" moves the
  clock a week, so the flow can be demoed and tested.
- **A student-set level is never overwritten by a check**; only its suggestion moves ("Use suggested level").
- **Resetting the model** archives the levels *and the check answers* and clears the check answers, so the retaken
  baseline starts fresh; watch history, notes and video answers stay.
- **A video stopped early** returns to the top when the playlist is read once 30 minutes have passed (not at a rebuild),
  unless the student has set their own order.
- **Left for later:** the My levels / start-result screens show 20 KU cards in plain styling (the Figma plan's
  "KU row" frame still needs designing); the "What changed" list repeats the lecture in every sentence and could group
  by lecture; `README.md` and `ui-ux-implementation-plan.md` still describe Week 7 (commit 8).
