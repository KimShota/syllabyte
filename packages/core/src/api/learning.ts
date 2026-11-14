import { fixtures, videoById } from "../fixtures";
import { coveredSeconds, mergeIntervals } from "../logic/playback";
import { feedbackRecap, learningFeedback, type LearningContext, type LearningReflection, type LearningSession } from "../learning";
import type { ResponseRecord } from "../types";
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
  "recordLearningPlayback" | "postLearningCheckIn" | "recordLearningFeedbackAction" | "getLearningReflection"> {
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
        s.playback[input.playbackId] = { videoId: video.id, snapshot: { ...p, intervals: mergeIntervals(p.intervals) }, receivedAt: now() };
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
      const s = getState().learning_sessions[context.sessionId];
      const observations = Object.values(s?.playback ?? {});
      const responses = getState().responses.filter((r) => r.learning_session_id === context.sessionId && r.context === "checkpoint");
      const answered = new Set(responses.map((r) => r.video_id));
      let glanced = 0;
      const videos = [...new Set(observations.map((p) => p.videoId))].flatMap((id) => {
          const rows = observations.filter((r) => r.videoId === id);
          const { unique, replay } = exposureOf(rows);
          if (unique <= 0) return [];
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
        sessionId: context.sessionId,
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
  return "Watch a video and answer its check; this page then sums up what you did.";
}
