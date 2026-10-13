# Per-student video generation: plan

Branch: `per-student-video` (from `main` at cb45549). Status: **step 2 (level in script generation) built and tried on real output (2026-10-13), revised the same day; steps 3–5 not started.**
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
| V1 | **A video is generated for one student's level on one KU, as soon as that level is known, and the level shapes the whole video** (revised 2026-10-13, superseding a shared-base design). Every segment is written for the level: Level 1 = plain words with every term defined on first use, one analogy, a recap of the prerequisite when there is one, a Remember/Understand objective and a full step-by-step worked example; Level 2 = course terms with a short gloss, an Apply/Analyze objective, one worked example; Level 3 = precise terms and comparative framing, an Evaluate/Create objective, and a "what if" question in place of the worked example (proposal §3.3). Nothing is generated for levels nobody needs. Videos are cached by (slide content, KU, level, pipeline version), so a second student with the same slides and level gets it instantly. |
| V2 | **Speed comes from the pipeline itself**, not from building parts before the level is known: time to the first video is the whole pipeline, so step 4 (animation-code speed) comes before the job queue (step 3), with real numbers reported first. |

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
- Whether the visual critic and layout audit stay on the critical path or run after the video is first made available.

## Step 2 results: level in script generation

**Built:** `write_script(..., level=, prereq_titles=)` and `write_script_with_critique(..., level=)`, with `level_system_prompt(level)` (the original
5-segment prompt with the level written in) and `critique_system_prompt(level)` (the critic judges appropriateness against the level). With a level, a
script the code-side checks reject is rewritten once with the reasons; without one the pipeline behaves exactly as before (the original prompts' text is
pinned by hash in the tests). 21 tests with a stubbed LLM.

**First tried and dropped (same day):** a shared base (hook, objective, core idea, recap written once per KU) plus a per-level example segment. It worked
(shared segments were identical across levels, verified on real output), but it kept the language the same for every level, which the proposal does not,
and its only purpose was building parts before the level is known. Lessons that carried over: tell the writer never to narrate the animation and to stay
with what the slides state; a reviewed shared part cannot be fixed by rewriting the part that varies.

**Real output, `ku-potential-outcomes`, Opus 5, second API key:**

| | Level 1 | Level 3 |
|---|---|---|
| language | defines each term as it appears ("Let Y-zero-i be…"), "picture two copies of Timmy" | precise notation, "the structure is in the subscripts, not the values" |
| objective | "explain potential outcomes" | "judge exactly what a claim about person i asserts" |
| second deliver | the worked example, step by step (4 with insurance, 3 without) | "what if both outcomes had come out at four?" |
| critic | passed in 1 round (one checker rewrite first) | passed in 2 rounds |
| time / cost | ≈ 76 s / $0.20 | ≈ 130 s / $0.32 |

Per call: writing 19–58 s, the critic 26–30 s. Spent on dry runs so far: ≈ $3.3 of the $10 budget (including the dropped design's runs).

## Next

4. **Speed of animation code** (before the job queue): cap or lower thinking on codegen and repair, measure time per segment, render success and cost on
   one KU first, within the remaining budget.
3. Then the cache and the on-demand job.
