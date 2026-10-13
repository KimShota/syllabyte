import { useEffect, useSyncExternalStore } from "react";
import { startOfWeek } from "@/lib/logic/time";
import type { DemoState } from "@/lib/types";

/**
 * Phase 0 persisted state (plan Q6). The mock API is the only writer; components
 * read through the API client, so Phase 1 can swap in FastAPI with no component
 * changes. Everything lives in localStorage under one key.
 */
const KEY = "syllabyte.demo.v2";
const VISIT_KEY = "syllabyte.visit";

export function freshState(now = Date.now()): DemoState {
  return {
    v: 2,
    clock_offset_ms: 0,
    semester_start: startOfWeek(now),
    participant_code: null,
    consent: null,
    condition: "A",
    picked_own: false,
    sittings: {},
    levels: {},
    made: {},
    progress: {},
    level_updates: [],
    upcoming_lecture: null,
    responses: [],
    playlist: { entries: [], manual_order: null, built_at_week: 1 },
    watched: {},
    next_session: [],
    visit: { id: "", handled: 0 },
    claims: {},
    reports: [],
    notes: [],
    self_explanations: [],
    difficulty: {},
    review: {},
    added_videos: [],
    known_videos: [],
    archived_models: [],
    settings: { captions: true, weekly_email: true },
    events: [],
    study: {},
    flags: { log_declined: true },
  };
}

/** The student has a level for every KU: the Week 0 baseline is done, or they set their own levels. */
export function isOnboarded(s: DemoState): boolean {
  return Boolean(s.sittings.week0?.finished_at) || s.picked_own;
}

let state: DemoState = freshState();
let version = 0;
let hydrated = false;
const listeners = new Set<() => void>();
let persistTimer: ReturnType<typeof setTimeout> | null = null;

function notify() {
  version += 1;
  listeners.forEach((l) => l());
}

function write() {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* storage can be full or blocked; the app keeps working in memory */
  }
}

function persist() {
  if (typeof window === "undefined") return;
  if (persistTimer) clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    persistTimer = null;
    write();
  }, 40);
}

/** Write any pending change now. Called when the page is hidden or unloading, so a tap followed by
 *  a quick navigation (or closing the tab) never loses the last change. */
export function flush(): void {
  if (typeof window === "undefined" || !persistTimer) return;
  clearTimeout(persistTimer);
  persistTimer = null;
  write();
}

export function getState(): DemoState {
  return state;
}

/** Wall clock plus the demo's "Simulate next day" offset. */
export function now(): number {
  return Date.now() + state.clock_offset_ms;
}

export function mutate(fn: (s: DemoState) => void): void {
  fn(state);
  state = { ...state };
  persist();
  notify();
}

export function replaceState(next: DemoState): void {
  state = { ...next };
  persist();
  notify();
}

export function resetState(): void {
  const { participant_code, condition } = state;
  state = freshState();
  state.participant_code = participant_code;
  state.condition = condition;
  state.visit = { id: currentVisitId(), handled: 0 };
  persist();
  notify();
}

function currentVisitId(): string {
  if (typeof window === "undefined") return "";
  try {
    let id = window.sessionStorage.getItem(VISIT_KEY);
    if (!id) {
      id = Math.random().toString(36).slice(2);
      window.sessionStorage.setItem(VISIT_KEY, id);
    }
    return id;
  } catch {
    return "visit";
  }
}

/** Called once on the client after mount. */
export function hydrate(): void {
  if (hydrated) return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as DemoState;
      if (parsed.v === 2) state = { ...freshState(), ...parsed };
    }
  } catch {
    /* corrupt or blocked storage: start fresh */
  }
  // A new browser session is a new "visit": the next-session cap starts over (Q13).
  const visit = currentVisitId();
  if (state.visit.id !== visit) state = { ...state, visit: { id: visit, handled: 0 } };
  window.addEventListener("pagehide", flush);
  document.addEventListener("visibilitychange", () => document.visibilityState === "hidden" && flush());
  notify();
}

// Events have their own channel: the player logs seeks and pauses constantly, and
// that must not make every query refetch.
const eventListeners = new Set<() => void>();
let eventVersion = 0;

export function appendEvent(ev: DemoState["events"][number]): void {
  state.events.push(ev);
  persist();
  eventVersion += 1;
  eventListeners.forEach((l) => l());
}

export function useEventCount(): number {
  return useSyncExternalStore(
    (l) => {
      eventListeners.add(l);
      return () => eventListeners.delete(l);
    },
    () => eventVersion,
    () => 0,
  );
}

export function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useStoreVersion(): number {
  return useSyncExternalStore(subscribe, () => version, () => 0);
}

/** true once localStorage has been read; pages wait for it before redirecting. */
export function useHydrated(): boolean {
  useStoreVersion();
  useEffect(() => hydrate(), []);
  return hydrated;
}
