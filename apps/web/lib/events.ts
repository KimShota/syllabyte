import { appendEvent, getState } from "@/lib/store";
import { weekOf } from "@/lib/logic/time";
import { now } from "@/lib/store";
import type { AppEvent, EventVerb } from "@/lib/types";
import { uid } from "@/lib/util";

/**
 * One event shape and one vocabulary in every phase (plan Q20, §6.2). The API layer
 * logs domain events (answers, skips, decisions); components log UI interactions
 * (play, seek, sheets opened). Both go through here.
 */
function device(): AppEvent["context"]["device"] {
  return typeof window !== "undefined" && window.innerWidth >= 1024 ? "desktop" : "mobile";
}
function orientation(): AppEvent["context"]["orientation"] {
  return typeof window !== "undefined" && window.matchMedia?.("(orientation: landscape)").matches ? "landscape" : "portrait";
}

export function track(verb: EventVerb, object: { type: string; id?: string }, result?: Record<string, unknown>): void {
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
      screen: typeof window !== "undefined" ? window.location.pathname : "ssr",
      device: device(),
      orientation: orientation(),
      condition: s.condition,
      participant_code: s.participant_code,
      week: weekOf(now(), s.semester_start),
    },
    timestamp: new Date(now()).toISOString(),
  });
}
