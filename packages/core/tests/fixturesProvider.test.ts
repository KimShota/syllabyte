import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Fixtures } from "../src/types";

// The API answers about whichever course is set (plan/slide-uploads-plan.md U19): the server sets each student's
// course as it loads their state. Uses the real fixtures as the starting point, so it skips without them.
const haveFixtures = existsSync(resolve(__dirname, "../fixtures/bank.json"));

describe.skipIf(!haveFixtures)("the course provider", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let fx: typeof import("../src/fixtures");

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    fx = await import("../src/fixtures");
    store.resetState();
  });

  afterEach(() => fx.setFixtures(fx.FIX));

  /** The demo course cut to its first lecture, under another name. */
  function firstLectureOnly(): Fixtures {
    const c = structuredClone(fx.FIX.course);
    c.name = "Another course";
    c.lectures = c.lectures.filter((l) => l.n === 1);
    c.kus = c.kus.filter((k) => k.lecture_n === 1);
    const kuIds = new Set(c.kus.map((k) => k.id));
    c.topics = c.topics.filter((t) => t.first_lecture === 1);
    return {
      course: c,
      items: fx.FIX.items.filter((i) => i.ku_id === null || kuIds.has(i.ku_id)),
      videos: fx.FIX.videos.filter((v) => kuIds.has(v.ku_id)),
      slides: fx.FIX.slides,
    };
  }

  it("defaults to the demo course", () => {
    expect(fx.fixtures()).toBe(fx.FIX);
  });

  it("answers about the course that is set, and back again", async () => {
    const other = firstLectureOnly();
    fx.setFixtures(other);
    expect(fx.fixtures().course.name).toBe("Another course");
    const map = await api.getCourseMap();
    expect(map.lectures.map((l) => l.lecture.n)).toEqual([1]);

    fx.setFixtures(fx.FIX);
    const full = await api.getCourseMap();
    expect(full.lectures.length).toBe(fx.FIX.course.lectures.filter((l) => fx.FIX.course.kus.some((k) => k.lecture_n === l.n)).length);
  });

  it("looks items and videos up in the course that is set", () => {
    const other = firstLectureOnly();
    const dropped = fx.FIX.videos.find((v) => !other.videos.includes(v));
    fx.setFixtures(other);
    if (dropped) expect(() => fx.videoById(dropped.id)).toThrow(/unknown video/);
    fx.setFixtures(fx.FIX);
    if (dropped) expect(fx.videoById(dropped.id).id).toBe(dropped.id);
  });
});
