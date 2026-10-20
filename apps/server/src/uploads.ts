import { randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { extname, join } from "node:path";
import type { DeckResult } from "@syllabyte/core/logic/assemble";
import type { Courses, DeckRow, LectureRow } from "./courses";
import type { Db } from "./db";

/**
 * Uploads (plan/slide-uploads-plan.md): a student's syllabus creates or joins a shared course, their slide files
 * become decks placed in its lectures, and the Python worker does the reading and processing through a job queue.
 *
 *   syllabus   -> job 'syllabus'  -> join the course with the same key, or create it with the lecture list (U2, U6)
 *   slide file -> job 'deck_read' -> the same deck already in the course (free), or a new deck (caps, U16)
 *   confirm    -> place new decks (U11, U12) -> job 'deck' per deck, one lecture after another (U3)
 *   deck done  -> job 'link_pass' when later lectures already have KUs (U7)
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

export class UploadError extends Error {
  constructor(
    message: string,
    readonly status: 400 | 403 | 404 | 409 | 413 = 400,
  ) {
    super(message);
  }
}

export type JobKind = "syllabus" | "deck_read" | "deck" | "link_pass";
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
  outcome: "new" | "existing" | "extra_part" | "updated_version" | "over_cap" | "unreadable" | null;
  created_at: number;
  error: string | null;
}

export interface DeckParse {
  page_count: number;
  first_title: string;
  pages: string[];
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

/** One row of the review screen (U13). */
export interface UploadView {
  id: string;
  file_name: string;
  status: DeckUploadRow["status"];
  outcome: DeckUploadRow["outcome"];
  error: string | null;
  deck: { id: string; first_title: string; page_count: number; status: DeckRow["status"] } | null;
  /** the deck's lecture when it is already placed (by whoever uploaded it first): fixed */
  placed_lecture_n: number | null;
  /** the suggested lecture for an unplaced deck; null when nothing matched */
  suggested_lecture_n: number | null;
  /** false: the suggestion is a guess the student must check (flagged) */
  suggestion_sure: boolean;
  /** this student may choose the lecture (the deck is not placed yet) */
  can_place: boolean;
}

export interface LectureState {
  n: number;
  title: string;
  week: number | null;
  state: "waiting" | "analyzing" | "ready" | "failed";
  decks: { id: string; file_name: string; status: DeckRow["status"] }[];
}

const STOP = new Set(["the", "and", "for", "with", "from", "into", "lecture", "week", "slides", "slide", "class", "part", "notes", "pdf", "pptx", "intro"]);
const words = (s: string) =>
  new Set(
    s
      .toLowerCase()
      .replace(/\.(pdf|pptx)$/i, "")
      .split(/[^a-z0-9]+/)
      .filter((w) => w.length >= 3 && !STOP.has(w) && !/^\d+$/.test(w)),
  );

/**
 * Which lecture a deck looks like (U13): a lecture or week number in the file name ("lecture03.pdf", "wk_3",
 * "L3 sorting.pdf") is sure; otherwise the lecture whose title shares the most words with the file name and the
 * first slide's title, sure when it covers half the title's words. Null when nothing matches.
 */
export function suggestLecture(fileName: string, firstTitle: string, lectures: Pick<LectureRow, "n" | "title" | "week">[]): { n: number | null; sure: boolean } {
  const num = /(?:^|[^a-z])(lecture|lec|week|wk|class|session|l|w)[\s_-]*0*(\d{1,2})(?!\d)/i.exec(fileName) ?? /^0*(\d{1,2})(?=[\s_.-])/.exec(fileName);
  if (num) {
    const kind = num.length > 2 ? num[1].toLowerCase() : "lecture";
    const n = Number(num[num.length - 1]);
    const byWeek = kind === "week" || kind === "wk" || kind === "w";
    const hit = byWeek ? lectures.find((l) => l.week === n) ?? lectures.find((l) => l.n === n) : lectures.find((l) => l.n === n);
    if (hit) return { n: hit.n, sure: true };
  }
  const have = new Set([...words(fileName), ...words(firstTitle)]);
  let best: { n: number; score: number } | null = null;
  for (const l of lectures) {
    const want = words(l.title);
    if (want.size === 0) continue;
    const score = [...want].filter((w) => have.has(w)).length / want.size;
    if (score > 0 && (!best || score > best.score)) best = { n: l.n, score };
  }
  return best ? { n: best.n, sure: best.score >= 0.5 } : { n: null, sure: false };
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
    this.enqueue("syllabus", id, null, 0);
    return { upload_id: id };
  }

  /** The worker read the syllabus: is it a new course? A known one is joined right away (no lecture list call). */
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

  private syllabusResult(jobId: string, r: { key: string; text: string; schedule?: Schedule }): void {
    const up = this.syllabusUploadOf(jobId);
    if (up.status !== "reading") return;
    const existing = this.courses.byKey(r.key);
    if (existing || !r.schedule) {
      // created by someone else meanwhile (or the worker skipped the list because it was not new)
      if (!existing) throw new Error("a syllabus result without a lecture list for a new course");
      this.joinCourse(up, existing.id);
      return;
    }
    const name = r.schedule.course_name.trim() || up.file_name.replace(/\.[a-z]+$/i, "");
    const courseId = this.courses.create({
      syllabusKey: r.key, code: r.schedule.course_code.trim(), name, syllabusText: r.text, syllabusPath: up.file_path, createdBy: up.user_id, status: "ready",
    });
    const lectures = r.schedule.lectures.map((l, i) => ({ n: i + 1, title: l.title, week: l.week ?? null }));
    if (lectures.length) this.courses.setLectures(courseId, lectures, "syllabus");
    this.db.prepare("UPDATE courses SET schedule_found = ? WHERE id = ?").run(lectures.length ? 1 : 0, courseId);
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
    return {
      status: "ready" as const,
      course: {
        id: c.id,
        code: c.code,
        name: c.name,
        schedule_found: c.schedule_found === 1,
        lectures_confirmed: c.lectures_confirmed_at !== null,
        /** this student created the course, so they confirm the lecture list (U11) */
        is_creator: c.created_by === userId,
        lectures: this.lectureStates(courseId),
      },
    };
  }

  /** Each lecture and its decks, for the roadmap's states (U14). */
  lectureStates(courseId: string): LectureState[] {
    const decks = this.courses.decks(courseId);
    return this.courses.lectures(courseId).map((l) => {
      const mine = decks.filter((d) => d.lecture_id === l.id);
      const state: LectureState["state"] = mine.some((d) => d.status === "ready")
        ? "ready"
        : mine.some((d) => d.status === "queued" || d.status === "processing")
          ? "analyzing"
          : mine.some((d) => d.status === "failed")
            ? "failed"
            : "waiting";
      return { n: l.n, title: l.title, week: l.week, state, decks: mine.map((d) => ({ id: d.id, file_name: d.file_name, status: d.status })) };
    });
  }

  /** The creator confirms or edits the lecture list read from the syllabus (U11); then it is fixed. */
  confirmLectures(userId: string, courseId: string, list?: { n: number; title: string; week: number | null }[]): void {
    const c = this.member(userId, courseId);
    if (c.created_by !== userId) throw new UploadError("Only the student who added this course can change its lectures.", 403);
    if (c.lectures_confirmed_at !== null) throw new UploadError("This course's lectures are already confirmed.", 409);
    if (list) {
      const titles = list.map((l) => String(l.title ?? "").trim());
      if (titles.some((t) => !t || t.length > 120)) throw new UploadError("Every lecture needs a title (up to 120 characters).");
      if (list.length > 60) throw new UploadError("A course can have at most 60 lectures.");
      this.courses.setLectures(
        courseId,
        list.map((l, i) => ({ n: i + 1, title: titles[i], week: Number.isInteger(l.week) ? l.week : null })),
        "syllabus",
      );
    }
    this.db.prepare("UPDATE courses SET lectures_confirmed_at = ? WHERE id = ?").run(this.now(), courseId);
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
      this.enqueue("deck_read", id, courseId, 1);
      ids.push(id);
    }
    return this.uploadViews(userId, courseId).filter((u) => ids.includes(u.id));
  }

  /** The worker read a slide file: the same deck already in the course, or a new one within the caps (U16). */
  private deckReadResult(jobId: string, r: { content_key: string } & DeckParse): void {
    const job = this.job(jobId);
    const up = this.db.prepare("SELECT * FROM deck_uploads WHERE id = ?").get(job.target_id) as unknown as DeckUploadRow;
    const same = this.db.prepare("SELECT id FROM decks WHERE course_id = ? AND content_key = ?").get(up.course_id, r.content_key) as { id: string } | undefined;
    if (same) {
      this.db.prepare("UPDATE deck_uploads SET status = 'read', deck_id = ?, outcome = 'existing' WHERE id = ?").run(same.id, up.id);
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
    const parse: DeckParse = { page_count: r.page_count, first_title: r.first_title, pages: r.pages };
    // the deck takes the upload's id: the worker already cited its slides under that name
    this.db
      .prepare(
        "INSERT INTO decks (id, course_id, content_key, file_name, file_path, parse_json, status, first_user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, 'unplaced', ?, ?)",
      )
      .run(up.id, up.course_id, r.content_key, up.file_name, up.file_path, JSON.stringify(parse), up.user_id, this.now());
    this.db.prepare("UPDATE deck_uploads SET status = 'read', deck_id = ?, outcome = 'new' WHERE id = ?").run(up.id, up.id);
  }

  /** The student's uploads not yet confirmed, and the ones that failed, for the review screen (U13). */
  uploadViews(userId: string, courseId: string): UploadView[] {
    const lectures = this.courses.lectures(courseId);
    const rows = this.db
      .prepare("SELECT * FROM deck_uploads WHERE user_id = ? AND course_id = ? AND status IN ('reading', 'read', 'failed') ORDER BY created_at")
      .all(userId, courseId) as unknown as DeckUploadRow[];
    return rows.map((u) => {
      const deck = u.deck_id ? this.courses.deck(u.deck_id) : null;
      const parse = deck ? (JSON.parse(deck.parse_json) as DeckParse) : null;
      const placed = deck?.lecture_id ? lectures.find((l) => l.id === deck.lecture_id)?.n ?? null : null;
      const guess = deck && !placed ? suggestLecture(u.file_name, parse!.first_title, lectures) : { n: null, sure: false };
      return {
        id: u.id,
        file_name: u.file_name,
        status: u.status,
        outcome: u.outcome,
        error: u.error,
        deck: deck ? { id: deck.id, first_title: parse!.first_title, page_count: parse!.page_count, status: deck.status } : null,
        placed_lecture_n: placed,
        suggested_lecture_n: guess.n,
        suggestion_sure: guess.sure,
        can_place: Boolean(deck && !deck.lecture_id && deck.status === "unplaced"),
      };
    });
  }

  /**
   * "Confirm all" (U13). Each read upload either is already placed (U11: nothing to choose), or is placed in the
   * chosen lecture. A lecture that already has slides needs the student's answer (U12): an extra part is placed and
   * processed, an updated version is logged and not processed. Without a lecture list (U2), choosing a number past
   * the end adds that lecture, titled from the deck's first slide.
   */
  confirmUploads(userId: string, courseId: string, choices: { upload_id: string; lecture_n?: number; kind?: "extra_part" | "updated_version" }[]): UploadView[] {
    const c = this.member(userId, courseId);
    for (const ch of choices) {
      const up = this.db.prepare("SELECT * FROM deck_uploads WHERE id = ? AND user_id = ?").get(ch.upload_id, userId) as DeckUploadRow | undefined;
      if (!up || up.course_id !== courseId) throw new UploadError("Unknown upload.", 404);
      if (up.status !== "read") continue;
      const deck = this.courses.deck(up.deck_id!)!;
      if (deck.lecture_id || deck.status !== "unplaced") {
        this.db.prepare("UPDATE deck_uploads SET status = 'confirmed' WHERE id = ?").run(up.id);
        continue;
      }
      if (!Number.isInteger(ch.lecture_n) || ch.lecture_n! < 1) throw new UploadError(`Choose a lecture for ${up.file_name}.`);
      let lecture = this.courses.lectures(courseId).find((l) => l.n === ch.lecture_n);
      if (!lecture) {
        const last = this.courses.lectures(courseId).at(-1)?.n ?? 0;
        if (c.schedule_found === 1 || ch.lecture_n !== last + 1) throw new UploadError(`There is no lecture ${ch.lecture_n}.`);
        const parse = JSON.parse(deck.parse_json) as DeckParse;
        this.courses.addLecture(courseId, { n: ch.lecture_n!, title: parse.first_title || up.file_name.replace(/\.[a-z]+$/i, ""), week: null }, "upload");
        lecture = this.courses.lectures(courseId).find((l) => l.n === ch.lecture_n)!;
      }
      const hasSlides = this.courses.decks(courseId).some((d) => d.lecture_id === lecture!.id);
      if (hasSlides && !ch.kind) throw new UploadError(`Lecture ${lecture.n} already has slides. Is ${up.file_name} an extra part, or an updated version of the same slides?`, 409);
      if (hasSlides && ch.kind === "updated_version") {
        this.db.prepare("UPDATE deck_uploads SET status = 'confirmed', outcome = 'updated_version' WHERE id = ?").run(up.id);
        continue;
      }
      this.db.prepare("UPDATE decks SET lecture_id = ?, status = 'queued', placed_at = ? WHERE id = ?").run(lecture.id, this.now(), deck.id);
      this.db
        .prepare("UPDATE deck_uploads SET status = 'confirmed', outcome = ? WHERE id = ?")
        .run(hasSlides ? "extra_part" : "new", up.id);
      this.enqueue("deck", deck.id, courseId, 10 + lecture.n);
      this.courses.touched(courseId);
    }
    return this.uploadViews(userId, courseId);
  }

  // ------------------------------------------------------------------ the job queue

  private enqueue(kind: JobKind, targetId: string, courseId: string | null, priority: number): void {
    this.db
      .prepare("INSERT INTO jobs (id, kind, target_id, course_id, status, priority, created_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)")
      .run(randomUUID(), kind, targetId, courseId, priority, this.now());
  }

  private job(id: string): JobRow {
    const j = this.db.prepare("SELECT * FROM jobs WHERE id = ?").get(id) as JobRow | undefined;
    if (!j) throw new UploadError("unknown job", 404);
    return j;
  }

  /**
   * A deck is processed only after every deck placed before it in the course order (earlier lectures, then earlier
   * decks of the same lecture), so it sees their KUs (U3). Everything else can run at once.
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

  /** The next job for the worker, with what it needs; null when there is nothing to do. */
  claim(): ClaimedJob | null {
    this.db
      .prepare("UPDATE jobs SET status = 'queued', claimed_at = NULL WHERE status = 'claimed' AND claimed_at < ?")
      .run(this.now() - STALE_CLAIM_MS);
    const queued = this.db.prepare("SELECT * FROM jobs WHERE status = 'queued' ORDER BY priority, created_at").all() as unknown as JobRow[];
    for (const j of queued) {
      if (!this.claimable(j)) continue;
      this.db.prepare("UPDATE jobs SET status = 'claimed', attempts = attempts + 1, claimed_at = ? WHERE id = ?").run(this.now(), j.id);
      if (j.kind === "deck") this.db.prepare("UPDATE decks SET status = 'processing' WHERE id = ?").run(j.target_id);
      return { id: j.id, kind: j.kind, payload: this.payload(j), file_name: this.fileOf(j)?.name ?? null };
    }
    return null;
  }

  /** The file a job reads: the syllabus, the slide file, or the deck's file. */
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
    return null;
  }

  private kusOf(deck: DeckRow, lectureN: number) {
    const r = JSON.parse(deck.result_json!) as DeckResult;
    return r.kus.map((k) => ({ id: k.id, title: k.title, summary: k.summary, lecture_n: lectureN }));
  }

  private payload(j: JobRow): Record<string, unknown> {
    if (j.kind === "syllabus") return { upload_id: j.target_id };
    if (j.kind === "deck_read") return { deck_name: j.target_id };
    const course = this.courses.get(j.course_id!)!;
    const lectures = this.courses.lectures(course.id);
    const nOf = new Map(lectures.map((l) => [l.id, l.n]));
    const ready = this.courses.decks(course.id).filter((d) => d.status === "ready" && d.result_json && d.lecture_id);
    if (j.kind === "deck") {
      const deck = this.courses.deck(j.target_id)!;
      const lecture = lectures.find((l) => l.id === deck.lecture_id)!;
      // decks placed before this one: earlier lectures, and earlier parts of this lecture (U10)
      const before = ready.filter((d) => nOf.get(d.lecture_id!)! <= lecture.n);
      return {
        deck_id: deck.id,
        course_name: course.name,
        syllabus_text: course.syllabus_text,
        lecture_n: lecture.n,
        lecture_title: lecture.title,
        earlier: before.flatMap((d) => this.kusOf(d, nOf.get(d.lecture_id!)!)),
        taken_ids: ready.flatMap((d) => (JSON.parse(d.result_json!) as DeckResult).kus.map((k) => k.id)),
      };
    }
    // link_pass: the target is the deck that arrived after later lectures were processed (U7)
    const deck = this.courses.deck(j.target_id)!;
    const n = nOf.get(deck.lecture_id!)!;
    return {
      course_name: course.name,
      new_kus: this.kusOf(deck, n),
      later_kus: ready.filter((d) => nOf.get(d.lecture_id!)! > n).flatMap((d) => this.kusOf(d, nOf.get(d.lecture_id!)!)),
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
    else if (j.kind === "deck") this.deckResult(j, result as unknown as DeckResult);
    else this.courses.addLinks(j.course_id!, ((result.links ?? []) as { ku_id: string; prereq_id: string }[]).filter((l) => l.ku_id && l.prereq_id));
    this.finish(jobId);
  }

  private deckResult(j: JobRow, r: DeckResult): void {
    if (!Array.isArray(r.kus) || !Array.isArray(r.items) || r.kus.length === 0) throw new UploadError("a deck result needs kus and items");
    const result: DeckResult = { kus: r.kus, items: r.items };
    this.courses.setDeckResult(j.target_id, result);
    const deck = this.courses.deck(j.target_id)!;
    const lectures = this.courses.lectures(deck.course_id);
    const nOf = new Map(lectures.map((l) => [l.id, l.n]));
    const n = nOf.get(deck.lecture_id!)!;
    const later = this.courses.decks(deck.course_id).some((d) => d.status === "ready" && d.lecture_id && nOf.get(d.lecture_id)! > n);
    if (later) this.enqueue("link_pass", deck.id, deck.course_id, 50);
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
    else if (j.kind === "deck_read")
      this.db.prepare("UPDATE deck_uploads SET status = 'failed', outcome = 'unreadable', error = ? WHERE id = ?").run(shown, j.target_id);
    else if (j.kind === "deck") {
      this.db.prepare("UPDATE decks SET status = 'failed', error = ? WHERE id = ?").run(shown, j.target_id);
      this.courses.touched(j.course_id!);
    }
  }

  /** Researcher: put a failed job back in the queue. */
  retry(jobId: string): void {
    const j = this.job(jobId);
    if (j.status !== "failed") throw new UploadError("Only a failed job can be retried.", 409);
    this.db.prepare("UPDATE jobs SET status = 'queued', attempts = 0, error = NULL, finished_at = NULL WHERE id = ?").run(jobId);
    if (j.kind === "deck") this.db.prepare("UPDATE decks SET status = 'queued', error = NULL WHERE id = ?").run(j.target_id);
    if (j.kind === "syllabus") this.db.prepare("UPDATE syllabus_uploads SET status = 'reading', error = NULL WHERE id = ?").run(j.target_id);
    if (j.kind === "deck_read") this.db.prepare("UPDATE deck_uploads SET status = 'reading', outcome = NULL, error = NULL WHERE id = ?").run(j.target_id);
  }
}
