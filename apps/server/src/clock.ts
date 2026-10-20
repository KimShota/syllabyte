import { fixtures } from "@syllabyte/core/fixtures";
import { studyModules } from "@syllabyte/core/logic/instruments";
import { DAY } from "@syllabyte/core/util";
import type { Db } from "./db";

/**
 * The facilitator's control over the study timeline: moving one student's clock forward so the later lecture checks
 * and questionnaires can be tried without waiting weeks. The offset lives beside the student's state, never in it, so
 * students cannot set it (the app's own methods only ever see the clock) and a reload cannot reset it.
 */
export interface ClockChange {
  participant_code: string;
  offset_days: number;
}

function userId(db: Db, code: string): string | undefined {
  return (db.prepare("SELECT id FROM users WHERE participant_code = ?").get(code) as { id: string } | undefined)?.id;
}

function current(db: Db, id: string): number {
  return (db.prepare("SELECT offset_ms FROM study_clock WHERE user_id = ?").get(id) as { offset_ms: number } | undefined)?.offset_ms ?? 0;
}

function write(db: Db, id: string, ms: number): void {
  db.prepare("INSERT INTO study_clock (user_id, offset_ms) VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET offset_ms = excluded.offset_ms").run(id, ms);
}

const result = (code: string, ms: number): ClockChange => ({ participant_code: code, offset_days: Math.round((ms / DAY) * 100) / 100 });

export function getClock(db: Db, code: string): ClockChange | null {
  const id = userId(db, code);
  return id ? result(code, current(db, id)) : null;
}

/** Moves the clock forward by `days` (never back: a student's recorded times must stay in order). */
export function advanceClock(db: Db, code: string, days: number): ClockChange | null {
  if (!Number.isFinite(days) || days < 0 || days > 400) throw new Error("days must be between 0 and 400");
  const id = userId(db, code);
  if (!id) return null;
  const next = current(db, id) + Math.round(days * DAY);
  write(db, id, next);
  return result(code, next);
}

/** Moves the clock just past the end of module `n`'s last lecture week, so that module's questionnaire is due. */
export function advanceToModuleEnd(db: Db, code: string, n: number): ClockChange | null {
  const id = userId(db, code);
  if (!id) return null;
  const mod = studyModules(fixtures().course)[n - 1];
  if (!mod) throw new Error(`there is no module ${n}`);
  const lastWeek = Math.max(...fixtures().course.lectures.filter((l) => mod.lectures.includes(l.n)).map((l) => l.week));
  const row = db.prepare("SELECT json FROM user_state WHERE user_id = ?").get(id) as { json: string } | undefined;
  const start = row ? (JSON.parse(row.json) as { semester_start: number }).semester_start : undefined;
  if (start === undefined) throw new Error("that student has not opened the app yet");
  const due = start + lastWeek * 7 * DAY;
  const offset = current(db, id);
  const t = Date.now() + offset;
  const next = t < due ? offset + (due - t) + 60_000 : offset;
  write(db, id, next);
  return result(code, next);
}

/** Back to real time: for a test account only, since it makes recorded times go backwards. */
export function resetClock(db: Db, code: string): ClockChange | null {
  const id = userId(db, code);
  if (!id) return null;
  write(db, id, 0);
  return result(code, 0);
}
