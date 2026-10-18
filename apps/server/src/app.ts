import { Hono, type Context } from "hono";
import { bodyLimit } from "hono/body-limit";
import { studyCsv } from "@syllabyte/core/logic/instruments";
import { Auth, type User } from "./auth";
import type { Db } from "./db";
import { RPC_METHODS, StateRunner, callMethod, trackClientEvents, type ClientEvent } from "./runner";

export interface Deps {
  db: Db;
  auth: Auth;
  runner: StateRunner;
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
export function createApp({ auth, runner }: Deps): Hono<Env> {
  const app = new Hono<Env>();
  app.use("*", bodyLimit({ maxSize: 512 * 1024, onError: (c) => c.json({ error: "too large" }, 413) }));

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

  return app;
}
