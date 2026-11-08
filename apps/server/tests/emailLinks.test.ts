import { describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { openDb } from "../src/db";
import { Auth } from "../src/auth";
import { memoryMailer } from "../src/mail";
import { makeServer } from "./helpers";

const redirectUrl = "syllabyte://signin";
const ticketOf = (text: string) => new URL(text.match(/https?:\/\/[^\s]+/)![0]).searchParams.get("ticket")!;

describe("public account creation", () => {
  it("creates a student account for a new verified email, never at the initial request", async () => {
    const s = makeServer();
    const response = await s.post("/api/auth/request-link", { email: " NEW@example.com ", redirectUrl, intent: "signup", role: "researcher" });
    expect(response.status).toBe(200);
    expect(s.db.prepare("SELECT COUNT(*) AS n FROM users").get()).toMatchObject({ n: 0 });
    expect(s.db.prepare("SELECT COUNT(*) AS n FROM allowlist").get()).toMatchObject({ n: 0 });
    expect(s.db.prepare("SELECT COUNT(*) AS n FROM sessions").get()).toMatchObject({ n: 0 });
    expect(s.mailer.sent[0]).toMatchObject({ to: "new@example.com", subject: "Verify your SyllaByte email" });
    const ticket = ticketOf(s.mailer.sent[0].text);
    expect(s.auth.emailLinkDestination(ticket)).toContain("mode=signup");
    const verified = await s.post("/api/auth/verify-link", { ticket, role: "researcher" });
    expect(verified.status).toBe(200);
    const account = await verified.json() as { token: string; email: string; role: string; study_participant: boolean };
    expect(account).toMatchObject({ email: "new@example.com", role: "student", study_participant: false });
    const session = await s.app.request("/api/session", { headers: { Authorization: `Bearer ${account.token}` } });
    expect(session.status).toBe(200);
    expect(await session.json()).toMatchObject({ email: "new@example.com", study_participant: false });
    expect((await s.post("/api/auth/verify-link", { ticket })).status).toBe(401);
  });

  it("signs up once across multiple links and can later sign in with the same identity", async () => {
    const s = makeServer();
    for (const email of ["new@example.com", "NEW@example.com"])
      await s.post("/api/auth/request-link", { email, redirectUrl, intent: "signup" });
    const accounts: { participant_code: string }[] = [];
    for (const mail of s.mailer.sent) accounts.push(await (await s.post("/api/auth/verify-link", { ticket: ticketOf(mail.text) })).json() as { participant_code: string });
    expect(s.db.prepare("SELECT COUNT(*) AS n FROM users").get()).toMatchObject({ n: 1 });
    expect(accounts[0].participant_code).toBe(accounts[1].participant_code);
    await s.post("/api/auth/request-link", { email: "new@example.com", redirectUrl, intent: "signin" });
    const signedIn = await (await s.post("/api/auth/verify-link", { ticket: ticketOf(s.mailer.sent[2].text) })).json();
    expect(signedIn).toMatchObject({ participant_code: accounts[0].participant_code, study_participant: false });
  });

  it("does not create an account for an expired signup link", async () => {
    let now = 1_000_000;
    const s = makeServer({ clock: () => now });
    await s.post("/api/auth/request-link", { email: "new@example.com", redirectUrl, intent: "signup" });
    now += 10 * 60_000;
    expect((await s.post("/api/auth/verify-link", { ticket: ticketOf(s.mailer.sent[0].text) })).status).toBe(401);
    expect(s.db.prepare("SELECT COUNT(*) AS n FROM users").get()).toMatchObject({ n: 0 });
    expect(s.db.prepare("SELECT COUNT(*) AS n FROM allowlist").get()).toMatchObject({ n: 0 });
  });

  it("does not let removed accounts restore access through signup or a previously issued signup link", async () => {
    const s = makeServer();
    for (let i = 0; i < 2; i++) await s.post("/api/auth/request-link", { email: "new@example.com", redirectUrl, intent: "signup" });
    expect((await s.post("/api/auth/verify-link", { ticket: ticketOf(s.mailer.sent[0].text) })).status).toBe(200);
    s.db.prepare("DELETE FROM allowlist WHERE email = ?").run("new@example.com");
    expect((await s.post("/api/auth/verify-link", { ticket: ticketOf(s.mailer.sent[1].text) })).status).toBe(401);
    await s.post("/api/auth/request-link", { email: "new@example.com", redirectUrl, intent: "signup" });
    expect(s.mailer.sent).toHaveLength(2);
  });

  it("keeps an existing account's identity, role, and invited-study status when signup is chosen again", async () => {
    const s = makeServer();
    const old = await s.signIn("researcher@nyu.edu", "researcher");
    const before = await (await old.get("/api/session")).json() as { participant_code: string };
    await s.post("/api/auth/request-link", { email: "researcher@nyu.edu", redirectUrl, intent: "signup" });
    const verified = await (await s.post("/api/auth/verify-link", { ticket: ticketOf(s.mailer.sent.at(-1)!.text) })).json();
    expect(verified).toMatchObject({ participant_code: before.participant_code, role: "researcher", study_participant: true });
    expect(s.db.prepare("SELECT COUNT(*) AS n FROM users").get()).toMatchObject({ n: 1 });
    expect((await s.post("/api/auth/request-link", { email: "new@example.com", redirectUrl, intent: "admin" })).status).toBe(400);
  });

  it("migrates existing accounts and pending sign-in links without treating them as public registrations", () => {
    const path = join(mkdtempSync(join(tmpdir(), "syllabyte-signup-migration-")), "db.sqlite");
    const old = new DatabaseSync(path);
    const ticket = "a".repeat(43);
    old.exec(`CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, participant_code TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL);
      CREATE TABLE login_links (token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, redirect_url TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
      INSERT INTO users VALUES ('old-user', 'old@nyu.edu', 'S-OLD', 1000);`);
    old.prepare("INSERT INTO login_links VALUES (?, ?, ?, ?, ?, 0)")
      .run(createHash("sha256").update(ticket).digest("hex"), "old@nyu.edu", redirectUrl, 1000, Date.now() + 60_000);
    old.close();
    const db = openDb(path);
    try {
      const auth = new Auth(db, memoryMailer(), "test-secret");
      auth.addToAllowlist("old@nyu.edu", "student");
      expect(auth.verifyEmailLink(ticket)?.user.id).toBe("old-user");
      expect(auth.isStudyParticipant("old-user")).toBe(true);
    } finally { db.close(); }
  });
});

describe("sign-in by email link", () => {
  it("only emails enrolled addresses, returns the same response, and stores a hash instead of the ticket", async () => {
    const s = makeServer();
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    const enrolled = await s.post("/api/auth/request-link", { email: " ANN@nyu.edu ", redirectUrl });
    const unknown = await s.post("/api/auth/request-link", { email: "unknown@nyu.edu", redirectUrl });
    expect(enrolled.status).toBe(200);
    expect(await enrolled.json()).toEqual(await unknown.json());
    expect(s.mailer.sent).toHaveLength(1);
    expect(s.mailer.sent[0].to).toBe("ann@nyu.edu");
    const ticket = ticketOf(s.mailer.sent[0].text);
    expect(ticket).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(JSON.stringify(s.db.prepare("SELECT * FROM login_links").all())).not.toContain(ticket);
  });

  it("does not consume a link when an email scanner visits it; the app can redeem it only once", async () => {
    const s = makeServer();
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    await s.post("/api/auth/request-link", { email: "ann@nyu.edu", redirectUrl });
    const ticket = ticketOf(s.mailer.sent[0].text);
    const path = `/api/auth/email-link?ticket=${ticket}`;
    const landing = await s.app.request(path);
    expect(landing.headers.get("cache-control")).toBe("no-store");
    expect(landing.headers.get("referrer-policy")).toBe("no-referrer");
    expect(await landing.text()).toContain(`syllabyte://signin?ticket=${ticket}`);
    expect((await s.app.request(path)).status).toBe(200);
    const response = await s.post("/api/auth/verify-link", { ticket });
    const result = await response.json() as { token: string; email: string };
    expect(response.status).toBe(200);
    expect(result.email).toBe("ann@nyu.edu");
    expect((await s.app.request("/api/session", { headers: { Authorization: `Bearer ${result.token}` } })).status).toBe(200);
    expect((await s.post("/api/auth/verify-link", { ticket })).status).toBe(401);
    expect((await s.app.request(path)).status).toBe(410);
  });

  it("rejects forged, expired, and removed students' links", async () => {
    let now = 1_000_000;
    const s = makeServer({ clock: () => now });
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    await s.post("/api/auth/request-link", { email: "ann@nyu.edu", redirectUrl });
    const ticket = ticketOf(s.mailer.sent[0].text);
    const forged = (ticket[0] === "a" ? "b" : "a") + ticket.slice(1);
    expect((await s.post("/api/auth/verify-link", { ticket: forged })).status).toBe(401);
    now += 10 * 60_000;
    expect((await s.post("/api/auth/verify-link", { ticket })).status).toBe(401);
    await s.post("/api/auth/request-link", { email: "ann@nyu.edu", redirectUrl });
    const current = ticketOf(s.mailer.sent[1].text);
    s.db.prepare("DELETE FROM allowlist WHERE email = ?").run("ann@nyu.edu");
    expect((await s.post("/api/auth/verify-link", { ticket: current })).status).toBe(401);
  });

  it.each(["https://attacker.example/signin", "javascript:alert(1)", "syllabyte://signin?next=https://attacker.example", "exp://evil.example:8081/--/signin"])("rejects unregistered return URLs: %s", async (redirectUrl) => {
    const s = makeServer();
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    expect((await s.post("/api/auth/request-link", { email: "ann@nyu.edu", redirectUrl })).status).toBe(400);
    expect(s.mailer.sent).toEqual([]);
  });

  it("allows Expo Go on the development API's host only when explicitly enabled", async () => {
    const s = makeServer({ emailLinks: { publicBase: "http://10.0.0.5:8790", allowExpoGo: true } });
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    const callback = "exp://10.0.0.5:8082/--/signin";
    expect((await s.post("/api/auth/request-link", { email: "ann@nyu.edu", redirectUrl: callback })).status).toBe(200);
    expect(s.auth.emailLinkDestination(ticketOf(s.mailer.sent[0].text))).toContain(callback + "?ticket=");
    expect((await s.post("/api/auth/request-link", { email: "ann@nyu.edu", redirectUrl: "exp://10.0.0.9:8082/--/signin" })).status).toBe(400);
    const production = makeServer({ emailLinks: { publicBase: "https://api.syllabyte.app" } });
    expect((await production.post("/api/auth/request-link", { email: "ann@nyu.edu", redirectUrl: callback })).status).toBe(400);
  });

  it("keeps the existing student identity and limits sign-in emails to five an hour", async () => {
    const s = makeServer();
    const old = await s.signIn("ann@nyu.edu");
    const who = await (await old.get("/api/session")).json() as { participant_code: string };
    for (let i = 0; i < 8; i++) await s.post("/api/auth/request-link", { email: "ann@nyu.edu", redirectUrl });
    const links = s.mailer.sent.filter((m) => m.subject === "Sign in to SyllaByte");
    expect(links).toHaveLength(5);
    const signedIn = await (await s.post("/api/auth/verify-link", { ticket: ticketOf(links[0].text) })).json() as { participant_code: string };
    expect(signedIn.participant_code).toBe(who.participant_code);
  });
});
