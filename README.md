# SyllaByte

Multi-agent AI pipeline that turns a course syllabus + lecture slides
into personalized, animated micro-videos. NYUAD CS capstone, advised by
Professor Hanan Salam.

See `plan/ShotaMatsumoto_CapstoneProposal.pdf` for the full capstone proposal.
SyllaByte works from the syllabus and slides only, with no lecture recordings:
students upload their course's slides, and videos and questions are made from them
(`plan/slide-uploads-plan.md`, `plan/per-student-video-plan.md`).
The student-facing UI/UX is specified in `plan/ui-ux-implementation-plan.md`; the student app is
`apps/mobile`, and `apps/web` is the earlier clickable prototype.

## Repo layout

```
syllabyte/
├── pyproject.toml             # uv-managed root project; installs all packages/ below
├── docker-compose.yml         # Mongo + Redis + MinIO + agent containers (Oct+ infra path)
├── .env.example
├── data/courses/<course>/     # local-only: syllabus + slide decks you drop in (gitignored)
├── runs/<run_id>/             # local-only: pipeline outputs per run (gitignored)
├── scripts/
│   ├── generate_shorts.py     # reads a course (KUs); Week-1 shorts with no level
│   ├── video_jobs.py          # per-student videos: one KU at one level, cached (see "Making videos")
│   ├── build_ui_fixtures.py   # turns a finished run into the web app's fixtures (see apps/web)
│   └── report.py              # renders runs/<id>/report.md
├── apps/
│   ├── mobile/                # student app (Expo / React Native)
│   ├── server/                # API: sign-in, student state, course uploads, the upload worker's job queue (apps/server/README.md)
│   └── web/                   # Next.js Phase 0 clickable prototype (apps/web/README.md)
└── packages/
    ├── core/                         # TypeScript app logic shared by apps/mobile, apps/web and apps/server
    ├── common/                       # shared: models.py, llm.py, run_store.py, db.py, storage.py, celery_app.py
    ├── ingestion_agent/               # Component 1: syllabus + slide parsing; the upload worker (worker.py)
    ├── curriculum_alignment_agent/    # Component 1: Knowledge Unit extraction (Claude), Bloom's tagging
    ├── assessment_agent/              # Component 2 (Oct): CAT engine, IRT, Week 7 reassessment
    ├── script_generation_agent/       # Component 3: CLT-bLM scripts, Semantic Critique, slide-grounded
    └── animation_agent/               # Component 4: TTS, Manim generation + repair, assembly
```

## Setup

1. **Install [uv](https://docs.astral.sh/uv/)** if you don't have it, then:
   ```bash
   uv sync
   ```
   This creates `.venv/` with Python 3.12 and installs every package under
   `packages/` in editable mode alongside third-party deps (Anthropic SDK,
   Manim, PyMuPDF, python-pptx, Kokoro TTS, ...).

2. **LaTeX (required by Manim for `MathTex`/`Tex`)**:
   ```bash
   brew install --cask basictex
   # then, after basictex is on PATH (may need a new shell):
   sudo tlmgr update --self
   sudo tlmgr install standalone preview dvisvgm doublestroke relsize \
       fundus-calligra wasysym physics setspace tipa rsfs ragged2e \
       babel-english cm-super
   ```
   If this fights you, the `animation_agent` Docker image (see below) already
   bundles `texlive` and is the fallback.

3. **Kokoro TTS** (local, offline, no API key):
   ```bash
   brew install espeak-ng
   brew install sox   # used by the manim-voiceover plugin; without it every `import manim` warns
   ```
   `uv sync` already installs the `kokoro` Python package. macOS `say` works
   as a zero-install fallback (`--tts say`); ElevenLabs works if you set
   `ELEVENLABS_API_KEY` and install the extra: `uv sync --extra elevenlabs`.

4. **Anthropic API key** — copy `.env.example` to `.env` and set
   `ANTHROPIC_API_KEY`. Every LLM-calling script loads `.env` automatically.

5. **Course materials** — drop a real syllabus + slide decks into
   `data/courses/<course-name>/` (e.g. `syllabus.pdf`, `slides/lecture01.pdf`).
   This directory is gitignored.

## Making videos

There are two ways to make a video. Both run the same stages (`make_ku_video` in
`scripts/generate_shorts.py`: script + critique → TTS → Manim → assembly), but
only the first makes what a student would get.

### Per-student videos — use this to judge video quality

`scripts/video_jobs.py` makes one KU's video **at one student's level** (1
Foundations, 2 Core, 3 Advanced; `plan/per-student-video-plan.md`). The level
shapes the whole script (`LEVEL_BRIEF` in `script_generation_agent/prompts.py`),
including the objective's Bloom level: Remember/Understand, Apply/Analyze, or
Evaluate/Create. A script the automatic checker rejects is rewritten once with
the problems fed back. Videos are cached by (slides, KU, level, pipeline version),
so asking again for the same one is instant.

```bash
# 1. Read the course once: corpus.json + kus.json, no videos (--n-videos 0)
uv run python scripts/generate_shorts.py \
    --syllabus data/courses/<course>/syllabus.pdf \
    --slides data/courses/<course>/slides/*.pdf \
    --n-videos 0 --out runs/<course>

# 2. Ask for KU:LEVEL videos, then make what is queued
uv run python scripts/video_jobs.py --store runs/videos request --course runs/<course> --want <ku-id>:2
uv run python scripts/video_jobs.py --store runs/videos work --workers 2
uv run python scripts/video_jobs.py --store runs/videos status    # where each video is
```

The server's upload worker (`apps/server/README.md`) does not call this yet; run it by hand.

### Week-1 shorts (`generate_shorts.py` on its own)

```bash
uv run python scripts/generate_shorts.py \
    --syllabus data/courses/<course>/syllabus.pdf \
    --slides data/courses/<course>/slides/*.pdf \
    --n-videos 3 --quality low --out runs/dev
```

Makes the top `--n-videos` KUs with **no level**, and a script the checker rejects
ends that KU's video (no second attempt). Use it to read a course (step 1 above)
or to reproduce Week-1 results; not to judge what students would see. See
`plan/week1-shorts-from-slides-plan.md`; `scripts/report.py` renders a metrics +
rubric report for a run.

In both, a script that has not passed the critic after two rounds is still made into a video
(`script_generation_agent/critic.py`); its scores are in the video's `critique.json`.

## Docker infra path (October+ / Celery+Mongo pipeline)

The `docker-compose.yml` / `packages/common/syllabyte_common/{db,storage,celery_app}.py`
path is the persistent multi-agent pipeline described in the proposal
(Mongo for the Knowledge Unit Graph, Redis+Celery for async jobs, S3-compatible
object storage). It is not required for the Week-1 file-based pipeline above.

1. Copy the env template: `cp .env.example .env`
2. Bring up infra: `docker compose up -d mongo redis minio`
3. Confirm connectivity:
   ```bash
   uv run python -m syllabyte_common.db       # "MongoDB reachable: True"
   uv run python -m syllabyte_common.storage  # "Bucket 'syllabyte-dev' ready..."
   ```
4. Build the heavier agent images (Manim's LaTeX layer especially — expect
   several GB): `docker compose build ingestion_agent animation_agent`

## Notes

- **MinIO** is a drop-in local stand-in for AWS S3 — same `boto3` API.
  For the pilot deployment, unset `SYLLABYTE_S3_ENDPOINT` to point at
  real AWS S3 instead (per the proposal's budget: S3 free tier / NYUAD storage).
- **Manim's Docker image is large** because of the LaTeX toolchain
  (`texlive-full`-adjacent packages). Budget disk space and build time
  accordingly.
- `ingestion_agent/ingestion_agent/worker.py` is the **upload worker**: it claims
  jobs from `apps/server` (read a syllabus, read and place a deck, write questions)
  and posts the results; see `apps/server/README.md`. It does not make videos.
- `animation_agent/animation_agent/worker.py` is still a Celery stub. Videos are
  made as plain Python by `scripts/video_jobs.py` / `scripts/generate_shorts.py`
  (see "Making videos"), not through Celery/Docker.
