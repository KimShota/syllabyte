import type { Instrument } from "@/content/instruments";
import type {
  AppSettings, BatteryRecord, CalibrationView, Choice, Condition, Confidence, Course, CourseMapView, DemoState, Difficulty, Item,
  Jol, KuLevel, Level, LevelsView, LevelUpdateCard, NextSessionCardView, PlaylistView, ReportCategory, SittingView,
  StartResultView, VariantView,
} from "@/lib/types";

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
