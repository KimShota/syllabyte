/**
 * The phone side of the shared store (packages/core/src/store.ts): the core's state document saved in AsyncStorage,
 * one visit per launch, the event context, and the React hooks the screens use. Screens read and write the study
 * data only through the core's `api`, as on the web, so Phase 1 can swap in the backend.
 *
 * A few settings belong to this app alone (playback speed, "notify me", the first-run screens seen); they are kept
 * beside it under their own key.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AppState, Dimensions } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { setEventEnv } from "@syllabyte/core/events";
import { flush, getVersion, hydrate, isHydrated, resetState, subscribe, type StorageAdapter } from "@syllabyte/core/store";

const STATE_KEY = "syllabyte.demo.v2";
const PREFS_KEY = "syllabyte.mobile.prefs.v1";
/** a launch of the app is a visit (the next-session cap counts per visit) */
const VISIT = Math.random().toString(36).slice(2);

let screen = "";
/** The route on screen, for the events' context; the root layout keeps it current. */
export function setScreen(pathname: string): void {
  screen = pathname;
}

setEventEnv({
  screen: () => screen,
  device: () => "mobile",
  orientation: () => {
    const { width, height } = Dimensions.get("window");
    return width > height ? "landscape" : "portrait";
  },
});

const phoneStorage: StorageAdapter = {
  load: () => AsyncStorage.getItem(STATE_KEY),
  save: (raw) => AsyncStorage.setItem(STATE_KEY, raw),
  visitId: () => VISIT,
};

// ------------------------------------------------------------------ prefs

export const SPEEDS = [0.75, 1, 1.25, 1.5, 2] as const;
export type Speed = (typeof SPEEDS)[number];

/** "1.0x", "1.25x" */
export function speedLabel(s: Speed): string {
  return `${Number.isInteger(s) ? s.toFixed(1) : s}x`;
}

export interface Prefs {
  /** went through the welcome and the course analysis (the baseline check may still be open) */
  setupDone: boolean;
  speed: Speed;
  /** "Notify when ready" on a KU whose video is still being made */
  notifyKuIds: string[];
}

const DEFAULT_PREFS: Prefs = { setupDone: false, speed: 1, notifyKuIds: [] };
let prefs: Prefs = DEFAULT_PREFS;
const prefListeners = new Set<() => void>();

function emitPrefs() {
  prefListeners.forEach((l) => l());
}

export function setPrefs(patch: Partial<Prefs>): void {
  prefs = { ...prefs, ...patch };
  emitPrefs();
  AsyncStorage.setItem(PREFS_KEY, JSON.stringify(prefs)).catch(() => {});
}

export function toggleNotify(kuId: string): void {
  const on = prefs.notifyKuIds.includes(kuId);
  setPrefs({ notifyKuIds: on ? prefs.notifyKuIds.filter((id) => id !== kuId) : [...prefs.notifyKuIds, kuId] });
}

async function loadPrefs(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(PREFS_KEY);
    if (raw) prefs = { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<Prefs>) };
  } catch {
    /* corrupt or unavailable: defaults */
  }
}

function subscribePrefs(l: () => void) {
  prefListeners.add(l);
  return () => {
    prefListeners.delete(l);
  };
}

export function usePrefs(): Prefs {
  return useSyncExternalStore(subscribePrefs, () => prefs, () => prefs);
}

/** Sign out: the demo starts over, study data and this app's settings alike. */
export function signOut(): void {
  resetState();
  setPrefs(DEFAULT_PREFS);
}

// ------------------------------------------------------------------ start-up

let ready = false;
let starting: Promise<void> | null = null;

/** Read both saved documents once; screens render after it. */
export function startApp(): Promise<void> {
  if (!starting) {
    starting = Promise.all([Promise.resolve(hydrate(phoneStorage)), loadPrefs()]).then(() => {
      ready = true;
      emitPrefs();
    });
    // write a pending change before the app is suspended
    AppState.addEventListener("change", (s) => {
      if (s !== "active") flush();
    });
  }
  return starting;
}

export function useAppReady(): boolean {
  useSyncExternalStore(subscribePrefs, () => ready, () => ready);
  useStoreVersion();
  return ready && isHydrated();
}

// ------------------------------------------------------------------ queries

export function useStoreVersion(): number {
  return useSyncExternalStore(subscribe, getVersion, getVersion);
}

/**
 * Runs `fn` on mount and again whenever the store changes or `deps` change, like apps/web's useQuery. Keeps the
 * previous data while refetching, so lists don't flash empty.
 */
export function useQuery<T>(fn: () => Promise<T>, deps: readonly unknown[] = []): T | undefined {
  const version = useStoreVersion();
  const [data, setData] = useState<T | undefined>(undefined);
  const run = useRef(0);
  useEffect(() => {
    const id = ++run.current;
    fn().then((d) => {
      if (id === run.current) setData(d);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, ...deps]);
  return data;
}
