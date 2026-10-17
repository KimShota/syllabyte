import type { Choice, Course, Item, ItemContext, KuLevel, Level, ResponseRecord, Topic, Video } from "../src/types";

export const T0 = new Date("2026-10-05T10:00:00").getTime();

export const topics: Topic[] = [
  { id: "lecture-1", title: "L1", ku_ids: [], first_lecture: 1 },
  { id: "lecture-2", title: "L2", ku_ids: [], first_lecture: 2 },
  { id: "lecture-3", title: "L3", ku_ids: [], first_lecture: 3 },
];

export const course: Course = {
  id: "c",
  code: "X",
  name: "Course",
  eyebrow: "COURSE",
  syllabus_summary: "",
  topics,
  lectures: [
    { n: 1, title: "L1", week: 1, slide_start: 1, slide_end: 16 },
    { n: 2, title: "L2", week: 2, slide_start: 17, slide_end: 24 },
    { n: 3, title: "L3", week: 3, slide_start: 25, slide_end: 34 },
  ],
  kus: [],
  config: {
    playlist_max_videos: 6, playlist_max_seconds: 600, next_session_min_hours: 12,
    next_session_max_per_visit: 2, next_session_expiry_days: 7, retention_due_days: 3, retention_delay_days: 14,
    reveal_retention_scores_after_week_14: false, upcoming_lecture_override: 3,
    cat_start_theta: 0, cat_items_per_topic: 4, cat_week0_length: 16, cat_week0_lectures: 4, cat_prelecture_new: 4,
    cat_prelecture_review: 2, irt_hint_beta_shift: 1, refresher_dropoff_fraction: 0.6, refresher_replay_count: 3,
  },
};

export function item(id: string, topic_id: string, context: ItemContext, extra: Partial<Item> = {}): Item {
  return {
    id, ku_id: null, topic_id, context, stem: `Q ${id}`, options: ["a", "b", "c"], correct_index: 1,
    allows_not_sure: context !== "checkpoint" && context !== "next_session", explanation: "because", hint: "hint",
    difficulty_prior: 0, discrimination: 1, tier: null, source_refs: [], ...extra,
  };
}

export function video(id: string, topic_id: string, lecture_n: number, slide: number, extra: Partial<Video> = {}): Video {
  const sk = (kind: "left_out" | "added" | "set_to", what: string, dimension: "recap" | "example" | "support", ev: string | null) => ({ kind, what, dimension, evidence_ku_id: ev });
  return {
    id, ku_id: id, title: `Video ${id}: a long full title`, short_title: `Video ${id}`, topic_id, lecture_n, file_level: 2, duration_s: 70, video_url: "", poster_url: "", vtt_url: "",
    segments: [], checkpoint: { t: 60, rewatch_from: 40, item_id: `cp-${id}` }, next_session_item_id: `ns-${id}`, prove_it_item_id: `pi-${id}`,
    sentence_frame: { template: "a ___ b ___", answers: ["x", "y"] }, claims: [],
    tailoring: {
      "1": [sk("added", "Short recap", "recap", id), sk("added", "Full example", "example", id), sk("set_to", "Hints shown", "support", null)],
      "2": [sk("left_out", "Full recap", "recap", id), sk("added", "One example", "example", id), sk("set_to", "Hints on request", "support", null)],
      "3": [sk("left_out", "Recap", "recap", id), sk("left_out", "Example", "example", id), sk("set_to", "No hints", "support", null)],
    },
    transcript: [], source_slides: [slide], prerequisite_titles: [], review_status: "unreviewed", ...extra,
  };
}

let n = 0;
export function resp(item_id: string, topic_id: string, context: ItemContext, choice: Choice, extra: Partial<ResponseRecord> = {}): ResponseRecord {
  n += 1;
  const correct = choice === "not_sure" ? null : choice === 1;
  return {
    id: `r${n}`, item_id, topic_id, video_id: null, context, choice, correct, confidence: null, hint_used: false,
    latency_ms: 1000, at: T0 + n, ...extra,
  };
}

/** A published KU level, as the playlist builder and the profile see it. */
export function level(ku_id: string, l: Level, source: "model" | "student" = "model", at = T0): KuLevel {
  return { ku_id, level: l, source, suggested_level: l, reason: "", not_checked: false, provisional: false, history: [{ level: l, source, at, cause: "baseline" }] };
}
