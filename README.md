# SyllaByte

Multi-agent AI pipeline that turns a course syllabus + lecture recordings
into personalized, animated micro-videos. NYUAD CS capstone, advised by
Professor Hanan Salam.

See `plan/ShotaMatsumoto_CapstoneProposal.pdf` for the full capstone proposal
and `plan/week1-shorts-from-slides-plan.md` for the current sprint plan
(generating short-form videos from syllabus + slides only, no lecture audio).
The student-facing UI/UX is specified in `plan/ui-ux-implementation-plan.md` and built in `apps/web`.

## Repo layout

```
syllabyte/
├── pyproject.toml             # uv-managed root project; installs all packages/ below
├── docker-compose.yml         # Mongo + Redis + MinIO + agent containers (Oct+ infra path)
├── .env.example
├── data/courses/<course>/     # local-only: syllabus + slide decks you drop in (gitignored)
├── runs/<run_id>/             # local-only: pipeline outputs per run (gitignored)
├── scripts/
│   ├── generate_shorts.py     # Week-1 end-to-end orchestrator CLI
│   ├── build_ui_fixtures.py   # turns a finished run into the web app's fixtures (see apps/web)
│   └── report.py              # renders runs/<id>/report.md
├── apps/web/                  # student web app (Next.js): Phase 0 clickable prototype, see apps/web/README.md
└── packages/
    ├── common/                       # shared: models.py, llm.py, run_store.py, db.py, storage.py, celery_app.py
    ├── ingestion_agent/               # Component 1: syllabus + slide parsing (no LLM)
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
   ```
   `uv sync` already installs the `kokoro` Python package. macOS `say` works
   as a zero-install fallback (`--tts say`); ElevenLabs works if you set
   `ELEVENLABS_API_KEY` and install the extra: `uv sync --extra elevenlabs`.

4. **Anthropic API key** — copy `.env.example` to `.env` and set
   `ANTHROPIC_API_KEY`. Every LLM-calling script loads `.env` automatically.

5. **Course materials** — drop a real syllabus + slide decks into
   `data/courses/<course-name>/` (e.g. `syllabus.pdf`, `slides/lecture01.pdf`).
   This directory is gitignored.

## Week-1 pipeline (syllabus + slides → short-form videos)

```bash
uv run python scripts/generate_shorts.py \
    --syllabus data/courses/<course>/syllabus.pdf \
    --slides data/courses/<course>/slides/*.pdf \
    --n-videos 3 --quality low --out runs/dev
```

See `plan/week1-shorts-from-slides-plan.md` for the full day-by-day plan,
architecture, and verification steps. `scripts/report.py` renders a metrics +
rubric report for a completed run.

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
- Celery task logic inside `ingestion_agent/ingestion_agent/worker.py` and
  `animation_agent/animation_agent/worker.py` is intentionally a stub — the
  Week-1 pipeline runs as plain Python via `scripts/generate_shorts.py`
  instead of through Celery/Docker.
