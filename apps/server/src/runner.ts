import { mockApi } from "@syllabyte/core/api/mock";
import { FIX, setFixtures } from "@syllabyte/core/fixtures";
import { setEventEnv, track } from "@syllabyte/core/events";
import { freshState, getEventVersion, getState, getVersion, mutate, replaceState } from "@syllabyte/core/store";
import { startOfWeek } from "@syllabyte/core/logic/time";
import type { DemoState, Fixtures } from "@syllabyte/core/types";
import type { Db } from "./db";
import type { User } from "./auth";

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
    private opts: { semesterStart?: number; courseFor?: (userId: string) => Fixtures | null } = {},
  ) {}

  run<T>(user: User, visit: string | null, fn: () => Promise<T> | T): Promise<T> {
    const job = this.tail.then(() => this.exec(user, visit, fn));
    this.tail = job.catch(() => undefined);
    return job;
  }

  private async exec<T>(user: User, visit: string | null, fn: () => Promise<T> | T): Promise<T> {
    setFixtures(this.opts.courseFor?.(user.id) ?? FIX);
    replaceState(this.load(user));
    const v = getVersion();
    const e = getEventVersion();
    // the next-session cap counts per visit; the phone sends one id per app launch
    if (visit && getState().visit.id !== visit) {
      mutate((s) => {
        s.visit = { id: visit, handled: 0 };
      });
    }
    try {
      return await fn();
    } finally {
      if (getVersion() !== v || getEventVersion() !== e) this.save(user.id);
    }
  }

  /** The saved state of a student; a first visit starts a fresh one under their participant code. */
  private load(user: User): DemoState {
    const row = this.db.prepare("SELECT json FROM user_state WHERE user_id = ?").get(user.id) as { json: string } | undefined;
    const base = freshState();
    base.participant_code = user.participant_code;
    base.clock_offset_ms = this.clockOffset(user.id);
    if (this.opts.semesterStart) base.semester_start = startOfWeek(this.opts.semesterStart);
    if (!row) return base;
    const parsed = JSON.parse(row.json) as DemoState;
    return { ...base, ...parsed, participant_code: user.participant_code, clock_offset_ms: this.clockOffset(user.id) };
  }

  /** How far the facilitator has moved this student's study clock (src/clock.ts); 0 for everyone else. */
  private clockOffset(userId: string): number {
    const row = this.db.prepare("SELECT offset_ms FROM study_clock WHERE user_id = ?").get(userId) as { offset_ms: number } | undefined;
    return row?.offset_ms ?? 0;
  }

  private save(userId: string): void {
    this.db
      .prepare("INSERT INTO user_state (user_id, json, updated_at) VALUES (?, ?, ?) ON CONFLICT (user_id) DO UPDATE SET json = excluded.json, updated_at = excluded.updated_at")
      .run(userId, JSON.stringify(getState()), Date.now());
  }

  /** Every student's saved state, for the researcher export. */
  allStates(): DemoState[] {
    const rows = this.db.prepare("SELECT json FROM user_state").all() as { json: string }[];
    return rows.map((r) => JSON.parse(r.json) as DemoState);
  }
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
}

/** Logs the phone's own events (play, seek, sheets) through the core's `track`, so each carries the server's condition, week and code. */
export function trackClientEvents(events: ClientEvent[]): void {
  for (const ev of events) {
    setEventEnv({ screen: () => ev.screen ?? "", device: () => ev.device ?? "mobile", orientation: () => ev.orientation ?? "portrait" });
    track(ev.verb as never, ev.object, ev.result);
  }
}
