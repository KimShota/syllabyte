import { describe, expect, it } from "vitest";
import { buildEntries, displayOrder, servedLevel, upcomingLecture, whyOrder, type BuildInput } from "../src/logic/playlist";
import { course, level, resp, T0, video } from "./helpers";
import type { KuEntry } from "../src/types";

// four videos, one KU each: a, b (lecture 1), c (lecture 2), d (lecture 3); levels are per KU
const videos = [
  video("a", "lecture-1", 1, 6), video("b", "lecture-1", 1, 10), video("c", "lecture-2", 2, 18), video("d", "lecture-3", 3, 25),
];
const ku = (id: string, lecture_n: number, prerequisites: string[] = []): KuEntry => ({
  id, title: `Title ${id}`, short_title: `Short ${id}`, topic_id: `lecture-${lecture_n}`, lecture_n, video_id: id, bloom_level: "understand", prerequisites,
});
const kus = [ku("a", 1), ku("b", 1, ["a"]), ku("c", 2, ["b"]), ku("d", 3)];
const base = (over: Partial<BuildInput> = {}): BuildInput => ({
  course: { ...course, kus }, videos, items: [], levels: { a: level("a", 3), b: level("b", 2), c: level("c", 2), d: level("d", 2) },
  responses: [], watched: {}, progress: {}, review: {}, prev: [], known: [], added: [], week: 1, now: T0, ...over,
});
const tags = (es: { video_id: string; tag: string }[]) => es.map((e) => `${e.video_id}:${e.tag}`);

describe("buildEntries (plan §4.3)", () => {
  it("tags unwatched Level-1 KUs as gaps and upcoming-lecture videos as new", () => {
    const es = buildEntries(base({ levels: { ...base().levels, c: level("c", 1) } }));
    expect(tags(es)).toEqual(["c:gap", "d:new"]);
  });
  it("orders gaps with the upcoming lecture first, then by earlier slides", () => {
    const lv = { a: level("a", 1), b: level("b", 1), c: level("c", 1), d: level("d", 1) };
    expect(buildEntries(base({ levels: lv })).map((e) => e.video_id)).toEqual(["d", "a", "b", "c"]);
  });
  it("holds refreshers back until every gap/new video is watched (first pass first)", () => {
    const watchedA = { a: { first_at: T0, last_at: T0, views: 1 } };
    const missed = [resp("cp-a", "lecture-1", "checkpoint", 0, { video_id: "a" })];
    const early = buildEntries(base({ watched: watchedA, responses: missed }));
    expect(tags(early)).toEqual(["d:new"]);
    const done = { ...watchedA, d: { first_at: T0, last_at: T0, views: 1 } };
    expect(tags(buildEntries(base({ watched: done, responses: missed })))).toEqual(["a:refresher"]);
  });
  it("caps at 6 videos / 600 s", () => {
    const many = Array.from({ length: 9 }, (_, i) => video(`x${i}`, "lecture-3", 3, 25 + i));
    expect(buildEntries(base({ videos: many, course: { ...course, kus: [] } })).length).toBe(6);
    const long = Array.from({ length: 4 }, (_, i) => video(`y${i}`, "lecture-3", 3, 25 + i, { duration_s: 250 }));
    expect(buildEntries(base({ videos: long, course: { ...course, kus: [] } })).length).toBe(2);
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
    const entries = buildEntries(base({ levels: { ...base().levels, c: level("c", 1) } }));
    const state = { entries, manual_order: ["pl-d", "pl-c"], built_at_week: 1 };
    expect(displayOrder(state).active.map((e) => e.video_id)).toEqual(["d", "c"]);
    expect(displayOrder({ ...state, manual_order: null }).active.map((e) => e.video_id)).toEqual(["c", "d"]);
  });
});

describe("per-KU rules (plan D13, D14)", () => {
  it("puts a prerequisite before the KU that builds on it, even when the slides say otherwise", () => {
    // b builds on a, but b comes first by slide order here
    const swapped = [video("a", "lecture-1", 1, 12), video("b", "lecture-1", 1, 6)];
    const lv = { a: level("a", 1), b: level("b", 1), c: level("c", 2), d: level("d", 2) };
    expect(buildEntries(base({ videos: swapped, levels: lv })).map((e) => e.video_id)).toEqual(["a", "b"]);
  });

  it("queues a video watched several times as a refresher, once the first pass is done", () => {
    const w = (views: number) => ({ a: { first_at: T0, last_at: T0, views }, d: { first_at: T0, last_at: T0, views: 1 } });
    expect(tags(buildEntries(base({ watched: w(2) })))).toEqual([]);
    expect(tags(buildEntries(base({ watched: w(3) })))).toEqual(["a:refresher"]);
  });

  it("sends a video stopped early back to the top, ahead of everything else", () => {
    const lv = { ...base().levels, c: level("c", 1) };
    const stopped = { b: { max_t: 20, duration_s: 100, last_at: T0 - 2 * 60 * 60 * 1000 } };
    const es = buildEntries(base({ levels: lv, progress: stopped }));
    expect(es.map((e) => e.video_id)[0]).toBe("b"); // b is from an earlier lecture and level 2: it is only here because it was left
    expect(tags(es)).toContain("b:new");
  });

  it("does not count a video as stopped early while the student may only be paused", () => {
    const paused = { b: { max_t: 20, duration_s: 100, last_at: T0 - 60 * 1000 } };
    expect(buildEntries(base({ progress: paused })).map((e) => e.video_id)).not.toContain("b");
  });

  it("serves a Level 1 KU as a gap whatever its lecture's other KUs are", () => {
    const lv = { ...base().levels, a: level("a", 1), b: level("b", 3) };
    expect(tags(buildEntries(base({ levels: lv })))).toEqual(["a:gap", "d:new"]);
  });
});

describe("whyOrder", () => {
  const kuList = kus;
  it("names the gap KUs and the order", () => {
    const entries = buildEntries(base({ levels: { ...base().levels, c: level("c", 1) } }));
    expect(whyOrder({ upcoming: 3, manual: false, entries, videos, kus: kuList })).toBe(
      "Lecture 3 is next, and your levels show Video c as a gap. We put those first, then new videos from Lecture 3.",
    );
  });
  it("says it is the student's order after a manual reorder", () => {
    expect(whyOrder({ upcoming: 3, manual: true, entries: [], videos, kus: kuList })).toMatch(/^You set this order/);
  });
  it("explains a prerequisite order and a video left partway", () => {
    const lv = { a: level("a", 1), b: level("b", 1), c: level("c", 2), d: level("d", 2) };
    const entries = buildEntries(base({ levels: lv }));
    const text = whyOrder({ upcoming: 3, manual: false, entries, videos, kus: kuList, resumeIds: ["b"] });
    expect(text).toContain("“Short a” comes first because “Short b” builds on it.");
    expect(text).toContain("You stopped “Video b” partway, so it is back at the top.");
  });
  it("shortens a long list of gaps", () => {
    const five = ["g1", "g2", "g3", "g4", "g5"].map((id, i) => video(id, "lecture-3", 3, 25 + i));
    const lv = Object.fromEntries(five.map((v) => [v.id, level(v.id, 1)]));
    const entries = buildEntries(base({ videos: five, levels: lv, course: { ...course, kus: [] } }));
    expect(whyOrder({ upcoming: 3, manual: false, entries, videos: five, kus: [] })).toContain("Video g1, Video g2, Video g3 and 2 more as gaps");
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
