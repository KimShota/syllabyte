import type { ClientEvent } from "../events";
import type { QuestionNeed } from "../types";
import type { Api, CourseFilesView, MyCourseView, UploadOrderEntry, UploadFile, UploadView } from "./types";

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
  timeoutMs?: number;
}

/** Methods that only read (the rest may change data, so the screens refetch after them). */
const READS = /^(get|list|export)[A-Z]/;

export interface SignedIn {
  token: string;
  role: "student" | "instructor" | "researcher";
  participant_code: string;
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
  async function upload(path: string, field: string, files: UploadFile[]): Promise<Record<string, unknown>> {
    const token = o.token();
    if (!token) throw new ApiError("Sign in to continue", 401);
    const form = new FormData();
    for (const f of files) {
      if (f.file) form.append(field, f.file, f.name);
      else form.append(field, { uri: f.uri, name: f.name, type: f.mimeType ?? "application/octet-stream" } as unknown as Blob);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 180_000);
    let res: Response;
    try {
      res = await doFetch(`${o.base}${path}`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "X-Visit": o.visit() }, body: form, signal: controller.signal });
    } catch {
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
        if (!READS.test(method)) o.onChanged();
        return data.result;
      };
    },
  });

  return {
    api,
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
    async session(): Promise<{ email: string; role: SignedIn["role"]; participant_code: string }> {
      const token = o.token();
      if (!token) throw new ApiError("Sign in to continue", 401);
      const res = await doFetch(`${o.base}/api/session`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => null);
      if (!res) throw new ApiError("Can't reach the server", 0);
      if (res.status === 401) {
        o.onUnauthorized();
        throw new ApiError("Sign in again", 401);
      }
      return (await res.json()) as { email: string; role: SignedIn["role"]; participant_code: string };
    },
    async sendEvents(events: ClientEvent[]): Promise<void> {
      await request("/api/events", { events }, true);
    },
    /** The student's uploaded course and its slides (plan/slide-uploads-plan.md). */
    courses: {
      mine: async (): Promise<MyCourseView> => (await get("/api/courses/mine")) as unknown as MyCourseView,
      /** the syllabus: the course is created or joined once the server has read it (poll `mine`) */
      create: async (syllabus: UploadFile): Promise<{ upload_id: string }> => (await upload("/api/courses", "syllabus", [syllabus])) as unknown as { upload_id: string },
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

/**
 * Collects UI events and sends them in batches: when `max` are waiting, or `delayMs` after the first one. A batch
 * that fails goes back in the queue (up to `keep` events), so a dropped connection loses nothing short of that.
 */
export function createEventQueue(send: (events: ClientEvent[]) => Promise<void>, o: { max?: number; delayMs?: number; keep?: number } = {}) {
  const max = o.max ?? 20;
  const delayMs = o.delayMs ?? 4000;
  const keep = o.keep ?? 500;
  let queue: ClientEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;
  let sending = false;

  async function flush(): Promise<void> {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (sending || !queue.length) return;
    sending = true;
    const batch = queue.slice(0, 200);
    queue = queue.slice(batch.length);
    try {
      await send(batch);
    } catch {
      queue = [...batch, ...queue].slice(-keep);
    } finally {
      sending = false;
    }
    if (queue.length >= max) void flush();
  }

  return {
    push(ev: ClientEvent): void {
      queue.push(ev);
      if (queue.length >= max) void flush();
      else if (!timer) timer = setTimeout(() => void flush(), delayMs);
    },
    flush,
    /** forget what is waiting (sign-out: the next student must not receive them) */
    clear(): void {
      queue = [];
      if (timer) clearTimeout(timer);
      timer = null;
    },
    size: () => queue.length,
  };
}
