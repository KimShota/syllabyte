import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

// These exercise the real mock API against the generated fixtures, which are local-only
// (course material). Without them the suite skips rather than failing a fresh clone.
const haveFixtures = existsSync(resolve(__dirname, "../fixtures/bank.json"));

describe.skipIf(!haveFixtures)("mock API with the real fixtures", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let demo: typeof import("../src/api/demo");
  let FIX: typeof import("../src/fixtures").FIX;

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    demo = await import("../src/api/demo");
    FIX = (await import("../src/fixtures")).FIX;
    store.resetState();
  });

  /** Sit the Week 0 baseline answering every question the same way, through the real API. */
  async function onboardWith(how: "right" | "not_sure") {
    if (store.getState().consent === null) await api.postConsent(true);
    await demo.runSitting("week0", how === "right" ? demo.scriptedStudent({}, 9) : () => "not_sure");
  }

  const levelsOf = async () => Object.fromEntries((await api.getLevels()).lectures.flatMap((l) => l.rows).map((r) => [r.ku.id, r.level.level]));

  it("has the shape the plan promises: lecture topics, a 3-tier bank per KU, one checkpoint per video", async () => {
    expect(FIX.course.topics.map((t) => t.id)).toEqual(["lecture-1", "lecture-2", "lecture-3"]);
    for (const k of FIX.course.kus) {
      const tiers = FIX.items.filter((i) => i.ku_id === k.id && i.context === "assessment").map((i) => i.tier).sort();
      expect(tiers, k.id).toEqual(["advanced", "applied", "basic"]);
    }
    expect(FIX.items.some((i) => i.context === ("onboarding" as string))).toBe(false);
    for (const v of FIX.videos) {
      expect(v.checkpoint.t).toBeGreaterThan(v.checkpoint.rewatch_from);
      expect(v.claims.length).toBeGreaterThanOrEqual(3);
      expect(FIX.items.find((i) => i.id === v.checkpoint.item_id)?.allows_not_sure).toBe(false);
    }
  });

  describe("the Week 0 baseline", () => {
    it("is a fixed-length adaptive sitting across the lectures, and each question is asked once", async () => {
      const first = await api.getSitting("week0");
      expect(first).toMatchObject({ kind: "week0", total: 12, answered: 0, done: false });
      const seen: string[] = [];
      const lectures: number[] = [];
      for (;;) {
        const v = await api.getSitting("week0");
        if (!v.current) break;
        seen.push(v.current.item.id);
        lectures.push(v.current.lecture_n);
        expect(v.current.item.context).toBe("assessment");
        await api.answerSitting("week0", v.current.item.id, v.current.item.correct_index, 1000);
      }
      expect(seen).toHaveLength(12);
      expect(new Set(seen).size).toBe(12);
      for (const n of [1, 2, 3]) expect(lectures.filter((x) => x === n)).toHaveLength(4);
      expect((await api.getSitting("week0")).done).toBe(true);
    });

    it("locks each answer: only the question the sitting is on can be answered, and only once", async () => {
      const v = await api.getSitting("week0");
      const other = FIX.items.find((i) => i.context === "assessment" && i.id !== v.current!.item.id)!;
      await expect(api.answerSitting("week0", other.id, 0, 1)).rejects.toThrow(/not the question/);
      await api.answerSitting("week0", v.current!.item.id, 0, 1);
      await expect(api.answerSitting("week0", v.current!.item.id, 1, 1)).rejects.toThrow(/not the question/);
    });

    it("adapts: the next question on a lecture depends on how the last one on it was answered", async () => {
      // the baseline interleaves lectures 1, 2, 3, 1, ...: slot 3 is the next lecture 1 question
      const askFourth = async (firstAnswer: "right" | "wrong") => {
        store.resetState();
        let first: string | undefined;
        for (let k = 0; k < 4; k++) {
          const v = await api.getSitting("week0");
          if (k === 3) return { first, fourth: v.current!.item, lecture: v.current!.lecture_n };
          const it = v.current!.item;
          if (k === 0) first = it.id;
          const right = k === 0 ? firstAnswer === "right" : true;
          await api.answerSitting("week0", it.id, right ? it.correct_index : (it.correct_index + 1) % 3, 1);
        }
      };
      const hit = (await askFourth("right"))!;
      const miss = (await askFourth("wrong"))!;
      expect(hit.lecture).toBe(1);
      expect(hit.first).toBe(miss.first);
      expect(hit.fourth.difficulty_prior).toBeGreaterThan(miss.fourth.difficulty_prior);
    });

    it("publishes a level for every KU when it is finished, with a reason built from the answers", async () => {
      await onboardWith("right");
      const levels = await api.getLevels();
      expect(levels.baseline_done).toBe(true);
      const rows = levels.lectures.flatMap((l) => l.rows);
      expect(rows).toHaveLength(FIX.course.kus.length);
      for (const r of rows) expect(r.level.reason.length).toBeGreaterThan(10);
    });

    it("logs every answer and the finish, and one level suggestion per KU", async () => {
      await onboardWith("right");
      const verbs = store.getState().events.map((e) => e.verb);
      expect(verbs.filter((v) => v === "cat_answered")).toHaveLength(12);
      expect(verbs.filter((v) => v === "level_suggested")).toHaveLength(FIX.course.kus.length);
      expect(verbs).toContain("cat_finished");
    });
  });

  it("a student who aces the baseline is Level 3 overall and only sees the upcoming lecture's new video", async () => {
    await onboardWith("right");
    const r = await api.getStartResult();
    expect(r.overall_level).toBe(3);
    expect(r.review).toHaveLength(12);
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
    // the coin-toss video builds on two others, so they come first even though its lecture is the upcoming one
    const order = pl.cards.map((c) => c.video_id);
    expect(order.indexOf("ku-coin-toss-average-causal-effect")).toBeGreaterThan(order.indexOf("ku-selection-bias-general-formula"));
    expect(order.indexOf("ku-coin-toss-average-causal-effect")).toBeGreaterThan(order.indexOf("ku-potential-outcomes"));
    expect(pl.why).toContain("as gaps");
    expect(pl.why).toContain("comes first because");
    const rows = (await api.getLevels()).lectures.flatMap((l) => l.rows);
    expect(rows.every((r) => r.level.level === 1)).toBe(true);
    expect(rows[0].level.reason).toMatch(/^You chose “Not sure” on all 4 questions on “/);
  });

  it("serves the nearest existing version and says so (a Level 3 KU, only a Level 2 file)", async () => {
    await onboardWith("right");
    const pl = await api.getPlaylist();
    expect(pl.cards[0].level).toBe(3);
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

  describe("levels change only at lecture boundaries (plan D11)", () => {
    it("in-video answers, replays and drop-offs do not move a published level; the next lecture's check does", async () => {
      await demo.fastOnboard();
      const before = await levelsOf();
      for (const v of FIX.videos) {
        const it = FIX.items.find((i) => i.id === v.checkpoint.item_id)!;
        await api.postCheckpointAnswer({ videoId: v.id, choice: (it.correct_index + 1) % 3, confidence: "certain", hintUsed: false, latencyMs: 1 });
        await api.markWatched(v.id);
        await api.markWatched(v.id);
        await api.markWatched(v.id);
        await api.recordProgress(v.id, 5, v.duration_s);
      }
      demo.simulateNextDay();
      expect(await levelsOf()).toEqual(before); // nothing moves in the middle of a lecture
      demo.simulateNextWeek();
      const due = (await api.getPlaylist()).precheck!;
      expect(due).toMatchObject({ lecture_n: 3, sitting_id: "lecture-3", total: 6, answered: 0 });
      expect(await levelsOf()).toEqual(before); // and a check that is due is not a check that was taken
      await demo.runSitting("lecture-3", () => "wrong");
      const after = await levelsOf();
      expect(Object.keys(after).filter((k) => after[k] < before[k]).length).toBeGreaterThan(0);
      expect(Object.keys(after).filter((k) => after[k] > before[k])).toHaveLength(0);
    });

    it("the baseline just covered this lecture this week, so no second check is due until the next week", async () => {
      await demo.fastOnboard();
      expect((await api.getPlaylist()).precheck).toBeNull();
      demo.simulateNextWeek();
      expect((await api.getPlaylist()).precheck?.title).toBe(FIX.course.lectures[2].title);
    });

    it("a check is four new questions on the lecture and two review questions from earlier ones, none repeated", async () => {
      await demo.fastOnboard();
      const before = new Set(store.getState().responses.map((r) => r.item_id));
      demo.simulateNextWeek();
      const roles: string[] = [];
      for (;;) {
        const v = await api.getSitting("lecture-3");
        if (!v.current) break;
        roles.push(`${v.current.role}:${v.current.lecture_n}`);
        expect(before.has(v.current.item.id)).toBe(false);
        await api.answerSitting("lecture-3", v.current.item.id, v.current.item.correct_index, 1);
      }
      expect(roles.filter((r) => r.startsWith("new:3"))).toHaveLength(4);
      expect(roles.filter((r) => r.startsWith("review:") && !r.endsWith(":3"))).toHaveLength(2);
    });

    it("skipping the check changes nothing and removes the card", async () => {
      await demo.fastOnboard();
      const before = await levelsOf();
      demo.simulateNextWeek();
      await api.skipSitting("lecture-3");
      expect((await api.getPlaylist()).precheck).toBeNull();
      expect(await levelsOf()).toEqual(before);
    });

    it("a level the student set is not overwritten by a check; only the suggestion moves", async () => {
      await demo.fastOnboard();
      const ku = FIX.course.kus.find((k) => k.lecture_n === 3)!.id;
      await api.correctLevel(ku, 3, null, "", "my_levels");
      demo.simulateNextWeek();
      await demo.runSitting("lecture-3", () => "wrong");
      const row = (await api.getLevels()).lectures.flatMap((l) => l.rows).find((r) => r.ku.id === ku)!;
      expect(row.level).toMatchObject({ level: 3, source: "student" });
      expect(row.level.suggested_level).toBeLessThan(3);
    });
  });

  describe("a video is made once (plan D15)", () => {
    it("remembers the level a video was made at, and says so when the level has since changed", async () => {
      await demo.fastOnboard();
      const card = (await api.getPlaylist()).cards[0];
      expect(card.made_level).toBe(card.level);
      await api.correctLevel(card.ku_id, card.level === 3 ? 1 : 3, null, "", "my_levels");
      const after = (await api.getPlaylist()).cards.find((c) => c.video_id === card.video_id)!;
      expect(after.made_level).toBe(card.level); // never remade
      expect(after.level).not.toBe(card.level);
      const variant = await api.getVariant(card.video_id);
      expect(variant.made_level).toBe(card.level);
      const row = (await api.getLevels()).lectures.flatMap((l) => l.rows).find((r) => r.ku.id === card.ku_id)!;
      expect(row.made_level).toBe(card.level);
    });
  });

  describe("correcting a level", () => {
    it("works per KU, can be undone, and 'Use suggested level' goes back to ours", async () => {
      await demo.fastOnboard();
      const row0 = (await api.getLevels()).lectures[0].rows[0];
      const { previous } = await api.correctLevel(row0.ku.id, 3, "too_easy", "", "my_levels");
      let now = (await api.getLevels()).lectures[0].rows[0];
      expect(now.level).toMatchObject({ level: 3, source: "student" });
      await api.restoreLevel(previous);
      now = (await api.getLevels()).lectures[0].rows[0];
      expect(now.level).toMatchObject({ level: row0.level.level, source: "model" });
      await api.correctLevel(row0.ku.id, 1, null, "", "my_levels");
      await api.useSuggestedLevel(row0.ku.id);
      now = (await api.getLevels()).lectures[0].rows[0];
      expect(now.level).toMatchObject({ level: row0.level.suggested_level, source: "model" });
    });

    it("'Pick my own level' sets every KU at once and counts as being onboarded", async () => {
      await api.postConsent(true);
      await api.pickAllLevels(2, 3);
      const rows = (await api.getLevels()).lectures.flatMap((l) => l.rows);
      expect(rows).toHaveLength(FIX.course.kus.length);
      expect(rows.every((r) => r.level.level === 2 && r.level.source === "student")).toBe(true);
      expect((await api.getMe()).onboarding_done).toBe(true);
    });
  });

  describe("engagement adjusts delivery, never levels (plan D13)", () => {
    it("sends a video stopped early back to the top and says why, after the pause has passed", async () => {
      await demo.fastOnboard();
      const second = (await api.getPlaylist()).cards[1];
      await api.recordProgress(second.video_id, 10, 100);
      expect((await api.getPlaylist()).why).not.toContain("You stopped"); // maybe just paused
      demo.simulateNextDay();
      const pl = await api.getPlaylist();
      expect(pl.cards[0].video_id).toBe(second.video_id);
      expect(pl.why).toContain(`You stopped “${second.title}” partway`);
    });
  });

  describe("resetting the model", () => {
    it("archives the levels and the check answers, keeps the watch history, and the retaken baseline asks fresh questions", async () => {
      await demo.fastOnboard();
      const vid = FIX.videos[0];
      await api.markWatched(vid.id);
      const asked = new Set(store.getState().responses.filter((r) => r.context === "assessment").map((r) => r.item_id));
      await api.resetModel();
      const s = store.getState();
      expect(s.archived_models).toHaveLength(1);
      expect(Object.keys(s.archived_models[0].levels)).toHaveLength(FIX.course.kus.length);
      expect(s.archived_models[0].assessment_responses).toHaveLength(12);
      expect(s.levels).toEqual({});
      expect(s.watched[vid.id]).toBeDefined();
      expect((await api.getMe()).onboarding_done).toBe(false);
      const v = await api.getSitting("week0");
      expect(v.answered).toBe(0);
      expect(asked.has(v.current!.item.id)).toBe(true); // the old answers are archived, so the same start is possible
    });
  });

  it("reports whether a video's quick check has been answered, right or wrong", async () => {
    await onboardWith("not_sure");
    const vid = FIX.videos[0];
    const item = FIX.items.find((i) => i.id === vid.checkpoint.item_id)!;
    expect((await api.getVariant(vid.id)).checkpoint_answered).toBe(false);
    await api.skipCheckpoint(vid.id);
    expect((await api.getVariant(vid.id)).checkpoint_answered).toBe(false);
    await api.postCheckpointAnswer({ videoId: vid.id, choice: (item.correct_index + 1) % 3, confidence: "certain", hintUsed: false, latencyMs: 900 });
    expect((await api.getVariant(vid.id)).checkpoint_answered).toBe(true);
    expect((await api.getVariant(FIX.videos[1].id)).checkpoint_answered).toBe(false);
  });

  it("edits and deletes a note", async () => {
    const id = FIX.videos[0].id;
    await api.addNote(id, 12, "first");
    const [note] = await api.listNotes(id);
    await api.updateNote(note.id, "second");
    expect((await api.listNotes(id)).map((n) => n.text)).toEqual(["second"]);
    await api.deleteNote(note.id);
    expect(await api.listNotes(id)).toEqual([]);
  });
});

describe.skipIf(!haveFixtures)("scripted students (plan §10)", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let demo: typeof import("../src/api/demo");

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    demo = await import("../src/api/demo");
    store.resetState();
  });

  it("the mid-course student crossed a lecture boundary: levels went up and down, each with a counted reason", async () => {
    await demo.loadPersona("midcourse");
    const card = await api.getLevelUpdates();
    expect(card).not.toBeNull();
    expect(card!.updates.some((u) => u.direction === "up")).toBe(true);
    expect(card!.updates.some((u) => u.direction === "down")).toBe(true);
    for (const u of card!.updates) {
      expect(u.reason).toContain(`Level ${u.from} → ${u.to}`);
      expect(u.reason).toMatch(/\d+ of \d+ right on “/);
    }
    expect(store.getState().sittings["lecture-3"].finished_at).not.toBeNull();
  });

  it("dismissing the card hides it; the levels stay", async () => {
    await demo.loadPersona("midcourse");
    const before = await api.getLevels();
    await api.dismissLevelUpdates((await api.getLevelUpdates())!.id);
    expect(await api.getLevelUpdates()).toBeNull();
    expect(await api.getLevels()).toEqual(before);
  });

  it("the 'check due' student has done the baseline and has the Lecture 3 check waiting", async () => {
    await demo.loadPersona("precheck");
    const pl = await api.getPlaylist();
    expect(pl.precheck).toMatchObject({ lecture_n: 3, sitting_id: "lecture-3", answered: 0 });
    expect(await api.getLevelUpdates()).toBeNull();
    expect((await api.getLevels()).baseline_done).toBe(true);
  });

  it("My levels shows both calibration blocks for the mid-course student", async () => {
    await demo.loadPersona("midcourse");
    const cal = await api.getCalibration();
    expect(cal.block1.rated).toBeGreaterThanOrEqual(1);
  });

  it("exports the profile per KU", async () => {
    await demo.loadPersona("midcourse");
    const data = (await api.exportMyData()) as { profile: { levels: Record<string, unknown>; made: Record<string, number> } };
    expect(Object.keys(data.profile.levels).length).toBeGreaterThan(10);
    expect(Object.keys(data.profile.made).length).toBeGreaterThan(0);
  });
});
