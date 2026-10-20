import { fixtures } from "../fixtures";
import { freshState, getState, replaceState } from "../store";
import { startOfWeek } from "../logic/time";
import type { DemoState } from "../types";
import { DAY } from "../util";
import { api } from "./client";
import { runSitting, scriptedStudent } from "./demo";

/**
 * The scripted students for usability task 8 and for the levels screens (plan §10). They are built by running the
 * real API with a backdated clock, so nothing here can drift from the app's own rules: the *inputs* are authored
 * (how this student answers), and levels, reasons and the "What changed and why" card are whatever the real
 * logic produces from them.
 *
 *   precheck   Week 0 baseline taken in Week 1; it is now Week 2 and the check before Lecture 3 is due.
 *   midcourse  As above, plus videos watched with their quick checks, and the Lecture 3 check taken: the student
 *              improved on Lecture 3 (levels go up), and has not kept up the earlier lectures (levels go down),
 *              so the "What changed and why" card is waiting.
 *
 * Abilities are per lecture: the baseline student is strong on 1, fairly strong on 2, weak on 3.
 */
const BASELINE = scriptedStudent({ 1: 1.2, 2: 0.7, 3: -1.2 });
const AT_LECTURE_3_CHECK = scriptedStudent({ 3: 0.8, 1: -1.5, 2: -1.5 });

export async function makePersonaState(variant: "midcourse" | "precheck"): Promise<DemoState> {
  const real = Date.now();
  const fresh = freshState(real);
  // Week 1 started three weeks ago, so "now" is Week 4 and the baseline can be backdated to Week 1.
  const start = startOfWeek(real) - 3 * 7 * DAY;
  replaceState({ ...fresh, semester_start: start, consent: "research", flags: { log_declined: true } });

  const at = (weeksAgo: number) => replaceState({ ...getState(), clock_offset_ms: -weeksAgo * 7 * DAY });
  at(3); // Week 1
  await runSitting("week0", BASELINE);

  if (variant === "precheck") {
    at(2); // Week 2: the Lecture 3 check is due
    return { ...getState(), upcoming_lecture: 3 };
  }

  // Week 2: watch the lecture 1 and 2 videos, answering each quick check
  at(2);
  const answers: [string, "right" | "wrong"][] = [
    ["ku-reading-difference-table", "right"],
    ["ku-potential-outcomes", "right"],
    ["ku-selection-bias-general-formula", "wrong"],
  ];
  for (const [id, how] of answers) {
    const v = fixtures().videos.find((x) => x.id === id);
    if (!v) continue;
    const item = fixtures().items.find((i) => i.id === v.checkpoint.item_id)!;
    await api.postCheckpointAnswer({
      videoId: id, choice: how === "right" ? item.correct_index : (item.correct_index + 1) % 3, confidence: how === "right" ? "pretty" : "certain",
      hintUsed: false, latencyMs: 4000,
    });
    await api.markWatched(id);
  }
  // Week 3 is the lecture 3 check
  at(1);
  replaceState({ ...getState(), upcoming_lecture: 3 });
  await runSitting("lecture-3", AT_LECTURE_3_CHECK);
  at(0);
  return { ...getState(), upcoming_lecture: 3 };
}
