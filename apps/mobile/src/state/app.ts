/**
 * The phone side of the shared store (packages/core/src/store.ts): the core's state document saved in AsyncStorage,
 * one visit per launch, the event context, and the React hooks the screens use. Screens read and write the study
 * data only through the core's `api`, as on the web, so Phase 1 can swap in the backend.
 *
 * Every student who has the app has already agreed to take part in the study (consent is collected before they
 * get it), so the app records research consent itself; there is no consent screen.
 *
 * A few settings belong to this app alone (playback speed, "notify me", the first-run screens seen); they are kept
 * beside it under their own key.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AppState, Dimensions } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { api } from "@syllabyte/core/api/client";
import { setEventEnv } from "@syllabyte/core/events";
import { flush, getState, getVersion, hydrate, isHydrated, resetState, subscribe, type StorageAdapter } from "@syllabyte/core/store";
import { REMOTE } from "@/data/backend";
import { VISIT, endBackendSession, flushEvents, loadSession, useSession } from "./session";

const STATE_KEY = "syllabyte.demo.v2";
const PREFS_KEY = "syllabyte.mobile.prefs.v1";

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
  /** the student's profile photo: a file in the app's document folder (state/photo.ts), or null for the initials */
  photoUri: string | null;
}

const DEFAULT_PREFS: Prefs = { setupDone: false, speed: 1, notifyKuIds: [], photoUri: null };
let prefs: Prefs = DEFAULT_PREFS;
const prefListeners = new Set<() => void>();

function emitPrefs() {
  prefListeners.forEach((l) => l());
}

export function getPrefs(): Prefs {
  return prefs;
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

/** Consent was given before the student got the app (see the top of this file): record it once. */
async function recordConsent(): Promise<void> {
  if (getState().consent === null) await api.postConsent(true);
}

/**
 * Sign out. Alone, the demo starts over: study data and this app's settings alike. With a backend the student's data
 * stays on the server for their next sign-in, and only this phone's settings are cleared.
 */
export function signOut(): void {
  setPrefs(DEFAULT_PREFS);
  if (REMOTE) {
    void endBackendSession();
    return;
  }
  resetState();
  void recordConsent();
}

// ------------------------------------------------------------------ start-up

let ready = false;
let starting: Promise<void> | null = null;

/** Read what is saved on the phone once (and, with a backend, check the session); screens render after it. */
export function startApp(): Promise<void> {
  if (!starting) {
    starting = (REMOTE
      ? Promise.all([loadPrefs(), loadSession()]).then(() => undefined)
      : Promise.all([Promise.resolve(hydrate(phoneStorage)), loadPrefs()]).then(recordConsent)
    ).then(() => {
      ready = true;
      emitPrefs();
    });
    // write a pending change before the app is suspended
    AppState.addEventListener("change", (s) => {
      if (s !== "active") {
        flush();
        flushEvents();
      }
    });
  }
  return starting;
}

export function useAppReady(): boolean {
  useSyncExternalStore(subscribePrefs, () => ready, () => ready);
  useStoreVersion();
  return ready && (REMOTE || isHydrated());
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
  // with a backend nothing can be asked until the student is signed in
  const signedIn = useSession().status === "signedIn";
  const [data, setData] = useState<T | undefined>(undefined);
  const run = useRef(0);
  useEffect(() => {
    if (!signedIn) return;
    const id = ++run.current;
    fn().then(
      (d) => {
        if (id === run.current) setData(d);
      },
      // the server couldn't be reached or said no: keep what is on screen (the banner offers a retry)
      () => {},
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, signedIn, ...deps]);
  return signedIn ? data : undefined;
}
