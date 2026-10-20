# Backend (Phase 1): plan and status

Status: **slices 1 and 2 built** on branch `backend` (2026-10-19): `apps/server`, and the phone can use it.

## Decided (2026-10-18)

- **A TypeScript server that runs the shared core, not FastAPI + Mongo** (plan/ui-ux-implementation-plan.md §6, §9
  predate `packages/core`). The adaptive test, levels, playlist and the rest (about 2,700 lines) already exist in
  `packages/core` and are tested; porting them to Python would mean two copies of the study's rules that must be kept
  in step. The server calls the same `mockApi`, so the web demo, the phone and the server can never disagree.
  The Python video pipeline stays as it is; the plan's `POST /admin/variants` registration (§7.6) is still to come.
- **SQLite** (Node's built-in `node:sqlite`, one file in WAL mode, nightly copy to off-machine storage) instead of Mongo: a pilot is a
  few dozen students, each with one saved document, and there is nothing else to run. Behind `src/db.ts` and
  `StateRunner`, so Postgres or Mongo can replace it later without touching the rules.
- **The server is authoritative.** The phone's `Api` becomes HTTP calls: `POST /api/rpc/<method>` with `{ args }`.
  Each call loads that student's state document into the core store, runs the method, and saves the document if it
  changed. Requests are queued one at a time (the core's store is one module-level document), so two students never
  see each other's state. A test breaks if the queue is removed.
- **Sign-in by emailed code, not a link** (changes plan §9.3): a 6-character code, single use, 10 minutes, 5 guesses,
  5 codes an hour per address; the app then keeps a 90-day session token (SecureStore). A code needs no
  universal-link / app-link setup and works the same on iOS and Android. Only allowlisted emails can sign in, and the
  server answers the same for everyone. Taking an email off the allowlist ends its sessions.
- **Research data is keyed by a pseudonym** (`S-XXXXX`, assigned at first sign-in). The email-to-code link lives only
  in the `users` table. Exports use the code and never contain an email.
- **Hosting (2026-10-19): DigitalOcean for the server, Cloudflare R2 for videos and slides.** One droplet (Node 24,
  systemd, Caddy for HTTPS) with the SQLite file on its disk, droplet backups on, plus a nightly copy off the machine.
  R2 has a free tier and no download fees, so video traffic cannot cause a surprise bill; the server hands the phone
  signed R2 links. Nothing provider-specific is used (plain Node, the S3 protocol), so moving to AWS or Google Cloud
  later is a copy of the database file and a bucket. The real scaling step is SQLite to Postgres, not the host.
  Ask the IRB / NYU IT whether student emails must stay in an NYU-approved or particular-region service; that would
  override this choice.
- The researcher CSV (`GET /api/research/study.csv`) covers every participant who consented, researchers only;
  the per-student `exportStudyCsv` method is not callable over HTTP.

## Built (slice 1)

`apps/server` (see its README): sign-in and sessions, the allowlist script, per-student saved state, the `Api` over
HTTP, batched event ingest (`POST /api/events`, logged through the core's `track` so each event carries the server's
condition, week and code), the researcher CSV. 20 tests, including a whole baseline run on the server.

## Built (slice 2): the phone uses it

- `packages/core/src/api/remote.ts`: `createBackend` (the `Api` over `/api/rpc`, plus sign-in calls) and an event queue
  (batches of 20 or after 4 s, a failed batch is kept). `api/client.ts` now has `setApi`, so one line swaps the mock for
  the server; the web demo is unchanged.
- `apps/mobile`: a sign-in screen (email, then code), the session token in the keychain (`expo-secure-store`), a root
  gate (signed out: only the sign-in screen), a "can't reach the server" banner with "Try again", and screens refetching
  after every call that changes data. UI events (`track`) go to the server in batches instead of the phone.
- **Switch (`apps/mobile/src/data/backend.ts`):** `EXPO_PUBLIC_API_BASE=https://…` uses that server;
  `EXPO_PUBLIC_USE_SERVER=1` uses the server on the Metro machine (port 8788); neither: the app runs on its own mock, so
  UI work needs no server. The old on-phone test data is simply not used (decided 2026-10-19).
- With the server there is no offline mode (decided 2026-10-19): a failed call shows the banner. Sign out clears this
  phone's settings only; the student's data stays on the server for their next sign-in.
- The facilitator's demo menu (long-press the name: simulate next day / week) is hidden with the server: it moved the
  phone's own clock. A server-side facilitator tool for testing the study timeline is still to do.
- Checked end to end in the web build against a running server: sign-in, a reload keeping the session, the whole
  baseline (12 answers, a reload in the middle resumed at the right question), the stored state, and the unreachable-server
  message. Not checked: typing on the iOS simulator (no tap tool) and a real phone.

## Deployed for testing (2026-10-19)

DigitalOcean droplet `134.209.54.77` (San Francisco SFO2, Ubuntu 24.04, 1 GB, weekly backups): Node 24, Caddy on
port 80, the server under systemd, a firewall (SSH/80/443), swap, automatic security updates. Files: `apps/server/deploy/`
(see the README). The domain `syllabyte.app` is bought (Cloudflare, $8.20 the first year, $14.20 a year to renew,
auto-renew off) and the server answers at **https://api.syllabyte.app** with a valid certificate.
**Still test mode:** sign-in codes are printed to the log, not emailed. Still needed for real students: Resend (its
DNS records go on `syllabyte.app`) and the key in `/etc/syllabyte/env` with `NODE_ENV=production`, the nightly
database copy to R2 (skipped for testing: only the weekly droplet backups exist, which can lose a week of answers), and the professor's OK to host the course content (the server holds the slides' text and the
question bank, the same files the phone app bundles).

## Next slices

1. ~~Facilitator tool~~ **built (2026-10-20):** `npm run facilitator` on the server and `POST /api/research/clock`
   (see the server README). Still open: whether the phone's local-only `setupDone` (first-run screens) should live on
   the server.
2. **Videos and slides from storage:** serve rendered videos by signed URL (replaces `npm run media`); `POST
   /admin/variants` for the pipeline. Blocked on the professor's OK to host course material (plan §15.1).
3. **Deployment:** one DigitalOcean droplet, Caddy for HTTPS, nightly database copy off the machine,
   `SYLLABYTE_SECRET` and `RESEND_API_KEY` set (Resend needs a domain with DNS records); videos in a Cloudflare R2
   bucket.
4. **Hardening:** the account-deletion / withdrawal paths (IRB), rate limits by IP, the event log moved out of the
   state document once it is large, instructor endpoints (§6.1).

## Needs advisor / IRB sign-off

- **Where the students are (2026-10-20):** they may be at NYU Abu Dhabi, not in the US. The droplet is in San Francisco
  (about 200-250 ms from the UAE, so every tap would lag). **Once the location is confirmed, move the server to
  Bangalore (BLR1) or Frankfurt (FRA1):** a new droplet, `setup.sh`, `deploy.sh`, then repoint the `api` DNS record
  (an hour's work while there is no real data). Also ask NYUAD's IT/IRB whether student emails and responses may be
  stored in India or Europe (DigitalOcean has no UAE region; the UAE has its own data-protection law). R2's automatic
  location pick (Eastern Europe) already suits the UAE.

- The server stores identifiable accounts (email) next to pseudonymous research data. Who may see the `users` table,
  and how long it is kept, is an IRB question.
- Course start date for the study clock: set `SYLLABYTE_SEMESTER_START`.
