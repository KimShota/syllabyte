import type { Choice, Item, Level, ResponseRecord, Topic } from "@/lib/types";

export const LEVEL_NAMES: Record<Level, string> = { 1: "Foundations", 2: "Core", 3: "Advanced" };
export const LEVEL_BLURBS: Record<Level, string> = {
  1: "More steps, hints and a recap.",
  2: "Key steps, hints if you ask.",
  3: "Skips the basics, adds a “what if”.",
};

export function levelLabel(level: Level): string {
  return `Level ${level} · ${LEVEL_NAMES[level]}`;
}

export function isCorrect(item: Item, choice: Choice): boolean | null {
  if (choice === "not_sure") return null;
  return choice === item.correct_index;
}

export interface Counts {
  right: number;
  wrong: number;
  notSure: number;
}

export function countsFor(topicId: string, responses: ResponseRecord[], contexts?: string[]): Counts {
  const c: Counts = { right: 0, wrong: 0, notSure: 0 };
  for (const r of responses) {
    if (r.topic_id !== topicId) continue;
    if (contexts && !contexts.includes(r.context)) continue;
    if (r.choice === "not_sure") c.notSure += 1;
    else if (r.correct) c.right += 1;
    else c.wrong += 1;
  }
  return c;
}

export interface OnboardingLevel {
  level: Level;
  reason: string;
  notChecked: boolean;
}

/** Plan §4.1. "Not sure" is missing evidence, never wrong (rule 3). */
export function onboardingLevel(
  topic: Topic,
  items: Item[],
  answers: Record<string, Choice>,
  lectureTitle?: string,
): OnboardingLevel {
  const own = items
    .filter((i) => i.context === "onboarding" && i.topic_id === topic.id)
    .sort((a, b) => a.id.localeCompare(b.id));
  const t = `“${topic.title}”`;
  if (own.length === 0) {
    return {
      level: 1,
      notChecked: true,
      reason: `Not covered yet. We will check this when ${lectureTitle ?? "its lecture"} comes up.`,
    };
  }
  let right = 0;
  let wrong = 0;
  for (const it of own) {
    const a = answers[it.id];
    if (a === undefined || a === "not_sure") continue;
    if (a === it.correct_index) right += 1;
    else wrong += 1;
  }
  const answered = right + wrong;
  const n = own.length;

  const allOf = (k: number) => (k === 2 ? "both" : `all ${k}`);

  if (answered === 0) {
    return {
      level: 1,
      notChecked: false,
      reason: `You chose “Not sure” on ${allOf(n)} questions on ${t}, so videos start from the basics with more hints.`,
    };
  }
  if (answered >= 2) {
    if (right === answered) return { level: 3, notChecked: false, reason: `You answered ${allOf(answered)} questions on ${t} correctly, so we skip the basics here.` };
    if (right === 0) return { level: 1, notChecked: false, reason: `You missed ${allOf(answered)} questions on ${t}, so videos start from the basics with more hints.` };
    return { level: 2, notChecked: false, reason: `Right on ${right} of ${answered} questions on ${t}. Mixed, so we use medium pacing.` };
  }
  // exactly one answered
  if (right === 1) {
    return {
      level: 2,
      notChecked: false,
      reason: `Right on one question on ${t}, “Not sure” on the other. Mixed, so we use medium pacing.`,
    };
  }
  return {
    level: 1,
    notChecked: false,
    reason: `Wrong on one question on ${t}, “Not sure” on the other, so videos start from the basics with more hints.`,
  };
}

/** Median of the topic levels, rounded down when mixed (rule 7: lean toward more help). */
export function overallLevel(levels: Level[]): Level {
  if (levels.length === 0) return 1;
  const sorted = [...levels].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) / 2)];
}
