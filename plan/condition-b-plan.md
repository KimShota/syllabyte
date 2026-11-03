# Condition B (control): plan

Status: **parked 2026-10-15** (user: study design is settled later). Roadmap item 2 of `plan/per-ku-profiling-plan.md`.
Builds on `plan/ui-ux-implementation-plan.md` §3.14 (Q26: a minimal SyllaByte shell, not the LMS).

## Decisions so far (grilled 2026-10-14/15)

| # | Decision |
|---|---|
| B1 | **Slides, not recordings.** The pilot course has only slides and a syllabus; there are no lecture recordings. B gets each lecture's slides (`slides.pdf`, cut at the lecture's `slide_start`–`slide_end`) instead of the proposal's "unmodified lecture recordings". Both conditions then learn from the same source; only the delivery differs. Advisor sign-off item. |
| B2 | **A slide-by-slide viewer** in B's one tab, Course materials: one full-width slide per screen, Next/Back and swipe, the slide's text as alt text and a "Slide text" panel. Logged per slide: enter, leave, time while the page is visible. |
| B3 | **B takes the same baseline check** (same items and engine) for the ANCOVA covariate; its estimates are stored for the analysis only and never shown. No levels, My levels, lecture checks or mid-semester recheck in B (those exist to set levels; in B they would be extra testing for one group). |
| B4 | **Lectures open on A's schedule** (when A's playlist reaches the lecture) and stay open; later ones are listed as "Opens with Lecture n · Week w". |
| B5 | **H2's primary measure uses each condition's own unit:** A, a video watched to the end (≥ 90%); B, a lecture's slides reached to the last one with ≥ 2 s on each slide passed. Drop-off = how far through the unit. Secondary: the share of each lecture's material viewed (A: its videos completed; B: its slides viewed ≥ 2 s). The 2 s threshold is an advisor sign-off item. |

## Open (when study design resumes)

- **Q6, slides outside the app:** the professor will likely post slides on the LMS for everyone. Recommended: give A the same
  slide viewer (a Slides section in its Course tab) and add one item to each module questionnaire, for both groups: "Outside
  this app, how much did you study this module from the slides or other course materials?" (None / A little / About half /
  Most / Nearly all). Not yet decided.
- Then: B's settings and notifications, its events (`slide_view`?), the export columns, and the e2e tests.
