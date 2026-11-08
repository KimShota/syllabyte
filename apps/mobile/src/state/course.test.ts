import type { MyCourseView } from "@syllabyte/core/api/types";
import { describe, expect, it } from "vitest";
import { busy, onlyVideosPending } from "./courseWait";

const ready = (over: { videos_pending?: number; slides_pending?: number; states?: string[]; adding?: unknown }): MyCourseView =>
  ({
    status: "ready",
    course: { id: "c", code: "C", name: "C", videos_pending: over.videos_pending ?? 0, slides_pending: over.slides_pending ?? 0, lectures: (over.states ?? ["ready"]).map((state, i) => ({ n: i + 1, title: "L", state })) },
    adding: over.adding ?? null,
  }) as unknown as MyCourseView;

describe("when the phone keeps looking at the course", () => {
  it("looks while a syllabus is read, slides are analyzed or videos are made, and stops otherwise", () => {
    expect(busy({ status: "reading" })).toBe(true);
    expect(busy(ready({ states: ["analyzing"] }))).toBe(true);
    expect(busy(ready({ videos_pending: 3 }))).toBe(true);
    expect(busy(ready({}))).toBe(false);
    expect(busy(null)).toBe(false);
    expect(busy({ status: "none" })).toBe(false);
  });

  it("looks while another course's syllabus is read, and stops once it failed (the error waits to be seen)", () => {
    expect(busy(ready({ adding: { status: "reading" } }))).toBe(true);
    expect(busy(ready({ adding: { status: "failed", error: "a scan" } }))).toBe(false);
  });

  it("keeps polling while slides are organized, even before any lecture exists", () => {
    const organizing = ready({ states: [], slides_pending: 2 });
    expect(busy(organizing)).toBe(true);
    expect(onlyVideosPending(organizing)).toBe(false);
    expect(busy(ready({ states: [], slides_pending: 0 }))).toBe(false);
  });

  it("looks more slowly when only videos are being made", () => {
    expect(onlyVideosPending(ready({ videos_pending: 2, adding: { status: "reading" } }))).toBe(false); // a student is waiting on the syllabus
    expect(onlyVideosPending(ready({ videos_pending: 2 }))).toBe(true);
    expect(onlyVideosPending(ready({ videos_pending: 2, states: ["analyzing"] }))).toBe(false); // a student is waiting on the slides
    expect(onlyVideosPending({ status: "reading" })).toBe(false);
    expect(onlyVideosPending(ready({}))).toBe(false);
  });
});
