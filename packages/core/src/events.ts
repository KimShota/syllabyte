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
  device(): AppEvent["context"]["device"];
  orientation(): AppEvent["context"]["orientation"];
}

let env: EventEnv = { screen: () => "", device: () => "mobile", orientation: () => "portrait" };

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
}

let sink: ((ev: ClientEvent) => void) | null = null;

/** With the backend, events go to the server instead of the local state document. `null` goes back to local. */
export function setEventSink(next: ((ev: ClientEvent) => void) | null): void {
  sink = next;
}

export function track(verb: EventVerb, object: { type: string; id?: string }, result?: Record<string, unknown>): void {
  if (sink) {
    sink({ verb, object, result, screen: env.screen(), device: env.device(), orientation: env.orientation() });
    return;
  }
  const s = getState();
  // Plan §6.3: decliners are not logged for research. In demo builds a facilitator can
  // leave logging on for usability sessions (hidden menu toggle, on by default).
  if (s.consent === "no_research" && !s.flags.log_declined) return;
  appendEvent({
    id: uid("ev"),
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
    },
    timestamp: new Date(now()).toISOString(),
  });
}
