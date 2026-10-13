import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { nextAssessmentItem, prelecturePlan, week0Plan, type AssessmentPlan } from "@/lib/logic/assessment";
import { kuLevels } from "@/lib/logic/kuProfile";
import type { Course, Item, ResponseRecord } from "@/lib/types";

// Simulated students sit the baseline and a pre-lecture check on the REAL generated bank and course, to check that
// what comes out is sensible: every KU gets a level, stronger students get higher ones, and no item repeats. The
// fixtures are local-only (course material), so without them the suite skips.
const dir = resolve(__dirname, "../../fixtures");
const have = existsSync(resolve(dir, "bank.json")) && existsSync(resolve(dir, "course.json"));

describe.skipIf(!have)("per-KU profiling on the real bank", () => {
  async function load() {
    const { FIX } = await import("@/lib/fixtures");
    const bank: Item[] = JSON.parse(readFileSync(resolve(dir, "bank.json"), "utf8"));
    return { course: FIX.course as Course, items: [...FIX.items, ...bank] };
  }

  /** A deterministic student: right exactly when their ability reaches the item's difficulty. */
  function sit(plan: AssessmentPlan, how: (it: Item) => "right" | "wrong" | "not_sure", ctx: { course: Course; items: Item[] }, prior: ResponseRecord[] = []) {
    const responses = [...prior];
    const asked: ReturnType<typeof nextAssessmentItem>[] = [];
    for (let k = 0; ; k++) {
      const next = nextAssessmentItem(plan, k, { ...ctx, responses });
      if (!next) break;
      asked.push(next);
      const o = how(next.item);
      responses.push({
        id: `r${prior.length + k}`, item_id: next.item.id, topic_id: next.item.topic_id, video_id: null, context: "assessment",
        choice: o === "not_sure" ? "not_sure" : o === "right" ? next.item.correct_index : (next.item.correct_index + 1) % 3,
        correct: o === "not_sure" ? null : o === "right", confidence: null, hint_used: false, latency_ms: 1, at: prior.length + k,
      });
    }
    return { asked, responses };
  }
  const student = (theta: number) => (it: Item) => (theta >= it.difficulty_prior ? "right" : "wrong") as "right" | "wrong";

  async function levelsFor(how: (it: Item) => "right" | "wrong" | "not_sure") {
    const ctx = await load();
    const { responses, asked } = sit(week0Plan(ctx.course), how, ctx);
    return { ...ctx, responses, asked, levels: kuLevels({ ...ctx, responses }) };
  }
  const total = (l: Record<string, { level: number }>) => Object.values(l).reduce((n, x) => n + x.level, 0);

  it("asks the baseline's fixed length, never the same item twice", async () => {
    const { asked, course } = await levelsFor(student(0));
    expect(asked).toHaveLength(Math.min(course.config.cat_week0_length, course.config.cat_items_per_topic * Math.min(course.config.cat_week0_lectures, course.lectures.length)));
    expect(new Set(asked.map((a) => a!.item.id)).size).toBe(asked.length);
  });

  it("gives every KU a level, and orders students by ability", async () => {
    const weak = await levelsFor(student(-2));
    const mid = await levelsFor(student(0));
    const strong = await levelsFor(student(2));
    for (const r of [weak, mid, strong]) expect(Object.keys(r.levels)).toHaveLength(r.course.kus.length);
    expect(total(weak.levels)).toBeLessThan(total(mid.levels));
    expect(total(mid.levels)).toBeLessThan(total(strong.levels));
    expect(Object.values(weak.levels).every((l) => l.level === 1)).toBe(true);
    expect(Object.values(strong.levels).filter((l) => l.level === 3).length).toBeGreaterThan(strong.course.kus.length / 2);
  });

  it("is novice everywhere for a student who answers 'Not sure' throughout, with reasons that say so", async () => {
    const { levels, course } = await levelsFor(() => "not_sure");
    for (const l of Object.values(levels)) expect(l.level).toBe(1);
    const asked = Object.values(levels).filter((l) => !l.not_checked);
    expect(asked.length).toBeGreaterThan(0);
    for (const l of asked) expect(l.reason).toMatch(/^You chose “Not sure” on (both|all \d+) questions on “/);
    expect(course.kus.length).toBeGreaterThan(0);
  });

  it("lets a lecture the baseline did not cover borrow the pooled ability, and says so", async () => {
    const ctx = await load();
    const course = { ...ctx.course, config: { ...ctx.course.config, cat_week0_lectures: 1 } };
    const { responses } = sit(week0Plan(course), student(0), { ...ctx, course });
    const levels = kuLevels({ course, items: ctx.items, responses });
    const lecture2 = course.kus.filter((k) => k.lecture_n === 2);
    expect(lecture2.length).toBeGreaterThan(0);
    for (const k of lecture2) {
      expect(levels[k.id].provisional).toBe(true);
      expect(levels[k.id].reason).toMatch(/^We have not asked about “/);
    }
  });

  it("runs a pre-lecture check after the baseline: new items on the lecture, review items before it, nothing repeated", async () => {
    const ctx = await load();
    const week0 = sit(week0Plan(ctx.course), student(0.5), ctx);
    const plan = prelecturePlan(ctx.course, 3);
    const check = sit(plan, student(0.5), ctx, week0.responses);
    const before = new Set(week0.responses.map((r) => r.item_id));
    expect(check.asked).toHaveLength(ctx.course.config.cat_prelecture_new + ctx.course.config.cat_prelecture_review);
    for (const a of check.asked) expect(before.has(a!.item.id)).toBe(false);
    expect(check.asked.filter((a) => a!.role === "review").every((a) => a!.lecture_n < 3)).toBe(true);
    expect(check.asked.filter((a) => a!.role === "new").every((a) => a!.lecture_n === 3)).toBe(true);
  });
});
