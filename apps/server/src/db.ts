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
  -- 'reading' until the lecture list is read from the syllabus
  status                TEXT NOT NULL CHECK (status IN ('reading', 'ready', 'failed')),
  schedule_found        INTEGER,
  created_by            TEXT NOT NULL REFERENCES users (id),
  created_at            INTEGER NOT NULL,
  lectures_confirmed_at INTEGER
);
CREATE TABLE IF NOT EXISTS course_members (
  course_id TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  user_id   TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  joined_at INTEGER NOT NULL,
  PRIMARY KEY (course_id, user_id)
);
CREATE TABLE IF NOT EXISTS lectures (
  id        TEXT PRIMARY KEY,
  course_id TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  n         INTEGER NOT NULL,
  title     TEXT NOT NULL,
  week      INTEGER,
  source    TEXT NOT NULL CHECK (source IN ('syllabus', 'upload')),
  UNIQUE (course_id, n)
);
CREATE TABLE IF NOT EXISTS decks (
  id            TEXT PRIMARY KEY,
  course_id     TEXT NOT NULL REFERENCES courses (id) ON DELETE CASCADE,
  -- set when its first uploader confirms the placement
  lecture_id    TEXT REFERENCES lectures (id),
  content_key   TEXT NOT NULL,
  file_name     TEXT NOT NULL,
  pdf_path      TEXT NOT NULL,
  -- the parse: page count, each page's text, the first page's title
  parse_json    TEXT NOT NULL,
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
-- Work for the Python worker: kind 'syllabus' (read it, then the lecture list), 'deck_read' (convert and parse),
-- 'deck' (KUs and items), 'link_pass' (U7). The worker claims them over HTTP.
CREATE TABLE IF NOT EXISTS jobs (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL CHECK (kind IN ('syllabus', 'deck_read', 'deck', 'link_pass')),
  target_id   TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('queued', 'claimed', 'done', 'failed')),
  priority    INTEGER NOT NULL DEFAULT 0,
  attempts    INTEGER NOT NULL DEFAULT 0,
  claimed_at  INTEGER,
  created_at  INTEGER NOT NULL,
  finished_at INTEGER,
  error       TEXT
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs (status, priority, created_at);
`;

export function openDb(path: string): Db {
  if (path !== ":memory:") mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");
  db.exec(SCHEMA);
  return db;
}
