import type { Course, Lecture } from "../types";

/** A lecture's place in the teaching order (plan/slide-uploads-plan.md V1): its `position`, else its number. */
export const lecturePosition = (l: Lecture): number => l.position ?? l.n;

/** The course's lectures in teaching order. */
export const lecturesInOrder = (course: Course): Lecture[] => [...course.lectures].sort((a, b) => lecturePosition(a) - lecturePosition(b));

/** Lecture `a` is taught before lecture `b` (both by number). */
export function taughtBefore(course: Course, a: number, b: number): boolean {
  const pos = (n: number) => {
    const l = course.lectures.find((x) => x.n === n);
    return l ? lecturePosition(l) : n;
  };
  return pos(a) < pos(b);
}

/**
 * A topic is a lecture (plan/per-ku-profiling-plan.md D2): the unit one CAT ability (theta) is estimated for.
 * Derived from the course's lectures and KUs, so there is no hand-written topic list.
 */
export interface LectureTopic {
  id: string;
  n: number;
  title: string;
  week: number;
  ku_ids: string[];
}

export const lectureTopicId = (n: number): string => `lecture-${n}`;

export function lectureTopics(course: Course): LectureTopic[] {
  return lecturesInOrder(course)
    .map((l) => ({
      id: lectureTopicId(l.n),
      n: l.n,
      title: l.title,
      week: l.week,
      ku_ids: course.kus.filter((k) => k.lecture_n === l.n).map((k) => k.id),
    }));
}
