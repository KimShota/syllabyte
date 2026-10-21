import type { Course, Item, ItemContext, ItemTier, KuEntry, Level, LevelUpdate, ResponseRecord } from "../types";
import { estimateTheta, readinessLevel, standardError, type Answer, type BankItem } from "./cat";

/**
 * From everything a student has answered to a level for each Knowledge Unit
 * (plan/per-ku-profiling-plan.md D2, D6, D7, D10).
 *
 *   - One ability (theta) per lecture, estimated from ALL the answers on that lecture's items: the adaptive
 *     assessment items, and the quick-check, next-day and prove-it items of its videos. A hinted answer counts as
 *     the same item made easier; "Not sure" counts for nothing (plan §2 rule 3).
 *   - A KU's level is the tier rule on that theta and the KU's own item difficulties.
 *   - A lecture nobody has asked about yet borrows the theta pooled over everything answered so far ("provisional"),
 *     so every KU has a level from day one; a lecture answered entirely "Not sure" is novice (D7).
 *
 * Every "because…" sentence is a template over these stored counts, never free text (rule 4).
 */

/** Items that carry evidence about a lecture's KUs. Anything else a student answers is not about a KU. */
export const EVIDENCE_CONTEXTS: readonly ItemContext[] = ["assessment", "checkpoint", "next_session", "prove_it"];

export interface ProfileInput {
  course: Course;
  items: Item[];
  responses: ResponseRecord[];
}

const lectureOfKu = (course: Course): Map<string, number> => new Map(course.kus.map((k) => [k.id, k.lecture_n]));

/** The item as the IRT model sees it: discrimination `a`, difficulty `b`. */
export function toBankItem(it: Item): BankItem {
  return { id: it.id, a: it.discrimination, b: it.difficulty_prior };
}

/** Items about one lecture's KUs, in fixture order (the order ties are broken in). */
export function evidenceItems(course: Course, items: Item[], lectureN: number): Item[] {
  const lec = lectureOfKu(course);
  return items.filter((i) => i.ku_id !== null && EVIDENCE_CONTEXTS.includes(i.context) && lec.get(i.ku_id) === lectureN);
}

/** Tier offsets of `assessment_agent/bank.py` (TIER_BETA_OFFSET), for a KU with neither tier difficulties nor items. */
const TIER_OFFSET: Record<ItemTier, number> = { basic: -1, applied: 0, advanced: 1 };

/**
 * A KU's question difficulty at each tier: set at extraction for uploaded courses (V4), else read off its bank
 * items, else the plain tier offsets. A tier with no item takes the offset from the tiers that have one.
 */
export function tierDifficulty(ku: KuEntry, items: readonly Item[]): Record<ItemTier, number> {
  if (ku.tier_difficulty) return ku.tier_difficulty;
  const own = new Map<ItemTier, number>();
  for (const i of items) if (i.ku_id === ku.id && i.context === "assessment" && i.tier && !own.has(i.tier)) own.set(i.tier, i.difficulty_prior);
  if (!own.size) return { ...TIER_OFFSET };
  const [t0, b0] = [...own.entries()][0];
  const shift = b0 - TIER_OFFSET[t0];
  return { basic: own.get("basic") ?? TIER_OFFSET.basic + shift, applied: own.get("applied") ?? TIER_OFFSET.applied + shift, advanced: own.get("advanced") ?? TIER_OFFSET.advanced + shift };
}

/** The adaptive-assessment bank of one lecture: what a CAT draws from. */
export function bankItems(course: Course, items: Item[], lectureN: number): Item[] {
  return evidenceItems(course, items, lectureN).filter((i) => i.context === "assessment");
}

/**
 * The student's answers to `pool`, in the order they were given. A repeated item (Watch again re-asks the check)
 * counts once, by its latest answer, as `missedVideo` does.
 */
export function answersFor(pool: readonly { id: string }[], responses: readonly ResponseRecord[]): Answer[] {
  const ids = new Set(pool.map((p) => p.id));
  const latest = new Map<string, { r: ResponseRecord; order: number }>();
  responses.forEach((r, order) => {
    if (!ids.has(r.item_id)) return;
    const prev = latest.get(r.item_id);
    if (!prev || r.at >= prev.r.at) latest.set(r.item_id, { r, order });
  });
  return [...latest.values()]
    .sort((a, b) => a.r.at - b.r.at || a.order - b.order)
    .map(({ r }) => ({
      item_id: r.item_id,
      outcome: r.choice === "not_sure" ? "not_sure" : r.correct ? "correct" : "wrong",
      hinted: r.hint_used,
    }));
}

export interface KuCounts {
  right: number;
  wrong: number;
  notSure: number;
}

/** What the student has answered about one KU, across assessment and video items (latest answer per item). */
export function kuCounts(kuId: string, items: Item[], responses: ResponseRecord[]): KuCounts {
  const own = items.filter((i) => i.ku_id === kuId && EVIDENCE_CONTEXTS.includes(i.context));
  const c: KuCounts = { right: 0, wrong: 0, notSure: 0 };
  for (const a of answersFor(own, responses)) {
    if (a.outcome === "not_sure") c.notSure += 1;
    else if (a.outcome === "correct") c.right += 1;
    else c.wrong += 1;
  }
  return c;
}

export interface Estimate {
  theta: number;
  /** answers given, "Not sure" included */
  n_shown: number;
  /** answers that entered the estimate */
  n_scored: number;
  n_right: number;
  n_not_sure: number;
  /** standard error of theta; Infinity before any scored answer */
  se: number;
}

/**
 * `range`: questions not written yet (V4), one per KU and tier, as the IRT model would see them. Nobody has answered
 * them, so they only set the span Dodd's heuristic moves theta within: the same span a full bank would give, so a
 * student who gets everything right can reach the advanced tier before an advanced question exists.
 */
function estimateFrom(pool: Item[], responses: ResponseRecord[], startTheta: number, shift: number, range: BankItem[] = []): Estimate {
  const answers = answersFor(pool, responses);
  const bank = [...pool.map(toBankItem), ...range];
  const theta = bank.length === 0 ? startTheta : estimateTheta(bank, answers, startTheta, shift);
  return {
    theta,
    n_shown: answers.length,
    // every answer is scored, "Not sure" as wrong
    n_scored: answers.length,
    n_right: answers.filter((a) => a.outcome === "correct").length,
    n_not_sure: answers.filter((a) => a.outcome === "not_sure").length,
    se: bank.length === 0 ? Infinity : standardError(bank, answers, theta, shift),
  };
}

/** The questions a lecture's KUs could still be asked at, for the estimate's range (on demand only). */
function unwrittenRange(course: Course, items: readonly Item[], lectureN: number | null): BankItem[] {
  if (!course.config.questions_on_demand) return [];
  return course.kus
    .filter((k) => lectureN === null || k.lecture_n === lectureN)
    .flatMap((k) => Object.entries(tierDifficulty(k, items)).map(([t, b]) => ({ id: `unwritten:${k.id}:${t}`, a: 1, b })));
}

/** Ability and evidence counts for one lecture. */
export function lectureEstimate({ course, items, responses }: ProfileInput, lectureN: number): Estimate {
  const cfg = course.config;
  return estimateFrom(evidenceItems(course, items, lectureN), responses, cfg.cat_start_theta, cfg.irt_hint_beta_shift, unwrittenRange(course, items, lectureN));
}

/** Ability over everything answered, across lectures: the provisional theta for a lecture not asked about yet. */
export function pooledEstimate({ course, items, responses }: ProfileInput): Estimate {
  const cfg = course.config;
  const all = course.lectures.flatMap((l) => evidenceItems(course, items, l.n));
  return estimateFrom(all, responses, cfg.cat_start_theta, cfg.irt_hint_beta_shift, unwrittenRange(course, items, null));
}

export interface KuLevelEstimate {
  ku_id: string;
  lecture_n: number;
  level: Level;
  /** nothing answered anywhere yet: the dashed "not checked" state */
  not_checked: boolean;
  /** the level rests on other lectures' answers, not on this lecture's own */
  provisional: boolean;
  /** the ability the level was read from; null when there is none */
  theta: number | null;
  /** the evidence the reason cites: this lecture's answers, or the pooled ones when provisional */
  n_scored: number;
  n_right: number;
  n_not_sure: number;
  reason: string;
}

const count = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`;

function levelReason(
  level: Level, lectureTitle: string, basis: Estimate, provisional: boolean,
): string {
  const t = `“${lectureTitle}”`;
  if (provisional) {
    return `We have not asked about ${t} yet. From your ${count(basis.n_scored, "answer")} so far (${basis.n_right} right) and how hard this concept is, we start you at Level ${level}. We will check it before that lecture.`;
  }
  const notSure = basis.n_not_sure > 0 ? `, and ${basis.n_not_sure} “Not sure” counted as wrong` : "";
  const lead = `From your ${count(basis.n_scored, "answer")} on ${t} (${basis.n_right} right${notSure}), `;
  if (level === 1) return `${lead}you are not yet likely to handle this concept's applied questions, so videos start from the basics with more hints.`;
  if (level === 2) return `${lead}you are likely to handle this concept's applied questions but not yet its advanced ones, so we use medium pacing.`;
  return `${lead}you are likely to handle even this concept's advanced questions, so we skip the basics here.`;
}

/** The level of every KU, from the answers so far. Pure: the caller decides when a level is published (D11). */
export function kuLevels(input: ProfileInput): Record<string, KuLevelEstimate> {
  const { course, items } = input;
  const pooled = pooledEstimate(input);
  const titles = new Map(course.lectures.map((l) => [l.n, l.title]));
  const estimates = new Map(course.lectures.map((l) => [l.n, lectureEstimate(input, l.n)]));
  const out: Record<string, KuLevelEstimate> = {};

  for (const ku of course.kus) {
    const own = estimates.get(ku.lecture_n)!;
    const title = titles.get(ku.lecture_n) ?? `Lecture ${ku.lecture_n}`;
    const tiers = new Map(items.filter((i) => i.ku_id === ku.id && i.context === "assessment" && i.tier).map((i) => [i.tier!, i]));
    // on demand a KU's difficulties come with it, before any of its questions is written; one extracted without them
    // (before V4) takes them from its questions or the plain tier offsets, as the question picker does, since on demand
    // a KU rarely has both an applied and an advanced question
    const fallback = course.config.questions_on_demand || (tiers.get("applied") && tiers.get("advanced"));
    const betas = ku.tier_difficulty ?? (fallback ? tierDifficulty(ku, items) : null);
    const base = { ku_id: ku.id, lecture_n: ku.lecture_n };

    if (own.n_shown > 0 && own.n_not_sure === own.n_shown) {
      out[ku.id] = {
        ...base, level: 1, not_checked: false, provisional: false, theta: null, n_scored: 0, n_right: 0, n_not_sure: own.n_not_sure,
        reason: `You chose “Not sure” on ${own.n_not_sure === 2 ? "both" : `all ${own.n_not_sure}`} questions on “${title}”, so videos start from the basics with more hints.`,
      };
      continue;
    }
    const provisional = own.n_shown === 0;
    const basis = provisional ? pooled : own;
    if (basis.n_scored === 0) {
      out[ku.id] = {
        ...base, level: 1, not_checked: true, provisional: false, theta: null, n_scored: 0, n_right: 0, n_not_sure: 0,
        reason: `Not covered yet. We will check this when “${title}” comes up.`,
      };
      continue;
    }
    if (!betas) {
      out[ku.id] = {
        ...base, level: 1, not_checked: false, provisional, theta: basis.theta, n_scored: basis.n_scored, n_right: basis.n_right,
        n_not_sure: basis.n_not_sure, reason: "There are no questions for this concept yet, so videos start from the basics.",
      };
      continue;
    }
    const level = readinessLevel(basis.theta, betas.applied, betas.advanced, basis.n_scored);
    out[ku.id] = {
      ...base, level, not_checked: false, provisional, theta: basis.theta, n_scored: basis.n_scored, n_right: basis.n_right,
      n_not_sure: basis.n_not_sure, reason: levelReason(level, title, basis, provisional),
    };
  }
  return out;
}

/** What moved between the published levels and a fresh estimate (the "What changed and why" card, D11). */
export function levelUpdates(
  published: Record<string, Level>,
  next: Record<string, KuLevelEstimate>,
  kus: KuEntry[],
  lectureTitles: Map<number, string>,
): LevelUpdate[] {
  const out: LevelUpdate[] = [];
  for (const ku of kus) {
    const from = published[ku.id];
    const est = next[ku.id];
    if (from === undefined || !est || est.level === from || est.not_checked) continue;
    const t = lectureTitles.get(ku.lecture_n) ?? `Lecture ${ku.lecture_n}`;
    out.push({
      ku_id: ku.id,
      from,
      to: est.level,
      direction: est.level > from ? "up" : "down",
      reason: `${ku.short_title}: Level ${from} → ${est.level}. ${est.n_right} of ${est.n_scored} right on “${t}” so far. Your next videos on it will use Level ${est.level}.`,
    });
  }
  return out;
}
