import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { assembleCourse, type CourseInput, type DeckResult } from "../src/logic/assemble";
import { week0Plan } from "../src/logic/assessment";
import { videoRequests } from "../src/logic/videoRequests";
import type { Item, ItemTier } from "../src/types";
import { item } from "./helpers";

// An uploaded course (plan/slide-uploads-plan.md) whose slides arrive over time, through the real mock API.

const TIERS: [ItemTier, number][] = [["basic", -1], ["applied", 0], ["advanced", 1]];

function deck(prefix: string, n: number): DeckResult {
  const kus = Array.from({ length: n }, (_, i) => `ku-${prefix}-${i}`);
  return {
    kus: kus.map((id, i) => ({ id, title: id, short_title: id, summary: "", bloom_level: "understand", prerequisites: i ? [kus[i - 1]] : [], source_refs: [] })),
    items: kus.flatMap((k) => TIERS.map(([t, b]): Item => item(`as-${k}-${t}`, "", "assessment", { ku_id: k, tier: t, difficulty_prior: b }))),
  };
}

const LECTURES = [1, 2, 3].map((n) => ({ n, title: `Lecture ${n}`, week: n }));
const course = (decks: CourseInput["decks"], upcoming = 1) =>
  assembleCourse({ id: "up", code: "UP-1", name: "Uploaded", lectures: LECTURES, decks, config: { upcoming_lecture_override: upcoming } });

describe("the baseline over the lectures that have slides (U9)", () => {
  it("covers only processed lectures, and is shorter when they have fewer items", () => {
    const fx = course([{ lecture_n: 2, result: deck("b", 1) }]);
    const plan = week0Plan(fx.course, fx.items);
    expect(plan.slots.map((s) => s.lecture_n)).toEqual([2, 2, 2]);
  });

  it("is empty before any slides are processed", () => {
    const fx = course([]);
    expect(week0Plan(fx.course, fx.items).slots).toEqual([]);
  });

  it("is the same as before for a course whose lectures all have items", () => {
    const fx = course([1, 2, 3].map((n) => ({ lecture_n: n, result: deck(`l${n}`, 4) })));
    expect(week0Plan(fx.course, fx.items)).toEqual(week0Plan(fx.course));
  });
});

describe("an uploaded course through the API", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let fxMod: typeof import("../src/fixtures");

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    fxMod = await import("../src/fixtures");
    store.resetState();
  });
  afterEach(() => fxMod.setFixtures(fxMod.FIX));

  async function answerAll(id: string, how: "right" | "wrong") {
    for (let guard = 0; guard < 50; guard++) {
      const s = await api.getSitting(id);
      if (!s.current) break;
      const it = s.current.item;
      await api.answerSitting(id, it.id, how === "right" ? it.correct_index : (it.correct_index + 1) % 3, 1000);
    }
    await api.finishSitting(id);
  }

  it("has no baseline to take until the first slides are processed", async () => {
    fxMod.setFixtures(course([]));
    expect((await api.getMe()).baseline_available).toBe(false);
    fxMod.setFixtures(course([{ lecture_n: 1, result: deck("a", 2) }]));
    expect((await api.getMe()).baseline_available).toBe(true);
    expect((await api.getSitting("week0")).total).toBe(4);
  });

  it("keeps a started baseline on its lectures when more slides arrive", async () => {
    fxMod.setFixtures(course([{ lecture_n: 1, result: deck("a", 2) }]));
    const first = await api.getSitting("week0");
    await api.answerSitting("week0", first.current!.item.id, first.current!.item.correct_index, 1000);
    fxMod.setFixtures(course([{ lecture_n: 1, result: deck("a", 2) }, { lecture_n: 2, result: deck("b", 4) }]));
    const after = await api.getSitting("week0");
    expect(after.total).toBe(4);
    expect(after.current!.lecture_n).toBe(1);
  });

  it("gives KUs from slides added later a level from their lecture, with no 'what changed' card (U10)", async () => {
    const part1 = { lecture_n: 1, result: deck("a", 2) };
    fxMod.setFixtures(course([part1]));
    await answerAll("week0", "right");
    const before = await api.getLevelUpdates();

    fxMod.setFixtures(course([part1, { lecture_n: 1, result: deck("a2", 1) }]));
    const levels = await api.getLevels();
    const rows = levels.lectures[0].rows;
    const row = rows.find((r) => r.ku.id === "ku-a2-0")!;
    expect(row.level.provisional).toBe(false);
    expect(row.level.level).toBe(rows.find((r) => r.ku.id === "ku-a-0")!.level.level);
    expect(row.level.history[0].cause).toBe("slides_added");
    expect(await api.getLevelUpdates()).toEqual(before);
  });

  it("asks for a later lecture's check, since the baseline did not cover it", async () => {
    const decks = [{ lecture_n: 1, result: deck("a", 2) }];
    fxMod.setFixtures(course(decks, 2));
    await answerAll("week0", "right");
    fxMod.setFixtures(course([...decks, { lecture_n: 2, result: deck("b", 2) }], 2));
    const playlist = await api.getPlaylist();
    expect(playlist.precheck?.lecture_n).toBe(2);
  });

  it("asks for videos only for lectures whose levels a sitting set (U18)", async () => {
    const decks = [{ lecture_n: 1, result: deck("a", 2) }];
    fxMod.setFixtures(course(decks, 2));
    await answerAll("week0", "right");
    const withTwo = course([...decks, { lecture_n: 2, result: deck("b", 2) }], 2);
    fxMod.setFixtures(withTwo);
    await api.getMe();
    const want = () => videoRequests(withTwo.course, store.getState().sittings, store.getState().levels, store.getState().made).map((r) => r.ku_id);
    expect(want()).toEqual(["ku-a-0", "ku-a-1"]);

    await answerAll("lecture-2", "right");
    expect(want()).toEqual(["ku-a-0", "ku-a-1", "ku-b-0", "ku-b-1"]);
  });
});
