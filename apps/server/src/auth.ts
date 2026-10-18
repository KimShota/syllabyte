import { createHash, createHmac, randomBytes, randomInt, timingSafeEqual } from "node:crypto";
import type { Db, Role } from "./db";
import type { Mailer } from "./mail";

/**
 * Sign-in by emailed code (plan §9.3, adapted for the phone): the student enters their email, gets a 6-digit code
 * that works once for 10 minutes, and types it into the app, which then keeps a session token in secure storage.
 * A code needs no universal-link setup and works the same on iOS and Android. Only emails on the allowlist can sign
 * in, and the server never says whether an email is on it.
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
    const user = this.upsertUser(email, entry.role);
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
