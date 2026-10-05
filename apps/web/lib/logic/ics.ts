/** A one-event calendar file for the Week 7 check-in slot (plan Q16). */
export function icsFor(opts: { title: string; description: string; start: number; minutes: number; uid: string }): string {
  const fmt = (ms: number) => new Date(ms).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const esc = (s: string) => s.replace(/\\/g, "\\\\").replace(/;/g, "\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//SyllaByte//Week 7 check-in//EN",
    "BEGIN:VEVENT",
    `UID:${opts.uid}@syllabyte`,
    `DTSTAMP:${fmt(Date.now())}`,
    `DTSTART:${fmt(opts.start)}`,
    `DTEND:${fmt(opts.start + opts.minutes * 60_000)}`,
    `SUMMARY:${esc(opts.title)}`,
    `DESCRIPTION:${esc(opts.description)}`,
    "END:VEVENT",
    "END:VCALENDAR",
    "",
  ].join("\r\n");
}
