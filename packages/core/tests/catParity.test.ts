import { describe, expect, it } from "vitest";
import { CatSession, type BankItem, type Outcome } from "../src/logic/cat";
import parity from "./fixtures/cat-parity.json";

// Golden sessions recorded from the Python engine (assessment_agent.cat, on catsim). Regenerate with
// `uv run python scripts/make_cat_parity.py` after changing either engine. The TypeScript port must choose the
// same item at every step and land on the same theta and standard error (plan D3).
interface Step {
  item_id: string;
  outcome: Outcome;
  hinted: boolean;
  theta: number;
  se: number | null;
}
interface Case {
  name: string;
  items: BankItem[];
  length: number;
  start_theta: number;
  hint_beta_shift: number;
  steps: Step[];
}
const tol: number = parity.theta_tolerance;
const cases = parity.cases as Case[];

describe("CAT parity with the Python engine", () => {
  it("has a useful number of recorded sessions", () => {
    expect(cases.length).toBeGreaterThanOrEqual(20);
    expect(cases.reduce((n, c) => n + c.steps.length, 0)).toBeGreaterThan(100);
  });

  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const s = new CatSession(c.items, { length: c.length, start_theta: c.start_theta, hint_beta_shift: c.hint_beta_shift });
    c.steps.forEach((step, k) => {
      const where = `${c.name} step ${k}`;
      expect(s.nextItem()?.id, `${where}: item`).toBe(step.item_id);
      s.answer(step.item_id, step.outcome, step.hinted);
      expect(Math.abs(s.theta - step.theta), `${where}: theta ${s.theta} vs ${step.theta}`).toBeLessThanOrEqual(tol);
      if (step.se === null) expect(s.standardError, `${where}: se`).toBe(Infinity);
      else expect(Math.abs(s.standardError - step.se), `${where}: se`).toBeLessThanOrEqual(tol);
    });
    expect(s.nextItem(), `${c.name}: session ends where the Python one did`).toBeNull();
  });
});
