import type { AppReportCategory, ProblemCategory, QuestionReportCategory, ReportCategory, ReportTarget } from "../types";

/**
 * What a student can report, and the words each app shows for it. The consent text promises "if something in a video
 * seems wrong ... you can report the error in the app"; questions and the app itself can be reported the same way.
 */
export const REPORT_TARGETS: { id: ReportTarget; label: string; hint: string }[] = [
  { id: "video", label: "A video", hint: "Something in a video is wrong or hard to follow" },
  { id: "question", label: "A quiz question", hint: "A question or its answer seems wrong" },
  { id: "app", label: "Something else", hint: "The app isn't working, or anything else" },
];

export const VIDEO_REPORT_CATEGORIES: { id: ReportCategory; label: string }[] = [
  { id: "fact", label: "A fact is wrong" },
  { id: "picture", label: "The picture doesn't match what's said" },
  { id: "captions", label: "Captions or audio are off" },
  { id: "layout", label: "Text is cut off or overlaps" },
  { id: "other", label: "Something else" },
];

export const QUESTION_REPORT_CATEGORIES: { id: QuestionReportCategory; label: string }[] = [
  { id: "answer_wrong", label: "The right answer is wrong, or more than one is right" },
  { id: "unclear", label: "The question is unclear" },
  { id: "not_in_slides", label: "It isn't from my course's slides" },
  { id: "display", label: "Text, code or a formula shows wrong" },
  { id: "other", label: "Something else" },
];

export const APP_REPORT_CATEGORIES: { id: AppReportCategory; label: string }[] = [
  { id: "bug", label: "Something isn't working" },
  { id: "upload", label: "A problem with my syllabus or slides" },
  { id: "other", label: "Something else" },
];

export const REPORT_CATEGORIES: Record<ReportTarget, readonly { id: ProblemCategory; label: string }[]> = {
  video: VIDEO_REPORT_CATEGORIES,
  question: QUESTION_REPORT_CATEGORIES,
  app: APP_REPORT_CATEGORIES,
};

/** The longest note a report keeps. */
export const REPORT_NOTE_MAX = 1000;

/** Whether the student must say what happened: a report about the app has nothing else to go on. */
export function reportNeedsNote(target: ReportTarget, category: ProblemCategory): boolean {
  return target === "app" || category === "other";
}

export function reportCategoryLabel(target: ReportTarget, category: ProblemCategory): string {
  return REPORT_CATEGORIES[target].find((c) => c.id === category)?.label ?? category;
}
