import { describe, expect, it } from "vitest";
import { makeServer } from "./helpers";

const redirectUrl = "syllabyte://signin";
const ticketOf = (text: string) => new URL(text.match(/https?:\/\/[^\s]+/)![0]).searchParams.get("ticket")!;

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
