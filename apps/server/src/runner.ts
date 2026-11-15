import { mockApi, questionBankLectures, questionNeedsNow, syncPlaylistWithVideos } from "@syllabyte/core/api/mock";
import { FIX, currentCourseId, setFixtures } from "@syllabyte/core/fixtures";
import { setEventEnv, trackReceived, type EventMeta } from "@syllabyte/core/events";
import { freshState, getEventVersion, getQuietVersion, getState, getVersion, mutate, now, replaceState } from "@syllabyte/core/store";
import { startOfWeek } from "@syllabyte/core/logic/time";
import { uid } from "@syllabyte/core/util";
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
    const q = getQuietVersion();
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
      if (getVersion() !== v || getEventVersion() !== e || getQuietVersion() !== q) this.save(user.id, courseId);
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
      learning_sessions: d.learning_sessions ?? {}, misconception_requests: d.misconception_requests ?? [], responses: d.responses ?? [], notes: d.notes ?? [], self_explanations: d.self_explanations ?? [],
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
  learning_sessions: DemoState["learning_sessions"];
  misconception_requests: DemoState["misconception_requests"];
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
  /** the phone's id for it, kept across retries */
  event_id?: string;
  /** when it happened, by the phone's clock (ms) */
  occurred_at?: number;
}

const EVENT_ID = /^[A-Za-z0-9_-]{1,100}$/;
/** The longest a phone may hold an event and still have its time trusted. */
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

/**
 * When a phone event happened, by the server's clock (the study clock, so it lines up with the student's other events).
 * The phone's own clock may be wrong, so its time is not used directly: the event's age on that clock (`sentAt` minus
 * `occurred_at`, both the phone's) is taken from the receipt time, and a wrong phone clock cancels out. An impossible
 * age (negative, or held for over a month) is flagged and the receipt time used.
 */
export function eventTime(ev: ClientEvent, sentAt: number | undefined, receivedAt: number): Pick<EventMeta, "timestamp" | "clock_anomaly" | "legacy"> {
  if (typeof ev.occurred_at !== "number" || !Number.isFinite(ev.occurred_at)) return { timestamp: new Date(receivedAt).toISOString(), legacy: true };
  const age = typeof sentAt === "number" && Number.isFinite(sentAt) ? sentAt - ev.occurred_at : receivedAt - ev.occurred_at;
  if (!(age >= 0 && age <= MAX_AGE_MS)) return { timestamp: new Date(receivedAt).toISOString(), clock_anomaly: true };
  return { timestamp: new Date(receivedAt - age).toISOString() };
}

/**
 * Logs the phone's own events (play, seek, sheets) through the core, so each carries the server's condition, week and
 * code. An event's course is the one the phone says it happened in, if the student is in it (`isMember`); otherwise the
 * course this request runs on. The course never carries over to the next event, or to the API calls after these.
 *
 * Each event is stored once: one whose id the student's log already has (a retried batch) is skipped. Phone events are
 * research telemetry, so they are stored only while the student's consent is "research", checked now, when they arrive:
 * a packet that arrives after the student withdrew (and perhaps deleted their past events) restores nothing. Returns
 * the ids the phone may forget: every event with a valid id, stored now, stored before, or not stored at all, since
 * sending it again would change nothing.
 */
export function trackClientEvents(
  events: ClientEvent[],
  isMember: (courseId: string) => boolean = () => false,
  sentAt?: number,
): string[] {
  const seen = new Set(getState().events.map((e) => e.id));
  const acked: string[] = [];
  const receivedAt = now();
  const consented = getState().consent === "research";
  try {
    for (const ev of events) {
      const id = typeof ev.event_id === "string" && EVENT_ID.test(ev.event_id) ? ev.event_id : null;
      if (id) acked.push(id);
      if (!consented || (id && seen.has(id))) continue;
      const claimed = typeof ev.course_id === "string" && isMember(ev.course_id) ? ev.course_id : null;
      setEventEnv({
        screen: () => ev.screen ?? "", device: () => ev.device ?? "mobile", orientation: () => ev.orientation ?? "portrait",
        course: () => claimed ?? currentCourseId(),
      });
      trackReceived(ev.verb as never, ev.object, ev.result, {
        id: id ?? uid("ev"), received_at: new Date(receivedAt).toISOString(), ...eventTime(ev, sentAt, receivedAt),
      });
      if (id) seen.add(id);
    }
  } finally {
    setEventEnv({ course: currentCourseId });
  }
  return acked;
}
