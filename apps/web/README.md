# SyllaByte student web app (Phase 0 prototype)

The student-facing UI from `plan/ui-ux-implementation-plan.md`. **Phase 0** is a clickable prototype:
a static Next.js site that runs the whole loop (a baseline check → a level for every Knowledge Unit → playlist →
videos with one quick check → a short check before each lecture that updates the levels) on course fixtures, with
no backend. Levels are measured by adaptive tests (2PL IRT), per KU: see `plan/per-ku-profiling-plan.md`. Phases 1–3 swap the
in-browser mock for FastAPI without touching any component.

## Run it

```bash
# 1. once, from the repo root: build the fixtures from a finished pipeline run
uv run python scripts/build_ui_fixtures.py --run runs/dev --out packages/core/fixtures
# 1b. the adaptive-assessment bank (3 questions per KU). It spends LLM credits the first time; --estimate prices it first
uv run python scripts/build_item_bank.py --estimate
uv run python scripts/build_item_bank.py
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

- **Participant code** (stamped on every event), **Reset demo**, **Simulate next day** (+24 h) and **Simulate next week** (+7 days: the
  next lecture's check becomes due).
- **Jump to** any screen. Anything that needs the baseline fast-forwards it (a scripted student: strong on lecture 1, middling on 2, weak on 3).
  The "Lecture checks" jumps load a scripted student (`packages/core/src/api/persona.ts`), built by running the *real* API with a backdated clock, who has
  crossed a lecture boundary: some levels went up, some down, and the "What changed and why" card is waiting.
- **Download session log** and `/debug/events`, a live timeline of what a click logged.
- "Log events even if consent was declined" is **on** for usability sessions; turn it off to see the research rule.

## Where things are

The app logic is shared with the phone app and lives in `packages/core` (`@syllabyte/core`, see its README):
the types, the API contract and its mock, the store, the rules in `logic/`, the questionnaires and the consent text.

```
app/                    routes (App Router). Pages are thin; behaviour lives below
components/             ui/ primitives, player/ (frame, quick check, sheets), shared screens
lib/store.ts            the browser side of the core store: localStorage, the visit per session, React hooks
lib/events.ts           the browser's event context (screen, device, orientation) for the core's `track`
lib/api/hooks.ts        useQuery over the core's `api`
lib/api/demo.ts         the core's demo-menu controls, plus a browser download
scripts/                copy-fixtures, check-fixtures, screenshots
tests/e2e               Playwright
```

**Rule for every "because…" sentence the student sees:** it is a template over stored answers
(`packages/core/src/logic/*`), never free text from a model, so the numbers in it are true by construction. The
unit tests assert this.

## Test

The rules and the mock API are unit-tested in `packages/core` (`npm test` there).

```bash
npm run test:e2e         # builds a test build, then Playwright at 390×844 and 1280×800, incl. axe (WCAG 2.2 AA)
npm run shots            # screenshots of every screen into ./shots
```

The e2e build lists a small WebM before the MP4 (`NEXT_PUBLIC_TEST_WEBM=1`, `FIXTURES_WEBM=1`)
because Playwright's Chromium has no H.264 decoder. Real browsers get the MP4.

## Decisions that shaped the code

The 37 design decisions are in the plan (§16 indexes them). The ones most likely to be revisited:

- **9:16 video**, capped at 62% of the screen height and shorter on a phone so the controls stay in view. Nothing is drawn over the video, captions included.
- **One quick check per video**, after the last *deliver* segment: answer → "How sure?" → result appears by itself. No "Not sure yet" there (the "Guessing" rating covers it).
- **A level belongs to a Knowledge Unit, a topic is a lecture.** The student's ability (θ) is estimated per lecture from every answer on it (the baseline and checks, plus the quick check, next-day and prove-it items of its videos); a KU's level comes from its own item difficulties (the tier rule).
- **Levels change only at a lecture boundary** (the end of a baseline or a check before a lecture) **or when the student corrects them.** In between, answers move the estimate behind the scenes but never a level the student sees. A level the student set is not overwritten.
- **The checks are adaptive and fixed-length, with no going back.** "Not sure" counts toward the length but not the estimate. Each question is chosen when it is asked, from the answers before it, so the same answers always give the same next question.
- **A video is made once** at the KU's level when first needed, and says so when the level has since changed. Engagement (a video stopped early, watched several times) changes what the playlist delivers, never a level.
- A hint that was visible when a student answered counts as used, so the answer is scored as the same question made easier (`irt_hint_beta_shift`); a Level 1 student, who sees the hint inline, always has it applied.
- **The adaptive engine exists twice**: Python (`catsim`, the engine of record) and a TypeScript port for this static site. `packages/core/tests/catParity.test.ts` replays 26 recorded sessions and fails on any difference in the question chosen or in θ (`uv run python scripts/make_cat_parity.py` regenerates them).

## Known issues

- **Video quality.** Two of the four fixture videos show an unrelated "Quadratic Growth" / "Areas Under Curve" plot and clipped titles. These are defects in the pipeline's older output, not in the app. Re-render with the current pipeline and rerun `npm run fixtures`.
- Only one version (labelled Level 2) of each video exists, so students at Level 1 or 3 see "Level 2 version · Level N coming soon" (plan Q31).
- "Download my data" is a JSON file in Phase 0 (the ZIP arrives in Phase 3). Sign-in, email and the instructor queue start in Phases 1–2.
