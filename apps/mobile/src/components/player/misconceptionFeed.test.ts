import { describe, expect, it } from "vitest";
import type { Ku } from "@/data/types";
import { buildFeedItems, feedKey, type ReadyClip } from "./misconceptionFeed";

const ku = (id: string): Ku => ({
  id, title: id, shortTitle: id, lectureN: 1, slides: [1, 2], durationS: 60, videoId: id,
  scene: { kind: "statement", framework: "", headline: id, points: [] }, transcript: [],
});
const ready = (id: string): ReadyClip => ({
  request: { id }, item_title: "Original lesson",
  clip: { video: { id: "shared-ku", title: "Correction", short_title: "A closer look", lecture_n: 1, source_slides: [3, 5], duration_s: 90, video_url: "https://example.com/clip.mp4", captions_burned_in: true } },
}) as ReadyClip;

describe("misconception videos in the feed", () => {
  const lessons = [ku("a"), ku("b")];
  it("inserts Watch now's clip after the current video and keeps the next lesson and ending in order", () => {
    const items = buildFeedItems(lessons, true, [{ after: "video:a", ready: ready("r1") }]);
    expect(items.map(feedKey)).toEqual(["video:a", "misconception:r1", "video:b", "end"]);
    const clip = items[1];
    expect(clip.kind).toBe("misconception");
    if (clip.kind === "misconception") {
      expect(clip.ku.videoUri).toBe("https://example.com/clip.mp4");
      expect(clip.ku.durationS).toBe(90);
      expect(clip.ku.videoId).toBeNull(); // playback must not submit progress against the original lesson
      expect(clip.ku.id).not.toBe("shared-ku");
      expect(clip.ready.request.id).toBe("r1");
    }
    expect(items[0]).toEqual({ kind: "video", ku: lessons[0] });
  });

  it("leaves Later's clip out of the feed until it is accepted", () => {
    expect(buildFeedItems(lessons, true, []).map(feedKey)).toEqual(["video:a", "video:b", "end"]);
  });

  it("inserts before the ending when accepted from the end page", () => {
    expect(buildFeedItems(lessons, true, [{ after: "end", ready: ready("r1") }]).map(feedKey))
      .toEqual(["video:a", "video:b", "misconception:r1", "end"]);
  });

  it("keeps one page per request, even when the same accepted clip appears again", () => {
    const insertion = { after: "video:a", ready: ready("r1") };
    expect(buildFeedItems(lessons, false, [insertion, insertion]).map(feedKey)).toEqual(["video:a", "misconception:r1", "video:b"]);
  });

  it("keeps different corrections for the same lesson distinct", () => {
    const items = buildFeedItems(lessons, false, [{ after: "video:a", ready: ready("r1") }, { after: "misconception:r1", ready: ready("r2") }]);
    expect(items.map(feedKey)).toEqual(["video:a", "misconception:r1", "misconception:r2", "video:b"]);
  });

  it("keeps an accepted clip accessible if a course refresh removes its original anchor", () => {
    expect(buildFeedItems([], true, [{ after: "video:a", ready: ready("r1") }]).map(feedKey)).toEqual(["misconception:r1", "end"]);
  });
});
