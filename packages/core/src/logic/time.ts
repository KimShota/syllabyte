import { DAY } from "../util";

export function weekOf(now: number, semesterStart: number): number {
  return Math.max(1, Math.floor((now - semesterStart) / (7 * DAY)) + 1);
}

/** Monday 00:00 local of the week containing `ts`. */
export function startOfWeek(ts: number): number {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  const day = (d.getDay() + 6) % 7; // Monday = 0
  d.setDate(d.getDate() - day);
  return d.getTime();
}
