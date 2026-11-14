import type { Confidence, Difficulty } from "./types";

export type PlaybackInterval = [number, number];
export interface PlaybackSnapshot {
  sequence: number;
  intervals: PlaybackInterval[];
  elapsed_s: number;
  exposure_s: number;
  position_s: number;
  duration_s: number;
  source: "video" | "demo";
}
export interface LearningContext { sessionId: string; courseId: string }
export interface LearningPlaybackInput extends LearningContext {
  playbackId: string;
  videoId: string;
  snapshot: PlaybackSnapshot;
}
export type AttentionReport = "on_task" | "drifted";
export interface LearningCheckInInput extends LearningContext {
  responseId: string;
  difficulty: Difficulty | null;
  attention: AttentionReport | null;
}
export type FeedbackRule = "confidence_mismatch" | "difficulty_support" | "attention_recovery" | "review_acknowledgment" | "reflection";
export type FeedbackAction = "continue" | "replay";
export interface LearningFeedback {
  rule: FeedbackRule;
  message: string;
  replayFrom: number;
  policyVersion: "1";
}
export interface LearningCheckIn extends LearningCheckInInput {
  id: string;
  videoId: string;
  at: number;
  feedback: LearningFeedback;
  action: FeedbackAction | null;
  actionAt: number | null;
}
/** The student left the app (backgrounded it) during a learning session and came back after `seconds`. */
export interface AwayRecord { at: number; seconds: number; videoId: string | null }

/**
 * A prompt the app offered by itself at a decision point (plan/engagement-feedback-implementation-plan.md, "Automatic
 * feedback"). `drift_check`: signs the student's engagement dropped, at the move to the next video. `welcome_back`: the
 * student came back to the app partway through a video.
 */
export type PromptKind = "drift_check" | "welcome_back";
/** The answer to "where was your attention?" in a drift check (Seli et al. 2016: deliberate vs unintended drift). */
export type DriftAnswer = "on_task" | "drifted" | "familiar" | "searching";
export type PromptAction = "continue" | "rewatch" | "replay" | "pause";
export interface LearningPrompt {
  id: string;
  kind: PromptKind;
  policyVersion: string;
  /** the observations that fired it, e.g. "early_leaves:3", "away:2", "errors:2", "away_s:95" */
  evidence: string[];
  /** what happened, in plain words, shown to the student (never a judgement about them) */
  observation: string;
  /** the video to recall: the last one really watched (drift) or the one on screen (welcome back) */
  recall: { videoId: string; title: string; points: string[]; replayFrom: number } | null;
  shownAt: number;
  answer: DriftAnswer | null;
  action: PromptAction | null;
  respondedAt: number | null;
}

export type SessionEndReason = "left" | "gap";
/** The short reflection the app shows by itself when a session ends: one observation and one next step. */
export interface SessionSummary {
  sessionId: string;
  observation: string;
  nextStep: string;
  /** e.g. "2 videos · 1 of 2 checks right · 4 min of playback" */
  stats: string;
  reason: SessionEndReason;
  createdAt: number;
}

export interface LearningSession {
  id: string;
  courseId: string;
  startedAt: number;
  updatedAt: number;
  /** one row per time a video was on screen; `firstAt` orders them (missing on rows saved before it existed) */
  playback: Record<string, { videoId: string; snapshot: PlaybackSnapshot; receivedAt: number; firstAt?: number }>;
  completedVideos: string[];
  checkIns: LearningCheckIn[];
  /** fields below were added later: missing on older sessions */
  away?: AwayRecord[];
  prompts?: LearningPrompt[];
  endedAt?: number | null;
  endReason?: SessionEndReason | null;
  /** null when the session gave nothing worth reflecting on, so nothing was shown */
  summary?: SessionSummary | null;
  summarySeenAt?: number | null;
}
export interface LearningReflection {
  sessionId: string;
  elapsedSeconds: number;
  /** videos with any observed playback; `synthetic` when it was only the stand-in clock of a video without its file */
  videos: { id: string; title: string; coverage: number; replaySeconds: number; synthetic: boolean; completed: boolean }[];
  /** videos whose playback was too brief to list (swiped past): only counted */
  glanced: number;
  /** one suggested next action, chosen from the saved evidence */
  nextStep: string;
  answers: number;
  correct: number;
  certainAnswers: number;
  certainCorrect: number;
  /** the saved check-ins, each with a recap that reads on its own, away from the checkpoint card */
  checkIns: (LearningCheckIn & { videoTitle: string; recap: string })[];
}

/**
 * The feedback after a checkpoint (plan/engagement-feedback-implementation-plan.md, "Feedback rules"): descriptive,
 * versioned rules over what the student did and said. Priority: a reported attention drift, then a wrong answer the
 * student found difficult, then a wrong answer given with certainty, then a correct answer after replaying. Anything
 * else, replay alone included, gets a plain retrieval prompt: no behavioural trace is read as attention or ability.
 */
export function learningFeedback(e: {
  correct: boolean | null; confidence: Confidence | null; hintUsed: boolean;
  difficulty: Difficulty | null; attention: AttentionReport | null; replaySeconds: number; replayFrom: number;
}): LearningFeedback {
  let rule: FeedbackRule = "reflection";
  let message = "Choose one idea from this explanation and try saying it in your own words.";
  if (e.attention === "drifted") {
    rule = "attention_recovery";
    message = "You said your attention drifted. You can replay the example, or continue when you feel ready.";
  } else if (e.correct === false && e.difficulty === "too_hard") {
    // one card, both observations, when the confidence mismatch applies too (never two alerts)
    rule = "difficulty_support";
    message = e.confidence === "certain" && !e.hintUsed
      ? "You felt certain and found this part difficult, and this answer was incorrect. Compare your reasoning with the explanation above, or replay the example one step at a time."
      : "You found this part difficult, and this answer needs another look. Compare your reasoning with the explanation above, or replay the example one step at a time.";
  } else if (e.correct === false && e.confidence === "certain" && !e.hintUsed) {
    rule = "confidence_mismatch";
    message = "You felt certain, but this answer was incorrect. Compare your reasoning with the explanation above. What would you change?";
  } else if (e.correct === true && e.replaySeconds >= 1) {
    rule = "review_acknowledgment";
    message = "You revisited part of this video and answered this question correctly. Which part helped your understanding?";
  }
  return { rule, message, replayFrom: e.replayFrom, policyVersion: "1" };
}

/**
 * What a saved card was about, in the past tense, for the session reflection: the card's own message points at "the
 * explanation above", which is not on that page.
 */
export function feedbackRecap(rule: FeedbackRule, e: { confidence: Confidence | null; hintUsed: boolean }): string {
  const certain = e.confidence === "certain" && !e.hintUsed;
  switch (rule) {
    case "attention_recovery": return "You said your attention drifted just before the question.";
    case "difficulty_support": return certain ? "You felt certain and found this part difficult, and the answer was incorrect." : "You found this part difficult, and the answer was incorrect.";
    case "confidence_mismatch": return "You felt certain, but the answer was incorrect.";
    case "review_acknowledgment": return "You revisited part of this video and answered its question correctly.";
    case "reflection": return "You saved a reflection on this part.";
  }
}
