import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";

export type Db = DatabaseSync;
export type Role = "student" | "instructor" | "researcher";
export const ROLES: readonly Role[] = ["student", "instructor", "researcher"];

/**
 * One SQLite file. A pilot is a few dozen students, each with one saved state document, so a single file (WAL mode,
 * backed up nightly) is enough, with nothing to run beside the server. `:memory:` is for tests.
 */
const SCHEMA = `
CREATE TABLE IF NOT EXISTS allowlist (
  email    TEXT PRIMARY KEY,
  role     TEXT NOT NULL CHECK (role IN ('student', 'instructor', 'researcher')),
  added_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id               TEXT PRIMARY KEY,
  email            TEXT NOT NULL UNIQUE,
  participant_code TEXT NOT NULL UNIQUE,
  created_at       INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_codes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  email      TEXT NOT NULL,
  code_hash  TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  attempts   INTEGER NOT NULL DEFAULT 0,
  used       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS login_codes_email ON login_codes (email, created_at);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  last_seen  INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS study_clock (
  user_id   TEXT PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
  offset_ms INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_state (
  user_id    TEXT PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
  json       TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

-- Uploaded courses (plan/slide-uploads-plan.md). A course is shared by everyone whose syllabus has the same normalized
-- text (syllabus_key); each deck is processed once per course.
CREATE TABLE IF NOT EXISTS syllabus_uploads (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  file_name  TEXT NOT NULL,
  file_path  TEXT NOT NULL,
  status     TEXT NOT NULL CHECK (status IN ('reading', 'joined', 'created', 'failed')),
  course_id  TEXT REFERENCES courses (id),
  error      TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS courses (
  id                    TEXT PRIMARY KEY,
  syllabus_key          TEXT NOT NULL UNIQUE,
  code                  TEXT NOT NULL DEFAULT '',
  name                  TEXT NOT NULL,
  syllabus_text         TEXT NOT NULL,
  syllabus_path         TEXT NOT NULL,
  status                TEXT NOT NULL CHECK (status IN ('reading', 'ready', 'failed')),
  schedule_found        INTEGER,
  -- the syllabus's schedule, as topic hints for placing decks (V1): a JSON list of titles
  topics_json           TEXT NOT NULL DEFAULT '[]',
  created_by            TEXT NOT NULL REFERENCES users (id),
  created_at            INTEGER NOT NULL,
  lectures_confirmed_at INTEGER
);
-- A syllabus that belongs to another course (U17): the researcher pointed it there, or merged its course into that one.
CREATE TABLE IF NOT EXISTS syllabus_aliases (
  syllabus_key TEXT PRIMARY KEY,
  course_id    TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  added_at     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS course_members (
  course_id TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  user_id   TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  joined_at INTEGER NOT NULL,
  PRIMARY KEY (course_id, user_id)
);
-- One per confirmed deck (V1-V3). n: the lecture's id within the course, never reused or changed; position: the
-- teaching order (a deck placed between two lectures takes a position between theirs).
CREATE TABLE IF NOT EXISTS lectures (
  id        TEXT PRIMARY KEY,
  course_id TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  n         INTEGER NOT NULL,
  title     TEXT NOT NULL,
  week      INTEGER,
  source    TEXT NOT NULL CHECK (source IN ('syllabus', 'upload')),
  position  REAL,
  UNIQUE (course_id, n)
);
CREATE TABLE IF NOT EXISTS decks (
  id            TEXT PRIMARY KEY,
  course_id     TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  -- set when its first uploader confirms the placement
  lecture_id    TEXT REFERENCES lectures (id),
  content_key   TEXT NOT NULL,
  file_name     TEXT NOT NULL,
  -- the uploaded file as it came (a PowerPoint is converted on the worker each time it is read)
  file_path     TEXT NOT NULL,
  -- the parse: page count, each page's text and key, the first page's title, the reader's summary (V1)
  parse_json    TEXT NOT NULL,
  -- the placement call's suggestion until the deck is placed: {position, sure}
  suggestion_json TEXT,
  status        TEXT NOT NULL CHECK (status IN ('unplaced', 'queued', 'processing', 'ready', 'failed')),
  -- the DeckResult (packages/core/src/logic/assemble.ts) once processed
  result_json   TEXT,
  first_user_id TEXT NOT NULL REFERENCES users (id),
  created_at    INTEGER NOT NULL,
  placed_at     INTEGER,
  ready_at      INTEGER,
  error         TEXT,
  UNIQUE (course_id, content_key)
);
-- Every slide file any student uploaded, and what became of it (also the research log for updated versions, U12).
CREATE TABLE IF NOT EXISTS deck_uploads (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  course_id  TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  file_name  TEXT NOT NULL,
  file_path  TEXT NOT NULL,
  byte_size  INTEGER NOT NULL,
  status     TEXT NOT NULL CHECK (status IN ('reading', 'read', 'confirmed', 'failed')),
  deck_id    TEXT REFERENCES decks (id),
  outcome    TEXT CHECK (outcome IN ('new', 'existing', 'extra_part', 'updated_version', 'over_cap', 'unreadable')),
  created_at INTEGER NOT NULL,
  error      TEXT
);
-- Prerequisite links added after a deck was processed (U7): ku_id builds on prereq_id.
CREATE TABLE IF NOT EXISTS ku_links (
  course_id TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  ku_id     TEXT NOT NULL,
  prereq_id TEXT NOT NULL,
  added_at  INTEGER NOT NULL,
  PRIMARY KEY (course_id, ku_id, prereq_id)
);
-- Work for the Python worker: kind 'syllabus' (read it, then its topics), 'deck_read' (convert, parse, say what it
-- teaches), 'placement' (order a student's new decks), 'deck' (KUs), 'question' (one question, V4), 'link_pass' (U7).
-- The worker claims them over HTTP (src/uploads.ts).
CREATE TABLE IF NOT EXISTS jobs (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL CHECK (kind IN ('syllabus', 'deck_read', 'placement', 'deck', 'question', 'link_pass')),
  -- the syllabus upload, deck upload or deck it works on; a placement's student; a question's "ku_id|tier"
  target_id   TEXT NOT NULL,
  course_id   TEXT,
  status      TEXT NOT NULL CHECK (status IN ('queued', 'claimed', 'done', 'failed')),
  priority    INTEGER NOT NULL DEFAULT 0,
  attempts    INTEGER NOT NULL DEFAULT 0,
  claimed_at  INTEGER,
  created_at  INTEGER NOT NULL,
  finished_at INTEGER,
  error       TEXT
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs (status, priority, created_at);
-- Questions written on demand (V4), saved for everyone in the course with the same slides. item_json: a core Item.
CREATE TABLE IF NOT EXISTS questions (
  id         TEXT PRIMARY KEY,
  course_id  TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  deck_id    TEXT NOT NULL REFERENCES decks (id),
  ku_id      TEXT NOT NULL,
  tier       TEXT NOT NULL CHECK (tier IN ('basic', 'applied', 'advanced')),
  item_json  TEXT NOT NULL,
  flags_json TEXT NOT NULL DEFAULT '[]',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS questions_by_ku ON questions (course_id, ku_id, tier);
-- Videos students need (U18), one per course, KU and level so classmates at the same level share it. prereq_ids: the
-- KU's prerequisites when its first video was requested, which the video keeps (U8). Made by the video pipeline
-- (plan/per-student-video-plan.md step 5), not yet wired.
CREATE TABLE IF NOT EXISTS video_requests (
  course_id     TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  ku_id         TEXT NOT NULL,
  level         INTEGER NOT NULL CHECK (level IN (1, 2, 3)),
  lecture_n     INTEGER NOT NULL,
  prereq_ids    TEXT NOT NULL,
  first_user_id TEXT NOT NULL REFERENCES users (id),
  requested_at  INTEGER NOT NULL,
  status        TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'making', 'ready', 'failed')),
  PRIMARY KEY (course_id, ku_id, level)
);
`;

export function openDb(path: string): Db {
  if (path !== ":memory:") mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");
  migrate(db);
  db.exec(SCHEMA);
  return db;
}

const columns = (db: Db, table: string) => (db.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]).map((c) => c.name);

/** Databases made before the 2026-10-21 revision (plan/slide-uploads-plan.md V1-V4) get its columns and job kinds. */
function migrate(db: Db): void {
  const tables = new Set((db.prepare("SELECT name FROM sqlite_master WHERE type = 'table'").all() as { name: string }[]).map((t) => t.name));
  if (tables.has("lectures") && !columns(db, "lectures").includes("position")) {
    db.exec("ALTER TABLE lectures ADD COLUMN position REAL; UPDATE lectures SET position = n;");
  }
  if (tables.has("courses") && !columns(db, "courses").includes("topics_json")) db.exec("ALTER TABLE courses ADD COLUMN topics_json TEXT NOT NULL DEFAULT '[]'");
  if (tables.has("decks") && !columns(db, "decks").includes("suggestion_json")) db.exec("ALTER TABLE decks ADD COLUMN suggestion_json TEXT");
  const jobs = db.prepare("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'jobs'").get() as { sql: string } | undefined;
  if (jobs && !jobs.sql.includes("'question'")) {
    // a CHECK constraint can't be altered: rebuild the table with the new kinds
    db.exec(`ALTER TABLE jobs RENAME TO jobs_before_v4; DROP INDEX IF EXISTS jobs_queue;`);
    db.exec(SCHEMA.slice(SCHEMA.indexOf("CREATE TABLE IF NOT EXISTS jobs"), SCHEMA.indexOf("CREATE INDEX IF NOT EXISTS jobs_queue")));
    db.exec("INSERT INTO jobs SELECT * FROM jobs_before_v4; DROP TABLE jobs_before_v4;");
  }
}
