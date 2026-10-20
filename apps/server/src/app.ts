import { Hono, type Context } from "hono";
import { bodyLimit } from "hono/body-limit";
import { cors } from "hono/cors";
import { studyCsv } from "@syllabyte/core/logic/instruments";
import { Auth, type User } from "./auth";
import { advanceClock, advanceToModuleEnd, getClock, resetClock } from "./clock";
import { readFileSync } from "node:fs";
import type { Courses } from "./courses";
import type { Db } from "./db";
import { RPC_METHODS, StateRunner, callMethod, trackClientEvents, type ClientEvent } from "./runner";
import { UploadError, type Uploads } from "./uploads";

export interface Deps {
  db: Db;
  auth: Auth;
  runner: StateRunner;
  /** Uploaded courses (plan/slide-uploads-plan.md); the runner was given the same store. */
  courses: Courses;
  uploads: Uploads;
  /** The upload worker's shared secret (SYLLABYTE_WORKER_TOKEN); without one the worker routes are off. */
  workerToken?: string;
  /** Browsers only (the phone app doesn't need it): the origin allowed to call, e.g. the web build in development. */
  corsOrigin?: string;
}

type Env = { Variables: { user: User; token: string } };

const MAX_EVENTS = 200;
const isObject = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);

async function json(c: Context): Promise<Record<string, unknown>> {
  try {
    const body = await c.req.json();
    return isObject(body) ? body : {};
  } catch {
    return {};
  }
}

/** Everything the phone calls, under /api. Built without a socket so tests can use `app.request`. */
export function createApp({ db, auth, runner, courses, uploads, workerToken, corsOrigin }: Deps): Hono<Env> {
  const app = new Hono<Env>();
  if (corsOrigin) app.use("/api/*", cors({ origin: corsOrigin, allowHeaders: ["Authorization", "Content-Type", "X-Visit"], allowMethods: ["GET", "POST", "OPTIONS"] }));
  // slide and syllabus files are checked one by one (25 MB each, src/uploads.ts); everything else is small
  const isUpload = (path: string) => /^\/api\/courses(\/[^/]+\/slides)?$/.test(path);
  const small = bodyLimit({ maxSize: 512 * 1024, onError: (c) => c.json({ error: "too large" }, 413) });
  const files = bodyLimit({ maxSize: 160 * 1024 * 1024, onError: (c) => c.json({ error: "Those files are too large together. Upload fewer at a time." }, 413) });
  app.use("*", (c, next) => (isUpload(c.req.path) ? files(c, next) : small(c, next)));

  app.get("/api/health", (c) => c.json({ ok: true }));

  // ---- sign-in
  app.post("/api/auth/request-code", async (c) => {
    const { email } = await json(c);
    // the same answer for every address, so nobody can tell who is enrolled
    if (typeof email === "string") {
      try {
        await auth.requestCode(email);
      } catch (e) {
        console.error("sending the sign-in code failed:", e);
      }
    }
    return c.json({ ok: true });
  });

  app.post("/api/auth/verify", async (c) => {
    const { email, code } = await json(c);
    const ok = typeof email === "string" && typeof code === "string" ? auth.verifyCode(email, code) : null;
    if (!ok) return c.json({ error: "That code didn't work. Ask for a new one." }, 401);
    return c.json({ token: ok.token, role: ok.user.role, participant_code: ok.user.participant_code });
  });

  // ---- everything below needs a session
  const needUser = async (c: Context<Env>, next: () => Promise<void>) => {
    const header = c.req.header("Authorization") ?? "";
    const token = header.startsWith("Bearer ") ? header.slice(7) : "";
    const user = token ? auth.authenticate(token) : null;
    if (!user) return c.json({ error: "sign in required" }, 401);
    c.set("user", user);
    c.set("token", token);
    await next();
  };
  app.use("/api/rpc/*", needUser);
  app.use("/api/events", needUser);
  app.use("/api/session", needUser);
  app.use("/api/research/*", needUser);
  app.use("/api/courses", needUser);
  app.use("/api/courses/*", needUser);

  app.get("/api/session", (c) => {
    const { email, role, participant_code } = c.get("user");
    return c.json({ email, role, participant_code });
  });

  app.post("/api/session/logout", needUser, (c) => {
    auth.logout(c.get("token"));
    return c.json({ ok: true });
  });

  /** The shared `Api` over HTTP: POST /api/rpc/<method> with { args: [...] }, answered { result }. */
  app.post("/api/rpc/:method", async (c) => {
    const method = c.req.param("method");
    if (!RPC_METHODS.has(method)) return c.json({ error: `unknown method ${method}` }, 404);
    const { args } = await json(c);
    if (args !== undefined && (!Array.isArray(args) || args.length > 8)) return c.json({ error: "args must be an array" }, 400);
    try {
      const result = await runner.run(c.get("user"), c.req.header("X-Visit") ?? null, () => callMethod(method, (args as unknown[]) ?? []));
      return c.json({ result: result ?? null });
    } catch (e) {
      // the rules throw plain Errors for things like an unknown id or a locked question
      return c.json({ error: e instanceof Error ? e.message : "failed" }, 400);
    }
  });

  /** The phone's own interaction events (play, seek, sheets), in batches. */
  app.post("/api/events", async (c) => {
    const { events } = await json(c);
    if (!Array.isArray(events) || events.length > MAX_EVENTS) return c.json({ error: "events must be an array of at most 200" }, 400);
    const good = events.filter(
      (e): e is ClientEvent => isObject(e) && typeof e.verb === "string" && isObject(e.object) && typeof (e.object as { type?: unknown }).type === "string",
    );
    await runner.run(c.get("user"), c.req.header("X-Visit") ?? null, () => trackClientEvents(good));
    return c.json({ accepted: good.length });
  });

  /** The study questionnaire export (plan/study-instruments-plan.md I12): researchers only, every consenting participant. */
  app.get("/api/research/study.csv", (c) => {
    if (c.get("user").role !== "researcher") return c.json({ error: "researchers only" }, 403);
    const participants = runner
      .allStates()
      .filter((s) => s.consent === "research")
      .map((s) => ({ participant_code: s.participant_code, condition: s.condition, study: s.study }));
    return c.body(studyCsv(participants), 200, { "Content-Type": "text/csv; charset=utf-8" });
  });

  /**
   * The facilitator's study-clock control (src/clock.ts), researchers only. Body: { participant_code } plus one of
   * { days }, { module } (just past that module's last lecture week) or { reset: true }; no action just reads it.
   */
  app.post("/api/research/clock", async (c) => {
    if (c.get("user").role !== "researcher") return c.json({ error: "researchers only" }, 403);
    const body = (await c.req.json().catch(() => null)) as { participant_code?: string; days?: number; module?: number; reset?: boolean } | null;
    const code = body?.participant_code;
    if (!code || typeof code !== "string") return c.json({ error: "participant_code is required" }, 400);
    try {
      const out = body?.reset
        ? resetClock(db, code)
        : typeof body?.module === "number"
          ? advanceToModuleEnd(db, code, body.module, (id) => courses.fixturesFor(id))
          : typeof body?.days === "number"
            ? advanceClock(db, code, body.days)
            : getClock(db, code);
      return out ? c.json(out) : c.json({ error: "no such participant" }, 404);
    } catch (e) {
      return c.json({ error: (e as Error).message }, 400);
    }
  });

  // ---- uploads (plan/slide-uploads-plan.md)
  const uploadErrors = (fn: (c: Context<Env>) => Promise<Response> | Response) => async (c: Context<Env>) => {
    try {
      return await fn(c);
    } catch (e) {
      if (e instanceof UploadError) return c.json({ error: e.message }, e.status);
      throw e;
    }
  };
  const idOf = (c: Context<Env>) => c.req.param("id") ?? "";
  const fileParts = async (c: Context<Env>, field: string) => {
    const body = await c.req.parseBody({ all: true }).catch(() => ({}) as Record<string, unknown>);
    const raw = (body as Record<string, unknown>)[field];
    const list = (Array.isArray(raw) ? raw : raw ? [raw] : []).filter((f): f is File => f instanceof File);
    return Promise.all(list.map(async (f) => ({ name: f.name, bytes: new Uint8Array(await f.arrayBuffer()) })));
  };

  app.get("/api/courses/mine", (c) => c.json(uploads.myCourse(c.get("user").id)));

  /** The syllabus (multipart field "syllabus"): the course is created or joined once the worker has read it. */
  app.post(
    "/api/courses",
    uploadErrors(async (c) => {
      const [file] = await fileParts(c, "syllabus");
      if (!file) return c.json({ error: "Choose your syllabus file." }, 400);
      return c.json(uploads.addSyllabus(c.get("user").id, file.name, file.bytes));
    }),
  );

  /** The creator confirms the lecture list, edited or as read ({ lectures } omitted). */
  app.post(
    "/api/courses/:id/lectures",
    uploadErrors(async (c) => {
      const { lectures } = await json(c);
      if (lectures !== undefined && !Array.isArray(lectures)) return c.json({ error: "lectures must be a list" }, 400);
      uploads.confirmLectures(c.get("user").id, idOf(c), lectures as { n: number; title: string; week: number | null }[] | undefined);
      return c.json(uploads.myCourse(c.get("user").id));
    }),
  );

  /** Slide files (multipart field "files", one or more). */
  app.post(
    "/api/courses/:id/slides",
    uploadErrors(async (c) => c.json({ uploads: uploads.addSlides(c.get("user").id, idOf(c), await fileParts(c, "files")) })),
  );

  app.get(
    "/api/courses/:id/uploads",
    uploadErrors((c) => c.json({ uploads: uploads.uploadViews(c.get("user").id, idOf(c)) })),
  );

  /** The review screen's "Confirm all": { choices: [{ upload_id, lecture_n, kind? }] }. */
  app.post(
    "/api/courses/:id/uploads/confirm",
    uploadErrors(async (c) => {
      const { choices } = await json(c);
      if (!Array.isArray(choices) || choices.length > 60) return c.json({ error: "choices must be a list" }, 400);
      return c.json({ uploads: uploads.confirmUploads(c.get("user").id, idOf(c), choices as never) });
    }),
  );

  // ---- the upload worker (ingestion_agent/worker.py), with its own token
  const needWorker = async (c: Context<Env>, next: () => Promise<void>) => {
    const header = c.req.header("Authorization") ?? "";
    if (!workerToken || header !== `Bearer ${workerToken}`) return c.json({ error: "worker token required" }, 401);
    await next();
  };
  app.use("/api/worker/*", needWorker);

  app.post("/api/worker/claim", (c) => c.json({ job: uploads.claim() }));

  app.get(
    "/api/worker/jobs/:id/file",
    uploadErrors((c) => {
      const f = uploads.fileOf(idOf(c));
      if (!f) return c.json({ error: "this job has no file" }, 404);
      return c.body(readFileSync(f.path), 200, { "Content-Type": "application/octet-stream" });
    }),
  );

  app.post(
    "/api/worker/jobs/:id/syllabus-key",
    uploadErrors(async (c) => {
      const { key } = await json(c);
      if (typeof key !== "string") return c.json({ error: "key is required" }, 400);
      return c.json(uploads.syllabusKey(idOf(c), key));
    }),
  );

  app.post(
    "/api/worker/jobs/:id/result",
    uploadErrors(async (c) => {
      const body = await c.req.json().catch(() => null);
      if (!isObject(body) || !isObject(body.result)) return c.json({ error: "result is required" }, 400);
      uploads.complete(idOf(c), body.result);
      return c.json({ ok: true });
    }),
  );

  app.post(
    "/api/worker/jobs/:id/fail",
    uploadErrors(async (c) => {
      const { error, user_message } = await json(c);
      uploads.fail(idOf(c), typeof error === "string" ? error.slice(0, 2000) : "failed", typeof user_message === "string" ? user_message.slice(0, 500) : undefined);
      return c.json({ ok: true });
    }),
  );

  /** Researcher: put a failed upload job back in the queue. */
  app.post(
    "/api/research/jobs/:id/retry",
    uploadErrors((c) => {
      if (c.get("user").role !== "researcher") return c.json({ error: "researchers only" }, 403);
      uploads.retry(idOf(c));
      return c.json({ ok: true });
    }),
  );

  return app;
}
