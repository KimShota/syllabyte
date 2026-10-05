import { describe, expect, it } from "vitest";
import { buildEntries, displayOrder, servedLevel, upcomingLecture, whyOrder, type BuildInput } from "@/lib/logic/playlist";
import { course, level, resp, T0, video } from "./helpers";

const videos = [
  video("a", "t1", 1, 6), video("b", "t2", 1, 10), video("c", "t3", 2, 18), video("d", "t4", 3, 25),
];
const base = (over: Partial<BuildInput> = {}): BuildInput => ({
  course, videos, items: [], levels: { t1: level("t1", 3), t2: level("t2", 2), t3: level("t3", 2), t4: level("t4", 2) },
  responses: [], watched: {}, review: {}, prev: [], known: [], added: [], week: 1, ...over,
});
const tags = (es: { video_id: string; tag: string }[]) => es.map((e) => `${e.video_id}:${e.tag}`);

describe("buildEntries (plan §4.3)", () => {
  it("tags unwatched Level-1 topics as gaps and upcoming-lecture videos as new", () => {
    const es = buildEntries(base({ levels: { ...base().levels, t3: level("t3", 1) } }));
    expect(tags(es)).toEqual(["c:gap", "d:new"]);
  });
  it("orders gaps with the upcoming lecture first, then by earlier slides", () => {
    const lv = { t1: level("t1", 1), t2: level("t2", 1), t3: level("t3", 1), t4: level("t4", 1) };
    expect(buildEntries(base({ levels: lv })).map((e) => e.video_id)).toEqual(["d", "a", "b", "c"]);
  });
  it("holds refreshers back until every gap/new video is watched (first pass first)", () => {
    const watchedA = { a: { first_at: T0, last_at: T0, views: 1 } };
    const missed = [resp("cp-a", "t1", "checkpoint", 0, { video_id: "a" })];
    const early = buildEntries(base({ watched: watchedA, responses: missed }));
    expect(tags(early)).toEqual(["d:new"]);
    const done = { ...watchedA, d: { first_at: T0, last_at: T0, views: 1 } };
    expect(tags(buildEntries(base({ watched: done, responses: missed })))).toEqual(["a:refresher"]);
  });
  it("caps at 6 videos / 600 s", () => {
    const many = Array.from({ length: 9 }, (_, i) => video(`x${i}`, "t4", 3, 25 + i));
    expect(buildEntries(base({ videos: many })).length).toBe(6);
    const long = Array.from({ length: 4 }, (_, i) => video(`y${i}`, "t4", 3, 25 + i, { duration_s: 250 }));
    expect(buildEntries(base({ videos: long })).length).toBe(2);
  });
  it("keeps skipped entries in their own group and out of the cap", () => {
    const prev = [{ id: "pl-d", video_id: "d", tag: "new" as const, state: "skipped" as const, skip_reason: "no_time", pos: 0 }];
    const es = buildEntries(base({ prev }));
    expect(es.find((e) => e.video_id === "d")?.state).toBe("skipped");
  });
  it("leaves out hidden videos and videos skipped as known after a passed prove-it", () => {
    expect(buildEntries(base({ review: { d: "hidden" } })).map((e) => e.video_id)).not.toContain("d");
    expect(buildEntries(base({ known: ["d"] })).map((e) => e.video_id)).not.toContain("d");
  });
  it("appends videos the student added from the Course map, beyond the cap", () => {
    const es = buildEntries(base({ added: ["a"] }));
    expect(tags(es)).toEqual(["d:new", "a:you_added"]);
  });
  it("keeps a student-added video's own tag if it is already in the playlist", () => {
    expect(tags(buildEntries(base({ added: ["d"] })))).toEqual(["d:new"]);
  });
});

describe("displayOrder", () => {
  it("honours a manual order and keeps skipped entries separate", () => {
    const entries = buildEntries(base({ levels: { ...base().levels, t3: level("t3", 1) } }));
    const state = { entries, manual_order: ["pl-d", "pl-c"], built_at_week: 1 };
    expect(displayOrder(state).active.map((e) => e.video_id)).toEqual(["d", "c"]);
    expect(displayOrder({ ...state, manual_order: null }).active.map((e) => e.video_id)).toEqual(["c", "d"]);
  });
});

describe("whyOrder", () => {
  const topicTitle = (id: string) => ({ t3: "Selection bias", t1: "Causal questions" }[id] ?? id);
  it("names the gap topics and the order", () => {
    const entries = buildEntries(base({ levels: { ...base().levels, t3: level("t3", 1) } }));
    expect(whyOrder({ upcoming: 3, manual: false, entries, videos, topicTitle })).toBe(
      "Lecture 3 is next, and your levels show Selection bias as a gap. We put those first, then new videos from Lecture 3.",
    );
  });
  it("says it is the student's order after a manual reorder", () => {
    expect(whyOrder({ upcoming: 3, manual: true, entries: [], videos, topicTitle })).toMatch(/^You set this order/);
  });
});

describe("upcomingLecture / servedLevel", () => {
  it("uses the Phase 0 override, else the next lecture by week", () => {
    expect(upcomingLecture(course, 1)).toBe(3);
    const c = { ...course, config: { ...course.config, upcoming_lecture_override: null } };
    expect(upcomingLecture(c, 2)).toBe(2);
    expect(upcomingLecture(c, 9)).toBe(3);
  });
  it("falls back toward more support when a level's file is missing (plan Q31)", () => {
    expect(servedLevel(2, [2])).toEqual({ level: 2, note: null });
    expect(servedLevel(3, [2])).toEqual({ level: 2, note: "Level 2 version · Level 3 coming soon" });
    expect(servedLevel(3, [1, 2]).level).toBe(2);
    expect(servedLevel(2, [1, 3]).level).toBe(1);
    expect(servedLevel(1, [2]).level).toBe(2);
  });
});
