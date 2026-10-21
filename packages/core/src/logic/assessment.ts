import type { Course, Item, ItemTier, KuEntry, QuestionNeed, ResponseRecord } from "../types";
import { information, selectNext, standardError, TIE_TOLERANCE } from "./cat";
import { answersFor, bankItems, EVIDENCE_CONTEXTS, evidenceItems, lectureEstimate, tierDifficulty, toBankItem } from "./kuProfile";
import { lecturesInOrder, taughtBefore } from "./lectures";

/**
 * The two adaptive sittings (plan/per-ku-profiling-plan.md D7-D9):
 *
 *   week0    a fixed-length baseline before any video: the first `cat_week0_lectures` lectures, `cat_items_per_topic`
 *            items each, interleaved lecture by lecture. It gives every KU a provisional level.
 *   lecture  the check before a lecture's videos: `cat_prelecture_new` items on that lecture, plus
 *            `cat_prelecture_review` items from earlier lectures, aimed where theta is least certain.
 *
 * A sitting has a fixed length whatever the size of the course. Each item is chosen when it is asked, from the
 * answers before it (one CAT per lecture, the most informative unseen item). Items already answered, in any
 * sitting, are never asked again. There is no going back (D9), so a sitting is just its length and the number of
 * answers given so far.
 *
 * With questions written on demand (uploaded courses, plan/slide-uploads-plan.md V4-V6) there is no baseline, a
 * pre-lecture check asks up to `cat_prelecture_new` questions but no more than the lecture has KUs, and each question
 * is chosen as a KU and a tier: the lecture's KU the student has answered least (ties: the one most later KUs build
 * on, then course order) at the tier most informative at the lecture's theta. A saved question the student has not
 * seen is asked; without one the sitting names the (KU, tier) it needs and waits for it to be written.
 */

export type AssessmentKind = "week0" | "lecture";

export interface Slot {
  role: "new" | "review";
  /** the lecture asked about; null for a review slot, chosen when the slot comes up */
  lecture_n: number | null;
}

export interface AssessmentPlan {
  kind: AssessmentKind;
  /** the lecture a pre-lecture check is for; null for the baseline */
  lecture_n: number | null;
  slots: Slot[];
}

/**
 * The lectures the baseline covers: the first `cat_week0_lectures` lectures that have bank items. With uploaded
 * slides (plan/slide-uploads-plan.md U9) that is whichever of the first lectures have been processed; without
 * `items`, the first lectures of the list.
 */
export function week0Lectures(course: Course, items?: Item[]): number[] {
  const ordered = lecturesInOrder(course);
  const withItems = items ? ordered.filter((l) => bankItems(course, items, l.n).length > 0) : ordered;
  return withItems.slice(0, course.config.cat_week0_lectures).map((l) => l.n);
}

/**
 * The baseline. `lectures`: the ones it covers, fixed when the student starts it, so slides added mid-sitting do
 * not move its questions; by default `week0Lectures`. It is shorter when those lectures have fewer bank items than
 * it would ask, and empty when there are none yet.
 */
export function week0Plan(course: Course, items?: Item[], lectures?: number[]): AssessmentPlan {
  const cfg = course.config;
  const covered = lectures ?? week0Lectures(course, items);
  const available = items ? covered.reduce((sum, n) => sum + bankItems(course, items, n).length, 0) : Infinity;
  const total = Math.min(cfg.cat_week0_length, covered.length * cfg.cat_items_per_topic, available);
  const slots: Slot[] = [];
  for (let k = 0; k < total; k++) slots.push({ role: "new", lecture_n: covered[k % covered.length] });
  return { kind: "week0", lecture_n: null, slots };
}

export function prelecturePlan(course: Course, lectureN: number): AssessmentPlan {
  const cfg = course.config;
  const newCount = cfg.questions_on_demand
    ? Math.min(cfg.cat_prelecture_new, course.kus.filter((k) => k.lecture_n === lectureN).length)
    : cfg.cat_prelecture_new;
  if (newCount === 0) return { kind: "lecture", lecture_n: lectureN, slots: [] };
  const hasEarlier = course.lectures.some((l) => taughtBefore(course, l.n, lectureN));
  const review = hasEarlier ? cfg.cat_prelecture_review : 0;
  const total = newCount + review;
  // a review item after every `every` slots, so the sitting reads new, new, review, new, new, review
  const every = review > 0 ? Math.floor(total / review) : Infinity;
  const slots: Slot[] = [];
  let reviewed = 0;
  for (let i = 0; i < total; i++) {
    if (reviewed < review && (i + 1) % every === 0) {
      slots.push({ role: "review", lecture_n: null });
      reviewed += 1;
    } else slots.push({ role: "new", lecture_n: lectureN });
  }
  return { kind: "lecture", lecture_n: lectureN, slots };
}

interface Position {
  lecture_n: number;
  role: Slot["role"];
  /** 0-based position in the sitting */
  index: number;
  total: number;
}

export interface NextItem extends Position {
  item: Item;
}

/** The question at a position of a sitting: a saved `item`, or the `need` it waits for while it is written (V4). */
export type NextStep = Position & Ask;

export interface Ctx {
  course: Course;
  items: Item[];
  /** every response the student has given, in any sitting or video */
  responses: ResponseRecord[];
}

type Ask = { item: Item; need: null } | { item: null; need: QuestionNeed };

/** The most informative unseen item of one lecture at its current theta, or null if it has none left. */
function pickFrom(ctx: Ctx, lectureN: number, seen: Set<string>): Ask | null {
  if (ctx.course.config.questions_on_demand) return pickOnDemand(ctx, lectureN, seen);
  const bank = bankItems(ctx.course, ctx.items, lectureN);
  const theta = lectureEstimate(ctx, lectureN).theta;
  const pick = selectNext(bank.map(toBankItem), seen, theta);
  const item = pick ? bank.find((b) => b.id === pick.id) : undefined;
  return item ? { item, need: null } : null;
}

const TIERS: readonly ItemTier[] = ["basic", "applied", "advanced"];

/** How many KUs build on each KU, directly or through others. */
export function dependentCounts(kus: readonly KuEntry[]): Map<string, number> {
  const children = new Map<string, string[]>();
  for (const k of kus) for (const p of k.prerequisites) children.set(p, [...(children.get(p) ?? []), k.id]);
  const out = new Map<string, number>();
  for (const k of kus) {
    const seen = new Set<string>();
    const stack = [...(children.get(k.id) ?? [])];
    while (stack.length) {
      const c = stack.pop()!;
      if (seen.has(c)) continue;
      seen.add(c);
      stack.push(...(children.get(c) ?? []));
    }
    out.set(k.id, seen.size);
  }
  return out;
}

/**
 * The highest tier to ask on a lecture right after a "Not sure" on it: one below the tier of that question (basic stays
 * basic). "Not sure" counts as wrong, which lowers the estimate too; this makes sure the very next question is easier,
 * where a real answer is likelier.
 * Null when the lecture's latest answer was right or wrong.
 */
function notSureCap(ctx: Ctx, lectureN: number): ItemTier | null {
  const lectureOf = new Map(ctx.course.kus.map((k) => [k.id, k.lecture_n]));
  const asked = new Map(
    ctx.items.filter((i) => i.context === "assessment" && i.tier && i.ku_id !== null && lectureOf.get(i.ku_id) === lectureN).map((i) => [i.id, i]),
  );
  let last: ResponseRecord | null = null;
  for (const r of ctx.responses) if (asked.has(r.item_id) && (!last || r.at >= last.at)) last = r;
  if (!last || last.choice !== "not_sure") return null;
  return TIERS[Math.max(0, TIERS.indexOf(asked.get(last.item_id)!.tier!) - 1)];
}

/** The KU and tier to ask next on one lecture (V5), and a saved question for it the student has not seen, if any. */
function pickOnDemand(ctx: Ctx, lectureN: number, seen: Set<string>): Ask | null {
  const kus = ctx.course.kus.filter((k) => k.lecture_n === lectureN);
  if (!kus.length) return null;
  const answered = new Map<string, number>();
  for (const it of ctx.items) {
    if (it.ku_id === null || !EVIDENCE_CONTEXTS.includes(it.context) || !seen.has(it.id)) continue;
    answered.set(it.ku_id, (answered.get(it.ku_id) ?? 0) + 1);
  }
  const deps = dependentCounts(ctx.course.kus);
  let ku = kus[0];
  for (const k of kus.slice(1)) {
    const da = answered.get(k.id) ?? 0;
    const db = answered.get(ku.id) ?? 0;
    if (da < db || (da === db && (deps.get(k.id) ?? 0) > (deps.get(ku.id) ?? 0))) ku = k;
  }
  const theta = lectureEstimate(ctx, lectureN).theta;
  const betas = tierDifficulty(ku, ctx.items);
  let tier: ItemTier = TIERS[0];
  for (const t of TIERS.slice(1)) {
    if (information(theta, 1, betas[t]) > information(theta, 1, betas[tier]) + TIE_TOLERANCE) tier = t;
  }
  const cap = notSureCap(ctx, lectureN);
  if (cap && TIERS.indexOf(tier) > TIERS.indexOf(cap)) tier = cap;
  const item = ctx.items.find((i) => i.context === "assessment" && i.ku_id === ku.id && i.tier === tier && !seen.has(i.id));
  return item ? { item, need: null } : { item: null, need: { ku_id: ku.id, tier } };
}

/** An earlier lecture can still be asked about: it has unseen bank items, or (on demand) any KU. */
function askable(ctx: Ctx, lectureN: number, seen: Set<string>): boolean {
  if (ctx.course.config.questions_on_demand) return ctx.course.kus.some((k) => k.lecture_n === lectureN);
  return bankItems(ctx.course, ctx.items, lectureN).some((i) => !seen.has(i.id));
}

/** Of the earlier lectures that still have unseen items, the one whose theta is least certain (ties: the earlier). */
function leastCertainEarlier(ctx: Ctx, before: number, seen: Set<string>): number | null {
  let best: { n: number; se: number } | null = null;
  for (const l of lecturesInOrder(ctx.course)) {
    if (!taughtBefore(ctx.course, l.n, before)) continue;
    if (!askable(ctx, l.n, seen)) continue;
    const pool = evidenceItems(ctx.course, ctx.items, l.n).map(toBankItem);
    const answers = answersFor(pool, ctx.responses);
    const est = lectureEstimate(ctx, l.n);
    const se = answers.length ? standardError(pool, answers, est.theta, ctx.course.config.irt_hint_beta_shift) : Infinity;
    if (best === null || se > best.se) best = { n: l.n, se };
  }
  return best ? best.n : null;
}

/** The item to ask at position `answered` of a sitting on a complete bank; see `nextAssessmentStep`. */
export function nextAssessmentItem(plan: AssessmentPlan, answered: number, ctx: Ctx): NextItem | null {
  const step = nextAssessmentStep(plan, answered, ctx);
  return step?.item ? { ...step, item: step.item } : null;
}

/**
 * What to ask at position `answered` of `plan`, or null when the sitting is over (or nothing is left to ask).
 * A pure function of the answers so far, so asking twice without an answer in between gives the same item.
 */
export function nextAssessmentStep(plan: AssessmentPlan, answered: number, ctx: Ctx): NextStep | null {
  if (answered >= plan.slots.length) return null;
  const slot = plan.slots[answered];
  const seen = new Set(ctx.responses.map((r) => r.item_id));
  const total = plan.slots.length;

  let lectureN = slot.lecture_n;
  if (slot.role === "review") {
    lectureN = plan.lecture_n === null ? null : leastCertainEarlier(ctx, plan.lecture_n, seen);
  }
  // a lecture can run out of unseen items; fall back to the next lecture of the sitting rather than stop early
  const order = lectureN === null ? [] : [lectureN, ...ctx.course.lectures.map((l) => l.n).filter((n) => n !== lectureN)];
  for (const n of order) {
    if (slot.role === "new" && plan.kind === "lecture" && n !== plan.lecture_n) continue;
    const pick = pickFrom(ctx, n, seen);
    if (pick) return { ...pick, lecture_n: n, role: slot.role, index: answered, total };
  }
  // a review slot with no earlier lecture left becomes one more item on the lecture itself
  if (slot.role === "review" && plan.lecture_n !== null) {
    const pick = pickFrom(ctx, plan.lecture_n, seen);
    if (pick) return { ...pick, lecture_n: plan.lecture_n, role: "new", index: answered, total };
  }
  return null;
}

/**
 * The question to write now for a sitting at position `answered`: the one it waits for, and only that one. The next
 * question depends on this answer, and most pre-checks are answered wrong or "not sure", so writing ahead for a guessed
 * answer mostly wrote questions nobody was asked. A student waits for each question that is not saved yet.
 */
export function questionNeeds(plan: AssessmentPlan, answered: number, ctx: Ctx): QuestionNeed[] {
  const cur = nextAssessmentStep(plan, answered, ctx);
  return cur?.need ? [cur.need] : [];
}
