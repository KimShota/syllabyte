import { randomUUID } from "node:crypto";
import type { CourseListItem } from "@syllabyte/core/api/types";
import { assembleCourse, type DeckResult } from "@syllabyte/core/logic/assemble";
import { videoRequests, type VideoRequest } from "@syllabyte/core/logic/videoRequests";
import type { DemoState, Fixtures, Item, ItemTier, Level, QuestionNeed, Video } from "@syllabyte/core/types";
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
  topics_json: string;
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
  /** teaching order (V1); null on rows from before it, which sort by n */
  position: number | null;
}

export interface DeckRow {
  id: string;
  course_id: string;
  lecture_id: string | null;
  content_key: string;
  file_name: string;
  file_path: string;
  parse_json: string;
  suggestion_json: string | null;
  status: "unplaced" | "queued" | "processing" | "ready" | "failed";
  result_json: string | null;
  first_user_id: string;
  created_at: number;
  placed_at: number | null;
  ready_at: number | null;
  error: string | null;
}

export class Courses {
  /** Signs the subject of a video's links ("media:<course>/<ku>/L<level>") into a query string; set by createApp. Without
   * it a video's urls carry no signature. */
  mediaSigner: (subject: string) => string = () => "";

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

  /** The course a syllabus belongs to: its own, or the one the researcher pointed it at (U17). */
  byKey(syllabusKey: string): CourseRow | null {
    const own = this.db.prepare("SELECT * FROM courses WHERE syllabus_key = ?").get(syllabusKey) as CourseRow | undefined;
    if (own) return own;
    const alias = this.db.prepare("SELECT course_id FROM syllabus_aliases WHERE syllabus_key = ?").get(syllabusKey) as { course_id: string } | undefined;
    return alias ? this.get(alias.course_id) : null;
  }

  /**
   * The course the student is in now: the one they chose (`setActive`) while they are still a member of it, else the
   * first they joined. Everything that is "the student's course" (their state, questions, videos) means this one.
   */
  courseOf(userId: string): string | null {
    const active = this.db
      .prepare("SELECT a.course_id FROM active_course a JOIN course_members m ON m.user_id = a.user_id AND m.course_id = a.course_id WHERE a.user_id = ?")
      .get(userId) as { course_id: string } | undefined;
    if (active) return active.course_id;
    const row = this.db.prepare("SELECT course_id FROM course_members WHERE user_id = ? ORDER BY joined_at, rowid LIMIT 1").get(userId) as
      | { course_id: string }
      | undefined;
    return row?.course_id ?? null;
  }

  /** Every course the student is in, the first they joined first. */
  coursesOf(userId: string): string[] {
    const rows = this.db.prepare("SELECT course_id FROM course_members WHERE user_id = ? ORDER BY joined_at, rowid").all(userId) as { course_id: string }[];
    return rows.map((r) => r.course_id);
  }

  /** Switches the student to one of their courses. */
  setActive(userId: string, courseId: string): void {
    if (!this.coursesOf(userId).includes(courseId)) throw new Error("not a member of that course");
    this.db
      .prepare("INSERT INTO active_course (user_id, course_id) VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET course_id = excluded.course_id")
      .run(userId, courseId);
  }

  /**
   * The student's courses for the Home screen: each with its lectures and how far they have got. Progress is the share of
   * the course's KUs they have watched, as the phone counts it for the course it shows.
   */
  courseList(userId: string): CourseListItem[] {
    const now = this.courseOf(userId);
    return this.coursesOf(userId).flatMap((id) => {
      const c = this.get(id);
      if (!c) return [];
      const lectures = this.lectures(id);
      const decks = this.decks(id);
      const ready = new Set(decks.filter((d) => d.status === "ready").map((d) => d.lecture_id));
      const kuIds = new Set(this.fixtures(id).course.kus.map((k) => k.id));
      const doc = this.db.prepare("SELECT json FROM course_state WHERE user_id = ? AND course_id = ?").get(userId, id) as { json: string } | undefined;
      const watched = doc ? Object.keys((JSON.parse(doc.json) as { watched?: Record<string, unknown> }).watched ?? {}).filter((k) => kuIds.has(k)).length : 0;
      return [
        {
          id, code: c.code, name: c.name, active: id === now, lectures: lectures.length, lectures_ready: lectures.filter((l) => ready.has(l.id)).length,
          progress: kuIds.size ? watched / kuIds.size : 0,
        },
      ];
    });
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

  /** Adds the student to the course, and it becomes the one they are in: they just chose it (a syllabus, or the facilitator). */
  addMember(courseId: string, userId: string): void {
    this.db.prepare("INSERT OR IGNORE INTO course_members (course_id, user_id, joined_at) VALUES (?, ?, ?)").run(courseId, userId, this.now());
    this.setActive(userId, courseId);
  }

  /** The course's lectures in teaching order (V1). */
  lectures(courseId: string): LectureRow[] {
    return this.db.prepare("SELECT * FROM lectures WHERE course_id = ? ORDER BY COALESCE(position, n), n").all(courseId) as unknown as LectureRow[];
  }

  /** A new lecture at `position` (default: last); its number is the next unused one, so no other lecture's changes. */
  addLecture(courseId: string, l: { title: string; position?: number; n?: number }, source: LectureRow["source"] = "upload"): LectureRow {
    const id = randomUUID();
    const max = this.db.prepare("SELECT MAX(n) AS n, MAX(COALESCE(position, n)) AS p FROM lectures WHERE course_id = ?").get(courseId) as { n: number | null; p: number | null };
    const n = l.n ?? (max.n ?? 0) + 1;
    const position = l.position ?? (max.p ?? 0) + 1;
    this.db.prepare("INSERT INTO lectures (id, course_id, n, title, week, source, position) VALUES (?, ?, ?, ?, NULL, ?, ?)").run(id, courseId, n, l.title, source, position);
    this.touched(courseId);
    return this.db.prepare("SELECT * FROM lectures WHERE id = ?").get(id) as unknown as LectureRow;
  }

  renameLecture(lectureId: string, title: string): void {
    const l = this.db.prepare("SELECT course_id FROM lectures WHERE id = ?").get(lectureId) as { course_id: string } | undefined;
    if (!l) throw new Error(`unknown lecture ${lectureId}`);
    this.db.prepare("UPDATE lectures SET title = ? WHERE id = ?").run(title, lectureId);
    this.touched(l.course_id);
  }

  /**
   * The course's decks in course order: by their lecture's place, then when they were placed, then id, so the order
   * never depends on timing ties. Unplaced decks come last.
   */
  decks(courseId: string): DeckRow[] {
    return this.db
      .prepare(
        `SELECT d.* FROM decks d LEFT JOIN lectures l ON l.id = d.lecture_id
         WHERE d.course_id = ? ORDER BY l.id IS NULL, COALESCE(l.position, l.n), l.n, d.placed_at, d.created_at, d.id`,
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

  /** Questions written on demand (V4), oldest first. */
  questions(courseId: string): { id: string; deck_id: string; ku_id: string; tier: ItemTier; item: Item }[] {
    const rows = this.db.prepare("SELECT id, deck_id, ku_id, tier, item_json FROM questions WHERE course_id = ? ORDER BY created_at, id").all(courseId) as {
      id: string; deck_id: string; ku_id: string; tier: ItemTier; item_json: string;
    }[];
    return rows.map((r) => ({ id: r.id, deck_id: r.deck_id, ku_id: r.ku_id, tier: r.tier, item: JSON.parse(r.item_json) as Item }));
  }

  addQuestion(courseId: string, deckId: string, item: Item, flags: unknown[]): void {
    this.db
      .prepare("INSERT INTO questions (id, course_id, deck_id, ku_id, tier, item_json, flags_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
      .run(item.id, courseId, deckId, item.ku_id, item.tier, JSON.stringify(item), JSON.stringify(flags), this.now());
    this.touched(courseId);
  }

  /** Questions the worker gave up on: a check waiting for one says so (V4). */
  questionFailures(courseId: string): QuestionNeed[] {
    const rows = this.db.prepare("SELECT target_id FROM jobs WHERE course_id = ? AND kind = 'question' AND status = 'failed'").all(courseId) as { target_id: string }[];
    return rows.map((r) => {
      const [ku_id, tier] = r.target_id.split("|");
      return { ku_id, tier: tier as ItemTier };
    });
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

  /** The course as the shared rules read it: its lectures, the processed decks, the questions written, the added links. */
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
      lectures: lectures.map((l) => ({ n: l.n, title: l.title, position: l.position ?? l.n })),
      decks,
      questions: this.questions(courseId).map((q) => q.item),
      question_failures: this.questionFailures(courseId),
      links,
    });
    this.cache.set(courseId, fx);
    return fx;
  }

  /**
   * The course a student's requests run against: theirs, or null for a student without one (they get the demo course).
   * It carries the videos made for them: per KU the one at the level their video was made at (D15) or, until one was,
   * the level their answers set, with the questions that video asks. A KU whose video at that level is not made yet has
   * none, and the app says it is being made.
   */
  fixturesFor(userId: string): Fixtures | null {
    const id = this.courseOf(userId);
    if (!id) return null;
    const fx = this.fixtures(id);
    const rows = this.db.prepare("SELECT ku_id, level, video_json, items_json FROM videos WHERE course_id = ?").all(id) as {
      ku_id: string;
      level: number;
      video_json: string;
      items_json: string;
    }[];
    if (!rows.length) return fx;
    const { levels, made } = this.studentLevels(userId);
    const videos: Video[] = [];
    const items: Item[] = [];
    for (const r of rows) {
      const want = made[r.ku_id] ?? levels[r.ku_id]?.level;
      if (want !== r.level) continue;
      const base = `/api/media/${id}/${r.ku_id}/${r.level}`;
      const sig = this.mediaSigner(`media:${id}/${r.ku_id}/L${r.level}`);
      const at = (name: string) => `${base}/${name}${sig ? `?${sig}` : ""}`;
      // one video per KU in a student's course, so its id is the KU's (as the demo course's are)
      videos.push({ ...(JSON.parse(r.video_json) as Video), id: r.ku_id, video_url: at("video.mp4"), poster_url: at("poster.jpg"), vtt_url: at("captions.vtt") });
      items.push(...(JSON.parse(r.items_json) as Item[]));
    }
    if (!videos.length) return fx;
    const have = new Set(videos.map((v) => v.ku_id));
    return {
      ...fx,
      course: { ...fx.course, kus: fx.course.kus.map((k) => (have.has(k.id) ? { ...k, video_id: k.id } : k)) },
      items: [...fx.items, ...items],
      videos,
    };
  }

  /** The levels a student's answers set and the levels their videos were made at, from their saved state. */
  private studentLevels(userId: string): { levels: Record<string, { level: Level }>; made: Record<string, Level> } {
    const courseId = this.courseOf(userId);
    const row = courseId === null ? undefined : (this.db.prepare("SELECT json FROM course_state WHERE user_id = ? AND course_id = ?").get(userId, courseId) as { json: string } | undefined);
    if (!row) return { levels: {}, made: {} };
    const s = JSON.parse(row.json) as Partial<DemoState>;
    return { levels: (s.levels ?? {}) as Record<string, { level: Level }>, made: s.made ?? {} };
  }
}
