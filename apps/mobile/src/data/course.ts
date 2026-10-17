/**
 * The course as the mobile screens draw it, built from the shared fixtures (packages/core/fixtures: gitignored,
 * because they come from the course's own slides): the lectures, every KU and its title, which KUs have a video,
 * and the videos' narration. What the design shows but the pipeline doesn't make yet is placeholder data here:
 * the professor, term and exam, lecture dates, the sections of a lecture, the lectures still to come, the other
 * courses, and the slides the "Analyzing" screen cycles through.
 */
import { FIX } from "@syllabyte/core/fixtures";
import type { KuEntry, Video } from "@syllabyte/core/types";
import type { CourseDef, CourseStub, Ku, LectureDef, LectureSectionDef, Scene, TranscriptLine } from "./types";

/** the length the stand-in frame plays for when a KU has no video yet */
const STAND_IN_S = 75;

function statement(framework: string, headline: string, points: string[]): Scene {
  return { kind: "statement", framework, headline, points };
}

/** The design's equation frames (immersive_reels_video_player); every other KU gets a plain title frame. */
const SCENES: Record<string, Scene> = {
  "ku-potential-outcomes": {
    kind: "equation",
    framework: "Potential Outcome Framework",
    subtitle: "One person, two worlds",
    terms: [{ symbol: "Y1,i", label: "Insured" }, { symbol: "Y0,i", label: "Uninsured" }],
    ops: ["|"],
    diagram: { left: "Insured", middle: "Same person", right: "Uninsured" },
  },
  "ku-individual-causal-effect": {
    kind: "equation",
    framework: "Potential Outcome Framework",
    subtitle: "Individual Level Equation",
    terms: [{ symbol: "Y_i(1)", label: "Treated" }, { symbol: "Y_i(0)", label: "Untreated" }, { symbol: "τ_i", label: "Effect", highlight: true }],
    ops: ["−", "="],
    diagram: { left: "Observed", middle: "Counterfactual Gap", right: "Missing" },
  },
};

/** Placeholder sections (the pipeline doesn't group KUs yet), by lecture; KUs not listed join a last section. */
const SECTIONS: Record<number, LectureSectionDef[]> = {
  1: [
    { id: "causal-questions", title: "Causal questions", kuIds: ["ku-random-assignment-origin", "ku-health-insurance-question", "ku-outcome-measure-health-index", "ku-treatment-control-sample", "ku-reading-difference-table", "ku-apples-oranges-confounders"] },
    { id: "potential-outcomes", title: "Potential outcomes", kuIds: ["ku-potential-outcomes", "ku-individual-causal-effect", "ku-fundamental-problem-observable-outcome", "ku-naive-comparison-timmy-spike"] },
  ],
  2: [
    { id: "decomposing", title: "Decomposing the difference", kuIds: ["ku-selection-bias-decomposition", "ku-selection-bias-general-formula"] },
    { id: "large-samples", title: "Large samples", kuIds: ["ku-law-of-large-numbers", "ku-lln-eliminates-selection-bias"] },
  ],
  3: [
    { id: "coin-toss", title: "The coin-toss example", kuIds: ["ku-coin-toss-average-causal-effect", "ku-balance-checking"] },
    { id: "rand-hie", title: "The RAND experiment", kuIds: ["ku-rand-hie-design", "ku-rand-hie-balance-tables", "ku-rand-hie-results", "ku-summary-avoiding-selection-bias"] },
  ],
};

const DATES = ["Sep 08", "Sep 15", "Sep 22", "Sep 29", "Oct 06", "Oct 13"];
/** lectures on the syllabus whose slides aren't in yet (placeholders) */
const UPCOMING = ["Natural experiments", "Text as data"];

const videos = new Map<string, Video>(FIX.videos.map((v) => [v.id, v]));

/** "Diagram: Coin decides — A coin mid-flip…" -> "Coin decides" */
function heading(visual: string | null): string | undefined {
  return visual?.match(/^[^:]+:\s*(.+?)\s+—/)?.[1];
}

function transcript(video: Video): TranscriptLine[] {
  return video.transcript.map((r) => ({ t: r.t, text: r.narration, heading: heading(r.visual) }));
}

/** The slides a KU is made from: its video's, else the ones its questions cite, else its lecture's. */
function slideSpan(ku: KuEntry, video: Video | undefined): [number, number] {
  let slides = video?.source_slides ?? [];
  if (!slides.length) slides = FIX.items.filter((i) => i.ku_id === ku.id).flatMap((i) => i.source_refs.map((r) => r.slide_number));
  if (!slides.length) {
    const l = FIX.course.lectures.find((x) => x.n === ku.lecture_n);
    return l ? [l.slide_start, l.slide_end] : [1, 1];
  }
  return [Math.min(...slides), Math.max(...slides)];
}

const lectureTitle = (n: number) => FIX.course.lectures.find((l) => l.n === n)?.title ?? `Lecture ${n}`;

export const KUS: Record<string, Ku> = Object.fromEntries(
  FIX.course.kus.map((k): [string, Ku] => {
    const video = k.video_id ? videos.get(k.video_id) : undefined;
    return [
      k.id,
      {
        id: k.id,
        title: k.title,
        shortTitle: k.short_title,
        lectureN: k.lecture_n,
        videoId: video ? video.id : null,
        slides: slideSpan(k, video),
        durationS: video?.duration_s ?? STAND_IN_S,
        scene: SCENES[k.id] ?? statement(lectureTitle(k.lecture_n), k.short_title, []),
        transcript: video ? transcript(video) : [],
      },
    ];
  }),
);

function sections(n: number): LectureSectionDef[] {
  const ids = FIX.course.kus.filter((k) => k.lecture_n === n).map((k) => k.id);
  const known = (SECTIONS[n] ?? [])
    .map((s) => ({ ...s, kuIds: s.kuIds.filter((id) => ids.includes(id)) }))
    .filter((s) => s.kuIds.length > 0);
  const placed = new Set(known.flatMap((s) => s.kuIds));
  const rest = ids.filter((id) => !placed.has(id));
  if (rest.length) known.push({ id: `lecture-${n}-more`, title: known.length ? "More topics" : lectureTitle(n), kuIds: rest });
  return known;
}

const made: LectureDef[] = FIX.course.lectures.map((l) => ({ n: l.n, title: l.title, date: DATES[l.n - 1], hasSlides: true, sections: sections(l.n) }));
const lastN = Math.max(0, ...made.map((l) => l.n));

export const COURSE: CourseDef = {
  id: FIX.course.id,
  code: FIX.course.code,
  name: FIX.course.name,
  professor: "Prof. Al-Mansoori",
  term: "Fall 2026",
  roadmapEyebrow: `${FIX.course.code} · Roadmap`,
  finalExam: { title: "Final Exam", subtitle: "December 14 · Comprehensive Review" },
  lecturesPlanned: 14,
  lectures: [
    ...made,
    ...UPCOMING.map((title, i) => ({ n: lastN + i + 1, title, date: DATES[lastN + i], hasSlides: false, sections: [] })),
  ],
};

/** The other courses on Home and in the drawer; they have no lectures in this build. */
export const OTHER_COURSES: CourseStub[] = [
  { id: "econ-micro-2", code: "ECON-UA 11", name: "Microeconomic Theory II", term: "Fall 2026", progress: 0.4, lecturesDone: 5, lecturesPlanned: 12 },
  { id: "ml-causal", code: "DS-GA 3001", name: "Machine Learning & Causal Inference", term: "Fall 2026", progress: 0.15, lecturesDone: 2, lecturesPlanned: 13 },
  { id: "intro-neuro", code: "NEURO-UA 100", name: "Introduction to Neuroscience", term: "Fall 2026", progress: 0, lecturesDone: 0, lecturesPlanned: 14, analyzing: { progress: 0.48 } },
];

/** Slides the "Analyzing your materials" screen cycles through. */
export const ANALYZER_SLIDES: { n: number; title: string; boxes: [string, string, string]; captions: [string, string, string] }[] = [
  { n: 3, title: "Does insurance improve health?", boxes: ["Insured", "Health index", "Uninsured"], captions: ["Treated", "Outcome", "Control"] },
  { n: 10, title: "Potential outcomes", boxes: ["Y1,i", "Person i", "Y0,i"], captions: ["With insurance", "Same moment", "Without"] },
  { n: 17, title: "Selection bias", boxes: ["Difference", "= Effect", "+ Bias"], captions: ["In means", "Causal", "Selection"] },
  { n: 25, title: "Randomization", boxes: ["Coin toss", "Groups", "Balance"], captions: ["Assignment", "Comparable", "Checked"] },
];
export const ANALYZER_TOTAL_SLIDES = Math.max(1, ...FIX.course.lectures.map((l) => l.slide_end));
