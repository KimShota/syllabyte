/**
 * Signing in and the connection to the backend (apps/server), when there is one (data/backend.ts).
 *
 * The student signs in with the email their course gave SyllaByte and a code emailed to it. The session token lives
 * in the phone's secure storage, so they stay signed in; if the server ever turns it down they are signed out.
 * With a backend, every `api` call goes to the server, UI events are sent in batches, and the study data lives
 * there, not on the phone.
 */
import { useSyncExternalStore } from "react";
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { setApi, api } from "@syllabyte/core/api/client";
import { createBackend, createEventQueue, ApiError, type SignedIn } from "@syllabyte/core/api/remote";
import { setEventSink } from "@syllabyte/core/events";
import { touch } from "@syllabyte/core/store";
import { BACKEND_BASE, REMOTE } from "@/data/backend";

const TOKEN_KEY = "syllabyte.session.token";
const newVisitId = () => Math.random().toString(36).slice(2);
let visit = newVisitId();
/**
 * One per time the student opens the app (a launch, or a return from the background): the next-session cap counts per
 * visit, and a questionnaire put off with "Not now" comes back on the next one.
 */
export const currentVisit = (): string => visit;
/** The app was opened again: a new visit. Returns its id. */
export function startNewVisit(): string {
  visit = newVisitId();
  return visit;
}

export interface Session {
  /** `loading` until the saved token has been checked */
  status: "loading" | "signedOut" | "signedIn";
  email: string | null;
}

// Without a backend there is no sign-in: the app is always "signed in" to its own mock.
let session: Session = { status: REMOTE ? "loading" : "signedIn", email: null };
let reachable = true;
let token: string | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
};

function setSession(next: Session) {
  session = next;
  emit();
  touch();
}

export const useSession = (): Session => useSyncExternalStore(subscribe, () => session, () => session);
/** false while the last request to the server did not get through */
export const useReachable = (): boolean => useSyncExternalStore(subscribe, () => reachable, () => reachable);
export const getSession = (): Session => session;

// The token is kept in the keychain / keystore. The web build (used only for checking screens) has none.
const tokenStore = {
  get: async (): Promise<string | null> => (Platform.OS === "web" ? AsyncStorage.getItem(TOKEN_KEY) : SecureStore.getItemAsync(TOKEN_KEY)),
  set: async (t: string): Promise<void> => (Platform.OS === "web" ? AsyncStorage.setItem(TOKEN_KEY, t) : SecureStore.setItemAsync(TOKEN_KEY, t)),
  clear: async (): Promise<void> => (Platform.OS === "web" ? AsyncStorage.removeItem(TOKEN_KEY) : SecureStore.deleteItemAsync(TOKEN_KEY)),
};

const backend = BACKEND_BASE
  ? createBackend({
      base: BACKEND_BASE,
      token: () => token,
      visit: currentVisit,
      onUnauthorized: () => void endSession(),
      onChanged: touch,
      onConnection: (ok) => {
        if (ok !== reachable) {
          reachable = ok;
          emit();
        }
      },
    })
  : null;

/** The course and upload calls (plan/slide-uploads-plan.md); null without a backend. */
export const courseCalls = backend?.courses ?? null;

const events = backend ? createEventQueue(backend.sendEvents) : null;
if (backend && events) {
  setApi(backend.api);
  setEventSink(events.push);
}

/** Send any waiting events now (the app is going to the background). */
export function flushEvents(): void {
  void events?.flush();
}

async function endSession(): Promise<void> {
  token = null;
  events?.clear();
  await tokenStore.clear().catch(() => {});
  setSession({ status: "signedOut", email: null });
}

/** Every student agreed to take part before they got the app, so the app records research consent itself. */
async function ensureConsent(): Promise<void> {
  const me = await api.getMe();
  if (me.consent === null) await api.postConsent(true);
}

/** At launch: is the saved token still good? */
export async function loadSession(): Promise<void> {
  if (!backend) return;
  token = await tokenStore.get().catch(() => null);
  if (!token) {
    setSession({ status: "signedOut", email: null });
    return;
  }
  try {
    const who = await backend.session();
    setSession({ status: "signedIn", email: who.email });
    await ensureConsent();
  } catch (e) {
    // 401 already signed them out. If the server just can't be reached, keep the token and let them retry.
    if (e instanceof ApiError && e.status === 0) setSession({ status: "signedIn", email: null });
  }
}

export async function requestSignInCode(email: string): Promise<void> {
  await backend?.requestCode(email.trim());
}

/** Throws an ApiError for a wrong code, or for a server that can't be reached. */
export async function verifySignInCode(email: string, code: string): Promise<SignedIn> {
  if (!backend) throw new Error("no backend");
  const res = await backend.verifyCode(email.trim(), code.trim());
  token = res.token;
  await tokenStore.set(res.token).catch(() => {});
  setSession({ status: "signedIn", email: email.trim().toLowerCase() });
  await ensureConsent().catch(() => {});
  touch();
  return res;
}

export async function endBackendSession(): Promise<void> {
  if (!backend) return;
  await events?.flush();
  await backend.logout();
  await endSession();
}

/** Try the requests again (the "can't reach the server" banner). */
export function retryConnection(): void {
  touch();
}
