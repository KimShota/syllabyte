# Per-student video generation: plan

Branch: `per-student-video` (from `main` at cb45549). Status: **step 2 (level in script generation) built and tried on real output (2026-10-13); steps 3–5 not started.**
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
| V1 | **What differs between levels (option c), as built:** the **hook (prepare), objective (initiate) and recap/end segments are shared across levels; only the worked-example (deliver) segment is level-specific.** Narration pace and wording follow the level too (140/155/165 words a minute for L1/L2/L3, plan §7.4), but a segment whose script text is identical across levels is the same animation. Segment renders are cached by script content (the existing `segment_render_key`), so shared segments hit the cache across levels and across students. |

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

- Model choice for the speed experiments (budget: $10, user-approved; ≈ $2.8 used).
- **Base prefetch policy:** build a KU's base script and animations lazily (when its level is first needed, slow the first time), for the upcoming
  lecture(s) ahead of time (recommended), or for the whole course at upload (about $1 per KU, most never watched).
- Whether the visual critic and layout audit stay on the critical path or run after the video is first made available.

## Step 2 results: level in script generation (built, committed on this branch)

Built: `script_generation_agent/leveled.py` (`BaseScript`, `write_base_with_critique`, `write_example`, `write_leveled_script`, `compose`),
the base and per-level example prompts, scoped critic prompts, and 38 tests with a stubbed LLM. A script is four shared segments (hook,
objective, core idea, recap) written **once per KU** plus one worked-example segment **per level**: Level 1 = a recap of the prerequisite (skipped
when the KU has none) and a full step-by-step example; Level 2 = one example, key steps; Level 3 = a "what if" question. Shared segments are identical
across levels by construction (verified on real output).

Real runs on `ku-potential-outcomes` (3 levels each, Opus 5, second API key; $0.70 + $0.36 + $0.94 + $0.76 spent, ≈ $2.8 of the $10 budget with the
ping):

| Iteration | What changed | Level 1 / 2 / 3 critic |
|---|---|---|
| 1 | first version | pass (2 rounds) / pass / pass (2 rounds) |
| 2 | (re-run of L1 after a no-recap fix) | **failed**: the base had unsupported claims the example loop could not fix |
| 3 | base critiqued once on its own; per-level critic scoped to the example | fail / fail / pass (all in 2 rounds) |
| 4 | example prompt: continue the screen, never narrate the animation, stay with the slides | **pass in 1 round** / fail (visual alignment 5–6) / **pass in 1 round** |

Findings:
- **The base needs its own critic loop**, once per KU: a flaw in a shared segment fails every level and no rewrite of the example can fix it.
- **Critic complaints about the example are mostly continuity** (re-growing bars the base already drew, naming an object it never drew) and
  **visuals that are text on screen**. Telling the writer to continue the screen as it ended raised first-round passes from 0/3 to 2/3.
- **Per-call latency is 6–30 s** (write ≈ 12–30 s, critic ≈ 17–28 s); a failed round adds ≈ 40 s. One run took 734 s end to end; per-call timings
  showed that was API latency, not the pipeline. With a cached base, a level's script costs one example write + one critic round (≈ 40 s) plus
  rewrites. That is on the critical path to the first video, so step 4 should decide whether the example's critic runs in the background.
- **Key architectural consequence of V1:** the base is level-independent, so its script **and its four segments' animations** can be made before the
  student's level is known (at upload, or one lecture ahead). Once a level is set only the example segment remains: one script call, one TTS clip and
  **one** segment of animation instead of five. That cuts the time to a first video from "all five segments" to "the slowest of one".

## Next

3. The cache and an on-demand job, including **base prefetch** (a policy to decide: see open questions).
4. Speed experiments on animation code (cap thinking first), within the $10 budget.
