import { describe, expect, it } from "vitest";
import { nextAssessmentItem, prelecturePlan, week0Plan } from "../src/logic/assessment";
import { answer, bank, course, items, lectureOfItem } from "./kuHelpers";
import type { ResponseRecord } from "../src/types";

const withConfig = (patch: Partial<typeof course.config>) => ({ ...course, config: { ...course.config, ...patch } });

/** Run a whole sitting, answering every item with `how(item)`; returns the items asked in order. */
function sit(plan: ReturnType<typeof week0Plan>, how: (id: string) => "right" | "wrong" | "not_sure", prior: ResponseRecord[] = [], c = course) {
  const responses = [...prior];
  const asked: { id: string; lecture: number; role: string }[] = [];
  for (let k = 0; ; k++) {
    const next = nextAssessmentItem(plan, k, { course: c, items, responses });
    if (!next) break;
    asked.push({ id: next.item.id, lecture: next.lecture_n, role: next.role });
    responses.push(answer(next.item.id, how(next.item.id)));
  }
  return { asked, responses };
}

describe("Week 0 plan", () => {
  it("interleaves the first lectures, items_per_topic each", () => {
    const plan = week0Plan(course);
    expect(plan.kind).toBe("week0");
    expect(plan.slots.map((s) => s.lecture_n)).toEqual([1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3]); // 3 lectures x 4
    expect(plan.slots.every((s) => s.role === "new")).toBe(true);
  });

  it("covers only the first cat_week0_lectures lectures and never exceeds cat_week0_length", () => {
    expect(week0Plan(withConfig({ cat_week0_lectures: 2 })).slots.map((s) => s.lecture_n)).toEqual([1, 2, 1, 2, 1, 2, 1, 2]);
    expect(week0Plan(withConfig({ cat_week0_length: 5 })).slots).toHaveLength(5);
  });
});

describe("pre-lecture plan", () => {
  it("is new, new, review, new, new, review for a later lecture", () => {
    const plan = prelecturePlan(course, 2);
    expect(plan.slots.map((s) => s.role)).toEqual(["new", "new", "review", "new", "new", "review"]);
    expect(plan.slots.filter((s) => s.role === "new").every((s) => s.lecture_n === 2)).toBe(true);
    expect(plan.slots.filter((s) => s.role === "review").every((s) => s.lecture_n === null)).toBe(true);
  });

  it("has no review slots before the first lecture, since nothing came earlier", () => {
    expect(prelecturePlan(course, 1).slots.map((s) => s.role)).toEqual(["new", "new", "new", "new"]);
  });

  it("spreads other review counts evenly", () => {
    expect(prelecturePlan(withConfig({ cat_prelecture_new: 3, cat_prelecture_review: 2 }), 3).slots.map((s) => s.role)).toEqual(["new", "review", "new", "review", "new"]);
    expect(prelecturePlan(withConfig({ cat_prelecture_review: 0 }), 3).slots).toHaveLength(4);
  });
});

describe("asking the next item", () => {
  it("gives the same item until it is answered", () => {
    const plan = week0Plan(course);
    const a = nextAssessmentItem(plan, 0, { course, items, responses: [] });
    const b = nextAssessmentItem(plan, 0, { course, items, responses: [] });
    expect(a?.item.id).toBe(b?.item.id);
    expect(a).toMatchObject({ lecture_n: 1, role: "new", index: 0, total: 12 });
  });

  it("starts each lecture at theta 0 with the item whose difficulty is closest", () => {
    const plan = week0Plan(course);
    expect(nextAssessmentItem(plan, 0, { course, items, responses: [] })?.item.id).toBe("as-ku-a-advanced"); // b = 0, the closest to 0 in lecture 1
    expect(nextAssessmentItem(plan, 1, { course, items, responses: [] })?.item.id).toBe("as-ku-c-applied"); // b = 0
  });

  it("adapts: a right answer makes the next item on that lecture harder, a wrong one easier", () => {
    const plan = week0Plan(course);
    const first = nextAssessmentItem(plan, 0, { course, items, responses: [] })!.item;
    const harder = nextAssessmentItem(plan, 3, { course, items, responses: [answer(first.id, "right")] })!;
    const easier = nextAssessmentItem(plan, 3, { course, items, responses: [answer(first.id, "wrong")] })!;
    expect(harder.lecture_n).toBe(1);
    expect(harder.item.difficulty_prior).toBeGreaterThan(first.difficulty_prior);
    expect(easier.item.difficulty_prior).toBeLessThan(first.difficulty_prior);
  });

  it("is over after the last slot, and never repeats an item", () => {
    const { asked } = sit(week0Plan(course), () => "right");
    expect(asked).toHaveLength(12);
    expect(new Set(asked.map((a) => a.id)).size).toBe(12);
    expect(nextAssessmentItem(week0Plan(course), 12, { course, items, responses: [] })).toBeNull();
  });

  it("asks exactly items_per_topic on each lecture of the baseline", () => {
    const c = withConfig({ cat_items_per_topic: 3 }); // every lecture has at least 3 bank items
    const { asked } = sit(week0Plan(c), (id) => (id.endsWith("advanced") ? "wrong" : "right"), [], c);
    expect(asked).toHaveLength(9);
    for (const n of [1, 2, 3]) expect(asked.filter((a) => a.lecture === n)).toHaveLength(3);
  });

  it("falls back to another lecture, rather than ending early, when one runs out of unseen items", () => {
    // lecture 3 has only 3 bank items but the baseline wants 4 of them
    const { asked } = sit(week0Plan(course), () => "right");
    expect(asked).toHaveLength(12);
    expect(asked.filter((a) => a.lecture === 3)).toHaveLength(3);
    expect(new Set(asked.map((a) => a.id)).size).toBe(12);
  });

  it("counts 'Not sure' toward the length", () => {
    const { asked } = sit(week0Plan(course), () => "not_sure");
    expect(asked).toHaveLength(12);
  });

  it("never asks an item the student already answered in an earlier sitting", () => {
    const week0 = sit(week0Plan(course), () => "right");
    const before = new Set(week0.responses.map((r) => r.item_id));
    const { asked } = sit(prelecturePlan(course, 2), () => "right", week0.responses);
    for (const a of asked) expect(before.has(a.id)).toBe(false);
  });
});

describe("review items", () => {
  it("go to the earlier lecture whose theta is least certain", () => {
    // lecture 1 is well measured, lecture 2 not at all: the review item must come from lecture 2
    const responses = ["as-ku-a-basic", "as-ku-a-applied", "as-ku-b-applied", "as-ku-b-advanced"].map((id, k) => answer(id, k % 2 ? "wrong" : "right"));
    const plan = prelecturePlan(course, 3);
    const review = nextAssessmentItem(plan, 2, { course, items, responses });
    expect(plan.slots[2].role).toBe("review");
    expect(review).toMatchObject({ role: "review", lecture_n: 2 });
  });

  it("break ties toward the earlier lecture", () => {
    const review = nextAssessmentItem(prelecturePlan(course, 3), 2, { course, items, responses: [] });
    expect(review?.lecture_n).toBe(1);
  });

  it("fall back to the lecture itself when no earlier lecture has an unseen item left", () => {
    const earlier = bank.filter((i) => lectureOfItem(i.id) < 3).map((i) => answer(i.id, "right"));
    const next = nextAssessmentItem(prelecturePlan(course, 3), 2, { course, items, responses: earlier });
    expect(next).toMatchObject({ lecture_n: 3, role: "new" });
  });

  it("are skipped, and the sitting ends, when nothing at all is left to ask", () => {
    const all = bank.map((i) => answer(i.id, "right"));
    expect(nextAssessmentItem(prelecturePlan(course, 2), 0, { course, items, responses: all })).toBeNull();
  });
});
