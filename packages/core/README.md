# @syllabyte/core

The app logic both front ends run: `apps/web` (the Next.js prototype) and `apps/mobile` (the Expo app). Plain
TypeScript with no build step and no browser or React Native APIs; each app bundles the sources it imports.

```
src/types.ts            types shared by fixtures, state and views (mirrors packages/common/.../learner.py)
src/api/types.ts        THE contract: every method a screen may call (plan §6.1)
src/api/mock.ts         Phase 0 implementation of that contract, on top of src/store.ts
src/api/client.ts       `api`, the only thing screens call. Phase 1 swaps it for a fetch client
src/api/demo.ts         facilitator controls (reset, simulate a day or week, scripted students)
src/api/persona.ts      the scripted students, built by running the real API with a backdated clock
src/store.ts            the state document, saved through a StorageAdapter each app provides
src/events.ts           one event shape and vocabulary (plan §6.2); each app sets the screen/device context
src/logic/              pure rules: cat.ts (the adaptive-test engine, a port of the Python one), kuProfile,
                        assessment, lectures, prereq, engagement, playlist, nextSession, calibration, receipt, …
src/content/            the questionnaires, and consent.md (placeholder: replace with the IRB-approved wording)
src/fixtures.ts         the course, items and videos from fixtures/ (gitignored, see below)
tests/                  Vitest; fixtures/cat-parity.json is the Python engine's golden sessions
```

## Use it from an app

Each app depends on it as `"@syllabyte/core": "file:../../packages/core"` and imports by path, e.g.
`import { api } from "@syllabyte/core/api/client"`. The app supplies:

- **storage:** `hydrate(adapter)` from `src/store.ts` with `load`, `save` and `visitId` (localStorage and a
  session id on the web; AsyncStorage and one id per launch on the phone). Until then state lives in memory.
- **event context:** `setEventEnv({ screen, device, orientation })` from `src/events.ts`.
- **bundler access** to this folder: `transpilePackages` and `turbopack.root` in `apps/web/next.config.ts`,
  `watchFolders` in `apps/mobile/metro.config.js`.

## Fixtures

`fixtures/{course,items,bank,videos,slides}.json` come from the course's own slides, so they are gitignored. From the
repo root:

```bash
uv run python scripts/build_ui_fixtures.py --run runs/dev   # writes packages/core/fixtures/
uv run python scripts/build_item_bank.py                     # the per-KU bank; spends LLM credits unless cached
```

Without them, the tests that need them skip, and the apps won't build.

## Test

```bash
npm install
npm test            # Vitest: rules, the store, and the mock API against the real fixtures
npm run typecheck   # no DOM types, so a browser API can't slip in
npm run consent     # regenerate src/content/consent.ts from consent.md (apps/web does this before dev/build)
```
