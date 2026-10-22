/**
 * Pure derivations for the roadmaps from the course (./course.ts) and the student's progress as the core's API
 * reports it (state/progress.ts): which KUs are watched, and the playlist's "up next". A KU without a video is
 * "drafting" (its video is still being made from the slides).
 */
import { COURSE, KUS, lectureNumber } from "./course";
import type { CourseDef, Ku, KuStatus, LectureDef, LectureStatus } from "./types";

export interface Progress {
  /** ids of the KUs whose video the student has watched */
  watched: readonly string[];
  /** the KU the playlist plays next, if any */
  upNext: string | null;
}

export const NO_PROGRESS: Progress = { watched: [], upNext: null };

export function lectureKuIds(lecture: LectureDef): string[] {
  return lecture.sections.flatMap((s) => s.kuIds);
}

export function isDrafting(id: string): boolean {
  return !KUS[id]?.videoId;
}

/**
 * Status of every KU in a lecture. "next" is the playlist's up-next when it is in this lecture, else the first
 * unwatched KU with a video.
 */
export function kuStatuses(lecture: LectureDef, p: Progress): Record<string, KuStatus> {
  const ids = lectureKuIds(lecture);
  const playable = (id: string) => !p.watched.includes(id) && !isDrafting(id);
  const next = p.upNext && ids.includes(p.upNext) && playable(p.upNext) ? p.upNext : ids.find(playable);
  const out: Record<string, KuStatus> = {};
  for (const id of ids) {
    if (p.watched.includes(id)) out[id] = "watched";
    else if (isDrafting(id)) out[id] = "drafting";
    else out[id] = id === next ? "next" : "available";
  }
  return out;
}

export interface LectureProgress {
  done: number;
  total: number;
  nextKu: Ku | null;
}

export function lectureProgress(lecture: LectureDef, p: Progress): LectureProgress {
  const statuses = kuStatuses(lecture, p);
  const ids = lectureKuIds(lecture);
  const nextId = ids.find((id) => statuses[id] === "next");
  return {
    done: ids.filter((id) => statuses[id] === "watched").length,
    total: ids.length,
    nextKu: nextId ? KUS[nextId] : null,
  };
}

export interface LectureNodeView {
  lecture: LectureDef;
  status: LectureStatus;
  progress: LectureProgress;
}

/**
 * The course roadmap. The active lecture is the one the playlist's up-next is in; without one, the first lecture
 * with slides that isn't finished.
 */
export function courseLectures(course: CourseDef, p: Progress): LectureNodeView[] {
  const views = course.lectures.map((lecture) => ({ lecture, progress: lectureProgress(lecture, p) }));
  const open = (v: (typeof views)[number]) => v.lecture.hasSlides && v.progress.total > 0 && v.progress.done < v.progress.total;
  const upNextLecture = p.upNext ? KUS[p.upNext]?.lectureN : undefined;
  const active = views.find((v) => open(v) && v.lecture.n === upNextLecture) ?? views.find(open);
  return views.map((v) => {
    let status: LectureStatus;
    if (!v.lecture.hasSlides || v.progress.total === 0) status = "awaiting";
    else if (v.progress.done === v.progress.total) status = "completed";
    else status = v === active ? "active" : "available";
    return { ...v, status };
  });
}

export function courseProgress(course: CourseDef, p: Progress) {
  const ids = course.lectures.flatMap(lectureKuIds);
  const done = ids.filter((id) => p.watched.includes(id)).length;
  const active = courseLectures(course, p).find((l) => l.status === "active");
  return { done, total: ids.length, fraction: ids.length ? done / ids.length : 0, activeLecture: active?.lecture ?? null };
}

export type SegmentState = "done" | "partial" | "empty";

/** The 3-segment bar on a lecture section: thirds of its KUs watched. */
export function sectionSegments(kuIds: readonly string[], statuses: Record<string, KuStatus>): SegmentState[] {
  const total = kuIds.length;
  const done = kuIds.filter((id) => statuses[id] === "watched").length;
  const hasNext = kuIds.some((id) => statuses[id] === "next");
  const filled = total ? (done / total) * 3 : 0;
  return [0, 1, 2].map((i) => {
    if (filled >= i + 1) return "done";
    // the segment the student is working through
    if (filled > i || (hasNext && i === Math.floor(filled))) return "partial";
    return "empty";
  });
}

/** The swipe feed for a lecture: every KU with a video, in lecture order. */
export function lectureFeed(lecture: LectureDef): Ku[] {
  return lectureKuIds(lecture)
    .filter((id) => !isDrafting(id))
    .map((id) => KUS[id]);
}

export interface CourseFeed {
  /** every KU with a video so far, lecture by lecture in teaching order */
  kus: Ku[];
  /** the lecture the feed stops at because its check isn't done; its videos and every later lecture's wait */
  lockedAt: LectureDef | null;
}

/** The swipe feed for the whole course: every lecture's feed in turn, up to the lecture whose check is due. */
export function courseFeed(course: CourseDef, checkLectureN: number | null): CourseFeed {
  const kus: Ku[] = [];
  for (const lecture of course.lectures) {
    if (lecture.n === checkLectureN) return { kus, lockedAt: lecture };
    kus.push(...lectureFeed(lecture));
  }
  return { kus, lockedAt: null };
}

/** Where a feed opens: the KU up next if it is in the feed, else the first one not watched, else the first. */
export function feedStart(kus: readonly Ku[], p: Progress): number {
  const next = firstUpNext(p);
  const at = next ? kus.findIndex((k) => k.id === next.id) : -1;
  if (at >= 0) return at;
  return Math.max(0, kus.findIndex((k) => !p.watched.includes(k.id)));
}

/** The line above a video's title in the player: "Lecture 3 · <its section>". */
export function kuEyebrow(ku: Ku): string {
  const lecture = findLecture(ku.lectureN);
  if (!lecture) return "";
  const section = lecture.sections.find((s) => s.kuIds.includes(ku.id))?.title ?? lecture.title;
  return `Lecture ${lectureNumber(lecture.n)} · ${section}`;
}

export function findLecture(n: number): LectureDef | undefined {
  return COURSE.lectures.find((l) => l.n === n);
}

/** The KU to start with: the playlist's up-next, else the next one in the active lecture. */
export function firstUpNext(p: Progress): Ku | null {
  if (p.upNext && KUS[p.upNext]) return KUS[p.upNext];
  for (const view of courseLectures(COURSE, p)) {
    if (view.status === "active") return view.progress.nextKu;
  }
  return null;
}

export function formatTime(s: number): string {
  const total = Math.max(0, Math.floor(s));
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function kuMinutes(ku: Ku): number {
  return Math.max(1, Math.round(ku.durationS / 60));
}
