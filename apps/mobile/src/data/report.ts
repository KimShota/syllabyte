/** Helpers for the report form (app/report.tsx). */

/** "1:05" or "65" as seconds; "" is no time (null); anything else is not a time (undefined). */
export function parseClock(s: string): number | null | undefined {
  const v = s.trim();
  if (!v) return null;
  const m = /^(\d{1,3}):([0-5]?\d)$/.exec(v);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  return /^\d{1,5}$/.test(v) ? Number(v) : undefined;
}

/** Seconds as "m:ss". */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** A question's stem on one card: code blocks and runs of spaces folded, so the picker stays short. */
export function stemPreview(stem: string): string {
  return stem.replace(/```[\s\S]*?(```|$)/g, " [code] ").replace(/\s+/g, " ").trim();
}
