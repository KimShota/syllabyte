import { FIX, itemById, videoById } from "@/lib/fixtures";
import { createTask } from "@/lib/logic/nextSession";
import { onboardingLevel } from "@/lib/logic/levels";
import { buildPlaylistState } from "@/lib/logic/playlist";
import { proposeLevels } from "@/lib/logic/proposals";
import { startOfWeek } from "@/lib/logic/time";
import { freshState } from "@/lib/store";
import type { Choice, ClaimVerdictRecord, Confidence, DemoState, Item, Jol, ResponseRecord } from "@/lib/types";
import { DAY, HOUR, uid } from "@/lib/util";

/**
 * The scripted student for usability task 8 and for screens 8–10 (plan §10).
 * Hand-written so the Week 7 story is coherent across My levels, the calibration
 * blocks and the proposals. Nothing here is computed from a model: the *inputs*
 * are authored, and the real rules (levels.ts, proposals.ts) produce the outputs,
 * which keeps this a test of the actual logic.
 *
 * The story (4 topics, 4 videos, Week 7):
 *   Causal questions   L3  aced everything                     -> Level 3, no change
 *   Potential outcomes L2  improving, 5 of 5 since Week 1      -> proposed UP to 3
 *   Selection bias     L1  was lost in Week 1, now mostly right -> proposed UP to 2
 *   Randomization      L2  overconfident on the coin-toss video -> proposed DOWN to 1
 */
const wrong = (item: Item): number => (item.correct_index + 1) % item.options.length;

function pick(item: Item, how: "right" | "wrong" | "not_sure"): Choice {
  return how === "not_sure" ? "not_sure" : how === "right" ? item.correct_index : wrong(item);
}

export function makePersonaState(variant: "invite" | "results", nowMs = Date.now()): DemoState {
  const s = freshState(nowMs);
  s.participant_code = null;
  s.consent = "research";
  // "Now" is in Week 7.
  s.semester_start = startOfWeek(nowMs) - 6 * 7 * DAY;
  const at = (weekN: number, dayN: number, hour = 14) => s.semester_start + (weekN - 1) * 7 * DAY + dayN * DAY + hour * HOUR;

  const responses: ResponseRecord[] = [];
  const add = (
    item: Item, how: "right" | "wrong" | "not_sure", when: number,
    o: { confidence?: Confidence; hint?: boolean } = {},
  ) => {
    const choice = pick(item, how);
    responses.push({
      id: uid("r"), item_id: item.id, topic_id: item.topic_id,
      video_id: item.context === "onboarding" || item.context === "recheck" ? null : item.ku_id,
      context: item.context, choice, correct: choice === "not_sure" ? null : choice === item.correct_index,
      confidence: o.confidence ?? null, hint_used: o.hint ?? false, latency_ms: 4000, at: when,
    });
    return choice;
  };

  // ---- Week 1 check (8 items, 2 per topic)
  const ob = (id: string) => itemById(id);
  const week1: [string, "right" | "wrong" | "not_sure"][] = [
    ["ob-causal-questions-1", "right"], ["ob-causal-questions-2", "right"],
    ["ob-potential-outcomes-1", "right"], ["ob-potential-outcomes-2", "wrong"],
    ["ob-selection-bias-1", "wrong"], ["ob-selection-bias-2", "not_sure"],
    ["ob-randomization-1", "right"], ["ob-randomization-2", "not_sure"],
  ];
  week1.forEach(([id, how], i) => {
    const c = add(ob(id), how, at(1, 1, 10) + i * 40_000);
    s.onboarding.answers[id] = c;
  });
  s.onboarding.done = true;
  for (const topic of FIX.course.topics) {
    const r = onboardingLevel(topic, FIX.items, s.onboarding.answers);
    s.levels[topic.id] = {
      topic_id: topic.id, level: r.level, source: "model", suggested_level: r.level, reason: r.reason, not_checked: r.notChecked,
      history: [{ level: r.level, source: "model", at: at(1, 1, 10), cause: "onboarding" }],
    };
  }

  // ---- Weeks 2–6: watch each video, answer its checkpoint, answer the next-day check
  type View = { video: string; week: number; day: number; cp: "right" | "wrong"; conf: Confidence; hint?: boolean; jol: Jol | null; ns: "right" | "wrong" };
  const views: View[] = [
    { video: "ku-reading-difference-table", week: 2, day: 1, cp: "right", conf: "certain", jol: "yes", ns: "right" },
    { video: "ku-potential-outcomes", week: 3, day: 1, cp: "right", conf: "pretty", jol: "maybe", ns: "right" },
    { video: "ku-selection-bias-general-formula", week: 4, day: 1, cp: "right", conf: "pretty", jol: "maybe", ns: "right" },
    { video: "ku-coin-toss-average-causal-effect", week: 5, day: 1, cp: "wrong", conf: "certain", jol: "yes", ns: "wrong" },
    // two watched again (Watch again re-asks the check)
    { video: "ku-potential-outcomes", week: 5, day: 3, cp: "right", conf: "certain", jol: null, ns: "right" },
    { video: "ku-coin-toss-average-causal-effect", week: 6, day: 1, cp: "wrong", conf: "guess", jol: null, ns: "wrong" },
    { video: "ku-selection-bias-general-formula", week: 6, day: 2, cp: "wrong", conf: "guess", jol: null, ns: "right" },
  ];
  for (const v of views) {
    const video = videoById(v.video);
    const t = at(v.week, v.day);
    add(itemById(video.checkpoint.item_id), v.cp, t, { confidence: v.conf, hint: v.hint });
    const w = s.watched[v.video];
    s.watched[v.video] = w ? { ...w, last_at: t, views: w.views + 1 } : { first_at: t, last_at: t, views: 1 };
    if (v.jol) {
      // only the first view of a video carries a next-day check in the story
      const task = createTask(video, t, FIX.course.config);
      task.jol = v.jol;
      task.done = true;
      const nsItem = itemById(video.next_session_item_id);
      const choice = add(nsItem, v.ns, t + 1 * DAY);
      task.result = { choice: choice as number, correct: v.ns === "right", at: t + 1 * DAY };
      s.next_session.push(task);
    } else {
      add(itemById(video.next_session_item_id), v.ns, t + 1 * DAY);
    }
  }

  // The student has not yet rated the videos' difficulty except two.
  s.difficulty["ku-potential-outcomes"] = "just_right";
  s.difficulty["ku-coin-toss-average-causal-effect"] = "too_hard";

  if (variant === "results") {
    // The Week 7 re-check was taken: Causal 1/1 right, Potential 2/2 right, Selection 2/2 right, Randomization 1/1 right.
    const rc: [string, "right" | "wrong"][] = [
      ["rc-causal-questions-1", "right"], ["rc-potential-outcomes-1", "right"], ["rc-potential-outcomes-2", "right"],
      ["rc-selection-bias-1", "right"], ["rc-selection-bias-2", "right"], ["rc-randomization-1", "right"],
    ];
    rc.forEach(([id, how], i) => {
      const c = add(itemById(id), how, nowMs - 2 * 60_000 + i * 10_000);
      s.recheck.answers[id] = c;
    });
    s.recheck.invite_seen_at = nowMs - 10 * 60_000;
  }
  s.responses = responses;

  // ---- the playlist the student has been following, rebuilt for Week 7
  s.playlist = buildPlaylistState({
    course: FIX.course, videos: FIX.videos, items: FIX.items, levels: s.levels, responses: s.responses, watched: s.watched,
    review: {}, prev: [], known: [], added: [], week: 7,
  });
  for (const e of s.playlist.entries) e.state = s.watched[e.video_id] ? "watched" : "todo";

  // a note and a claim verdict, so Notes and the Course map have something in them
  s.notes.push({ id: uid("note"), video_id: "ku-potential-outcomes", video_t: 18, text: "Y1 vs Y0: same person, two worlds.", at: at(3, 1) });
  const verdict: ClaimVerdictRecord = { video_id: "ku-potential-outcomes", claim_idx: 0, verdict: "matches", note: "", at: at(3, 1) };
  s.claims["ku-potential-outcomes:0"] = verdict;

  if (variant === "results") {
    s.recheck.proposals = proposeLevels({
      course: FIX.course, items: FIX.items, videos: FIX.videos, responses: s.responses, levels: s.levels, watched: s.watched,
      semesterStart: s.semester_start, now: nowMs,
    });
    s.recheck.status = "done";
  }
  return s;
}
