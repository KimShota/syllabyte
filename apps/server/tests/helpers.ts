import { createApp } from "../src/app";
import { Auth } from "../src/auth";
import { openDb, type Db, type Role } from "../src/db";
import { memoryMailer } from "../src/mail";
import { StateRunner } from "../src/runner";

export function makeServer(opts: { db?: Db; clock?: () => number; semesterStart?: number } = {}) {
  const db = opts.db ?? openDb(":memory:");
  const mailer = memoryMailer();
  const auth = new Auth(db, mailer, "test-secret", opts.clock);
  const app = createApp({ db, auth, runner: new StateRunner(db, { semesterStart: opts.semesterStart }) });
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
  return { app, db, auth, mailer, post, signIn };
}
