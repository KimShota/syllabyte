import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { assembleCourse, DEFAULT_COURSE_CONFIG, UPLOADED_COURSE_CONFIG, type CourseInput, type DeckKu } from "../src/logic/assemble";
import { week0Plan } from "../src/logic/assessment";
import type { Item } from "../src/types";
import { item } from "./helpers";

const ku = (id: string, prerequisites: string[] = []): DeckKu => ({
  id, title: `Title ${id}`, short_title: id, summary: "", bloom_level: "understand", prerequisites,
  source_refs: [{ deck_name: "d", slide_number: 1 }],
});
const bankItem = (id: string, kuId: string): Item => item(id, "unset", "assessment", { ku_id: kuId, tier: "basic" });

const input = (): CourseInput => ({
  id: "c1",
  code: "CS-101",
  name: "Intro",
  lectures: [
    { n: 2, title: "Two", position: 2 },
    { n: 1, title: "One", position: 1 },
    { n: 3, title: "Three", position: 5 },
  ],
  decks: [
    { lecture_n: 3, result: { kus: [ku("c", ["a", "gone"])], items: [bankItem("i-c", "c")] } },
    { lecture_n: 1, result: { kus: [ku("a"), ku("b", ["a"])], items: [bankItem("i-a", "a"), bankItem("i-b", "b")] } },
  ],
  links: [{ ku_id: "c", prereq_id: "b" }],
});

describe("assembleCourse", () => {
  it("lists the lectures in teaching order, numbered and dated by their place", () => {
    const { course } = assembleCourse(input());
    expect(course.lectures.map((l) => [l.n, l.position, l.week])).toEqual([[1, 1, 1], [2, 2, 2], [3, 3, 3]]);
    expect(course.topics.map((t) => [t.id, t.ku_ids])).toEqual([["lecture-1", ["a", "b"]], ["lecture-2", []], ["lecture-3", ["c"]]]);
  });

  it("places each KU and item in its deck's lecture", () => {
    const { course, items } = assembleCourse(input());
    expect(course.kus.map((k) => [k.id, k.lecture_n, k.topic_id])).toEqual([["a", 1, "lecture-1"], ["b", 1, "lecture-1"], ["c", 3, "lecture-3"]]);
    expect(items.map((i) => [i.id, i.topic_id])).toEqual([["i-a", "lecture-1"], ["i-b", "lecture-1"], ["i-c", "lecture-3"]]);
  });

  it("adds the questions written on demand to their KU's lecture, and drops ones on unknown KUs", () => {
    const { items } = assembleCourse({ ...input(), questions: [bankItem("q-b", "b"), bankItem("q-x", "x")] });
    expect(items.filter((i) => i.id.startsWith("q-")).map((i) => [i.id, i.topic_id])).toEqual([["q-b", "lecture-1"]]);
  });

  it("keeps a KU's tier difficulties and passes on questions that could not be written", () => {
    const tiers = { basic: -0.5, applied: 0.5, advanced: 1.5 };
    const fx = assembleCourse({ ...input(), decks: [{ lecture_n: 1, result: { kus: [{ ...ku("a"), tier_difficulty: tiers }], items: [] } }], question_failures: [{ ku_id: "a", tier: "basic" }] });
    expect(fx.course.kus[0].tier_difficulty).toEqual(tiers);
    expect(fx.question_failures).toEqual([{ ku_id: "a", tier: "basic" }]);
  });

  it("adds later links and drops links to KUs that are not in the course", () => {
    const { course } = assembleCourse(input());
    expect(course.kus.find((k) => k.id === "c")!.prerequisites).toEqual(["a", "b"]);
  });

  it("uses the default config with on-demand questions and no baseline (V4-V6), with overrides", () => {
    expect(assembleCourse(input()).course.config).toEqual({ ...DEFAULT_COURSE_CONFIG, ...UPLOADED_COURSE_CONFIG });
    expect(assembleCourse(input()).course.config).toMatchObject({ questions_on_demand: true, cat_prelecture_new: 10, cat_week0_lectures: 0 });
    expect(assembleCourse({ ...input(), config: { cat_week0_lectures: 2 } }).course.config.cat_week0_lectures).toBe(2);
  });

  it("has no videos yet", () => {
    expect(assembleCourse(input()).videos).toEqual([]);
  });
});

// The demo course rebuilt from its own pieces (one deck per lecture) must give the same baseline.
const haveFixtures = existsSync(resolve(__dirname, "../fixtures/bank.json"));

describe.skipIf(!haveFixtures)("the demo course, assembled from stored pieces", () => {
  it("gives the same baseline plan and lectures", async () => {
    const { FIX } = await import("../src/fixtures");
    const bank = FIX.items.filter((i) => i.context === "assessment");
    const assembled = assembleCourse({
      id: FIX.course.id,
      code: FIX.course.code,
      name: FIX.course.name,
      config: FIX.course.config,
      lectures: FIX.course.lectures.map((l) => ({ n: l.n, title: l.title })),
      decks: FIX.course.lectures.map((l) => ({
        lecture_n: l.n,
        result: {
          kus: FIX.course.kus
            .filter((k) => k.lecture_n === l.n)
            .map((k) => ({ ...ku(k.id, k.prerequisites), title: k.title, short_title: k.short_title, bloom_level: k.bloom_level })),
          items: bank.filter((i) => FIX.course.kus.find((k) => k.id === i.ku_id)?.lecture_n === l.n),
        },
      })),
    });
    expect(week0Plan(assembled.course)).toEqual(week0Plan(FIX.course));
    expect(assembled.course.kus.map((k) => [k.id, k.lecture_n, k.prerequisites])).toEqual(
      FIX.course.kus.map((k) => [k.id, k.lecture_n, k.prerequisites]),
    );
    expect(assembled.items.map((i) => [i.id, i.topic_id]).sort()).toEqual(bank.map((i) => [i.id, i.topic_id]).sort());
  });
});
