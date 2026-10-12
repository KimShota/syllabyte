import { describe, expect, it } from "vitest";
import { CatSession, estimateTheta, readinessLevel, selectNext, standardError, type Answer, type BankItem } from "@/lib/logic/cat";

const pool = (...bs: number[]): BankItem[] => bs.map((b, k) => ({ id: `i${k}`, a: 1, b }));
const ans = (item_id: string, outcome: Answer["outcome"], hinted = false): Answer => ({ item_id, outcome, hinted });

describe("item selection", () => {
  it("picks the item closest to theta when discrimination is equal", () => {
    const p = pool(-2, -0.4, 0.9, 1.7);
    expect(selectNext(p, new Set(), 0)?.id).toBe("i1");
    expect(selectNext(p, new Set(), 1)?.id).toBe("i2");
    expect(selectNext(p, new Set(), 5)?.id).toBe("i3");
  });

  it("skips administered items and returns null when none are left", () => {
    const p = pool(-1, 0, 1);
    expect(["i0", "i2"]).toContain(selectNext(p, new Set(["i1"]), 0)?.id);
    expect(selectNext(p, new Set(["i0", "i1", "i2"]), 0)).toBeNull();
  });

  it("breaks ties by pool order", () => {
    expect(selectNext(pool(0.5, -0.5), new Set(), 0)?.id).toBe("i0");
    expect(selectNext(pool(-0.5, 0.5), new Set(), 0)?.id).toBe("i0");
    expect(selectNext(pool(0.5, -0.5, 0.5), new Set(["i0"]), 0)?.id).toBe("i1");
  });

  it("prefers a sharper item over a closer, blunter one (2PL)", () => {
    const p: BankItem[] = [{ id: "blunt", a: 0.5, b: 0.1 }, { id: "sharp", a: 2, b: 0.6 }];
    expect(selectNext(p, new Set(), 0)?.id).toBe("sharp");
  });
});

describe("ability estimate", () => {
  it("leaves theta at the start without evidence", () => {
    expect(estimateTheta(pool(-1, 0, 1), [], 0.3)).toBe(0.3);
  });

  it("uses Dodd over the whole pool, recursively, for an all-correct pattern", () => {
    const p = pool(-1, 0, 2); // hardest item is 2, even if never asked
    expect(estimateTheta(p, [ans("i0", "correct")])).toBeCloseTo(1.0, 12); // 0 + (2 - 0) / 2
    expect(estimateTheta(p, [ans("i0", "correct"), ans("i1", "correct")])).toBeCloseTo(1.5, 12); // 1 + (2 - 1) / 2
  });

  it("uses Dodd toward the easiest item for an all-wrong pattern", () => {
    expect(estimateTheta(pool(-1, 0, 2), [ans("i1", "wrong")])).toBeCloseTo(-0.5, 12); // 0 - (0 + 1) / 2
  });

  it("finds the maximum-likelihood estimate for mixed answers", () => {
    const p = pool(-1.2, -0.3, 0.4, 1.1, 1.9);
    const answers = [ans("i0", "correct"), ans("i1", "correct"), ans("i2", "wrong"), ans("i3", "wrong")];
    const got = estimateTheta(p, answers);
    const ll = (t: number) =>
      [true, true, false, false].reduce((s, ok, k) => {
        const pr = 1 / (1 + Math.exp(-(t - p[k].b)));
        return s + Math.log(ok ? pr : 1 - pr);
      }, 0);
    let best = -6;
    for (let t = -6; t <= 6; t += 0.0001) if (ll(t) > ll(best)) best = t;
    expect(Math.abs(got - best)).toBeLessThan(1e-3);
  });

  it("never lowers theta for one more correct answer among mixed patterns", () => {
    const p = pool(-1, -0.5, 0, 0.5, 1, 1.5);
    const order = ["i2", "i3", "i1", "i4", "i0", "i5"];
    for (let k = 1; k <= 4; k++) {
      const worse = order.map((id, n) => ans(id, n < k ? "correct" : "wrong"));
      const better = order.map((id, n) => ans(id, n <= k ? "correct" : "wrong"));
      expect(estimateTheta(p, better)).toBeGreaterThanOrEqual(estimateTheta(p, worse));
    }
  });

  it("ignores 'Not sure' answers completely", () => {
    const p = pool(-1, 0, 1, 0.5);
    const base = [ans("i0", "correct"), ans("i1", "wrong")];
    expect(estimateTheta(p, [...base, ans("i2", "not_sure")])).toBe(estimateTheta(p, base));
    expect(estimateTheta(p, [ans("i2", "not_sure"), ans("i3", "not_sure")], 0.2)).toBe(0.2);
  });

  it("counts a hinted correct answer for less, and a hinted wrong answer as worse", () => {
    const p = pool(-1, 0, 1, 0.5);
    const up = [ans("i0", "correct"), ans("i2", "wrong"), ans("i3", "wrong")];
    expect(estimateTheta(p, [...up, ans("i1", "correct", true)])).toBeLessThan(estimateTheta(p, [...up, ans("i1", "correct")]));
    const down = [ans("i0", "correct"), ans("i2", "correct"), ans("i3", "correct")];
    expect(estimateTheta(p, [...down, ans("i1", "wrong", true)])).toBeLessThan(estimateTheta(p, [...down, ans("i1", "wrong")]));
  });

  it("a hint shift of zero means hints have no effect", () => {
    const p = pool(-1, 0, 1);
    const a = [ans("i0", "correct"), ans("i1", "wrong", true), ans("i2", "wrong")];
    expect(estimateTheta(p, a, 0, 0)).toBe(estimateTheta(p, a.map((x) => ({ ...x, hinted: false }))));
  });

  it("rejects unknown items, duplicate ids and bad parameters", () => {
    expect(() => estimateTheta(pool(0), [ans("nope", "correct")])).toThrow(/unknown item/);
    expect(() => estimateTheta([{ id: "x", a: 1, b: 0 }, { id: "x", a: 1, b: 1 }], [])).toThrow(/duplicate/);
    expect(() => new CatSession([{ id: "x", a: 0, b: 0 }], { length: 1 })).toThrow(/discrimination/);
    expect(() => new CatSession([{ id: "x", a: 1, b: NaN }], { length: 1 })).toThrow(/difficulty/);
  });
});

describe("standard error", () => {
  it("is infinite without evidence and shrinks with more items", () => {
    const p = pool(-1, -0.5, 0, 0.5, 1);
    expect(standardError(p, [], 0)).toBe(Infinity);
    const two = [ans("i1", "correct"), ans("i3", "wrong")];
    const five = [...two, ans("i0", "correct"), ans("i2", "correct"), ans("i4", "wrong")];
    expect(standardError(p, five, 0)).toBeLessThan(standardError(p, two, 0));
  });

  it("matches the closed form for Rasch items", () => {
    const info = [-0.5, 0.5].reduce((s, b) => s + Math.exp(b) / (1 + Math.exp(b)) ** 2, 0);
    expect(standardError(pool(-0.5, 0.5), [ans("i0", "correct"), ans("i1", "wrong")], 0)).toBeCloseTo(1 / Math.sqrt(info), 12);
  });

  it("stays near one logit after four items with alpha = 1 (the limitation recorded in the plan)", () => {
    const p = pool(-0.3, -0.1, 0.1, 0.3);
    const a = [ans("i0", "correct"), ans("i1", "wrong"), ans("i2", "correct"), ans("i3", "wrong")];
    const se = standardError(p, a, 0);
    expect(se).toBeGreaterThan(0.9);
    expect(se).toBeLessThan(1.2);
  });
});

describe("session", () => {
  it("asks exactly `length` items, each chosen from the answers before it", () => {
    const s = new CatSession(pool(-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2), { length: 4 });
    const asked: number[] = [];
    for (let it = s.nextItem(); it; it = s.nextItem()) {
      asked.push(it.b);
      s.answer(it.id, "correct");
    }
    expect(asked).toEqual([0, 1, 1.5, 2]); // all correct: theta climbs, so each item is harder
    expect(s.done).toBe(true);
  });

  it("counts 'Not sure' toward the length but not the estimate", () => {
    const s = new CatSession(pool(-1, 0, 1, 2, 3), { length: 3 });
    for (let k = 0; k < 3; k++) s.answer(s.nextItem()!.id, "not_sure");
    expect(s.done).toBe(true);
    expect(s.nScored).toBe(0);
    expect(s.theta).toBe(0);
    expect(s.standardError).toBe(Infinity);
  });

  it("stops when the pool runs out and refuses repeated or unknown items", () => {
    const s = new CatSession(pool(-1, 0, 1), { length: 5 });
    for (let it = s.nextItem(); it; it = s.nextItem()) s.answer(it.id, "wrong");
    expect(s.answers).toHaveLength(3);
    expect(s.nextItem()).toBeNull();
    const t = new CatSession(pool(-1, 0, 1), { length: 3 });
    t.answer("i1", "correct");
    expect(() => t.answer("i1", "wrong")).toThrow(/already answered/);
    expect(() => t.answer("zzz", "wrong")).toThrow(/unknown/);
  });

  it("starts from the configured theta", () => {
    const s = new CatSession(pool(-2, -1, 0, 1, 2), { length: 2, start_theta: -1.4 });
    expect(s.nextItem()?.b).toBe(-1);
    expect(s.theta).toBe(-1.4);
  });
});

describe("readiness level (the tier rule)", () => {
  it.each([[-2, 1], [-0.01, 1], [0, 2], [0.9, 2], [1, 3], [3, 3]] as const)("theta %s → level %s", (theta, level) => {
    expect(readinessLevel(theta, 0, 1, 4)).toBe(level);
  });

  it("is novice with no scored answers whatever theta says", () => {
    expect(readinessLevel(5, 0, 1, 0)).toBe(1);
  });

  it("cannot skip 'developing' when the tiers came out of order", () => {
    expect(readinessLevel(0.2, 0.6, 0.1, 3)).toBe(1);
    expect(readinessLevel(0.7, 0.6, 0.1, 3)).toBe(3);
  });

  it("judges each KU by its own items at the same theta", () => {
    expect([readinessLevel(0.5, -0.5, 0.4, 4), readinessLevel(0.5, 0.8, 1.6, 4)]).toEqual([3, 1]);
  });
});
