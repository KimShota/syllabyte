import { getState, mutate, replaceState, resetState } from "@/lib/store";
import { DAY } from "@/lib/util";
import { makePersonaState } from "./persona";

/** Facilitator controls for the Phase 0 demo menu (plan §3.17). Not part of the API contract. */
export function resetDemo(): void {
  resetState();
}

export function loadPersona(variant: "invite" | "results"): void {
  const code = getState().participant_code;
  const next = makePersonaState(variant);
  next.participant_code = code;
  replaceState(next);
}

export function simulateNextDay(): void {
  mutate((s) => {
    s.clock_offset_ms += DAY;
  });
}

export function setParticipantCode(code: string): void {
  mutate((s) => {
    s.participant_code = code.trim() || null;
  });
}

export function setLogDeclined(on: boolean): void {
  mutate((s) => {
    s.flags.log_declined = on;
  });
}

export function sessionLogJson(): string {
  const s = getState();
  return JSON.stringify({ participant_code: s.participant_code, exported_at: new Date().toISOString(), events: s.events }, null, 2);
}

export function downloadText(filename: string, text: string, type = "application/json"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

import { api } from "./client";
import { FIX, itemById } from "@/lib/fixtures";

/** Skip onboarding with a mixed set of answers (one Level 3, 2, 1, 2 topic) so every later screen has data. */
export async function fastOnboard(): Promise<void> {
  if (getState().consent === null) await api.postConsent(true);
  const plan: Record<string, ("right" | "wrong" | "not_sure")[]> = {
    "causal-questions": ["right", "right"],
    "potential-outcomes": ["right", "wrong"],
    "selection-bias": ["wrong", "not_sure"],
    randomization: ["right", "not_sure"],
  };
  for (const topic of FIX.course.topics) {
    const hows = plan[topic.id] ?? ["right", "right"];
    const items = FIX.items.filter((i) => i.context === "onboarding" && i.topic_id === topic.id).sort((a, b) => a.id.localeCompare(b.id));
    for (let k = 0; k < items.length; k++) {
      const it = itemById(items[k].id);
      const how = hows[k] ?? "right";
      await api.answerOnboarding(it.id, how === "not_sure" ? "not_sure" : how === "right" ? it.correct_index : (it.correct_index + 1) % 3, 1500);
    }
  }
  await api.finishOnboarding();
}

/** Hide every video so the playlist is empty ("videos are being made"). Reset demo undoes it. */
export async function showEmptyPlaylist(): Promise<void> {
  if (!getState().onboarding.done) await fastOnboard();
  mutate((s) => {
    for (const v of FIX.videos) s.review[v.id] = "hidden";
    s.playlist = { entries: [], manual_order: null, built_at_week: s.playlist.built_at_week };
  });
}
