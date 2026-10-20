import type { Courses } from "./courses";
import type { Db } from "./db";
import { UploadError, type Uploads } from "./uploads";

/**
 * The researcher's fixes for uploaded courses (plan/slide-uploads-plan.md U11, U12, U17), behind
 * `npm run courses`. Students never reorganize a course; these are for mistakes: a wrong lecture title or placement,
 * one course split in two by slightly different syllabi, a failed job.
 */

export function courseSummaries(db: Db) {
  const rows = db
    .prepare(
      `SELECT c.id, c.code, c.name, c.created_at,
        (SELECT COUNT(*) FROM course_members m WHERE m.course_id = c.id) AS students,
        (SELECT COUNT(*) FROM lectures l WHERE l.course_id = c.id) AS lectures,
        (SELECT COUNT(*) FROM decks d WHERE d.course_id = c.id AND d.status = 'ready') AS ready_decks,
        (SELECT COUNT(*) FROM decks d WHERE d.course_id = c.id AND d.status = 'failed') AS failed_decks
       FROM courses c ORDER BY c.created_at`,
    )
    .all() as { id: string; code: string; name: string; created_at: number; students: number; lectures: number; ready_decks: number; failed_decks: number }[];
  return rows;
}

export function courseDetail(db: Db, courses: Courses, courseId: string) {
  const c = courses.get(courseId);
  if (!c) throw new UploadError(`no course ${courseId}`, 404);
  const lectures = courses.lectures(courseId);
  const decks = courses.decks(courseId);
  return {
    course: { id: c.id, code: c.code, name: c.name, confirmed: c.lectures_confirmed_at !== null },
    lectures: lectures.map((l) => ({
      n: l.n,
      title: l.title,
      decks: decks.filter((d) => d.lecture_id === l.id).map((d) => ({ id: d.id, file: d.file_name, status: d.status, error: d.error })),
    })),
    unplaced: decks.filter((d) => !d.lecture_id).map((d) => ({ id: d.id, file: d.file_name })),
    updated_versions: db
      .prepare("SELECT u.file_name, u.created_at, us.participant_code FROM deck_uploads u JOIN users us ON us.id = u.user_id WHERE u.course_id = ? AND u.outcome = 'updated_version' ORDER BY u.created_at")
      .all(courseId) as { file_name: string; created_at: number; participant_code: string }[],
    failed_jobs: db
      .prepare("SELECT id, kind, error FROM jobs WHERE course_id = ? AND status = 'failed' ORDER BY created_at")
      .all(courseId) as { id: string; kind: string; error: string }[],
  };
}

export function renameLecture(courses: Courses, courseId: string, n: number, title: string): void {
  const l = courses.lectures(courseId).find((x) => x.n === n);
  if (!l) throw new UploadError(`no lecture ${n}`, 404);
  if (!title.trim()) throw new UploadError("a title is required");
  courses.renameLecture(l.id, title.trim());
}

/** Adds a lecture after the last one (a syllabus that missed one, or a course without a schedule). */
export function appendLecture(courses: Courses, courseId: string, title: string): number {
  const n = (courses.lectures(courseId).at(-1)?.n ?? 0) + 1;
  courses.addLecture(courseId, { n, title: title.trim(), week: null }, "upload");
  return n;
}

/**
 * Puts a deck in another lecture. Its KUs stay as they are; they now count for that lecture's level and checks.
 * Students who already took a check on either lecture keep their answers.
 */
export function moveDeck(db: Db, courses: Courses, deckId: string, lectureN: number): void {
  const deck = courses.deck(deckId);
  if (!deck) throw new UploadError(`no deck ${deckId}`, 404);
  const l = courses.lectures(deck.course_id).find((x) => x.n === lectureN);
  if (!l) throw new UploadError(`no lecture ${lectureN}`, 404);
  db.prepare("UPDATE decks SET lecture_id = ? WHERE id = ?").run(l.id, deckId);
  courses.touched(deck.course_id);
}

function studentByCodeOrEmail(db: Db, who: string): { id: string; participant_code: string } {
  const u = db.prepare("SELECT id, participant_code FROM users WHERE participant_code = ? OR email = ?").get(who, who.toLowerCase()) as
    | { id: string; participant_code: string }
    | undefined;
  if (!u) throw new UploadError(`no student ${who}`, 404);
  return u;
}

/** A student who has answered nothing yet can move: their KUs and questions would otherwise come from two courses. */
function hasAnswers(db: Db, userId: string): boolean {
  const row = db.prepare("SELECT json FROM user_state WHERE user_id = ?").get(userId) as { json: string } | undefined;
  return row ? ((JSON.parse(row.json) as { responses?: unknown[] }).responses?.length ?? 0) > 0 : false;
}

/** Points a student at another course (U17), before they have answered anything. */
export function moveStudent(db: Db, courses: Courses, who: string, courseId: string): void {
  const u = studentByCodeOrEmail(db, who);
  if (!courses.get(courseId)) throw new UploadError(`no course ${courseId}`, 404);
  if (hasAnswers(db, u.id)) throw new UploadError(`${u.participant_code} has already answered questions in their course`, 409);
  db.prepare("DELETE FROM course_members WHERE user_id = ?").run(u.id);
  courses.addMember(courseId, u.id);
}

/**
 * Merges course `from` into `into` (U17): its students move, and its syllabus joins `into` from now on. Only while
 * `from` has no slides placed and its students have answered nothing.
 */
export function mergeCourses(db: Db, courses: Courses, fromId: string, intoId: string): void {
  const from = courses.get(fromId);
  if (!from || !courses.get(intoId)) throw new UploadError("unknown course", 404);
  if (fromId === intoId) throw new UploadError("a course can't be merged into itself");
  if (courses.decks(fromId).some((d) => d.lecture_id)) throw new UploadError("that course already has slides placed; move its students one by one", 409);
  const members = db.prepare("SELECT user_id FROM course_members WHERE course_id = ?").all(fromId) as { user_id: string }[];
  for (const m of members) if (hasAnswers(db, m.user_id)) throw new UploadError("a student of that course has already answered questions", 409);
  db.exec("BEGIN");
  try {
    for (const m of members) {
      db.prepare("DELETE FROM course_members WHERE user_id = ?").run(m.user_id);
      courses.addMember(intoId, m.user_id);
    }
    db.prepare("INSERT OR REPLACE INTO syllabus_aliases (syllabus_key, course_id, added_at) VALUES (?, ?, ?)").run(from.syllabus_key, intoId, Date.now());
    db.prepare("UPDATE syllabus_aliases SET course_id = ? WHERE course_id = ?").run(intoId, fromId);
    db.prepare("UPDATE syllabus_uploads SET course_id = ? WHERE course_id = ?").run(intoId, fromId);
    db.prepare("DELETE FROM deck_uploads WHERE course_id = ?").run(fromId);
    db.prepare("DELETE FROM decks WHERE course_id = ?").run(fromId);
    db.prepare("DELETE FROM jobs WHERE course_id = ?").run(fromId);
    db.prepare("DELETE FROM courses WHERE id = ?").run(fromId);
    db.exec("COMMIT");
  } catch (e) {
    db.exec("ROLLBACK");
    throw e;
  }
  courses.touched(intoId);
}

export function retryJob(uploads: Uploads, jobId: string): void {
  uploads.retry(jobId);
}
