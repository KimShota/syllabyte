import AsyncStorage from "@react-native-async-storage/async-storage";
import { AppState } from "react-native";
import { api } from "@syllabyte/core/api/client";
import { ApiError } from "@syllabyte/core/api/remote";
import type { Api } from "@syllabyte/core/api/types";
import { uid } from "@syllabyte/core/util";
import { createOutbox } from "./outbox";

const KEY = "syllabyte.learningOutbox.v1";

/** Learning writes that may wait for the network (state/outbox.ts): each is idempotent on the server. */
type Queued = "recordLearningPlayback" | "recordLearningAway" | "respondToLearningPrompt" | "finishLearningSession" | "dismissReflection"
  | "respondToMisconceptionClip";

let signedIn: () => boolean = () => true;

const box = createOutbox({
  load: () => AsyncStorage.getItem(KEY),
  save: (raw) => AsyncStorage.setItem(KEY, raw),
  call: (method, args) => (api as unknown as Record<string, (...a: unknown[]) => Promise<unknown>>)[method](...args),
  // unreachable or timed out (0), or the server failed (5xx): try again. A 401 waits for the next sign-in (which clears
  // the queue if it is another account's); anything else was refused and would be refused again.
  retryable: (e) => e instanceof ApiError && (e.status === 0 || e.status === 401 || e.status >= 500),
  canSend: () => signedIn(),
  later: (fn, ms) => {
    const t = setTimeout(fn, ms);
    return () => clearTimeout(t);
  },
  now: () => Date.now(),
  newId: () => uid("outbox"),
});

/** Sends a learning write now, or keeps it until it can be sent. Resolves with the answer when it went straight through. */
export function sendLearning<M extends Queued>(method: M, ...args: Parameters<Api[M]>): Promise<Awaited<ReturnType<Api[M]>> | undefined> {
  return box.send(method, args);
}

/** At launch: tells the outbox when it may send, and sends what an earlier run left whenever the app comes to the front. */
export function startLearningOutbox(isSignedIn: () => boolean): () => void {
  signedIn = isSignedIn;
  void box.flush();
  const sub = AppState.addEventListener("change", (s) => {
    if (s === "active") void box.flush();
  });
  return () => sub.remove();
}

export const flushLearningOutbox = (): Promise<void> => box.flush();
/** Sign-out: the waiting writes belong to the account that made them. */
export const clearLearningOutbox = (): Promise<void> => box.clear();
