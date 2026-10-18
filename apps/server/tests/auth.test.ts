import { describe, expect, it } from "vitest";
import { makeServer } from "./helpers";

const codeOf = (text: string) => /code is (\S+?)\./.exec(text)![1];

describe("sign-in", () => {
  it("emails a code only to allowlisted addresses, and answers the same either way", async () => {
    const s = makeServer();
    s.auth.addToAllowlist("in@nyu.edu", "student");
    const a = await s.post("/api/auth/request-code", { email: "in@nyu.edu" });
    const b = await s.post("/api/auth/request-code", { email: "out@nyu.edu" });
    expect(a.status).toBe(200);
    expect(await a.json()).toEqual(await b.json());
    expect(s.mailer.sent.map((m) => m.to)).toEqual(["in@nyu.edu"]);
    expect(s.mailer.sent[0].text).toMatch(/code is [2-9A-Z]{6}\./);
  });

  it("is case and space insensitive on the email and the code", async () => {
    const s = makeServer();
    s.auth.addToAllowlist("Ann@NYU.edu", "student");
    await s.post("/api/auth/request-code", { email: "  ann@nyu.EDU " });
    const code = codeOf(s.mailer.sent[0].text).toLowerCase();
    const res = await s.post("/api/auth/verify", { email: "ANN@nyu.edu", code: ` ${code} ` });
    expect(res.status).toBe(200);
  });

  it("gives a session and a pseudonymous participant code, the same on the next sign-in", async () => {
    const s = makeServer();
    const first = await s.signIn("ann@nyu.edu");
    const me1 = (await (await first.get("/api/session")).json()) as { participant_code: string; role: string; email: string };
    expect(me1.participant_code).toMatch(/^S-[2-9A-Z]{5}$/);
    expect(me1.participant_code).not.toContain("ann");
    const again = await s.signIn("ann@nyu.edu");
    const me2 = (await (await again.get("/api/session")).json()) as { participant_code: string };
    expect(me2.participant_code).toBe(me1.participant_code);
  });

  it("works once", async () => {
    const s = makeServer();
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    await s.post("/api/auth/request-code", { email: "ann@nyu.edu" });
    const code = codeOf(s.mailer.sent[0].text);
    expect((await s.post("/api/auth/verify", { email: "ann@nyu.edu", code })).status).toBe(200);
    expect((await s.post("/api/auth/verify", { email: "ann@nyu.edu", code })).status).toBe(401);
  });

  it("expires after 10 minutes", async () => {
    let now = 1_000_000;
    const s = makeServer({ clock: () => now });
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    await s.post("/api/auth/request-code", { email: "ann@nyu.edu" });
    now += 10 * 60_000 + 1;
    expect((await s.post("/api/auth/verify", { email: "ann@nyu.edu", code: codeOf(s.mailer.sent[0].text) })).status).toBe(401);
  });

  it("locks a code after 5 wrong guesses, even if the next guess is right", async () => {
    const s = makeServer();
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    await s.post("/api/auth/request-code", { email: "ann@nyu.edu" });
    const code = codeOf(s.mailer.sent[0].text);
    const wrong = code === "AAAAAA" ? "BBBBBB" : "AAAAAA";
    for (let i = 0; i < 5; i++) expect((await s.post("/api/auth/verify", { email: "ann@nyu.edu", code: wrong })).status).toBe(401);
    expect((await s.post("/api/auth/verify", { email: "ann@nyu.edu", code })).status).toBe(401);
  });

  it("sends at most 5 codes an hour to one address", async () => {
    const s = makeServer();
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    for (let i = 0; i < 8; i++) await s.post("/api/auth/request-code", { email: "ann@nyu.edu" });
    expect(s.mailer.sent).toHaveLength(5);
  });

  it("ends a session when the email leaves the allowlist, and on logout", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    expect((await ann.get("/api/session")).status).toBe(200);
    s.db.prepare("DELETE FROM allowlist WHERE email = ?").run("ann@nyu.edu");
    expect((await ann.get("/api/session")).status).toBe(401);

    const bob = await s.signIn("bob@nyu.edu");
    expect((await bob.post("/api/session/logout", {})).status).toBe(200);
    expect((await bob.get("/api/session")).status).toBe(401);
  });

  it("rejects calls without a valid token", async () => {
    const s = makeServer();
    expect((await s.post("/api/rpc/getMe", { args: [] })).status).toBe(401);
    expect((await s.post("/api/rpc/getMe", { args: [] }, { Authorization: "Bearer nope" })).status).toBe(401);
  });
});

describe("cors", () => {
  it("is off unless an origin is configured", async () => {
    const s = makeServer();
    const res = await s.app.request("/api/health", { headers: { Origin: "http://localhost:8081" } });
    expect(res.headers.get("access-control-allow-origin")).toBeNull();
  });
});
