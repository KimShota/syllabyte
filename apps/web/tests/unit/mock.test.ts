import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

// These exercise the real mock API against the generated fixtures, which are local-only
// (course material). Without them the suite skips rather than failing a fresh clone.
const haveFixtures = existsSync(resolve(__dirname, "../../fixtures/videos.json"));

describe.skipIf(!haveFixtures)("mock API with the real fixtures", () => {
  let api: typeof import("@/lib/api/client").api;
  let store: typeof import("@/lib/store");
  let demo: typeof import("@/lib/api/demo");
  let FIX: typeof import("@/lib/fixtures").FIX;

  beforeEach(async () => {
    api = (await import("@/lib/api/client")).api;
    store = await import("@/lib/store");
    demo = await import("@/lib/api/demo");
    FIX = (await import("@/lib/fixtures")).FIX;
    store.resetState();
  });

  async function onboardWith(how: "right" | "not_sure") {
    const items = await api.getOnboardingItems();
    for (const v of items) await api.answerOnboarding(v.item.id, how === "right" ? v.item.correct_index : "not_sure", 1000);
    await api.finishOnboarding();
  }

  it("has the shape the plan promises: 8 onboarding items, 6 re-check items, one checkpoint per video", async () => {
    expect((await api.getOnboardingItems()).length).toBe(8);
    expect((await api.getRecheckItems()).length).toBe(6);
    for (const v of FIX.videos) {
      expect(v.checkpoint.t).toBeGreaterThan(v.checkpoint.rewatch_from);
      expect(v.claims.length).toBeGreaterThanOrEqual(3);
      expect(FIX.items.find((i) => i.id === v.checkpoint.item_id)?.allows_not_sure).toBe(false);
    }
  });

  it("onboarding spreads questions across topics", async () => {
    const items = await api.getOnboardingItems();
    expect(new Set(items.slice(0, 4).map((i) => i.item.topic_id)).size).toBe(4);
  });

  it("a student who aces onboarding is Level 3 overall and only sees the upcoming lecture's new video", async () => {
    await onboardWith("right");
    const r = await api.getOnboardingResult();
    expect(r.overall_level).toBe(3);
    const pl = await api.getPlaylist();
    expect(pl.cards.map((c) => c.tag)).toEqual(["new"]);
    expect(pl.why).toMatch(/^Lecture 3 is next/);
  });

  it("a student who answers 'Not sure' everywhere is Level 1 with every video as a gap, upcoming lecture first", async () => {
    await onboardWith("not_sure");
    const pl = await api.getPlaylist();
    expect(pl.overall_level).toBe(1);
    expect(pl.cards.length).toBe(4);
    expect(pl.cards.every((c) => c.tag === "gap")).toBe(true);
    expect(pl.cards[0].lecture_n).toBe(3);
    expect(pl.why).toContain("as gaps");
  });

  it("serves the nearest existing version and says so (Level 3 topic, only a Level 2 file)", async () => {
    await onboardWith("right");
    const pl = await api.getPlaylist();
    expect(pl.cards[0].served_level).toBe(2);
    expect(pl.cards[0].fallback_note).toBe("Level 2 version · Level 3 coming soon");
  });

  it("skip, undo, reason, and prove-it behave as specified", async () => {
    await onboardWith("not_sure");
    const first = (await api.getPlaylist()).cards[0];
    await api.skip(first.entry_id!);
    let pl = await api.getPlaylist();
    expect(pl.skipped.map((c) => c.video_id)).toEqual([first.video_id]);
    await api.undoSkip(first.entry_id!);
    pl = await api.getPlaylist();
    expect(pl.skipped).toHaveLength(0);

    await api.skip(first.entry_id!);
    await api.setSkipReason(first.entry_id!, "already_know");
    const item = await api.getProveIt(first.video_id);
    const fail = await api.answerProveIt(first.entry_id!, (item.correct_index + 1) % 3);
    expect(fail.pass).toBe(false);
    expect((await api.getPlaylist()).skipped).toHaveLength(0); // back in the playlist
    await api.skip(first.entry_id!);
    const pass = await api.answerProveIt(first.entry_id!, item.correct_index);
    expect(pass.pass).toBe(true);
    expect((await api.getPlaylist()).skipped.map((c) => c.video_id)).toContain(first.video_id);
  });

  it("manual order wins until reset", async () => {
    await onboardWith("not_sure");
    const ids = (await api.getPlaylist()).cards.map((c) => c.entry_id!);
    await api.reorder([...ids].reverse());
    let pl = await api.getPlaylist();
    expect(pl.cards.map((c) => c.entry_id)).toEqual([...ids].reverse());
    expect(pl.why).toMatch(/^You set this order/);
    await api.resetOrder();
    pl = await api.getPlaylist();
    expect(pl.cards.map((c) => c.entry_id)).toEqual(ids);
  });

  it("a correct checkpoint answer rated 'Guessing' is queued for tomorrow; the next-session card waits 12 h and then appears once", async () => {
    await onboardWith("not_sure");
    const vid = FIX.videos[0];
    const item = FIX.items.find((i) => i.id === vid.checkpoint.item_id)!;
    const res = await api.postCheckpointAnswer({ videoId: vid.id, choice: item.correct_index, confidence: "guess", hintUsed: false, latencyMs: 900 });
    expect(res).toEqual({ correct: true, queuedForTomorrow: true });
    await api.markWatched(vid.id);
    await api.postJol(vid.id, "maybe");
    expect(await api.getNextSession()).toBeNull(); // not due yet
    demo.simulateNextDay();
    const card = await api.getNextSession();
    expect(card?.task.video_id).toBe(vid.id);
    expect(card?.task.flagged_guess).toBe(true);
    const wrong = await api.answerNextSession(card!.task.id, (card!.item.correct_index + 1) % 3);
    expect(wrong).toMatchObject({ correct: false, jol: "maybe" });
    expect(await api.getNextSession()).toBeNull();
  });

  it("claims: a 'does not match' verdict flags the video for everyone", async () => {
    await onboardWith("right");
    const vid = FIX.videos[0].id;
    expect((await api.getVariant(vid)).review_status).toBe("unreviewed");
    await api.postClaimVerdict(vid, 0, "mismatch", "not on the slide");
    expect((await api.getVariant(vid)).review_status).toBe("flagged");
  });

  it("add-to-playlist appends a 'you added' entry", async () => {
    await onboardWith("right");
    const other = FIX.videos.find((v) => v.lecture_n !== 3)!;
    await api.addToPlaylist(other.id);
    const pl = await api.getPlaylist();
    expect(pl.cards.find((c) => c.video_id === other.id)?.tag).toBe("you_added");
  });

  it("the tailoring receipt lists only real rows and counts the changes", async () => {
    await onboardWith("right");
    const v = await api.getVariant(FIX.videos[0].id);
    expect(v.tailoring.length).toBe(3);
    expect(v.changes_count).toBe(v.tailoring.filter((r) => r.kind !== "set_to").length);
  });
});

describe.skipIf(!haveFixtures)("scripted persona → Week 7 (plan §10)", () => {
  let api: typeof import("@/lib/api/client").api;
  let store: typeof import("@/lib/store");
  let demo: typeof import("@/lib/api/demo");

  beforeEach(async () => {
    api = (await import("@/lib/api/client")).api;
    store = await import("@/lib/store");
    demo = await import("@/lib/api/demo");
    store.resetState();
  });

  it("is in Week 7, and the real rules produce the intended story: two ups, one down, one unchanged", async () => {
    demo.loadPersona("results");
    expect((await api.getMe()).week).toBe(7);
    const { proposals } = await api.getProposals();
    const by = Object.fromEntries(proposals.map((p) => [p.topic_id, p]));
    expect(by["causal-questions"]).toMatchObject({ direction: "same", from: 3, to: 3 });
    expect(by["potential-outcomes"]).toMatchObject({ direction: "up", from: 2, to: 3 });
    expect(by["selection-bias"]).toMatchObject({ direction: "up", from: 1, to: 2 });
    expect(by["randomization"]).toMatchObject({ direction: "down", from: 2, to: 1 });
    expect(by["selection-bias"].reason).toContain("up from 0 of 1 in Week 1");
  });

  it("My levels shows both calibration blocks for the persona", async () => {
    demo.loadPersona("results");
    const c = await api.getCalibration();
    expect(c.block1.ready).toBe(true);
    expect(c.block1.sentences[0]).toMatch(/no better than “Pretty sure”/);
    expect(c.block1.sentences[1]).toMatch(/guesses were honest/);
    expect(c.block2.summary).toMatch(/^When you said Yes/);
  });

  it("invite variant is Week 7 with the re-check not yet taken", async () => {
    demo.loadPersona("invite");
    const s = await api.getRecheckStatus();
    expect(s).toMatchObject({ in_window: true, status: "idle", invite_seen: false });
    expect(s.slots.map((x) => x.id)).toContain("now");
  });

  it("applying: accepted levels change, kept ones don't, undo restores, 'keep old' changes nothing", async () => {
    demo.loadPersona("results");
    await api.decideProposal("potential-outcomes", "accepted", "");
    await api.decideProposal("selection-bias", "accepted", "");
    await api.decideProposal("randomization", "kept", "");
    await api.applyDecisions("apply");
    let levels = (await api.getLevels()).topics.map((t) => [t.topic.id, t.level.level]);
    expect(Object.fromEntries(levels)).toMatchObject({ "potential-outcomes": 3, "selection-bias": 2, randomization: 2, "causal-questions": 3 });
    const view = await api.getProposals();
    expect(view.applied?.summary).toMatchObject({ accepted: 2, kept: 1 });
    expect(view.undo_available).toBe(true);
    await api.undoApply();
    levels = (await api.getLevels()).topics.map((t) => [t.topic.id, t.level.level]);
    expect(Object.fromEntries(levels)).toMatchObject({ "potential-outcomes": 2, "selection-bias": 1 });

    await api.applyDecisions("keep_old");
    const after = (await api.getLevels()).topics.map((t) => t.level.level);
    expect(after).toEqual([3, 2, 1, 2]);
    expect((await api.getProposals()).proposals.filter((p) => p.direction === "up" || p.direction === "down").every((p) => p.decision === "kept")).toBe(true);
  });

  it("a proposal the student never decides is recorded as 'ignored' and changes nothing", async () => {
    demo.loadPersona("results");
    await api.applyDecisions("apply");
    const { proposals } = await api.getProposals();
    expect(proposals.find((p) => p.topic_id === "potential-outcomes")?.decision).toBe("ignored");
    expect((await api.getLevels()).topics.find((t) => t.topic.id === "potential-outcomes")?.level.level).toBe(2);
  });

  it("disputing keeps the level and stores the text", async () => {
    demo.loadPersona("results");
    await api.decideProposal("randomization", "disputed", "I was tired that day");
    await api.applyDecisions("apply");
    const p = (await api.getProposals()).proposals.find((x) => x.topic_id === "randomization")!;
    expect(p).toMatchObject({ decision: "disputed", dispute_text: "I was tired that day" });
    expect((await api.getLevels()).topics.find((t) => t.topic.id === "randomization")?.level.level).toBe(2);
  });

  it("the re-check can be scheduled and produces a calendar file", async () => {
    demo.loadPersona("invite");
    const r = await api.scheduleRecheck("tomorrow");
    expect(r.ics).toContain("BEGIN:VEVENT");
    expect((await api.getRecheckStatus()).status).toBe("scheduled");
    await api.skipRecheck();
    expect((await api.getLevels()).recheck_due).toBe(true);
  });

  it("finishing the re-check from scratch uses the real rule (few answers → not enough yet)", async () => {
    store.resetState();
    for (const v of await api.getOnboardingItems()) await api.answerOnboarding(v.item.id, "not_sure", 1);
    await api.finishOnboarding();
    for (const v of await api.getRecheckItems()) await api.answerRecheck(v.item.id, v.item.correct_index, 1);
    await api.finishRecheck();
    const { proposals } = await api.getProposals();
    expect(proposals.every((p) => p.direction === "not_enough" || p.direction === "same" || p.direction === "up")).toBe(true);
  });
});
