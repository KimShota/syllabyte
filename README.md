# SyllaByte

Multi-agent AI pipeline that turns a course syllabus + lecture recordings
into personalized, animated micro-videos. NYUAD CS capstone, advised by
Professor Hanan Salam.

## Repo layout

```
syllabyte/
├── docker-compose.yml        # Mongo + Redis + MinIO + agent containers
├── .env.example
└── packages/
    ├── common/                       # shared: db.py, storage.py, celery_app.py
    ├── ingestion_agent/               # Component 1 (Sept–Oct): syllabus parsing, Whisper transcription, KUG
    ├── curriculum_alignment_agent/    # Component 1 (Oct): Bloom's tagging, cognitive load estimate
    ├── assessment_agent/              # Component 2 (Oct): CAT engine, IRT, Week 7 reassessment
    ├── script_generation_agent/       # Component 3 (Nov): CLT-bLM scripts, Semantic Critique, RAG
    └── animation_agent/               # Component 4 (Dec): Manim generation, ScopeRefine, Visual Critic
```

## September setup (foundations)

1. **Install Docker + Docker Compose** if you don't have them already.
2. Copy the env template:
   ```bash
   cp .env.example .env
   ```
3. Bring up the infra services (Mongo, Redis, MinIO):
   ```bash
   docker compose up -d mongo redis minio
   ```
4. Confirm connectivity:
   ```bash
   cd packages/common/src
   python db.py       # should print "MongoDB reachable: True"
   python storage.py  # should print "Bucket 'syllabyte-dev' ready..."
   ```
5. Build the two heavier agent images (these take a while — Manim's
   LaTeX layer especially, expect several GB):
   ```bash
   docker compose build ingestion_agent animation_agent
   ```
6. Test the syllabus parser against a real syllabus PDF:
   ```bash
   cd packages/ingestion_agent/src
   pip install -r ../requirements.txt   # or run this inside the container
   python syllabus_parser.py /path/to/some_syllabus.pdf
   ```

## Notes

- **MinIO** is a drop-in local stand-in for AWS S3 — same `boto3` API.
  For the pilot deployment, unset `SYLLABYTE_S3_ENDPOINT` to point at
  real AWS S3 instead (per the proposal's budget: S3 free tier / NYUAD storage).
- **Manim's Docker image is large** because of the LaTeX toolchain
  (`texlive-full`-adjacent packages). Budget disk space and build time
  accordingly — this is worth doing early in September, not December.
- Task logic inside `ingestion_agent/src/worker.py` and
  `animation_agent/src/worker.py` is intentionally a stub right now.
  October and December respectively are when real Celery tasks get
  wired in per the project timeline.
