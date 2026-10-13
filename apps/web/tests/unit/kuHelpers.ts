import type { Course, Item, ItemTier, KuEntry, ResponseRecord } from "@/lib/types";
import { course as baseCourse, item, resp } from "./helpers";

/**
 * A small course for the per-KU profiling tests: 3 lectures, 5 KUs with a prerequisite graph,
 * and a 3-tier bank per KU.
 *
 *   lecture 1: ku-a (root)            ku-b (needs a)
 *   lecture 2: ku-c (needs b)         ku-d (root)
 *   lecture 3: ku-e (needs c and d)
 *
 * A KU's three items sit one logit apart around its base difficulty, like the generated bank
 * (basic = base - 1, applied = base, advanced = base + 1).
 */
const BASE: Record<string, number> = { "ku-a": -1, "ku-b": -0.5, "ku-c": 0, "ku-d": 0.5, "ku-e": 1 };
const SPEC: [string, number, string[]][] = [
  ["ku-a", 1, []], ["ku-b", 1, ["ku-a"]], ["ku-c", 2, ["ku-b"]], ["ku-d", 2, []], ["ku-e", 3, ["ku-c", "ku-d"]],
];

export const TIERS: ItemTier[] = ["basic", "applied", "advanced"];
const OFFSET: Record<ItemTier, number> = { basic: -1, applied: 0, advanced: 1 };

export const kus: KuEntry[] = SPEC.map(([id, lecture_n, prerequisites]) => ({
  id, title: `Title of ${id}`, short_title: `Short ${id}`, topic_id: `lecture-${lecture_n}`, lecture_n, video_id: null,
  bloom_level: "understand", prerequisites,
}));

export const bank: Item[] = SPEC.flatMap(([ku, lecture_n]) =>
  TIERS.map((tier) =>
    item(`as-${ku}-${tier}`, `lecture-${lecture_n}`, "assessment", { ku_id: ku, tier, difficulty_prior: BASE[ku] + OFFSET[tier] }),
  ),
);

/** In-video items for ku-a, as the fixtures have them (difficulty from the LLM, no tier). */
export const videoItems: Item[] = [
  item("cp-ku-a", "lecture-1", "checkpoint", { ku_id: "ku-a", difficulty_prior: -0.5 }),
  item("ns-ku-a", "lecture-1", "next_session", { ku_id: "ku-a", difficulty_prior: 0 }),
  item("pi-ku-a", "lecture-1", "prove_it", { ku_id: "ku-a", difficulty_prior: 0.5 }),
];

export const items: Item[] = [...bank, ...videoItems];

export const course: Course = {
  ...baseCourse,
  lectures: [
    { n: 1, title: "Lecture One", week: 1, slide_start: 1, slide_end: 10 },
    { n: 2, title: "Lecture Two", week: 2, slide_start: 11, slide_end: 20 },
    { n: 3, title: "Lecture Three", week: 3, slide_start: 21, slide_end: 30 },
  ],
  kus,
};

/** `item()` keys choice 1 as the right answer. */
export const RIGHT = 1;
export const WRONG = 0;

export function answer(
  itemId: string, how: "right" | "wrong" | "not_sure", extra: Partial<ResponseRecord> = {},
): ResponseRecord {
  const it = items.find((i) => i.id === itemId)!;
  return resp(itemId, it.topic_id, it.context, how === "right" ? RIGHT : how === "wrong" ? WRONG : "not_sure", extra);
}

export const lectureOfItem = (id: string): number => kus.find((k) => k.id === items.find((i) => i.id === id)!.ku_id)!.lecture_n;
