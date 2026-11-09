# SyllaByte server

Sign-in, one saved state per student, and the shared app rules (`packages/core`) running on the server.
Plan and status: `plan/backend-plan.md`.

```bash
npm install
npm test                 # 76 tests, no network
npm run allowlist -- add you@nyu.edu researcher     # or: npm run allowlist -- students.csv
npm run dev              # http://localhost:8788; sign-in codes are printed in this terminal
```

Environment (all optional in development):

| Variable | Meaning |
|---|---|
| `PORT` | default 8788 |
| `SYLLABYTE_DB` | database file, default `data/syllabyte.db` |
| `SYLLABYTE_SECRET` | signs sign-in codes; required when `NODE_ENV=production` |
| `RESEND_API_KEY`, `MAIL_FROM` | send sign-in links by email (Resend); without a key emails are logged locally |
| `SYLLABYTE_PUBLIC_URL` | HTTPS API address used in sign-in emails; required in production; development uses the request's origin |
| `SYLLABYTE_AUTH_REDIRECT_URLS` | additional exact app/web return URLs, comma-separated; `syllabyte://signin` is always registered |
| `SYLLABYTE_SEMESTER_START` | ISO date; week 1 for new students |
| `SYLLABYTE_CORS_ORIGIN` | let a browser at this origin call the API (the phone app doesn't need it); development only |
| `SYLLABYTE_FILES` | where uploaded syllabi and slides are kept, default `data/files` |
| `SYLLABYTE_WORKER_TOKEN` | the upload worker's secret; without it the worker routes are off and uploads are never processed |

Endpoints (all under `/api`): `POST auth/request-code`, `POST auth/verify`, `GET session`, `POST session/logout`,
`POST rpc/<method>` (`{ "args": [...] }`; any method of the core's `Api`), `POST events`, `GET research/study.csv`
(researchers), `GET health`. Send `Authorization: Bearer <token>`, and `X-Visit: <id of this app launch>` so the
"next session" cap counts per visit.

## Email-link sign-in

The mobile app requests `POST auth/request-link` with `{email, redirectUrl, intent}`, where `intent` is `signup` or
`signin` (the default for older clients). Sign up sends a verification link to a new email and creates a student
account only when `POST auth/verify-link` redeems the ticket. Sign in sends links only to existing/invited accounts.
Responses do not reveal whether an account exists. Repeating sign up for an existing account preserves its identity
and role; removed accounts cannot restore their access through signup. There is no code entry.
Links expire after 10 minutes, work once, and are stored as hashes.
The browser landing page does not consume the ticket, so mail scanners cannot invalidate it by following the link.
Existing accounts, course progress, and session tokens are preserved. The older code endpoints remain for old clients.
Public sign-ups have `study_participant: false` in their session and are not automatically recorded as consenting
research participants. Existing invited users keep their prior study enrollment. Database upgrades preserve existing
users and pending sign-in links.

For local email delivery, copy `.env.example` to `.env` in `apps/server`, set `RESEND_API_KEY` and `MAIL_FROM`, and
restart the backend. The `.env` file is ignored by Git and loaded automatically. Do not put the key in the mobile app.
With Expo Go, the app creates an `exp://<Metro-host>:<port>/--/signin` return URL. Development accepts it only when
Metro and the API use the same hostname/IP; open Metro using the same LAN address as `EXPO_PUBLIC_API_BASE`.
Installed builds use the existing `syllabyte` URL scheme. The email opens a page with an "Open SyllaByte" button.
Keep the API and Metro running during local phone testing.

Production must set `SYLLABYTE_PUBLIC_URL=https://api.syllabyte.app`. Expo Go return URLs are disabled in production;
register any web sign-in URL explicitly with `SYLLABYTE_AUTH_REDIRECT_URLS`. Native installed builds need no Google
OAuth setup or extra dependencies.

Uploads: `GET courses/mine`, `POST courses` (multipart `syllabus` and optional `slides`),
`POST courses/:id/slides` (multipart `files`), `GET courses/:id/uploads`, and `POST research/jobs/:id/retry`
(researchers). `POST courses/:id/uploads/confirm` remains available to older clients; normal uploads proceed
automatically. The worker
(with `Authorization: Bearer $SYLLABYTE_WORKER_TOKEN`): `POST worker/claim`, `GET worker/jobs/:id/file`,
`POST worker/jobs/:id/syllabus-key`, `POST worker/jobs/:id/result`, `POST worker/jobs/:id/fail`.

## Uploaded courses and the worker

A student's syllabus creates their course, or joins the course of anyone whose syllabus has the same text; their slide
files are organized into lectures automatically. The initial upload saves the syllabus and optional slides together,
so processing continues if the app closes. The worker uses the syllabus topics and slide content to order decks, then
queues analysis without a review or confirmation step. If placement fails twice, decks are appended in upload order
and analysis continues. `courses/mine` reports `slides_pending` while reading and organization are in progress,
including before the first lecture exists. The Python worker reads and processes them (LLM calls: the lecture list once per
course, then each new deck's KUs and questions), claiming jobs from this server. Until it has a host of its own it runs
on a laptop, from the repository root:

```bash
SYLLABYTE_WORKER_TOKEN=... uv run python -m ingestion_agent.worker --server http://localhost:8788   # add --once to stop when the queue is empty
```

General workers, question-bank workers, and `--kinds video` run up to three jobs at once. Use `--concurrency N` to
choose another limit, including `--concurrency 1` for sequential generation. Other specialized workers default to one.
Restart an existing worker to apply a new concurrency setting. Paused jobs must be retried separately.

The mobile analyzer uses `GET courses/materials` to list the student's original syllabus and slide files, including
bundled slides before course creation. It queues separate `preview` jobs once per file. An updated worker renders
every PDF page to a small JPEG and sends `PUT worker/jobs/:id/pages/:page`, followed by
`POST worker/jobs/:id/preview` with its manifest. Images use signed, short-lived `material-previews/:fileId/:page`
links; only the uploader receives these links. Preview errors never fail the ingestion job.
Office files are rendered through LibreOffice when available; otherwise the analyzer shows the actual extracted
slide text or DOCX sections, labeled accordingly. Page cycling is a preview; status reports document-level processing.
Restart both backend and worker after upgrading. Older workers continue processing materials but do not claim
preview jobs. A worker with explicit `--kinds` must include `preview` (or use a separate `--kinds preview` worker).

The first teachable lecture starts preparing pre-check questions as soon as its KUs arrive. Opening a later check
prepares that lecture's bank too; the server does not automatically generate the whole semester. Each
`question_bank` job writes three independent questions for one KU (basic, applied, advanced) in one call, followed by
a joint critic review. A waiting student's KU is prioritized. Once saved, the adaptive selector chooses among those
questions without a model call between answers, and classmates reuse the same bank. Queued single-question jobs
covered by a bank are completed without duplicate generation. A missing/unseen question still has the on-demand
fallback. Old workers continue receiving only job kinds they support.

Pre-check questions have no hints. The writer and reviewer check for answer giveaways, mismatched tiers and
slide-specific trivia. Every question must have an explicit review verdict; unresolved flags prevent publication of
the entire bank, and flagged legacy questions are excluded. Retries remain bounded and failed attempts count toward
the worker's spending limit. A cold or failed bank can still require waiting; no latency benchmark is implied.

Questions may use standard CS/math symbols, equations, quantifiers and case-sensitive identifiers. Pre-check stems
allow up to 90 words of prose plus fenced code/data. The reviewer checks necessary assumptions, code semantics,
equivalent answer choices and genuine wording cues; formula length and absolute words alone are not rejection rules.
Clients show Unicode/plain-text math and preserve inline/fenced code. They do not typeset LaTeX. Restart workers to
apply the new writing rules; existing approved banks are reused rather than automatically regenerated.

Restart the backend and worker to use the new jobs. To prepare banks without starting videos, run from the root:

```bash
SYLLABYTE_WORKER_TOKEN=... .venv/bin/python -m ingestion_agent.worker --server http://localhost:8788 --kinds question_bank,question
```

For uploaded courses, answering a new KU's precheck question settles its level and immediately requests its video.
The worker can generate it while the student answers the remaining questions. That KU is not asked again in the same
check, and its level stays fixed through the end of that check. KUs not asked about receive levels and video requests
when the check finishes. Question jobs take priority over video jobs when the worker claims its next job.

PowerPoint files need LibreOffice (`soffice`) on the worker's machine. Students never reorganize a course; the
researcher fixes mistakes:

```bash
npm run courses -- list                                 # every course, its students and decks
npm run courses -- show <course>                        # lectures, decks, updated versions, failed jobs
npm run courses -- rename <course> <n> "<title>"
npm run courses -- add-lecture <course> "<title>"
npm run courses -- move-deck <deck> <n>
npm run courses -- move-student <code|email> <course>   # before they have answered anything
npm run courses -- merge <from-course> <into-course>    # its students and its syllabus join the other course
npm run courses -- retry <job>
```

## Running the phone against it

```bash
# terminal 1
npm run allowlist -- add you@nyu.edu student && npm run dev
# terminal 2 (apps/mobile): the simulator reaches the server at localhost; a phone on Wi-Fi uses EXPO_PUBLIC_USE_SERVER=1
EXPO_PUBLIC_API_BASE=http://localhost:8788 npx expo start --ios
```
The sign-in code appears in terminal 1. See `apps/mobile/src/data/backend.ts` for the switch.

## Deploying (DigitalOcean droplet)

Files are in `deploy/`.

1. **Once, on a fresh Ubuntu 24.04 droplet:** `scp deploy/setup.sh root@<ip>:/root/ && ssh root@<ip> bash /root/setup.sh`.
   It installs Node 24 and Caddy, adds 1 GB of swap, creates the `syllabyte` user, a firewall (SSH, 80, 443),
   automatic security updates, and `/etc/syllabyte/env` with a random `SYLLABYTE_SECRET`.
2. **Each release, from your laptop:** `apps/server/deploy/deploy.sh root@<ip>`. It copies `apps/server` and
   `packages/core` (including the gitignored `fixtures/`, which the server needs), runs `npm ci`, restarts the service
   and checks `/api/health`.
3. **Allowlist a student:** `ssh root@<ip>`, then `cd /opt/syllabyte/apps/server && set -a && . /etc/syllabyte/env && set +a &&
   sudo -u syllabyte -E env HOME=/var/lib/syllabyte npm run allowlist -- add student@nyu.edu`.
4. **Logs:** `journalctl -u syllabyte -f`. In test mode (no `RESEND_API_KEY`) the sign-in codes appear there.
5. **Database:** `/var/lib/syllabyte/syllabyte.db` (plus `-wal` and `-shm` files while running).

The server is at **https://api.syllabyte.app** (Cloudflare DNS `A` record `api` -> the droplet, "DNS only"; Caddy gets
the certificate by itself). It is still in test mode: with no `RESEND_API_KEY` the sign-in codes are printed in the log.
For real students set `NODE_ENV=production`, `RESEND_API_KEY` and `MAIL_FROM` in `/etc/syllabyte/env`.

## Facilitator: moving a student's study clock

The study runs over weeks, and the phone's demo menu is hidden when a server is configured, so the facilitator moves a
test student's clock from the server instead. It only moves forward (recorded times must stay in order), never touches
other students, survives restarts, and a student cannot set it. `reset` exists for test accounts.

On the droplet (same environment as the allowlist command above):

```
npm run facilitator -- list                    # every participant code, its clock offset
npm run facilitator -- advance S-ABCDE 7       # a week later: the next lecture check is due
npm run facilitator -- module S-ABCDE 1        # just past module 1's last lecture week: its questionnaire is due
npm run facilitator -- reset S-ABCDE           # back to real time (test accounts only)
```

Researchers can do the same over HTTP: `POST /api/research/clock` with `{ participant_code, days }`, `{ participant_code,
module }`, `{ participant_code, reset: true }`, or just `{ participant_code }` to read it. Anyone not on the allowlist as
a `researcher` gets 403.
