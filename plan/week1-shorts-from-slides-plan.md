# Week Plan: Can SyllaByte make good short-form videos from syllabus + slides only?

## Context

The professor's question for this week: **using only course materials (syllabus + slide decks — no lecture recordings), can the pipeline produce educational short-form videos of good enough quality?** This is a feasibility spike, not the full system from the proposal (`plan/ShotaMatsumoto_CapstoneProposal.pdf`). It front-loads the riskiest part of the proposal — LLM-generated Manim (documented ~38% render-failure rate) — so we learn early whether the core bet holds.

**Deliverable by end of week:** 3–5 vertical (9:16, 60–90 s) narrated Manim shorts generated from one real NYUAD STEM course's syllabus + slides, plus a `report.md` with render success rate, critique scores, cost/time per video, and a human-review rubric for you and the professor.

**Decisions already made (from our Q&A):**
- Input: real syllabus PDF + slide decks (PDF/PPTX) — you'll drop them into `data/courses/<course>/` (gitignored).
- Renderer: **Manim only, from day one** (no slide-image fallback renderer). Deterministic Manim *templates* still exist as the last-resort repair tier so a video always completes.
- Narration: free local TTS (Kokoro-82M, high quality, offline; macOS `say` as zero-install fallback). ElevenLabs behind a flag, not required.
- Format: 9:16, 1080×1920, 60–90 s. Burned-in captions (short-form convention) + sidecar `.srt`.

**Current repo state:** September scaffold only — `packages/common/src/{db,storage,celery_app}.py`, `packages/ingestion_agent/src/syllabus_parser.py` (PyMuPDF/python-docx text extraction, no LLM), stub workers, Docker Compose for Mongo/Redis/MinIO. No LLM code, no Manim, no API keys. Local machine: Python 3.12 available via uv, ffmpeg 8 present, cairo present, **no LaTeX, no Manim, no LibreOffice, Docker not running**, 61 GB free.

**Explicit scope-out this week:** Whisper/lecture audio, KU *graph* with prerequisites edges beyond a list, CAT/IRT assessment, personalization, Mongo/Celery/Docker wiring, web UI. Everything is file-based under `runs/<run_id>/` so nothing needs Docker.

---

## Architecture of the spike

```
syllabus.pdf + slides/*.pdf|pptx
   │  (1) ingest         → corpus.json  (+ slide PNGs)              [PyMuPDF, python-pptx]
   │  (2) extract_kus    → kus.json     (Knowledge Units, ranked)   [Claude, structured output]
   │  (3) write_script   → <ku>/script.json  (CLT-bLM phases, segments w/ VisualSpec)
   │      critique       → <ku>/critique.json (regenerate if below threshold, ≤2 rounds)
   │  (4) tts            → <ku>/audio/seg_i.wav + narration.wav + captions.srt
   │  (5) animate        → <ku>/seg_i.py → seg_i.mp4  (Claude codegen + ScopeRefine repair + template fallback)
   │  (6) assemble       → <ku>/final.mp4  (concat, sync to audio, mux, burn captions)   [ffmpeg]
   └─ (7) report         → report.md  (metrics + rubric table)
```

Key sync design: **audio is generated before animation**. Each segment's narration WAV fixes that segment's duration; the Manim scene is told the exact duration and pads with `self.wait()`. After render, `ffprobe` checks drift and ffmpeg `tpad`/`-t` corrects it deterministically.

Grounding design ("RAG-lite"): KUs cite `(deck, slide)` refs. Script generation receives the cited slides' verbatim text **and their rendered PNGs as image blocks** — no embeddings needed at this scale. KU extraction passes the whole deck PDF as a `document` block so Claude sees diagrams, not just text.

---

## Repo changes

### Packaging fix (needed for cross-package imports)
All three packages use a directory literally named `src`, so `common` and `ingestion_agent` can't both be imported. Rename to real package names and add one root `pyproject.toml` (uv-managed, Python 3.12 — Manim 0.21 needs ≥3.11, Kokoro needs <3.13):

- `packages/common/src/` → `packages/common/syllabyte_common/`
- `packages/ingestion_agent/src/` → `packages/ingestion_agent/ingestion_agent/`
- `packages/animation_agent/src/` → `packages/animation_agent/animation_agent/`
- new `packages/curriculum_alignment_agent/curriculum_alignment_agent/`
- new `packages/script_generation_agent/script_generation_agent/`
- root `pyproject.toml` (hatchling; `[tool.hatch.build.targets.wheel] packages = [...the five dirs...]`), `.python-version` = `3.12`
- Update the two Dockerfiles' `COPY src/` / `CMD` lines and the README layout block accordingly (small, keeps scaffold consistent).
- `.gitignore`: add `data/`, `runs/`, `.env` already there.

Dependencies (root pyproject): `anthropic>=1.7`, `manim>=0.21`, `pymupdf`, `python-pptx`, `python-docx`, `pydantic`, `python-dotenv`, `kokoro>=0.9`, `soundfile`, plus the existing infra deps (`pymongo`, `boto3`, `celery`, `redis`) kept for the scaffold. Optional extra `elevenlabs`.

### New / modified files

**`packages/common/syllabyte_common/`**
- `models.py` — Pydantic schemas shared by every stage: `Slide`, `SlideDeck`, `CourseCorpus`, `KnowledgeUnit`, `KUList`, `VisualSpec` (constrained `kind`: `title | bullets | equation | plot | diagram | code | compare`), `Segment` (phase `prepare|initiate|deliver|end`, `narration`, `visual`, `source_refs`), `Script`, `CritiqueResult`, `RenderResult`, `RunManifest` (per-stage token usage + wall time).
- `llm.py` — thin Anthropic wrapper: `Anthropic()` client (reads `ANTHROPIC_API_KEY` from `.env` via dotenv), `structured(system, content_blocks, schema, model="claude-opus-5")` using `client.messages.parse(..., output_format=Schema)`, `text(...)` for code generation, helpers to build `document` (PDF base64) and `image` (PNG base64) content blocks, `cache_control` on the stable system prompt, and a usage accumulator that writes into `RunManifest` for the cost report. Handle `stop_reason == "refusal"` by raising (course content won't trigger it; server-side fallbacks intentionally not enabled because `parse()` is on the non-beta path — easy to add later).
- `run_store.py` — `RunDir` helper: creates `runs/<timestamp>/`, `save_json/load_json`, per-KU subdirs, `stage_done(name)` so the CLI can resume from any stage.

**`packages/ingestion_agent/ingestion_agent/`**
- `syllabus_parser.py` — existing, unchanged (reuse `parse_syllabus`).
- `slide_parser.py` (new) — PDF: per-page text + 150-dpi PNG via PyMuPDF. PPTX: text + speaker notes via python-pptx; if LibreOffice is present (`soffice --headless --convert-to pdf`) convert to PDF first so we also get images, else text-only with a warning. Returns `SlideDeck`.
- `corpus.py` (new) — `build_corpus(syllabus_path, slide_paths, run_dir) -> CourseCorpus`.

**`packages/curriculum_alignment_agent/curriculum_alignment_agent/`**
- `ku_extractor.py` (new) — one Claude call per deck: system prompt = KU definition + Bloom levels + "each KU must be teachable in 60–90 s and cite slide numbers"; content = syllabus text + deck PDF document block → `KUList`. `select_kus(kus, n)` ranks by `short_worthiness` (1–5, with reason) and syllabus order. Also stores `bloom_level`, `prerequisites` (ids), `visual_idea`.

**`packages/script_generation_agent/script_generation_agent/`**
- `prompts.py` — CLT-bLM template compressed for shorts: Hook/Prepare (1 seg) → Initiate/objective (1) → Deliver (2–4) → End/recap (1). Constraints: 150–220 words total (~60–90 s at 150 wpm), one idea per segment, every segment cites ≥1 slide, `VisualSpec` must use only the allowed kinds, LaTeX only inside `equation` kind.
- `script_writer.py` — `write_script(ku, corpus) -> Script`: cited slides' text + PNG image blocks → `Script` via `structured()`. Hard code-side checks (word count, refs present, kinds valid) before the LLM critic.
- `critic.py` — `critique(script, source_slides) -> CritiqueResult` scoring pedagogical coherence / conceptual accuracy vs. slides / learner appropriateness (0–10 each, with issue list). `write_script_with_critique()` regenerates with the critique text appended if any score < 7, max 2 rounds; records rounds in manifest.

**`packages/animation_agent/animation_agent/`**
- `tts.py` — backends `kokoro` (default if importable; voice e.g. `af_heart`, 24 kHz), `say` (macOS, aiff→wav via ffmpeg), `elevenlabs` (only if key set). `synthesize_segments(script) -> [(wav_path, seconds)]`, `concat_wavs()`, `build_srt(segments, durations)` (one cue per segment; split long narrations at sentence boundaries proportional to character count).
- `manim_prompt.py` — system prompt for codegen: vertical frame facts (1080×1920 → Manim frame is 4.5 wide × 8 tall; safe area ±3.9 × ±7.2), **allowed API subset** (`Text`, `MarkupText`, `MathTex`, `Tex`, `Axes`, `NumberPlane`, basic shapes, `Arrow`, `VGroup`, `Write`, `FadeIn/Out`, `Create`, `Transform`, `Indicate`, `Circumscribe`, `self.wait`), mandatory rules (every text object `.scale_to_fit_width(≤4.0)`, min `font_size` 36, `self.wait()` so total runtime == given duration, class name `Seg{i}`, no imports besides `from manim import *`, no file/network access) + 3 few-shot scenes in `examples/` (title card, bullet reveal, equation + plot).
- `manim_codegen.py` — `generate_scene(segment, duration) -> code`, `repair_scene(code, traceback) -> code` (ScopeRefine tier 1), `regenerate_scene(...)` (tier 3). Static pre-check: `ast.parse` + reject forbidden names (`import os/sys/subprocess`, `open`, `eval`, `exec`, `__import__`).
- `templates.py` — deterministic Manim scenes built from `VisualSpec` without an LLM (`title`, `bullets`, `equation`, generic text card). Used as the final fallback tier **and** as the Day-1 smoke test that Manim + LaTeX work.
- `renderer.py` — writes `seg_i.py`, runs `manim render --resolution 1080,1920 --frame_rate 30 --format mp4 --disable_caching -o seg_i.mp4 seg_i.py Seg{i}` in a subprocess with a timeout (~180 s), captures stderr. Repair ladder: tier 1 fix ×2 → tier 3 regenerate ×1 → template fallback. Returns `RenderResult` (attempts, tier used, time). `--quality low` maps to `--resolution 540,960` for fast iteration.
- `visual_critic.py` (Day 5, stretch) — extract frames at 25/50/90% with ffmpeg, send as image blocks → `{ok, issues}` (overlap, off-screen, illegible). One repair round on failure.
- `assemble.py` — per segment: ffprobe duration vs. audio duration → `tpad` (clone last frame) or `-t` trim; concat demuxer (`-c copy`); mux `narration.wav` (`-c:a aac`); burn captions with `subtitles=captions.srt:force_style='FontSize=…,Alignment=2,MarginV=…'` → `final.mp4`; also keep `final_nocaptions.mp4` and `captions.srt`.

**`scripts/generate_shorts.py`** — orchestrator CLI (argparse): `--syllabus`, `--slides ...`, `--n-videos 3`, `--ku-ids` (optional override), `--out runs/<ts>`, `--tts kokoro|say|elevenlabs`, `--quality low|high`, `--from-stage`, `--skip-critic`. Runs stages 1–7, resumable.

**`scripts/report.py`** — writes `runs/<id>/report.md`: per video — KU title/Bloom level, word count, critique scores + rounds, per-segment render tier/attempts, render wall time, tokens + $ (Opus 5: $5/$25 per MTok), paths; aggregate render-success-rate (first-try and after-repair), mean cost/time per video; blank rubric table (LASEV 0–3 publishability + accuracy-vs-slides, flow, legibility, narration naturalness, sync) for you and the professor to fill.

**`docs/week1-findings.md`** — written on Day 7 (see below).

---

## Day-by-day steps

**Day 1 — Toolchain + smoke tests (the critical path)**
1. `uv python pin 3.12`, root `pyproject.toml`, package renames, `uv sync`.
2. LaTeX: `brew install --cask basictex`, then `sudo tlmgr update --self && sudo tlmgr install standalone preview dvisvgm doublestroke relsize fundus-calligra wasysym physics setspace tipa rsfs ragged2e babel-english cm-super` (the package list from Manim's install docs). Fallback if this fights back: Docker `animation_agent` image (already has texlive) — start Docker Desktop.
3. Kokoro: `brew install espeak-ng`; `uv add kokoro soundfile`; synthesize one sentence.
4. Manim smoke test via `templates.py`: render a 9:16 `equation` scene with `MathTex` at low res. This proves LaTeX + cairo + ffmpeg together.
5. Put your `ANTHROPIC_API_KEY` in `.env`; `llm.py` hello-world with `messages.parse`.
6. Drop the course syllabus + slides into `data/courses/<course>/`.

**Day 2 — Ingestion + KU extraction**
7. `slide_parser.py`, `corpus.py`; run on the real decks; eyeball `corpus.json` and PNGs.
8. `ku_extractor.py`; run; read `kus.json` critically — are KUs 60–90 s-sized, are slide refs right? Tune prompt. Pick 3–5 KUs (mix of an equation-heavy one, a diagram/concept one, and a procedural one so the visual kinds get exercised).

**Day 3 — Scripts, critique, narration**
9. `prompts.py`, `script_writer.py`, `critic.py`; generate + critique scripts for the chosen KUs; read every script against the slides yourself (this is where "grounded only in course materials" is judged).
10. `tts.py` + SRT; listen to `narration.wav` for each KU; check word count → duration lands in 60–90 s.

**Day 4 — Manim generation + repair loop**
11. `manim_prompt.py` + `examples/`, `manim_codegen.py`, `renderer.py`, `templates.py` fallback. Render one KU's segments at low quality. Log which tier each segment needed — this number is the headline finding of the week.
12. Iterate on the codegen prompt for the top failure classes (off-screen text, LaTeX errors, wrong duration).

**Day 5 — Assembly + first complete short**
13. `assemble.py`; produce the first `final.mp4`; watch it on a phone-shaped window. Fix sync/caption sizing.
14. Stretch: `visual_critic.py` (Claude vision on 3 frames) with one repair round.

**Day 6 — Full run + metrics**
15. `generate_shorts.py` end-to-end at `--quality high` for all 3–5 KUs; `report.py`. Capture render success rate (first try / after repair / template-fallback share), critique scores, $ and minutes per video.

**Day 7 — Review + findings**
16. Score each video with the rubric (you first; the professor second). Fix the two most common failure modes, re-run the affected KUs.
17. Write `docs/week1-findings.md`: answer the professor's question directly (yes/no/partially), what quality dimensions held (grounding, narration, pacing) vs. didn't (visual legibility, LaTeX failures…), the metrics table, and what this implies for the October–December timeline. Commit.

---

## Verification

- **Toolchain:** `uv run manim --version` (0.21.x); `uv run python -c "import kokoro, anthropic, pymupdf, pptx"`; `latex --version`.
- **Manim + LaTeX + 9:16:** `uv run python -m animation_agent.templates --smoke` renders an `equation` scene to `runs/smoke/seg_0.mp4`; `ffprobe` shows 1080×1920 (or 540×960 at low).
- **TTS:** `uv run python -m animation_agent.tts --demo "Hello"` produces a WAV; play it.
- **LLM:** `uv run python -m syllabyte_common.llm --ping` returns a parsed Pydantic object and prints token usage.
- **Ingestion:** `uv run python -m ingestion_agent.corpus --syllabus data/courses/X/syllabus.pdf --slides data/courses/X/slides/*.pdf` → `corpus.json` with per-slide text and PNG paths.
- **End-to-end (low quality, 1 video):** `uv run python scripts/generate_shorts.py --syllabus … --slides … --n-videos 1 --quality low --out runs/dev` → `runs/dev/<ku>/final.mp4`, 60–90 s by `ffprobe`, captions visible, audio/video aligned within 0.2 s per segment (assemble logs drift).
- **Resumability:** re-run with `--from-stage animate` and confirm scripts/audio are reused, only renders repeat.
- **Full run:** `--n-videos 3..5 --quality high` completes; `report.md` populated; every video has a `final.mp4` even if some segments fell back to templates (fallback share is reported, not hidden).
- **Human check:** you and the professor fill the rubric in `report.md`.

## Risks / notes
- LaTeX install is the most likely Day-1 blocker; Docker image is the fallback. Don't let it eat more than a morning.
- PPTX decks without LibreOffice lose slide images (text-only grounding). `brew install --cask libreoffice` fixes it if the decks are PPTX.
- Cost estimate on Opus 5: roughly $1–3 per video (KU extraction with a full-deck PDF is the biggest single call; codegen repairs multiply). The report shows exact numbers.
- LLM-generated Manim runs as a local subprocess with only a static forbidden-names check — fine for local dev, not for a hosted service.
