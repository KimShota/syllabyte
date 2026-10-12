/**
 * Shared types. The "fixture" half mirrors packages/common/syllabyte_common/learner.py
 * (keep both in sync); the rest are app-state and view models. From Phase 1 the API
 * types are generated from FastAPI's OpenAPI schema and must match these shapes.
 */

export type Level = 1 | 2 | 3;
export type Confidence = "guess" | "pretty" | "certain";
export type Choice = number | "not_sure";
export type ItemContext = "onboarding" | "checkpoint" | "recheck" | "next_session" | "prove_it" | "retention";
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

export interface Topic {
  id: string;
  title: string;
  blurb: string;
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
  recheck_week: number;
  recheck_skip_until_week: number;
  recheck_up_threshold: number;
  recheck_down_threshold: number;
  recheck_min_answers: number;
  playlist_max_videos: number;
  playlist_max_seconds: number;
  next_session_min_hours: number;
  next_session_max_per_visit: number;
  next_session_expiry_days: number;
  retention_due_days: number;
  retention_delay_days: number;
  reveal_retention_scores_after_week_14: boolean;
  upcoming_lecture_override: number | null;
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
  evidence_topic_id: string | null;
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

export type LevelCause = "onboarding" | "student" | "week7" | "reset" | "use_suggested" | "pick_all";

export interface LevelChange {
  level: Level;
  source: "model" | "student";
  at: number;
  cause: LevelCause;
}

export interface TopicLevel {
  topic_id: string;
  level: Level;
  source: "model" | "student";
  /** what the model proposed; used by "Use suggested level" */
  suggested_level: Level;
  reason: string;
  /** no onboarding evidence yet (dashed card on My levels) */
  not_checked: boolean;
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

export type ProposalDirection = "up" | "down" | "same" | "not_enough";
export type ProposalDecision = "accepted" | "kept" | "disputed" | "ignored";

export interface LevelProposal {
  topic_id: string;
  from: Level;
  to: Level;
  direction: ProposalDirection;
  score: number | null;
  answered: number;
  correct: number;
  not_sure: number;
  reason: string;
  /** "You set this level in Week 3" */
  note: string | null;
  decision: ProposalDecision | null;
  dispute_text: string;
}

export interface RecheckSlot {
  id: "now" | "tonight" | "tomorrow" | "friday" | "monday";
  label: string;
  at: number;
}

export interface ApplySnapshot {
  at: number;
  levels: Record<string, TopicLevel>;
  playlist: PlaylistState;
  summary: { accepted: number; kept: number; new: number; swapped: number; removed: number };
}

export interface RecheckState {
  status: "idle" | "scheduled" | "in_progress" | "done" | "skipped";
  slot: RecheckSlot | null;
  invite_seen_at: number | null;
  answers: Record<string, Choice>;
  proposals: LevelProposal[];
  applied: ApplySnapshot | null;
  mode: "apply" | "keep_old" | "pick_myself" | null;
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
  | "consent_given" | "onboarding_answered" | "level_suggested" | "level_kept" | "level_corrected"
  | "playlist_viewed" | "reordered" | "skipped" | "skip_reason" | "undo" | "prove_it_result"
  | "video_play" | "video_pause" | "video_seek" | "video_ended" | "speed_changed" | "captions_toggled"
  | "transcript_opened" | "note_saved" | "checkpoint_shown" | "checkpoint_answered" | "checkpoint_skipped"
  | "hint_used" | "rewatch_part" | "receipt_opened" | "full_version_requested" | "about_opened"
  | "claim_slide_viewed" | "claim_verdict" | "error_reported" | "difficulty_rated" | "jol_answered"
  | "self_explanation_saved" | "next_session_answered" | "course_video_added" | "recheck_scheduled"
  | "recheck_answered" | "proposal_decided" | "playlist_applied" | "data_downloaded" | "model_reset";

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
  v: 1;
  clock_offset_ms: number;
  semester_start: number;
  participant_code: string | null;
  consent: null | "research" | "no_research";
  condition: Condition;
  onboarding: { answers: Record<string, Choice>; done: boolean; picked_own: boolean };
  levels: Record<string, TopicLevel>;
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
  archived_models: { at: number; levels: Record<string, TopicLevel> }[];
  settings: AppSettings;
  recheck: RecheckState;
  events: AppEvent[];
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
  topic_id: string;
  topic_title: string;
  /** the level the student's topic is at */
  level: Level;
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
  level: Level;
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

export interface OnboardingResultView {
  overall_level: Level;
  topics: { topic: Topic; level: TopicLevel }[];
  review: { item: Item; choice: Choice | undefined }[];
}

export interface LevelsView {
  overall_level: Level | null;
  topics: { topic: Topic; level: TopicLevel }[];
  history_lines: string[];
  recheck_due: boolean;
  recheck_status: RecheckState["status"];
  /** the student applied Week 7 level changes (not just took the re-check) */
  week7_applied: boolean;
  week: number;
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

export interface DiffRow {
  video_id: string;
  title: string;
  topic_title: string;
  reason: string;
}

export interface PlaylistDiff {
  new: DiffRow[];
  swapped: DiffRow[];
  removed: DiffRow[];
}
