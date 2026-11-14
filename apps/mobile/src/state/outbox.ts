/**
 * A small queue for learning writes nobody waits on (a prompt's answer, an absence, the end of a session, dismissing the
 * reflection, a page's last playback save), kept in storage so a network failure or a closed app does not lose them
 * (plan/engagement-feedback-implementation-plan.md, "Reliable delivery"). Plain TypeScript with its storage and network
 * passed in, so it can be tested without a phone; state/learningOutbox.ts wires the real ones.
 *
 * Every queued write must be idempotent on the server (a retried one is kept once): cumulative playback snapshots, prompt
 * answers where the first one stands, absences with the phone's id, ending a session, dismissing a reflection.
 * Writes are sent in order: one made while others wait joins the end of the line.
 */
export interface OutboxEntry {
  id: string;
  method: string;
  args: unknown[];
  queuedAt: number;
  attempts: number;
}

export interface OutboxDeps {
  load(): Promise<string | null>;
  save(raw: string): Promise<void>;
  /** sends one write; resolves with the server's answer */
  call(method: string, args: unknown[]): Promise<unknown>;
  /** worth trying again later (the server could not be reached, or failed), as opposed to refused */
  retryable(error: unknown): boolean;
  /** whether writes may be sent now (signed in) */
  canSend(): boolean;
  /** runs `fn` after `ms`; returns a cancel */
  later(fn: () => void, ms: number): () => void;
  now(): number;
  newId(): string;
}

/** The most writes kept; beyond it the oldest go (counted in `dropped`). */
export const OUTBOX_MAX = 200;
const BACKOFF_MS = [15_000, 30_000, 60_000, 120_000, 300_000];

export function createOutbox(d: OutboxDeps) {
  let queue: OutboxEntry[] = [];
  let ready: Promise<void> | null = null;
  let running: Promise<void> | null = null;
  let cancelRetry: (() => void) | null = null;
  let failures = 0;
  let dropped = 0;

  const loaded = () =>
    (ready ??= d.load().then(
      (raw) => {
        try {
          const parsed = raw ? (JSON.parse(raw) as OutboxEntry[]) : [];
          if (Array.isArray(parsed)) queue = [...parsed, ...queue];
        } catch {
          /* unreadable: start empty */
        }
      },
      () => {},
    ));
  const persist = () => d.save(JSON.stringify(queue)).catch(() => {});

  function enqueue(method: string, args: unknown[]) {
    queue.push({ id: d.newId(), method, args, queuedAt: d.now(), attempts: 0 });
    while (queue.length > OUTBOX_MAX) {
      queue.shift();
      dropped += 1;
    }
    void persist();
  }

  function scheduleRetry() {
    if (cancelRetry || !queue.length) return;
    const ms = BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)];
    cancelRetry = d.later(() => {
      cancelRetry = null;
      void flush();
    }, ms);
  }

  /** Sends what is waiting, oldest first; stops at the first write that can't get through yet. A call while a flush is
   *  running tries again once it ends (the network may have come back in between). */
  function flush(): Promise<void> {
    if (running) return running.then(flush);
    return (running = (async () => {
      await loaded();
      while (queue.length && d.canSend()) {
        const entry = queue[0];
        try {
          await d.call(entry.method, entry.args);
        } catch (e) {
          if (d.retryable(e)) {
            entry.attempts += 1;
            failures += 1;
            void persist();
            scheduleRetry();
            return;
          }
          // refused (invalid, or no longer applies): sending it again would be refused again
        }
        queue.shift();
        failures = 0;
        void persist();
      }
    })().finally(() => {
      running = null;
    }));
  }

  return {
    /**
     * Sends a write, or queues it to send later if the network fails. Resolves with the server's answer when it went
     * straight through, undefined when it was queued (or refused).
     */
    async send<T>(method: string, args: unknown[]): Promise<T | undefined> {
      await loaded();
      if (queue.length || !d.canSend()) {
        enqueue(method, args);
        void flush();
        return undefined;
      }
      try {
        return (await d.call(method, args)) as T;
      } catch (e) {
        if (d.retryable(e)) {
          enqueue(method, args);
          failures += 1;
          scheduleRetry();
        }
        return undefined;
      }
    },
    flush,
    /** Forgets everything waiting (sign-out: the queue belongs to the account that made it). */
    async clear(): Promise<void> {
      await loaded();
      queue = [];
      cancelRetry?.();
      cancelRetry = null;
      await persist();
    },
    size: () => queue.length,
    dropped: () => dropped,
  };
}

export type Outbox = ReturnType<typeof createOutbox>;
