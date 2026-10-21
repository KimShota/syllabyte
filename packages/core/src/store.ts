import { startOfWeek } from "./logic/time";
import type { DemoState } from "./types";

/**
 * Phase 0 persisted state (plan Q6). The mock API is the only writer; screens read through the API client, so
 * Phase 1 can swap in FastAPI with no screen changes. The state is one JSON document, saved through the
 * StorageAdapter the app hands to `hydrate` (localStorage on the web, AsyncStorage on the phone). Until then,
 * and in tests, it lives in memory only.
 */
export interface StorageAdapter {
  /** The saved document, or null. May be async (AsyncStorage). */
  load(): string | null | Promise<string | null>;
  save(raw: string): void | Promise<void>;
  /** Id of the current visit: a browser session, or one launch of the app. The next-session cap counts per visit. */
  visitId(): string;
}

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
let storage: StorageAdapter | null = null;
const listeners = new Set<() => void>();
let persistTimer: ReturnType<typeof setTimeout> | null = null;

function notify() {
  version += 1;
  listeners.forEach((l) => l());
}

function write() {
  if (!storage) return;
  try {
    const done = storage.save(JSON.stringify(state));
    if (done instanceof Promise) done.catch(() => {});
  } catch {
    /* storage can be full or blocked; the app keeps working in memory */
  }
}

function persist() {
  if (!storage) return;
  if (persistTimer) clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    persistTimer = null;
    write();
  }, 40);
}

/** Write any pending change now. Apps call it when the page is hidden or the app goes to the background, so a tap
 *  followed by a quick exit never loses the last change. */
export function flush(): void {
  if (!persistTimer) return;
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

/** The data changed somewhere else (the server answered a write): wake every screen that reads through the API. */
/** The app was opened again: a new visit, so the next-session cap starts over and "Not now" expires (Q13). */
export function startVisit(id: string): void {
  if (state.visit.id === id) return;
  state = { ...state, visit: { id, handled: 0 } };
  persist();
  notify();
}

export function touch(): void {
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
  state.visit = { id: storage?.visitId() ?? "", handled: 0 };
  persist();
  notify();
}

function adopt(raw: string | null, visit: string): void {
  try {
    if (raw) {
      const parsed = JSON.parse(raw) as DemoState;
      if (parsed.v === 2) state = { ...freshState(), ...parsed };
    }
  } catch {
    /* corrupt storage: start fresh */
  }
  // A new visit (browser session, app launch): the next-session cap starts over (Q13).
  if (state.visit.id !== visit) state = { ...state, visit: { id: visit, handled: 0 } };
  hydrated = true;
  notify();
}

/**
 * Load the saved state once and save every later change through `adapter`. Synchronous when the adapter's load
 * is (the web), a promise otherwise (the phone). Later calls do nothing.
 */
export function hydrate(adapter: StorageAdapter): void | Promise<void> {
  if (storage) return;
  storage = adapter;
  const visit = adapter.visitId();
  let raw: ReturnType<StorageAdapter["load"]>;
  try {
    raw = adapter.load();
  } catch {
    raw = null;
  }
  if (raw instanceof Promise) return raw.then((r) => adopt(r, visit), () => adopt(null, visit));
  adopt(raw, visit);
}

/** true once the saved state has been read; screens wait for it before redirecting. */
export function isHydrated(): boolean {
  return hydrated;
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

export function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Bumped on every change; with `subscribe` it feeds React's useSyncExternalStore. */
export function getVersion(): number {
  return version;
}

export function subscribeEvents(l: () => void): () => void {
  eventListeners.add(l);
  return () => eventListeners.delete(l);
}

export function getEventVersion(): number {
  return eventVersion;
}
