# Study instruments: plan

Branch: `study-instruments` (from `main` at 4369192). Status: **built 2026-10-14** (commits 1-3 below; tests: 218 unit, 108 e2e with axe, 157 Python).
Roadmap item 1 of `plan/per-ku-profiling-plan.md`. Source: the proposal §4.2 (outcome measures) and §5 (timeline batteries).
Supersedes `plan/ui-ux-implementation-plan.md` §3.18's "questionnaires open in Qualtrics" (Q27): they are now in the app.

## What the proposal asks for

| Proposal | Instrument | Here |
|---|---|---|
| Week 0 baseline | CAT knowledge assessment, demographic survey | CAT exists; demographics added (I6) |
| "after each module" | NASA-TLX | Raw TLX at each module end (I2, I4) |
| Week 7 midterm battery | retention quiz, NASA-TLX, SUS, Likert efficacy, trust | module-end battery, minus the retention quiz (roadmap 3) |
| Week 14 final battery | the same scales, transfer questions, course grade | the same module-end battery; transfer and grades are roadmap 3 / offline |
| Weeks 7 and 14 | focus groups | offline, not in the app |

## Decisions (grilled 2026-10-14)

| # | Decision |
|---|---|
| I1 | **In the app**, for both conditions, through the same API as everything else (Phase 1 swaps the mock for the backend with no screen changes). One channel, one participant code, one dataset for the mixed-model analysis. |
| I2 | **Scheduled by course modules, not calendar weeks** (the study's length is not decided). A module is a configured group of lectures (`study_modules`; default: the course's lectures split in two). Three time points as in the proposal's analysis: baseline at sign-up, a battery at the end of module 1 and at the end of module 2. A module has ended once the course schedule has moved past the week of its last lecture (the same moment for every student, whatever they watched). The proposal's "Week 7 / Week 14" become "end of module 1 / 2": an advisor sign-off item. |
| I3 | **Trust: 16 items, Condition A only.** Jian, Bisantz & Drury's 12 items word for word with "the system" replaced by "SyllaByte" (an instruction line says SyllaByte means the AI system that made the videos), plus 4 study-specific items on the topics ReelEd describes (accuracy, help for learning, reliance) and one on the level choice. 7 points, 1 "Not at all" – 7 "Extremely". Reported as "Jian et al.'s 12 items plus 4 study-specific items"; the Jian score is computed from the 12 alone (items 1–5 reversed). |
| I4 | **NASA-TLX: Raw TLX.** Six dimensions with NASA's wording and anchors, 0–100 in steps of 5, no weighting; score = mean. Both conditions, about "studying this module's videos". |
| I5 | **SUS: both conditions, about "this app"** (standard 10 items, "system" → "app"); H4 uses Condition A, B is the baseline. |
| I6 | **Demographics at baseline:** 8 questions (below), each with "Prefer not to say"; age as a range; no nationality or ethnicity. Research participants only, after consent, before the CAT; skippable. |
| I7 | **Learning efficacy: 12 items, both conditions** (below): 8 of ReelEd's 9 with the comparisons to lectures removed, plus relevance and pacing. 7 points, 1 "Not at all" – 7 "Extremely". |
| I8 | **Consent in the app** (exists): declining keeps the full app with nothing recorded and no questionnaires; withdrawing in Settings stops research logging and can delete what was collected, questionnaire answers included. |
| I9 | **Batteries never block learning:** a card at the top of the playlist until submitted; "Not now" hides it for this visit and it returns on the next. The time from the module's end to the answer is recorded. |
| I10 | **Any question can be skipped.** Leaving items blank and pressing Next asks "Skip N questions?", so a skip is deliberate and recorded as skipped. A scale with a skipped item keeps its answers, is marked incomplete and gets no score (how to treat missing data is the analysis plan's call). |
| I11 | **Condition (A/B) is on the participant**, set by the researcher (the demo menu in Phase 0, the backend in Phase 1), and no longer reset at consent. For now it decides only who sees the trust scale; Condition B's experience is roadmap item 2. |
| I12 | **Researcher export:** CSV, one row per participant × battery × item (response or skipped, timings) plus one row per scale score. Demo data can be run through the analysis now. Out of scope: retention/transfer quizzes (roadmap 3), sending answers to a server (Phase 1). |

## Instruments

**Demographics (I6)** — every question also offers "Prefer not to say".
1. Year of study: 1st, 2nd, 3rd, 4th, Other
2. Major or intended major (free text)
3. Have you taken a course on this subject before? No / Yes, at school / Yes, at university
4. How familiar are you with this course's topics? 1 (Not at all) – 5 (Very)
5. How often do you watch short educational videos (TikTok, YouTube Shorts, Reels)? Never / Less than weekly / Weekly / Several times a week / Daily
6. Is English your first language? Yes / No
7. Age: 18–19, 20–21, 22–24, 25 or older
8. Gender: Woman, Man, Non-binary, Self-describe (free text)

**Raw NASA-TLX (I4)** — "Think about studying this module's videos." 0–100 in steps of 5.
Mental demand "How mentally demanding was the task?" (Very low – Very high); Physical demand "How physically demanding was the
task?"; Temporal demand "How hurried or rushed was the pace of the task?"; Performance "How successful were you in accomplishing
what you were asked to do?" (Perfect – Failure); Effort "How hard did you have to work to accomplish your level of performance?";
Frustration "How insecure, discouraged, irritated, stressed, and annoyed were you?"

**SUS (I5)** — 1 Strongly disagree – 5 Strongly agree; score = 2.5 × Σ(odd: x−1, even: 5−x).
1 I think that I would like to use this app frequently. 2 I found the app unnecessarily complex. 3 I thought the app was easy to
use. 4 I think that I would need the support of a technical person to be able to use this app. 5 I found the various functions in
this app were well integrated. 6 I thought there was too much inconsistency in this app. 7 I would imagine that most people would
learn to use this app very quickly. 8 I found the app very cumbersome to use. 9 I felt very confident using the app. 10 I needed to
learn a lot of things before I could get going with this app.

**Learning efficacy (I7)** — 1 Not at all – 7 Extremely; score = mean.
1 I was able to understand the topics well through these videos. 2 I feel confident explaining these topics to others. 3 The videos
broke the topics down into manageable parts. 4 The videos helped me remember the key points. 5 The videos made it easy to revisit
important concepts. 6 The videos helped me stay focused. 7 I felt engaged while watching the videos. 8 I would like to learn future
topics this way. 9 The videos covered what I needed for this course. 10 The examples in the videos were relevant to the course
material. 11 The pace of the videos was right for me. 12 The videos were at the right level for what I already knew.

**Trust (I3)** — "SyllaByte here means the AI system that made your videos." 1 Not at all – 7 Extremely.
Jian et al. (distrust 1–5, reversed for the score): 1 SyllaByte is deceptive. 2 SyllaByte behaves in an underhanded manner. 3 I am
suspicious of SyllaByte's intent, action, or outputs. 4 I am wary of SyllaByte. 5 SyllaByte's actions will have a harmful or
injurious outcome. 6 I am confident in SyllaByte. 7 SyllaByte provides security. 8 SyllaByte has integrity. 9 SyllaByte is
dependable. 10 SyllaByte is reliable. 11 I can trust SyllaByte. 12 I am familiar with SyllaByte.
Study-specific: 13 The videos were accurate to my course's slides. 14 The videos helped me learn. 15 I would rely on these videos to
study for this course in the future. 16 I trust the levels SyllaByte chose for me.
(Item 16 asks about trusting the level choice rather than "the right level", which efficacy item 12 already asks.)

**Before IRB submission:** check the Jian wording against the original paper (Jian, Bisantz & Drury 2000, *Int. J. Cognitive
Ergonomics* 4(1)); it was taken from secondary sources that agree on the items and their order.

## Design

- **Content:** `apps/web/content/instruments.ts`: every instrument as data (id, version, items with wording, response options,
  reverse flags, condition filter, source).
- **Logic:** `lib/logic/instruments.ts`: which batteries are open (`studyModules(course)` with the default split; a module has
  ended when the week is past its last lecture's week, or the demo's upcoming lecture is past it), what each battery contains for a
  condition, scoring (SUS, Raw TLX, efficacy mean, Jian score, study-items mean; `complete: false` and no score when any item is
  skipped), and the CSV export.
- **Config:** `CourseConfig.study_modules: { id, title, lectures: number[] }[] | null` (null = split in two), mirrored in
  `learner.py`.
- **State:** `DemoState.study: Record<batteryId, BatteryRecord>` (`baseline`, `module-1`, `module-2`), with `opened_at` (when it
  became due), `started_at`, `submitted_at`, `snoozed_visit`, and `answers: Record<itemId, number | string | "skipped">`. Written only
  when consent is "research".
- **API:** `getStudyTasks()`, `getBattery(id)`, `saveBatteryPage(id, answers)`, `submitBattery(id)`, `snoozeBattery(id)`,
  `exportStudyCsv()`; `postConsent` keeps the condition; `withdrawFromResearch(deletePast)` also deletes questionnaire answers.
- **Screens:** `/study?b=<id>`: one instrument per page, one tap per item (TLX as a 21-point tap scale with no default), the skip
  confirmation, a thank-you page. `StudyCard` at the top of the playlist. After consent, research participants see the
  demographics before the baseline CAT. Consent text: drops the stale "mid-semester re-check" line and lists questionnaires.
  Demo menu: Condition A/B and "Download study responses (CSV)".
- **Events:** `study_shown`, `study_started`, `study_submitted`, `study_snoozed`.

## Commits

1. Instruments as data, scoring and the CSV export, with unit tests.
2. Config, state, schedule and the mock API (consent keeps the condition; withdraw deletes answers), with unit tests.
3. Screens: the study route, the playlist card, demographics after consent, consent text, demo menu; e2e tests with axe.
4. Docs: this plan's status, the per-KU plan's roadmap, the advisor sign-off items (Week 7/14 wording; the 16-item trust scale's
   composition).

## Built (2026-10-14)

- **Behaviour checked end to end** (`tests/e2e/study.spec.ts`, mobile and desktop): "About you" right after research consent, with
  the gender self-description appearing only when chosen and the skip confirmation; a decliner never sees a questionnaire; the
  module 1 card appears once the schedule passes lecture 2, and the battery runs TLX → efficacy → SUS → trust (Condition B: three
  pages); "Not now" and resuming mid-way. axe runs on every questionnaire page, the skip sheet and the playlist with its cards.
- **Found while building:** a tap on the middle of an unanswered TLX line moves nothing, so the browser sends no change event; the
  line answers on the tap itself. Research participants who close "About you" keep its card on the playlist, so a playlist can carry
  two "Not now" buttons (the lecture-check test now scopes to its card).
- **The course config's `upcoming_lecture_override`** (Phase 0's pin so all videos show) does not end modules; only the weeks or
  the demo's own upcoming-lecture override do. Otherwise every demo would open with module 1's questionnaire due.

## Open

- Condition B's own experience (roadmap item 2) will need the same cards on its home screen.
- Phase 1: `exportStudyCsv` over all participants, from the backend.
- Advisor sign-off: the Week 7/14 wording and the trust scale's composition (listed in `per-ku-profiling-plan.md`).
