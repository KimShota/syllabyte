# Per-KU learner profiling with CAT: plan

Branch: `per-ku-profiling` (from `main` at 2d391ce). Status: **decisions settled (2026-10-12), not started.**
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
| D5 | **Item parameters before calibration:** β = LLM `difficulty_prior` adjusted by Bloom tier; **α fixed at 1.0** (Rasch inside the 2PL machinery) until post-pilot calibration. Stated as a limitation. |
| D6 | **KU readiness (tier rule):** proficient if θ ≥ β of the KU's advanced item; developing if θ ≥ β of its applied item; else novice. Shown as Levels 3/2/1. |
| D7 | **CAT settings:** start θ = 0 (`FixedPointInitializer`); next item = most informative unseen item (`MaxInfoSelector`); θ by `NumericalSearchEstimator` (bounded) with Dodd; **fixed length** (`TestLengthStopper`). **"Not sure"** counts toward the length but not the estimate (plan §2 rule 3); a topic answered entirely "Not sure" makes its KUs novice. Limitation: with α = 1, SE(θ) stays ≈ 1 logit after ~4 items, so an SE stopping rule would never fire at these lengths. |
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
1. **Fixtures carry the KU graph:** lectures as topics, Bloom level and prerequisites on KUs, new item fields;
   Python models, builder, TS types, `check-fixtures`.
2. **CAT engine (Python):** add `catsim`; `assessment_agent` CAT + readiness; pytest; parity golden file.
3. **CAT engine (TypeScript):** `cat.ts`, `readiness.ts`; parity and unit tests.
4. **Item bank:** per-KU 3-tier generation in the builder. **Dry run on one lecture first and report the LLM cost;
   full run only after approval.** Retire onboarding/re-check items.
5. **Profile and delivery:** state v2, Week 0 CAT, pre-lecture checks with review items, continuous evidence,
   lecture-boundary updates, made-level tracking, prerequisite ordering, engagement refreshers, per-KU "Correct
   this", Week 7 removal, persona; unit tests.
6. **Screens:** CAT quiz (no back), pre-lecture check card, My levels by lecture, "What changed" card, onboarding
   result; delete `/recheck/*`; e2e + axe.
7. **Docs:** `ui-ux-implementation-plan.md` (rule 1, rule 2, §3.1, §3.1b, §3.3, §3.8, §3.9–3.10 removed, §4.1,
   §4.3, §4.4 removed, §4.6, §5, §6.1 endpoints, traceability), `apps/web/README.md`.

## Needs the advisor's sign-off (proposed changes to the proposal; OSF pre-registration not filed yet)
- **H3 and the profile-shift heatmap:** from "learning gains after the automatic Week 7 reassessment vs a static
  initial profile" to "continuous per-lecture adaptation vs a static Week 0 profile", with a per-KU readiness
  trajectory across lectures.
- **Week 7** stays only as the study's midterm measurement (retention quiz, NASA-TLX, SUS, Likert, trust scale,
  focus groups), not a level update.
- **Limitations:** item parameters are LLM priors with α fixed at 1 until calibration; SE(θ) ≈ 1 logit at these test
  lengths; engagement adjusts delivery, not ability.
- **Videos:** generated on demand at the student's level and cached (roadmap 4), instead of "per readiness level"
  ahead of time (§3.3 wording).

## Roadmap after this branch (separate branches, in order)
1. **Study instruments:** NASA-TLX per module, SUS, learning-efficacy Likert, trust-in-automation scale; the Week 0,
   Week 7 (midterm) and Week 14 batteries. Needed for H1–H4 and the IRB package.
2. **Condition B:** the control experience ("unmodified lecture recordings uploaded to the LMS") and its logging.
3. **Retention and transfer:** module quizzes immediately and two weeks later (forgetting curve, H1); final-exam
   transfer items; kept separate from the items that set levels.
4. **Pipeline:** on-demand generation at the student's KU level, cached by (slide content, KU, level); replaces
   "three versions per KU" (plan §7.4). Target: first video ≈ 3 min after a check, each later one ready before the
   student needs it (today ≈ 8 min per video). Item banks generated per upload.
5. **Figma UI redesign** (`ui-improvement`): resumes with My Levels grouped by lecture and the Week 7 banner
   dropped.
