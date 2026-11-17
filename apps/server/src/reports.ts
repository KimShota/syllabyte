import { reportCategoryLabel } from "@syllabyte/core/content/reports";
import type { DemoState, ReportRecord } from "@syllabyte/core/types";
import type { Db } from "./db";

/**
 * Every student's error reports, for the research team (consent text: "if something in a video seems wrong ... you can
 * report the error in the app"; "Error reports you send about a video may be shared with the instructor without your
 * name"). A report lives in the student's course document; this reads them all, newest first. Rows carry the study
 * code, never a name or email, so the list can be passed on as it is.
 */
export interface ReportRow {
  report_id: string;
  at: string;
  status: ReportRecord["status"];
  participant_code: string;
  /** whether the student consented to research; reports are kept either way, since they are about the app */
  research_consent: boolean;
  course_id: string;
  course: string;
  target: "video" | "question" | "app";
  /** the video's or question's id; "" for the app */
  target_id: string;
  lecture_n: number | null;
  /** what was reported, as the student saw it */
  about: string;
  category: string;
  category_label: string;
  video_t: number | null;
  note: string;
  screen: string;
}

export function allReports(db: Db, describeCourse: (courseId: string) => string): ReportRow[] {
  const rows = db
    .prepare("SELECT c.course_id, c.json AS doc, p.json AS profile FROM course_state c LEFT JOIN user_profile p ON p.user_id = c.user_id")
    .all() as { course_id: string; doc: string; profile: string | null }[];
  const out: ReportRow[] = [];
  for (const r of rows) {
    const doc = JSON.parse(r.doc) as Partial<DemoState>;
    if (!doc.reports?.length) continue;
    const profile = (r.profile ? JSON.parse(r.profile) : {}) as Partial<DemoState>;
    const course = describeCourse(r.course_id);
    for (const rep of doc.reports) {
      const target = rep.target ?? "video";
      out.push({
        report_id: rep.id,
        at: new Date(rep.at).toISOString(),
        status: rep.status,
        participant_code: profile.participant_code ?? "",
        research_consent: profile.consent === "research",
        course_id: r.course_id,
        course,
        target,
        target_id: target === "video" ? rep.video_id : target === "question" ? (rep.item_id ?? "") : "",
        lecture_n: rep.lecture_n ?? null,
        about: rep.about ?? "",
        category: rep.category,
        category_label: reportCategoryLabel(target, rep.category),
        video_t: rep.video_t ?? null,
        note: rep.note,
        screen: rep.screen ?? "",
      });
    }
  }
  return out.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}

const COLUMNS: (keyof ReportRow)[] = [
  "report_id", "at", "status", "participant_code", "research_consent", "course_id", "course", "target", "target_id", "lecture_n",
  "about", "category", "category_label", "video_t", "note", "screen",
];

/**
 * A cell students wrote: quoted when it must be, and never read as a formula by a spreadsheet (a note that starts
 * with "=" would otherwise run when the researcher opens the file).
 */
function cell(v: string | number | boolean | null): string {
  if (v === null) return "";
  let s = String(v);
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function reportsCsv(rows: ReportRow[]): string {
  return [COLUMNS.join(","), ...rows.map((r) => COLUMNS.map((k) => cell(r[k])).join(","))].join("\n") + "\n";
}
