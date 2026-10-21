# Slide uploads (all at once, or lecture by lecture): plan

Branch: `slide-uploads` (from `main` at a09aa7b). Status: **decisions settled (2026-10-20); steps 1–7 built the same
day (see "Built" at the end). A paid trial on L1–L3 of a real course (2026-10-20) led to the revision below
(2026-10-21), which replaces U1, U2, U9, U10, U12 and parts of U11 and U13. The revision is built (steps 1-5 below);
L4-L23 of the real course wait for approval.**

## Revision (2026-10-21)

**What the trial showed** (CS-UH 3253 Machine Learning: syllabus + 23 image-only PDF decks):
- **The syllabus schedule drifts from what was taught after lecture 6** ("L7 - Classification (contd)…" is the
  syllabus's lecture 7 "Clustering"; "L12 - Midterm Review" is not in the syllabus). Placing decks in the syllabus's
  slots by the file name's number put 16 of 23 decks under the wrong title, marked sure.
- **Neither file names nor covers can be relied on.** Every deck's cover is the same ("Machine Learning · Saurabh
  Ray"), with no number or title; a file may be called `slides.pdf`.
- **KUs and questions were good:** 17/7/10 KUs for L1–L3, cross-lecture prerequisites, every KU citing slides;
  102 questions with answers balanced 34/34/34. $1.88 for three decks with Sonnet. One KU extraction was cut off at
  max_tokens and passed on its retry (now: a higher limit, and a cut-off response is reported as such and costed).
- **Most of the bank is never asked:** a check asked 4 questions per lecture, so L1's 51 questions would give one
  student about 6. With students worldwide, most courses have one student and nothing is shared.

| # | Decision (2026-10-21) | Replaces |
|---|---|---|
| V1 | **The decks are the lectures, in teaching order.** A **reader** (one cheap model call per deck, Sonnet) looks at the deck's content pages (a generic cover is skipped) and writes its title and a short summary of what it teaches. A **placement** call then orders the new decks among themselves and among the course's lectures, from those summaries, the syllabus's topics and the lectures already in the course. The file name is only a hint. The first uploader sees the suggested titles and order on the review screen, can fix them, and confirms. | U2, U13's file-name suggestion |
| V2 | **One deck is one lecture.** Each new deck becomes its own lecture, normally the next one, earlier when its content clearly comes before an existing lecture. **An updated version** (most of its pages match a deck already in the course) is not processed: it is logged, and the student is told the slides are already in. No question about it is asked. | U1, U10, U12 |
| V3 | **Only real lectures are shown.** The syllabus gives the course's name and code and topic hints for V1; its schedule is not a lecture list. The "Your lectures" setup screen goes; the app shows "N lectures so far" and an "Add the next lecture's slides" card. | U2, U11's lecture-list confirmation |
| V4 | **Questions are written on demand** for a (KU, level), checked by the critic, and **saved** by the course's deck, so a later student with the same slides reuses the saved questions they have not answered before anything new is written. The next question is prepared while the student answers the current one. Questions already written (the trial's L1–L3) are kept as saved questions. Video checkpoint questions are written with the video. | The full 3-per-KU bank at processing |
| V5 | **A precheck asks up to 10 questions on the lecture** (fewer when it has fewer KUs) **plus 2 review questions**, under the existing assessment rules (fixed length; "Not sure" counts toward the length, not the estimate; nothing asked twice; review goes to the least certain earlier lecture). Each question goes to the KU with the fewest answers from this student, ties to the KU that most later KUs build on, so important KUs come first and coverage spreads across the lecture. Its difficulty follows the student's current estimate for that lecture. | 4 + 2 (D8) |
| V6 | **No separate baseline.** The first sitting is lecture 1's precheck; every lecture has its own precheck before its videos. Lectures not yet checked take a provisional level from everything answered so far (as today). | Week 0 baseline (D8, U9) |

**Defaults taken (2026-10-21):** lecture ids stay stable when a deck is placed before an existing lecture (only the
order changes, so recorded answers, levels and videos keep pointing at the right lecture); a lecture's first precheck
question is written when its precheck card appears; when a question can't be written the student sees "Try again",
and after repeated failures the sitting ends with the answers given; the demo course keeps its fixtures and
baseline (its bank is complete), uploaded courses follow V4–V6.

**Cost per course with one student** (estimate from the trial): KU extraction ≈ $0.15 per deck, the reader and
placement ≈ $0.02 per deck, questions ≈ $0.025 each as asked (≈ 12 per lecture). The ML course: ≈ $4 KUs + ≈ $7
questions over a semester, against ≈ $9 + KUs for the full bank; a second student with the same slides adds only the
questions nobody has written yet.

**Needs advisor sign-off (added):** dropping the Week 0 baseline (V6); longer prechecks (V5); questions written on
demand instead of a bank reviewed in advance (V4: the critic still checks each one, but no person sees it before the
student does). All stay inside the proposal's "a CAT before any video, per-KU readiness".

**Build order (revision):**
1. LLM call: a cut-off response is reported and costed (done); KU extraction max_tokens 32000 (done).
2. Core: lecture order separate from lecture number (`position`); V5 precheck length and KU choice; V6 (uploaded
   courses have no baseline); V4 selection that names the (KU, level) it needs when no saved question fits, and a
   "preparing" state for the sitting.
3. Python: the reader in the deck-read job; the placement job; the question job (one question, with critic); the deck
   job without the bank; page keys for V2.
4. Server: lectures created from confirmed decks with a position; placement jobs; review and confirm with titles and
   order; updated-version detection; question jobs queued from what the student's sitting needs, with priority over
   deck jobs; the lecture-list routes removed.
5. App: no lecture-list screen; the review screen with titles and order; "Writing your next question…" in a sitting;
   the course without syllabus slots.
6. Checked with the stubbed worker end to end, then L4–L23 of the ML course for real (asks first).

**Built (2026-10-21):** steps 1–5, one commit each. Checked: core 249 tests, server 77, Python 185 (+1 skipped
without LibreOffice), phone 21 + typecheck + lint, web e2e 108 (the demo course is unchanged). End to end in the
phone's web build against the real server and the real Python worker (LLM stubbed): syllabus and three decks picked
out of order with meaningless file names, the review screen's suggested order with the unsure deck flagged, a deck
moved and a lecture renamed, processing in the confirmed order, Home offering lecture 1's check first (no baseline),
"Writing your next question…" while a question is written, then the question.
Where the build differs from the text above:
- **The reader skips decks the course already has** (the server sends the course's content keys), so a classmate's
  copy costs nothing.
- **The placement call runs once all of a student's files are read**; if it fails, the new decks go after the last
  lecture, marked to check.
- **A KU's tier difficulties** come from a `difficulty` the extraction now rates (as the bank's `ku_difficulty` did);
  the estimate's range includes the questions not yet written, so a strong student can reach the advanced tier
  before an advanced question exists.
- **The likely next question** assumes the likelier answer at the lecture's ability; a second worker started with
  `--kinds question` keeps checks moving during a long deck job.
- **One worker can run several jobs at once** (`--concurrency N`, threads): reads, placement and questions run side
  by side; deck jobs stay in lecture order because the server hands out a deck only after the earlier ones.
- **The researcher's tools:** `move-lecture <course> <n> <after>` replaces `add-lecture` and `move-deck`.
- **Caps are configurable** by `SYLLABYTE_DECKS_PER_COURSE`, `SYLLABYTE_MAX_FILE_MB`, `SYLLABYTE_NEW_DECKS_PER_DAY`.
- **The trial course** (`runs/ml-trial`) was migrated: its 20 empty syllabus lectures removed, the syllabus's
  schedule kept as topics, the 102 questions already written kept as saved questions (backup: `db.before-v4.sqlite`).

## Why

The mentor asked (2026-10-20): "Is there a way we can handle both cases? (i) the student can upload slides later during
the semester, (ii) also at the same time, the system supports the case where all slides are uploaded from the
beginning." Students upload their own course materials (user, 2026-10-20).

## What exists today (facts, 2026-10-20)

- **Only "everything at once", and only on the laptop.** `scripts/generate_shorts.py` takes `--syllabus` and every deck
  (`--slides a.pdf b.pdf …`) in one run. Adding a deck to a run does not work: the KU stage is skipped when `kus.json`
  exists (`generate_shorts.py:254`), and forcing it (`--from-stage extract_kus`) re-extracts every deck, which can change
  KU ids that students' levels, history and notes point at.
- **KU extraction is per deck** (`ku_extractor.py:56`, one Claude call each, syllabus text as context), but
  prerequisites may only name KUs **of the same deck** (the prompt), so links across lectures are lost even today.
- **PPTX decks are always extracted from text only**: even after LibreOffice converts one to PDF, `ku_extractor.py:73`
  falls back to text because `deck.source_path` is still the `.pptx`.
- **There is no lecture list from data.** The dev course is one 34-slide deck split into 3 invented lectures
  (`build_ui_fixtures.py:98`, an author decision); a core `Lecture` is a slide range (`slide_start`/`slide_end`) of that
  deck. KU short titles are hand-written (`SHORT_TITLES`). The syllabus parser returns text and headings only.
- **The course is built into the code.** `packages/core/src/fixtures.ts` imports the gitignored JSON fixtures
  statically as `FIX`; about 50 references across the core's mock API, the server's clock and the phone's
  `data/course.ts`. One course per student throughout.
- **The app's uploads are UI only.** `welcome.tsx` (syllabus + slides, picker accepts PDF/PPTX/KEY) and `UploadSheet.tsx`
  ("+ Upload Another Course") keep file names and open the mock `/analyzing` screen. The server has no upload route.
- **Video jobs exist** (`syllabyte_common/video_jobs.py`: `VideoStore`, content-keyed by slide content, KU, the
  prerequisites' titles, level and pipeline version; priority by playlist position). Wiring them to the app is step 5 of
  `per-student-video-plan.md`, waiting on the backend.
- **Adaptive tests keep one estimate per lecture** (`assessment.ts`, `kuProfile.ts:112`); the baseline covers the first
  `cat_week0_lectures` lectures (`week0Plan`). A lecture's videos are locked until its check is done.

## Decisions (2026-10-20)

| # | Decision |
|---|---|
| U1 | **A deck belongs to exactly one lecture; a lecture may have several decks** (part 1, part 2). A deck covering two lectures is placed in the first; there is no splitting. |
| U2 | **The lecture list comes from the syllabus:** one LLM call reads its schedule into a list of lectures (number, title, week if given). When the syllabus has no readable schedule, a lecture is created as each deck arrives, numbered by the uploader. |
| U3 | **One path for both cases.** "Everything at once" is N single-deck uploads, queued in lecture order. Every deck goes through the same "add a deck" job, which shows the model the syllabus and the KUs of the lectures before it, so prerequisites may point to **earlier** lectures. A processed deck never changes. |
| U4 | **Scope:** pipeline, data model, server and app. **Not in scope:** hosting the worker (until then a worker on the laptop polls the server for jobs), push notifications, several courses per student (its own plan, after this one). Every new table, call and event carries a `courseId` so that plan needs no migration. |
| U5 | **The syllabus comes first.** Creating a course needs the syllabus; slides are optional then and can be added at any time. (Each deck's KUs depend on the syllabus text, so a deck processed without it could never match one processed with it.) |
| U6 | **Shared course, keyed by the syllabus's text.** A student whose syllabus matches an existing one joins that course. Each deck is processed **once per shared course**; everyone who uploads it gets the same KUs and questions, and videos come from the same cache. |
| U7 | **Out-of-order decks are processed right away.** When an earlier lecture's deck arrives later, one extra LLM pass **adds** prerequisite links from the later lectures' KUs to the new ones. It never changes KU ids, titles or questions. Links point only from later lectures to earlier ones, so the graph cannot get a cycle. |
| U8 | **Videos already made keep being served.** The video cache key uses the prerequisites a KU had when its **first** video was made, so a link added later does not split the cache; only levels made after the link get the recap sentence. New links change "up next" ordering at once. |
| U9 | **The baseline waits for the first processed deck** and covers whichever of the first `cat_week0_lectures` lectures exist. With fewer bank items than `cat_week0_length` it is simply shorter. Until then the student sees the lecture list with "Waiting for slides" (the baseline gate does not apply while there is nothing to ask). |
| U10 | **A deck added to a lecture the student was already checked on takes that lecture's estimate:** levels at once, no new check. Its items join the bank and can be asked as review items in later checks. |
| U11 | **One structure for everyone.** The first student to create a shared course confirms or edits the lecture list; the first to upload a deck confirms or changes its suggested lecture. After that it is fixed: later uploads of the same deck are placed automatically, and only the researcher can change the list or move a deck. Students never reorganize, remove or hide anything (2026-10-20: "to not complicate it"). |
| U12 | **A different deck for a lecture that already has slides:** the uploader is asked "extra part, or an updated version of the same slides?" An extra part is processed (U10). An updated version is **not** processed: everyone keeps the existing KUs and videos, and the upload is logged for the researcher. |
| U13 | **One review screen for placing decks**, for one deck or many: each row shows the file and its suggested lecture ("week3_sorting.pdf → Lecture 3: Sorting"); unmatched decks are flagged at the top and must be placed; one "Confirm all". The "change" control appears only for decks the student is the first to upload (U11). |
| U14 | **Status in the app only:** a new lecture state, "Analyzing slides…", between "Waiting for slides" and ready. The app shows it on its next fetch (opening the course, pull to refresh, or after any call that changes data). Push notifications are a follow-up for the hosting plan. |
| U15 | **PDF and PPTX.** The worker converts PPTX to PDF with LibreOffice and uses that PDF everywhere (KU extraction sees the slides' visuals; content keys come from it). Keynote: "Export to PDF first." The picker stops offering `.key`. |
| U16 | **Caps, checked by the server, in config:** 30 decks per course, 25 MB per file, 15 **new** decks per student per day. A deck already processed in the shared course does not count. The researcher can raise any cap. |
| U17 | **Syllabus matching is exact after normalizing** (case, whitespace, punctuation, repeated page headers/footers and page numbers removed); anything else is a new course. The researcher can **merge** two shared courses while neither has a processed deck, or **point** a syllabus at an existing course. |
| U18 | **Videos are made per lecture, after the sitting that sets its levels:** the baseline for the lectures it covered, else that lecture's pre-lecture check; for a deck added under U10, as soon as it is processed. Only that student's levels are made (others come from the cache), first playlist video first. Nothing is made for the whole course up front. This sharpens D15/D16 of `per-ku-profiling-plan.md`: a lecture's provisional levels from the baseline never start generation. |
| U19 | **The course comes from the server**, not the app's built-in fixtures. |

Per lecture, for one student: **upload → processing → pre-lecture check → that student's videos.**

## Data model (server, SQLite)

New tables, all keyed by `course_id`:

- `courses`: id, `syllabus_key` (hash of the normalized text, unique), name/code read from the syllabus, the syllabus's
  text and file, `schedule_found` (U2), the creating user, created_at, `lecture_list_confirmed_at`.
- `course_members`: (course_id, user_id), joined_at. One course per user for now (U4), enforced in code, not in the schema.
- `lectures`: id, course_id, `n` (the canonical order), title, week (nullable), created_by (`syllabus` / `upload`).
- `decks`: id, course_id, lecture_id, `content_key` (hash of the converted PDF's per-page text and rendered images,
  unique per course), file name, file path, `status` (`queued` / `processing` / `ready` / `failed`), the first uploader,
  `placed_at`, error.
- `deck_uploads`: every upload by every student (user, file name, content_key, outcome: `new` / `existing` /
  `updated-version-logged` / `rejected-cap`). This is also the research log for U12.
- `jobs`: id, course_id, kind (`syllabus`, `deck`, `link_pass`), target id, status, attempts, worker id, claimed_at,
  result, error. Claimed by the worker over HTTP (below); two attempts, like `VideoStore`.
- KUs, items and the KU graph: stored per deck as the worker returns them (`kus`, `items` tables or one JSON column per
  deck; choose at build time). `kus.prereqs_at_first_video` is filled when a KU's first video job is created (U8).

Core types: `Lecture` loses `slide_start`/`slide_end` and gains `deck_ids`; `Video.source_slides` refers to a deck and its
slide numbers. KU ids are made unique within a course by the worker (the LLM's slug, suffixed on a clash).

## Processing (Python worker)

- **Syllabus job:** parse (existing parser), normalize, `syllabus_key`; one LLM call for the lecture list and the
  course's name/code (schema: `[{n, title, week?}]`, empty when no schedule is found).
- **Deck job:** PPTX → PDF (U15); parse; `content_key`; if the course already has that key, stop (shared). Otherwise KU
  extraction with: the syllabus text, the deck as a PDF block, and the **earlier lectures' KUs** (id, title, one-line
  summary) so prerequisites may name them (U3). The schema gains `short_title`, replacing the hand-written
  `SHORT_TITLES`. Then the item bank for the new KUs (`build_item_bank.py`'s generator, per deck), then, if any
  **later** lecture already has KUs, a `link_pass` job (U7).
- **Link pass:** one LLM call: "Which of these later KUs build on these earlier KUs?" Output: links to add. The server
  validates (both ids exist, later → earlier only) and adds them.
- **Worker loop:** `uv run python -m ingestion_agent.worker --server https://… --token …` claims a job
  (`POST /api/worker/claim`), downloads its inputs, runs it, posts the result (`POST /api/worker/jobs/:id/result`).
  A worker token (config) authorizes it. The laptop runs it until the hosting plan.
- **Course assembly:** the server builds the core's `Fixtures` (course, lectures, KUs with Bloom level and
  prerequisites, items, videos made so far) from the tables, per course. This replaces `build_ui_fixtures.py` for
  uploaded courses; the demo course keeps its fixtures.

## Server (TypeScript)

- `POST /api/courses` (multipart: syllabus): creates or joins a shared course (U6, U17); returns its id and whether the
  student is the first (and so confirms the lecture list).
- `PUT /api/courses/:id/lectures`: the first student's confirmation or edit (U11); refused after confirmation.
- `POST /api/courses/:id/decks` (multipart, one or more files): checks caps (U16) and type/size, stores files, parses
  nothing itself, and returns a **placement draft** per file: suggested lecture (from the file name and first-slide
  title against the lecture titles; the worker's parse refines it if the draft is unclear), `already_in_course`,
  `lecture_has_slides` (for U12).
- `POST /api/courses/:id/decks/confirm`: the review screen's "Confirm all" with each deck's lecture and, where asked,
  "extra part" / "updated version". Queues deck jobs in lecture order (U3).
- `GET /api/courses/:id`: the assembled course plus each lecture's state (`waiting` / `analyzing` / `ready` /
  `failed`). The `Api` methods (`/api/rpc/<method>`) load the student's state together with **their course's** fixtures.
- Researcher scripts (like `npm run facilitator`): edit a confirmed lecture list, move a deck, merge/point courses,
  list updated-version uploads, retry a failed job, raise caps.
- Events: `deck_uploaded`, `deck_confirmed`, `deck_ready`, `deck_failed`, `course_joined`, with the participant code.

## App (Expo)

- **Welcome:** the syllabus is required; slides optional ("You can add slides any time"). After the syllabus: the
  first student sees the lecture list to confirm or edit; a joining student sees it read-only.
- **Add slides:** an "Add slides" action on the course screen opens the picker (PDF/PPTX, several at once), then the
  review screen (U13). The extra-part / updated-version question appears in the row when it applies (U12).
- **Lecture states on the roadmap:** "Waiting for slides" (exists as `awaiting`), "Analyzing slides…", "Couldn't
  read these slides" (the researcher can retry), then the existing ones.
- **The baseline gate** (`_layout.tsx`) applies only once the course has bank items (U9).
- **Course data from the server:** `data/course.ts` reads the course from `GET /api/courses/:id` instead of `FIX`;
  placeholder data stays only for what the pipeline does not make (professor, term, exam).
- "+ Upload Another Course" stays hidden until the multi-course plan (U4).

## Assessment changes (core)

- `week0Plan` uses the lectures that have bank items (U9); its length is `min(cat_week0_length, items available)`.
- A KU in a lecture the student has an estimate for gets its level from that estimate when its deck lands (U10); the
  "What changed" card is not shown for new KUs (nothing changed for the student).
- `per-student-video` step 5 wiring uses U18's trigger: on the sitting that publishes a lecture's levels (or on a U10
  deck), queue that student's videos for the lecture, priority = playlist position.

## Build order

Each step its own commit, tests first where it is logic. No LLM spend without asking: tests use a stubbed `structured`.

1. **Core reads the course as data.** `Fixtures` is passed in (the mock API, persona, demo and the server's clock take it
   from a provider) instead of the static `FIX` import; the demo keeps its fixtures through the same provider.
   `Lecture.deck_ids`. All existing tests pass unchanged.
2. **Server tables and the course assembly** (`courses`, `course_members`, `lectures`, `decks`, `deck_uploads`, `jobs`,
   KUs/items), the fixtures builder, and `/api/rpc` loading the student's course. Tests: a course assembled from
   stored rows gives the same baseline as the dev fixtures.
3. **Pipeline jobs, offline:** syllabus job (normalize, key, lecture list), deck job (PPTX → PDF, content key, KU
   extraction with earlier KUs, `short_title`, unique ids, item bank), link pass. Tests with a stubbed LLM, including
   **the key property: uploading all decks at once and one at a time, in order, produce identical KUs, links and items.**
4. **Worker loop and the server's job API** (claim, result, retry, worker token). Test: a fake worker processes a queue.
5. **Upload API:** create/join a course, lecture-list confirmation, deck upload with caps, placement drafts, confirm,
   U12, lecture states, researcher scripts. Tests for each rule (first student only, caps, shared deck free, exact
   syllabus match).
6. **Assessment changes:** U9 baseline, U10 estimate, U18 video trigger (queues jobs in `VideoStore`; serving videos
   stays as today until backend slice 2).
7. **App:** welcome with required syllabus and lecture-list confirmation, "Add slides" and the review screen, lecture
   states, course from the server, gate change. Checked by Playwright on the web build against a local server and the
   laptop worker with the stubbed LLM.
8. **One real run (asks first, small spend):** the dev syllabus and decks uploaded once all at once and once one by one,
   compared. Then docs (READMEs, this plan's status).

## Needs advisor sign-off

- **Out-of-order uploads can change "up next" mid-study (U7):** a later link pass can reorder a student's next video.
  Levels, checks and videos are not affected.
- **The first uploader decides for the class (U11):** one student's confirmation fixes the lecture list and placements
  for everyone in a shared course; mistakes are fixed by the researcher.
- **Hosting students' uploaded slides on the server**: the same question as the professor's OK in `backend-plan.md`,
  now for files students upload.

## Follow-ups (not this plan)

- Hosting the worker (machine, queue, R2 for slides and videos), then push notifications ("Lecture 4 is ready").
- Several courses per student (U4).
- Handling a professor's updated deck properly (re-processing with KU mapping) instead of logging it (U12).

## Built (2026-10-20)

Commits on `slide-uploads`, each with tests: the core reads the course through a provider (`setFixtures`); course
tables and `assembleCourse`; item writing moved into `assessment_agent`; the Python jobs (`ingestion_agent/uploads.py`,
`upload_jobs.py`, `curriculum_alignment_agent/deck_kus.py`); the server's upload API and job queue
(`apps/server/src/uploads.ts`); the worker (`ingestion_agent/worker.py`); the assessment changes (U9, U10, U18); the
phone client and screens; the researcher's `npm run courses`.

Checked: core 243 tests, server 76, Python 178 (+1 skipped without LibreOffice), phone 21 + typecheck + lint, web e2e
108. The server tests include the key property (all decks at once and one at a time give the same course). End to end
with the real server and the real Python worker (LLM stubbed): over HTTP with curl, and in the phone app's web build
with Playwright (sign in, syllabus, lecture list, three decks at once, review, processing, then the baseline; a
classmate joining with a deck already in the course and one nothing matched).

**Where the build differs from the text above:**
- **"First uploader" (U11) is the first student to confirm a deck's placement.** Anyone who uploaded the same slides
  while they were still unplaced may place them; the first confirmation wins and fixes it for everyone.
- **The baseline's lectures are fixed at its first answer** (`SittingState.lectures`), so slides processed mid-sitting
  don't move its questions. The "no second check right after the baseline" rule uses those lectures.
- **A placement suggestion waits for the worker to read the file** (the review screen shows "Reading…"). Lecture and
  week numbers in the file name count as sure; title matches as sure at half the title's words.
- **`Lecture` keeps `slide_start`/`slide_end`** (0 for uploaded courses) instead of gaining `deck_ids`: decks live on
  the server, and nothing in the core needs them.
- **Merging and pointing courses (U17)** use a `syllabus_aliases` table, and only before the moved students have
  answered anything (their KUs and questions would otherwise come from two courses).
- **U18 records the videos students need** (`video_requests`: one row per course, KU and level, with the KU's first
  prerequisites, U8). Nothing makes them yet: that is `per-student-video-plan.md` step 5, a worker job of its own.

**Not done yet:**
- Step 8: one real run with the dev syllabus and decks (LLM spend; ask first), all at once and one by one.
- PowerPoint conversion is tested only where LibreOffice is installed (not on this laptop).
- Upload events in the research log (`deck_uploaded`, `deck_confirmed`, …); the `deck_uploads` table records every
  upload and its outcome meanwhile.
- Native iOS: the screens were checked in the web build only.
- Deploying: the droplet needs `SYLLABYTE_WORKER_TOKEN`, a files folder, and the hosting decisions above.

