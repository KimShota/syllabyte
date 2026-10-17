import bank from "../fixtures/bank.json";
import course from "../fixtures/course.json";
import items from "../fixtures/items.json";
import slides from "../fixtures/slides.json";
import videos from "../fixtures/videos.json";
import type { Course, Fixtures, Item, Lecture, Topic, Video } from "./types";

/**
 * Phase 0 fixtures: course, videos and their items from scripts/build_ui_fixtures.py, plus the per-KU
 * adaptive-assessment bank from scripts/build_item_bank.py. They derive from the course's own slides, so
 * they are gitignored; see apps/web/scripts/check-fixtures.mjs.
 */
export const FIX: Fixtures = {
  course: course as unknown as Course,
  items: [...(items as unknown as Item[]), ...(bank as unknown as Item[])],
  videos: videos as unknown as Video[],
  slides: slides as Record<string, string>,
};

const itemMap = new Map(FIX.items.map((i) => [i.id, i]));
const videoMap = new Map(FIX.videos.map((v) => [v.id, v]));

export function itemById(id: string): Item {
  const it = itemMap.get(id);
  if (!it) throw new Error(`unknown item ${id}`);
  return it;
}
export function videoById(id: string): Video {
  const v = videoMap.get(id);
  if (!v) throw new Error(`unknown video ${id}`);
  return v;
}
export function topicById(id: string): Topic {
  const t = FIX.course.topics.find((x) => x.id === id);
  if (!t) throw new Error(`unknown topic ${id}`);
  return t;
}
export function lectureByN(n: number): Lecture {
  const l = FIX.course.lectures.find((x) => x.n === n);
  if (!l) throw new Error(`unknown lecture ${n}`);
  return l;
}
export function slideUrl(n: number): string {
  return `/fixtures/slides/slide-${String(n).padStart(3, "0")}.png`;
}
export function slideText(n: number): string {
  return (FIX.slides[String(n)] ?? "").trim();
}
/** Items for one context, in a stable order. */
export function itemsFor(context: Item["context"]): Item[] {
  return FIX.items.filter((i) => i.context === context).sort((a, b) => a.id.localeCompare(b.id));
}
