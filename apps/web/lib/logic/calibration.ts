import type { Confidence, Jol, NextSessionTask, ResponseRecord, Video } from "@/lib/types";

const LABEL: Record<Confidence, string> = { certain: "Certain", pretty: "Pretty sure", guess: "Guessing" };
const ORDER: Confidence[] = ["certain", "pretty", "guess"];
const MIN_RATED = 5;

export interface Block1 {
  ready: boolean;
  rated: number;
  rows: { confidence: Confidence; label: string; right: number; n: number }[];
  sentences: string[];
}

/** Plan Q35 block 1. A correct answer after "Show a hint" still counts as right here:
 *  this measures confidence accuracy, not the level. */
export function calibrationBlock1(responses: ResponseRecord[]): Block1 {
  const rated = responses.filter((r) => r.context === "checkpoint" && r.confidence && r.choice !== "not_sure");
  const rows = ORDER.map((c) => {
    const mine = rated.filter((r) => r.confidence === c);
    return { confidence: c, label: LABEL[c], right: mine.filter((r) => r.correct).length, n: mine.length };
  });
  const sentences: string[] = [];
  if (rated.length >= MIN_RATED) {
    const by = Object.fromEntries(rows.map((r) => [r.confidence, r])) as Record<Confidence, (typeof rows)[number]>;
    const rate = (x: { right: number; n: number }) => (x.n ? x.right / x.n : 0);
    if (by.certain.n >= 2 && by.pretty.n >= 2 && rate(by.certain) <= rate(by.pretty)) {
      sentences.push(`Your “Certain” answers were right ${by.certain.right} times in ${by.certain.n}, no better than “Pretty sure”.`);
    }
    if (by.guess.n >= 2 && rate(by.guess) < 0.5) {
      sentences.push("Your guesses were honest: you were usually wrong when you said so.");
    }
    if (sentences.length === 0) sentences.push("Your confidence matches your results well.");
  }
  return { ready: rated.length >= MIN_RATED, rated: rated.length, rows, sentences };
}

export interface Block2 {
  pairs: { video_id: string; title: string; jol: Jol; correct: boolean }[];
  summary: string | null;
}

const JOL_WORD: Record<Jol, string> = { yes: "Yes", maybe: "Maybe", no: "No" };

/** Plan Q35 block 2: the student's own guess against the next-day result. */
export function calibrationBlock2(tasks: NextSessionTask[], videos: Video[]): Block2 {
  const title = (id: string) => videos.find((v) => v.id === id)?.short_title ?? id;
  const done = tasks
    .filter((t) => t.done && t.result && t.jol)
    .sort((a, b) => (b.result!.at - a.result!.at))
    .slice(0, 5);
  const pairs = done.map((t) => ({ video_id: t.video_id, title: title(t.video_id), jol: t.jol as Jol, correct: t.result!.correct }));
  let summary: string | null = null;
  if (pairs.length >= 3) {
    const groups = (["yes", "maybe", "no"] as Jol[]).map((j) => ({ j, n: pairs.filter((p) => p.jol === j).length, right: pairs.filter((p) => p.jol === j && p.correct).length }));
    const best = groups.reduce((a, b) => (b.n > a.n ? b : a));
    if (best.n > 0) summary = `When you said ${JOL_WORD[best.j]}, you got the next-day question right ${best.right} of ${best.n} times.`;
  }
  return { pairs, summary };
}
