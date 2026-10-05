import { track } from "@/lib/events";
import { FIX, itemById, itemsFor, lectureByN, slideText, slideUrl, topicById, videoById } from "@/lib/fixtures";
import { calibrationBlock1, calibrationBlock2 } from "@/lib/logic/calibration";
import { icsFor } from "@/lib/logic/ics";
import { onboardingLevel, overallLevel } from "@/lib/logic/levels";
import { createTask, currentNextSession } from "@/lib/logic/nextSession";
import {
  buildEntries,
  buildPlaylistState,
  displayOrder,
  servedLevel,
  upcomingLecture,
  whyOrder,
  type BuildInput,
} from "@/lib/logic/playlist";
import { changedProposals, proposeLevels } from "@/lib/logic/proposals";
import { changesCount, tailoringRows } from "@/lib/logic/receipt";
import { describeSlot, recheckSlots, weekOf } from "@/lib/logic/time";
import { getState, mutate, now } from "@/lib/store";
import type {
  ClaimView, Choice, DiffRow, Item, Level, PlaylistDiff, PlaylistEntry, ResponseRecord,
  ReviewStatus, TopicLevel, Video, VideoCardView, VariantView,
} from "@/lib/types";
import { DAY, uid } from "@/lib/util";
import type { Api, OnboardingItemView, ProposalRow } from "./types";

// ----------------------------------------------------------------- helpers

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const S = () => getState();
const cfg = () => FIX.course.config;
const week = () => weekOf(now(), S().semester_start);
const topicTitle = (id: string) => topicById(id).title;

function roundRobin(context: Item["context"]): Item[] {
  const per = FIX.course.topics.map((t) => itemsFor(context).filter((i) => i.topic_id === t.id));
  const out: Item[] = [];
  const max = Math.max(0, ...per.map((a) => a.length));
  for (let k = 0; k < max; k++) for (const list of per) if (list[k]) out.push(list[k]);
  return out;
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
    video_id: item.context === "onboarding" || item.context === "recheck" ? null : item.ku_id,
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

function buildInput(prev: PlaylistEntry[], levels = S().levels): BuildInput {
  const s = S();
  return {
    course: FIX.course, videos: FIX.videos, items: FIX.items, levels, responses: s.responses, watched: s.watched,
    review: reviewMap(), prev, known: s.known_videos, added: s.added_videos, week: week(),
  };
}

function rebuildPlaylist(keepManual = false): void {
  mutate((s) => {
    const next = buildPlaylistState(buildInput(s.playlist.entries));
    next.manual_order = keepManual ? s.playlist.manual_order : null;
    s.playlist = next;
  });
}

function levelOf(topicId: string): Level {
  return S().levels[topicId]?.level ?? 2;
}

function card(video: Video, entry: PlaylistEntry | null): VideoCardView {
  const level = levelOf(video.topic_id);
  const served = servedLevel(level, [video.file_level]);
  return {
    entry_id: entry?.id ?? null,
    video_id: video.id,
    title: video.short_title,
    lecture_n: video.lecture_n,
    duration_s: video.duration_s,
    poster_url: video.poster_url,
    tag: entry?.tag ?? null,
    state: entry?.state ?? (S().watched[video.id] ? "watched" : "todo"),
    topic_id: video.topic_id,
    topic_title: topicTitle(video.topic_id),
    level,
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

function levelsAfterAccepted(): Record<string, TopicLevel> {
  const out = clone(S().levels);
  for (const p of S().recheck.proposals) {
    if ((p.direction === "up" || p.direction === "down") && p.decision === "accepted" && out[p.topic_id]) out[p.topic_id].level = p.to;
  }
  return out;
}

function computeDiff(): PlaylistDiff {
  const s = S();
  const accepted = new Set(s.recheck.proposals.filter((p) => p.decision === "accepted" && p.direction !== "same" && p.direction !== "not_enough").map((p) => p.topic_id));
  const after = buildEntries(buildInput(s.playlist.entries, levelsAfterAccepted())).filter((e) => e.state !== "skipped");
  const before = s.playlist.entries.filter((e) => e.state !== "skipped");
  const bIds = new Set(before.map((e) => e.video_id));
  const aIds = new Set(after.map((e) => e.video_id));
  const row = (video_id: string, reason: string): DiffRow => ({ video_id, title: videoById(video_id).short_title, topic_title: topicTitle(videoById(video_id).topic_id), reason });
  const lvl = levelsAfterAccepted();
  return {
    new: after.filter((e) => !bIds.has(e.video_id)).map((e) => row(e.video_id, e.tag === "gap" ? "Fills a gap." : e.tag === "refresher" ? "A short refresher." : "New for you.")),
    swapped: after
      .filter((e) => bIds.has(e.video_id) && accepted.has(videoById(e.video_id).topic_id))
      .map((e) => row(e.video_id, `“${topicTitle(videoById(e.video_id).topic_id)}” moves to Level ${lvl[videoById(e.video_id).topic_id].level}.`)),
    removed: before
      .filter((e) => !aIds.has(e.video_id))
      .map((e) => row(e.video_id, `“${topicTitle(videoById(e.video_id).topic_id)}” is at Level ${lvl[videoById(e.video_id).topic_id].level}, which you already know.`)),
  };
}

function onboardingViews(items: Item[], answers: Record<string, Choice>): OnboardingItemView[] {
  return items.map((item, i) => ({ item, topic_title: topicTitle(item.topic_id), index: i, total: items.length, answer: answers[item.id] }));
}

function entryFor(entryId: string): PlaylistEntry {
  const e = S().playlist.entries.find((x) => x.id === entryId);
  if (!e) throw new Error(`unknown playlist entry ${entryId}`);
  return e;
}

function describeLevelChange(topic: string, from: Level, to: Level, cause: string, at: number): string {
  const wk = weekOf(at, S().semester_start);
  const when = cause === "week7" ? "at your Week 7 check-in" : cause === "use_suggested" ? `in Week ${wk}, when you went back to our level` : `in Week ${wk}, when you changed it`;
  return `“${topic}” went from Level ${from} to Level ${to} ${when}.`;
}

// --------------------------------------------------------------------- api

export const mockApi: Api = {
  async getMe() {
    const s = S();
    return {
      course: FIX.course, participant_code: s.participant_code, consent: s.consent, condition: s.condition, week: week(),
      now: now(), settings: s.settings, onboarding_done: s.onboarding.done,
    };
  },

  async postConsent(research) {
    mutate((s) => {
      s.consent = research ? "research" : "no_research";
      s.condition = "A";
    });
    track("consent_given", { type: "consent" }, { research });
  },

  async withdrawFromResearch(deletePast) {
    mutate((s) => {
      s.consent = "no_research";
      if (deletePast) s.events = [];
    });
  },

  async updateSettings(patch) {
    const before = S().settings;
    mutate((s) => {
      s.settings = { ...s.settings, ...patch };
    });
    if (patch.captions !== undefined && patch.captions !== before.captions) track("captions_toggled", { type: "setting" }, { on: patch.captions, from: "settings" });
  },

  // ---- onboarding
  async getOnboardingItems() {
    return onboardingViews(roundRobin("onboarding"), S().onboarding.answers);
  },

  async answerOnboarding(itemId, choice, latencyMs) {
    const item = itemById(itemId);
    mutate((s) => {
      s.onboarding.answers[itemId] = choice;
    });
    addResponse(item, choice, { latencyMs, replace: true });
    track("onboarding_answered", { type: "item", id: itemId }, { choice, topic: item.topic_id, correct: choice === "not_sure" ? null : choice === item.correct_index });
  },

  async finishOnboarding() {
    mutate((s) => {
      for (const topic of FIX.course.topics) {
        const r = onboardingLevel(topic, FIX.items, s.onboarding.answers, lectureByN(topic.first_lecture).title);
        s.levels[topic.id] = {
          topic_id: topic.id, level: r.level, source: "model", suggested_level: r.level, reason: r.reason, not_checked: r.notChecked,
          history: [{ level: r.level, source: "model", at: now(), cause: "onboarding" }],
        };
      }
      s.onboarding.done = true;
    });
    rebuildPlaylist();
    for (const t of FIX.course.topics) track("level_suggested", { type: "topic", id: t.id }, { level: S().levels[t.id].level });
  },

  async pickAllLevels(level, fromQuestion) {
    mutate((s) => {
      for (const topic of FIX.course.topics) {
        const r = onboardingLevel(topic, FIX.items, s.onboarding.answers, lectureByN(topic.first_lecture).title);
        s.levels[topic.id] = {
          topic_id: topic.id, level, source: "student", suggested_level: r.level, reason: r.reason, not_checked: false,
          history: [{ level, source: "student", at: now(), cause: "pick_all" }],
        };
      }
      s.onboarding.done = true;
      s.onboarding.picked_own = true;
    });
    rebuildPlaylist();
    track("level_corrected", { type: "all_topics" }, { to: level, source_screen: "onboarding_pick_own", at_question: fromQuestion });
  },

  async getOnboardingResult() {
    const s = S();
    const topics = FIX.course.topics.map((topic) => ({ topic, level: s.levels[topic.id] }));
    const checked = topics.filter((t) => t.level && !t.level.not_checked).map((t) => t.level.level);
    return {
      overall_level: overallLevel(checked),
      topics,
      review: roundRobin("onboarding").map((item) => ({ item, choice: s.onboarding.answers[item.id] })),
    };
  },

  async keepLevels() {
    for (const t of FIX.course.topics) track("level_kept", { type: "topic", id: t.id }, { level: S().levels[t.id]?.level });
  },

  // ---- levels
  async getLevels() {
    const s = S();
    const topics = FIX.course.topics.filter((t) => s.levels[t.id]).map((topic) => ({ topic, level: s.levels[topic.id] }));
    const lines: string[] = [];
    for (const { topic, level } of topics) {
      for (let i = 1; i < level.history.length; i++) lines.push(describeLevelChange(topic.title, level.history[i - 1].level, level.history[i].level, level.history[i].cause, level.history[i].at));
    }
    const wk = week();
    return {
      overall_level: overall(), topics, history_lines: lines, week: wk, recheck_status: s.recheck.status,
      week7_applied: Boolean(s.recheck.applied) && s.recheck.mode !== "keep_old",
      recheck_due: s.recheck.status === "skipped" && wk < cfg().recheck_skip_until_week,
    };
  },

  async correctLevel(topicId, level, reasonChip, note, sourceScreen) {
    const previous = clone(S().levels[topicId]) as TopicLevel;
    const from = previous?.level;
    mutate((s) => {
      const tl = s.levels[topicId] ?? { topic_id: topicId, level, source: "model", suggested_level: 1, reason: "", not_checked: false, history: [] };
      tl.level = level;
      tl.source = "student";
      tl.not_checked = false;
      tl.history.push({ level, source: "student", at: now(), cause: "student" });
      s.levels[topicId] = tl;
    });
    track("level_corrected", { type: "topic", id: topicId }, { from, to: level, reason: reasonChip, note, source_screen: sourceScreen });
    return { previous };
  },

  async restoreLevel(previous) {
    mutate((s) => {
      s.levels[previous.topic_id] = previous;
    });
    track("undo", { type: "level", id: previous.topic_id });
  },

  async useSuggestedLevel(topicId) {
    mutate((s) => {
      const tl = s.levels[topicId];
      if (!tl) return;
      tl.level = tl.suggested_level;
      tl.source = "model";
      tl.history.push({ level: tl.level, source: "model", at: now(), cause: "use_suggested" });
    });
    track("level_corrected", { type: "topic", id: topicId }, { to: S().levels[topicId]?.level, source_screen: "use_suggested" });
  },

  async getCalibration() {
    const s = S();
    return { block1: calibrationBlock1(s.responses), block2: calibrationBlock2(s.next_session, FIX.videos) };
  },

  // ---- playlist
  async getPlaylist() {
    const s = S();
    const upcoming = upcomingLecture(FIX.course, week());
    if (!s.onboarding.done) {
      return { overall_level: null, cards: [], skipped: [], why: "", manual: false, total_seconds: 0, watched_count: 0, upcoming_lecture: upcoming, current_entry_id: null, empty_message: null };
    }
    const { active, skipped } = displayOrder(s.playlist);
    const current = active.find((e) => e.state === "todo")?.id ?? null;
    const cards = active.map((e) => card(videoById(e.video_id), e));
    const todo = cards.filter((c) => c.state === "todo");
    return {
      overall_level: overall(),
      cards,
      skipped: skipped.map((e) => card(videoById(e.video_id), e)),
      why: whyOrder({ upcoming, manual: Boolean(s.playlist.manual_order), entries: active, videos: FIX.videos, topicTitle }),
      manual: Boolean(s.playlist.manual_order),
      total_seconds: todo.reduce((n, c) => n + c.duration_s, 0),
      watched_count: Object.keys(s.watched).length,
      upcoming_lecture: upcoming,
      current_entry_id: current,
      empty_message: active.length === 0 && skipped.length === 0 ? `Your Lecture ${upcoming} videos are being made. Check back soon.` : null,
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
            ku, topic_title: topicTitle(ku.topic_id), status,
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
    track("course_video_added", { type: "video", id: videoId });
  },

  // ---- player
  async getVariant(videoId) {
    const s = S();
    const video = videoById(videoId);
    const level = levelOf(video.topic_id);
    const served = servedLevel(level, [video.file_level]);
    const rows = tailoringRows(video, served.level, FIX.course.topics, s.responses);
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
      level,
      served_level: served.level,
      fallback_note: served.note,
      prototype_note: video.file_level !== served.level || served.note !== null,
      review_status: effectiveReview(videoId),
      open_reports: s.reports.filter((r) => r.video_id === videoId && r.status === "open").length,
      checkpoint_item: itemById(video.checkpoint.item_id),
      tailoring: rows,
      changes_count: changesCount(rows),
      claims,
      topic_title: topicTitle(video.topic_id),
      lecture_title: lectureByN(video.lecture_n).title,
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

  async markWatched(videoId) {
    const video = videoById(videoId);
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

  // ---- week 7
  async getRecheckStatus() {
    const s = S();
    const wk = week();
    const r = s.recheck;
    const inWindow = wk >= cfg().recheck_week;
    return {
      status: r.status,
      week: wk,
      in_window: inWindow,
      invite_seen: r.invite_seen_at !== null,
      slot: r.slot,
      slot_text: r.slot ? describeSlot(r.slot, now()) : null,
      slots: recheckSlots(now()),
      videos_watched: Object.keys(s.watched).length,
      skipped_until_week: cfg().recheck_skip_until_week,
      pinned: inWindow && r.invite_seen_at !== null && (r.status === "idle" || r.status === "scheduled" || r.status === "in_progress"),
    };
  },

  async markInviteSeen() {
    mutate((s) => {
      if (s.recheck.invite_seen_at === null) s.recheck.invite_seen_at = now();
    });
  },

  async scheduleRecheck(slotId) {
    const slot = recheckSlots(now()).find((x) => x.id === slotId) ?? recheckSlots(now())[0];
    mutate((s) => {
      s.recheck.slot = slot;
      s.recheck.status = slot.id === "now" ? "in_progress" : "scheduled";
    });
    track("recheck_scheduled", { type: "recheck" }, { slot: slot.id });
    return {
      slot,
      text: describeSlot(slot, now()),
      ics: icsFor({
        title: `${FIX.course.name}: Week 7 check-in`, description: "6 questions, about 3 minutes. Not graded. It only retunes what comes next.",
        start: slot.at, minutes: 5, uid: uid("recheck"),
      }),
    };
  },

  async skipRecheck() {
    mutate((s) => {
      s.recheck.status = "skipped";
    });
  },

  async getRecheckItems() {
    return onboardingViews(roundRobin("recheck"), S().recheck.answers);
  },

  async answerRecheck(itemId, choice, latencyMs) {
    const item = itemById(itemId);
    mutate((s) => {
      s.recheck.answers[itemId] = choice;
      s.recheck.status = "in_progress";
    });
    addResponse(item, choice, { latencyMs, replace: true });
    track("recheck_answered", { type: "item", id: itemId }, { choice, correct: choice === "not_sure" ? null : choice === item.correct_index });
  },

  async finishRecheck() {
    const s = S();
    const proposals = proposeLevels({
      course: FIX.course, items: FIX.items, videos: FIX.videos, responses: s.responses, levels: s.levels, watched: s.watched,
      semesterStart: s.semester_start, now: now(),
    });
    mutate((st) => {
      st.recheck.proposals = proposals;
      st.recheck.status = "done";
      st.recheck.applied = null;
      st.recheck.mode = null;
    });
  },

  async getProposals() {
    const s = S();
    const proposals: ProposalRow[] = s.recheck.proposals.map((p) => ({ ...p, topic_title: topicTitle(p.topic_id) }));
    const applied = s.recheck.applied;
    return {
      proposals,
      diff: computeDiff(),
      applied,
      mode: s.recheck.mode,
      undo_available: Boolean(applied) && now() - applied!.at < DAY,
    };
  },

  async decideProposal(topicId, decision, disputeText) {
    mutate((s) => {
      const p = s.recheck.proposals.find((x) => x.topic_id === topicId);
      if (p) {
        p.decision = decision;
        p.dispute_text = decision === "disputed" ? disputeText : "";
      }
    });
  },

  async applyDecisions(mode) {
    const s0 = S();
    const changed = changedProposals(s0.recheck.proposals);
    const diff = computeDiff();
    const snapshot = {
      at: now(), levels: clone(s0.levels), playlist: clone(s0.playlist),
      summary: {
        accepted: changed.filter((p) => p.decision === "accepted").length,
        kept: changed.filter((p) => p.decision !== "accepted").length,
        new: diff.new.length, swapped: diff.swapped.length, removed: diff.removed.length,
      },
    };
    mutate((s) => {
      for (const p of s.recheck.proposals) {
        if (p.direction !== "up" && p.direction !== "down") continue;
        if (mode === "keep_old") p.decision = "kept";
        else if (p.decision === null) p.decision = "ignored";
        if (mode !== "keep_old" && p.decision === "accepted") {
          const tl = s.levels[p.topic_id];
          if (tl) {
            tl.level = p.to;
            tl.suggested_level = p.to;
            tl.source = "model";
            tl.history.push({ level: p.to, source: "model", at: now(), cause: "week7" });
          }
        }
      }
      s.recheck.applied = snapshot;
      s.recheck.mode = mode;
    });
    if (mode === "apply") rebuildPlaylist(false);
    for (const p of S().recheck.proposals.filter((x) => x.direction === "up" || x.direction === "down")) {
      track("proposal_decided", { type: "topic", id: p.topic_id }, { decision: p.decision, from: p.from, to: p.to });
    }
    track("playlist_applied", { type: "playlist" }, { mode, ...snapshot.summary });
  },

  async undoApply() {
    const snap = S().recheck.applied;
    if (!snap || now() - snap.at >= DAY) return;
    mutate((s) => {
      s.levels = snap.levels;
      s.playlist = snap.playlist;
      s.recheck.applied = null;
      s.recheck.mode = null;
      for (const p of s.recheck.proposals) p.decision = null;
    });
    track("undo", { type: "playlist_apply" });
  },

  // ---- data rights
  async exportMyData() {
    const s = S();
    track("data_downloaded", { type: "export" });
    return {
      profile: { levels: s.levels, overall_level: overall(), consent: s.consent, condition: s.condition },
      responses: s.responses, events: s.events, notes: s.notes, self_explanations: s.self_explanations, settings: s.settings,
    };
  },

  async resetModel() {
    mutate((s) => {
      s.archived_models.push({ at: now(), levels: clone(s.levels) });
      s.levels = {};
      s.onboarding = { answers: {}, done: false, picked_own: false };
      s.playlist = { entries: [], manual_order: null, built_at_week: week() };
    });
    track("model_reset", { type: "model" });
  },
};
