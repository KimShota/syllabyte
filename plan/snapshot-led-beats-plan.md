# Snapshot-led beats: every point a step of the picture

Status: steps 1-3 built 2026-11-14 (uncommitted, branch `visual-alignment`); step 4 waits for a go-ahead on its cost. The co-writing attempt (runs/va3) was taken out first.

## Why

Visual alignment (the critic's "each beat's picture shows what that same line says, at the moment it says it")
sits at about 5 of 10 for scene-grammar videos, and two rounds of targeted fixes did not move it beyond noise
(runs/va1, runs/va2: 4.0 -> 4.4 on 5 topics, 4.8 -> 4.6 on 10; writer noise is about +-0.3 on 10). What the fixes
did change is which complaint dominates. It is now the picture standing still while a line brings in something new:

- DFS running time: "most beats from deliver segment 2 onward keep the picture unchanged; the formula
  O(1) x sum deg(u) = O(|E|) is never written".
- House painting: "'The picture stays as it is' while OPT(5), OPT(6), the choice and the jump back are spoken".
- Topological sort: the picture runs ahead of the line ("d b c a" while the line says "d, b").

The cause is structural. Two plans are made separately and only meet by luck:

1. the **beat plan**, fixed by code (`storyboard.skeleton`): 5 segments, 17 beats at level 2, each with a
   tutoring role (question, wrong idea, feedback, build, predict, check);
2. the **picture program**, written by the planner: as many snapshots as it chooses, often 5 or 6 for 11 lines
   that make a point.

The planner then assigns snapshots to beats, and the writer writes each line to its beat's picture. When the
program has fewer steps than the beat plan has points, most points get no picture change, and no check can
create the missing steps afterwards (the redraw tried in runs/va2 mostly returned another thin plan).

## The change

Build the beat plan's points from the picture's steps, so a point-making line without its own picture change
can't exist.

1. **The planner writes the program first, with each snapshot tagged by the part of the video it belongs to.**
   `snap(caption, name=..., part='deliver_1')`. Parts are the skeleton's segments. Code runs the program (as now)
   and has the ordered list of snapshots per part.

2. **Code builds the beats from the snapshots.** The tutoring roles stay (the hook question, the wrong idea and
   its feedback, the predict line and its answer, the restatement), because they are what make the video teach.
   But a part's *build* beats are no longer a fixed count: each snapshot of the part after the first gets one
   point-making line, in program order, and code writes its `p.show(snap=...)` call. Questions and predict lines
   keep the picture, as now. The planner no longer places show calls at all, so a line can't be out of step with
   its picture or jump ahead: the calls are made in order by construction.

3. **Length stays a short.** The video must stay 70-100 s (about 14-18 lines). Code checks the snapshot count
   per part against a band (deliver parts 3-6 steps each, prepare and initiate 1-2), and a program outside it is
   sent back once with the counts (the only redraw left).

4. **Formulas become steps of the picture.** A new `formula` view in the scene grammar: one or more TeX lines, a
   term highlighted, a line boxed, a step rewritten. "sum is cin XOR a XOR b" or "O(1) x sum deg(u) = O(|E|)" is then
   a snapshot like any other, with its own line, instead of an optional EquationSteps the planner often leaves out.
   (Fits beside a diagram: it takes a band like a code panel does.)

5. **The writer is unchanged**, except that each point-making line now has exactly one change to say.

## What stays

The tutoring frame and its critic rubric, the scene-grammar views and layout, the checks of the program (fit,
slide example, fidelity), voices, render and assembly. The template path (`SYLLABYTE_PICTURES=templates`) keeps
the fixed skeleton.

## Risks

- Variable-length segments touch code that assumes the skeleton's beat counts: `validate_dialogue` word ranges,
  the slang placement, `match_lines`, the critic's 5-segment format. Each needs a look; the segment count stays 5.
- A program tagged badly (all snapshots in one part) needs a clear refusal and one redraw; that adds 15-20 s
  when it happens.
- More picture changes mean more animation per segment: render time may rise by a few seconds.
- The planner must write the program before the beats, which is a different prompt shape; the planner's output
  may get longer (it is about 2k tokens now).

## Plan and cost

| Step | What | Cost |
|---|---|---|
| 1 | `formula` view (api, layout, draw, brief, tests, rendered examples with no findings) | free |
| 2 | `part=` on snap(); beats built from snapshots; show calls made by code; band check | free |
| 3 | offline check on the 51 saved plans in runs/p5/plans and runs/picture-p4/plans: how many would pass the band, and what the beat counts become | free |
| 4 | 10-topic test on the same topics as runs/va2, same critic view | about $1.40 |

Success: mean visual alignment at least 5.8 on the 10 topics (from 4.6-4.8), accuracy not lower, time per video
no more than 5 s slower. If step 4 misses that, the branch stays unmerged and `main` keeps today's behaviour.

## Built (steps 1-3)

- `formula` view (scene/api.py, layout.py, draw.py): up to 4 TeX lines in a band under the picture (0.9 units a
  line); add, set (a rewritten step morphs), mark, highlight a term, box. A backslash a plain string swallowed
  ('\frac' as a form feed) is put back. Brief and a whole-video example (examples.GEOMETRIC, tagged by part).
- `snap(..., part=, wrong=)`; `script_generation_agent/snapshot_beats.py`: the program-only planner call (one
  redraw with the previous program and the checker's reasons), the band check, the beats built from the snapshots
  (each part's tutoring roles, plus one build line per extra snapshot, speakers taking turns), and every call made
  by code. Default for grammar videos on this branch; `SYLLABYTE_BEATS=planned` gives the old beats. A program
  that still can't run or fit after the redraw falls back to the old path; one that runs but misses the band is
  built anyway (extra snapshots passed over, missing ones leave their lines holding the picture).
- Not run on this path: settle_picture (its fixes move shows off question lines and fill still beats, which would
  undo the order code made); only a last pass that drops a refused call.

Step 3 result: of the 43 saved plans with a program, none pass the band as the old plans placed their snapshots
(median 5 snapshots a program, against the 9-14 the band needs; initiate and deliver_2 usually had none). Built
anyway, they'd change the picture on a median of 5 of 15 lines, the same thinness the critic complained of. Those
planners were never told the bands, so this doesn't predict the new prompt's pass rate, but it says the redraw may
fire often (15-20 s each) until the prompt gets the counts right first time.

## Step 4 result (runs/va4, 2026-11-14)

Same 10 topics and critic as runs/va2. Mean visual alignment 4.6 -> 6.0 (the 9 built from snapshots 4.56 -> 6.22),
accuracy 6.2 -> 6.4, coherence 5.7 -> 5.8: the success bar (5.8, accuracy not lower) is met, well past the writer's
+-0.3 noise on 10 topics. Up on 8, level on 1 (eigen), down on 1 (the TCP handshake, which fell back to the old path:
its sequence of 8-9 messages never fit). Biggest gains on the three that scored 3: topological sort 7, house
painting 6, DFS running time 5.

- Time: on the 6 topics run without re-extraction, 58 s a video against 67 s in va2 (faster: no settle or fix call).
- Length: videos average 114 s (va2: 112 s), both past the 100 s target; DFA built 19 lines (its wrong idea wasn't
  second in deliver_1, so the misconception line holds and adds one).
- Redraws: 8 of 10 first programs were redrawn (most for not running or not fitting); the third try for a program
  that can't be drawn was used once (full adder).
- Accuracy fell on round robin (7 -> 4: slide 25's numbers not drawn) and house painting (5 -> 4).
- Caveats: one run; 4 topics (eigen, TCP, round robin, call stack) ran on re-extracted KUs, worded a little
  differently from va2's.
- Cost: $2.83 against an estimate of $1.40 ($0.91 an accidental KU re-extraction, $0.59 TCP's fallback).
