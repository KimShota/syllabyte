# Mobile app (React Native / Expo) from the Figma design: plan

Status: **being built.** `apps/mobile` (all design screens) and `packages/core` (the shared logic) are on `main`;
the study flows are on branch `study-flows` (2026-10-18). Real video files and Android come next.

## Decided

- **Mobile first, one codebase for iOS and Android** (the user and their mentor). The pilot is phone-only.
- **React Native with Expo**, not Capacitor. The app will have a vertical swipe feed (one full-screen video at a
  time, swiping to the next), which needs native paging and the native video player. Capacitor (the current web app
  wrapped in a web view) was considered: it keeps every screen, but a smooth swipe feed of videos is its weak spot.
- **The UI follows the Figma design**, replacing the paused `ui-improvement` restyle of the web app.
- **The current Next.js app (`apps/web`) stays** as the reference and the advisor demo until the Expo app matches it;
  then it is retired.

## Proposed setup (to confirm in the planning round)

- `apps/mobile`: Expo (managed), Expo Router, TypeScript; `expo-video` for the player; `FlatList` paging (or
  `react-native-pager-view`) for the feed; EAS Build for iOS/Android builds, TestFlight and Play internal testing.
- **Shared core package** (e.g. `packages/core`): move the plain-TypeScript code from `apps/web` so both apps import
  it unchanged, with its Vitest tests:
  - `lib/logic/*`: the CAT engine and its parity test, `kuProfile`, `levels`, `playlist`, `prereq`, `nextSession`,
    `instruments`, …
  - `content/*`: instruments, consent text, …
  - `lib/types.ts` and `lib/api/types.ts` (the `Api` interface), and the mock API.
  - These touch no browser APIs, except `lib/events.ts`, `lib/store.ts` and `lib/api/demo.ts`, which use
    `localStorage`/`window` and need a storage adapter (AsyncStorage or SecureStore on the phone).
- **Screens are rewritten** in React Native from the Figma frames.
- **Tests:**
  - Vitest for the core stays;
  - React Native Testing Library for components;
  - **Maestro** flows on the simulator replace Playwright;
  - accessibility via React Native accessibility props plus manual VoiceOver/TalkBack passes (axe doesn't apply).
- **Tools:** Xcode is installed; Android Studio is not (needed for the Android emulator). Node 24.

## Figma

- **File key `GEyz1Qcu8eGYySr6IpTpya`** (capital I). The user said on 2026-10-17 that the design is complete; confirm
  this is the final file.
- **Frames on Page 1** (390 wide on mobile):
  - Course Roadmap `1:2`
  - Lecture Roadmap `1:202`
  - My Levels `1:436`
  - Profile & Components `1:637`
  - Video Player & Study Workspace `1:1315`
  - desktop versions of the Course Roadmap, Lecture Roadmap and Player (ignored for a phone-only pilot)
- **The player frame** has:
  - the video, ±10 s, CC, speed;
  - an "Ask AI Explainer" button;
  - a "Slides 9-11" chip and a bookmark;
  - Transcript / Study Notes tabs.
- **Mentor's comment:** a Home screen separate from the lecture roadmap. The frames checked on 2026-10-17 had none.

## Decided while building (2026-10-18)

- **iOS first.** Android waits (no Android Studio yet); the code stays cross-platform.
- **The in-video quick check** interrupts the video at its checkpoint and **blocks swiping** until it is answered
  (the back button still works; leaving and coming back asks it again). It is asked **only the first time**: once
  answered, right or wrong, it never comes back. No skip and no "Not sure yet" (the "How sure?" rating covers it).
  This answers Q1 for the quick check; "Not sure yet" stays on the adaptive checks.
- **No consent screen in the app:** every student who gets the app has already consented to the research, so the
  app records research consent itself. Needs advisor sign-off: the IRB usually wants a way to withdraw, which the
  app no longer offers (the web app had it under Settings).
- **No My Levels screen.** Levels still drive the videos behind the scenes; students don't see or correct them.
  Needs advisor sign-off: the Trust questionnaire's item 16 ("I trust the levels SyllaByte chose for me") asks
  about levels the phone app never shows.
- **The check before a lecture is required** (2026-10-18): there is no way to skip or postpone it. Until it is
  done, that lecture's videos are locked: a direct link to one goes to the check, and the roadmap node says "Take the
  check first". Earlier lectures' videos stay open. Needs advisor sign-off: the web app's plan (D8) lets the student
  skip it, so this changes the research design, and the web app still allows skipping.
- **The initial quick check (Week 0 baseline) is required and can't be left** (2026-10-18): no skip, no "Not now", and
  no close button on its questions. Until it is finished, every screen except the first-run screens and the check
  itself sends the student back to it (a root-layout guard), so backing out, killing the app or opening a video link all
  end at the check, which resumes where it was left. Needs advisor sign-off with the lecture-check item above. The
  check before a lecture still has a close button, but its videos stay locked until it is done.
- **The questionnaires** appear as cards on Home with "Not now", which hides one until the next launch. The check
  before a lecture is also a card on Home and on its lecture's roadmap.

## Open questions for the planning round (roughly in order)

1. **Scope of the swipe feed:** does it replace the playlist, the player, or both? Where do the in-video checks,
   quick checks and "Not sure yet" go in a feed?
2. **A Home screen**, separate from the roadmap (the mentor's comment): what's on it (the next videos, the check
   before a lecture, the study cards)?
3. **New features in the design that the app doesn't have yet:**
   - **Ask AI Explainer:** what it may answer, grounding in the slides, cost, and whether it's in the study.
   - **Study Notes.**
4. **Which existing flows carry over first:**
   - consent;
   - the baseline check and results;
   - the playlist and feed, the player;
   - the check before a lecture, My Levels;
   - the questionnaires, the demo menu.
5. **Data on the phone:** AsyncStorage vs SecureStore, and the mock until the Phase 1 backend.
6. **Branch order:**
   - Expo shell and shared core package;
   - then the screens;
   - the Phase 1 backend is separate.

## Carried over from the framework discussion

- **Sign-in (Phase 1):** a token in secure storage, not the cookie of UI plan §9.3. The email sign-in link must open
  the app (universal links / app links).
- **iOS distribution:** an Apple Developer account ($99/year). TestFlight external testing needs a one-time beta
  review, and **builds expire after 90 days**, so the semester needs at least one new build.
- **Real data must live on the backend** (Phase 1); the phone only caches it.

## Parked (not part of this)

- **Condition B and retention/transfer quizzes** (study design): `plan/condition-b-plan.md`.
- **Phase 1 backend** (FastAPI, Mongo, auth, event ingest, video job wiring): after or alongside, separate branch.
