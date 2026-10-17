import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

// The course comes from the shared fixtures, which are local-only (course material); without them this skips.
const haveFixtures = existsSync(resolve(__dirname, "../../../../packages/core/fixtures/course.json"));

describe.skipIf(!haveFixtures)("roadmap selectors on the real course", () => {
  let C: typeof import("./course");
  let S: typeof import("./selectors");

  beforeAll(async () => {
    C = await import("./course");
    S = await import("./selectors");
  });

  const lecture = (n: number) => C.COURSE.lectures.find((l) => l.n === n)!;
  const ids = (n: number) => S.lectureKuIds(lecture(n));
  const withVideo = (n: number) => ids(n).filter((id) => !S.isDrafting(id));
  const none = { watched: [], upNext: null };

  it("builds every KU from the fixtures, and only KUs with a video are playable", () => {
    const all = C.COURSE.lectures.flatMap(S.lectureKuIds);
    expect(new Set(all).size).toBe(Object.keys(C.KUS).length);
    for (const n of [1, 2, 3]) expect(withVideo(n).length).toBeGreaterThan(0);
    expect(Object.values(C.KUS).filter((k) => k.videoId).every((k) => k.transcript.length > 0)).toBe(true);
  });

  it("marks KUs without a video as drafting, and the first playable one as next", () => {
    const s = S.kuStatuses(lecture(1), none);
    for (const id of ids(1)) expect(s[id]).toBe(S.isDrafting(id) ? "drafting" : id === withVideo(1)[0] ? "next" : "available");
  });

  it("prefers the playlist's up-next when it is in the lecture", () => {
    const [first, second] = withVideo(1);
    expect(second).toBeDefined();
    const s = S.kuStatuses(lecture(1), { watched: [], upNext: second });
    expect(s[second]).toBe("next");
    expect(s[first]).toBe("available");
  });

  it("has no next once every video in the lecture is watched", () => {
    const s = S.kuStatuses(lecture(1), { watched: withVideo(1), upNext: null });
    expect(Object.values(s)).not.toContain("next");
  });

  it("makes the up-next's lecture the active one, and lectures without slides awaiting", () => {
    const up = withVideo(3)[0];
    const views = S.courseLectures(C.COURSE, { watched: [], upNext: up });
    expect(views.filter((v) => v.status === "active").map((v) => v.lecture.n)).toEqual([3]);
    expect(views.filter((v) => !v.lecture.hasSlides).every((v) => v.status === "awaiting")).toBe(true);
    expect(S.firstUpNext({ watched: [], upNext: up })?.id).toBe(up);
  });

  it("without an up-next, starts on the first lecture's first video", () => {
    expect(S.courseLectures(C.COURSE, none).find((v) => v.status === "active")?.lecture.n).toBe(1);
    expect(S.firstUpNext(none)?.id).toBe(withVideo(1)[0]);
  });

  it("counts watched KUs out of every KU", () => {
    const p = S.courseProgress(C.COURSE, { watched: withVideo(1), upNext: null });
    expect(p.done).toBe(withVideo(1).length);
    expect(p.total).toBe(Object.keys(C.KUS).length);
  });

  it("leaves drafting KUs out of the swipe feed", () => {
    expect(S.lectureFeed(lecture(1)).map((k) => k.id)).toEqual(withVideo(1));
  });

  it("puts every KU of a lecture in exactly one section", () => {
    for (const l of C.COURSE.lectures.filter((x) => x.hasSlides)) {
      const placed = l.sections.flatMap((s) => s.kuIds);
      expect(new Set(placed).size).toBe(placed.length);
      expect(placed.every((id) => C.KUS[id].lectureN === l.n)).toBe(true);
    }
  });

  const six = ["a", "b", "c", "d", "e", "f"];

  it("fills a section's thirds as KUs are watched", () => {
    expect(S.sectionSegments(six, { a: "watched", b: "watched", c: "next", d: "available", e: "available", f: "available" })).toEqual(["done", "partial", "empty"]);
    expect(S.sectionSegments(six, Object.fromEntries(six.map((i) => [i, "watched" as const])))).toEqual(["done", "done", "done"]);
  });

  it("shows a section's first third in progress when it holds the next KU", () => {
    expect(S.sectionSegments(six, { a: "next", b: "available", c: "available", d: "available", e: "available", f: "available" })).toEqual(["partial", "empty", "empty"]);
  });

  it("formats seconds as mm:ss", () => {
    expect(S.formatTime(0)).toBe("00:00");
    expect(S.formatTime(102.7)).toBe("01:42");
    expect(S.formatTime(240)).toBe("04:00");
  });
});
