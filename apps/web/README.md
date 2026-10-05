# SyllaByte student web app (Phase 0 prototype)

The student-facing UI from `plan/ui-ux-implementation-plan.md`. **Phase 0** is a clickable prototype:
a static Next.js site that runs the whole loop (onboarding → per-topic levels → playlist → videos
with one quick check → Week 7 re-check) on course fixtures, with no backend. Phases 1–3 swap the
in-browser mock for FastAPI without touching any component.

## Run it

```bash
# 1. once, from the repo root: build the fixtures from a finished pipeline run
uv run python scripts/build_ui_fixtures.py --run runs/dev --out apps/web/fixtures
# (reuses runs/dev/ui_cache, so it is free after the first run; add --regen to redo the LLM part)

# 2. from apps/web
npm install
npm run fixtures          # copies videos, posters, captions and slide images into public/fixtures/
npm run dev -- --hostname 0.0.0.0      # phones on the same Wi-Fi can open http://<your-ip>:3000
```

`npm run build` makes a static export in `out/` that can be hosted anywhere. Fixtures and media are
**gitignored**: they come from the professor's slides, so they stay on your machine.

The course content is *Computational Social Science*. Its four rendered videos are early-pipeline
output and some contain visual defects (see "Known issues"); the app does not depend on which run
you point it at.

## For facilitators: the demo menu

Hidden from students. Open it with `?demo=1` on any URL, a 1-second long-press on any course
eyebrow (the small grey title above a heading), or `Ctrl+Alt+D`.

- **Participant code** (stamped on every event), **Reset demo**, **Simulate next day** (+24 h on the app's clock).
- **Jump to** any screen. Anything that needs onboarding fast-forwards it. The "Week 7" jumps load a
  scripted student (`lib/api/persona.ts`) whose answers, run through the *real* rules, produce two
  level-ups, one level-down and one unchanged topic.
- **Download session log** and `/debug/events`, a live timeline of what a click logged.
- "Log events even if consent was declined" is **on** for usability sessions; turn it off to see the research rule.

## Where things are

```
app/                    routes (App Router). Pages are thin; behaviour lives below
components/             ui/ primitives, player/ (frame, quick check, sheets), shared screens
lib/types.ts            types shared by fixtures, state and views (mirrors packages/common/.../learner.py)
lib/api/types.ts        THE contract: every method the UI may call (plan §6.1)
lib/api/mock.ts         Phase 0 implementation of that contract, on top of lib/store.ts (localStorage)
lib/api/client.ts       the only import components use: `api`
lib/logic/              pure rules, unit-tested: levels, playlist, Week 7 proposals, next-day timing,
                        calibration, tailoring receipt, time slots, .ics
lib/events.ts           one event shape and vocabulary in every phase (plan §6.2)
content/consent.md      placeholder consent text: replace with the IRB-approved wording
scripts/                copy-fixtures, check-fixtures, sync-consent, screenshots
tests/unit, tests/e2e   Vitest and Playwright
```

**Rule for every "because…" sentence the student sees:** it is a template over stored answers
(`lib/logic/*`), never free text from a model, so the numbers in it are true by construction. The
unit tests assert this.

## Test

```bash
npm test                 # Vitest: rules and the mock API against the real fixtures (skips if there are none)
npm run test:e2e         # builds a test build, then Playwright at 390×844 and 1280×800, incl. axe (WCAG 2.2 AA)
npm run shots            # screenshots of every screen into ./shots
```

The e2e build lists a small WebM before the MP4 (`NEXT_PUBLIC_TEST_WEBM=1`, `FIXTURES_WEBM=1`)
because Playwright's Chromium has no H.264 decoder. Real browsers get the MP4.

## Decisions that shaped the code

The 37 design decisions are in the plan (§16 indexes them). The ones most likely to be revisited:

- **9:16 video**, capped at 62% of the screen height and shorter on a phone so the controls stay in view. Nothing is drawn over the video, captions included.
- **One quick check per video**, after the last *deliver* segment: answer → "How sure?" → result appears by itself. No "Not sure yet" there (the "Guessing" rating covers it).
- **Levels change only at Week 7 or when the student corrects them.** Weeks 1–6 evidence only affects playlist tags.
- **Week 7 proposal rule** (`lib/logic/proposals.ts`) reads "needs ≥ 3 answered" as: the *score* rules need 3 answered, the *"mostly Not sure"* rule needs 3 presented. Read literally, the second could never fire.
- A hint that was visible when a student answered counts as used (half credit at Week 7), so a Level 1 student, who sees the hint inline, earns half credit for checkpoint answers.

## Known issues

- **Video quality.** Two of the four fixture videos show an unrelated "Quadratic Growth" / "Areas Under Curve" plot and clipped titles. These are defects in the pipeline's older output, not in the app. Re-render with the current pipeline and rerun `npm run fixtures`.
- Only one version (labelled Level 2) of each video exists, so students at Level 1 or 3 see "Level 2 version · Level N coming soon" (plan Q31).
- "Download my data" is a JSON file in Phase 0 (the ZIP arrives in Phase 3). Sign-in, email and the instructor queue start in Phases 1–2.
