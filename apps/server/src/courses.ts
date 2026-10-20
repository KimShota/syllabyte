import { randomUUID } from "node:crypto";
import { assembleCourse, type DeckResult } from "@syllabyte/core/logic/assemble";
import { videoRequests, type VideoRequest } from "@syllabyte/core/logic/videoRequests";
import type { DemoState, Fixtures } from "@syllabyte/core/types";
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
  file_path: string;
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

  /**
   * The course's decks in course order: by lecture, then when they were placed (part 1 before part 2), then id, so the
   * order never depends on timing ties. Unplaced decks come last.
   */
  decks(courseId: string): DeckRow[] {
    return this.db
      .prepare(
        `SELECT d.* FROM decks d LEFT JOIN lectures l ON l.id = d.lecture_id
         WHERE d.course_id = ? ORDER BY l.n IS NULL, l.n, d.placed_at, d.created_at, d.id`,
      )
      .all(courseId) as unknown as DeckRow[];
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

  /**
   * Records the videos a student needs (U18). A KU's prerequisites are fixed at its first request, for every level
   * (U8): a link added later does not split the cache.
   */
  requestVideos(courseId: string, userId: string, requests: VideoRequest[]): number {
    if (!requests.length) return 0;
    const kus = new Map(this.fixtures(courseId).course.kus.map((k) => [k.id, k]));
    const firstPrereqs = this.db.prepare("SELECT prereq_ids FROM video_requests WHERE course_id = ? AND ku_id = ? ORDER BY requested_at LIMIT 1");
    const insert = this.db.prepare(
      "INSERT OR IGNORE INTO video_requests (course_id, ku_id, level, lecture_n, prereq_ids, first_user_id, requested_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    );
    let added = 0;
    for (const r of requests) {
      const ku = kus.get(r.ku_id);
      if (!ku) continue;
      const fixed = firstPrereqs.get(courseId, r.ku_id) as { prereq_ids: string } | undefined;
      added += Number(insert.run(courseId, r.ku_id, r.level, r.lecture_n, fixed?.prereq_ids ?? JSON.stringify(ku.prerequisites), userId, this.now()).changes);
    }
    return added;
  }

  /** After a student's request: the videos their state now needs (U18). */
  recordVideoNeeds(userId: string, state: DemoState): void {
    const courseId = this.courseOf(userId);
    if (!courseId) return;
    this.requestVideos(courseId, userId, videoRequests(this.fixtures(courseId).course, state.sittings, state.levels, state.made));
  }

  videoRequests(courseId: string): { ku_id: string; level: number; lecture_n: number; prereq_ids: string[]; status: string }[] {
    const rows = this.db
      .prepare("SELECT ku_id, level, lecture_n, prereq_ids, status FROM video_requests WHERE course_id = ? ORDER BY lecture_n, requested_at, ku_id, level")
      .all(courseId) as { ku_id: string; level: number; lecture_n: number; prereq_ids: string; status: string }[];
    return rows.map((r) => ({ ...r, prereq_ids: JSON.parse(r.prereq_ids) as string[] }));
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
