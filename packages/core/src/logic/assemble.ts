import type { BloomLevel, Course, CourseConfig, Fixtures, Item, ItemTier, KuEntry, QuestionNeed, SlideRef } from "../types";

/**
 * A course uploaded by students, assembled from what the server stores (plan/slide-uploads-plan.md): the lectures
 * (one per confirmed deck, in teaching order, V1-V3), each processed deck's KUs, the questions written for them so
 * far (V4), and the prerequisite links added later (U7). Videos are made per student and registered later, so a fresh
 * course has none.
 */

/** The defaults in syllabyte_common/learner.py's CourseConfig. */
export const DEFAULT_COURSE_CONFIG: CourseConfig = {
  playlist_max_videos: 6,
  playlist_max_seconds: 600,
  next_session_min_hours: 12,
  next_session_max_per_visit: 2,
  next_session_expiry_days: 7,
  retention_due_days: 3,
  retention_delay_days: 14,
  reveal_retention_scores_after_week_14: false,
  cat_start_theta: 0,
  cat_items_per_topic: 4,
  cat_week0_length: 16,
  cat_week0_lectures: 4,
  cat_prelecture_new: 4,
  cat_prelecture_review: 2,
  irt_hint_beta_shift: 1,
  refresher_dropoff_fraction: 0.6,
  refresher_replay_count: 3,
  upcoming_lecture_override: null,
};

/** What uploaded courses change (V4-V6): questions on demand, up to 10 per lecture check, no baseline. */
export const UPLOADED_COURSE_CONFIG: Partial<CourseConfig> = {
  questions_on_demand: true,
  cat_prelecture_new: 10,
  cat_week0_lectures: 0,
};

/** A KU as the deck job returns it (the extraction's KnowledgeUnit plus a short title). */
export interface DeckKu {
  id: string;
  title: string;
  short_title: string;
  summary: string;
  bloom_level: BloomLevel;
  /** KU ids of this deck or of earlier lectures */
  prerequisites: string[];
  source_refs: SlideRef[];
  /** question difficulty per tier (V4); absent on KUs processed with a full bank */
  tier_difficulty?: Record<ItemTier, number>;
}

/** What processing one deck produces: its KUs, and (before V4) their adaptive-assessment items. */
export interface DeckResult {
  kus: DeckKu[];
  /** context "assessment"; topic_id is set here from the deck's lecture */
  items: Item[];
}

export interface CourseInput {
  id: string;
  code: string;
  name: string;
  syllabus_summary?: string;
  config?: Partial<CourseConfig>;
  /** `position`: the teaching order (any increasing numbers); absent = `n` */
  lectures: { n: number; title: string; position?: number }[];
  /** processed decks only, each with the lecture it is placed in */
  decks: { lecture_n: number; result: DeckResult }[];
  /** questions written on demand (V4), each on a KU of the course */
  questions?: Item[];
  /** questions the worker could not write */
  question_failures?: QuestionNeed[];
  /** prerequisite links added after a deck was processed: ku -> the KU it builds on */
  links?: { ku_id: string; prereq_id: string }[];
}

export const topicId = (n: number) => `lecture-${n}`;

export function assembleCourse(input: CourseInput): Fixtures {
  const pos = (l: { n: number; position?: number }) => l.position ?? l.n;
  const lectures = [...input.lectures].sort((a, b) => pos(a) - pos(b) || a.n - b.n);
  const rank = new Map(lectures.map((l, i) => [l.n, i + 1]));
  const decks = input.decks.filter((d) => rank.has(d.lecture_n)).sort((a, b) => rank.get(a.lecture_n)! - rank.get(b.lecture_n)!);

  const added = new Map<string, string[]>();
  for (const l of input.links ?? []) added.set(l.ku_id, [...(added.get(l.ku_id) ?? []), l.prereq_id]);

  const kus: KuEntry[] = [];
  const items: Item[] = [];
  for (const d of decks) {
    for (const k of d.result.kus) {
      kus.push({
        id: k.id,
        title: k.title,
        short_title: k.short_title,
        topic_id: topicId(d.lecture_n),
        lecture_n: d.lecture_n,
        video_id: null,
        bloom_level: k.bloom_level,
        prerequisites: [...new Set([...k.prerequisites, ...(added.get(k.id) ?? [])])],
        ...(k.tier_difficulty ? { tier_difficulty: k.tier_difficulty } : {}),
      });
    }
    for (const i of d.result.items) items.push({ ...i, topic_id: topicId(d.lecture_n) });
  }
  const lectureOf = new Map(kus.map((k) => [k.id, k.lecture_n]));
  for (const q of input.questions ?? []) {
    const n = q.ku_id === null ? undefined : lectureOf.get(q.ku_id);
    if (n !== undefined) items.push({ ...q, topic_id: topicId(n) });
  }
  // a link to a KU that is not in the course (e.g. its deck was moved out by the researcher) is dropped
  const ids = new Set(kus.map((k) => k.id));
  for (const k of kus) k.prerequisites = k.prerequisites.filter((p) => ids.has(p) && p !== k.id);

  const course: Course = {
    id: input.id,
    code: input.code,
    name: input.name,
    eyebrow: (input.code || input.name).toUpperCase(),
    syllabus_summary: input.syllabus_summary ?? "",
    config: { ...DEFAULT_COURSE_CONFIG, ...UPLOADED_COURSE_CONFIG, ...input.config },
    topics: lectures.map((l) => ({
      id: topicId(l.n),
      title: l.title,
      ku_ids: kus.filter((k) => k.lecture_n === l.n).map((k) => k.id),
      first_lecture: l.n,
    })),
    // a lecture is a deck now, not a slide range of one deck; the range is kept for the demo's screens. Its week is
    // its place in the order: a lecture placed before others moves them a week later
    lectures: lectures.map((l) => ({ n: l.n, position: rank.get(l.n)!, title: l.title, week: rank.get(l.n)!, slide_start: 0, slide_end: 0 })),
    kus,
  };
  return { course, items, videos: [], slides: {}, ...(input.question_failures?.length ? { question_failures: input.question_failures } : {}) };
}
