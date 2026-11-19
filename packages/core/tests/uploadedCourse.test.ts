import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { assembleCourse, type CourseInput, type DeckResult } from "../src/logic/assemble";
import { dependentCounts, prelecturePlan } from "../src/logic/assessment";
import { videoRequests } from "../src/logic/videoRequests";
import type { Fixtures, Item, QuestionNeed } from "../src/types";
import { item } from "./helpers";

// An uploaded course (plan/slide-uploads-plan.md V1-V6) whose slides arrive over time and whose questions are
// written as whole banks before a check opens, through the real mock API.

const BETAS = { basic: -1, applied: 0, advanced: 1 };
const TIERS = ["basic", "applied", "advanced"] as const;

/** `n` KUs, each building on the one before, with tier difficulties and no questions yet. */
function deck(prefix: string, n: number): DeckResult {
  const kus = Array.from({ length: n }, (_, i) => `ku-${prefix}-${i}`);
  return {
    kus: kus.map((id, i) => ({
      id, title: id, short_title: id, summary: "", bloom_level: "understand", prerequisites: i ? [kus[i - 1]] : [], source_refs: [],
      tier_difficulty: BETAS,
    })),
    items: [],
  };
}

type Input = Omit<CourseInput, "id" | "code" | "name">;
const course = (over: Partial<Input> & { decks: CourseInput["decks"] }, upcoming = 1): Fixtures =>
  assembleCourse({
    id: "up", code: "UP-1", name: "Uploaded",
    lectures: over.decks.map((d) => ({ n: d.lecture_n, title: `Lecture ${d.lecture_n}` })),
    config: { upcoming_lecture_override: upcoming },
    ...over,
  });

/** What the worker would write for a need: one question at that KU and tier. */
let written = 0;
const question = (need: QuestionNeed): Item =>
  item(`as-${need.ku_id}-${need.tier}-${++written}`, "", "assessment", { ku_id: need.ku_id, tier: need.tier, difficulty_prior: BETAS[need.tier] });

describe("pre-lecture check length (V5)", () => {
  it("asks up to 10 on the lecture, no more than it has KUs, plus 2 review once there is an earlier lecture", () => {
    const fx = course({ decks: [{ lecture_n: 1, result: deck("a", 12) }, { lecture_n: 2, result: deck("b", 3) }] });
    expect(prelecturePlan(fx.course, 1).slots.map((s) => s.role)).toEqual(Array(10).fill("new"));
    const second = prelecturePlan(fx.course, 2).slots.map((s) => s.role);
    expect(second.filter((r) => r === "new")).toHaveLength(3);
    expect(second.filter((r) => r === "review")).toHaveLength(2);
  });

  it("has nothing to ask on a lecture without KUs", () => {
    const fx = course({ decks: [{ lecture_n: 1, result: deck("a", 0) }] });
    expect(prelecturePlan(fx.course, 1).slots).toEqual([]);
  });

  it("counts dependents through the whole graph", () => {
    const fx = course({ decks: [{ lecture_n: 1, result: deck("a", 3) }] });
    expect([...dependentCounts(fx.course.kus)]).toEqual([["ku-a-0", 2], ["ku-a-1", 1], ["ku-a-2", 0]]);
  });
});

describe("lecture order (V1)", () => {
  it("keeps a lecture's number when another is placed before it, and orders and dates by position", () => {
    const fx = course({
      lectures: [{ n: 1, title: "One", position: 1 }, { n: 2, title: "Two", position: 3 }, { n: 3, title: "Between", position: 2 }],
      decks: [1, 2, 3].map((n) => ({ lecture_n: n, result: deck(`l${n}`, 1) })),
    });
    expect(fx.course.lectures.map((l) => [l.n, l.position, l.week])).toEqual([[1, 1, 1], [3, 2, 2], [2, 3, 3]]);
    // lecture 3 is taught before lecture 2, so it has review questions and lecture 1 is earlier for both
    expect(prelecturePlan(fx.course, 3).slots.some((s) => s.role === "review")).toBe(true);
  });
});

describe("an uploaded course through the API", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let fxMod: typeof import("../src/fixtures");
  let mock: typeof import("../src/api/mock");

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    fxMod = await import("../src/fixtures");
    mock = await import("../src/api/mock");
    store.resetState();
  });
  afterEach(() => fxMod.setFixtures(fxMod.FIX));

  it("prepares the due lecture and an explicitly opened check even before its first answer", () => {
    fxMod.setFixtures(course({ decks: [{ lecture_n: 1, result: deck("a", 2) }, { lecture_n: 2, result: deck("b", 2) }] }));
    expect(mock.questionBankLectures()).toEqual([1]);
    expect(mock.questionBankLectures("lecture-2").sort()).toEqual([1, 2]);
    // questions come as whole banks, written before a check opens: none is written one at a time
    expect(mock.questionNeedsNow("lecture-2")).toEqual([]);
    expect(store.getState().sittings).toEqual({}); // viewing the check does not record an answer or start it
  });

  /** Writes a bank (one question per tier) for every KU of the lectures whose checks are due or open, as the server's
   *  workers would before a check opens, and returns everything written. */
  function writeBanks(input: Parameters<typeof course>[0], saved: Item[], opened?: string): Item[] {
    const lectures = mock.questionBankLectures(opened);
    for (const k of course(input).course.kus.filter((k) => lectures.includes(k.lecture_n))) {
      for (const tier of TIERS) if (!saved.some((i) => i.ku_id === k.id && i.tier === tier)) saved.push(question({ ku_id: k.id, tier }));
    }
    fxMod.setFixtures(course({ ...input, questions: [...saved] }));
    return saved;
  }

  async function answerAll(id: string, how: "right" | "wrong", input: Parameters<typeof course>[0], saved: Item[] = []) {
    for (let guard = 0; guard < 50; guard++) {
      writeBanks(input, saved, id);
      const s = await api.getSitting(id);
      if (!s.current) break;
      const it = s.current.item;
      await api.answerSitting(id, it.id, how === "right" ? it.correct_index : (it.correct_index + 1) % 3, 1000);
    }
    await api.finishSitting(id);
    return saved;
  }

  it("has no baseline: the first thing to do is lecture 1's check (V6)", async () => {
    fxMod.setFixtures(course({ decks: [] }));
    const me = await api.getMe();
    expect(me.onboarding_done).toBe(true);
    expect(me.baseline_available).toBe(false);
    expect((await api.getPlaylist()).precheck).toBeNull();

    fxMod.setFixtures(course({ decks: [{ lecture_n: 1, result: deck("a", 2) }] }));
    expect((await api.getPlaylist()).precheck?.lecture_n).toBe(1);
  });

  it("opens the check only once every topic's questions are written, so no question is ever waited for", async () => {
    const input = { decks: [{ lecture_n: 1, result: deck("a", 3) }] };
    fxMod.setFixtures(course(input));
    const before = await api.getSitting("lecture-1");
    expect(before.current).toBeNull();
    expect(before.preparing).toBe("writing");
    expect(before.done).toBe(false);
    expect(before.questions_ready).toEqual({ ready: 0, total: 3 });
    expect((await api.getPlaylist()).precheck?.questions_ready).toEqual({ ready: 0, total: 3 });
    await expect(api.answerSitting("lecture-1", "anything", 0, 1000)).rejects.toThrow();

    // one topic's bank is not enough
    fxMod.setFixtures(course({ ...input, questions: TIERS.map((tier) => question({ ku_id: "ku-a-0", tier })) }));
    expect((await api.getSitting("lecture-1")).questions_ready).toEqual({ ready: 1, total: 3 });

    writeBanks(input, []);
    const after = await api.getSitting("lecture-1");
    // the most depended-on KU first, at the tier nearest a starting ability of 0
    expect(after.current?.item.ku_id).toBe("ku-a-0");
    expect(after.current?.item.tier).toBe("applied");
    expect(after.questions_ready).toBeNull();
    expect(after.preparing).toBeNull();
    expect((await api.getPlaylist()).precheck?.questions_ready).toBeNull();
  });

  it("writes no single question while a check runs: it asks only the banks written before it opened", async () => {
    const input = { decks: [{ lecture_n: 1, result: deck("a", 3) }] };
    fxMod.setFixtures(course(input));
    writeBanks(input, []);
    expect((await api.getSitting("lecture-1")).current?.item.ku_id).toBe("ku-a-0");
    expect(mock.questionNeedsNow()).toEqual([]);
  });

  it("spreads questions over the lecture's KUs and moves the tier with the answers", async () => {
    const input = { decks: [{ lecture_n: 1, result: deck("a", 3) }] };
    fxMod.setFixtures(course(input));
    const saved = await answerAll("lecture-1", "right", input);
    const asked = store.getState().sittings["lecture-1"].answered_ids.map((id) => saved.find((q) => q.id === id)!);
    expect(asked.map((q) => q.ku_id)).toEqual(["ku-a-0", "ku-a-1", "ku-a-2"]);
    expect(asked[0].tier).toBe("applied");
    expect(asked[2].tier).toBe("advanced");
  });

  it("asks one tier lower after a Not sure, down to basic, and goes back up after a scored answer", async () => {
    const input = { decks: [{ lecture_n: 1, result: deck("a", 7) }] };
    fxMod.setFixtures(course(input));
    const saved: Item[] = [];
    const tiers: string[] = [];
    for (const how of ["right", "right", "not_sure", "not_sure", "not_sure", "right"] as const) {
      writeBanks(input, saved);
      const it = (await api.getSitting("lecture-1")).current!.item;
      tiers.push(it.tier!);
      await api.answerSitting("lecture-1", it.id, how === "right" ? it.correct_index : "not_sure", 1000);
    }
    writeBanks(input, saved);
    tiers.push((await api.getSitting("lecture-1")).current!.item.tier!);
    // two right answers reach advanced; each Not sure steps down one and counts as wrong, so after three of them a
    // right answer lets the estimate choose again, from lower down
    expect(tiers).toEqual(["applied", "applied", "advanced", "applied", "basic", "basic", "applied"]);
  });

  it("sets levels from the answers for a KU extracted without tier difficulties", async () => {
    const old = deck("a", 3);
    for (const k of old.kus) delete k.tier_difficulty;
    const input = { decks: [{ lecture_n: 1, result: old }] };
    fxMod.setFixtures(course(input));
    await answerAll("lecture-1", "right", input);
    const levels = store.getState().levels;
    for (const [i, k] of old.kus.entries()) {
      // Each KU retains the estimate from when its own question was answered.
      expect(levels[k.id].reason).toContain(`${i + 1} right`);
      expect(levels[k.id].level).toBeGreaterThan(1);
    }
  });

  it("leaves out a topic whose questions could not be written: the check opens and asks the others", async () => {
    const input = { decks: [{ lecture_n: 1, result: deck("a", 2) }] };
    const other = TIERS.map((tier) => question({ ku_id: "ku-a-1", tier }));
    fxMod.setFixtures(course({ ...input, questions: other, question_failures: TIERS.map((tier) => ({ ku_id: "ku-a-0", tier })) }));
    const s = await api.getSitting("lecture-1");
    expect(s.questions_ready).toBeNull();
    expect(s.current?.item.ku_id).toBe("ku-a-1");
  });

  it("counts a topic ready only when each tier is saved or was given up, and asks its saved tiers", async () => {
    const input = { decks: [{ lecture_n: 1, result: deck("a", 2) }] };
    const others = TIERS.map((tier) => question({ ku_id: "ku-a-1", tier }));
    // ku-a-0: one tier given up, the others not written yet: not ready
    fxMod.setFixtures(course({ ...input, questions: others, question_failures: [{ ku_id: "ku-a-0", tier: "advanced" }] }));
    expect((await api.getSitting("lecture-1")).questions_ready).toEqual({ ready: 1, total: 2 });
    // its basic and applied saved, advanced given up: ready, and the check asks a saved tier of it
    const partial = (["basic", "applied"] as const).map((tier) => question({ ku_id: "ku-a-0", tier }));
    fxMod.setFixtures(course({ ...input, questions: [...others, ...partial], question_failures: [{ ku_id: "ku-a-0", tier: "advanced" }] }));
    const s = await api.getSitting("lecture-1");
    expect(s.questions_ready).toBeNull();
    expect(s.current?.item.ku_id).toBe("ku-a-0");
    expect(["basic", "applied"]).toContain(s.current?.item.tier);
  });

  it("reuses saved questions for a classmate, and never asks a student the same one twice", async () => {
    const input = { decks: [{ lecture_n: 1, result: deck("a", 2) }] };
    fxMod.setFixtures(course(input));
    const saved = await answerAll("lecture-1", "right", input);
    const count = saved.length;

    store.resetState();
    fxMod.setFixtures(course({ ...input, questions: saved }));
    const s = await api.getSitting("lecture-1");
    expect(saved.map((q) => q.id)).toContain(s.current?.item.id);
    expect(saved).toHaveLength(count);
  });

  it("gives KUs of a lecture added later a provisional level, with no 'what changed' card", async () => {
    const one = { decks: [{ lecture_n: 1, result: deck("a", 2) }] };
    fxMod.setFixtures(course(one));
    const saved = await answerAll("lecture-1", "right", one);
    const before = await api.getLevelUpdates();

    fxMod.setFixtures(course({ decks: [...one.decks, { lecture_n: 2, result: deck("b", 1) }], questions: saved }));
    const levels = await api.getLevels();
    const row = levels.lectures.find((l) => l.lecture.n === 2)!.rows[0];
    expect(row.level.provisional).toBe(true);
    expect(row.level.history[0].cause).toBe("slides_added");
    expect(await api.getLevelUpdates()).toEqual(before);
  });

  it("releases answered KUs early, keeps their levels fixed, and waits until finish for unasked KUs", async () => {
    const input = { decks: [{ lecture_n: 1, result: deck("a", 4) }], config: { cat_prelecture_new: 2 } };
    const fx = course(input);
    fxMod.setFixtures(fx);
    const want = () => videoRequests(fx.course, store.getState().sittings, store.getState().levels, store.getState().made);
    expect(want()).toEqual([]);
    const saved: Item[] = [];
    await api.getSitting("lecture-1");
    writeBanks(input, saved);
    const first = (await api.getSitting("lecture-1")).current!.item;
    await api.answerSitting("lecture-1", first.id, first.correct_index, 1000);
    const early = want();
    expect(early).toEqual([{ ku_id: first.ku_id, lecture_n: 1, level: store.getState().levels[first.ku_id!].level }]);
    expect(store.getState().sittings["lecture-1"].finished_at).toBeNull();

    writeBanks(input, saved);
    const second = (await api.getSitting("lecture-1")).current!.item;
    expect(second.ku_id).not.toBe(first.ku_id);
    await api.answerSitting("lecture-1", second.id, "not_sure", 1000);
    expect(want()).toHaveLength(2);
    expect(want()[0]).toEqual(early[0]);
    await api.finishSitting("lecture-1");
    expect(want()).toHaveLength(4);
    expect(want()[0]).toEqual(early[0]);
    expect(store.getState().levels[first.ku_id!].history).toHaveLength(1);
  });

  it("asks for videos only for lectures whose levels a check set (U18)", async () => {
    const one = { decks: [{ lecture_n: 1, result: deck("a", 2) }] };
    fxMod.setFixtures(course(one, 1));
    const saved = await answerAll("lecture-1", "right", one);
    const two = { decks: [...one.decks, { lecture_n: 2, result: deck("b", 2) }], questions: saved };
    const withTwo = course(two, 2);
    fxMod.setFixtures(withTwo);
    await api.getMe();
    const want = () => videoRequests(withTwo.course, store.getState().sittings, store.getState().levels, store.getState().made).map((r) => r.ku_id);
    expect(want()).toEqual(["ku-a-0", "ku-a-1"]);

    const input2 = { ...two, config: { upcoming_lecture_override: 2 } };
    await answerAll("lecture-2", "right", input2, [...saved]);
    expect(want()).toEqual(["ku-a-0", "ku-a-1", "ku-b-0", "ku-b-1"]);
  });
});
