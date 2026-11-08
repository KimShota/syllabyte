import type { DemoState } from "@syllabyte/core/types";
import type { Db } from "./db";

/**
 * A student's saved state, stored in two layers so that a student can have several courses (plan/participant-ready-plan.md,
 * multi-course):
 *
 *  - the profile, one per student: who they are to the study and the app (consent, condition, settings, the research event
 *    log, the questionnaires, one-time flags, the study clock's anchor);
 *  - a course document, one per student and course: everything that is about that course's KUs (levels, answers,
 *    sittings, playlist, what they watched, notes). A student without a course has one under the id "" (the demo course).
 *
 * The core keeps working on one whole `DemoState`: the runner merges the two layers when it loads a student and splits
 * them again when it saves, so nothing in core knows about courses.
 */

/** the fields of `DemoState` that belong to the student, not to a course */
export const PROFILE_KEYS = [
  "v", "clock_offset_ms", "semester_start", "participant_code", "consent", "condition", "settings", "events", "study", "flags", "visit",
] as const satisfies readonly (keyof DemoState)[];

type ProfileKey = (typeof PROFILE_KEYS)[number];
export type Profile = Pick<DemoState, ProfileKey>;
export type CourseDoc = Omit<DemoState, ProfileKey>;

/** The demo course's id in `course_state`: a student who has not uploaded a course. */
export const NO_COURSE = "";

export function splitState(s: DemoState): { profile: Profile; course: CourseDoc } {
  const profile: Record<string, unknown> = {};
  const course: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(s)) (PROFILE_KEYS as readonly string[]).includes(k) ? (profile[k] = v) : (course[k] = v);
  return { profile: profile as unknown as Profile, course: course as unknown as CourseDoc };
}

export class StateStore {
  constructor(private db: Db) {}

  profile(userId: string): Partial<Profile> | null {
    const row = this.db.prepare("SELECT json FROM user_profile WHERE user_id = ?").get(userId) as { json: string } | undefined;
    return row ? (JSON.parse(row.json) as Partial<Profile>) : null;
  }

  course(userId: string, courseId: string): Partial<CourseDoc> | null {
    const row = this.db.prepare("SELECT json FROM course_state WHERE user_id = ? AND course_id = ?").get(userId, courseId) as { json: string } | undefined;
    return row ? (JSON.parse(row.json) as Partial<CourseDoc>) : null;
  }

  /** Every course document of a student, newest first. */
  courseDocs(userId: string): { course_id: string; doc: Partial<CourseDoc> }[] {
    const rows = this.db.prepare("SELECT course_id, json FROM course_state WHERE user_id = ? ORDER BY updated_at DESC").all(userId) as { course_id: string; json: string }[];
    return rows.map((r) => ({ course_id: r.course_id, doc: JSON.parse(r.json) as Partial<CourseDoc> }));
  }

  save(userId: string, courseId: string, state: DemoState, now = Date.now()): void {
    const { profile, course } = splitState(state);
    this.db
      .prepare("INSERT INTO user_profile (user_id, json, updated_at) VALUES (?, ?, ?) ON CONFLICT (user_id) DO UPDATE SET json = excluded.json, updated_at = excluded.updated_at")
      .run(userId, JSON.stringify(profile), now);
    this.db
      .prepare(
        "INSERT INTO course_state (user_id, course_id, json, updated_at) VALUES (?, ?, ?, ?) " +
          "ON CONFLICT (user_id, course_id) DO UPDATE SET json = excluded.json, updated_at = excluded.updated_at",
      )
      .run(userId, courseId, JSON.stringify(course), now);
  }

  /** Forgets a student's documents for a course (the facilitator moved them away before they answered anything). */
  dropCourse(userId: string, courseId?: string): void {
    if (courseId === undefined) this.db.prepare("DELETE FROM course_state WHERE user_id = ?").run(userId);
    else this.db.prepare("DELETE FROM course_state WHERE user_id = ? AND course_id = ?").run(userId, courseId);
  }

  /**
   * One state per student, for the researcher's export: their profile with the course document of the course they are
   * in (`activeOf`), else the one they used last. The study is one row per participant.
   */
  allStates(activeOf: (userId: string) => string | null): DemoState[] {
    const users = this.db.prepare("SELECT user_id FROM user_profile").all() as { user_id: string }[];
    const out: DemoState[] = [];
    for (const { user_id } of users) {
      const docs = this.courseDocs(user_id);
      const want = activeOf(user_id);
      const chosen = docs.find((d) => d.course_id === want) ?? docs[0];
      out.push({ ...(chosen?.doc ?? {}), ...(this.profile(user_id) ?? {}) } as DemoState);
    }
    return out;
  }
}

/**
 * Databases from before several courses kept one document per student (`user_state`). Each is split into a profile and
 * the course document of the course the student was in (the demo course's id when they had none); the old row stays,
 * untouched, as a backup. Safe to run again: it only fills in students that have no profile yet.
 */
export function migrateStates(db: Db): void {
  const rows = db
    .prepare("SELECT s.user_id, s.json, s.updated_at FROM user_state s WHERE NOT EXISTS (SELECT 1 FROM user_profile p WHERE p.user_id = s.user_id)")
    .all() as { user_id: string; json: string; updated_at: number }[];
  if (!rows.length) return;
  const store = new StateStore(db);
  const courseOf = db.prepare("SELECT course_id FROM course_members WHERE user_id = ? ORDER BY joined_at LIMIT 1");
  db.exec("BEGIN");
  try {
    for (const r of rows) {
      const course = (courseOf.get(r.user_id) as { course_id: string } | undefined)?.course_id ?? NO_COURSE;
      store.save(r.user_id, course, JSON.parse(r.json) as DemoState, r.updated_at);
    }
    db.exec("COMMIT");
  } catch (e) {
    db.exec("ROLLBACK");
    throw e;
  }
}
