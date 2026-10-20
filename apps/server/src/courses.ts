import { randomUUID } from "node:crypto";
import { assembleCourse, type DeckResult } from "@syllabyte/core/logic/assemble";
import type { Fixtures } from "@syllabyte/core/types";
import type { Db } from "./db";

/**
 * Uploaded courses (plan/slide-uploads-plan.md): reading and writing the course tables, and the course each student's
 * requests run against. The assembled course is cached per course and rebuilt after any write to it.
 */

export interface CourseRow {
  id: string;
  syllabus_key: string;
  code: string;
  name: string;
  syllabus_text: string;
  syllabus_path: string;
  status: "reading" | "ready" | "failed";
  schedule_found: number | null;
  created_by: string;
  created_at: number;
  lectures_confirmed_at: number | null;
}

export interface LectureRow {
  id: string;
  course_id: string;
  n: number;
  title: string;
  week: number | null;
  source: "syllabus" | "upload";
}

export interface DeckRow {
  id: string;
  course_id: string;
  lecture_id: string | null;
  content_key: string;
  file_name: string;
  pdf_path: string;
  parse_json: string;
  status: "unplaced" | "queued" | "processing" | "ready" | "failed";
  result_json: string | null;
  first_user_id: string;
  created_at: number;
  placed_at: number | null;
  ready_at: number | null;
  error: string | null;
}

export class Courses {
  private cache = new Map<string, Fixtures>();

  constructor(
    private db: Db,
    private now: () => number = Date.now,
  ) {}

  /** Drop the cached course after a write; the next request assembles it again. */
  touched(courseId: string): void {
    this.cache.delete(courseId);
  }

  get(courseId: string): CourseRow | null {
    return (this.db.prepare("SELECT * FROM courses WHERE id = ?").get(courseId) as CourseRow | undefined) ?? null;
  }

  byKey(syllabusKey: string): CourseRow | null {
    return (this.db.prepare("SELECT * FROM courses WHERE syllabus_key = ?").get(syllabusKey) as CourseRow | undefined) ?? null;
  }

  /** The student's course; one per student for now (U4). */
  courseOf(userId: string): string | null {
    const row = this.db.prepare("SELECT course_id FROM course_members WHERE user_id = ? ORDER BY joined_at LIMIT 1").get(userId) as
      | { course_id: string }
      | undefined;
    return row?.course_id ?? null;
  }

  create(c: { syllabusKey: string; code: string; name: string; syllabusText: string; syllabusPath: string; createdBy: string; status?: CourseRow["status"] }): string {
    const id = randomUUID();
    this.db
      .prepare(
        "INSERT INTO courses (id, syllabus_key, code, name, syllabus_text, syllabus_path, status, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
      )
      .run(id, c.syllabusKey, c.code, c.name, c.syllabusText, c.syllabusPath, c.status ?? "reading", c.createdBy, this.now());
    return id;
  }

  addMember(courseId: string, userId: string): void {
    this.db.prepare("INSERT OR IGNORE INTO course_members (course_id, user_id, joined_at) VALUES (?, ?, ?)").run(courseId, userId, this.now());
  }

  lectures(courseId: string): LectureRow[] {
    return this.db.prepare("SELECT * FROM lectures WHERE course_id = ? ORDER BY n").all(courseId) as unknown as LectureRow[];
  }

  /** Replaces the lecture list; refused once a deck is placed in it (the researcher moves decks first). */
  setLectures(courseId: string, list: { n: number; title: string; week: number | null }[], source: LectureRow["source"]): void {
    const placed = this.db.prepare("SELECT COUNT(*) AS n FROM decks WHERE course_id = ? AND lecture_id IS NOT NULL").get(courseId) as { n: number };
    if (placed.n > 0) throw new Error("decks are already placed in this course's lectures");
    this.db.prepare("DELETE FROM lectures WHERE course_id = ?").run(courseId);
    const insert = this.db.prepare("INSERT INTO lectures (id, course_id, n, title, week, source) VALUES (?, ?, ?, ?, ?, ?)");
    for (const l of list) insert.run(randomUUID(), courseId, l.n, l.title, l.week, source);
    this.touched(courseId);
  }

  addLecture(courseId: string, l: { n: number; title: string; week: number | null }, source: LectureRow["source"]): string {
    const id = randomUUID();
    this.db.prepare("INSERT INTO lectures (id, course_id, n, title, week, source) VALUES (?, ?, ?, ?, ?, ?)").run(id, courseId, l.n, l.title, l.week, source);
    this.touched(courseId);
    return id;
  }

  decks(courseId: string): DeckRow[] {
    return this.db.prepare("SELECT * FROM decks WHERE course_id = ? ORDER BY created_at").all(courseId) as unknown as DeckRow[];
  }

  deck(deckId: string): DeckRow | null {
    return (this.db.prepare("SELECT * FROM decks WHERE id = ?").get(deckId) as DeckRow | undefined) ?? null;
  }

  /** The processed result of a deck; the course's KUs and items change, so its cache is dropped. */
  setDeckResult(deckId: string, result: DeckResult): void {
    const deck = this.deck(deckId);
    if (!deck) throw new Error(`unknown deck ${deckId}`);
    this.db.prepare("UPDATE decks SET status = 'ready', result_json = ?, ready_at = ?, error = NULL WHERE id = ?").run(JSON.stringify(result), this.now(), deckId);
    this.touched(deck.course_id);
  }

  addLinks(courseId: string, links: { ku_id: string; prereq_id: string }[]): void {
    const insert = this.db.prepare("INSERT OR IGNORE INTO ku_links (course_id, ku_id, prereq_id, added_at) VALUES (?, ?, ?, ?)");
    for (const l of links) insert.run(courseId, l.ku_id, l.prereq_id, this.now());
    this.touched(courseId);
  }

  /** The course as the shared rules read it: every lecture, the processed decks placed in them, and the added links. */
  fixtures(courseId: string): Fixtures {
    const cached = this.cache.get(courseId);
    if (cached) return cached;
    const course = this.get(courseId);
    if (!course) throw new Error(`unknown course ${courseId}`);
    const lectures = this.lectures(courseId);
    const nOf = new Map(lectures.map((l) => [l.id, l.n]));
    const decks = this.decks(courseId)
      .filter((d) => d.status === "ready" && d.result_json && d.lecture_id && nOf.has(d.lecture_id))
      .map((d) => ({ lecture_n: nOf.get(d.lecture_id!)!, result: JSON.parse(d.result_json!) as DeckResult }));
    const links = this.db.prepare("SELECT ku_id, prereq_id FROM ku_links WHERE course_id = ?").all(courseId) as { ku_id: string; prereq_id: string }[];
    const fx = assembleCourse({
      id: course.id,
      code: course.code,
      name: course.name,
      lectures: lectures.map((l) => ({ n: l.n, title: l.title, week: l.week })),
      decks,
      links,
    });
    this.cache.set(courseId, fx);
    return fx;
  }

  /** The course a student's requests run against: theirs, or null for a student without one (they get the demo course). */
  fixturesFor(userId: string): Fixtures | null {
    const id = this.courseOf(userId);
    return id ? this.fixtures(id) : null;
  }
}
