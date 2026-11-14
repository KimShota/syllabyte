import { describe, expect, it } from "vitest";
import { DRIFT_POLICY, driftDecision, driftObservation, welcomeBackDecision, type DriftInput, type Visit } from "../src/logic/engagementDrift";

const MIN = 60_000;
const T = 1_000_000_000;
const visit = (i: number, coverage: number, completed = false): Visit => ({ videoId: `v${i}`, firstAt: T + i * MIN, coverage, completed });
const input = (over: Partial<DriftInput> = {}): DriftInput => ({ now: T + 30 * MIN, visits: [], away: [], answers: [], prompts: [], ...over });

describe("driftDecision", () => {
  it("fires on three early leaves in a row on its own", () => {
    const d = driftDecision(input({ visits: [visit(1, 1, true), visit(2, 0.1), visit(3, 0), visit(4, 0.3)] }));
    expect(d).toEqual({ fire: true, evidence: ["early_leaves:3"] });
  });

  it("does not fire on two early leaves alone, or when the run is broken by a video watched through", () => {
    expect(driftDecision(input({ visits: [visit(1, 0.1), visit(2, 0.2)] })).fire).toBe(false);
    expect(driftDecision(input({ visits: [visit(1, 0.1), visit(2, 0.2), visit(3, 0.95, true), visit(4, 0.1)] })).fire).toBe(false);
  });

  it("a completed video is never an early leave, however little of it played this time", () => {
    expect(driftDecision(input({ visits: [visit(1, 0.1, true), visit(2, 0.1, true), visit(3, 0.1, true)] })).fire).toBe(false);
  });

  it("fires on two weaker signals together: two early leaves plus repeated absences", () => {
    const away = [{ at: T + 25 * MIN, seconds: 40, videoId: "v1" }, { at: T + 28 * MIN, seconds: 20, videoId: "v2" }];
    const d = driftDecision(input({ visits: [visit(1, 0.1), visit(2, 0.2)], away }));
    expect(d).toEqual({ fire: true, evidence: ["early_leaves:2", "away:2"] });
  });

  it("ignores short absences and ones older than the window", () => {
    const away = [{ at: T + 29 * MIN, seconds: 5, videoId: null }, { at: T + 2 * MIN, seconds: 300, videoId: null }];
    expect(driftDecision(input({ visits: [visit(1, 0.1), visit(2, 0.2)], away })).fire).toBe(false);
  });

  it("counts wrong answers among the last three checks as a signal", () => {
    const answers = [{ correct: true, at: T }, { correct: false, at: T + MIN }, { correct: false, at: T + 2 * MIN }];
    const d = driftDecision(input({ visits: [visit(1, 0.1), visit(2, 0.2)], answers }));
    expect(d.evidence).toEqual(["early_leaves:2", "errors:2"]);
    expect(d.fire).toBe(true);
  });

  it("only counts evidence since the last prompt, so a dismissed prompt isn't re-offered for the same observations", () => {
    const visits = [visit(1, 0.1), visit(2, 0.1), visit(3, 0.1)];
    expect(driftDecision(input({ visits, prompts: [{ kind: "drift_check", shownAt: T + 3.5 * MIN }] })).fire).toBe(false);
  });

  it("respects the cooldown and the per-session budget, and says which held it back", () => {
    const visits = [visit(10, 0.1), visit(11, 0.1), visit(12, 0.1)].map((v) => ({ ...v, firstAt: v.firstAt + 10 * MIN }));
    const now = T + 23 * MIN;
    const recent = driftDecision(input({ now, visits, prompts: [{ kind: "welcome_back", shownAt: now - 3.5 * MIN }] }));
    expect(recent).toMatchObject({ fire: false, heldBack: "cooldown" });
    const spent = driftDecision(input({ now, visits, prompts: [{ kind: "drift_check", shownAt: T }, { kind: "drift_check", shownAt: T + 1 }] }));
    expect(spent).toMatchObject({ fire: false, heldBack: "budget" });
  });
});

describe("welcomeBackDecision", () => {
  const base = { awaySeconds: 120, position: 45, duration: 110, prompts: [] };
  it("offers a recall after a real absence partway through a video", () => {
    expect(welcomeBackDecision(base)).toBe(true);
  });
  it("not after a short absence, one long enough to end the session, at the start or at the end", () => {
    expect(welcomeBackDecision({ ...base, awaySeconds: 30 })).toBe(false);
    expect(welcomeBackDecision({ ...base, awaySeconds: DRIFT_POLICY.sessionGapMs / 1000 })).toBe(false);
    expect(welcomeBackDecision({ ...base, position: 5 })).toBe(false);
    expect(welcomeBackDecision({ ...base, position: 108 })).toBe(false);
  });
  it("at most twice a session", () => {
    const prompts = [{ kind: "welcome_back" as const, shownAt: 1 }, { kind: "welcome_back" as const, shownAt: 2 }];
    expect(welcomeBackDecision({ ...base, prompts })).toBe(false);
  });
});

describe("driftObservation", () => {
  it("describes what happened, never the student", () => {
    expect(driftObservation(["early_leaves:3"])).toBe("You moved on early from the last 3 videos.");
    expect(driftObservation(["early_leaves:2", "away:2", "errors:2"])).toBe("You moved on early from the last 2 videos, left the app 2 times and missed 2 of the last checks.");
    for (const text of [driftObservation(["early_leaves:3"]), driftObservation(["away:2", "errors:2"])]) expect(text).not.toMatch(/disengaged|bored|distracted|lazy/i);
  });
});
