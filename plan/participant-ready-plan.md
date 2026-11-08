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
