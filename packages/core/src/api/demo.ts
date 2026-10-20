import { fixtures } from "../fixtures";
import { studyModules } from "../logic/instruments";
import { getState, isOnboarded, mutate, replaceState, resetState } from "../store";
import type { Condition, Item } from "../types";
import { DAY } from "../util";
import { api } from "./client";
import { makePersonaState } from "./persona";

/** Facilitator controls for the Phase 0 demo menu (plan §3.17). Not part of the API contract. */
export function resetDemo(): void {
  resetState();
}

export async function loadPersona(variant: "midcourse" | "precheck"): Promise<void> {
  const { participant_code, condition } = getState();
  const next = await makePersonaState(variant);
  next.participant_code = participant_code;
  next.condition = condition;
  replaceState(next);
}

export function simulateNextDay(): void {
  mutate((s) => {
    s.clock_offset_ms += DAY;
  });
}

/** A week later: the next lecture's check becomes due. */
export function simulateNextWeek(): void {
  mutate((s) => {
    s.clock_offset_ms += 7 * DAY;
  });
}

export function setParticipantCode(code: string): void {
  mutate((s) => {
    s.participant_code = code.trim() || null;
  });
}

/** Moves the demo clock just past module 1's last lecture week, so its questionnaire is due (plan I2). */
export function endFirstModule(): void {
  const [m1] = studyModules(fixtures().course);
  const lastWeek = Math.max(...fixtures().course.lectures.filter((l) => m1.lectures.includes(l.n)).map((l) => l.week));
  mutate((s) => {
    const due = s.semester_start + lastWeek * 7 * DAY;
    const t = Date.now() + s.clock_offset_ms;
    if (t < due) s.clock_offset_ms += due - t + 60_000;
  });
}

/** The participant's study condition (plan I11): set by the researcher, kept across Reset demo. */
export function setCondition(condition: Condition): void {
  mutate((s) => {
    s.condition = condition;
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

/** A scripted student: right exactly when their ability on the item's lecture reaches the item's difficulty. */
export function scriptedStudent(ability: Record<number, number>, otherwise = 0): (item: Item) => "right" | "wrong" {
  return (item) => {
    const n = Number(item.topic_id.split("-")[1]);
    return (ability[n] ?? otherwise) >= item.difficulty_prior ? "right" : "wrong";
  };
}

/** Answer every question of a sitting with `how`, then finish it, through the real API. */
export async function runSitting(id: string, how: (item: Item) => "right" | "wrong" | "not_sure"): Promise<void> {
  for (;;) {
    const v = await api.getSitting(id);
    if (!v.current) break;
    const it = v.current.item;
    const o = how(it);
    await api.answerSitting(id, it.id, o === "not_sure" ? "not_sure" : o === "right" ? it.correct_index : (it.correct_index + 1) % 3, 1500);
  }
  await api.finishSitting(id);
}

/** Skip the baseline with a mixed student (strong on lecture 1, middling on 2, weak on 3) so every later screen has data. */
export async function fastOnboard(): Promise<void> {
  if (getState().consent === null) await api.postConsent(true);
  if (isOnboarded(getState())) return;
  await runSitting("week0", scriptedStudent({ 1: 1.4, 2: -0.2, 3: -1.4 }));
}

/** Hide every video so the playlist is empty ("videos are being made"). Reset demo undoes it. */
export async function showEmptyPlaylist(): Promise<void> {
  if (!isOnboarded(getState())) await fastOnboard();
  mutate((s) => {
    for (const v of fixtures().videos) s.review[v.id] = "hidden";
    s.playlist = { entries: [], manual_order: null, built_at_week: s.playlist.built_at_week };
  });
}
