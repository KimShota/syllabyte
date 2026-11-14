import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { feedbackRecap, learningFeedback } from "../src/learning";
import type { PlaybackSnapshot } from "../src/learning";
import { PlaybackMeter, coveredSeconds, mergeIntervals } from "../src/logic/playback";

describe("playback intervals", () => {
  it("merges overlapping and touching intervals, in any order", () => {
    expect(mergeIntervals([[5, 8], [0, 3], [2, 4], [8, 9]])).toEqual([[0, 4], [5, 9]]);
    expect(coveredSeconds([[0, 10], [5, 15], [20, 21]])).toBe(16);
  });
});

describe("PlaybackMeter", () => {
  /** Plays from `from` for `seconds` of wall time at `rate`, sampled every 250 ms. Returns the next wall time. */
  function play(m: PlaybackMeter, from: number, seconds: number, at: number, rate = 1): number {
    for (let i = 0; i <= seconds * 4; i++) m.sample(from + (i / 4) * rate, at + i * 250, true, rate);
    return at + seconds * 4 * 250;
  }

  it("counts what actually played; seeking to the end covers nothing", () => {
    const m = new PlaybackMeter(60, "video");
    let at = play(m, 0, 10, 0);
    m.boundary(); // a seek
    m.sample(59, at + 250, true, 1);
    at = play(m, 59, 1, at + 250);
    const s = m.snapshot();
    expect(coveredSeconds(s.intervals)).toBeCloseTo(11, 5);
    expect(s.exposure_s).toBeCloseTo(11, 5);
  });

  it("never counts a jump between two samples as playback, even without a boundary", () => {
    const m = new PlaybackMeter(60, "video");
    m.sample(0, 0, true, 1);
    m.sample(30, 250, true, 1); // a native seek the app didn't see
    expect(m.snapshot().exposure_s).toBe(0);
  });

  it("a replay adds exposure but not unique coverage", () => {
    const m = new PlaybackMeter(60, "video");
    let at = play(m, 0, 10, 0);
    m.boundary();
    at = play(m, 5, 5, at + 1000);
    const s = m.snapshot();
    expect(coveredSeconds(s.intervals)).toBeCloseTo(10, 5);
    expect(s.exposure_s).toBeCloseTo(15, 5);
  });

  it("at 2x, content advances twice as fast as elapsed time", () => {
    const m = new PlaybackMeter(60, "video");
    play(m, 0, 5, 0, 2);
    const s = m.snapshot();
    expect(s.exposure_s).toBeCloseTo(10, 5);
    expect(s.elapsed_s).toBeCloseTo(5, 5);
  });

  it("does not count paused samples or a long gap between callbacks (background, buffering)", () => {
    const m = new PlaybackMeter(60, "video");
    m.sample(0, 0, false, 1);
    m.sample(0.25, 250, false, 1);
    expect(m.snapshot().sequence).toBe(0);
    m.sample(1, 1000, true, 1);
    m.sample(4, 4000, true, 1); // 3 s between callbacks: unknown, not playback
    expect(m.snapshot().exposure_s).toBe(0);
  });

  it("ignores a rate change mid-step and non-finite input", () => {
    const m = new PlaybackMeter(60, "video");
    m.sample(0, 0, true, 1);
    m.sample(0.5, 250, true, 2);
    m.sample(Number.NaN, 500, true, 2);
    m.sample(1, 750, true, 2);
    expect(m.snapshot().exposure_s).toBe(0);
  });
});

describe("learningFeedback rules", () => {
  const base = { correct: true, confidence: "pretty", hintUsed: false, difficulty: null, attention: null, replaySeconds: 0, replayFrom: 12 } as const;

  it("a reported attention drift comes first, whatever the answer", () => {
    expect(learningFeedback({ ...base, correct: false, confidence: "certain", attention: "drifted" }).rule).toBe("attention_recovery");
  });
  it("a wrong answer found difficult gets support; with certainty too it is one combined card", () => {
    const hard = learningFeedback({ ...base, correct: false, difficulty: "too_hard" });
    expect(hard.rule).toBe("difficulty_support");
    const both = learningFeedback({ ...base, correct: false, difficulty: "too_hard", confidence: "certain" });
    expect(both.rule).toBe("difficulty_support");
    expect(both.message).toMatch(/certain/);
    expect(both.message).toMatch(/difficult/);
  });
  it("a wrong answer given with certainty, without a hint, is a confidence mismatch", () => {
    expect(learningFeedback({ ...base, correct: false, confidence: "certain" }).rule).toBe("confidence_mismatch");
    expect(learningFeedback({ ...base, correct: false, confidence: "certain", hintUsed: true }).rule).toBe("reflection");
  });
  it("replay alone is not evidence of anything; replay plus a correct answer is acknowledged", () => {
    expect(learningFeedback({ ...base, correct: false, replaySeconds: 30 }).rule).toBe("reflection");
    expect(learningFeedback({ ...base, replaySeconds: 30 }).rule).toBe("review_acknowledgment");
  });
  it("recaps every rule without pointing at the checkpoint card", () => {
    for (const rule of ["attention_recovery", "difficulty_support", "confidence_mismatch", "review_acknowledgment", "reflection"] as const) {
      expect(feedbackRecap(rule, { confidence: "pretty", hintUsed: false })).not.toMatch(/above/);
    }
    expect(feedbackRecap("difficulty_support", { confidence: "certain", hintUsed: true })).not.toMatch(/certain/);
  });
  it("carries the replay target and a policy version", () => {
    expect(learningFeedback(base)).toMatchObject({ replayFrom: 12, policyVersion: "1" });
  });
});

// The API half runs the real mock API against the generated fixtures, which are local-only (course material).
const haveFixtures = existsSync(resolve(__dirname, "../fixtures/bank.json"));

describe.skipIf(!haveFixtures)("learning API", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let FIX: typeof import("../src/fixtures").FIX;
  let ctx: { sessionId: string; courseId: string };

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    FIX = (await import("../src/fixtures")).FIX;
    store.resetState();
    ctx = { sessionId: `learning-${Math.random().toString(36).slice(2)}`, courseId: FIX.course.id };
  });

  const snap = (duration: number, intervals: [number, number][], sequence: number, source: PlaybackSnapshot["source"] = "video", extra = 0): PlaybackSnapshot => {
    const unique = coveredSeconds(intervals);
    return { sequence, intervals, elapsed_s: unique + extra, exposure_s: unique + extra, position_s: intervals.at(-1)?.[1] ?? 0, duration_s: duration, source };
  };
  const vid = () => FIX.videos[0];
  const item = () => FIX.items.find((i) => i.id === vid().checkpoint.item_id)!;
  const answer = (choice: number, confidence: "certain" | "pretty" | "guess", attemptId = "attempt-1") =>
    api.postCheckpointAnswer({ attemptId, learning: ctx, videoId: vid().id, choice, confidence, hintUsed: false, latencyMs: 1200 });
  const wrong = () => (item().correct_index + 1) % item().options.length;

  it("a video counts as watched at 90% unique coverage, once, and not from a seek to the end", async () => {
    const d = vid().duration_s;
    let r = await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(d, [[0, d * 0.3], [d * 0.95, d]], 1) });
    expect(r.completedNow).toBe(false);
    expect(store.getState().watched[vid().id]).toBeUndefined();
    r = await api.recordLearningPlayback({ ...ctx, playbackId: "playback-b", videoId: vid().id, snapshot: snap(d, [[d * 0.3, d * 0.9]], 1) });
    expect(r.completedNow).toBe(true);
    expect(store.getState().watched[vid().id]?.views).toBe(1);
    // more playback, or the same snapshot again, never counts a second view
    r = await api.recordLearningPlayback({ ...ctx, playbackId: "playback-b", videoId: vid().id, snapshot: snap(d, [[d * 0.3, d]], 2) });
    expect(r.completedNow).toBe(false);
    expect(store.getState().watched[vid().id]?.views).toBe(1);
  });

  it("real and stand-in playback don't add up to a completion", async () => {
    const d = vid().duration_s;
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(d, [[0, d * 0.5]], 1, "video") });
    const r = await api.recordLearningPlayback({ ...ctx, playbackId: "playback-b", videoId: vid().id, snapshot: snap(d, [[d * 0.5, d]], 1, "demo") });
    expect(r.completedNow).toBe(false);
  });

  it("duplicate and out-of-order snapshots are harmless; a snapshot that goes backwards is refused", async () => {
    const d = vid().duration_s;
    const input = (s: PlaybackSnapshot) => ({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: s });
    await api.recordLearningPlayback(input(snap(d, [[0, 20]], 5)));
    await api.recordLearningPlayback(input(snap(d, [[0, 10]], 3))); // older, arrived late: ignored
    await api.recordLearningPlayback(input(snap(d, [[0, 20]], 5))); // a retry
    const saved = store.getState().learning_sessions[ctx.sessionId].playback["playback-a"];
    expect(saved.snapshot.intervals).toEqual([[0, 20]]);
    await expect(api.recordLearningPlayback(input(snap(d, [[0, 5]], 6)))).rejects.toThrow(/backwards/);
  });

  it("refuses impossible observations and another course's session", async () => {
    const d = vid().duration_s;
    const bad = { ...snap(d, [[0, 20]], 1), exposure_s: 5 }; // covers more than it traversed
    await expect(api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: bad })).rejects.toThrow(/Invalid/);
    await expect(api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(d + 30, [[0, 20]], 1) })).rejects.toThrow(/Invalid/);
    await expect(
      api.recordLearningPlayback({ sessionId: ctx.sessionId, courseId: "another-course", playbackId: "playback-a", videoId: vid().id, snapshot: snap(d, [[0, 20]], 1) }),
    ).rejects.toThrow(/course changed/);
    await expect(api.recordLearningPlayback({ ...ctx, sessionId: "__proto__", playbackId: "playback-a", videoId: vid().id, snapshot: snap(d, [[0, 20]], 1) })).rejects.toThrow();
  });

  it("saving playback does not wake the screens; completing a video does", async () => {
    const d = vid().duration_s;
    let woken = 0;
    const off = store.subscribe(() => (woken += 1));
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(d, [[0, 10]], 1) });
    expect(woken).toBe(0);
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(d, [[0, d]], 2) });
    expect(woken).toBeGreaterThan(0);
    off();
  });

  it("a retried checkpoint answer is saved once; a changed retry is refused", async () => {
    const first = await answer(wrong(), "certain");
    const again = await answer(wrong(), "certain");
    expect(again.responseId).toBe(first.responseId);
    expect(store.getState().responses.filter((r) => r.attempt_id === "attempt-1")).toHaveLength(1);
    await expect(answer(item().correct_index, "certain")).rejects.toThrow(/changed/);
    await expect(answer(99, "certain", "attempt-2")).rejects.toThrow(/Invalid/);
  });

  it("observation → certain wrong answer → 'difficult' check-in → one combined card → replay → reflection", async () => {
    const d = vid().duration_s;
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(d, [[0, d * 0.5]], 1) });
    const { responseId, correct } = await answer(wrong(), "certain");
    expect(correct).toBe(false);

    const check = await api.postLearningCheckIn({ ...ctx, responseId, difficulty: "too_hard", attention: null });
    expect(check.feedback.rule).toBe("difficulty_support");
    expect(check.feedback.replayFrom).toBe(vid().checkpoint.rewatch_from);
    // a retry returns the same check-in; a different one for the same answer is refused
    expect((await api.postLearningCheckIn({ ...ctx, responseId, difficulty: "too_hard", attention: null })).id).toBe(check.id);
    await expect(api.postLearningCheckIn({ ...ctx, responseId, difficulty: "just_right", attention: null })).rejects.toThrow();

    await api.recordLearningFeedbackAction(ctx, check.id, "replay");
    await api.recordLearningFeedbackAction(ctx, check.id, "continue"); // the first choice stands
    const r = await api.getLearningReflection(ctx);
    expect(r.answers).toBe(1);
    expect(r.correct).toBe(0);
    expect(r.certainAnswers).toBe(1);
    expect(r.certainCorrect).toBe(0);
    expect(r.checkIns).toHaveLength(1);
    expect(r.checkIns[0].action).toBe("replay");
    expect(r.videos).toEqual([expect.objectContaining({ id: vid().id, coverage: expect.closeTo(0.5, 5), synthetic: false, completed: false })]);
    expect(r.nextStep).toMatch(/^Rewatch the part of/);
    // the recap reads on its own: the card's "explanation above" is not on the reflection page
    expect(r.checkIns[0].recap).toBe("You felt certain and found this part difficult, and the answer was incorrect.");
    expect(r.checkIns[0].videoTitle).toBe(vid().short_title);
  });

  it("videos only swiped past are counted, not listed, and never suggested as the next step", async () => {
    const [a, b, c] = FIX.videos;
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: a.id, snapshot: snap(a.duration_s, [[0, 30]], 1) });
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-b", videoId: b.id, snapshot: snap(b.duration_s, [[0, 3]], 1) });
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-c", videoId: c.id, snapshot: snap(c.duration_s, [[0, 4]], 1) });
    const r = await api.getLearningReflection(ctx);
    expect(r.videos.map((v) => v.id)).toEqual([a.id]);
    expect(r.glanced).toBe(2);
    expect(r.nextStep).toContain(a.short_title);
    expect(r.elapsedSeconds).toBeCloseTo(37, 5); // glanced playback still counts toward the total
  });

  it("a briefly played video stays listed when its checkpoint was answered", async () => {
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(vid().duration_s, [[0, 5]], 1) });
    await answer(item().correct_index, "pretty");
    const r = await api.getLearningReflection(ctx);
    expect(r.videos.map((v) => v.id)).toEqual([vid().id]);
    expect(r.glanced).toBe(0);
  });

  it("a check-in must point at a checkpoint answer from the same session", async () => {
    const { responseId } = await answer(wrong(), "pretty");
    await expect(api.postLearningCheckIn({ ...ctx, sessionId: "learning-other", responseId, difficulty: "too_hard", attention: null })).rejects.toThrow(/not found/);
    await expect(api.postLearningCheckIn({ ...ctx, responseId, difficulty: "impossible" as never, attention: null })).rejects.toThrow(/Invalid/);
  });

  it("the reflection of an empty session says so honestly", async () => {
    const r = await api.getLearningReflection(ctx);
    expect(r).toMatchObject({ answers: 0, videos: [], glanced: 0, checkIns: [], elapsedSeconds: 0 });
    expect(r.nextStep).toMatch(/^Watch a video/);
  });

  it("the reflection marks stand-in playback and suggests finishing an unfinished video", async () => {
    const d = vid().duration_s;
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(d, [[0, d * 0.4]], 1, "demo") });
    const r = await api.getLearningReflection(ctx);
    expect(r.videos[0]).toMatchObject({ synthetic: true, completed: false });
    expect(r.nextStep).toMatch(/^Finish/);
  });

  it("learning sessions are part of the student's data download", async () => {
    await api.recordLearningPlayback({ ...ctx, playbackId: "playback-a", videoId: vid().id, snapshot: snap(vid().duration_s, [[0, 10]], 1) });
    const data = await api.exportMyData();
    expect(Object.keys(data.learning_sessions as Record<string, unknown>)).toContain(ctx.sessionId);
  });
});

describe.skipIf(!haveFixtures)("automatic prompts and the session reflection", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let FIX: typeof import("../src/fixtures").FIX;
  let ctx: { sessionId: string; courseId: string };
  const MIN = 60_000;

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    FIX = (await import("../src/fixtures")).FIX;
    store.resetState();
    ctx = { sessionId: `learning-${Math.random().toString(36).slice(2)}`, courseId: FIX.course.id };
  });

  /** Moves the app's clock on, as the demo's "simulate next day" does. */
  const later = (ms: number) => store.mutate((s) => { s.clock_offset_ms += ms; });
  const play = (i: number, upTo: number, id = `playback-${i}`) => {
    const v = FIX.videos[i];
    const end = Math.min(upTo, v.duration_s);
    return api.recordLearningPlayback({ ...ctx, playbackId: id, videoId: v.id,
      snapshot: { sequence: 1, intervals: end > 0 ? [[0, end]] : [], elapsed_s: end, exposure_s: end, position_s: end, duration_s: v.duration_s, source: "video" } });
  };
  const answerWrongCertain = (i: number) => {
    const v = FIX.videos[i];
    const item = FIX.items.find((x) => x.id === v.checkpoint.item_id)!;
    return api.postCheckpointAnswer({ attemptId: `attempt-${i}`, learning: ctx, videoId: v.id, choice: (item.correct_index + 1) % item.options.length, confidence: "certain", hintUsed: false, latencyMs: 900 });
  };

  it("after a video watched and three left early, the move to the next video offers a drift check recalling the watched one", async () => {
    await play(0, FIX.videos[0].duration_s * 0.7);
    for (const i of [1, 2, 3]) { later(1000); await play(i, 3); }
    later(1000);
    const p = await api.evaluateLearningBoundary(ctx, { reason: "next_video", videoId: FIX.videos[1].id }); // back to one seen before
    expect(p).toMatchObject({ kind: "drift_check", evidence: ["early_leaves:3"], observation: "You moved on early from the last 3 videos.", answer: null, action: null });
    expect(p!.recall?.videoId).toBe(FIX.videos[0].id);
    expect(p!.recall!.points.length).toBeGreaterThan(0);
    // nothing new since: no second prompt
    expect(await api.evaluateLearningBoundary(ctx, { reason: "next_video", videoId: FIX.videos[2].id })).toBeNull();

    await api.respondToLearningPrompt(ctx, p!.id, { answer: "drifted" });
    await api.respondToLearningPrompt(ctx, p!.id, { answer: "on_task", action: "rewatch" }); // the first answer stands
    const saved = store.getState().learning_sessions[ctx.sessionId].prompts![0];
    expect(saved).toMatchObject({ answer: "drifted", action: "rewatch", policyVersion: "drift-1" });
  });

  it("swiping straight through (videos that never played) counts as moving on early too", async () => {
    for (const i of [1, 2, 3]) { later(1000); await play(i, 0); }
    later(1000);
    expect((await api.evaluateLearningBoundary(ctx, { reason: "next_video", videoId: FIX.videos[0].id }))?.kind).toBe("drift_check");
  });

  it("coming back after a minute or more, partway through a video, offers a recall of what came before", async () => {
    const v = FIX.videos.find((x) => x.duration_s > 60)!;
    const i = FIX.videos.indexOf(v);
    await play(i, 45);
    await api.recordLearningAway(ctx, { seconds: 120, videoId: v.id });
    const p = await api.evaluateLearningBoundary(ctx, { reason: "return", videoId: v.id });
    expect(p?.kind).toBe("welcome_back");
    expect(p!.observation).toBe(`Welcome back. You were 0:45 into “${v.short_title}”.`);
    expect(p!.recall?.replayFrom).toBeLessThanOrEqual(45);
    // a short absence: carry on
    await api.recordLearningAway(ctx, { seconds: 20, videoId: v.id });
    expect(await api.evaluateLearningBoundary(ctx, { reason: "return", videoId: v.id })).toBeNull();
    await expect(api.recordLearningAway(ctx, { seconds: -1, videoId: v.id })).rejects.toThrow(/Invalid/);
  });

  it("ending a session with a certain wrong answer leaves a reflection to show once; nothing is shown for an empty one", async () => {
    await play(0, 40);
    await answerWrongCertain(0);
    const summary = await api.finishLearningSession(ctx, "left");
    expect(summary).toMatchObject({ sessionId: ctx.sessionId, reason: "left" });
    expect(summary!.observation).toBe(`You felt certain on the check in “${FIX.videos[0].short_title}”, but the answer was incorrect.`);
    expect(summary!.nextStep).toMatch(/^Rewatch the part of/);
    expect(summary!.stats).toMatch(/0 of 1 check right/);
    expect(await api.finishLearningSession(ctx, "left")).toEqual(summary); // idempotent
    expect(await api.getPendingReflection()).toEqual(summary);
    await api.dismissReflection(ctx.sessionId);
    expect(await api.getPendingReflection()).toBeNull();

    const empty = { ...ctx, sessionId: "learning-empty" };
    await api.recordLearningPlayback({ ...empty, playbackId: "playback-x", videoId: FIX.videos[1].id,
      snapshot: { sequence: 1, intervals: [[0, 4]], elapsed_s: 4, exposure_s: 4, position_s: 4, duration_s: FIX.videos[1].duration_s, source: "video" } });
    expect(await api.finishLearningSession(empty, "left")).toBeNull();
    expect(await api.getPendingReflection()).toBeNull();
  });

  it("a session left idle for 10 minutes (the app was closed) ends by itself, and its reflection waits for the next open", async () => {
    await play(0, 40);
    await answerWrongCertain(0);
    expect(await api.getPendingReflection()).toBeNull(); // still going
    later(11 * MIN);
    const pending = await api.getPendingReflection();
    expect(pending).toMatchObject({ sessionId: ctx.sessionId, reason: "gap" });
    // an ended session offers no more prompts
    expect(await api.evaluateLearningBoundary(ctx, { reason: "next_video", videoId: FIX.videos[1].id })).toBeNull();
  });

  it("of several sessions ended together after the app was closed, the most recently active one is shown", async () => {
    const first = ctx;
    await play(0, 40);
    await answerWrongCertain(0);
    later(1000);
    ctx = { ...ctx, sessionId: "learning-later" };
    await play(1, 40);
    await answerWrongCertain(1);
    later(11 * MIN);
    expect((await api.getPendingReflection())?.sessionId).toBe("learning-later");
    await api.dismissReflection("learning-later");
    expect(await api.getPendingReflection()).toBeNull();
    expect(store.getState().learning_sessions[first.sessionId].summarySeenAt).not.toBeNull();
  });

  it("only the latest waiting reflection is shown; dismissing it clears older ones", async () => {
    const first = ctx;
    await play(0, 40);
    await answerWrongCertain(0);
    await api.finishLearningSession(first, "left");
    later(1000);
    ctx = { ...ctx, sessionId: "learning-second" };
    await play(1, 40);
    await answerWrongCertain(1);
    await api.finishLearningSession(ctx, "left");
    expect((await api.getPendingReflection())?.sessionId).toBe("learning-second");
    await api.dismissReflection("learning-second");
    expect(await api.getPendingReflection()).toBeNull();
    expect(store.getState().learning_sessions[first.sessionId].summarySeenAt).not.toBeNull();
  });

  it("right answers given while unsure are named as competence", async () => {
    for (const i of [0, 1]) {
      const v = FIX.videos[i];
      const item = FIX.items.find((x) => x.id === v.checkpoint.item_id)!;
      await play(i, 30);
      await api.postCheckpointAnswer({ attemptId: `attempt-${i}`, learning: ctx, videoId: v.id, choice: item.correct_index, confidence: "pretty", hintUsed: false, latencyMs: 900 });
    }
    const s = await api.finishLearningSession(ctx, "left");
    expect(s!.observation).toBe("You answered 2 checks right even when you weren't sure.");
    expect(s!.nextStep).toMatch(/you know more than you felt/);
  });
});
