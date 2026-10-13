# Per-student video generation: plan

Branch: `per-student-video` (from `main` at cb45549). Status: **design started (2026-10-13); one decision settled, nothing built.**
Roadmap item 4 of `plan/per-ku-profiling-plan.md`. Context: the student uploads their own course, each KU's video is made on
demand at that student's level for that KU, and "fast" means the first video is ready within about 3 minutes of a level being set
and each later one before the student needs it (per-KU plan D15, D16).

## Why

- **Level is not a parameter anywhere in the pipeline.** `script_generation_agent.prompts.build_script_prompt` has no level; the
  Level 1/2/3 "tailoring" rows in the app are hand-written fixtures; only a Level 2 video exists per KU. Personalization (H1, H3) is not
  delivered until the pipeline can make a KU at a level.
- **A video takes about 8 minutes** (`runs/bench-par.log`: 14:59:17 → 15:07:37 for one KU, 5 segments in parallel).

## Where the time goes (measured from existing run records, no new spend)

`runs/dev/manifest.json` (86 LLM calls, 1 497 s of waiting) and `runs/bench-par/manifest.json` (20 calls, 1 236 s):

| Stage | dev run | share |
|---|---|---|
| `manim_codegen` (animation code per segment) | 846 s, 45 calls | 56 % |
| `manim_repair` | 397 s, 30 calls | 27 % |
| `extract_kus` | 93 s | 6 % |
| `critique` + `write_script` (all 5 videos) | 162 s | 11 % |

So script writing and its critic are ≈ 30 s per video. **Animation code is ≈ 83 % of the LLM time.**

In the benchmark run (current pipeline, with the legibility rules and visual critic) the five `manim_codegen` calls took
74, 81, 119, 200 and **336 s** for 5 467, 6 668, 9 777, 16 194 and 26 731 output tokens: a steady **75–80 tokens/s**, so wall time is
output tokens. `codegen_max_tokens` is 64 000 on Anthropic models and its docstring says that thinking counts against it and "the model can
think past 20k before writing any code". **Most of the codegen time is thinking, not code** (the dev run's median codegen output was
1 258 tokens, before the legibility rules). After codegen come layout repair (71 s and 154 s), visual repair, visual critic and repair
again. A video's time is the slowest segment's whole chain: codegen 336 s + repair 19 + critic 21 + visual repair 18 + layout repair 154…

Implications: the first lever is capping or lowering thinking on codegen, not a faster renderer. Script generation per level is cheap.

## Decisions

| # | Decision |
|---|---|
| V1 | **What differs between levels (option c):** the **hook (prepare), objective (initiate) and recap/end segments are shared across levels; only the worked-example (deliver) segment is level-specific.** Narration pace and wording follow the level too (140/155/165 words a minute for L1/L2/L3, plan §7.4), but a segment whose script text is identical across levels is the same animation. Segment renders are cached by script content (the existing `segment_render_key`), so shared segments hit the cache across levels and across students. |

## Plan

1. **Measure** *(done from existing records; a clean re-run only if a decision needs it).*
2. **Make level an input to script generation:** `level` in `build_script_prompt` and the critic (recap depth, example type: full worked example at
   L1, one example at L2, a "what if" question at L3; Bloom-tier wording per proposal §3.3); the example segment is marked level-specific; tests that
   three levels give three different example segments and identical shared segments.
3. **Cache and an on-demand job:** an idempotent `generate_video(course_hash, ku_id, level)`, content-keyed (slide content, KU, level, pipeline
   version), with a priority queue (the first playlist video first), a worker limit, and a status (`queued` / `making` / `ready` / `failed`). File-based
   now; the same interface fronts Celery in Phase 1.
4. **Cut the time, ranked by measured gain** (each judged on time to first video, render success rate ≥ 75 % and cost per video): cap/lower thinking on
   codegen and repair; a faster model for codegen; fewer repair/critic loops; run every queued video's segments in parallel.
5. **Wire it to the app** with the backend (Phase 1); until then the demo keeps simulating "made at level".

## Open questions

- Budget and model choice for the speed experiments (each full video ≈ $1 on Opus 5).
- Whether the visual critic and layout audit stay on the critical path or run after the video is first made available.
