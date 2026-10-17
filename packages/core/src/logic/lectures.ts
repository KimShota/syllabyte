import type { Course } from "../types";

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
  return [...course.lectures]
    .sort((a, b) => a.n - b.n)
    .map((l) => ({
      id: lectureTopicId(l.n),
      n: l.n,
      title: l.title,
      week: l.week,
      ku_ids: course.kus.filter((k) => k.lecture_n === l.n).map((k) => k.id),
    }));
}
