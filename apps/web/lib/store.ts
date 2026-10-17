import { useEffect, useSyncExternalStore } from "react";
import { setEventEnv } from "@syllabyte/core/events";
import {
  flush, getEventVersion, getVersion, hydrate as hydrateCore, isHydrated, subscribe, subscribeEvents, type StorageAdapter,
} from "@syllabyte/core/store";

/**
 * The browser side of the shared store (packages/core/src/store.ts): localStorage under one key, a visit per
 * browser session, and the React hooks pages use. The state and its rules live in the core.
 */
export {
  appendEvent, flush, freshState, getState, isOnboarded, mutate, now, replaceState, resetState, subscribe,
} from "@syllabyte/core/store";

const KEY = "syllabyte.demo.v2";
const VISIT_KEY = "syllabyte.visit";

function currentVisitId(): string {
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

const browserStorage: StorageAdapter = {
  load: () => window.localStorage.getItem(KEY),
  save: (raw) => window.localStorage.setItem(KEY, raw),
  visitId: currentVisitId,
};

if (typeof window !== "undefined") {
  setEventEnv({
    screen: () => window.location.pathname,
    device: () => (window.innerWidth >= 1024 ? "desktop" : "mobile"),
    orientation: () => (window.matchMedia?.("(orientation: landscape)").matches ? "landscape" : "portrait"),
  });
}

let listening = false;

/** Called once on the client after mount. */
export function hydrate(): void {
  if (isHydrated()) return;
  void hydrateCore(browserStorage);
  if (listening) return;
  listening = true;
  window.addEventListener("pagehide", flush);
  document.addEventListener("visibilitychange", () => document.visibilityState === "hidden" && flush());
}

export function useEventCount(): number {
  return useSyncExternalStore(subscribeEvents, getEventVersion, () => 0);
}

export function useStoreVersion(): number {
  return useSyncExternalStore(subscribe, getVersion, () => 0);
}

/** true once localStorage has been read; pages wait for it before redirecting. */
export function useHydrated(): boolean {
  useStoreVersion();
  useEffect(() => hydrate(), []);
  return isHydrated();
}
