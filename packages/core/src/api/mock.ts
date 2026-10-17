import { INSTRUMENTS_VERSION } from "../content/instruments";
import { track } from "../events";
import { FIX, itemById, lectureByN, slideText, slideUrl, topicById, videoById } from "../fixtures";
import { nextAssessmentItem, prelecturePlan, week0Plan, type AssessmentPlan } from "../logic/assessment";
import { calibrationBlock1, calibrationBlock2 } from "../logic/calibration";
import { droppedEarly } from "../logic/engagement";
import { kuLevels, levelUpdates } from "../logic/kuProfile";
import {
  batteryInstruments, dueModules, moduleEndTime, newBattery, studyCsv, studyModules, visibleItems,
} from "../logic/instruments";
import { overallLevel } from "../logic/levels";
import { createTask, currentNextSession } from "../logic/nextSession";
import {
  buildPlaylistState,
  displayOrder,
  servedLevel,
  upcomingLecture,
  whyOrder,
  type BuildInput,
} from "../logic/playlist";
import { changesCount, tailoringRows } from "../logic/receipt";
import { weekOf } from "../logic/time";
import { getState, isOnboarded, mutate, now } from "../store";
import type {
  Choice, ClaimView, Item, KuLevel, KuLevelRow, Level, LectureLevels, PlaylistEntry, PrecheckView, ResponseRecord,
  ReviewStatus, SittingState, Video, VideoCardView, VariantView,
} from "../types";
import { uid } from "../util";
import type { Api, BatteryView, StudyTaskView } from "./types";

// ----------------------------------------------------------------- helpers

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const S = () => getState();
const cfg = () => FIX.course.config;
const week = () => weekOf(now(), S().semester_start);
const topicTitle = (id: string) => topicById(id).title;
const lectureTitle = (n: number) => lectureByN(n).title;
const profileInput = () => ({ course: FIX.course, items: FIX.items, responses: S().responses });
/** The lecture whose videos are next: the schedule's, unless the demo moved it. */
const upcoming = () => S().upcoming_lecture ?? upcomingLecture(FIX.course, week());
const baselineDone = () => isOnboarded(S());
const research = () => S().consent === "research";

/** Creates the record of every battery that is due (plan I2): the baseline from consent, each module from its end. */
function openDueBatteries(): void {
  if (!research()) return;
  const s = S();
  const missing: { id: string; at: number }[] = [];
  if (!s.study.baseline) missing.push({ id: "baseline", at: now() });
  for (const m of dueModules(FIX.course, week(), s.upcoming_lecture)) {
    if (!s.study[m.id]) missing.push({ id: m.id, at: moduleEndTime(FIX.course, m, s.semester_start, now()) });
  }
  if (!missing.length) return;
  mutate((st) => {
    for (const { id, at } of missing) st.study[id] = newBattery(id, INSTRUMENTS_VERSION, at);
  });
}

function batteryTitle(id: string): string {
  if (id === "baseline") return "About you";
  const m = studyModules(FIX.course).find((x) => x.id === id);
  return `${m?.title ?? id} questionnaire`;
}

function studyRecord(id: string) {
  if (!research()) throw new Error("study questionnaires are for research participants only");
  openDueBatteries();
  const r = S().study[id];
  if (!r) throw new Error(`questionnaire ${id} is not due`);
  return r;
}

function addResponse(
  item: Item,
  choice: Choice,
  o: { confidence?: ResponseRecord["confidence"]; hintUsed?: boolean; latencyMs?: number; replace?: boolean } = {},
): ResponseRecord {
  const correct = choice === "not_sure" ? null : choice === item.correct_index;
  const r: ResponseRecord = {
    id: uid("r"),
    item_id: item.id,
    topic_id: item.topic_id,
    video_id: item.context === "assessment" ? null : item.ku_id,
    context: item.context,
    choice,
    correct,
    confidence: o.confidence ?? null,
    hint_used: o.hintUsed ?? false,
    latency_ms: o.latencyMs ?? 0,
    at: now(),
  };
  mutate((s) => {
    if (o.replace) s.responses = s.responses.filter((x) => !(x.item_id === item.id && x.context === item.context));
    s.responses.push(r);
  });
  return r;
}

function effectiveReview(videoId: string): ReviewStatus {
  const s = S();
  const base = s.review[videoId] ?? videoById(videoId).review_status;
  if (base === "hidden" || base === "approved") return base;
  const mismatch = Object.values(s.claims).some((c) => c.video_id === videoId && c.verdict === "mismatch");
  const open = s.reports.some((r) => r.video_id === videoId && r.status === "open");
  return mismatch || open ? "flagged" : base;
}

function reviewMap(): Record<string, ReviewStatus> {
  return Object.fromEntries(FIX.videos.map((v) => [v.id, effectiveReview(v.id)]));
}

function buildInput(prev: PlaylistEntry[]): BuildInput {
  const s = S();
  return {
    course: FIX.course, videos: FIX.videos, items: FIX.items, levels: s.levels, responses: s.responses, watched: s.watched,
    progress: s.progress, review: reviewMap(), prev, known: s.known_videos, added: s.added_videos, week: week(), now: now(),
    upcoming: s.upcoming_lecture ?? undefined,
  };
}

const levelOf = (kuId: string): Level => S().levels[kuId]?.level ?? 2;

/** A video is made once, at the KU's level when it is first needed, and never remade (plan D15). */
function ensureMade(kuId: string): void {
  mutate((s) => {
    if (s.made[kuId] === undefined) s.made[kuId] = (s.levels[kuId]?.level ?? 2) as Level;
  });
}

function rebuildPlaylist(keepManual = false): void {
  mutate((s) => {
    const next = buildPlaylistState(buildInput(s.playlist.entries));
    next.manual_order = keepManual ? s.playlist.manual_order : null;
    s.playlist = next;
    for (const e of next.entries) {
      const ku = videoById(e.video_id).ku_id;
      if (s.made[ku] === undefined) s.made[ku] = (s.levels[ku]?.level ?? 2) as Level;
    }
  });
}

function card(video: Video, entry: PlaylistEntry | null): VideoCardView {
  const level = levelOf(video.ku_id);
  const made = S().made[video.ku_id] ?? null;
  const served = servedLevel(made ?? level, [video.file_level]);
  return {
    entry_id: entry?.id ?? null,
    video_id: video.id,
    title: video.short_title,
    lecture_n: video.lecture_n,
    duration_s: video.duration_s,
    poster_url: video.poster_url,
    tag: entry?.tag ?? null,
    state: entry?.state ?? (S().watched[video.id] ? "watched" : "todo"),
    ku_id: video.ku_id,
    topic_id: video.topic_id,
    topic_title: topicTitle(video.topic_id),
    level,
    made_level: made,
    served_level: served.level,
    fallback_note: served.note,
    review_status: effectiveReview(video.id),
    skip_reason: entry?.skip_reason ?? null,
  };
}

function overall(): Level | null {
  const ls = Object.values(S().levels).filter((l) => !l.not_checked).map((l) => l.level);
  return ls.length ? overallLevel(ls) : null;
}

function entryFor(entryId: string): PlaylistEntry {
  const e = S().playlist.entries.find((x) => x.id === entryId);
  if (!e) throw new Error(`unknown playlist entry ${entryId}`);
  return e;
}

// ---- levels: the published level of every KU (plan D6, D11)

function kuRows(lectureN: number): KuLevelRow[] {
  const s = S();
  return FIX.course.kus
    .filter((k) => k.lecture_n === lectureN && s.levels[k.id])
    .map((ku) => ({ ku, level: s.levels[ku.id], made_level: s.made[ku.id] ?? null }));
}

function lectureLevels(): LectureLevels[] {
  return FIX.course.lectures.map((lecture) => ({ lecture, rows: kuRows(lecture.n) })).filter((l) => l.rows.length > 0);
}

/**
 * Publish the levels the answers so far support. Called only at a lecture boundary (the baseline, or the end of a
 * pre-lecture check): levels never move in the middle of a lecture, so queued videos are not cancelled and the
 * student is not surprised mid-video. A level the student set is not overwritten; only its suggestion moves.
 * Returns what changed for KUs the model owns.
 */
function publishLevels(cause: "baseline" | "lecture_check"): ReturnType<typeof levelUpdates> {
  const est = kuLevels(profileInput());
  const before = Object.fromEntries(Object.values(S().levels).filter((l) => l.source === "model").map((l) => [l.ku_id, l.level]));
  mutate((s) => {
    for (const ku of FIX.course.kus) {
      const e = est[ku.id];
      const cur = s.levels[ku.id];
      if (!cur) {
        s.levels[ku.id] = {
          ku_id: ku.id, level: e.level, source: "model", suggested_level: e.level, reason: e.reason, not_checked: e.not_checked,
          provisional: e.provisional, history: [{ level: e.level, source: "model", at: now(), cause }],
        };
        continue;
      }
      cur.suggested_level = e.level;
      cur.reason = e.reason;
      cur.not_checked = e.not_checked && cur.source === "model";
      cur.provisional = e.provisional;
      if (cur.source === "model" && cur.level !== e.level) {
        cur.level = e.level;
        cur.history.push({ level: e.level, source: "model", at: now(), cause });
      }
    }
  });
  return levelUpdates(before, est, FIX.course.kus, new Map(FIX.course.lectures.map((l) => [l.n, l.title])));
}

function describeLevelChange(ku: string, from: Level, to: Level, cause: string, at: number): string {
  const wk = weekOf(at, S().semester_start);
  const lecture = lectureTitle(FIX.course.kus.find((k) => k.short_title === ku)?.lecture_n ?? 1);
  const when =
    cause === "lecture_check" ? `at your “${lecture}” check` : cause === "use_suggested" ? `in Week ${wk}, when you went back to our level` : `in Week ${wk}, when you changed it`;
  return `“${ku}” went from Level ${from} to Level ${to} ${when}.`;
}

// ---- adaptive sittings (plan D8, D9)

const sittingKind = (id: string): SittingState["kind"] => (id === "week0" ? "week0" : "lecture");
const sittingLecture = (id: string): number | null => (id === "week0" ? null : Number(id.split("-")[1]));
const planOf = (id: string): AssessmentPlan => (id === "week0" ? week0Plan(FIX.course) : prelecturePlan(FIX.course, sittingLecture(id)!));
const sittingLabel = (id: string) => (id === "week0" ? "Start check" : `${lectureTitle(sittingLecture(id)!)} check`);

function ensureSitting(id: string): void {
  mutate((s) => {
    if (!s.sittings[id]) {
      s.sittings[id] = { id, kind: sittingKind(id), lecture_n: sittingLecture(id), answered_ids: [], started_at: now(), finished_at: null, skipped: false, week: null };
    }
  });
}

function currentOf(id: string) {
  const st = S().sittings[id];
  if (st?.finished_at) return null;
  return nextAssessmentItem(planOf(id), st?.answered_ids.length ?? 0, profileInput());
}

/** The check before the upcoming lecture's videos, when one is due. */
function precheck(): PrecheckView | null {
  const s = S();
  if (!baselineDone()) return null;
  const n = upcoming();
  const id = `lecture-${n}`;
  const st = s.sittings[id];
  if (st?.finished_at || st?.skipped) return null;
  // the baseline just covered this lecture, in this lecture week: no second check yet
  const w0 = s.sittings.week0;
  if (w0?.finished_at && w0.week === week() && week0Plan(FIX.course).slots.some((x) => x.lecture_n === n)) return null;
  if (!currentOf(id)) return null;
  return { sitting_id: id, lecture_n: n, title: lectureTitle(n), total: planOf(id).slots.length, answered: st?.answered_ids.length ?? 0 };
}

// --------------------------------------------------------------------- api

export const mockApi: Api = {
  async getMe() {
    const s = S();
    return {
      course: FIX.course, participant_code: s.participant_code, consent: s.consent, condition: s.condition, week: week(),
      now: now(), settings: s.settings, onboarding_done: baselineDone(),
    };
  },

  async postConsent(research) {
    // The condition is the researcher's (plan I11), so consent leaves it alone.
    mutate((s) => {
      s.consent = research ? "research" : "no_research";
    });
    openDueBatteries();
    track("consent_given", { type: "consent" }, { research });
  },

  async withdrawFromResearch(deletePast) {
    mutate((s) => {
      s.consent = "no_research";
      if (deletePast) {
        s.events = [];
        s.study = {};
      }
    });
  },

  async updateSettings(patch) {
    const before = S().settings;
    mutate((s) => {
      s.settings = { ...s.settings, ...patch };
    });
    if (patch.captions !== undefined && patch.captions !== before.captions) track("captions_toggled", { type: "setting" }, { on: patch.captions, from: "settings" });
  },

  // ---- adaptive sittings
  async getSitting(id) {
    const plan = planOf(id);
    const st = S().sittings[id];
    const next = currentOf(id);
    return {
      id, kind: sittingKind(id), lecture_n: sittingLecture(id), label: sittingLabel(id), total: plan.slots.length,
      answered: st?.answered_ids.length ?? 0, done: Boolean(st?.finished_at) || next === null,
      current: next ? { item: next.item, lecture_n: next.lecture_n, lecture_title: lectureTitle(next.lecture_n), role: next.role } : null,
    };
  },

  async answerSitting(id, itemId, choice, latencyMs) {
    const next = currentOf(id);
    if (!next || next.item.id !== itemId) throw new Error(`"${itemId}" is not the question sitting ${id} is on`);
    ensureSitting(id);
    const item = itemById(itemId);
    addResponse(item, choice, { latencyMs });
    mutate((s) => {
      s.sittings[id].answered_ids.push(itemId);
    });
    track("cat_answered", { type: "item", id: itemId }, {
      sitting: id, lecture: next.lecture_n, role: next.role, tier: item.tier, choice, correct: choice === "not_sure" ? null : choice === item.correct_index,
    });
  },

  async finishSitting(id) {
    const st = S().sittings[id];
    if (!st || st.finished_at) return;
    mutate((s) => {
      s.sittings[id].finished_at = now();
      s.sittings[id].week = week();
    });
    if (st.kind === "week0") {
      publishLevels("baseline");
      rebuildPlaylist();
      for (const ku of FIX.course.kus) track("level_suggested", { type: "ku", id: ku.id }, { level: S().levels[ku.id].level });
    } else {
      const updates = publishLevels("lecture_check");
      if (updates.length) {
        mutate((s) => {
          s.level_updates.push({ id: uid("lu"), lecture_n: st.lecture_n!, at: now(), updates, seen: false });
        });
      }
      rebuildPlaylist();
      track("levels_updated", { type: "lecture", id: String(st.lecture_n) }, { up: updates.filter((u) => u.direction === "up").length, down: updates.filter((u) => u.direction === "down").length });
    }
    track("cat_finished", { type: "sitting", id }, { answered: S().sittings[id].answered_ids.length });
  },

  async skipSitting(id) {
    ensureSitting(id);
    mutate((s) => {
      s.sittings[id].skipped = true;
    });
  },

  async pickAllLevels(level, fromQuestion) {
    const est = kuLevels(profileInput());
    ensureSitting("week0");
    mutate((s) => {
      for (const ku of FIX.course.kus) {
        s.levels[ku.id] = {
          ku_id: ku.id, level, source: "student", suggested_level: est[ku.id].level, reason: est[ku.id].reason, not_checked: false,
          provisional: false, history: [{ level, source: "student", at: now(), cause: "pick_all" }],
        };
      }
      s.picked_own = true;
      s.sittings.week0.finished_at = now();
      s.sittings.week0.week = week();
    });
    rebuildPlaylist();
    track("level_corrected", { type: "all_kus" }, { to: level, source_screen: "onboarding_pick_own", at_question: fromQuestion });
  },

  async getStartResult() {
    const s = S();
    const checked = Object.values(s.levels).filter((l) => !l.not_checked).map((l) => l.level);
    const answered = s.sittings.week0?.answered_ids ?? [];
    return {
      overall_level: overallLevel(checked),
      lectures: lectureLevels(),
      review: answered.map((id) => {
        const r = [...s.responses].reverse().find((x) => x.item_id === id);
        return { item: itemById(id), choice: r?.choice };
      }),
    };
  },

  async keepLevels() {
    track("level_kept", { type: "levels" }, { n: FIX.course.kus.length });
  },

  // ---- levels
  async getLevels() {
    const s = S();
    const lines: string[] = [];
    for (const l of Object.values(s.levels)) {
      const ku = FIX.course.kus.find((k) => k.id === l.ku_id)!;
      for (let i = 1; i < l.history.length; i++) lines.push(describeLevelChange(ku.short_title, l.history[i - 1].level, l.history[i].level, l.history[i].cause, l.history[i].at));
    }
    const due = precheck();
    return {
      overall_level: overall(), lectures: lectureLevels(), history_lines: lines, baseline_done: baselineDone(),
      next_check: due ? { lecture_n: due.lecture_n, title: due.title } : null, week: week(),
    };
  },

  async correctLevel(kuId, level, reasonChip, note, sourceScreen) {
    const previous = clone(S().levels[kuId]) as KuLevel;
    const from = previous?.level;
    mutate((s) => {
      const tl: KuLevel = s.levels[kuId] ?? { ku_id: kuId, level, source: "model", suggested_level: 1, reason: "", not_checked: false, provisional: false, history: [] };
      tl.level = level;
      tl.source = "student";
      tl.not_checked = false;
      tl.provisional = false;
      tl.history.push({ level, source: "student", at: now(), cause: "student" });
      s.levels[kuId] = tl;
    });
    track("level_corrected", { type: "ku", id: kuId }, { from, to: level, reason: reasonChip, note, source_screen: sourceScreen });
    return { previous };
  },

  async restoreLevel(previous) {
    mutate((s) => {
      s.levels[previous.ku_id] = previous;
    });
    track("undo", { type: "level", id: previous.ku_id });
  },

  async useSuggestedLevel(kuId) {
    mutate((s) => {
      const tl = s.levels[kuId];
      if (!tl) return;
      tl.level = tl.suggested_level;
      tl.source = "model";
      tl.history.push({ level: tl.level, source: "model", at: now(), cause: "use_suggested" });
    });
    track("level_corrected", { type: "ku", id: kuId }, { to: S().levels[kuId]?.level, source_screen: "use_suggested" });
  },

  async getLevelUpdates() {
    const c = [...S().level_updates].reverse().find((x) => !x.seen);
    if (!c) return null;
    return {
      id: c.id, lecture_n: c.lecture_n, lecture_title: lectureTitle(c.lecture_n),
      updates: c.updates.map((u) => ({ ...u, title: FIX.course.kus.find((k) => k.id === u.ku_id)?.short_title ?? u.ku_id })),
    };
  },

  async dismissLevelUpdates(id) {
    mutate((s) => {
      const c = s.level_updates.find((x) => x.id === id);
      if (c) c.seen = true;
    });
  },

  async getCalibration() {
    const s = S();
    return { block1: calibrationBlock1(s.responses), block2: calibrationBlock2(s.next_session, FIX.videos) };
  },

  // ---- playlist
  async getPlaylist() {
    const s = S();
    const upcomingN = upcoming();
    if (!baselineDone()) {
      return { overall_level: null, cards: [], skipped: [], why: "", manual: false, total_seconds: 0, watched_count: 0, upcoming_lecture: upcomingN, current_entry_id: null, empty_message: null, precheck: null };
    }
    const { active: ordered, skipped } = displayOrder(s.playlist);
    // A video the student stopped early goes back to the top as soon as the pause has passed, without waiting for a
    // rebuild (plan D13). A manual order is the student's own and wins.
    const stopped = new Set(ordered.filter((e) => droppedEarly(s.progress[e.video_id], Boolean(s.watched[e.video_id]), cfg(), now())).map((e) => e.video_id));
    const active = s.playlist.manual_order ? ordered : [...ordered.filter((e) => stopped.has(e.video_id)), ...ordered.filter((e) => !stopped.has(e.video_id))];
    const current = active.find((e) => e.state === "todo")?.id ?? null;
    const cards = active.map((e) => card(videoById(e.video_id), e));
    const todo = cards.filter((c) => c.state === "todo");
    return {
      overall_level: overall(),
      cards,
      skipped: skipped.map((e) => card(videoById(e.video_id), e)),
      why: whyOrder({
        upcoming: upcomingN, manual: Boolean(s.playlist.manual_order), entries: active, videos: FIX.videos, kus: FIX.course.kus,
        resumeIds: s.playlist.manual_order ? [] : [...stopped],
      }),
      manual: Boolean(s.playlist.manual_order),
      total_seconds: todo.reduce((n, c) => n + c.duration_s, 0),
      watched_count: Object.keys(s.watched).length,
      upcoming_lecture: upcomingN,
      current_entry_id: current,
      empty_message: active.length === 0 && skipped.length === 0 ? `Your Lecture ${upcomingN} videos are being made. Check back soon.` : null,
      precheck: precheck(),
    };
  },

  async reorder(ids) {
    mutate((s) => {
      s.playlist.manual_order = ids;
    });
    track("reordered", { type: "playlist" }, { order: ids });
  },

  async resetOrder() {
    mutate((s) => {
      s.playlist.manual_order = null;
    });
    track("reordered", { type: "playlist" }, { reset: true });
  },

  async skip(entryId) {
    const e = entryFor(entryId);
    mutate((s) => {
      const x = s.playlist.entries.find((y) => y.id === entryId)!;
      x.state = "skipped";
      x.skip_reason = null;
    });
    track("skipped", { type: "video", id: e.video_id });
  },

  async undoSkip(entryId) {
    const e = entryFor(entryId);
    mutate((s) => {
      const x = s.playlist.entries.find((y) => y.id === entryId)!;
      x.state = s.watched[x.video_id] ? "watched" : "todo";
      x.skip_reason = null;
      s.known_videos = s.known_videos.filter((id) => id !== x.video_id);
    });
    track("undo", { type: "skip", id: e.video_id });
  },

  async setSkipReason(entryId, reason) {
    const e = entryFor(entryId);
    mutate((s) => {
      s.playlist.entries.find((y) => y.id === entryId)!.skip_reason = reason;
    });
    track("skip_reason", { type: "video", id: e.video_id }, { reason });
  },

  async getProveIt(videoId) {
    return itemById(videoById(videoId).prove_it_item_id);
  },

  async answerProveIt(entryId, choice) {
    const e = entryFor(entryId);
    const item = itemById(videoById(e.video_id).prove_it_item_id);
    addResponse(item, choice);
    const pass = choice !== "not_sure" && choice === item.correct_index;
    mutate((s) => {
      const x = s.playlist.entries.find((y) => y.id === entryId)!;
      if (pass) {
        if (!s.known_videos.includes(x.video_id)) s.known_videos.push(x.video_id);
      } else {
        x.state = s.watched[x.video_id] ? "watched" : "todo"; // "No problem, it's back in your playlist"
      }
    });
    track("prove_it_result", { type: "video", id: e.video_id }, { pass, choice });
    return { pass };
  },

  async keepSkipped(entryId) {
    mutate((s) => {
      s.playlist.entries.find((y) => y.id === entryId)!.state = "skipped";
    });
  },

  async getNextSession() {
    const s = S();
    const cur = currentNextSession(s.next_session, now(), cfg(), s.visit);
    if (!cur) return null;
    return { task: cur.task, video_title: videoById(cur.task.video_id).short_title, item: itemById(cur.task.item_id), remaining: cur.remaining };
  },

  async answerNextSession(taskId, choice) {
    const task = S().next_session.find((t) => t.id === taskId)!;
    const item = itemById(task.item_id);
    const correct = choice === item.correct_index;
    addResponse(item, choice);
    mutate((s) => {
      const t = s.next_session.find((x) => x.id === taskId)!;
      t.done = true;
      t.result = { choice, correct, at: now() };
      s.visit = { ...s.visit, handled: s.visit.handled + 1 };
    });
    track("next_session_answered", { type: "video", id: task.video_id }, { correct, jol: task.jol });
    if (!correct) rebuildPlaylist(true); // a miss queues a refresher; a manual order stays
    return { correct, item, jol: task.jol };
  },

  async dismissNextSession() {
    mutate((s) => {
      s.visit = { ...s.visit, handled: s.visit.handled + 1 };
    });
  },

  // ---- course
  async getCourseMap() {
    const s = S();
    return {
      lectures: FIX.course.lectures.map((lecture) => ({
        lecture,
        rows: FIX.course.kus.filter((k) => k.lecture_n === lecture.n).map((ku) => {
          const video = ku.video_id ? videoById(ku.video_id) : null;
          const entry = video ? s.playlist.entries.find((e) => e.video_id === video.id) ?? null : null;
          let status: "watched" | "in_playlist" | "skipped" | "not_made" | "available" = "not_made";
          if (video) {
            if (entry?.state === "skipped") status = "skipped";
            else if (s.watched[video.id]) status = "watched";
            else if (entry) status = "in_playlist";
            else status = "available";
          }
          return {
            ku, topic_title: lectureTitle(ku.lecture_n), status,
            video: video ? card(video, entry) : null,
            notes: video ? s.notes.filter((n) => n.video_id === video.id) : [],
          };
        }),
      })),
    };
  },

  async addToPlaylist(videoId) {
    mutate((s) => {
      if (!s.added_videos.includes(videoId)) s.added_videos.push(videoId);
      const existing = s.playlist.entries.find((e) => e.video_id === videoId);
      if (existing) {
        if (existing.state === "skipped") existing.state = s.watched[videoId] ? "watched" : "todo";
      } else {
        s.playlist.entries.push({ id: `pl-${videoId}`, video_id: videoId, tag: "you_added", state: s.watched[videoId] ? "watched" : "todo", skip_reason: null, pos: s.playlist.entries.length });
      }
      s.known_videos = s.known_videos.filter((id) => id !== videoId);
    });
    ensureMade(videoById(videoId).ku_id);
    track("course_video_added", { type: "video", id: videoId });
  },

  // ---- player
  async getVariant(videoId) {
    const s = S();
    const video = videoById(videoId);
    const level = levelOf(video.ku_id);
    const made = s.made[video.ku_id] ?? null;
    const served = servedLevel(made ?? level, [video.file_level]);
    const rows = tailoringRows(video, served.level, FIX.course.kus, FIX.items, s.responses);
    const { active } = displayOrder(s.playlist);
    const idx = active.findIndex((e) => e.video_id === videoId);
    const after = idx >= 0 ? active.slice(idx + 1).find((e) => e.state === "todo") : undefined;
    const claims: ClaimView[] = video.claims.map((c) => {
      const rec = s.claims[`${videoId}:${c.idx}`];
      const seg = video.segments[c.segment_idx];
      return {
        ...c,
        verdict: rec?.verdict ?? null,
        note: rec?.note ?? "",
        slide_urls: c.slide_refs.map((r) => ({ slide: r.slide_number, url: slideUrl(r.slide_number), text: slideText(r.slide_number) })),
        span: [seg.start, seg.end],
      };
    });
    const view: VariantView = {
      video,
      ku_id: video.ku_id,
      level,
      made_level: made,
      served_level: served.level,
      fallback_note: served.note,
      prototype_note: video.file_level !== served.level || served.note !== null,
      review_status: effectiveReview(videoId),
      open_reports: s.reports.filter((r) => r.video_id === videoId && r.status === "open").length,
      checkpoint_item: itemById(video.checkpoint.item_id),
      tailoring: rows,
      changes_count: changesCount(rows),
      claims,
      topic_title: lectureTitle(video.lecture_n),
      lecture_title: lectureTitle(video.lecture_n),
      position: idx >= 0 ? { index: idx, total: active.length } : null,
      next_video: after ? { id: after.video_id, title: videoById(after.video_id).short_title } : null,
    };
    return view;
  },

  async postCheckpointAnswer(a) {
    const video = videoById(a.videoId);
    const item = itemById(video.checkpoint.item_id);
    const correct = a.choice === item.correct_index;
    addResponse(item, a.choice, { confidence: a.confidence, hintUsed: a.hintUsed, latencyMs: a.latencyMs });
    const queued = correct && a.confidence === "guess";
    if (queued) mutate((s) => { s.flags[`guess:${a.videoId}`] = true; });
    track("checkpoint_answered", { type: "item", id: item.id }, { correct, confidence: a.confidence, hint_used: a.hintUsed, latency_ms: a.latencyMs });
    return { correct, queuedForTomorrow: queued };
  },

  async skipCheckpoint(videoId) {
    track("checkpoint_skipped", { type: "video", id: videoId });
  },

  async recordProgress(videoId, t, durationS) {
    mutate((s) => {
      const p = s.progress[videoId];
      s.progress[videoId] = { max_t: Math.max(p?.max_t ?? 0, t), duration_s: durationS, last_at: now() };
    });
  },

  async markWatched(videoId) {
    const video = videoById(videoId);
    ensureMade(video.ku_id);
    const t = now();
    mutate((s) => {
      const w = s.watched[videoId];
      s.watched[videoId] = w ? { ...w, last_at: t, views: w.views + 1 } : { first_at: t, last_at: t, views: 1 };
      const entry = s.playlist.entries.find((e) => e.video_id === videoId);
      if (entry && entry.state === "todo") entry.state = "watched";
      const open = s.next_session.find((x) => x.video_id === videoId && !x.done && x.expires_at > t);
      if (!open) s.next_session.push(createTask(video, t, cfg(), Boolean(s.flags[`guess:${videoId}`])));
      else if (s.flags[`guess:${videoId}`]) open.flagged_guess = true;
    });
    track("video_ended", { type: "video", id: videoId });
  },

  async postJol(videoId, jol) {
    mutate((s) => {
      const open = [...s.next_session].reverse().find((x) => x.video_id === videoId && !x.done);
      if (open) open.jol = jol;
    });
    track("jol_answered", { type: "video", id: videoId }, { jol });
  },

  async postSelfExplanation(videoId, mode, blanks, text) {
    mutate((s) => {
      s.self_explanations = s.self_explanations.filter((x) => x.video_id !== videoId);
      s.self_explanations.push({ video_id: videoId, mode, blanks, text, at: now() });
    });
    track("self_explanation_saved", { type: "video", id: videoId }, { mode, chars: (text || blanks.join(" ")).length });
  },

  async postDifficulty(videoId, d) {
    mutate((s) => {
      s.difficulty[videoId] = d;
    });
    track("difficulty_rated", { type: "video", id: videoId }, { rating: d });
  },

  async listNotes(videoId) {
    return S().notes.filter((n) => n.video_id === videoId).sort((a, b) => a.video_t - b.video_t).map((n) => ({ id: n.id, video_t: n.video_t, text: n.text }));
  },

  async addNote(videoId, videoT, text) {
    mutate((s) => {
      s.notes.push({ id: uid("note"), video_id: videoId, video_t: videoT, text, at: now() });
    });
    track("note_saved", { type: "video", id: videoId }, { video_t: videoT, chars: text.length });
  },

  async updateNote(noteId, text) {
    const note = S().notes.find((n) => n.id === noteId);
    if (!note) throw new Error(`unknown note ${noteId}`);
    mutate((s) => {
      s.notes = s.notes.map((n) => (n.id === noteId ? { ...n, text } : n));
    });
    track("note_saved", { type: "video", id: note.video_id }, { video_t: note.video_t, chars: text.length, edited: true });
  },

  async deleteNote(noteId) {
    const note = S().notes.find((n) => n.id === noteId);
    if (!note) return;
    mutate((s) => {
      s.notes = s.notes.filter((n) => n.id !== noteId);
    });
    track("note_deleted", { type: "video", id: note.video_id }, { video_t: note.video_t });
  },

  async postClaimVerdict(videoId, claimIdx, verdict, note) {
    mutate((s) => {
      s.claims[`${videoId}:${claimIdx}`] = { video_id: videoId, claim_idx: claimIdx, verdict, note, at: now() };
    });
    track("claim_verdict", { type: "claim", id: `${videoId}:${claimIdx}` }, { verdict });
  },

  async postReport(videoId, category, videoT, note) {
    mutate((s) => {
      s.reports.push({ id: uid("rep"), video_id: videoId, category, video_t: videoT, note, status: "open", at: now() });
    });
    track("error_reported", { type: "video", id: videoId }, { category, video_t: videoT });
  },

  // ---- study questionnaires
  async getStudyTasks() {
    if (!research()) return [];
    openDueBatteries();
    const s = S();
    const order = (id: string) => (id === "baseline" ? -1 : studyModules(FIX.course).findIndex((m) => m.id === id));
    return Object.values(s.study)
      .filter((r) => r.submitted_at === null && r.snoozed_visit !== s.visit.id)
      .sort((a, b) => order(a.id) - order(b.id))
      .map((r): StudyTaskView => {
        const items = batteryInstruments(r.id, s.condition).reduce((n, i) => n + visibleItems(i, r.answers).length, 0);
        return { battery_id: r.id, title: batteryTitle(r.id), minutes: Math.max(1, Math.round((items * 9) / 60)), started: r.started_at !== null };
      });
  },

  async getBattery(id) {
    const r = studyRecord(id);
    const view: BatteryView = {
      id, kind: r.kind, title: batteryTitle(id), instruments: batteryInstruments(id, S().condition),
      answers: clone(r.answers), submitted: r.submitted_at !== null,
    };
    return view;
  },

  async saveBatteryAnswers(id, answers) {
    const first = studyRecord(id).started_at === null;
    mutate((s) => {
      const r = s.study[id];
      r.answers = { ...r.answers, ...answers };
      r.started_at ??= now();
    });
    if (first) track("study_started", { type: "battery", id });
  },

  async submitBattery(id) {
    const r = studyRecord(id);
    if (r.submitted_at !== null) return;
    const asked = batteryInstruments(id, S().condition).flatMap((i) => visibleItems(i, r.answers));
    const skipped = asked.filter((it) => r.answers[it.id] === undefined || r.answers[it.id] === null).length;
    mutate((s) => {
      const rec = s.study[id];
      for (const it of asked) if (rec.answers[it.id] === undefined) rec.answers[it.id] = null;
      rec.started_at ??= now();
      rec.submitted_at = now();
    });
    track("study_submitted", { type: "battery", id }, { asked: asked.length, skipped });
  },

  async snoozeBattery(id) {
    studyRecord(id);
    mutate((s) => {
      s.study[id].snoozed_visit = s.visit.id;
    });
    track("study_snoozed", { type: "battery", id });
  },

  async exportStudyCsv() {
    const s = S();
    return studyCsv([{ participant_code: s.participant_code, condition: s.condition, study: s.study }]);
  },

  // ---- data rights
  async exportMyData() {
    const s = S();
    track("data_downloaded", { type: "export" });
    return {
      profile: { levels: s.levels, made: s.made, sittings: s.sittings, overall_level: overall(), consent: s.consent, condition: s.condition },
      responses: s.responses, events: s.events, notes: s.notes, self_explanations: s.self_explanations, settings: s.settings,
      study: s.study,
    };
  },

  async resetModel() {
    mutate((s) => {
      const assessment = s.responses.filter((r) => r.context === "assessment");
      s.archived_models.push({ at: now(), levels: clone(s.levels), assessment_responses: assessment });
      // start over: the retaken check draws fresh evidence; watch history, notes and video answers stay
      s.responses = s.responses.filter((r) => r.context !== "assessment");
      s.levels = {};
      s.made = {};
      s.sittings = {};
      s.level_updates = [];
      s.picked_own = false;
      s.playlist = { entries: [], manual_order: null, built_at_week: week() };
    });
    track("model_reset", { type: "model" });
  },
};
