import { createHash, createHmac, randomBytes, randomInt, timingSafeEqual } from "node:crypto";
import type { Db, Role } from "./db";
import type { Mailer } from "./mail";

/**
 * Sign-in by single-use email link, with emailed codes retained for older clients. A legacy client gets a 6-digit code
 * that works once for 10 minutes, and types it into the app, which then keeps a session token in secure storage.
 * Sign-up links create a student account only after email verification. Existing/invited users can sign in; removed
 * accounts cannot restore their access by signing up again. Requests never reveal whether an account exists.
 */
const CODE_TTL_MS = 10 * 60_000;
const MAX_ATTEMPTS = 5;
const MAX_CODES_PER_HOUR = 5;
const SESSION_TTL_MS = 90 * 24 * 3600_000;
const LAST_SEEN_EVERY_MS = 10 * 60_000;
/** no 0/O/1/I */
const CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";

export interface User {
  id: string;
  email: string;
  role: Role;
  participant_code: string;
}

export const normalizeEmail = (raw: string): string => raw.trim().toLowerCase();
export const looksLikeEmail = (s: string): boolean => s.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);

const sha256 = (s: string) => createHash("sha256").update(s).digest("hex");

export class Auth {
  constructor(
    private db: Db,
    private mailer: Mailer,
    private secret: string,
    private clock: () => number = Date.now,
  ) {}

  private codeHash(email: string, code: string): string {
    return createHmac("sha256", this.secret).update(`${email}\n${code}`).digest("hex");
  }

  /**
   * A link to `subject` that works without a sign-in until `ttlMs` from now: for opening an uploaded file in a browser
   * view, which cannot send the app's token. The query string carries the expiry and its signature.
   */
  signLink(subject: string, ttlMs: number): string {
    const expires = this.clock() + ttlMs;
    return `e=${expires}&s=${this.linkSig(subject, expires)}`;
  }

  /** Whether a link from `signLink` for `subject` is genuine and not yet expired. */
  checkLink(subject: string, expires: string | undefined, sig: string | undefined): boolean {
    const e = Number(expires);
    if (!Number.isFinite(e) || e < this.clock() || !sig) return false;
    const want = Buffer.from(this.linkSig(subject, e));
    const got = Buffer.from(sig);
    return want.length === got.length && timingSafeEqual(want, got);
  }

  private linkSig(subject: string, expires: number): string {
    return createHmac("sha256", this.secret).update(`link\n${subject}\n${expires}`).digest("hex");
  }

  addToAllowlist(email: string, role: Role): void {
    this.db
      .prepare("INSERT INTO allowlist (email, role, added_at) VALUES (?, ?, ?) ON CONFLICT (email) DO UPDATE SET role = excluded.role")
      .run(normalizeEmail(email), role, this.clock());
  }

  /** Emails a code if the address is on the allowlist and not over its hourly limit; always looks the same to the caller. */
  async requestCode(rawEmail: string): Promise<void> {
    const email = normalizeEmail(rawEmail);
    if (!looksLikeEmail(email)) return;
    if (!this.db.prepare("SELECT 1 FROM allowlist WHERE email = ?").get(email)) return;
    const now = this.clock();
    const recent = this.db.prepare("SELECT COUNT(*) AS n FROM login_codes WHERE email = ? AND created_at > ?").get(email, now - 3600_000) as { n: number };
    if (recent.n >= MAX_CODES_PER_HOUR) return;
    const code = Array.from({ length: 6 }, () => CODE_ALPHABET[randomInt(CODE_ALPHABET.length)]).join("");
    this.db.prepare("INSERT INTO login_codes (email, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?)").run(email, this.codeHash(email, code), now, now + CODE_TTL_MS);
    await this.mailer.send(
      email,
      `Your SyllaByte code: ${code}`,
      `Your SyllaByte sign-in code is ${code}.\n\nIt works once and expires in 10 minutes. If you did not ask for it, ignore this email.\n`,
    );
  }

  /** Store only a hash; email the single-use ticket through a browser landing page, then back into the app. */
  async requestEmailLink(rawEmail: string, redirectUrl: string, publicBase: string, intent: "signin" | "signup" = "signin"): Promise<void> {
    const email = normalizeEmail(rawEmail);
    if (!looksLikeEmail(email)) return;
    const invited = this.db.prepare("SELECT 1 FROM allowlist WHERE email = ?").get(email);
    if (!invited && (intent !== "signup" || this.db.prepare("SELECT 1 FROM users WHERE email = ?").get(email))) return;
    const now = this.clock();
    const recent = this.db.prepare("SELECT COUNT(*) AS n FROM login_links WHERE email = ? AND created_at > ?").get(email, now - 3600_000) as { n: number };
    if (recent.n >= MAX_CODES_PER_HOUR) return;
    const ticket = randomBytes(32).toString("base64url");
    this.db.prepare("INSERT INTO login_links (token_hash, email, redirect_url, intent, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)")
      .run(sha256(ticket), email, redirectUrl, invited ? "signin" : "signup", now, now + CODE_TTL_MS);
    const link = new URL("/api/auth/email-link", publicBase);
    link.searchParams.set("ticket", ticket);
    try {
      const subject = intent === "signup" ? "Verify your SyllaByte email" : "Sign in to SyllaByte";
      await this.mailer.send(email, subject, `${subject}:\n\n${link.href}\n\nThis link works once and expires in 10 minutes. If you did not request it, ignore this email.\n`);
    } catch (error) {
      this.db.prepare("UPDATE login_links SET used = 1 WHERE token_hash = ?").run(sha256(ticket));
      throw error;
    }
  }

  /** Viewing the email's landing page must not consume a ticket: email scanners often open links automatically. */
  emailLinkDestination(ticket: string): string | null {
    const row = this.emailLink(ticket);
    if (!row) return null;
    const url = new URL(row.redirect_url);
    url.searchParams.set("ticket", ticket);
    if (row.intent === "signup") url.searchParams.set("mode", "signup");
    return url.href;
  }

  private emailLink(ticket: string): { email: string; redirect_url: string; intent: "signin" | "signup" } | undefined {
    if (!/^[A-Za-z0-9_-]{43}$/.test(ticket)) return undefined;
    return this.db.prepare("SELECT email, redirect_url, intent FROM login_links WHERE token_hash = ? AND used = 0 AND expires_at > ?")
      .get(sha256(ticket), this.clock()) as { email: string; redirect_url: string; intent: "signin" | "signup" } | undefined;
  }

  verifyEmailLink(ticket: string): { token: string; user: User } | null {
    const row = this.emailLink(ticket);
    if (!row) return null;
    this.db.exec("SAVEPOINT verify_email_link");
    try {
      let entry = this.db.prepare("SELECT role FROM allowlist WHERE email = ?").get(row.email) as { role: Role } | undefined;
      const existing = this.db.prepare("SELECT 1 FROM users WHERE email = ?").get(row.email);
      const registering = !entry && !existing && row.intent === "signup";
      if (!entry && !registering) {
        this.db.exec("RELEASE verify_email_link");
        return null;
      }
      const used = this.db.prepare("UPDATE login_links SET used = 1 WHERE token_hash = ? AND used = 0 AND expires_at > ?")
        .run(sha256(ticket), this.clock());
      if (!used.changes) {
        this.db.exec("RELEASE verify_email_link");
        return null;
      }
      if (registering) {
        this.db.prepare("INSERT INTO allowlist (email, role, added_at) VALUES (?, 'student', ?)").run(row.email, this.clock());
        entry = { role: "student" };
      }
      const session = this.createSession(row.email, entry!.role);
      if (registering) this.db.prepare("UPDATE users SET self_registered = 1 WHERE id = ?").run(session.user.id);
      this.db.exec("RELEASE verify_email_link");
      return session;
    } catch (error) {
      this.db.exec("ROLLBACK TO verify_email_link; RELEASE verify_email_link");
      throw error;
    }
  }

  /** Public account creation is distinct from the researcher's prior study enrollment. */
  isStudyParticipant(userId: string): boolean {
    return (this.db.prepare("SELECT self_registered FROM users WHERE id = ?").get(userId) as { self_registered: number } | undefined)?.self_registered === 0;
  }

  /** The session token for a right code, or null. A code that was used, expired or guessed wrong 5 times is dead. */
  verifyCode(rawEmail: string, rawCode: string): { token: string; user: User } | null {
    const email = normalizeEmail(rawEmail);
    const code = rawCode.trim().toUpperCase();
    const now = this.clock();
    const row = this.db
      .prepare("SELECT id, code_hash, attempts FROM login_codes WHERE email = ? AND used = 0 AND expires_at > ? ORDER BY created_at DESC, id DESC LIMIT 1")
      .get(email, now) as { id: number; code_hash: string; attempts: number } | undefined;
    if (!row || row.attempts >= MAX_ATTEMPTS) return null;
    this.db.prepare("UPDATE login_codes SET attempts = attempts + 1 WHERE id = ?").run(row.id);
    const given = Buffer.from(this.codeHash(email, code), "hex");
    const real = Buffer.from(row.code_hash, "hex");
    if (given.length !== real.length || !timingSafeEqual(given, real)) return null;
    this.db.prepare("UPDATE login_codes SET used = 1 WHERE email = ?").run(email);
    const entry = this.db.prepare("SELECT role FROM allowlist WHERE email = ?").get(email) as { role: Role } | undefined;
    if (!entry) return null;
    return this.createSession(email, entry.role);
  }

  private createSession(email: string, role: Role): { token: string; user: User } {
    const now = this.clock();
    const user = this.upsertUser(email, role);
    const token = randomBytes(32).toString("base64url");
    this.db
      .prepare("INSERT INTO sessions (token_hash, user_id, created_at, last_seen, expires_at) VALUES (?, ?, ?, ?, ?)")
      .run(sha256(token), user.id, now, now, now + SESSION_TTL_MS);
    return { token, user };
  }

  private upsertUser(email: string, role: Role): User {
    const existing = this.db.prepare("SELECT id, participant_code FROM users WHERE email = ?").get(email) as { id: string; participant_code: string } | undefined;
    if (existing) return { id: existing.id, email, role, participant_code: existing.participant_code };
    const id = `u-${randomBytes(8).toString("hex")}`;
    for (;;) {
      // the pseudonym research data is keyed by; the email-to-code link stays in this table
      const participant_code = `S-${Array.from({ length: 5 }, () => CODE_ALPHABET[randomInt(CODE_ALPHABET.length)]).join("")}`;
      try {
        this.db.prepare("INSERT INTO users (id, email, participant_code, created_at) VALUES (?, ?, ?, ?)").run(id, email, participant_code, this.clock());
        return { id, email, role, participant_code };
      } catch (e) {
        if (!/UNIQUE/.test(String(e))) throw e;
        if (this.db.prepare("SELECT 1 FROM users WHERE id = ?").get(id)) throw e;
      }
    }
  }

  /** The user a session token belongs to. Taking someone off the allowlist ends their sessions. */
  authenticate(token: string): User | null {
    const now = this.clock();
    const row = this.db
      .prepare(
        `SELECT s.token_hash, s.last_seen, u.id, u.email, u.participant_code, a.role
         FROM sessions s JOIN users u ON u.id = s.user_id JOIN allowlist a ON a.email = u.email
         WHERE s.token_hash = ? AND s.expires_at > ?`,
      )
      .get(sha256(token), now) as { token_hash: string; last_seen: number; id: string; email: string; participant_code: string; role: Role } | undefined;
    if (!row) return null;
    if (now - row.last_seen > LAST_SEEN_EVERY_MS) this.db.prepare("UPDATE sessions SET last_seen = ? WHERE token_hash = ?").run(now, row.token_hash);
    return { id: row.id, email: row.email, role: row.role, participant_code: row.participant_code };
  }

  logout(token: string): void {
    this.db.prepare("DELETE FROM sessions WHERE token_hash = ?").run(sha256(token));
  }
}
