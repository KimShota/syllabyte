import { mockApi, questionBankLectures, questionNeedsNow, syncPlaylistWithVideos } from "@syllabyte/core/api/mock";
import { FIX, currentCourseId, setFixtures } from "@syllabyte/core/fixtures";
import { setEventEnv, track } from "@syllabyte/core/events";
import { freshState, getEventVersion, getState, getVersion, mutate, replaceState } from "@syllabyte/core/store";
import { startOfWeek } from "@syllabyte/core/logic/time";
import type { DemoState, Fixtures, QuestionNeed } from "@syllabyte/core/types";
import type { Db } from "./db";
import type { User } from "./auth";
import { NO_COURSE, StateStore } from "./state";

/**
 * Runs the shared app rules (packages/core) for one student at a time.
 *
 * The core keeps its state in one module-level document and its API methods run start to finish without waiting, so
 * serving a request is: load the student's saved document into the store, call the method, save the document if it
 * changed. Requests are queued one after another so two students' calls can never interleave and read each other's
 * state. This is the whole reason a lone Node process can serve everyone: the pilot is a few dozen students.
 */
export class StateRunner {
  private tail: Promise<unknown> = Promise.resolve();

  /**
   * `semesterStart`: the course's first Monday, for new students (default: the week they first sign in).
   * `courseFor`: the student's uploaded course (src/courses.ts); without one they get the demo course.
   */
  constructor(
    private db: Db,
    private opts: {
      semesterStart?: number;
      courseFor?: (userId: string) => Fixtures | null;
      /** the course a student is in now, for the researcher's export (one row per student) */
      courseIdOf?: (userId: string) => string | null;
      /** after each request of a student with a course that changed their state, e.g. to record the videos they need */
      after?: (userId: string, state: DemoState) => void;
      /** after every request of a student with a course: the questions their checks need written (V4) */
      needs?: (userId: string, needs: QuestionNeed[], lectures: number[]) => void;
    } = {},
  ) {
    this.store = new StateStore(db);
  }

  private store: StateStore;

  run<T>(user: User, visit: string | null, fn: () => Promise<T> | T, openedSitting?: string): Promise<T> {
    const job = this.tail.then(() => this.exec(user, visit, fn, openedSitting));
    this.tail = job.catch(() => undefined);
    return job;
  }

  private async exec<T>(user: User, visit: string | null, fn: () => Promise<T> | T, openedSitting?: string): Promise<T> {
    const course = this.opts.courseFor?.(user.id) ?? null;
    // a student's state is kept per course (src/state.ts): this request runs on the one they are in now
    const courseId = course?.course.id ?? NO_COURSE;
    setFixtures(course ?? FIX);
    replaceState(this.load(user, courseId));
    const v = getVersion();
    const e = getEventVersion();
    // a video made since their last request joins their playlist (core's syncPlaylistWithVideos); after the versions
    // are noted, so the change is saved
    if (course) syncPlaylistWithVideos();
    // the next-session cap counts per visit; the phone sends one id per app launch
    if (visit && getState().visit.id !== visit) {
      mutate((s) => {
        s.visit = { id: visit, handled: 0 };
      });
    }
    try {
      const out = await fn();
      if (course && this.opts.after && getVersion() !== v) this.opts.after(user.id, getState());
      if (course && this.opts.needs) this.opts.needs(user.id, questionNeedsNow(openedSitting), questionBankLectures(openedSitting));
      return out;
    } finally {
      if (getVersion() !== v || getEventVersion() !== e) this.save(user.id, courseId);
    }
  }

  /**
   * The saved state of a student in a course: their profile (consent, settings, the questionnaires, the event log) and
   * that course's document (levels, answers, playlist). A first visit, or a first visit to a course, starts a fresh
   * document under their participant code; the profile carries over between courses.
   */
  private load(user: User, courseId: string): DemoState {
    const profile = this.store.profile(user.id);
    const doc = this.store.course(user.id, courseId);
    const base = freshState();
    base.participant_code = user.participant_code;
    base.clock_offset_ms = this.clockOffset(user.id);
    if (this.opts.semesterStart) base.semester_start = startOfWeek(this.opts.semesterStart);
    if (!profile && !doc) return base;
    return { ...base, ...(doc ?? {}), ...(profile ?? {}), participant_code: user.participant_code, clock_offset_ms: this.clockOffset(user.id) } as DemoState;
  }

  /** How far the facilitator has moved this student's study clock (src/clock.ts); 0 for everyone else. */
  private clockOffset(userId: string): number {
    const row = this.db.prepare("SELECT offset_ms FROM study_clock WHERE user_id = ?").get(userId) as { offset_ms: number } | undefined;
    return row?.offset_ms ?? 0;
  }

  private save(userId: string, courseId: string): void {
    this.store.save(userId, courseId, getState());
  }

  /**
   * Each of a student's courses in their data download: its levels, answers, notes and sittings. A student's state is kept
   * per course (src/state.ts) and a request runs on one, so the core's own export covers only that one; this adds the
   * rest, so "download my data" has everything. Call it inside `run` for that student: the course they are in is read from
   * the state in memory, the others from what was saved. `describe` names a course (null for one that no longer exists).
   */
  courseExports(userId: string, courseIds: string[], describe: (courseId: string) => { code: string; name: string } | null): CourseExport[] {
    const active = this.opts.courseIdOf?.(userId) ?? NO_COURSE;
    const live = getState();
    const part = (d: Partial<DemoState>): Omit<CourseExport, "course_id" | "code" | "name" | "active"> => ({
      profile: { levels: d.levels ?? {}, made: d.made ?? {}, sittings: d.sittings ?? {} },
      responses: d.responses ?? [], notes: d.notes ?? [], self_explanations: d.self_explanations ?? [],
    });
    const out: CourseExport[] = courseIds.flatMap((id) => {
      const named = describe(id);
      // only its code and name: the record `describe` finds has the syllabus, a file path and who made the course
      return named ? [{ course_id: id, code: named.code, name: named.name, active: id === active, ...part(id === active ? live : (this.store.course(userId, id) ?? {})) }] : [];
    });
    // what they did on the demo course before they had one of their own
    const demo = this.store.course(userId, NO_COURSE);
    if (demo && !courseIds.includes(NO_COURSE)) out.push({ course_id: NO_COURSE, code: "", name: "Demo course", active: active === NO_COURSE, ...part(active === NO_COURSE ? live : demo) });
    return out;
  }

  /** One saved state per student, for the researcher export: the course they are in now. */
  allStates(): DemoState[] {
    return this.store.allStates((id) => this.opts.courseIdOf?.(id) ?? null);
  }
}

/** One course's part of a student's data download (`StateRunner.courseExports`). */
export interface CourseExport {
  course_id: string;
  code: string;
  name: string;
  /** the course they were in when they downloaded */
  active: boolean;
  profile: Pick<DemoState, "levels" | "made" | "sittings">;
  responses: DemoState["responses"];
  notes: DemoState["notes"];
  self_explanations: DemoState["self_explanations"];
}

/** Methods a student may call: the whole `Api` except the ones that read across students. */
const RESTRICTED = new Set(["exportStudyCsv"]);
export const RPC_METHODS: ReadonlySet<string> = new Set(Object.keys(mockApi).filter((k) => !RESTRICTED.has(k)));

export function callMethod(method: string, args: unknown[]): Promise<unknown> {
  if (!RPC_METHODS.has(method)) throw new Error(`unknown method ${method}`);
  const fn = (mockApi as unknown as Record<string, (...a: unknown[]) => Promise<unknown>>)[method];
  return fn.apply(mockApi, args);
}

export interface ClientEvent {
  verb: string;
  object: { type: string; id?: string };
  result?: Record<string, unknown>;
  screen?: string;
  device?: "mobile" | "desktop";
  orientation?: "portrait" | "landscape";
  /** the course on screen when it happened (the phone stamps it: events arrive in batches, after a student may have switched) */
  course_id?: string | null;
}

/**
 * Logs the phone's own events (play, seek, sheets) through the core's `track`, so each carries the server's condition, week
 * and code. An event's course is the one the phone says it happened in, if the student is in it (`isMember`); otherwise the
 * course this request runs on. The course never carries over to the next event, or to the API calls after these.
 */
export function trackClientEvents(events: ClientEvent[], isMember: (courseId: string) => boolean = () => false): void {
  try {
    for (const ev of events) {
      const claimed = typeof ev.course_id === "string" && isMember(ev.course_id) ? ev.course_id : null;
      setEventEnv({
        screen: () => ev.screen ?? "", device: () => ev.device ?? "mobile", orientation: () => ev.orientation ?? "portrait",
        course: () => claimed ?? currentCourseId(),
      });
      track(ev.verb as never, ev.object, ev.result);
    }
  } finally {
    setEventEnv({ course: currentCourseId });
  }
}
