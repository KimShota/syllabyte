# Participant-ready: plan

Branch `participant-ready` (from `main` at a7166a2). Goal (2026-11-08): the app works end to end on a real course, then is
deployed for real participants. Findings below were read from the code on 2026-11-08, not assumed.

## What is connected today

- App to server (`EXPO_PUBLIC_USE_SERVER=1`): sign-in by emailed code, the course, its lectures, the questions. Seen working
  on a copy of `runs/ml-trial` (23 lectures, 11 questions, student `trial-ann@nyu.edu`).
- Upload worker to server (`ingestion_agent.worker`, claims `/api/worker/claim`): kinds `syllabus`, `deck_read`,
  `placement`, `deck`, `question`, `link_pass` (`apps/server/src/db.ts`, the `jobs` CHECK).
- The server records the videos a student needs: `video_requests` rows, status `waiting` (17 for the ML trial course).

## What is missing, verified

1. **Nothing makes a waiting video.** There is no `video` job kind and no worker route for one. `scripts/video_jobs.py` keeps
   its own file-based `VideoStore` (`syllabyte_common/video_jobs.py`) and never talks to the server.
2. **The server's course has no videos.** `assembleCourse` returns `videos: []` (`packages/core/src/logic/assemble.ts:134`), so
   a rendered video would not appear in the app.
3. **A video is more than an mp4.** A `Video` (`packages/core/src/types.ts:201`) carries segment spans, a checkpoint
   (`item_id`), next-session and prove-it item ids, a sentence frame, one claim per deliver/end segment, a tailoring
   skeleton, a transcript, poster and VTT urls. Today `build_ui_fixtures.py` makes these: poster, VTT, spans, transcript
   with no LLM (`animation_agent/ui_manifest.py`); items, frame and claims with an LLM grounded in the cited slides and checked
   by a critic pass. It only runs over a finished `runs/dev`-shaped folder.
4. **Videos reach the app from a local script.** `mediaUrl` (`apps/mobile/src/data/media.ts`) points at `npm run media`, which
   serves `apps/web/public`. `EXPO_PUBLIC_MEDIA_BASE` can point elsewhere.
5. **Not yet confirmed:** how `made[ku_id]` is set when the server, not the mock, owns a student's state
   (`packages/core/src/api/mock.ts:125-139` does it for the mock).

## Steps that need nothing from outside

| # | Step |
|---|---|
| S1 | Server: a `video` job kind and a `videos` table (course, KU, level, content key, status, manifest, file names). A worker claims a waiting `video_requests` row, one job per (course, KU, level), shared by every student with that course (U8). |
| S2 | Worker: a handler that runs `make_ku_video` for the job, builds the UI manifest, and writes the per-video items, frame and claims (reusing `build_ui_fixtures.py`'s generation, cached), then posts the files and the manifest. |
| S3 | Server and core: `assembleCourse` includes ready videos; a student's `made` level is recorded when a video is served to them; the app plays it. |
| S4 | Media: serve files from the server (range requests, iOS needs them) behind the student's sign-in; signed URLs once storage is R2. |
| S5 | End to end on a copy of `runs/ml-trial`: upload, worker, the 17 videos, play in the simulator. Spend: the videos are about $0.17 each in model calls (measured 2026-11-07) plus the per-video items, so roughly $3-4 in all. |

## Steps that need the researcher (not mine to do or decide)

- **The professor's OK to host the course material** (`plan/backend-plan.md` §15.1): until then nothing goes on a public host.
- **Credentials:** DigitalOcean (a droplet was set up for testing 2026-10-19), a Cloudflare R2 bucket, and a Resend domain with
  its DNS records so sign-in codes reach real inboxes.
- **Apple:** a Developer account ($99/year) and a TestFlight beta; external testers need Apple's one-time beta review
  (`plan/mobile-app-plan.md`).
- **Backups:** the nightly database copy to R2 was skipped for testing; before participants answer anything it must exist
  (the weekly droplet backups can lose a week of answers).
- **Who the participants are:** the allowlist (`npm run allowlist` in `apps/server`), consent as the app records it, and the
  pilot course.
- **Quality bar:** videos run about 100 s against the under-a-minute target, and none pass all four critic scores at 7
  (see `plan/one-shot-storyboard-plan.md`). Whether that is good enough for participants is a study decision.
- **Several courses per student** is deferred to its own plan (U4); the server refuses a second syllabus (409). Not part
  of this branch.

## Status 2026-11-08: S1-S5 built and run on a copy of the ML trial course

**Built.** A `video` job kind and `videos` table (apps/server: db.ts, uploads.ts, courses.ts, app.ts); the worker's video job
(ingestion_agent/video_job.py, worker.py) over the existing pipeline, with its app data in
assessment_agent/video_app_data.py (moved out of scripts/build_ui_fixtures.py, which now imports it: the five fixture files
rebuilt from the cache are byte-identical); each student's course carries the video made at their own level, from their
saved levels and `made` (D15), with links signed per video for 12 hours and a range-capable media route; core's
`syncPlaylistWithVideos`, run by the server before each request, because a playlist is saved state and a video arriving
later never joined it (found by a test, not by reading); the phone loads each made video's details (`getVariant`), builds
its KUs from them, and keeps looking every 10 s while videos are pending, rebuilding only when something visible changed.
Worker options `--max-jobs` and `--budget-usd`. Tests: Python 474, server 95 (a Python-written golden result is posted
through the real routes), core 251, mobile 31.

**Run.** All 17 waiting requests of the ML trial course were made by one worker on this Mac: 17 ready, 0 failed. One job
failed once on a model output that did not fit its schema and passed on the server's retry. Videos run 107-132 s
(mean about 2 minutes), 540x960, about 2 MB each. The trial student's playlist, the roadmap ("Next: What Is ML?") and the
player show and play them from the server: full GET 200, range 206, a tampered signature 403.

**Cost.** $4.66 for the 17 (median $0.19; $0.15-0.61, the dearest needing 22-27 model calls), against the $3-4 projected
from the first video ($0.233). My budget stop only checks before a job starts, with three at once, so it overshot. Use a
lower `--budget-usd` than the ceiling, or `--concurrency 1`, next time.

**Found along the way.** (1) The app rebuilt the whole course on every refresh, harmless while an uploaded course had no
playable video; with videos pending it polled every 4 s, and the player hopped between videos by itself. The two fixes
above removed it in two clean runs (all videos ready; a video landing mid-play), but one run after the fix that hopped
was on a session hot-reloaded several times, so the exact cause is not proven. (2) A KU whose request ends `failed` is not
counted as pending, so the student sees "drafting from slides" until the researcher retries the job
(`POST /api/research/jobs/:id/retry`). (3) The player deep link only works once the student's baseline is done.

**Still needs the researcher** (unchanged above), and for hosting: a host for the worker with Manim, LaTeX, ffmpeg and the voice
engine (it runs on a laptop today), `--kinds video` as its own worker so decks and checks are not held behind videos, and
a decision on whether videos stay on the server's disk (about 2 MB each, fine for a pilot) or move to R2. Open on the
product side: videos are about twice the under-a-minute target, and none passed all four critic scores at 7.
