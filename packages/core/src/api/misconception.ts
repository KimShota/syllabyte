import { fixtures, itemById, videoById } from "../fixtures";
import type { LearningContext } from "../learning";
import { getState, mutate, mutateQuietly, now } from "../store";
import type { Confidence, MisconceptionClip, MisconceptionRequest } from "../types";
import { uid } from "../util";
import { validateLearningContext } from "./learning";
import type { Api } from "./types";

/**
 * Misconception clips (plan/engagement-feedback-implementation-plan.md, "Misconception clips"). A checkpoint answered
 * wrong with "Certain" signals a misconception rather than a gap (Hasan et al., 1999), and high-confidence errors are the
 * most correctable after feedback (Metcalfe, 2017). So such an answer records a request for a short video that refutes
 * that misconception. The server makes it on demand (a `misconception` job) and caches it per question and wrong option;
 * the app offers it as soon as it is ready, never mid-video, and asks a follow-up question after it.
 */

/** One clip per question and wrong option. */
export const misconceptionKey = (itemId: string, choice: number): string => `${itemId}|${choice}`;

/** Whether an answer asks for a clip: wrong, given as "Certain", without a hint. */
export const wantsMisconceptionClip = (a: { correct: boolean; confidence: Confidence; hintUsed: boolean }): boolean =>
  !a.correct && a.confidence === "certain" && !a.hintUsed;

/**
 * Records a request for the clip about this answer's misconception, once per student and key: a student who makes the
 * same mistake again is offered the same clip, not a second request. Called by postCheckpointAnswer.
 */
export function requestMisconceptionClip(a: { videoId: string; itemId: string; choice: number; sessionId: string | null }): void {
  const key = misconceptionKey(a.itemId, a.choice);
  const state = getState();
  if ((state.misconception_requests ?? []).some((r) => r.key === key)) return;
  const video = videoById(a.videoId);
  const request: MisconceptionRequest = {
    id: uid("mc"), key, item_id: a.itemId, choice: a.choice, video_id: video.id, ku_id: video.ku_id, level: video.file_level,
    session_id: a.sessionId, requested_at: now(), offered_at: null, action: null, action_at: null, follow_up: null,
  };
  mutate((s) => {
    (s.misconception_requests ??= []).push(request);
  });
}

const readyClip = (key: string): MisconceptionClip | undefined => (fixtures().misconception_clips ?? []).find((c) => c.key === key);

function requestOf(requestId: string): MisconceptionRequest {
  const r = (getState().misconception_requests ?? []).find((x) => x.id === requestId);
  if (!r) throw new Error("Clip request not found");
  return r;
}

export const misconceptionApi: Pick<Api, "getMisconceptionClips" | "respondToMisconceptionClip" | "answerMisconceptionCheck"> = {
  async getMisconceptionClips(context: LearningContext) {
    validateLearningContext(context);
    // not yet watched, and made: oldest first (the app offers one at a time)
    return (getState().misconception_requests ?? [])
      .filter((r) => r.action !== "watched")
      .flatMap((r) => {
        const clip = readyClip(r.key);
        return clip ? [{ request: structuredClone(r), clip: structuredClone(clip), item_title: videoById(r.video_id).short_title }] : [];
      })
      .sort((a, b) => a.request.requested_at - b.request.requested_at);
  },

  async respondToMisconceptionClip(context, requestId, response) {
    validateLearningContext(context);
    if (response.action !== undefined && !["watched", "later"].includes(response.action)) throw new Error("Invalid action");
    const r = requestOf(requestId);
    // the first offer is kept; "later" can still become "watched", but "watched" stands
    mutateQuietly(() => {
      if (response.offered && r.offered_at === null) r.offered_at = now();
      if (response.action && r.action !== "watched") {
        r.action = response.action;
        r.action_at = now();
      }
    });
  },

  async answerMisconceptionCheck(context, requestId, choice) {
    validateLearningContext(context);
    const r = requestOf(requestId);
    const item = readyClip(r.key)?.check_item;
    if (!item) throw new Error("This clip has no follow-up question");
    if (!Number.isInteger(choice) || choice < 0 || choice >= item.options.length) throw new Error("Invalid answer");
    const correct = choice === item.correct_index;
    // the first answer stands, including on a retried request
    if (!r.follow_up) mutate(() => { r.follow_up = { choice, correct, at: now() }; });
    const saved = r.follow_up ?? { choice, correct };
    return { correct: saved.correct, correct_index: item.correct_index, explanation: item.explanation };
  },
};

/** The question a clip request is about, for the job that makes the clip (server). */
export function misconceptionBrief(r: Pick<MisconceptionRequest, "item_id" | "choice">) {
  const item = itemById(r.item_id);
  return { stem: item.stem, options: item.options, correct_index: item.correct_index, chosen: r.choice, explanation: item.explanation };
}
