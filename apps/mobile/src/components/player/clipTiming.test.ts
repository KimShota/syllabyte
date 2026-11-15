import { describe, expect, it } from "vitest";
import { clipDecision } from "./clipTiming";

const clip = (id: string) => ({ request: { id } });
const base = { clips: [clip("a")], deferred: new Set<string>(), laterCount: {}, moved: false, canShow: true, busy: false, reoffers: 1 };

describe("when a misconception clip is shown", () => {
  it("at once when it is ready and no video is in progress", () => {
    expect(clipDecision(base).show?.request.id).toBe("a");
  });

  it("not over a video in progress, but at the move to the next one", () => {
    expect(clipDecision({ ...base, busy: true }).show).toBeNull();
    expect(clipDecision({ ...base, busy: true, moved: true }).show?.request.id).toBe("a");
  });

  it("never while another card is open or the feed is not on screen", () => {
    expect(clipDecision({ ...base, canShow: false, moved: true }).show).toBeNull();
  });

  it("put off with Later: not again until the next move, and only once more", () => {
    const later = { ...base, deferred: new Set(["a"]), laterCount: { a: 1 } };
    expect(clipDecision(later).show).toBeNull(); // same video: stays put off
    const next = clipDecision({ ...later, moved: true });
    expect(next.show?.request.id).toBe("a");
    expect(next.deferred.has("a")).toBe(false);
    const twice = clipDecision({ ...later, laterCount: { a: 2 }, moved: true });
    expect(twice.show).toBeNull(); // put off twice: not again in this visit
  });

  it("once watched, never again in this visit, even if a check still lists it", () => {
    expect(clipDecision({ ...base, deferred: new Set(["a"]), laterCount: { a: Infinity }, moved: true }).show).toBeNull();
  });

  it("the oldest waiting clip first", () => {
    expect(clipDecision({ ...base, clips: [clip("old"), clip("new")] }).show?.request.id).toBe("old");
  });
});
