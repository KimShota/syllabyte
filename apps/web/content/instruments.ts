import type { Condition } from "@/lib/types";

/**
 * The study's questionnaires as data (plan/study-instruments-plan.md, decisions I3-I7). Wording is the instruments'
 * own, changed only where the plan says so. Bump INSTRUMENTS_VERSION whenever any wording or option changes: every
 * answer is stored with the version it was given under.
 */
export const INSTRUMENTS_VERSION = "2026-10-14";

export type InstrumentId = "demographics" | "tlx" | "sus" | "efficacy" | "trust";

export interface Option {
  value: string;
  label: string;
}

export type ResponseFormat =
  /** whole numbers from min to max in steps; the two anchors label the ends */
  | { kind: "scale"; min: number; max: number; step: number; anchors: [string, string] }
  | { kind: "choice"; options: Option[] }
  | { kind: "text"; placeholder?: string };

export interface InstrumentItem {
  id: string;
  text: string;
  response: ResponseFormat;
  /** scored as (min + max − answer) */
  reverse?: boolean;
  /** shown only when another item has this answer (the gender self-description) */
  showIf?: { item: string; value: string };
  /** a short name for the export and the scoring notes, e.g. "mental" */
  label?: string;
}

export interface Instrument {
  id: InstrumentId;
  title: string;
  /** one line above the items */
  intro: string;
  source: string;
  /** who is asked */
  conditions: Condition[];
  items: InstrumentItem[];
}

export const PREFER_NOT: Option = { value: "prefer_not", label: "Prefer not to say" };

const likert7: ResponseFormat = { kind: "scale", min: 1, max: 7, step: 1, anchors: ["Not at all", "Extremely"] };
const agree5: ResponseFormat = { kind: "scale", min: 1, max: 5, step: 1, anchors: ["Strongly disagree", "Strongly agree"] };
const tlx = (low: string, high: string): ResponseFormat => ({ kind: "scale", min: 0, max: 100, step: 5, anchors: [low, high] });
const choice = (...labels: string[]): ResponseFormat => ({
  kind: "choice",
  options: [...labels.map((label) => ({ value: label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, ""), label })), PREFER_NOT],
});

export const DEMOGRAPHICS: Instrument = {
  id: "demographics",
  title: "About you",
  intro: "This helps us describe who took part. Every question has “Prefer not to say”.",
  source: "Study-specific (plan I6)",
  conditions: ["A", "B"],
  items: [
    { id: "year", label: "year", text: "Year of study", response: choice("1st year", "2nd year", "3rd year", "4th year", "Other") },
    { id: "major", label: "major", text: "Major or intended major", response: { kind: "text", placeholder: "e.g. Economics" } },
    {
      id: "prior_course", label: "prior_course", text: "Have you taken a course on this subject before?",
      response: choice("No", "Yes, at school", "Yes, at university"),
    },
    {
      id: "familiarity", label: "familiarity", text: "How familiar are you with this course’s topics?",
      response: choice("1 Not at all", "2", "3", "4", "5 Very"),
    },
    {
      id: "short_video_use", label: "short_video_use",
      text: "How often do you watch short educational videos (TikTok, YouTube Shorts, Reels)?",
      response: choice("Never", "Less than weekly", "Weekly", "Several times a week", "Daily"),
    },
    { id: "english_first", label: "english_first", text: "Is English your first language?", response: choice("Yes", "No") },
    { id: "age", label: "age", text: "Age", response: choice("18–19", "20–21", "22–24", "25 or older") },
    { id: "gender", label: "gender", text: "Gender", response: choice("Woman", "Man", "Non-binary", "Prefer to self-describe") },
    {
      id: "gender_text", label: "gender_text", text: "In your own words (optional)",
      response: { kind: "text" }, showIf: { item: "gender", value: "prefer_to_self_describe" },
    },
  ],
};

export const TLX: Instrument = {
  id: "tlx",
  title: "How demanding was it?",
  intro: "Think about studying this module’s videos.",
  source: "NASA Task Load Index, Raw TLX (Hart & Staveland 1988; Hart 2006): six subscales, unweighted",
  conditions: ["A", "B"],
  items: [
    { id: "tlx_mental", label: "mental", text: "How mentally demanding was the task?", response: tlx("Very low", "Very high") },
    { id: "tlx_physical", label: "physical", text: "How physically demanding was the task?", response: tlx("Very low", "Very high") },
    { id: "tlx_temporal", label: "temporal", text: "How hurried or rushed was the pace of the task?", response: tlx("Very low", "Very high") },
    {
      id: "tlx_performance", label: "performance", text: "How successful were you in accomplishing what you were asked to do?",
      response: tlx("Perfect", "Failure"),
    },
    {
      id: "tlx_effort", label: "effort", text: "How hard did you have to work to accomplish your level of performance?",
      response: tlx("Very low", "Very high"),
    },
    {
      id: "tlx_frustration", label: "frustration", text: "How insecure, discouraged, irritated, stressed, and annoyed were you?",
      response: tlx("Very low", "Very high"),
    },
  ],
};

const SUS_TEXT = [
  "I think that I would like to use this app frequently.",
  "I found the app unnecessarily complex.",
  "I thought the app was easy to use.",
  "I think that I would need the support of a technical person to be able to use this app.",
  "I found the various functions in this app were well integrated.",
  "I thought there was too much inconsistency in this app.",
  "I would imagine that most people would learn to use this app very quickly.",
  "I found the app very cumbersome to use.",
  "I felt very confident using the app.",
  "I needed to learn a lot of things before I could get going with this app.",
];

export const SUS: Instrument = {
  id: "sus",
  title: "Using the app",
  intro: "How much do you agree with each statement about this app?",
  source: "System Usability Scale (Brooke 1996), “system” replaced by “app”",
  conditions: ["A", "B"],
  // Even items are worded negatively; the SUS formula handles them (scoreInstrument), so no reverse flag.
  items: SUS_TEXT.map((text, i) => ({ id: `sus_${i + 1}`, label: `sus_${i + 1}`, text, response: agree5 })),
};

const EFFICACY_TEXT = [
  "I was able to understand the topics well through these videos.",
  "I feel confident explaining these topics to others.",
  "The videos broke the topics down into manageable parts.",
  "The videos helped me remember the key points.",
  "The videos made it easy to revisit important concepts.",
  "The videos helped me stay focused.",
  "I felt engaged while watching the videos.",
  "I would like to learn future topics this way.",
  "The videos covered what I needed for this course.",
  "The examples in the videos were relevant to the course material.",
  "The pace of the videos was right for me.",
  "The videos were at the right level for what I already knew.",
];

export const EFFICACY: Instrument = {
  id: "efficacy",
  title: "Learning with these videos",
  intro: "How much does each statement describe your experience of this module’s videos?",
  source: "Adapted from ReelEd’s learning-efficacy questionnaire (Stavrinou et al. 2025); items 9–12 study-specific",
  conditions: ["A", "B"],
  items: EFFICACY_TEXT.map((text, i) => ({ id: `eff_${i + 1}`, label: `eff_${i + 1}`, text, response: likert7 })),
};

const TRUST_JIAN = [
  "SyllaByte is deceptive.",
  "SyllaByte behaves in an underhanded manner.",
  "I am suspicious of SyllaByte’s intent, action, or outputs.",
  "I am wary of SyllaByte.",
  "SyllaByte’s actions will have a harmful or injurious outcome.",
  "I am confident in SyllaByte.",
  "SyllaByte provides security.",
  "SyllaByte has integrity.",
  "SyllaByte is dependable.",
  "SyllaByte is reliable.",
  "I can trust SyllaByte.",
  "I am familiar with SyllaByte.",
];

const TRUST_STUDY = [
  "The videos were accurate to my course’s slides.",
  "The videos helped me learn.",
  "I would rely on these videos to study for this course in the future.",
  "I trust the levels SyllaByte chose for me.",
];

/** Jian et al.'s distrust items: reversed for the trust score. */
export const TRUST_REVERSED = new Set(["trust_1", "trust_2", "trust_3", "trust_4", "trust_5"]);

export const TRUST: Instrument = {
  id: "trust",
  title: "Trust in SyllaByte",
  intro: "SyllaByte here means the AI system that made your videos.",
  source: "Items 1–12: Jian, Bisantz & Drury (2000), “the system” replaced by “SyllaByte”; items 13–16 study-specific",
  conditions: ["A"],
  items: [...TRUST_JIAN, ...TRUST_STUDY].map((text, i) => ({
    id: `trust_${i + 1}`, label: `trust_${i + 1}`, text, response: likert7, reverse: TRUST_REVERSED.has(`trust_${i + 1}`),
  })),
};

export const INSTRUMENTS: Record<InstrumentId, Instrument> = {
  demographics: DEMOGRAPHICS, tlx: TLX, sus: SUS, efficacy: EFFICACY, trust: TRUST,
};

/** The baseline at sign-up and the battery at each module's end (plan I2), in the order they are asked. */
export const BATTERY_CONTENTS: Record<"baseline" | "module", InstrumentId[]> = {
  baseline: ["demographics"],
  // TLX first, while the module is freshest.
  module: ["tlx", "efficacy", "sus", "trust"],
};
