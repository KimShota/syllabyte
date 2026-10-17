import { describe, expect, it } from "vitest";
import { isCorrect, LEVEL_NAMES, levelLabel, overallLevel } from "../src/logic/levels";
import { item } from "./helpers";

describe("level labels", () => {
  it("names the three levels", () => {
    expect(LEVEL_NAMES).toEqual({ 1: "Foundations", 2: "Core", 3: "Advanced" });
    expect(levelLabel(2)).toBe("Level 2 · Core");
  });
});

describe("overallLevel (the median of the KU levels, leaning toward more help)", () => {
  it("is the median", () => {
    expect(overallLevel([3, 3, 2, 3, 2])).toBe(3);
    expect(overallLevel([1, 2, 3])).toBe(2);
  });
  it("rounds down when mixed, so an even split leans toward more help", () => {
    expect(overallLevel([1, 3])).toBe(1);
    expect(overallLevel([2, 2, 3, 3])).toBe(2);
  });
  it("is Level 1 with nothing to go on", () => {
    expect(overallLevel([])).toBe(1);
  });
});

describe("isCorrect", () => {
  const it1 = item("x", "lecture-1", "assessment"); // the keyed answer is option 1
  it("is true for the keyed option, false for another, and null for 'Not sure' (missing evidence, never wrong)", () => {
    expect(isCorrect(it1, 1)).toBe(true);
    expect(isCorrect(it1, 0)).toBe(false);
    expect(isCorrect(it1, "not_sure")).toBeNull();
  });
});
