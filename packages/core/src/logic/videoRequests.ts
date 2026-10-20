import type { Course, KuLevel, Level, SittingState } from "../types";
import { week0Lectures } from "./assessment";

/**
 * Which videos a student needs made (plan/slide-uploads-plan.md U18): every KU of a lecture whose levels a sitting has
 * set, at the student's level for it, unless one was already made for them (D15: made once, never remade). A lecture's
 * levels are set by the baseline when it covered the lecture, else by the lecture's own check. Provisional levels from
 * the baseline never start a video: the check would only lock a guess in. KUs added to a lecture after its check
 * (U10) are included as soon as they have a level. In course order, so the earliest lecture is made first.
 */
export interface VideoRequest {
  ku_id: string;
  lecture_n: number;
  level: Level;
}

export function lecturesWithSetLevels(course: Course, sittings: Record<string, SittingState>): Set<number> {
  const set = new Set<number>();
  const w0 = sittings.week0;
  if (w0?.finished_at) for (const n of w0.lectures ?? week0Lectures(course)) set.add(n);
  for (const st of Object.values(sittings)) if (st.kind === "lecture" && st.finished_at && st.lecture_n !== null) set.add(st.lecture_n);
  return set;
}

export function videoRequests(
  course: Course,
  sittings: Record<string, SittingState>,
  levels: Record<string, KuLevel>,
  made: Record<string, Level>,
): VideoRequest[] {
  const set = lecturesWithSetLevels(course, sittings);
  return [...course.kus]
    .filter((k) => set.has(k.lecture_n) && levels[k.id] && made[k.id] === undefined)
    .sort((a, b) => a.lecture_n - b.lecture_n)
    .map((k) => ({ ku_id: k.id, lecture_n: k.lecture_n, level: levels[k.id].level }));
}
