/**
 * View-model types for the mobile screens: the shapes the design draws, built from the shared domain types
 * (@syllabyte/core/types: Course, KuEntry, Item, Video…) in ./course.ts.
 */

export interface TranscriptLine {
  /** seconds */
  t: number;
  text: string;
  /** a short label for the transcript list */
  heading?: string;
}

/** What the player draws while there's no rendered video file for a KU (the design's motion-graphic frame). */
export type Scene =
  | {
      kind: "equation";
      framework: string;
      subtitle: string;
      terms: { symbol: string; label: string; highlight?: boolean }[];
      /** operators between terms, e.g. ["−", "="] */
      ops: string[];
      diagram?: { left: string; middle: string; right: string };
    }
  | { kind: "statement"; framework: string; headline: string; points: string[] };

/** A Knowledge Unit as the roadmap and player see it. */
export interface Ku {
  id: string;
  title: string;
  shortTitle: string;
  lectureN: number;
  /** "slides" counter on the player, e.g. [10, 11] */
  slides: [number, number];
  durationS: number;
  /** the KU's video in the core's data; null while it is still being made from the slides */
  videoId: string | null;
  /** the video's file, once the player plays files; until then, and without one, the player draws `scene` */
  videoUri?: string;
  scene: Scene;
  transcript: TranscriptLine[];
}

export interface LectureSectionDef {
  id: string;
  title: string;
  kuIds: string[];
}

export interface LectureDef {
  n: number;
  title: string;
  /** e.g. "Oct 22"; shown on the roadmap card */
  date?: string;
  /** false: the slides for it haven't been uploaded or processed yet */
  hasSlides: boolean;
  /** bottom-to-top on the lecture roadmap */
  sections: LectureSectionDef[];
}

export interface CourseDef {
  id: string;
  code: string;
  name: string;
  professor: string;
  term: string;
  /** e.g. "ECON 204B · ROADMAP" eyebrow on the lecture roadmap */
  roadmapEyebrow: string;
  finalExam: { title: string; subtitle: string };
  lectures: LectureDef[];
  /** total planned lectures on the syllabus (more than the ones listed) */
  lecturesPlanned: number;
}

/** Courses on Home / in the drawer that have no content in this build. */
export interface CourseStub {
  id: string;
  code: string;
  name: string;
  term: string;
  /** 0..1 */
  progress: number;
  lecturesDone: number;
  lecturesPlanned: number;
  analyzing?: { progress: number };
}

export type KuStatus = "watched" | "next" | "available" | "drafting";
export type LectureStatus = "completed" | "active" | "available" | "awaiting";

export interface Note {
  id: string;
  /** seconds into the video when it was written */
  at: number;
  text: string;
}
