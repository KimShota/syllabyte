import type { ClientEvent } from "../events";
import type { QuestionNeed } from "../types";
import type { AnalyzerMaterial, Api, CourseFilesView, CourseListItem, MyCourseView, UploadOrderEntry, UploadFile, UploadView } from "./types";

/**
 * The `Api` over HTTP to apps/server (plan/backend-plan.md): every method is `POST /api/rpc/<method>` with
 * `{ args }`, answered `{ result }` or `{ error }`. The server runs the same rules as the in-browser mock, so a
 * screen can't tell them apart.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    /** HTTP status; 0 when the server could not be reached */
    readonly status: number,
  ) {
    super(message);
  }
}

export interface BackendOptions {
  /** e.g. https://api.example.com, no trailing slash */
  base: string;
  /** the session token, or null when signed out */
  token(): string | null;
  /** one id per launch of the app: the next-session cap counts per visit */
  visit(): string;
  /** the server turned the session down: sign the student out */
  onUnauthorized(): void;
  /** a call that changes data finished: screens should refetch */
  onChanged(): void;
  /** whether the last request reached the server */
  onConnection(reachable: boolean): void;
  fetch?: typeof fetch;
  /** Native apps may use a file-aware fetch for multipart uploads. */
  uploadFetch?: typeof fetch;
  timeoutMs?: number;
}

/** Methods that only read (the rest may change data, so the screens refetch after them). */
const READS = /^(get|list|export)[A-Z]/;
/** Writes that no screen shows straight away (a playing video's observations, every few seconds): no refetch after them. */
const QUIET = new Set(["recordLearningPlayback", "recordLearningAway", "evaluateLearningBoundary", "respondToLearningPrompt", "keepLearningSessionOpen", "respondToMisconceptionClip"]);

export interface SignedIn {
  token: string;
  role: "student" | "instructor" | "researcher";
  participant_code: string;
  /** False for public sign-ups, whose account creation is not research consent. */
  study_participant?: boolean;
}

export function createBackend(o: BackendOptions) {
  const doFetch = o.fetch ?? fetch;

  async function request(path: string, body: unknown, auth: boolean): Promise<Record<string, unknown>> {
    const token = o.token();
    if (auth && !token) throw new ApiError("Sign in to continue", 401);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), o.timeoutMs ?? 15_000);
    let res: Response;
    try {
      res = await doFetch(`${o.base}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Visit": o.visit(), ...(auth ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch {
      o.onConnection(false);
      throw new ApiError("Can't reach the server", 0);
    } finally {
      clearTimeout(timer);
    }
    o.onConnection(true);
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.status === 401 && auth) {
      o.onUnauthorized();
      throw new ApiError("Sign in again", 401);
    }
    if (!res.ok) throw new ApiError(typeof data.error === "string" ? data.error : `The server said ${res.status}`, res.status);
    return data;
  }

  /** GET with the session; for the course routes. */
  async function get(path: string): Promise<Record<string, unknown>> {
    const token = o.token();
    if (!token) throw new ApiError("Sign in to continue", 401);
    const res = await doFetch(`${o.base}${path}`, { headers: { Authorization: `Bearer ${token}`, "X-Visit": o.visit() } }).catch(() => null);
    if (!res) {
      o.onConnection(false);
      throw new ApiError("Can't reach the server", 0);
    }
    o.onConnection(true);
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.status === 401) {
      o.onUnauthorized();
      throw new ApiError("Sign in again", 401);
    }
    if (!res.ok) throw new ApiError(typeof data.error === "string" ? data.error : `The server said ${res.status}`, res.status);
    return data;
  }

  /** Files as multipart/form-data under `field`. On a phone a file is its { uri, name, type }; in a browser, its Blob. */
  async function upload(path: string, field: string, files: UploadFile[], extra: Record<string, UploadFile[]> = {}): Promise<Record<string, unknown>> {
    const token = o.token();
    if (!token) throw new ApiError("Sign in to continue", 401);
    const form = new FormData();
    for (const [name, attachments] of Object.entries({ [field]: files, ...extra })) {
      for (const f of attachments) {
        if (f.file) form.append(name, f.file, f.name);
        else form.append(name, { uri: f.uri, name: f.name, type: f.mimeType ?? "application/octet-stream" } as unknown as Blob);
      }
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 180_000);
    let res: Response;
    try {
      res = await (o.uploadFetch ?? doFetch)(`${o.base}${path}`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "X-Visit": o.visit() }, body: form, signal: controller.signal });
    } catch (cause) {
      console.log("[SyllaByte] upload transport failed", `${o.base}${path}`, cause);
      o.onConnection(false);
      throw new ApiError("Can't reach the server", 0);
    } finally {
      clearTimeout(timer);
    }
    o.onConnection(true);
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.status === 401) {
      o.onUnauthorized();
      throw new ApiError("Sign in again", 401);
    }
    if (!res.ok) throw new ApiError(typeof data.error === "string" ? data.error : `The server said ${res.status}`, res.status);
    o.onChanged();
    return data;
  }

  const api = new Proxy({} as Api, {
    get: (_t, method) => {
      if (typeof method !== "string" || method === "then") return undefined;
      return async (...args: unknown[]) => {
        const data = await request(`/api/rpc/${method}`, { args }, true);
        if (!READS.test(method) && !QUIET.has(method)) o.onChanged();
        return data.result;
      };
    },
  });

  return {
    api,
    async requestEmailLink(email: string, redirectUrl: string, intent: "signin" | "signup" = "signin"): Promise<void> {
      await request("/api/auth/request-link", { email, redirectUrl, intent }, false);
    },
    async verifyEmailLink(ticket: string): Promise<SignedIn & { email: string }> {
      return (await request("/api/auth/verify-link", { ticket }, false)) as unknown as SignedIn & { email: string };
    },
    /** Emails a sign-in code. Always succeeds from the caller's side: the server never says who is enrolled. */
    async requestCode(email: string): Promise<void> {
      await request("/api/auth/request-code", { email }, false);
    },
    /** Trades the emailed code for a session token. Throws an ApiError (401) for a wrong or used code. */
    async verifyCode(email: string, code: string): Promise<SignedIn> {
      return (await request("/api/auth/verify", { email, code }, false)) as unknown as SignedIn;
    },
    async logout(): Promise<void> {
      await request("/api/session/logout", {}, true).catch(() => undefined);
    },
    async session(): Promise<{ email: string; role: SignedIn["role"]; participant_code: string; study_participant?: boolean }> {
      const token = o.token();
      if (!token) throw new ApiError("Sign in to continue", 401);
      const res = await doFetch(`${o.base}/api/session`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => null);
      if (!res) throw new ApiError("Can't reach the server", 0);
      if (res.status === 401) {
        o.onUnauthorized();
        throw new ApiError("Sign in again", 401);
      }
      return (await res.json()) as { email: string; role: SignedIn["role"]; participant_code: string; study_participant?: boolean };
    },
    /** Sends a batch of the phone's events; resolves with the ids the server acknowledged (stored now or before), or
     *  undefined from an older server that names none (it took the whole batch, and resending would store it twice). */
    async sendEvents(events: ClientEvent[]): Promise<string[] | undefined> {
      const data = await request("/api/events", { events, sent_at: Date.now() }, true);
      return Array.isArray(data.ids) ? data.ids.filter((id): id is string => typeof id === "string") : undefined;
    },
    /** The student's uploaded course and its slides (plan/slide-uploads-plan.md). */
    courses: {
      materials: async (): Promise<AnalyzerMaterial[]> => ((await get("/api/courses/materials")) as unknown as { materials: AnalyzerMaterial[] }).materials,
      mine: async (): Promise<MyCourseView> => (await get("/api/courses/mine")) as unknown as MyCourseView,
      /** every course the student is in, the one they are in now marked */
      list: async (): Promise<CourseListItem[]> => ((await get("/api/courses")) as unknown as { courses: CourseListItem[] }).courses,
      /** switches to one of their courses: every call after this one is about it (state, questions, videos) */
      activate: async (courseId: string): Promise<void> => {
        await request(`/api/courses/${courseId}/activate`, {}, true);
        o.onChanged();
      },
      /** the student has read why their last syllabus could not be read */
      syllabusErrorSeen: async (): Promise<void> => {
        await request("/api/courses/syllabus-error/seen", {}, true);
      },
      /** the syllabus: the course is created or joined once the server has read it (poll `mine`) */
      create: async (syllabus: UploadFile, slides: UploadFile[] = []): Promise<{ upload_id: string }> =>
        (await upload("/api/courses", "syllabus", [syllabus], { slides })) as unknown as { upload_id: string },
      addSlides: async (courseId: string, files: UploadFile[]): Promise<UploadView[]> =>
        ((await upload(`/api/courses/${courseId}/slides`, "files", files)) as unknown as { uploads: UploadView[] }).uploads,
      /** the student's own syllabus and slide files, for "Syllabus & Course Slides" */
      files: async (courseId: string): Promise<CourseFilesView> => (await get(`/api/courses/${courseId}/files`)) as unknown as CourseFilesView,
      /** a link (a path on the server) that opens one of the student's files for a few minutes, no sign-in needed */
      fileLink: async (courseId: string, fileId: string): Promise<string> =>
        ((await request(`/api/courses/${courseId}/files/${fileId}/link`, {}, true)) as unknown as { path: string }).path,
      uploads: async (courseId: string): Promise<UploadView[]> => ((await get(`/api/courses/${courseId}/uploads`)) as unknown as { uploads: UploadView[] }).uploads,
      confirmUploads: async (courseId: string, order: UploadOrderEntry[]): Promise<UploadView[]> => {
        const out = ((await request(`/api/courses/${courseId}/uploads/confirm`, { order }, true)) as unknown as { uploads: UploadView[] }).uploads;
        o.onChanged();
        return out;
      },
      /** a check is stuck on a question the worker could not write: try writing it again (V4) */
      retryQuestion: async (need: QuestionNeed): Promise<void> => {
        await request("/api/questions/retry", need, true);
        o.onChanged();
      },
    },
  };
}

export type Backend = ReturnType<typeof createBackend>;

/** Where the event queue keeps what is waiting, so a closed app or a long time offline loses nothing (AsyncStorage on the phone). */
export interface QueueStorage {
  load(): Promise<string | null>;
  save(raw: string): Promise<void>;
}

/**
 * Collects UI events and sends them in batches: when `max` are waiting, or `delayMs` after the first one
 * (plan/engagement-feedback-implementation-plan.md, "Reliable delivery"). Each event carries an id made when it happened;
 * an event leaves the queue only once the server acknowledges that id (`send` resolves with them), so a lost answer
 * means a resend, and the server stores a resent event once. With `storage` the queue survives the app closing. A batch
 * that fails is retried after a growing delay, and up to `keep` events wait; beyond that the oldest go, counted in
 * `dropped` (missing data the analysis should know about).
 *
 * `send` resolving with nothing (an older server) counts as acknowledging the whole batch.
 */
export function createEventQueue(
  send: (events: ClientEvent[]) => Promise<string[] | void>,
  o: { max?: number; delayMs?: number; keep?: number; storage?: QueueStorage; retryMs?: number[] } = {},
) {
  const max = o.max ?? 20;
  const delayMs = o.delayMs ?? 4000;
  const keep = o.keep ?? 500;
  const retryMs = o.retryMs ?? [5_000, 15_000, 60_000, 300_000];
  let queue: ClientEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;
  let sending: Promise<void> | null = null;
  let failures = 0;
  let dropped = 0;
  let loaded: Promise<void> | null = null;

  const load = () =>
    (loaded ??= (o.storage?.load() ?? Promise.resolve(null)).then(
      (raw) => {
        try {
          const saved = raw ? (JSON.parse(raw) as ClientEvent[]) : [];
          if (Array.isArray(saved)) queue = trim([...saved, ...queue]);
        } catch {
          /* unreadable: start empty */
        }
      },
      () => {},
    ));
  const persist = () => o.storage?.save(JSON.stringify(queue)).catch(() => {});
  function trim(q: ClientEvent[]): ClientEvent[] {
    if (q.length <= keep) return q;
    dropped += q.length - keep;
    return q.slice(-keep);
  }
  function schedule(ms: number) {
    if (timer) return;
    timer = setTimeout(() => {
      timer = null;
      void flush();
    }, ms);
  }

  async function flush(): Promise<void> {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (sending) return sending;
    sending = (async () => {
      await load();
      while (queue.length) {
        const batch = queue.slice(0, 200);
        let acked: Set<string> | null;
        try {
          const ids = await send(batch);
          acked = ids ? new Set(ids) : null;
        } catch {
          failures += 1;
          schedule(retryMs[Math.min(failures - 1, retryMs.length - 1)]);
          return;
        }
        // drop what the server acknowledged (all of the batch for an older server that names none); anything else in
        // the batch stays for the next try
        const sent = new Set(batch);
        queue = queue.filter((ev) => {
          if (!sent.has(ev)) return true; // came in while this batch was out
          if (acked === null || !ev.event_id) return false; // an older server, or an event it can't name: sent is all there is
          return !acked.has(ev.event_id); // kept until the server has it
        });
        void persist();
        if (acked && batch.every((ev) => ev.event_id && !acked!.has(ev.event_id))) {
          // nothing of it was acknowledged: back off as for a failure, rather than resending every few seconds
          failures += 1;
          schedule(retryMs[Math.min(failures - 1, retryMs.length - 1)]);
          return;
        }
        failures = 0;
        if (queue.length < max) break;
      }
      if (queue.length) schedule(delayMs);
    })().finally(() => {
      sending = null;
    });
    return sending;
  }

  return {
    push(ev: ClientEvent): void {
      queue = trim([...queue, ev]);
      void persist();
      if (queue.length >= max) void flush();
      else schedule(delayMs);
    },
    flush,
    /** Sends what an earlier run of the app left (call once at launch). */
    restore: (): Promise<void> => load().then(() => (queue.length ? flush() : undefined)),
    /** forget what is waiting (sign-out: the next student must not receive them) */
    clear(): void {
      queue = [];
      if (timer) clearTimeout(timer);
      timer = null;
      void persist();
    },
    size: () => queue.length,
    /** events lost because more than `keep` were waiting */
    dropped: () => dropped,
  };
}
