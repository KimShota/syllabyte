import { describe, expect, it } from "vitest";
import { DROPOFF_GRACE_MS, droppedEarly, replayedMany } from "../src/logic/engagement";
import { MINUTE } from "../src/util";
import { course, } from "./kuHelpers";
import { T0 } from "./helpers";

const cfg = course.config; // dropoff fraction 0.6, replay count 3
const prog = (max_t: number, ago = 2 * DROPOFF_GRACE_MS) => ({ max_t, duration_s: 100, last_at: T0 - ago });

describe("dropped early", () => {
  it("is true for an unfinished video left before the threshold", () => {
    expect(droppedEarly(prog(40), false, cfg, T0)).toBe(true);
    expect(droppedEarly(prog(59), false, cfg, T0)).toBe(true);
  });
  it("is false once the student got far enough, or finished", () => {
    expect(droppedEarly(prog(60), false, cfg, T0)).toBe(false);
    expect(droppedEarly(prog(40), true, cfg, T0)).toBe(false);
  });
  it("waits out a pause: not dropped until the grace period has passed", () => {
    expect(droppedEarly(prog(40, 5 * MINUTE), false, cfg, T0)).toBe(false);
    expect(droppedEarly(prog(40, DROPOFF_GRACE_MS), false, cfg, T0)).toBe(true);
  });
  it("is false for a video that was never started or has no recorded length", () => {
    expect(droppedEarly(undefined, false, cfg, T0)).toBe(false);
    expect(droppedEarly(prog(0), false, cfg, T0)).toBe(false);
    expect(droppedEarly({ max_t: 10, duration_s: 0, last_at: 0 }, false, cfg, T0)).toBe(false);
  });
});

describe("replayed many times", () => {
  const w = (views: number) => ({ first_at: T0, last_at: T0, views });
  it("triggers at refresher_replay_count views", () => {
    expect(replayedMany(w(2), cfg)).toBe(false);
    expect(replayedMany(w(3), cfg)).toBe(true);
    expect(replayedMany(undefined, cfg)).toBe(false);
  });
  it("follows the config", () => {
    expect(replayedMany(w(2), { ...cfg, refresher_replay_count: 2 })).toBe(true);
  });
});
