import type { AwayRecord, PromptKind } from "../learning";

/**
 * When the app offers a prompt by itself (plan/engagement-feedback-implementation-plan.md, "Automatic feedback"). A
 * just-in-time adaptive intervention in the sense of Nahum-Shani et al. (2018): decision points (the move to the next
 * video, the return to the app, the end of a session), tailoring variables (below), and "no prompt" as the default.
 *
 * Behaviour alone never says why a student moved on or left the app (familiar material, searching, a message), so a drop
 * in behaviour only ever triggers a question and a retrieval exercise, which help whatever the cause (Szpunar et al.
 * 2013), never a verdict. The numbers are starting points to pilot, not values from the literature; they are versioned
 * so the data says which policy a student saw.
 */
export const DRIFT_POLICY = {
  version: "drift-1",
  /** a video counts as left early when the student moved on before this share of it played */
  earlyCoverage: 0.5,
  /** this many early leaves in a row is enough on its own */
  earlyStreakAlone: 3,
  /** this many in a row counts as one signal, combined with another */
  earlyStreakPart: 2,
  /** an absence from the app shorter than this is ignored (a glance at a notification) */
  awayMinS: 15,
  /** this many absences within `awayWindowMs` count as one signal */
  awayCount: 2,
  awayWindowMs: 10 * 60_000,
  /** this many wrong of the last 3 checkpoint answers count as one signal */
  errorsOf3: 2,
  /** automatic prompts of each kind per session, and the gap between two automatic prompts */
  maxPerSession: 2,
  cooldownMs: 5 * 60_000,
  /** returning after at least this long away offers the welcome-back recall (shorter: just carry on) */
  welcomeBackMinS: 60,
  /** a welcome back needs the video to be this far in, and not at its end */
  welcomeBackMinPosition: 20,
  /** a session with no activity for this long has ended */
  sessionGapMs: 10 * 60_000,
} as const;

/** One time a video was on screen, in the order they came. */
export interface Visit {
  videoId: string;
  firstAt: number;
  /** unique share of the video that played, 0-1 */
  coverage: number;
  completed: boolean;
}

export interface DriftInput {
  now: number;
  /** visits before the one the student just moved to, oldest first */
  visits: Visit[];
  away: AwayRecord[];
  /** this session's checkpoint answers, oldest first */
  answers: { correct: boolean | null; at: number }[];
  /** automatic prompts already shown in this session */
  prompts: { kind: PromptKind; shownAt: number }[];
}

export interface DriftDecision {
  fire: boolean;
  /** the signals present, e.g. ["early_leaves:3"]; filled even when the budget holds the prompt back */
  evidence: string[];
  /** why nothing was shown, when something was observed */
  heldBack?: "budget" | "cooldown";
}

const isEarly = (v: Visit, p = DRIFT_POLICY) => !v.completed && v.coverage < p.earlyCoverage;

/**
 * Whether to offer a drift check at the move to the next video. Only evidence since the last automatic prompt counts, so
 * a dismissed prompt is never re-offered for the same observations.
 */
export function driftDecision(input: DriftInput, p = DRIFT_POLICY): DriftDecision {
  const since = Math.max(0, ...input.prompts.map((x) => x.shownAt));
  const visits = input.visits.filter((v) => v.firstAt > since);
  let streak = 0;
  for (let i = visits.length - 1; i >= 0 && isEarly(visits[i], p); i--) streak += 1;
  const away = input.away.filter((a) => a.at > since && a.at > input.now - p.awayWindowMs && a.seconds >= p.awayMinS).length;
  const recent = input.answers.filter((a) => a.at > since).slice(-3);
  const errors = recent.filter((a) => a.correct === false).length;

  const evidence: string[] = [];
  if (streak >= p.earlyStreakPart) evidence.push(`early_leaves:${streak}`);
  if (away >= p.awayCount) evidence.push(`away:${away}`);
  if (errors >= p.errorsOf3) evidence.push(`errors:${errors}`);
  const fire = streak >= p.earlyStreakAlone || evidence.length >= 2;
  if (!fire) return { fire: false, evidence };

  const drift = input.prompts.filter((x) => x.kind === "drift_check");
  if (drift.length >= p.maxPerSession) return { fire: false, evidence, heldBack: "budget" };
  if (input.prompts.some((x) => input.now - x.shownAt < p.cooldownMs)) return { fire: false, evidence, heldBack: "cooldown" };
  return { fire: true, evidence };
}

/** Whether to offer the welcome-back recall when the student returns to the app partway through a video. */
export function welcomeBackDecision(
  e: { awaySeconds: number; position: number; duration: number; prompts: { kind: PromptKind; shownAt: number }[] },
  p = DRIFT_POLICY,
): boolean {
  if (e.awaySeconds < p.welcomeBackMinS || e.awaySeconds * 1000 >= p.sessionGapMs) return false;
  if (e.position < p.welcomeBackMinPosition || e.position > e.duration - 5) return false;
  return e.prompts.filter((x) => x.kind === "welcome_back").length < p.maxPerSession;
}

/** What happened, in plain words, from a drift check's evidence: an observation, never a judgement about the student. */
export function driftObservation(evidence: string[]): string {
  const parts: string[] = [];
  for (const e of evidence) {
    const [key, n] = e.split(":");
    if (key === "early_leaves") parts.push(`moved on early from the last ${n} videos`);
    if (key === "away") parts.push(`left the app ${n} times`);
    if (key === "errors") parts.push(`missed ${n} of the last checks`);
  }
  if (!parts.length) return "Quick check-in.";
  const text = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}`;
  return `You ${text}.`;
}
