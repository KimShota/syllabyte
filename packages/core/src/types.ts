/**
 * Shared types. The "fixture" half mirrors packages/common/syllabyte_common/learner.py
 * (keep both in sync); the rest are app-state and view models. From Phase 1 the API
 * types are generated from FastAPI's OpenAPI schema and must match these shapes.
 */

export type Level = 1 | 2 | 3;
export type Confidence = "guess" | "pretty" | "certain";
export type Choice = number | "not_sure";
export type ItemContext =
  | "checkpoint" | "next_session" | "prove_it" | "retention"
  /** the per-KU item bank: Week 0 baseline, pre-lecture checks and review questions */
  | "assessment";
/** Bloom's taxonomy level of a Knowledge Unit (mirrors syllabyte_common.models.BloomLevel). */
export type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";
/** Tier of an item in the per-KU bank: basic = Remember/Understand, applied = Apply/Analyze, advanced = Evaluate/Create. */
export type ItemTier = "basic" | "applied" | "advanced";
export type ReviewStatus = "unreviewed" | "approved" | "flagged" | "hidden";
export type TailoringKind = "left_out" | "added" | "set_to";
export type Condition = "A" | "B";

// ---------------------------------------------------------------- fixtures

export interface SlideRef {
  deck_name: string;
  slide_number: number;
}

export interface Item {
  id: string;
  ku_id: string | null;
  topic_id: string;
  context: ItemContext;
  stem: string;
  options: string[];
  correct_index: number;
  allows_not_sure: boolean;
  explanation: string;
  hint: string | null;
  /** IRT difficulty (β), logit scale */
  difficulty_prior: number;
  /** IRT discrimination (α); fixed at 1 until post-pilot calibration */
  discrimination: number;
  /** per-KU item bank tier; null on the legacy onboarding / re-check / video items */
  tier: ItemTier | null;
  source_refs: SlideRef[];
}

/** A topic is a lecture (plan/per-ku-profiling-plan.md D2): the unit one CAT ability is estimated for. */
export interface Topic {
  /** "lecture-<n>" */
  id: string;
  title: string;
  ku_ids: string[];
  first_lecture: number;
}

export interface Lecture {
  n: number;
  title: string;
  week: number;
  slide_start: number;
  slide_end: number;
}

export interface KuEntry {
  id: string;
  title: string;
  short_title: string;
  topic_id: string;
  lecture_n: number;
  video_id: string | null;
  bloom_level: BloomLevel;
  /** ids of the KUs this one builds on (the Knowledge Unit Graph is a DAG) */
  prerequisites: string[];
}

export interface CourseConfig {
  playlist_max_videos: number;
  playlist_max_seconds: number;
  next_session_min_hours: number;
  next_session_max_per_visit: number;
  next_session_expiry_days: number;
  retention_due_days: number;
  retention_delay_days: number;
  reveal_retention_scores_after_week_14: boolean;
  // Adaptive assessment (plan/per-ku-profiling-plan.md D7-D13); mirrors CourseConfig in learner.py.
  cat_start_theta: number;
  /** a topic is a lecture */
  cat_items_per_topic: number;
  /** the baseline before any video */
  cat_week0_length: number;
  /** how many of the first lectures the baseline covers */
  cat_week0_lectures: number;
  /** items on the lecture about to start */
  cat_prelecture_new: number;
  /** items from earlier lectures, aimed where theta is least certain */
  cat_prelecture_review: number;
  /** an answer given after a hint is scored as the item made this much easier */
  irt_hint_beta_shift: number;
  /** left a video before this share of it: it goes back to the top of the playlist */
  refresher_dropoff_fraction: number;
  /** watched this many times: queue it as a refresher */
  refresher_replay_count: number;
  upcoming_lecture_override: number | null;
  /** the study's modules (plan/study-instruments-plan.md I2); null or absent = the lectures split in two */
  study_modules?: StudyModule[] | null;
}

/** A group of lectures; its questionnaire battery opens once the schedule has moved past its last lecture. */
export interface StudyModule {
  id: string;
  title: string;
  lectures: number[];
}

/** One questionnaire battery's answers (plan/study-instruments-plan.md): the baseline or a module's end. */
export interface BatteryRecord {
  id: string;
  kind: "baseline" | "module";
  /** INSTRUMENTS_VERSION the answers were given under */
  version: string;
  /** when it became due: sign-up for the baseline, the module's end for a module battery */
  opened_at: number;
  started_at: number | null;
  submitted_at: number | null;
  /** "Not now" hides it until the next visit (I9) */
  snoozed_visit: string | null;
  /** item id -> answer; null = skipped on purpose (I10); absent = not reached */
  answers: Record<string, number | string | null>;
}

export interface Course {
  id: string;
  code: string;
  name: string;
  eyebrow: string;
  syllabus_summary: string;
  config: CourseConfig;
  topics: Topic[];
  lectures: Lecture[];
  kus: KuEntry[];
}

export interface SegmentSpan {
  phase: "prepare" | "initiate" | "deliver" | "end";
  start: number;
  end: number;
}

export interface Checkpoint {
  t: number;
  rewatch_from: number;
  item_id: string;
}

export interface Claim {
  idx: number;
  text: string;
  segment_idx: number;
  slide_refs: SlideRef[];
  lecture_clip: string | null;
}

export interface TailoringSkeleton {
  kind: TailoringKind;
  what: string;
  dimension: "recap" | "example" | "support";
  /** the KU whose answers the receipt cites for this row */
  evidence_ku_id: string | null;
}

export interface SentenceFrame {
  template: string;
  answers: string[];
}

export interface TranscriptRow {
  t: number;
  narration: string;
  visual: string | null;
}

export interface Video {
  id: string;
  ku_id: string;
  title: string;
  short_title: string;
  topic_id: string;
  lecture_n: number;
  file_level: Level;
  duration_s: number;
  video_url: string;
  poster_url: string;
  vtt_url: string;
  segments: SegmentSpan[];
  checkpoint: Checkpoint;
  next_session_item_id: string;
  prove_it_item_id: string;
  sentence_frame: SentenceFrame;
  claims: Claim[];
  tailoring: Record<"1" | "2" | "3", TailoringSkeleton[]>;
  transcript: TranscriptRow[];
  source_slides: number[];
  prerequisite_titles: string[];
  review_status: ReviewStatus;
}

export interface Fixtures {
  course: Course;
  items: Item[];
  videos: Video[];
  slides: Record<string, string>;
}

// ------------------------------------------------------------ app state

export interface ResponseRecord {
  id: string;
  item_id: string;
  topic_id: string;
  video_id: string | null;
  context: ItemContext;
  choice: Choice;
  /** null when choice is "not_sure" */
  correct: boolean | null;
  confidence: Confidence | null;
  hint_used: boolean;
  latency_ms: number;
  at: number;
}

export type LevelCause = "baseline" | "lecture_check" | "student" | "reset" | "use_suggested" | "pick_all";

export interface LevelChange {
  level: Level;
  source: "model" | "student";
  at: number;
  cause: LevelCause;
}

/** One Knowledge Unit's level (plan D6): published at lecture boundaries, correctable by the student any time. */
export interface KuLevel {
  ku_id: string;
  level: Level;
  source: "model" | "student";
  /** what the model would set now; used by "Use suggested level" */
  suggested_level: Level;
  /** a template over the stored answers (plan §2 rule 4) */
  reason: string;
  /** nothing answered anywhere yet (dashed card on My levels) */
  not_checked: boolean;
  /** the level rests on other lectures' answers: this lecture has not been asked about yet */
  provisional: boolean;
  history: LevelChange[];
}

export type PlaylistTag = "gap" | "new" | "refresher" | "you_added";

export interface PlaylistEntry {
  id: string;
  video_id: string;
  tag: PlaylistTag;
  state: "todo" | "watched" | "skipped";
  skip_reason: string | null;
  /** position in the suggested order */
  pos: number;
}

export interface WatchRecord {
  first_at: number;
  last_at: number;
  views: number;
}

export type Jol = "yes" | "maybe" | "no";

export interface NextSessionTask {
  id: string;
  video_id: string;
  item_id: string;
  jol: Jol | null;
  due_after: number;
  expires_at: number;
  done: boolean;
  /** the student rated a correct checkpoint answer "Guessing" */
  flagged_guess: boolean;
  result: { choice: number; correct: boolean; at: number } | null;
}

export interface ClaimVerdictRecord {
  video_id: string;
  claim_idx: number;
  verdict: "matches" | "mismatch";
  note: string;
  at: number;
}

export type ReportCategory = "fact" | "picture" | "captions" | "layout" | "other";

export interface ReportRecord {
  id: string;
  video_id: string;
  category: ReportCategory;
  video_t: number;
  note: string;
  status: "open" | "resolved";
  at: number;
}

export interface NoteRecord {
  id: string;
  video_id: string;
  video_t: number;
  text: string;
  at: number;
}

export interface SelfExplanationRecord {
  video_id: string;
  mode: "frame" | "free";
  blanks: string[];
  text: string;
  at: number;
}

export type Difficulty = "too_easy" | "just_right" | "too_hard";

/** How far into a video the student has ever got (drives "pick up where you left off", plan D13). */
export interface ProgressRecord {
  max_t: number;
  duration_s: number;
  last_at: number;
}

/** One adaptive sitting: the Week 0 baseline or a pre-lecture check (plan D8). */
export interface SittingState {
  id: string;
  kind: "week0" | "lecture";
  lecture_n: number | null;
  /** ids of the items answered so far, in order; a sitting is just its plan and these */
  answered_ids: string[];
  started_at: number;
  finished_at: number | null;
  skipped: boolean;
  /** the lecture week it was finished in */
  week: number | null;
}

/** A KU level that moved at a lecture boundary: one row of the "What changed and why" card. */
export interface LevelUpdate {
  ku_id: string;
  from: Level;
  to: Level;
  direction: "up" | "down";
  /** a template over the stored counts */
  reason: string;
}

export interface PendingLevelUpdates {
  id: string;
  lecture_n: number;
  at: number;
  updates: LevelUpdate[];
  seen: boolean;
}

export interface PlaylistState {
  entries: PlaylistEntry[];
  manual_order: string[] | null;
  built_at_week: number;
}

export interface AppSettings {
  captions: boolean;
  weekly_email: boolean;
}

export type EventVerb =
  | "consent_given" | "cat_answered" | "cat_finished" | "level_suggested" | "levels_updated" | "level_kept" | "level_corrected"
  | "playlist_viewed" | "reordered" | "skipped" | "skip_reason" | "undo" | "prove_it_result"
  | "video_play" | "video_pause" | "video_seek" | "video_ended" | "speed_changed" | "captions_toggled"
  | "transcript_opened" | "note_saved" | "note_deleted" | "checkpoint_shown" | "checkpoint_answered" | "checkpoint_skipped"
  | "hint_used" | "rewatch_part" | "receipt_opened" | "full_version_requested" | "about_opened"
  | "claim_slide_viewed" | "claim_verdict" | "error_reported" | "difficulty_rated" | "jol_answered"
  | "self_explanation_saved" | "next_session_answered" | "course_video_added" | "data_downloaded" | "model_reset"
  | "study_shown" | "study_started" | "study_submitted" | "study_snoozed";

export interface AppEvent {
  id: string;
  verb: EventVerb;
  object: { type: string; id?: string };
  result?: Record<string, unknown>;
  context: {
    screen: string;
    device: "mobile" | "desktop";
    orientation: "portrait" | "landscape";
    condition: Condition;
    participant_code: string | null;
    week: number;
  };
  timestamp: string;
}

export interface DemoState {
  v: 2;
  clock_offset_ms: number;
  semester_start: number;
  participant_code: string | null;
  consent: null | "research" | "no_research";
  condition: Condition;
  /** the student set one level for everything instead of taking the baseline ("Pick my own level") */
  picked_own: boolean;
  /** adaptive sittings by id: "week0" and "lecture-<n>" */
  sittings: Record<string, SittingState>;
  /** the published level of every KU; changes only at lecture boundaries or when the student corrects it */
  levels: Record<string, KuLevel>;
  /** the level each KU's video was made at for this student; a video is made once and never remade (D15) */
  made: Record<string, Level>;
  progress: Record<string, ProgressRecord>;
  /** "What changed and why" cards, newest last */
  level_updates: PendingLevelUpdates[];
  /** demo override: the lecture treated as upcoming (null = from the schedule) */
  upcoming_lecture: number | null;
  responses: ResponseRecord[];
  playlist: PlaylistState;
  watched: Record<string, WatchRecord>;
  next_session: NextSessionTask[];
  visit: { id: string; handled: number };
  claims: Record<string, ClaimVerdictRecord>;
  reports: ReportRecord[];
  notes: NoteRecord[];
  self_explanations: SelfExplanationRecord[];
  difficulty: Record<string, Difficulty>;
  review: Record<string, ReviewStatus>;
  added_videos: string[];
  /** videos skipped as "I already know this" with the prove-it passed */
  known_videos: string[];
  /** models archived by "Reset my model" (kept for the study, plan Q30) */
  archived_models: { at: number; levels: Record<string, KuLevel>; assessment_responses: ResponseRecord[] }[];
  settings: AppSettings;
  events: AppEvent[];
  /** questionnaire batteries by id ("baseline", "module-1", ...), research participants only */
  study: Record<string, BatteryRecord>;
  /** one-time UI flags */
  flags: Record<string, boolean>;
}

// ------------------------------------------------------------- view models

export type ServedLevel = Level;

export interface VideoCardView {
  entry_id: string | null;
  video_id: string;
  title: string;
  lecture_n: number;
  duration_s: number;
  poster_url: string;
  tag: PlaylistTag | null;
  state: "todo" | "watched" | "skipped";
  ku_id: string;
  /** the lecture (topic) this video belongs to */
  topic_id: string;
  topic_title: string;
  /** the level the student's KU is at now */
  level: Level;
  /** the level this video was made at for the student; null until it has been made (a video is made once, D15) */
  made_level: Level | null;
  /** the level of the file actually served (fallback toward more support) */
  served_level: Level;
  fallback_note: string | null;
  review_status: ReviewStatus;
  skip_reason: string | null;
}

export interface PlaylistView {
  overall_level: Level | null;
  cards: VideoCardView[];
  skipped: VideoCardView[];
  why: string;
  manual: boolean;
  total_seconds: number;
  watched_count: number;
  upcoming_lecture: number;
  current_entry_id: string | null;
  empty_message: string | null;
  /** the check before the upcoming lecture's videos, when one is due */
  precheck: PrecheckView | null;
}

export interface TailoringRow {
  kind: TailoringKind;
  what: string;
  why: string;
}

export interface ClaimView extends Claim {
  verdict: "matches" | "mismatch" | null;
  note: string;
  slide_urls: { slide: number; url: string; text: string }[];
  /** [start, end] seconds of this claim's segment in the video */
  span: [number, number];
}

export interface VariantView {
  video: Video;
  ku_id: string;
  level: Level;
  made_level: Level | null;
  served_level: Level;
  fallback_note: string | null;
  prototype_note: boolean;
  review_status: ReviewStatus;
  open_reports: number;
  checkpoint_item: Item;
  tailoring: TailoringRow[];
  changes_count: number;
  claims: ClaimView[];
  topic_title: string;
  lecture_title: string;
  position: { index: number; total: number } | null;
  next_video: { id: string; title: string } | null;
}

/** One KU on My levels / the start result: its published level and the level its video was made at. */
export interface KuLevelRow {
  ku: KuEntry;
  level: KuLevel;
  made_level: Level | null;
}

export interface LectureLevels {
  lecture: Lecture;
  rows: KuLevelRow[];
}

export interface StartResultView {
  overall_level: Level;
  lectures: LectureLevels[];
  review: { item: Item; choice: Choice | undefined }[];
}

export interface LevelsView {
  overall_level: Level | null;
  lectures: LectureLevels[];
  history_lines: string[];
  baseline_done: boolean;
  /** the lecture whose check updates the levels next, if one is coming */
  next_check: { lecture_n: number; title: string } | null;
  week: number;
}

/** The question a sitting is on, or nothing when it is over. */
export interface SittingView {
  id: string;
  kind: SittingState["kind"];
  lecture_n: number | null;
  /** "Lecture 3 check" */
  label: string;
  total: number;
  answered: number;
  done: boolean;
  current: {
    item: Item;
    lecture_n: number;
    lecture_title: string;
    role: "new" | "review";
  } | null;
}

/** The check before the upcoming lecture's videos, shown at the top of the playlist when it is due. */
export interface PrecheckView {
  sitting_id: string;
  lecture_n: number;
  title: string;
  total: number;
  answered: number;
}

/** The "What changed and why" card (plan D11). */
export interface LevelUpdateCard {
  id: string;
  lecture_n: number;
  lecture_title: string;
  updates: (LevelUpdate & { title: string })[];
}

export interface CalibrationView {
  block1: {
    ready: boolean;
    rated: number;
    rows: { confidence: Confidence; label: string; right: number; n: number }[];
    sentences: string[];
  };
  block2: {
    pairs: { video_id: string; title: string; jol: Jol; correct: boolean }[];
    summary: string | null;
  };
}

export interface NextSessionCardView {
  task: NextSessionTask;
  video_title: string;
  item: Item;
  remaining: number;
}

export interface CourseMapRow {
  ku: KuEntry;
  topic_title: string;
  status: "watched" | "in_playlist" | "skipped" | "not_made" | "available";
  video: VideoCardView | null;
  notes: NoteRecord[];
}

export interface CourseMapView {
  lectures: { lecture: Lecture; rows: CourseMapRow[] }[];
}
