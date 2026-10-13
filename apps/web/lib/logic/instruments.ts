import {
  BATTERY_CONTENTS, INSTRUMENTS, type Instrument, type InstrumentId, type InstrumentItem,
} from "@/content/instruments";
import type { BatteryRecord, Condition, Course, StudyModule } from "@/lib/types";
import { DAY } from "@/lib/util";

/**
 * When the study's questionnaires are due, what each battery contains, and how they are scored
 * (plan/study-instruments-plan.md). Batteries follow course modules, not calendar weeks (I2), because the study's
 * length is not decided.
 */

/** The configured modules, or the lectures split in two (the first half rounded up). */
export function studyModules(course: Course): StudyModule[] {
  const configured = course.config.study_modules;
  if (configured && configured.length) return configured;
  const ns = course.lectures.map((l) => l.n).sort((a, b) => a - b);
  if (ns.length <= 1) return [{ id: "module-1", title: "Module 1", lectures: ns }];
  const half = Math.ceil(ns.length / 2);
  return [
    { id: "module-1", title: "Module 1", lectures: ns.slice(0, half) },
    { id: "module-2", title: "Module 2", lectures: ns.slice(half) },
  ];
}

/**
 * A module has ended once the schedule has moved past the week of its last lecture: the same moment for every student,
 * whatever they watched. The demo's "treat lecture N as upcoming" (`upcomingOverride`) can end it sooner. The course
 * config's `upcoming_lecture_override` pins only the playlist (Phase 0), so it does not count here.
 */
export function moduleEnded(course: Course, module: StudyModule, week: number, upcomingOverride: number | null): boolean {
  if (!module.lectures.length) return false;
  const last = Math.max(...module.lectures);
  const lecture = course.lectures.find((l) => l.n === last);
  return (lecture !== undefined && week > lecture.week) || (upcomingOverride !== null && upcomingOverride > last);
}

/**
 * When a module's battery became due: the start of the week after its last lecture's week, or `now` when the demo's
 * override ended it before then (there is no schedule moment to point at).
 */
export function moduleEndTime(course: Course, module: StudyModule, semesterStart: number, now: number): number {
  const last = Math.max(...module.lectures);
  const lecture = course.lectures.find((l) => l.n === last);
  if (!lecture) return now;
  const scheduled = semesterStart + lecture.week * 7 * DAY;
  return scheduled <= now ? scheduled : now;
}

/** Module batteries that are due now, in module order. */
export function dueModules(course: Course, week: number, upcomingOverride: number | null): StudyModule[] {
  return studyModules(course).filter((m) => moduleEnded(course, m, week, upcomingOverride));
}

export function batteryKind(batteryId: string): "baseline" | "module" {
  return batteryId === "baseline" ? "baseline" : "module";
}

/** The instruments a battery asks, for this participant's condition (trust is Condition A only, I3). */
export function batteryInstruments(batteryId: string, condition: Condition): Instrument[] {
  return BATTERY_CONTENTS[batteryKind(batteryId)].map((id) => INSTRUMENTS[id]).filter((i) => i.conditions.includes(condition));
}

/** Items to show given the answers so far (the gender self-description appears only when chosen). */
export function visibleItems(instrument: Instrument, answers: BatteryRecord["answers"]): InstrumentItem[] {
  return instrument.items.filter((it) => !it.showIf || answers[it.showIf.item] === it.showIf.value);
}

export function newBattery(id: string, version: string, openedAt: number): BatteryRecord {
  return { id, kind: batteryKind(id), version, opened_at: openedAt, started_at: null, submitted_at: null, snoozed_visit: null, answers: {} };
}

// ---------------------------------------------------------------- scoring

export type ScoreId = "sus" | "tlx_raw" | "efficacy" | "trust_jian" | "trust_study";

export interface ScaleScore {
  id: ScoreId;
  instrument: InstrumentId;
  /** every item of the score was answered (I10); otherwise `score` is null */
  complete: boolean;
  answered: number;
  total: number;
  score: number | null;
}

const num = (v: number | string | null | undefined): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function scoreOver(id: ScoreId, instrument: Instrument, itemIds: string[], answers: BatteryRecord["answers"], f: (values: number[]) => number): ScaleScore {
  const values = itemIds.map((i) => num(answers[i]));
  const answered = values.filter((v) => v !== null).length;
  const complete = answered === itemIds.length;
  return { id, instrument: instrument.id, complete, answered, total: itemIds.length, score: complete ? f(values as number[]) : null };
}

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
const round2 = (x: number) => Math.round(x * 100) / 100;

/** The scores an instrument yields. Demographics yield none. */
export function scoreInstrument(instrument: Instrument, answers: BatteryRecord["answers"]): ScaleScore[] {
  const ids = instrument.items.map((i) => i.id);
  switch (instrument.id) {
    case "sus":
      // Brooke (1996): odd items contribute (x − 1), even items (5 − x); the sum times 2.5 gives 0-100.
      return [scoreOver("sus", instrument, ids, answers, (v) => 2.5 * v.reduce((acc, x, i) => acc + (i % 2 === 0 ? x - 1 : 5 - x), 0))];
    case "tlx":
      // Raw TLX: the unweighted mean of the six subscales (performance runs Perfect 0 -> Failure 100, so higher = more load).
      return [scoreOver("tlx_raw", instrument, ids, answers, (v) => round2(mean(v)))];
    case "efficacy":
      return [scoreOver("efficacy", instrument, ids, answers, (v) => round2(mean(v)))];
    case "trust": {
      const jian = instrument.items.slice(0, 12);
      const study = instrument.items.slice(12);
      const jianScore = scoreOver("trust_jian", instrument, jian.map((i) => i.id), answers, (v) =>
        round2(mean(v.map((x, k) => (jian[k].reverse ? 8 - x : x)))),
      );
      const studyScore = scoreOver("trust_study", instrument, study.map((i) => i.id), answers, (v) => round2(mean(v)));
      return [jianScore, studyScore];
    }
    case "demographics":
      return [];
  }
}

export function scoreBattery(record: BatteryRecord, condition: Condition): ScaleScore[] {
  return batteryInstruments(record.id, condition).flatMap((i) => scoreInstrument(i, record.answers));
}

// ---------------------------------------------------------------- export (I12)

export interface ParticipantStudy {
  participant_code: string | null;
  condition: Condition;
  study: Record<string, BatteryRecord>;
}

export const CSV_COLUMNS = [
  "row", "participant_code", "condition", "battery", "version", "instrument", "item", "value", "skipped", "complete",
  "opened_at", "started_at", "submitted_at", "days_after_due",
] as const;

function csvCell(v: string | number | boolean | null): string {
  if (v === null) return "";
  const s = String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

const iso = (t: number | null) => (t === null ? null : new Date(t).toISOString());

/**
 * One row per participant × battery × item asked (its answer, or skipped), then one row per scale score. Items the
 * participant never reached are left out; a submitted battery's unanswered items count as skipped.
 */
export function studyCsv(participants: ParticipantStudy[]): string {
  const lines: string[] = [CSV_COLUMNS.join(",")];
  const push = (cells: (string | number | boolean | null)[]) => lines.push(cells.map(csvCell).join(","));
  for (const p of participants) {
    for (const record of Object.values(p.study).sort((a, b) => a.opened_at - b.opened_at)) {
      const timing = [
        iso(record.opened_at), iso(record.started_at), iso(record.submitted_at),
        record.submitted_at === null ? null : round2((record.submitted_at - record.opened_at) / DAY),
      ];
      const base = [p.participant_code, p.condition, record.id, record.version];
      for (const instrument of batteryInstruments(record.id, p.condition)) {
        for (const item of visibleItems(instrument, record.answers)) {
          const reached = item.id in record.answers || record.submitted_at !== null;
          if (!reached) continue;
          const value = record.answers[item.id] ?? null;
          push(["item", ...base, instrument.id, item.id, value, value === null, null, ...timing]);
        }
      }
      for (const s of scoreBattery(record, p.condition)) {
        push(["score", ...base, s.instrument, s.id, s.score, null, s.complete, ...timing]);
      }
    }
  }
  return lines.join("\n") + "\n";
}
