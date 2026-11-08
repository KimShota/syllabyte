import type { MyCourseView } from "@syllabyte/core/api/types";

/**
 * When the course will change by itself, so the phone keeps looking at it (state/course.ts): a syllabus is being read,
 * slides are being analyzed, or videos are being made. Kept apart from the screens' state so it can be tested.
 */
export function busy(v: MyCourseView | null): boolean {
  if (!v) return false;
  if (v.status === "reading") return true;
  return v.status === "ready" && (v.course.lectures.some((l) => l.state === "analyzing") || v.course.videos_pending > 0 || v.adding?.status === "reading");
}

/** Only videos are still being made: the course will change by itself, but nobody is waiting on this screen for it. */
export function onlyVideosPending(v: MyCourseView | null): boolean {
  return busy(v) && v?.status === "ready" && !v.course.lectures.some((l) => l.state === "analyzing") && v.adding?.status !== "reading";
}
