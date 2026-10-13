import type { Choice, Item, Level } from "@/lib/types";

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

/** Median of the KU levels, rounded down when mixed (rule 7: lean toward more help). */
export function overallLevel(levels: Level[]): Level {
  if (levels.length === 0) return 1;
  const sorted = [...levels].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) / 2)];
}
