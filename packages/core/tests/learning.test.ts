import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { learningFeedback } from "../src/learning";
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
  });

  it("a check-in must point at a checkpoint answer from the same session", async () => {
    const { responseId } = await answer(wrong(), "pretty");
    await expect(api.postLearningCheckIn({ ...ctx, sessionId: "learning-other", responseId, difficulty: "too_hard", attention: null })).rejects.toThrow(/not found/);
    await expect(api.postLearningCheckIn({ ...ctx, responseId, difficulty: "impossible" as never, attention: null })).rejects.toThrow(/Invalid/);
  });

  it("the reflection of an empty session says so honestly", async () => {
    const r = await api.getLearningReflection(ctx);
    expect(r).toMatchObject({ answers: 0, videos: [], checkIns: [], elapsedSeconds: 0 });
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
