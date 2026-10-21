import type { Level } from "../types";

/**
 * Computerized Adaptive Testing for one topic (= one lecture), on the 2PL model.
 *
 * A port of the Python engine in packages/assessment_agent/assessment_agent/cat.py, which runs on catsim and is
 * the engine of record (plan/per-ku-profiling-plan.md D3). The static Phase 0 demo has no server, so the same
 * maths runs here; tests/unit/catParity.test.ts replays golden sessions recorded from the Python engine and
 * fails if this module picks a different item or lands on a different theta.
 *
 * What is ported, and from where:
 *   - response curve and item information: catsim.irt (c = 0, d = 1, so P = 1 / (1 + e^(-a(theta - b)))
 *     and information = a² P (1 - P));
 *   - the maximum-likelihood search: scipy's bounded Brent minimiser on [-6, 6], which is what
 *     catsim's NumericalSearchEstimator(method="bounded") calls;
 *   - Dodd's heuristic for an all-correct / all-wrong pattern: catsim.cat.dodd, over the whole pool's difficulties;
 *   - selection: the most informative unseen item; ties go to the item earlier in the pool (catsim's argsort is
 *     not stable, so the Python engine fixes the order and this port matches it).
 *
 * Plan rules: "Not sure" is scored as a wrong answer (decided 2026-10-21, replacing rule 3, under which it never
 * entered the estimate); an answer given after a hint is scored as the same item made easier, b - hint_beta_shift (D10).
 */

export type Outcome = "correct" | "wrong" | "not_sure";

/** A 2PL item: discrimination `a`, difficulty `b` (logit scale). No guessing, no upper asymptote. */
export interface BankItem {
  id: string;
  a: number;
  b: number;
}

export interface Answer {
  item_id: string;
  outcome: Outcome;
  hinted?: boolean;
}

export interface CatConfig {
  length: number;
  start_theta?: number;
  hint_beta_shift?: number;
}

const THETA_MIN = -6;
const THETA_MAX = 6;
/** Two items whose information differs by less than this are "tied"; the earlier one in the pool wins. */
export const TIE_TOLERANCE = 1e-9;

function assertItem(it: BankItem): void {
  if (!(Number.isFinite(it.a) && it.a > 0)) throw new Error(`item ${it.id}: discrimination must be positive, got ${it.a}`);
  if (!Number.isFinite(it.b)) throw new Error(`item ${it.id}: difficulty must be finite, got ${it.b}`);
}

function byId(pool: readonly BankItem[]): Map<string, BankItem> {
  const m = new Map<string, BankItem>();
  for (const it of pool) {
    assertItem(it);
    m.set(it.id, it);
  }
  if (m.size !== pool.length) throw new Error("duplicate item ids in the pool");
  return m;
}

/** P(correct) for a 2PL item. */
export function icc(theta: number, a: number, b: number): number {
  return 1 / (1 + Math.exp(-a * (theta - b)));
}

/** Fisher information of a 2PL item at theta: a² P (1 - P). */
export function information(theta: number, a: number, b: number): number {
  const p = icc(theta, a, b);
  return a * a * p * (1 - p);
}

const sign0 = (x: number): number => Math.sign(x) + (x === 0 ? 1 : 0);

/** scipy.optimize._minimize_scalar_bounded (Brent's fminbound), xatol = 1e-5, at most 500 evaluations. */
function minimizeBounded(f: (x: number) => number, x1: number, x2: number, xatol = 1e-5, maxfun = 500): number {
  const sqrtEps = Math.sqrt(2.2e-16);
  const goldenMean = 0.5 * (3 - Math.sqrt(5));
  let a = x1;
  let b = x2;
  let fulc = a + goldenMean * (b - a);
  let nfc = fulc;
  let xf = fulc;
  let rat = 0;
  let e = 0;
  let x = xf;
  let fx = f(x);
  let num = 1;
  let fu = Infinity;
  let ffulc = fx;
  let fnfc = fx;
  let xm = 0.5 * (a + b);
  let tol1 = sqrtEps * Math.abs(xf) + xatol / 3;
  let tol2 = 2 * tol1;

  while (Math.abs(xf - xm) > tol2 - 0.5 * (b - a)) {
    let golden = true;
    if (Math.abs(e) > tol1) {
      golden = false;
      let r = (xf - nfc) * (fx - ffulc);
      let q = (xf - fulc) * (fx - fnfc);
      let p = (xf - fulc) * q - (xf - nfc) * r;
      q = 2 * (q - r);
      if (q > 0) p = -p;
      q = Math.abs(q);
      r = e;
      e = rat;
      if (Math.abs(p) < Math.abs(0.5 * q * r) && p > q * (a - xf) && p < q * (b - xf)) {
        rat = p / q;
        x = xf + rat;
        if (x - a < tol2 || b - x < tol2) rat = tol1 * sign0(xm - xf);
      } else {
        golden = true;
      }
    }
    if (golden) {
      e = xf >= xm ? a - xf : b - xf;
      rat = goldenMean * e;
    }
    x = xf + sign0(rat) * Math.max(Math.abs(rat), tol1);
    fu = f(x);
    num += 1;

    if (fu <= fx) {
      if (x >= xf) a = xf;
      else b = xf;
      fulc = nfc;
      ffulc = fnfc;
      nfc = xf;
      fnfc = fx;
      xf = x;
      fx = fu;
    } else {
      if (x < xf) a = x;
      else b = x;
      if (fu <= fnfc || nfc === xf) {
        fulc = nfc;
        ffulc = fnfc;
        nfc = x;
        fnfc = fu;
      } else if (fu <= ffulc || fulc === xf || fulc === nfc) {
        fulc = x;
        ffulc = fu;
      }
    }
    xm = 0.5 * (a + b);
    tol1 = sqrtEps * Math.abs(xf) + xatol / 3;
    tol2 = 2 * tol1;
    if (num >= maxfun) break;
  }
  return xf;
}

interface Scored {
  item: BankItem;
  shift: number;
  correct: boolean;
}

function scored(items: Map<string, BankItem>, answers: readonly Answer[], hintBetaShift: number): Scored[] {
  const out: Scored[] = [];
  // "Not sure" is scored as wrong, with no hint shift
  for (const a of answers) {
    const item = items.get(a.item_id);
    if (!item) throw new Error(`answer for unknown item ${a.item_id}`);
    const hinted = a.hinted && a.outcome !== "not_sure";
    out.push({ item, shift: hinted ? hintBetaShift : 0, correct: a.outcome === "correct" });
  }
  return out;
}

/**
 * Ability after `answers`, replaying them in order the way a live CAT would. Replaying matters only for Dodd's
 * heuristic, which is defined from the previous estimate: while every scored answer so far is correct (or every
 * one wrong) theta moves halfway toward the pool's hardest (easiest) item; once the pattern is mixed the
 * maximum-likelihood estimate takes over and ignores the past.
 *
 * Known quirk, inherited from catsim: Dodd's value is a heuristic, not a maximum-likelihood estimate, so with a
 * narrow pool "all correct" can land below "all but one correct". It is always finite and inside the pool's range.
 */
export function estimateTheta(pool: readonly BankItem[], answers: readonly Answer[], startTheta = 0, hintBetaShift = 1): number {
  if (pool.length === 0) throw new Error("empty pool");
  const items = byId(pool);
  const bs = pool.map((it) => it.b);
  const bMax = Math.max(...bs);
  const bMin = Math.min(...bs);
  const all = scored(items, answers, hintBetaShift);
  let theta = startTheta;
  for (let k = 1; k <= all.length; k++) {
    const upto = all.slice(0, k);
    const nCorrect = upto.filter((s) => s.correct).length;
    if (nCorrect === k) theta = theta + (bMax - theta) / 2;
    else if (nCorrect === 0) theta = theta - (theta - bMin) / 2;
    else {
      const negLogLik = (t: number): number => {
        let ll = 0;
        for (const s of upto) {
          const p = icc(t, s.item.a, s.item.b - s.shift);
          ll += s.correct ? Math.log(p) : Math.log(1 - p);
        }
        return -ll;
      };
      theta = minimizeBounded(negLogLik, THETA_MIN, THETA_MAX);
    }
  }
  return theta;
}

/** 1 / sqrt(test information) at `theta` over the scored answers; Infinity before any evidence. */
export function standardError(pool: readonly BankItem[], answers: readonly Answer[], theta: number, hintBetaShift = 1): number {
  const all = scored(byId(pool), answers, hintBetaShift);
  if (all.length === 0) return Infinity;
  const info = all.reduce((sum, s) => sum + information(theta, s.item.a, s.item.b - s.shift), 0);
  return info > 0 ? 1 / Math.sqrt(info) : Infinity;
}

/** The most informative item not yet administered, ties to the earlier item; null when none are left. */
export function selectNext(pool: readonly BankItem[], administered: ReadonlySet<string>, theta: number): BankItem | null {
  const free: number[] = [];
  pool.forEach((it, i) => {
    if (!administered.has(it.id)) free.push(i);
  });
  if (free.length === 0) return null;
  const info = pool.map((it) => information(theta, it.a, it.b));
  const best = Math.max(...free.map((i) => info[i]));
  for (const i of free) if (info[i] >= best - TIE_TOLERANCE) return pool[i];
  throw new Error("unreachable");
}

/** One adaptive test: `config.length` items from `pool`, each chosen from the answers before it. */
export class CatSession {
  readonly answers: Answer[] = [];
  theta: number;
  private readonly startTheta: number;
  private readonly hintBetaShift: number;

  constructor(
    readonly pool: readonly BankItem[],
    readonly config: CatConfig,
  ) {
    byId(pool);
    this.startTheta = config.start_theta ?? 0;
    this.hintBetaShift = config.hint_beta_shift ?? 1;
    this.theta = this.startTheta;
  }

  get done(): boolean {
    return this.answers.length >= this.config.length || this.answers.length >= this.pool.length;
  }

  get nScored(): number {
    return this.answers.length; // every answer is scored; "Not sure" as wrong
  }

  nextItem(): BankItem | null {
    if (this.done) return null;
    return selectNext(this.pool, new Set(this.answers.map((a) => a.item_id)), this.theta);
  }

  answer(itemId: string, outcome: Outcome, hinted = false): number {
    if (this.answers.some((a) => a.item_id === itemId)) throw new Error(`item ${itemId} was already answered`);
    if (!this.pool.some((it) => it.id === itemId)) throw new Error(`unknown item ${itemId}`);
    this.answers.push({ item_id: itemId, outcome, hinted });
    this.theta = estimateTheta(this.pool, this.answers, this.startTheta, this.hintBetaShift);
    return this.theta;
  }

  get standardError(): number {
    return standardError(this.pool, this.answers, this.theta, this.hintBetaShift);
  }
}

/**
 * From a topic's ability to a Knowledge Unit's readiness level (plan D6; proposal §3.2): Level 3 (proficient) if
 * theta reaches the KU's advanced item, 2 (developing) if it reaches its applied item, else 1 (novice).
 *
 * With no scored answer theta is just the starting value and says nothing, so the KU is novice (D7). The advanced
 * threshold is never taken below the applied one, so a bank whose tiers came out of order cannot make a student
 * proficient without being developing.
 */
export function readinessLevel(theta: number, bApplied: number, bAdvanced: number, nScored: number): Level {
  if (nScored === 0) return 1;
  if (theta >= Math.max(bAdvanced, bApplied)) return 3;
  if (theta >= bApplied) return 2;
  return 1;
}
