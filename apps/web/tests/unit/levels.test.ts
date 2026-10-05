import { describe, expect, it } from "vitest";
import { onboardingLevel, overallLevel } from "@/lib/logic/levels";
import { item, topics } from "./helpers";

const t = topics[2]; // Selection bias
const items = [item("ob-t3-1", "t3", "onboarding"), item("ob-t3-2", "t3", "onboarding")];
// correct_index is 1 for every helper item

describe("onboardingLevel (plan §4.1)", () => {
  it("2/2 correct -> Level 3 and says so", () => {
    const r = onboardingLevel(t, items, { "ob-t3-1": 1, "ob-t3-2": 1 });
    expect(r.level).toBe(3);
    expect(r.reason).toBe("You answered both questions on “Selection bias” correctly, so we skip the basics here.");
  });
  it("1 of 2 correct -> Level 2", () => {
    const r = onboardingLevel(t, items, { "ob-t3-1": 1, "ob-t3-2": 0 });
    expect(r.level).toBe(2);
    expect(r.reason).toContain("Right on 1 of 2 questions on “Selection bias”");
  });
  it("0 of 2 -> Level 1", () => {
    expect(onboardingLevel(t, items, { "ob-t3-1": 0, "ob-t3-2": 2 }).level).toBe(1);
  });
  it("all Not sure -> Level 1 with the 'Not sure' reason (missing evidence, not wrong)", () => {
    const r = onboardingLevel(t, items, { "ob-t3-1": "not_sure", "ob-t3-2": "not_sure" });
    expect(r.level).toBe(1);
    expect(r.notChecked).toBe(false);
    expect(r.reason).toContain("“Not sure” on both questions on “Selection bias”");
  });
  it("one right + one Not sure -> Level 2 (a Not sure is not counted as wrong)", () => {
    expect(onboardingLevel(t, items, { "ob-t3-1": 1, "ob-t3-2": "not_sure" }).level).toBe(2);
  });
  it("one wrong + one Not sure -> Level 1", () => {
    expect(onboardingLevel(t, items, { "ob-t3-1": 0, "ob-t3-2": "not_sure" }).level).toBe(1);
  });
  it("a topic with no onboarding items is 'not checked yet' at Level 1", () => {
    const r = onboardingLevel(topics[3], items, {}, "Lecture 3");
    expect(r).toMatchObject({ level: 1, notChecked: true });
    expect(r.reason).toContain("Lecture 3");
  });
});

describe("overallLevel", () => {
  it("is the median, rounded down when mixed", () => {
    expect(overallLevel([3, 2, 1])).toBe(2);
    expect(overallLevel([2, 3])).toBe(2);
    expect(overallLevel([1, 3, 3, 3])).toBe(3);
    expect(overallLevel([1, 1, 3, 3])).toBe(1);
    expect(overallLevel([])).toBe(1);
  });
});
