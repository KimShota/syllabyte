import { fixtures, videoById } from "../fixtures";
import { coveredSeconds, mergeIntervals } from "../logic/playback";
import { feedbackRecap, learningFeedback, type LearningContext, type LearningPrompt, type LearningReflection, type LearningSession, type SessionEndReason, type SessionSummary } from "../learning";
import { DRIFT_POLICY, driftDecision, driftObservation, welcomeBackDecision, type Visit } from "../logic/engagementDrift";
import type { ResponseRecord, Video } from "../types";
import { getState, mutate, mutateQuietly, now } from "../store";
import { uid } from "../util";
import type { Api } from "./types";

export function validateLearningContext(context: LearningContext) {
  if (!context || context.courseId !== fixtures().course.id) throw new Error("The course changed. Reopen this video.");
  if (typeof context.sessionId !== "string" || !/^[a-zA-Z0-9-]{1,100}$/.test(context.sessionId) || ["constructor", "prototype", "__proto__"].includes(context.sessionId)) throw new Error("Invalid learning session");
}

function session(context: LearningContext): LearningSession {
  validateLearningContext(context);
  const existing = getState().learning_sessions[context.sessionId];
  if (existing) return existing;
  const value: LearningSession = { id: context.sessionId, courseId: context.courseId, startedAt: now(), updatedAt: now(), playback: {}, completedVideos: [], checkIns: [] };
  mutateQuietly((s) => { s.learning_sessions[value.id] = value; });
  return value;
}

type Observation = LearningSession["playback"][string];

/** Unique coverage, total traversed content and replay (traversed again) of one video's observations. */
function exposureOf(rows: Observation[]) {
  const unique = coveredSeconds(rows.flatMap((r) => r.snapshot.intervals));
  const exposure = rows.reduce((n, r) => n + r.snapshot.exposure_s, 0);
  return { unique, exposure, replay: Math.max(0, exposure - unique) };
}

/** Real and synthetic (no video file) playback never add up: a video is complete once one source alone covers 90%. */
function bestCoverage(rows: Observation[]): number {
  return Math.max(0, ...(["video", "demo"] as const).map((src) => exposureOf(rows.filter((r) => r.snapshot.source === src)).unique));
}

/** Below this much unique playback a video only counts as glanced at in the reflection (it was swiped past). */
export const GLANCE_S = 10;

/** Share of a video's unique content that must play before it counts as watched (the old rule, now on coverage). */
export const WATCHED_COVERAGE = 0.9;

export function learningApi(markWatched: (videoId: string) => Promise<void>): Pick<Api,
  "recordLearningPlayback" | "postLearningCheckIn" | "recordLearningFeedbackAction" | "getLearningReflection" | "recordLearningAway"
  | "evaluateLearningBoundary" | "respondToLearningPrompt" | "finishLearningSession" | "getPendingReflection" | "dismissReflection"
  | "keepLearningSessionOpen"> {
  return {
    async recordLearningPlayback(input) {
      validateLearningContext(input);
      const video = videoById(input.videoId);
      const p = input.snapshot;
      if (!/^[a-zA-Z0-9-]{1,100}$/.test(input.playbackId) || ["constructor", "prototype"].includes(input.playbackId)) throw new Error("Invalid playback ID");
      if (!p || !Number.isInteger(p.sequence) || p.sequence < 0 || ![p.duration_s, p.elapsed_s, p.exposure_s, p.position_s].every(Number.isFinite)
        || Math.abs(p.duration_s - video.duration_s) > 1 || p.duration_s <= 0 || p.elapsed_s < 0 || p.exposure_s < 0
        || p.position_s < 0 || p.position_s > p.duration_s || !["video", "demo"].includes(p.source)
        || !Array.isArray(p.intervals) || p.intervals.length > 10000
        || p.intervals.some((i) => !Array.isArray(i) || i.length !== 2 || !i.every(Number.isFinite) || i[0] < 0 || i[1] <= i[0] || i[1] > p.duration_s)
        || coveredSeconds(p.intervals) > p.exposure_s + 0.01) throw new Error("Invalid playback observation");
      const s = session(input);
      const old = s.playback[input.playbackId];
      if (old && (old.videoId !== input.videoId || old.snapshot.source !== p.source || old.snapshot.duration_s !== p.duration_s)) throw new Error("Playback identity changed");
      if (old && old.snapshot.sequence >= p.sequence) return { completedNow: false };
      if (old && (old.snapshot.elapsed_s > p.elapsed_s || old.snapshot.exposure_s > p.exposure_s
        || coveredSeconds([...old.snapshot.intervals, ...p.intervals]) > coveredSeconds(p.intervals) + 0.01)) throw new Error("Playback observation went backwards");
      // observations are saved quietly: screens are woken only when a video completes
      mutateQuietly(() => {
        s.playback[input.playbackId] = { videoId: video.id, snapshot: { ...p, intervals: mergeIntervals(p.intervals) }, receivedAt: now(), firstAt: old?.firstAt ?? now() };
        s.updatedAt = now();
      });
      const rows = Object.values(s.playback).filter((r) => r.videoId === video.id);
      if (s.completedVideos.includes(video.id) || bestCoverage(rows) < video.duration_s * WATCHED_COVERAGE) return { completedNow: false };
      await markWatched(video.id);
      mutate(() => { s.completedVideos.push(video.id); });
      return { completedNow: true };
    },

    async postLearningCheckIn(input) {
      validateLearningContext(input);
      if (![null, "too_easy", "just_right", "too_hard"].includes(input.difficulty) || ![null, "on_task", "drifted"].includes(input.attention)) throw new Error("Invalid check-in");
      const response = getState().responses.find((r) => r.id === input.responseId && r.learning_session_id === input.sessionId && r.context === "checkpoint");
      if (!response?.video_id) throw new Error("Checkpoint response not found in this session");
      const video = videoById(response.video_id);
      const s = session(input);
      const existing = s.checkIns.find((r) => r.responseId === input.responseId);
      if (existing) {
        if (existing.difficulty !== input.difficulty || existing.attention !== input.attention) throw new Error("This reflection was already saved");
        return structuredClone(existing);
      }
      const { replay } = exposureOf(Object.values(s.playback).filter((r) => r.videoId === video.id));
      const feedback = learningFeedback({ correct: response.correct, confidence: response.confidence, hintUsed: response.hint_used,
        difficulty: input.difficulty, attention: input.attention, replaySeconds: replay, replayFrom: video.checkpoint.rewatch_from });
      const result = { ...input, id: uid("checkin"), videoId: video.id, at: now(), feedback, action: null, actionAt: null };
      mutate(() => { s.checkIns.push(result); s.updatedAt = now(); });
      return structuredClone(result);
    },

    async recordLearningFeedbackAction(context, checkInId, action) {
      validateLearningContext(context);
      if (!["continue", "replay"].includes(action)) throw new Error("Invalid feedback action");
      const check = getState().learning_sessions[context.sessionId]?.checkIns.find((r) => r.id === checkInId);
      if (!check) throw new Error("Reflection not found");
      if (check.action) return; // first choice wins, including retried requests
      mutate(() => { check.action = action; check.actionAt = now(); });
    },

    async getLearningReflection(context) {
      validateLearningContext(context);
      return reflectionOf(context.sessionId);
    },

    async recordLearningAway(context, input) {
      validateLearningContext(context);
      if (!Number.isFinite(input.seconds) || input.seconds < 0 || input.seconds > 7 * 86400 || typeof input.id !== "string" || !/^[a-zA-Z0-9-]{1,100}$/.test(input.id)) throw new Error("Invalid absence");
      if (input.videoId !== null) videoById(input.videoId);
      const s = session(context);
      if (s.away?.some((a) => a.id === input.id)) return; // a retried save
      mutateQuietly(() => {
        (s.away ??= []).push({ id: input.id, at: now(), seconds: input.seconds, videoId: input.videoId });
        s.updatedAt = now();
      });
    },

    async keepLearningSessionOpen(context) {
      validateLearningContext(context);
      const s = session(context);
      if (s.endedAt) return { ended: true };
      mutateQuietly(() => { s.updatedAt = now(); });
      return { ended: false };
    },

    async evaluateLearningBoundary(context, input) {
      validateLearningContext(context);
      if (!["next_video", "return"].includes(input.reason)) throw new Error("Invalid decision point");
      const video = videoById(input.videoId);
      const s = session(context);
      if (s.endedAt) return null;
      const prompts = s.prompts ?? [];
      const t = now();
      let prompt: LearningPrompt | null = null;

      if (input.reason === "return") {
        const away = (s.away ?? []).at(-1);
        const rows = Object.values(s.playback).filter((r) => r.videoId === video.id).sort((a, b) => a.receivedAt - b.receivedAt);
        const position = rows.at(-1)?.snapshot.position_s ?? 0;
        const recall = recallUpTo(video, position);
        // nothing to recall yet (no key point before where they stopped): just carry on
        if (away && recall && welcomeBackDecision({ awaySeconds: away.seconds, position, duration: video.duration_s, prompts })) {
          prompt = newPrompt("welcome_back", [`away_s:${Math.round(away.seconds)}`], `Welcome back. You were ${clock(position)} into “${video.short_title}”.`, recall, t);
        }
      }
      if (!prompt) {
        // the visits before the video the student is on now
        const visits: Visit[] = Object.values(s.playback)
          .filter((r) => !(input.reason === "next_video" && r.videoId === video.id && (r.firstAt ?? r.receivedAt) >= t - 2000))
          .sort((a, b) => (a.firstAt ?? a.receivedAt) - (b.firstAt ?? b.receivedAt))
          .map((r) => ({ videoId: r.videoId, firstAt: r.firstAt ?? r.receivedAt, coverage: coveredSeconds(r.snapshot.intervals) / r.snapshot.duration_s,
            completed: s.completedVideos.includes(r.videoId) }));
        const answers = getState().responses.filter((r) => r.learning_session_id === s.id && r.context === "checkpoint").map((r) => ({ correct: r.correct, at: r.at }));
        const d = driftDecision({ now: t, visits, away: s.away ?? [], answers, prompts });
        if (d.fire) {
          // recall the last video the student really watched, not the one they skimmed
          const watched = [...visits].reverse().find((v) => v.completed || v.coverage >= DRIFT_POLICY.earlyCoverage);
          const target = watched ? videoById(watched.videoId) : null;
          prompt = newPrompt("drift_check", d.evidence, driftObservation(d.evidence), target ? recallUpTo(target, target.duration_s) : null, t);
        }
      }
      if (!prompt) return null;
      const saved = prompt;
      mutateQuietly(() => { (s.prompts ??= []).push(saved); s.updatedAt = t; });
      return structuredClone(saved);
    },

    async respondToLearningPrompt(context, promptId, response) {
      validateLearningContext(context);
      if (response.answer !== undefined && !["on_task", "drifted", "familiar", "searching"].includes(response.answer)) throw new Error("Invalid answer");
      if (response.action !== undefined && !["continue", "rewatch", "replay", "pause"].includes(response.action)) throw new Error("Invalid action");
      const prompt = getState().learning_sessions[context.sessionId]?.prompts?.find((x) => x.id === promptId);
      if (!prompt) throw new Error("Prompt not found");
      // each part is recorded once: the first answer and the first action stand, including on retried requests
      mutateQuietly(() => {
        if (response.answer && !prompt.answer) prompt.answer = response.answer;
        if (response.action && !prompt.action) prompt.action = response.action;
        prompt.respondedAt ??= now();
      });
    },

    async finishLearningSession(context, reason) {
      validateLearningContext(context);
      if (!["left", "gap"].includes(reason)) throw new Error("Invalid reason");
      const s = getState().learning_sessions[context.sessionId];
      if (!s) return null;
      if (s.endedAt) return s.summary ? structuredClone(s.summary) : null;
      return finish(s, reason);
    },

    async getPendingReflection() {
      // a session left without saying so (the app was closed) ends after a gap with no activity
      const t = now();
      for (const s of Object.values(getState().learning_sessions)) {
        if (!s.endedAt && s.courseId === fixtures().course.id && t - s.updatedAt >= DRIFT_POLICY.sessionGapMs) finish(s, "gap");
      }
      const pending = Object.values(getState().learning_sessions)
        .filter((s) => s.summary && !s.summarySeenAt && s.courseId === fixtures().course.id)
        .sort((a, b) => b.updatedAt - a.updatedAt); // the most recent activity (sessions ended together tie on createdAt)
      return pending[0]?.summary ? structuredClone(pending[0].summary) : null;
    },

    async dismissReflection(sessionId) {
      const s = getState().learning_sessions[sessionId];
      if (!s?.summary) throw new Error("Reflection not found");
      // older ones still waiting are superseded: only the latest is ever shown
      mutate((st) => {
        for (const x of Object.values(st.learning_sessions)) if (x.summary && !x.summarySeenAt && x.summary.createdAt <= s.summary!.createdAt) x.summarySeenAt = now();
      });
    },
  };
}

/**
 * One next action, from what this session saved: the part behind the latest wrong checkpoint answer, else a video left
 * unfinished, else a retrieval prompt. Never a claim about what the student understands.
 */
function nextStep(responses: ResponseRecord[], videos: LearningReflection["videos"]): string {
  const missed = [...responses].reverse().find((r) => r.correct === false && r.video_id);
  if (missed?.video_id) return `Rewatch the part of “${videoById(missed.video_id).short_title}” before its check, then explain that question's idea in your own words.`;
  const unfinished = videos.find((v) => v.coverage < WATCHED_COVERAGE);
  if (unfinished) return `Finish “${unfinished.title}”: about ${Math.round(unfinished.coverage * 100)}% of it has played.`;
  if (responses.length || videos.length) return "Without looking back, explain one idea from this session in your own words. If you get stuck, rewatch that part.";
  return "Watch a video and answer its check.";
}

/** What a session saved, for the reflection: playback by video (brief ones only counted), answers and check-ins. */
function reflectionOf(sessionId: string): LearningReflection {
  const s = getState().learning_sessions[sessionId];
  const observations = Object.values(s?.playback ?? {});
  const responses = getState().responses.filter((r) => r.learning_session_id === sessionId && r.context === "checkpoint");
  const answered = new Set(responses.map((r) => r.video_id));
  let glanced = 0;
  const videos = [...new Set(observations.map((p) => p.videoId))].flatMap((id) => {
    const rows = observations.filter((r) => r.videoId === id);
    const { unique, replay } = exposureOf(rows);
    const completed = s?.completedVideos.includes(id) ?? false;
    // a video swiped past is counted, not listed, unless something else happened on it
    if (unique < GLANCE_S && !completed && !answered.has(id)) {
      glanced += 1;
      return [];
    }
    return [{ id, title: videoById(id).short_title, coverage: Math.min(1, unique / rows[0].snapshot.duration_s), replaySeconds: replay,
      synthetic: rows.every((r) => r.snapshot.source === "demo"), completed }];
  });
  return {
    sessionId,
    elapsedSeconds: observations.reduce((n, r) => n + r.snapshot.elapsed_s, 0),
    videos,
    glanced,
    nextStep: nextStep(responses, videos),
    answers: responses.length, correct: responses.filter((r) => r.correct === true).length,
    certainAnswers: responses.filter((r) => r.confidence === "certain" && !r.hint_used).length,
    certainCorrect: responses.filter((r) => r.confidence === "certain" && !r.hint_used && r.correct === true).length,
    checkIns: (s?.checkIns ?? []).map((c) => {
      const r = responses.find((x) => x.id === c.responseId);
      return { ...structuredClone(c), videoTitle: videoById(c.videoId).short_title,
        recap: feedbackRecap(c.feedback.rule, { confidence: r?.confidence ?? null, hintUsed: r?.hint_used ?? false }) };
    }),
  };
}

/** Ends a session and decides its reflection: null (nothing shown) when it gave nothing worth reflecting on. */
function finish(s: LearningSession, reason: SessionEndReason): SessionSummary | null {
  const summary = sessionSummary(s, reason);
  mutate(() => {
    s.endedAt = now();
    s.endReason = reason;
    s.summary = summary;
    s.summarySeenAt = null;
  });
  return summary ? structuredClone(summary) : null;
}

/**
 * The automatic reflection: one observation and one next step, chosen from the session's evidence in this order (most
 * useful to the student first): a wrong answer given with certainty, any wrong answer, right answers given while unsure,
 * a reported drift, all answers right, videos finished. A session with no answer, no finished video and no answered
 * check-in gets none: the reflection appears only when there is something to say (Guo 2022: specific, adaptive prompts;
 * Kizilcec et al. 2016: generic advice did not help).
 */
export function sessionSummary(s: LearningSession, reason: SessionEndReason): SessionSummary | null {
  const r = reflectionOf(s.id);
  const responses = getState().responses.filter((x) => x.learning_session_id === s.id && x.context === "checkpoint");
  const finished = r.videos.filter((v) => v.completed);
  const drifted = (s.prompts ?? []).some((x) => x.answer === "drifted") || s.checkIns.some((c) => c.attention === "drifted");
  if (!responses.length && !finished.length && !drifted) return null;

  const title = (id: string | null | undefined) => (id ? `“${videoById(id).short_title}”` : "a check");
  const certainWrong = responses.filter((x) => x.correct === false && x.confidence === "certain" && !x.hint_used);
  const wrong = responses.filter((x) => x.correct === false);
  const unsureRight = responses.filter((x) => x.correct === true && (x.confidence === "guess" || x.confidence === "pretty"));
  let observation: string;
  if (certainWrong.length) observation = `You felt certain on the check in ${title(certainWrong.at(-1)!.video_id)}, but the answer was incorrect.`;
  else if (wrong.length) observation = `The check in ${title(wrong.at(-1)!.video_id)} needs another look.`;
  else if (unsureRight.length >= 2) observation = `You answered ${unsureRight.length} checks right even when you weren't sure.`;
  else if (drifted) observation = "You said your attention drifted during this session.";
  else if (responses.length) observation = `You got ${r.correct} of ${r.answers} ${r.answers === 1 ? "check" : "checks"} right.`;
  else observation = `You finished ${title(finished[0].id)}${finished.length > 1 ? ` and ${finished.length - 1} more` : ""}.`;

  const nextStepText = unsureRight.length >= 2 && !wrong.length
    ? "Before the next video, say why one of those answers is right: you know more than you felt you did."
    : r.nextStep;
  const minutes = Math.round(r.elapsedSeconds / 60);
  const stats = [
    r.videos.length ? `${r.videos.length} ${r.videos.length === 1 ? "video" : "videos"}` : null,
    r.answers ? `${r.correct} of ${r.answers} ${r.answers === 1 ? "check" : "checks"} right` : null,
    minutes ? `${minutes} min of playback` : null,
  ].filter(Boolean).join(" · ");
  return { sessionId: s.id, observation, nextStep: nextStepText, stats, reason, createdAt: now() };
}

function newPrompt(kind: LearningPrompt["kind"], evidence: string[], observation: string, recall: LearningPrompt["recall"], at: number): LearningPrompt {
  return { id: uid("prompt"), kind, policyVersion: DRIFT_POLICY.version, evidence, observation, recall, shownAt: at, answer: null, action: null, respondedAt: null };
}

/** The video's key points up to `position` (its last two), to compare with what the student recalls; null when none. */
function recallUpTo(video: Video, position: number): LearningPrompt["recall"] {
  const start = (c: Video["claims"][number]) => video.segments[c.segment_idx]?.start ?? 0;
  const covered = video.claims.filter((c) => start(c) <= position).sort((a, b) => start(a) - start(b));
  if (!covered.length) return null;
  const shown = covered.slice(-2);
  return { videoId: video.id, title: video.short_title, points: shown.map((c) => c.text), replayFrom: start(shown[0]) };
}

const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
