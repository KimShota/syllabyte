import { randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { extname, join } from "node:path";
import type { DeckKu, DeckResult } from "@syllabyte/core/logic/assemble";
import { tierDifficulty } from "@syllabyte/core/logic/kuProfile";
import type { CourseFilesView, LectureStateView as LectureState, UploadOrderEntry, UploadView } from "@syllabyte/core/api/types";
import type { Item, ItemTier, QuestionNeed } from "@syllabyte/core/types";
import type { Courses, DeckRow } from "./courses";
import type { Db } from "./db";

export type { LectureState, UploadView };

/**
 * Uploads (plan/slide-uploads-plan.md, revised 2026-10-21 as V1-V6): a student's syllabus creates or joins a shared
 * course, each slide file they confirm becomes one lecture of it, and the Python worker does the reading, the KUs and
 * the questions through a job queue.
 *
 *   syllabus    -> job 'syllabus'  -> join the course with the same key, or create it, keeping its topics as hints
 *   slide file  -> job 'deck_read' -> the same deck already in the course (free), an updated version of one (logged),
 *                                     or a new deck the reader says what it teaches (caps, U16)
 *   all read    -> job 'placement' -> the new decks' suggested titles and order among the lectures (V1)
 *   confirm     -> a lecture per new deck, where the student put it -> job 'deck' in course order (U3)
 *   deck done   -> job 'link_pass' when later lectures already have KUs (U7)
 *   a check     -> job 'question' for the (KU, tier) a student's check needs, before anything else (V4)
 */

export interface Caps {
  decksPerCourse: number;
  maxFileBytes: number;
  newDecksPerDay: number;
}
export const DEFAULT_CAPS: Caps = { decksPerCourse: 30, maxFileBytes: 25 * 1024 * 1024, newDecksPerDay: 15 };

const SYLLABUS_TYPES = new Set([".pdf", ".docx"]);
const SLIDE_TYPES = new Set([".pdf", ".pptx"]);
/** a worker that stopped answering: its job goes back to the queue */
const STALE_CLAIM_MS = 30 * 60 * 1000;
const MAX_ATTEMPTS = 2;
const DAY_MS = 24 * 60 * 60 * 1000;
/** a deck most of whose pages are already in a deck of the course is an updated version of it (V2) */
const UPDATED_VERSION_SHARE = 0.5;
const TIERS: ItemTier[] = ["basic", "applied", "advanced"];
/** a student's check is waiting for these */
const PRIORITY = { question: -10, deck_read: 1, placement: 2, syllabus: 0, deck: 10, link_pass: 50 } as const;

export class UploadError extends Error {
  constructor(
    message: string,
    readonly status: 400 | 403 | 404 | 409 | 413 = 400,
  ) {
    super(message);
  }
}

export type JobKind = "syllabus" | "deck_read" | "placement" | "deck" | "question" | "link_pass";
interface JobRow {
  id: string;
  kind: JobKind;
  target_id: string;
  course_id: string | null;
  status: "queued" | "claimed" | "done" | "failed";
  priority: number;
  attempts: number;
  claimed_at: number | null;
  created_at: number;
  error: string | null;
}

interface SyllabusUploadRow {
  id: string;
  user_id: string;
  file_name: string;
  file_path: string;
  status: "reading" | "joined" | "created" | "failed";
  course_id: string | null;
  error: string | null;
  created_at: number;
}

interface DeckUploadRow {
  id: string;
  user_id: string;
  course_id: string;
  file_name: string;
  file_path: string;
  byte_size: number;
  status: "reading" | "read" | "confirmed" | "failed";
  deck_id: string | null;
  outcome: UploadView["outcome"];
  created_at: number;
  error: string | null;
}

/** What the reader said a deck teaches (ingestion_agent/placement.py). */
interface DeckSummary {
  title: string;
  summary: string;
  lecture_number: number | null;
  is_lecture: boolean;
}

export interface DeckParse {
  page_count: number;
  first_title: string;
  pages: string[];
  page_keys?: string[];
  summary?: DeckSummary;
}

interface Suggestion {
  position: number;
  sure: boolean;
}

interface Schedule {
  course_code: string;
  course_name: string;
  lectures: { n: number; title: string; week: number | null }[];
}

/** What the worker gets when it claims a job. */
export interface ClaimedJob {
  id: string;
  kind: JobKind;
  payload: Record<string, unknown>;
  /** the job's file, for GET /api/worker/jobs/:id/file */
  file_name: string | null;
}

const parseOf = (deck: DeckRow): DeckParse => JSON.parse(deck.parse_json) as DeckParse;
const stem = (fileName: string) => fileName.replace(/\.[a-z0-9]+$/i, "");
const questionKey = (n: QuestionNeed) => `${n.ku_id}|${n.tier}`;

/**
 * Positions for new decks placed between two lectures (V1): evenly between `before` and `after`, or one apart after
 * the last lecture. Lecture numbers never change; only the order does.
 */
function spread(before: number, after: number | null, count: number): number[] {
  return Array.from({ length: count }, (_, k) => (after === null ? before + k + 1 : before + ((after - before) * (k + 1)) / (count + 1)));
}

export class Uploads {
  constructor(
    private db: Db,
    private courses: Courses,
    private filesDir: string,
    private caps: Caps = DEFAULT_CAPS,
    private now: () => number = Date.now,
  ) {
    mkdirSync(join(filesDir, "syllabi"), { recursive: true });
    mkdirSync(join(filesDir, "slides"), { recursive: true });
  }

  // ------------------------------------------------------------------ files

  private store(kind: "syllabi" | "slides", id: string, fileName: string, bytes: Uint8Array): string {
    const path = join(this.filesDir, kind, id + extname(fileName).toLowerCase());
    writeFileSync(path, bytes);
    return path;
  }

  // ------------------------------------------------------------------ syllabus

  /** A syllabus (U5): read by the worker, then the student joins or creates the course. One course per student (U4). */
  addSyllabus(userId: string, fileName: string, bytes: Uint8Array): { upload_id: string } {
    if (this.courses.courseOf(userId)) throw new UploadError("You already have a course.", 409);
    const pending = this.db.prepare("SELECT id FROM syllabus_uploads WHERE user_id = ? AND status = 'reading'").get(userId);
    if (pending) throw new UploadError("Your syllabus is still being read.", 409);
    const ext = extname(fileName).toLowerCase();
    if (!SYLLABUS_TYPES.has(ext)) throw new UploadError("A syllabus must be a PDF or Word (.docx) file.");
    if (bytes.byteLength > this.caps.maxFileBytes) throw new UploadError("That file is over 25 MB.", 413);
    const id = randomUUID();
    const path = this.store("syllabi", id, fileName, bytes);
    this.db
      .prepare("INSERT INTO syllabus_uploads (id, user_id, file_name, file_path, status, created_at) VALUES (?, ?, ?, ?, 'reading', ?)")
      .run(id, userId, fileName, path, this.now());
    this.enqueue("syllabus", id, null);
    return { upload_id: id };
  }

  /** The worker read the syllabus: is it a new course? A known one is joined right away (no model call). */
  syllabusKey(jobId: string, key: string): { is_new: boolean } {
    const up = this.syllabusUploadOf(jobId);
    const existing = this.courses.byKey(key);
    if (!existing) return { is_new: true };
    this.joinCourse(up, existing.id);
    this.finish(jobId);
    return { is_new: false };
  }

  private joinCourse(up: SyllabusUploadRow, courseId: string): void {
    this.courses.addMember(courseId, up.user_id);
    this.db.prepare("UPDATE syllabus_uploads SET status = 'joined', course_id = ? WHERE id = ?").run(courseId, up.id);
  }

  /** A new course: no lectures until slides are confirmed (V3); the syllabus's schedule is kept as topic hints. */
  private syllabusResult(jobId: string, r: { key: string; text: string; schedule?: Schedule }): void {
    const up = this.syllabusUploadOf(jobId);
    if (up.status !== "reading") return;
    const existing = this.courses.byKey(r.key);
    if (existing || !r.schedule) {
      // created by someone else meanwhile (or the worker skipped the schedule because it was not new)
      if (!existing) throw new Error("a syllabus result without a schedule for a new course");
      this.joinCourse(up, existing.id);
      return;
    }
    const name = r.schedule.course_name.trim() || stem(up.file_name);
    const courseId = this.courses.create({
      syllabusKey: r.key, code: r.schedule.course_code.trim(), name, syllabusText: r.text, syllabusPath: up.file_path, createdBy: up.user_id, status: "ready",
    });
    const topics = r.schedule.lectures.map((l) => l.title.trim()).filter(Boolean);
    this.db.prepare("UPDATE courses SET schedule_found = ?, topics_json = ? WHERE id = ?").run(topics.length ? 1 : 0, JSON.stringify(topics), courseId);
    this.courses.addMember(courseId, up.user_id);
    this.db.prepare("UPDATE syllabus_uploads SET status = 'created', course_id = ? WHERE id = ?").run(courseId, up.id);
  }

  private syllabusUploadOf(jobId: string): SyllabusUploadRow {
    const job = this.job(jobId);
    if (job.kind !== "syllabus") throw new UploadError("not a syllabus job");
    return this.db.prepare("SELECT * FROM syllabus_uploads WHERE id = ?").get(job.target_id) as unknown as SyllabusUploadRow;
  }

  /** The student's course status: none yet, their syllabus being read (or failed), or the course. */
  myCourse(userId: string) {
    const courseId = this.courses.courseOf(userId);
    if (!courseId) {
      const up = this.db.prepare("SELECT * FROM syllabus_uploads WHERE user_id = ? ORDER BY created_at DESC LIMIT 1").get(userId) as SyllabusUploadRow | undefined;
      if (up?.status === "reading") return { status: "reading" as const };
      if (up?.status === "failed") return { status: "failed" as const, error: up.error };
      return { status: "none" as const };
    }
    const c = this.courses.get(courseId)!;
    return { status: "ready" as const, course: { id: c.id, code: c.code, name: c.name, lectures: this.lectureStates(courseId) } };
  }

  /** The files this student uploaded to the course: their syllabus and every slide file, with what became of each. */
  myFiles(userId: string, courseId: string): CourseFilesView {
    this.member(userId, courseId);
    const syllabus = this.db
      .prepare("SELECT id, file_name, created_at FROM syllabus_uploads WHERE user_id = ? AND course_id = ? ORDER BY created_at DESC LIMIT 1")
      .get(userId, courseId) as { id: string; file_name: string; created_at: number } | undefined;
    const lectures = this.courses.lectures(courseId);
    const rank = new Map(lectures.map((l, i) => [l.id, i]));
    // rowid: files sent together keep the order they were sent in
    const rows = this.db.prepare("SELECT * FROM deck_uploads WHERE user_id = ? AND course_id = ? ORDER BY created_at, rowid").all(userId, courseId) as unknown as DeckUploadRow[];
    const slides = rows.map((u) => {
      const deck = u.deck_id ? this.courses.deck(u.deck_id) : null;
      const lecture = deck?.lecture_id ? lectures.find((l) => l.id === deck.lecture_id) : undefined;
      const state: CourseFilesView["slides"][number]["state"] =
        u.status === "reading"
          ? "reading"
          : u.status === "failed" || deck?.status === "failed"
            ? "failed"
            : u.outcome === "existing"
              ? "same_as"
              : u.outcome === "updated_version"
                ? "updated_version"
                : lecture
                  ? "lecture"
                  : "to_review";
      return {
        id: u.id,
        file_name: u.file_name,
        uploaded_at: u.created_at,
        state,
        lecture: lecture ? { n: lecture.n, title: lecture.title } : null,
        rank: deck?.lecture_id && state === "lecture" ? rank.get(deck.lecture_id)! : Infinity,
      };
    });
    // stable: files that are lectures in teaching order, the rest after them in upload order
    slides.sort((a, b) => a.rank - b.rank);
    return {
      syllabus: syllabus ? { id: syllabus.id, file_name: syllabus.file_name, uploaded_at: syllabus.created_at } : null,
      slides: slides.map(({ rank: _rank, ...s }) => s),
    };
  }

  /** One of this student's own uploaded files in the course (their syllabus or a slide file), or a 404. */
  myFile(userId: string, courseId: string, fileId: string): { id: string; name: string } {
    this.member(userId, courseId);
    const row =
      this.db.prepare("SELECT id, file_name FROM syllabus_uploads WHERE id = ? AND user_id = ? AND course_id = ?").get(fileId, userId, courseId) ??
      this.db.prepare("SELECT id, file_name FROM deck_uploads WHERE id = ? AND user_id = ? AND course_id = ?").get(fileId, userId, courseId);
    if (!row) throw new UploadError("No such file.", 404);
    const r = row as { id: string; file_name: string };
    return { id: r.id, name: r.file_name };
  }

  /** An uploaded file by its id, for a signed link (the link was only given to its owner). */
  uploadedFile(fileId: string): { path: string; name: string } | null {
    const row =
      this.db.prepare("SELECT file_path, file_name FROM syllabus_uploads WHERE id = ?").get(fileId) ??
      this.db.prepare("SELECT file_path, file_name FROM deck_uploads WHERE id = ?").get(fileId);
    if (!row) return null;
    const r = row as { file_path: string; file_name: string };
    return { path: r.file_path, name: r.file_name };
  }

  /** Each lecture in teaching order, with its deck's state (U14). */
  lectureStates(courseId: string): LectureState[] {
    const decks = this.courses.decks(courseId);
    return this.courses.lectures(courseId).map((l) => {
      const mine = decks.filter((d) => d.lecture_id === l.id);
      const state: LectureState["state"] = mine.some((d) => d.status === "ready") ? "ready" : mine.some((d) => d.status === "failed") ? "failed" : "analyzing";
      return { n: l.n, position: l.position ?? l.n, title: l.title, state, decks: mine.map((d) => ({ id: d.id, file_name: d.file_name, status: d.status })) };
    });
  }

  private member(userId: string, courseId: string) {
    const c = this.courses.get(courseId);
    if (!c || this.courses.courseOf(userId) !== courseId) throw new UploadError("Not your course.", 404);
    return c;
  }

  // ------------------------------------------------------------------ slide files

  /** Slide files for the student's course; each is read by the worker before it can be placed. */
  addSlides(userId: string, courseId: string, files: { name: string; bytes: Uint8Array }[]): UploadView[] {
    this.member(userId, courseId);
    if (files.length === 0) throw new UploadError("Choose at least one file.");
    for (const f of files) {
      const ext = extname(f.name).toLowerCase();
      if (ext === ".key") throw new UploadError(`${f.name}: Keynote files can't be read. In Keynote, choose File > Export To > PDF, then upload the PDF.`);
      if (!SLIDE_TYPES.has(ext)) throw new UploadError(`${f.name}: slides must be a PDF or PowerPoint (.pptx) file.`);
      if (f.bytes.byteLength > this.caps.maxFileBytes) throw new UploadError(`${f.name} is over 25 MB.`, 413);
    }
    const ids: string[] = [];
    for (const f of files) {
      const id = randomUUID();
      const path = this.store("slides", id, f.name, f.bytes);
      this.db
        .prepare("INSERT INTO deck_uploads (id, user_id, course_id, file_name, file_path, byte_size, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'reading', ?)")
        .run(id, userId, courseId, f.name, path, f.bytes.byteLength, this.now());
      this.enqueue("deck_read", id, courseId);
      ids.push(id);
    }
    return this.uploadViews(userId, courseId).filter((u) => ids.includes(u.id));
  }

  /** The deck of the course most of whose pages `keys` has: what a new upload would be an updated version of (V2). */
  private updatedVersionOf(courseId: string, keys: string[]): DeckRow | null {
    if (!keys.length) return null;
    let best: { deck: DeckRow; share: number } | null = null;
    for (const d of this.courses.decks(courseId)) {
      const theirs = new Set(parseOf(d).page_keys ?? []);
      if (!theirs.size) continue;
      const share = keys.filter((k) => theirs.has(k)).length / keys.length;
      if (share > UPDATED_VERSION_SHARE && (!best || share > best.share)) best = { deck: d, share };
    }
    return best?.deck ?? null;
  }

  /** The worker read a slide file: a deck already in the course, an updated version of one, or a new deck (U16). */
  private deckReadResult(jobId: string, r: { content_key: string } & DeckParse): void {
    const job = this.job(jobId);
    const up = this.db.prepare("SELECT * FROM deck_uploads WHERE id = ?").get(job.target_id) as unknown as DeckUploadRow;
    const same = this.db.prepare("SELECT id FROM decks WHERE course_id = ? AND content_key = ?").get(up.course_id, r.content_key) as { id: string } | undefined;
    if (same) {
      this.db.prepare("UPDATE deck_uploads SET status = 'read', deck_id = ?, outcome = 'existing' WHERE id = ?").run(same.id, up.id);
      return;
    }
    const older = this.updatedVersionOf(up.course_id, r.page_keys ?? []);
    if (older) {
      // not processed: everyone keeps the KUs and videos of the slides already in; the upload is logged (U12, V2)
      this.db.prepare("UPDATE deck_uploads SET status = 'read', deck_id = ?, outcome = 'updated_version' WHERE id = ?").run(older.id, up.id);
      return;
    }
    const inCourse = (this.db.prepare("SELECT COUNT(*) AS n FROM decks WHERE course_id = ?").get(up.course_id) as { n: number }).n;
    const today = (
      this.db.prepare("SELECT COUNT(*) AS n FROM decks WHERE first_user_id = ? AND created_at > ?").get(up.user_id, this.now() - DAY_MS) as { n: number }
    ).n;
    const over =
      inCourse >= this.caps.decksPerCourse
        ? `This course already has ${this.caps.decksPerCourse} slide files, the most it can have.`
        : today >= this.caps.newDecksPerDay
          ? `You can add up to ${this.caps.newDecksPerDay} new slide files a day. Try this one again tomorrow.`
          : null;
    if (over) {
      this.db.prepare("UPDATE deck_uploads SET status = 'failed', outcome = 'over_cap', error = ? WHERE id = ?").run(over, up.id);
      return;
    }
    const parse: DeckParse = { page_count: r.page_count, first_title: r.first_title, pages: r.pages, page_keys: r.page_keys ?? [], ...(r.summary ? { summary: r.summary } : {}) };
    // the deck takes the upload's id: the worker already cited its slides under that name
    this.db
      .prepare(
        "INSERT INTO decks (id, course_id, content_key, file_name, file_path, parse_json, status, first_user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, 'unplaced', ?, ?)",
      )
      .run(up.id, up.course_id, r.content_key, up.file_name, up.file_path, JSON.stringify(parse), up.user_id, this.now());
    this.db.prepare("UPDATE deck_uploads SET status = 'read', deck_id = ?, outcome = 'new' WHERE id = ?").run(up.id, up.id);
  }

  /** The new decks this student uploaded and nobody has placed yet. */
  private unplacedOf(userId: string, courseId: string): DeckRow[] {
    return this.db
      .prepare(
        `SELECT d.* FROM decks d JOIN deck_uploads u ON u.deck_id = d.id
         WHERE u.user_id = ? AND u.course_id = ? AND u.status = 'read' AND u.outcome = 'new' AND d.lecture_id IS NULL AND d.status = 'unplaced'
         ORDER BY u.created_at, u.rowid`,
      )
      .all(userId, courseId) as unknown as DeckRow[];
  }

  /** Once every file the student sent is read, one placement call orders the new ones (V1). */
  private maybePlace(userId: string, courseId: string): void {
    const reading = this.db.prepare("SELECT 1 FROM deck_uploads WHERE user_id = ? AND course_id = ? AND status = 'reading'").get(userId, courseId);
    if (reading) return;
    const decks = this.unplacedOf(userId, courseId);
    if (!decks.length) return;
    this.db.prepare(`UPDATE decks SET suggestion_json = NULL WHERE id IN (${decks.map(() => "?").join(",")})`).run(...decks.map((d) => d.id));
    const target = `${userId}|${courseId}`;
    const queued = this.db.prepare("SELECT 1 FROM jobs WHERE kind = 'placement' AND target_id = ? AND status = 'queued'").get(target);
    if (!queued) this.enqueue("placement", target, courseId);
  }

  private placementPayload(target: string) {
    const [userId, courseId] = target.split("|");
    const course = this.courses.get(courseId)!;
    const decks = this.courses.decks(courseId);
    const lectures = this.courses.lectures(courseId).map((l) => {
      const deck = decks.find((d) => d.lecture_id === l.id);
      return { id: `lecture:${l.n}`, title: l.title, summary: deck ? (parseOf(deck).summary?.summary ?? "") : "" };
    });
    const fresh = this.unplacedOf(userId, courseId).map((d) => {
      const p = parseOf(d);
      return { id: d.id, file_name: d.file_name, title: p.summary?.title || p.first_title || stem(d.file_name), summary: p.summary?.summary ?? "", lecture_number: p.summary?.lecture_number ?? null };
    });
    return { course_name: course.name, topics: JSON.parse(course.topics_json || "[]") as string[], lectures, new: fresh };
  }

  /** Positions for the new decks from the order the placement call gave (unknown ids are ignored). */
  private placementResult(j: JobRow, r: { order: string[]; unsure: string[] }): void {
    const [userId, courseId] = j.target_id.split("|");
    const decks = new Map(this.unplacedOf(userId, courseId).map((d) => [d.id, d]));
    const posOf = new Map(this.courses.lectures(courseId).map((l) => [`lecture:${l.n}`, l.position ?? l.n]));
    const order = (Array.isArray(r.order) ? r.order : []).filter((id) => posOf.has(id) || decks.has(id));
    for (const id of decks.keys()) if (!order.includes(id)) order.push(id);
    const unsure = new Set(Array.isArray(r.unsure) ? r.unsure : []);
    this.positionsFor(order, posOf, (id) => decks.has(id), (id, position) => {
      const p = parseOf(decks.get(id)!);
      const s: Suggestion = { position, sure: !unsure.has(id) && p.summary?.is_lecture !== false };
      this.db.prepare("UPDATE decks SET suggestion_json = ? WHERE id = ?").run(JSON.stringify(s), id);
    });
  }

  /** Walks `order` (lecture keys with positions, and new ids) and gives each new id a position between its neighbours. */
  private positionsFor(order: string[], posOf: Map<string, number>, isNew: (id: string) => boolean, set: (id: string, position: number) => void): void {
    let before = 0;
    let run: string[] = [];
    const flush = (after: number | null) => {
      spread(before, after, run.length).forEach((p, k) => set(run[k], p));
      run = [];
    };
    for (const id of order) {
      if (isNew(id)) run.push(id);
      else if (posOf.has(id)) {
        flush(posOf.get(id)!);
        before = posOf.get(id)!;
      }
    }
    flush(null);
  }

  /** The student's uploads not yet confirmed, and the ones that failed, for the review screen. */
  uploadViews(userId: string, courseId: string): UploadView[] {
    const lectures = this.courses.lectures(courseId);
    const rows = this.db
      .prepare("SELECT * FROM deck_uploads WHERE user_id = ? AND course_id = ? AND status IN ('reading', 'read', 'failed') ORDER BY created_at")
      .all(userId, courseId) as unknown as DeckUploadRow[];
    return rows.map((u) => {
      const deck = u.deck_id ? this.courses.deck(u.deck_id) : null;
      const parse = deck ? parseOf(deck) : null;
      const lecture = deck?.lecture_id ? lectures.find((l) => l.id === deck.lecture_id) : undefined;
      const canPlace = Boolean(deck && u.status === "read" && u.outcome === "new" && !deck.lecture_id && deck.status === "unplaced");
      const suggestion = canPlace && deck!.suggestion_json ? (JSON.parse(deck!.suggestion_json) as Suggestion) : null;
      return {
        id: u.id,
        file_name: u.file_name,
        status: u.status,
        outcome: u.outcome,
        error: u.error,
        deck: deck ? { id: deck.id, page_count: parse!.page_count, status: deck.status } : null,
        title: lecture?.title ?? (parse ? parse.summary?.title || parse.first_title || stem(u.file_name) : null),
        summary: parse?.summary?.summary ?? null,
        placed_lecture_n: lecture?.n ?? null,
        placing: u.status === "reading" || (canPlace && !suggestion),
        suggested_position: suggestion?.position ?? null,
        suggestion_sure: suggestion?.sure ?? false,
        can_place: canPlace,
      };
    });
  }

  /**
   * "Confirm all" (V1). `order`: the course's lectures, all of them in their order, and this student's new decks where
   * they go. Each new deck becomes a lecture at that place, titled as the student left it, and is queued for
   * processing; uploads that need no placing (already in the course, an updated version) are just confirmed.
   */
  confirmUploads(userId: string, courseId: string, order: UploadOrderEntry[]): UploadView[] {
    this.member(userId, courseId);
    const rows = this.db.prepare("SELECT * FROM deck_uploads WHERE user_id = ? AND course_id = ? AND status = 'read'").all(userId, courseId) as unknown as DeckUploadRow[];
    const placeable = new Map(
      rows.flatMap((u) => {
        const deck = u.deck_id ? this.courses.deck(u.deck_id) : null;
        return u.outcome === "new" && deck && !deck.lecture_id && deck.status === "unplaced" ? [[u.id, { up: u, deck }] as const] : [];
      }),
    );
    const lectures = this.courses.lectures(courseId);
    const given = order.filter((e): e is { lecture_n: number } => "lecture_n" in e).map((e) => e.lecture_n);
    if (given.join(",") !== lectures.map((l) => l.n).join(",")) {
      throw new UploadError("The course changed while you were placing your slides. Check the order and confirm again.", 409);
    }
    const titles = new Map<string, string>();
    const keys: string[] = [];
    for (const e of order) {
      if ("lecture_n" in e) {
        keys.push(`lecture:${e.lecture_n}`);
        continue;
      }
      if (keys.includes(e.upload_id)) throw new UploadError("A file is listed twice.");
      if (!placeable.has(e.upload_id)) continue; // placed by a classmate meanwhile, or nothing to place
      const p = parseOf(placeable.get(e.upload_id)!.deck);
      const title = (e.title ?? p.summary?.title ?? p.first_title ?? "").trim() || stem(placeable.get(e.upload_id)!.up.file_name);
      if (title.length > 120) throw new UploadError("A lecture title can be up to 120 characters.");
      titles.set(e.upload_id, title);
      keys.push(e.upload_id);
    }
    const missing = [...placeable.values()].find(({ up }) => !titles.has(up.id));
    if (missing) throw new UploadError(`Place ${missing.up.file_name} among the lectures.`);

    const posOf = new Map(lectures.map((l) => [`lecture:${l.n}`, l.position ?? l.n]));
    const positions = new Map<string, number>();
    this.positionsFor(keys, posOf, (id) => titles.has(id), (id, p) => positions.set(id, p));
    for (const key of keys) {
      if (!titles.has(key)) continue;
      const { up, deck } = placeable.get(key)!;
      const lecture = this.courses.addLecture(courseId, { title: titles.get(key)!, position: positions.get(key)! });
      this.db.prepare("UPDATE decks SET lecture_id = ?, status = 'queued', placed_at = ?, suggestion_json = NULL WHERE id = ?").run(lecture.id, this.now(), deck.id);
      this.enqueue("deck", deck.id, courseId);
    }
    for (const u of rows) this.db.prepare("UPDATE deck_uploads SET status = 'confirmed' WHERE id = ?").run(u.id);
    this.courses.touched(courseId);
    return this.uploadViews(userId, courseId);
  }

  // ------------------------------------------------------------------ questions written on demand (V4)

  /** After a student's request: queue the questions their checks need that nobody is writing yet. */
  requestQuestions(userId: string, needs: QuestionNeed[]): void {
    const courseId = this.courses.courseOf(userId);
    if (!courseId || !needs.length) return;
    for (const need of needs) {
      const busy = this.db
        .prepare("SELECT 1 FROM jobs WHERE course_id = ? AND kind = 'question' AND target_id = ? AND status IN ('queued', 'claimed', 'failed')")
        .get(courseId, questionKey(need));
      if (!busy) this.enqueue("question", questionKey(need), courseId);
    }
  }

  /** "Try again" on a check stuck on a question the worker gave up on. */
  retryQuestion(userId: string, need: QuestionNeed): void {
    const courseId = this.courses.courseOf(userId);
    if (!courseId) throw new UploadError("You have no course yet.", 404);
    this.db
      .prepare("UPDATE jobs SET status = 'queued', attempts = 0, error = NULL, finished_at = NULL WHERE course_id = ? AND kind = 'question' AND target_id = ? AND status = 'failed'")
      .run(courseId, questionKey(need));
    this.courses.touched(courseId);
  }

  /** The KU a question job is for, as the deck job returned it, and its deck. */
  private kuOf(courseId: string, kuId: string): { ku: DeckKu; deck: DeckRow } | null {
    for (const deck of this.courses.decks(courseId)) {
      if (deck.status !== "ready" || !deck.result_json) continue;
      const ku = (JSON.parse(deck.result_json) as DeckResult).kus.find((k) => k.id === kuId);
      if (ku) return { ku, deck };
    }
    return null;
  }

  private questionPayload(j: JobRow): Record<string, unknown> {
    const [kuId, tier] = j.target_id.split("|") as [string, ItemTier];
    const found = this.kuOf(j.course_id!, kuId);
    if (!found) throw new UploadError(`no KU ${kuId} in this course`, 404);
    const fx = this.courses.fixtures(j.course_id!);
    const entry = fx.course.kus.find((k) => k.id === kuId)!;
    const own = fx.items.filter((i) => i.ku_id === kuId && i.context === "assessment");
    const sameTier = own.filter((i) => i.tier === tier).length;
    const ids = new Set(fx.items.map((i) => i.id));
    let k = sameTier + 1;
    while (ids.has(`as-${kuId}-${tier}-${k}`)) k += 1;
    const rank = [...fx.course.kus.map((x) => x.id)].sort().indexOf(kuId);
    const titles = new Map(fx.course.kus.map((x) => [x.id, x.title]));
    return {
      deck_id: found.deck.id,
      item_id: `as-${kuId}-${tier}-${k}`,
      ku: found.ku,
      prereq_titles: entry.prerequisites.map((p) => titles.get(p)).filter(Boolean),
      tier,
      beta: tierDifficulty(entry, fx.items)[tier],
      // answers spread over A/B/C across the course, as a bank's are (assessment_agent/bank.py balance_positions)
      target_index: (rank + TIERS.indexOf(tier) + sameTier) % 3,
      avoid: own.map((i) => i.stem),
    };
  }

  private questionResult(j: JobRow, r: { item?: Item; flags?: unknown[] }): void {
    const [kuId, tier] = j.target_id.split("|");
    const item = r.item;
    if (!item || item.ku_id !== kuId || item.tier !== tier || item.context !== "assessment" || !Array.isArray(item.options) || item.options.length < 3) {
      throw new UploadError("a question result needs an assessment item on the job's KU and tier");
    }
    if (!(item.correct_index >= 0 && item.correct_index < item.options.length)) throw new UploadError("the keyed answer is not one of the options");
    const found = this.kuOf(j.course_id!, kuId);
    if (!found) return;
    if (this.db.prepare("SELECT 1 FROM questions WHERE id = ?").get(item.id)) return;
    this.courses.addQuestion(j.course_id!, found.deck.id, item, Array.isArray(r.flags) ? r.flags : []);
  }

  // ------------------------------------------------------------------ the job queue

  private enqueue(kind: JobKind, targetId: string, courseId: string | null): void {
    this.db
      .prepare("INSERT INTO jobs (id, kind, target_id, course_id, status, priority, created_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)")
      .run(randomUUID(), kind, targetId, courseId, PRIORITY[kind], this.now());
  }

  private job(id: string): JobRow {
    const j = this.db.prepare("SELECT * FROM jobs WHERE id = ?").get(id) as JobRow | undefined;
    if (!j) throw new UploadError("unknown job", 404);
    return j;
  }

  /**
   * A deck is processed only after every deck placed before it in the course order, so it sees their KUs (U3). Everything
   * else can run at once.
   */
  private claimable(j: JobRow): boolean {
    if (j.kind !== "deck") return true;
    const deck = this.courses.deck(j.target_id);
    if (!deck?.lecture_id) return false;
    // decks() is in course order; any deck ahead of this one still waiting holds it back
    const order = this.courses.decks(deck.course_id).filter((d) => d.lecture_id);
    const ahead = order.slice(0, order.findIndex((d) => d.id === deck.id));
    return !ahead.some((d) => d.status === "queued" || d.status === "processing");
  }

  /** The next job for the worker (only of `kinds` when given), with what it needs; null when there is nothing to do. */
  claim(kinds?: string[]): ClaimedJob | null {
    this.db
      .prepare("UPDATE jobs SET status = 'queued', claimed_at = NULL WHERE status = 'claimed' AND claimed_at < ?")
      .run(this.now() - STALE_CLAIM_MS);
    const queued = this.db.prepare("SELECT * FROM jobs WHERE status = 'queued' ORDER BY priority, created_at").all() as unknown as JobRow[];
    for (const j of queued) {
      if (kinds?.length && !kinds.includes(j.kind)) continue;
      if (!this.claimable(j)) continue;
      let payload: Record<string, unknown>;
      try {
        payload = this.payload(j);
      } catch (e) {
        // its KU or deck is gone (the researcher moved things): nothing to do
        this.db.prepare("UPDATE jobs SET status = 'failed', finished_at = ?, error = ? WHERE id = ?").run(this.now(), (e as Error).message, j.id);
        continue;
      }
      this.db.prepare("UPDATE jobs SET status = 'claimed', attempts = attempts + 1, claimed_at = ? WHERE id = ?").run(this.now(), j.id);
      if (j.kind === "deck") this.db.prepare("UPDATE decks SET status = 'processing' WHERE id = ?").run(j.target_id);
      return { id: j.id, kind: j.kind, payload, file_name: this.fileOf(j)?.name ?? null };
    }
    return null;
  }

  /** The file a job reads: the syllabus, the slide file, or the deck's file (for a question, its KU's deck). */
  fileOf(jobOrId: JobRow | string): { path: string; name: string } | null {
    const j = typeof jobOrId === "string" ? this.job(jobOrId) : jobOrId;
    if (j.kind === "syllabus") {
      const r = this.db.prepare("SELECT file_path, file_name FROM syllabus_uploads WHERE id = ?").get(j.target_id) as { file_path: string; file_name: string };
      return { path: r.file_path, name: r.file_name };
    }
    if (j.kind === "deck_read") {
      const r = this.db.prepare("SELECT file_path, file_name FROM deck_uploads WHERE id = ?").get(j.target_id) as { file_path: string; file_name: string };
      return { path: r.file_path, name: r.file_name };
    }
    if (j.kind === "deck") {
      const d = this.courses.deck(j.target_id)!;
      return { path: d.file_path, name: d.file_name };
    }
    if (j.kind === "question") {
      const found = this.kuOf(j.course_id!, j.target_id.split("|")[0]);
      return found ? { path: found.deck.file_path, name: found.deck.file_name } : null;
    }
    return null;
  }

  private kusOf(deck: DeckRow, lectureN: number) {
    const r = JSON.parse(deck.result_json!) as DeckResult;
    return r.kus.map((k) => ({ id: k.id, title: k.title, summary: k.summary, lecture_n: lectureN }));
  }

  private payload(j: JobRow): Record<string, unknown> {
    if (j.kind === "syllabus") return { upload_id: j.target_id };
    if (j.kind === "placement") return this.placementPayload(j.target_id);
    if (j.kind === "question") return this.questionPayload(j);
    const course = this.courses.get(j.course_id!)!;
    if (j.kind === "deck_read") {
      const up = this.db.prepare("SELECT file_name FROM deck_uploads WHERE id = ?").get(j.target_id) as { file_name: string };
      const known = this.courses.decks(course.id).map((d) => d.content_key);
      return { deck_name: j.target_id, file_name: up.file_name, course_name: course.name, known_keys: known };
    }
    const lectures = this.courses.lectures(course.id);
    const rank = new Map(lectures.map((l, i) => [l.id, i]));
    const ready = this.courses.decks(course.id).filter((d) => d.status === "ready" && d.result_json && d.lecture_id);
    if (j.kind === "deck") {
      const deck = this.courses.deck(j.target_id)!;
      const lecture = lectures.find((l) => l.id === deck.lecture_id)!;
      const before = ready.filter((d) => rank.get(d.lecture_id!)! < rank.get(lecture.id)!);
      return {
        deck_id: deck.id,
        course_name: course.name,
        syllabus_text: course.syllabus_text,
        lecture_n: rank.get(lecture.id)! + 1,
        lecture_title: lecture.title,
        earlier: before.flatMap((d) => this.kusOf(d, rank.get(d.lecture_id!)! + 1)),
        taken_ids: ready.flatMap((d) => (JSON.parse(d.result_json!) as DeckResult).kus.map((k) => k.id)),
      };
    }
    // link_pass: the target is the deck that arrived after later lectures were processed (U7)
    const deck = this.courses.deck(j.target_id)!;
    const at = rank.get(deck.lecture_id!)!;
    return {
      course_name: course.name,
      new_kus: this.kusOf(deck, at + 1),
      later_kus: ready.filter((d) => rank.get(d.lecture_id!)! > at).flatMap((d) => this.kusOf(d, rank.get(d.lecture_id!)! + 1)),
    };
  }

  /** The worker's result for a job. */
  complete(jobId: string, result: Record<string, unknown>): void {
    const j = this.job(jobId);
    // a syllabus of a known course is finished when its key arrives (syllabusKey)
    if (j.status === "done") return;
    if (j.status !== "claimed") throw new UploadError("That job is not claimed.", 409);
    if (j.kind === "syllabus") this.syllabusResult(jobId, result as { key: string; text: string; schedule?: Schedule });
    else if (j.kind === "deck_read") this.deckReadResult(jobId, result as unknown as { content_key: string } & DeckParse);
    else if (j.kind === "placement") this.placementResult(j, result as { order: string[]; unsure: string[] });
    else if (j.kind === "deck") this.deckResult(j, result as unknown as DeckResult);
    else if (j.kind === "question") this.questionResult(j, result as { item?: Item; flags?: unknown[] });
    else this.courses.addLinks(j.course_id!, ((result.links ?? []) as { ku_id: string; prereq_id: string }[]).filter((l) => l.ku_id && l.prereq_id));
    this.finish(jobId);
    if (j.kind === "deck_read") {
      const up = this.db.prepare("SELECT user_id, course_id FROM deck_uploads WHERE id = ?").get(j.target_id) as { user_id: string; course_id: string };
      this.maybePlace(up.user_id, up.course_id);
    }
  }

  private deckResult(j: JobRow, r: DeckResult): void {
    // no KUs is allowed: a deck with nothing to teach is a lecture with no check
    if (!Array.isArray(r.kus)) throw new UploadError("a deck result needs kus");
    const result: DeckResult = { kus: r.kus, items: Array.isArray(r.items) ? r.items : [] };
    this.courses.setDeckResult(j.target_id, result);
    const deck = this.courses.deck(j.target_id)!;
    const lectures = this.courses.lectures(deck.course_id);
    const rank = new Map(lectures.map((l, i) => [l.id, i]));
    const at = rank.get(deck.lecture_id!)!;
    const later = this.courses.decks(deck.course_id).some((d) => d.status === "ready" && d.lecture_id && rank.get(d.lecture_id)! > at);
    if (later) this.enqueue("link_pass", deck.id, deck.course_id);
  }

  private finish(jobId: string): void {
    this.db.prepare("UPDATE jobs SET status = 'done', finished_at = ?, error = NULL WHERE id = ?").run(this.now(), jobId);
  }

  /**
   * The worker could not do a job. `userMessage`: the file itself is the problem (unreadable, a scan): the student
   * sees it and it is not retried. Otherwise it is retried once, then shown as failed.
   */
  fail(jobId: string, error: string, userMessage?: string): void {
    const j = this.job(jobId);
    const final = Boolean(userMessage) || j.attempts >= MAX_ATTEMPTS;
    if (!final) {
      this.db.prepare("UPDATE jobs SET status = 'queued', claimed_at = NULL, error = ? WHERE id = ?").run(error, jobId);
      if (j.kind === "deck") this.db.prepare("UPDATE decks SET status = 'queued' WHERE id = ?").run(j.target_id);
      return;
    }
    this.db.prepare("UPDATE jobs SET status = 'failed', finished_at = ?, error = ? WHERE id = ?").run(this.now(), error, jobId);
    const shown = userMessage ?? "Something went wrong reading this file. The researcher has been told.";
    if (j.kind === "syllabus") this.db.prepare("UPDATE syllabus_uploads SET status = 'failed', error = ? WHERE id = ?").run(shown, j.target_id);
    else if (j.kind === "deck_read") {
      this.db.prepare("UPDATE deck_uploads SET status = 'failed', outcome = 'unreadable', error = ? WHERE id = ?").run(shown, j.target_id);
      const up = this.db.prepare("SELECT user_id, course_id FROM deck_uploads WHERE id = ?").get(j.target_id) as { user_id: string; course_id: string };
      this.maybePlace(up.user_id, up.course_id);
    } else if (j.kind === "placement") {
      // no suggestion: the new decks go after the last lecture in the order they were sent, for the student to check
      const [userId, courseId] = j.target_id.split("|");
      const last = this.courses.lectures(courseId).reduce((m, l) => Math.max(m, l.position ?? l.n), 0);
      this.unplacedOf(userId, courseId).forEach((d, k) => {
        this.db.prepare("UPDATE decks SET suggestion_json = ? WHERE id = ?").run(JSON.stringify({ position: last + k + 1, sure: false } satisfies Suggestion), d.id);
      });
    } else if (j.kind === "deck") {
      this.db.prepare("UPDATE decks SET status = 'failed', error = ? WHERE id = ?").run(shown, j.target_id);
      this.courses.touched(j.course_id!);
    } else if (j.kind === "question") this.courses.touched(j.course_id!);
  }

  /** Researcher: put a failed job back in the queue. */
  retry(jobId: string): void {
    const j = this.job(jobId);
    if (j.status !== "failed") throw new UploadError("Only a failed job can be retried.", 409);
    this.db.prepare("UPDATE jobs SET status = 'queued', attempts = 0, error = NULL, finished_at = NULL WHERE id = ?").run(jobId);
    if (j.kind === "deck") this.db.prepare("UPDATE decks SET status = 'queued', error = NULL WHERE id = ?").run(j.target_id);
    if (j.kind === "syllabus") this.db.prepare("UPDATE syllabus_uploads SET status = 'reading', error = NULL WHERE id = ?").run(j.target_id);
    if (j.kind === "deck_read") this.db.prepare("UPDATE deck_uploads SET status = 'reading', outcome = NULL, error = NULL WHERE id = ?").run(j.target_id);
    if (j.kind === "question") this.courses.touched(j.course_id!);
  }
}
