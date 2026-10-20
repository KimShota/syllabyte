import type { Instrument } from "../content/instruments";
import type {
  AppSettings, BatteryRecord, CalibrationView, Choice, Condition, Confidence, Course, CourseMapView, DemoState, Difficulty, Item,
  Jol, KuLevel, Level, LevelsView, LevelUpdateCard, NextSessionCardView, PlaylistView, ReportCategory, SittingView,
  StartResultView, VariantView,
} from "../types";

/**
 * The API contract (plan §6.1). Phase 0 implements it in the browser (mock.ts);
 * Phase 1 implements the same methods over FastAPI. Components only ever call this.
 */
export interface Me {
  course: Course;
  participant_code: string | null;
  consent: DemoState["consent"];
  condition: Condition;
  week: number;
  now: number;
  settings: AppSettings;
  /** the Week 0 baseline is done, or the student set their own levels */
  onboarding_done: boolean;
  /** the baseline has questions to ask: false while an uploaded course has no processed slides yet (U9) */
  baseline_available: boolean;
}

/** A questionnaire battery that is due (plan/study-instruments-plan.md I9). */
export interface StudyTaskView {
  battery_id: string;
  title: string;
  minutes: number;
  started: boolean;
}

export interface BatteryView {
  id: string;
  kind: BatteryRecord["kind"];
  title: string;
  /** what this participant is asked, in order (trust only for Condition A) */
  instruments: Instrument[];
  answers: BatteryRecord["answers"];
  submitted: boolean;
}

export interface CheckpointAnswerInput {
  videoId: string;
  choice: number;
  confidence: Confidence;
  hintUsed: boolean;
  latencyMs: number;
}

export interface Api {
  // session / first run
  getMe(): Promise<Me>;
  postConsent(research: boolean): Promise<void>;
  withdrawFromResearch(deletePast: boolean): Promise<void>;
  updateSettings(patch: Partial<AppSettings>): Promise<void>;

  // adaptive sittings: the Week 0 baseline ("week0") and the check before a lecture ("lecture-<n>"), plan D8
  getSitting(id: string): Promise<SittingView>;
  /** Locks the answer: there is no going back inside a sitting (D9). Must be for the question the sitting is on. */
  answerSitting(id: string, itemId: string, choice: Choice, latencyMs: number): Promise<void>;
  /** Ends the sitting and publishes the levels (D11). */
  finishSitting(id: string): Promise<void>;
  skipSitting(id: string): Promise<void>;
  pickAllLevels(level: Level, fromQuestion: number): Promise<void>;
  getStartResult(): Promise<StartResultView>;
  keepLevels(): Promise<void>;

  // levels
  getLevels(): Promise<LevelsView>;
  correctLevel(kuId: string, level: Level, reasonChip: string | null, note: string, sourceScreen: string): Promise<{ previous: KuLevel }>;
  restoreLevel(previous: KuLevel): Promise<void>;
  useSuggestedLevel(kuId: string): Promise<void>;
  getCalibration(): Promise<CalibrationView>;
  /** The "What changed and why" card for the newest unseen lecture boundary, if any. */
  getLevelUpdates(): Promise<LevelUpdateCard | null>;
  dismissLevelUpdates(id: string): Promise<void>;

  // playlist
  getPlaylist(): Promise<PlaylistView>;
  reorder(entryIds: string[]): Promise<void>;
  resetOrder(): Promise<void>;
  skip(entryId: string): Promise<void>;
  undoSkip(entryId: string): Promise<void>;
  setSkipReason(entryId: string, reason: string): Promise<void>;
  getProveIt(videoId: string): Promise<Item>;
  answerProveIt(entryId: string, choice: Choice): Promise<{ pass: boolean }>;
  keepSkipped(entryId: string): Promise<void>;
  getNextSession(): Promise<NextSessionCardView | null>;
  answerNextSession(taskId: string, choice: number): Promise<{ correct: boolean; item: Item; jol: Jol | null }>;
  dismissNextSession(taskId: string): Promise<void>;

  // course
  getCourseMap(): Promise<CourseMapView>;
  addToPlaylist(videoId: string): Promise<void>;

  // player
  getVariant(videoId: string): Promise<VariantView>;
  postCheckpointAnswer(a: CheckpointAnswerInput): Promise<{ correct: boolean; queuedForTomorrow: boolean }>;
  skipCheckpoint(videoId: string): Promise<void>;
  markWatched(videoId: string): Promise<void>;
  /** How far into the video the student has got; drives "pick up where you left off" (D13). */
  recordProgress(videoId: string, t: number, durationS: number): Promise<void>;
  postJol(videoId: string, jol: Jol): Promise<void>;
  postSelfExplanation(videoId: string, mode: "frame" | "free", blanks: string[], text: string): Promise<void>;
  postDifficulty(videoId: string, d: Difficulty): Promise<void>;
  listNotes(videoId: string): Promise<{ id: string; video_t: number; text: string }[]>;
  addNote(videoId: string, videoT: number, text: string): Promise<void>;
  updateNote(noteId: string, text: string): Promise<void>;
  deleteNote(noteId: string): Promise<void>;
  postClaimVerdict(videoId: string, claimIdx: number, verdict: "matches" | "mismatch", note: string): Promise<void>;
  postReport(videoId: string, category: ReportCategory, videoT: number, note: string): Promise<void>;

  // study questionnaires (plan/study-instruments-plan.md): research participants only
  /** batteries due and not yet submitted, minus any put off with "Not now" this visit */
  getStudyTasks(): Promise<StudyTaskView[]>;
  getBattery(id: string): Promise<BatteryView>;
  /** merges answers (null = skipped on purpose) */
  saveBatteryAnswers(id: string, answers: BatteryRecord["answers"]): Promise<void>;
  /** items never answered are recorded as skipped */
  submitBattery(id: string): Promise<void>;
  snoozeBattery(id: string): Promise<void>;
  /** the researcher export (I12) */
  exportStudyCsv(): Promise<string>;

  // data rights
  exportMyData(): Promise<Record<string, unknown>>;
  resetModel(): Promise<void>;
}

// ---------------------------------------------------------------- uploads (plan/slide-uploads-plan.md)

/** A lecture of an uploaded course and how far its slides are (U14). */
/** A lecture of an uploaded course and its slides (plan/slide-uploads-plan.md V1-V3): one per confirmed deck. */
export interface LectureStateView {
  n: number;
  /** sorts the lectures in teaching order, and an upload's `suggested_position` among them (not a lecture number) */
  position: number;
  title: string;
  state: "analyzing" | "ready" | "failed";
  decks: { id: string; file_name: string; status: "unplaced" | "queued" | "processing" | "ready" | "failed" }[];
}

/** GET /api/courses/mine: no course yet, the syllabus being read (or failed), or the course. */
export type MyCourseView =
  | { status: "none" }
  | { status: "reading" }
  | { status: "failed"; error: string | null }
  | {
      status: "ready";
      course: {
        id: string;
        code: string;
        name: string;
        /** in teaching order */
        lectures: LectureStateView[];
      };
    };

/** One row of the review screen (V1). */
export interface UploadView {
  id: string;
  file_name: string;
  status: "reading" | "read" | "confirmed" | "failed";
  outcome: "new" | "existing" | "updated_version" | "over_cap" | "unreadable" | null;
  error: string | null;
  deck: { id: string; page_count: number; status: LectureStateView["decks"][number]["status"] } | null;
  /** what the slides teach, as the reader said (or the lecture's title once placed) */
  title: string | null;
  summary: string | null;
  /** the lecture these slides already are (someone placed them, or this is an updated version of them) */
  placed_lecture_n: number | null;
  /** the reader or the placement call is still working, so there is no suggestion yet */
  placing: boolean;
  /** where the placement call put it among the lectures (compare with their positions); null until it has */
  suggested_position: number | null;
  /** false: a guess the student should check */
  suggestion_sure: boolean;
  /** the deck is not placed yet, so this student places and names it */
  can_place: boolean;
}

/**
 * The review screen's "Confirm all" (V1): the course's lectures and this student's new decks in teaching order. The
 * lectures must stay in their order (only new decks move); a new deck may be renamed.
 */
export type UploadOrderEntry = { lecture_n: number } | { upload_id: string; title?: string };

/** A file picked on the phone (expo-document-picker's asset) or in a browser (with its `file`). */
export interface UploadFile {
  name: string;
  uri: string;
  mimeType?: string | null;
  file?: Blob | null;
}

