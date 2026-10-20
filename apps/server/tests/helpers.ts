import { createApp } from "../src/app";
import { Auth } from "../src/auth";
import { Courses } from "../src/courses";
import { openDb, type Db, type Role } from "../src/db";
import { memoryMailer } from "../src/mail";
import { StateRunner } from "../src/runner";
import { DEFAULT_CAPS, Uploads, type Caps } from "../src/uploads";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";

export const WORKER_TOKEN = "worker-test-token";

export function makeServer(opts: { db?: Db; clock?: () => number; semesterStart?: number; caps?: Partial<Caps> } = {}) {
  const db = opts.db ?? openDb(":memory:");
  const mailer = memoryMailer();
  const auth = new Auth(db, mailer, "test-secret", opts.clock);
  const courses = new Courses(db);
  const runner = new StateRunner(db, { semesterStart: opts.semesterStart, courseFor: (id) => courses.fixturesFor(id),
    after: (id, state) => courses.recordVideoNeeds(id, state),
  });
  const uploads = new Uploads(db, courses, mkdtempSync(tmpdir() + "/syllabyte-files-"), { ...DEFAULT_CAPS, ...opts.caps }, opts.clock);
  const app = createApp({ db, auth, runner, courses, uploads, workerToken: WORKER_TOKEN });
  const post = (path: string, body: unknown, headers: Record<string, string> = {}) =>
    app.request(path, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });

  /** Signs `email` in (adding it to the allowlist) and returns the call helpers for that student. */
  async function signIn(email: string, role: Role = "student") {
    auth.addToAllowlist(email, role);
    await post("/api/auth/request-code", { email });
    const mail = mailer.sent.findLast((m) => m.to === email.toLowerCase())!;
    const code = /code is (\S+?)\./.exec(mail.text)![1];
    const res = await post("/api/auth/verify", { email, code });
    const { token } = (await res.json()) as { token: string };
    const authz = { Authorization: `Bearer ${token}` };
    return {
      token,
      /** POST /api/rpc/<method> */
      async rpc<T = unknown>(method: string, ...args: unknown[]): Promise<T> {
        const r = await post(`/api/rpc/${method}`, { args }, authz);
        const body = (await r.json()) as { result: T; error?: string };
        if (!r.ok) throw new Error(body.error ?? String(r.status));
        return body.result;
      },
      post: (path: string, body: unknown, headers: Record<string, string> = {}) => post(path, body, { ...authz, ...headers }),
      get: (path: string) => app.request(path, { headers: authz }),
    };
  }
  /** The worker's calls, with its token. */
  const worker = {
    post: (path: string, body: unknown) => post(path, body, { Authorization: `Bearer ${WORKER_TOKEN}` }),
    get: (path: string) => app.request(path, { headers: { Authorization: `Bearer ${WORKER_TOKEN}` } }),
  };
  return { app, db, auth, courses, uploads, worker, mailer, post, signIn };
}
