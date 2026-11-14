import { weekOf } from "./logic/time";
import { appendEvent, getState, now } from "./store";
import type { AppEvent, EventVerb } from "./types";
import { uid } from "./util";

/**
 * One event shape and one vocabulary in every phase (plan Q20, §6.2). The API layer
 * logs domain events (answers, skips, decisions); screens log UI interactions
 * (play, seek, sheets opened). Both go through here.
 */
export interface EventEnv {
  /** the route the student is on */
  screen(): string;
  /** the course the student is in: the one the app shows (the phone), or the one the request runs on (the server) */
  course(): string;
  device(): AppEvent["context"]["device"];
  orientation(): AppEvent["context"]["orientation"];
}

// the fixtures module sets `course` to the course it holds (fixtures.ts), so this module needs no fixtures to load
let env: EventEnv = { screen: () => "", course: () => "", device: () => "mobile", orientation: () => "portrait" };

/**
 * Events about the student, not about a course: they carry no course id, whichever course is open. Everything else
 * happened in a course (a video played, a question answered, a level changed) and says which.
 */
export const STUDENT_EVENT_VERBS: ReadonlySet<EventVerb> = new Set<EventVerb>([
  "consent_given", "data_downloaded", "study_shown", "study_started", "study_submitted", "study_snoozed",
]);

const courseOf = (verb: EventVerb): string | null => (STUDENT_EVENT_VERBS.has(verb) ? null : env.course());

/** Each app says where events happen (window on the web, the router and screen size on the phone). */
export function setEventEnv(next: Partial<EventEnv>): void {
  env = { ...env, ...next };
}

/** What the phone sends the server for one UI event; the server adds condition, week and participant code. */
export interface ClientEvent {
  verb: EventVerb;
  object: { type: string; id?: string };
  result?: Record<string, unknown>;
  screen: string;
  device: AppEvent["context"]["device"];
  orientation: AppEvent["context"]["orientation"];
  /** the course on screen when it happened, stamped on the phone because events are sent in batches, after the student may have switched */
  course_id?: string | null;
  /** made once when it happened and kept across retries: the server stores an event once and acknowledges it by this id
   *  (plan/engagement-feedback-implementation-plan.md, "Event envelope"). Absent on events from older phones. */
  event_id?: string;
  /** when it happened, in ms since the epoch by the phone's clock (events reach the server later, in batches) */
  occurred_at?: number;
}

/** What an event logged somewhere other than where it happened says about itself. */
export interface EventMeta {
  id: string;
  timestamp: string;
  received_at?: string;
  clock_anomaly?: boolean;
  legacy?: boolean;
}

let sink: ((ev: ClientEvent) => void) | null = null;

/** With the backend, events go to the server instead of the local state document. `null` goes back to local. */
export function setEventSink(next: ((ev: ClientEvent) => void) | null): void {
  sink = next;
}

export function track(verb: EventVerb, object: { type: string; id?: string }, result?: Record<string, unknown>): void {
  if (sink) {
    sink({ verb, object, result, screen: env.screen(), device: env.device(), orientation: env.orientation(), course_id: courseOf(verb),
      event_id: uid("ev"), occurred_at: now() });
    return;
  }
  record(verb, object, result, { id: uid("ev"), timestamp: new Date(now()).toISOString() });
}

/** Logs an event that happened elsewhere (the phone's), with its own id and time (the server's `trackClientEvents`). */
export function trackReceived(verb: EventVerb, object: { type: string; id?: string }, result: Record<string, unknown> | undefined, meta: EventMeta): void {
  record(verb, object, result, meta);
}

function record(verb: EventVerb, object: { type: string; id?: string }, result: Record<string, unknown> | undefined, meta: EventMeta): void {
  const s = getState();
  // Plan §6.3: decliners are not logged for research. In demo builds a facilitator can
  // leave logging on for usability sessions (hidden menu toggle, on by default).
  if (s.consent === "no_research" && !s.flags.log_declined) return;
  appendEvent({
    id: meta.id,
    verb,
    object,
    result,
    context: {
      screen: env.screen(),
      device: env.device(),
      orientation: env.orientation(),
      condition: s.condition,
      participant_code: s.participant_code,
      week: weekOf(now(), s.semester_start),
      course_id: courseOf(verb),
    },
    timestamp: meta.timestamp,
    ...(meta.received_at ? { received_at: meta.received_at } : {}),
    ...(meta.clock_anomaly ? { clock_anomaly: true } : {}),
    ...(meta.legacy ? { legacy: true } : {}),
  });
}
