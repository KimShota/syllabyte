import { describe, expect, it } from "vitest";
import { formatClock, parseClock, stemPreview } from "./report";

describe("the report form's helpers", () => {
  it("reads a time as minutes:seconds or seconds, and empty as no time", () => {
    expect(parseClock("1:05")).toBe(65);
    expect(parseClock(" 0:7 ")).toBe(7);
    expect(parseClock("90")).toBe(90);
    expect(parseClock("")).toBeNull();
    expect(parseClock("  ")).toBeNull();
    expect(parseClock("1:75")).toBeUndefined();
    expect(parseClock("abc")).toBeUndefined();
    expect(parseClock("-3")).toBeUndefined();
  });

  it("writes seconds back as m:ss", () => {
    expect(formatClock(65.4)).toBe("1:05");
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(-4)).toBe("0:00");
  });

  it("folds code blocks and whitespace in a question's stem", () => {
    expect(stemPreview("What does this print?\n```python\nprint(1)\n```\nPick one.")).toBe("What does this print? [code] Pick one.");
    expect(stemPreview("An unclosed ```block")).toBe("An unclosed [code]");
  });
});
