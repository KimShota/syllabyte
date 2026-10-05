import type { RecheckSlot } from "@/lib/types";
import { DAY } from "@/lib/util";

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

function at(base: Date, dayOffset: number, hour: number): number {
  const d = new Date(base);
  d.setDate(d.getDate() + dayOffset);
  d.setHours(hour, 0, 0, 0);
  return d.getTime();
}

/**
 * Week 7 invite slots (plan Q16), generated from the current time:
 * Now · Tonight 8:00 pm (hidden after 7 pm) · Tomorrow 9:00 am · Friday 9:00 am,
 * which becomes Monday from Thursday on so it never collides with "tomorrow".
 */
export function recheckSlots(now: number): RecheckSlot[] {
  const d = new Date(now);
  const slots: RecheckSlot[] = [{ id: "now", label: "Now", at: now }];
  if (d.getHours() < 19) slots.push({ id: "tonight", label: "Tonight at 8:00 pm", at: at(d, 0, 20) });
  slots.push({ id: "tomorrow", label: "Tomorrow morning", at: at(d, 1, 9) });
  const dow = d.getDay(); // 0 Sun … 6 Sat
  if (dow === 4 || dow === 5 || dow === 6) {
    const toMonday = (8 - dow) % 7 || 7;
    slots.push({ id: "monday", label: "Remind me on Monday", at: at(d, toMonday, 9) });
  } else {
    const toFriday = (5 - dow + 7) % 7;
    slots.push({ id: "friday", label: "Remind me on Friday", at: at(d, toFriday, 9) });
  }
  return slots;
}

const fmtDay = new Intl.DateTimeFormat("en-US", { weekday: "long" });
const fmtTime = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });

/** "Tonight at 8:00 PM" style text for confirmations. */
export function describeSlot(slot: RecheckSlot, now: number): string {
  if (slot.id === "now") return "now";
  const when = new Date(slot.at);
  const today = new Date(now);
  const sameDay = when.toDateString() === today.toDateString();
  const tomorrow = new Date(now + DAY).toDateString() === when.toDateString();
  const time = fmtTime.format(when).replace(" ", " ").toLowerCase();
  if (sameDay) return `tonight at ${time}`;
  if (tomorrow) return `tomorrow at ${time}`;
  return `${fmtDay.format(when)} at ${time}`;
}
