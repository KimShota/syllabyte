import type { Course, Item, ResponseRecord } from "../types";
import { selectNext, standardError } from "./cat";
import { answersFor, bankItems, evidenceItems, lectureEstimate, toBankItem } from "./kuProfile";

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
  const ordered = [...course.lectures].sort((a, b) => a.n - b.n);
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
  const hasEarlier = course.lectures.some((l) => l.n < lectureN);
  const review = hasEarlier ? cfg.cat_prelecture_review : 0;
  const total = cfg.cat_prelecture_new + review;
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

export interface NextItem {
  item: Item;
  lecture_n: number;
  role: Slot["role"];
  /** 0-based position in the sitting */
  index: number;
  total: number;
}

interface Ctx {
  course: Course;
  items: Item[];
  /** every response the student has given, in any sitting or video */
  responses: ResponseRecord[];
}

/** The most informative unseen item of one lecture at its current theta, or null if it has none left. */
function pickFrom(ctx: Ctx, lectureN: number, seen: Set<string>): Item | null {
  const bank = bankItems(ctx.course, ctx.items, lectureN);
  const theta = lectureEstimate(ctx, lectureN).theta;
  const pick = selectNext(bank.map(toBankItem), seen, theta);
  return pick ? (bank.find((b) => b.id === pick.id) ?? null) : null;
}

/** Of the earlier lectures that still have unseen items, the one whose theta is least certain (ties: the earlier). */
function leastCertainEarlier(ctx: Ctx, before: number, seen: Set<string>): number | null {
  let best: { n: number; se: number } | null = null;
  for (const l of [...ctx.course.lectures].sort((a, b) => a.n - b.n)) {
    if (l.n >= before) continue;
    if (!bankItems(ctx.course, ctx.items, l.n).some((i) => !seen.has(i.id))) continue;
    const pool = evidenceItems(ctx.course, ctx.items, l.n).map(toBankItem);
    const answers = answersFor(pool, ctx.responses);
    const est = lectureEstimate(ctx, l.n);
    const se = answers.some((a) => a.outcome !== "not_sure") ? standardError(pool, answers, est.theta, ctx.course.config.irt_hint_beta_shift) : Infinity;
    if (best === null || se > best.se) best = { n: l.n, se };
  }
  return best ? best.n : null;
}

/**
 * The item to ask at position `answered` of `plan`, or null when the sitting is over (or nothing is left to ask).
 * A pure function of the answers so far, so asking twice without an answer in between gives the same item.
 */
export function nextAssessmentItem(plan: AssessmentPlan, answered: number, ctx: Ctx): NextItem | null {
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
    const item = pickFrom(ctx, n, seen);
    if (item) return { item, lecture_n: n, role: slot.role, index: answered, total };
  }
  // a review slot with no earlier lecture left becomes one more item on the lecture itself
  if (slot.role === "review" && plan.lecture_n !== null) {
    const item = pickFrom(ctx, plan.lecture_n, seen);
    if (item) return { item, lecture_n: plan.lecture_n, role: "new", index: answered, total };
  }
  return null;
}
