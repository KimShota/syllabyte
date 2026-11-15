import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const haveFixtures = existsSync(resolve(__dirname, "../fixtures/bank.json"));

describe.skipIf(!haveFixtures)("misconception clips", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let fx: typeof import("../src/fixtures");
  let mc: typeof import("../src/api/misconception");
  let ctx: { sessionId: string; courseId: string };

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    fx = await import("../src/fixtures");
    mc = await import("../src/api/misconception");
    store.resetState();
    fx.setFixtures(fx.FIX);
    ctx = { sessionId: `learning-${Math.random().toString(36).slice(2)}`, courseId: fx.FIX.course.id };
  });
  afterEach(() => fx.setFixtures(fx.FIX));

  const video = () => fx.FIX.videos[0];
  const item = () => fx.FIX.items.find((i) => i.id === video().checkpoint.item_id)!;
  const wrong = () => (item().correct_index + 1) % item().options.length;
  const answer = (choice: number, confidence: "certain" | "pretty" | "guess", attemptId: string, hintUsed = false) =>
    api.postCheckpointAnswer({ attemptId, learning: ctx, videoId: video().id, choice, confidence, hintUsed, latencyMs: 800 });
  const requests = () => store.getState().misconception_requests;

  /** The clip the server would add to the course once the worker made it. */
  const withClip = (choice: number, check = true) => {
    const checkItem = fx.FIX.items.find((i) => i.id === fx.FIX.videos[1].checkpoint.item_id)!;
    fx.setFixtures({
      ...fx.FIX,
      misconception_clips: [{ key: mc.misconceptionKey(item().id, choice), item_id: item().id, choice, video: fx.FIX.videos[1], check_item: check ? checkItem : null }],
    });
    return checkItem;
  };

  it("a wrong answer given as Certain (no hint) requests a clip for that question and option, once", async () => {
    await answer(wrong(), "certain", "a-1");
    expect(requests()).toEqual([
      expect.objectContaining({ key: `${item().id}|${wrong()}`, item_id: item().id, choice: wrong(), video_id: video().id, ku_id: video().ku_id,
        level: video().file_level, session_id: ctx.sessionId, offered_at: null, action: null, follow_up: null }),
    ]);
    await answer(wrong(), "certain", "a-2"); // the same mistake again: the same clip, no second request
    expect(requests()).toHaveLength(1);
  });

  it("no clip for a right answer, a wrong answer that wasn't certain, or one given after a hint", async () => {
    await answer(item().correct_index, "certain", "a-1");
    await answer(wrong(), "pretty", "a-2");
    await answer(wrong(), "guess", "a-3");
    await answer(wrong(), "certain", "a-4", true);
    expect(requests()).toEqual([]);
  });

  it("offers a clip only once it is made, until it is watched", async () => {
    await answer(wrong(), "certain", "a-1");
    expect(await api.getMisconceptionClips(ctx)).toEqual([]); // not made yet
    withClip(wrong());
    const [ready] = await api.getMisconceptionClips(ctx);
    expect(ready.clip.key).toBe(`${item().id}|${wrong()}`);
    expect(ready.item_title).toBe(video().short_title);

    await api.respondToMisconceptionClip(ctx, ready.request.id, { offered: true, action: "later" });
    expect(await api.getMisconceptionClips(ctx)).toHaveLength(1); // "later": still offered
    await api.respondToMisconceptionClip(ctx, ready.request.id, { offered: true, action: "watched" });
    await api.respondToMisconceptionClip(ctx, ready.request.id, { action: "later" }); // "watched" stands
    expect(requests()[0]).toMatchObject({ action: "watched" });
    expect(requests()[0].offered_at).not.toBeNull();
    expect(await api.getMisconceptionClips(ctx)).toEqual([]);
  });

  it("records the follow-up answer once; a clip without a question refuses it", async () => {
    await answer(wrong(), "certain", "a-1");
    const check = withClip(wrong());
    const [ready] = await api.getMisconceptionClips(ctx);
    const first = await api.answerMisconceptionCheck(ctx, ready.request.id, check.correct_index);
    expect(first).toMatchObject({ correct: true, correct_index: check.correct_index });
    await api.answerMisconceptionCheck(ctx, ready.request.id, (check.correct_index + 1) % check.options.length); // a retry: first stands
    expect(requests()[0].follow_up).toMatchObject({ choice: check.correct_index, correct: true });
    await expect(api.answerMisconceptionCheck(ctx, ready.request.id, 99)).rejects.toThrow(/Invalid/);

    withClip(wrong(), false);
    await expect(api.answerMisconceptionCheck(ctx, ready.request.id, 0)).rejects.toThrow(/no follow-up/);
  });

  it("a clip made for a different wrong option is not offered", async () => {
    await answer(wrong(), "certain", "a-1");
    withClip((wrong() + 1) % item().options.length === item().correct_index ? (wrong() + 2) % item().options.length : (wrong() + 1) % item().options.length);
    expect(await api.getMisconceptionClips(ctx)).toEqual([]);
  });

  it("requests are part of the student's data download", async () => {
    await answer(wrong(), "certain", "a-1");
    const data = await api.exportMyData();
    expect(data.misconception_requests).toHaveLength(1);
  });
});
