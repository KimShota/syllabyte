import type { ClientEvent } from "../events";
import type { Api } from "./types";

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
  };
}

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
