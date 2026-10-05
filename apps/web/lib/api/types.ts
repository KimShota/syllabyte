import type {
  AppSettings, CalibrationView, Choice, Condition, Confidence, Course, CourseMapView, Difficulty, Item,
  Jol, LevelProposal, LevelsView, NextSessionCardView, OnboardingResultView, PlaylistDiff, PlaylistView,
  RecheckSlot, RecheckState, ReportCategory, TopicLevel, VariantView, ApplySnapshot, Level, DemoState,
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
  onboarding_done: boolean;
}

export interface OnboardingItemView {
  item: Item;
  topic_title: string;
  index: number;
  total: number;
  answer: Choice | undefined;
}

export interface CheckpointAnswerInput {
  videoId: string;
  choice: number;
  confidence: Confidence;
  hintUsed: boolean;
  latencyMs: number;
}

export interface RecheckStatusView {
  status: RecheckState["status"];
  week: number;
  in_window: boolean;
  invite_seen: boolean;
  slot: RecheckSlot | null;
  slot_text: string | null;
  slots: RecheckSlot[];
  videos_watched: number;
  skipped_until_week: number;
  /** a re-check card should be pinned on the playlist */
  pinned: boolean;
}

export interface ProposalRow extends LevelProposal {
  topic_title: string;
}

export interface ProposalsView {
  proposals: ProposalRow[];
  diff: PlaylistDiff;
  applied: ApplySnapshot | null;
  mode: RecheckState["mode"];
  /** Undo is offered for 24 h after applying */
  undo_available: boolean;
}

export interface Api {
  // session / first run
  getMe(): Promise<Me>;
  postConsent(research: boolean): Promise<void>;
  withdrawFromResearch(deletePast: boolean): Promise<void>;
  updateSettings(patch: Partial<AppSettings>): Promise<void>;

  // onboarding
  getOnboardingItems(): Promise<OnboardingItemView[]>;
  answerOnboarding(itemId: string, choice: Choice, latencyMs: number): Promise<void>;
  finishOnboarding(): Promise<void>;
  pickAllLevels(level: Level, fromQuestion: number): Promise<void>;
  getOnboardingResult(): Promise<OnboardingResultView>;
  keepLevels(): Promise<void>;

  // levels
  getLevels(): Promise<LevelsView>;
  correctLevel(topicId: string, level: Level, reasonChip: string | null, note: string, sourceScreen: string): Promise<{ previous: TopicLevel }>;
  restoreLevel(previous: TopicLevel): Promise<void>;
  useSuggestedLevel(topicId: string): Promise<void>;
  getCalibration(): Promise<CalibrationView>;

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
  postJol(videoId: string, jol: Jol): Promise<void>;
  postSelfExplanation(videoId: string, mode: "frame" | "free", blanks: string[], text: string): Promise<void>;
  postDifficulty(videoId: string, d: Difficulty): Promise<void>;
  listNotes(videoId: string): Promise<{ id: string; video_t: number; text: string }[]>;
  addNote(videoId: string, videoT: number, text: string): Promise<void>;
  postClaimVerdict(videoId: string, claimIdx: number, verdict: "matches" | "mismatch", note: string): Promise<void>;
  postReport(videoId: string, category: ReportCategory, videoT: number, note: string): Promise<void>;

  // week 7
  getRecheckStatus(): Promise<RecheckStatusView>;
  markInviteSeen(): Promise<void>;
  scheduleRecheck(slotId: RecheckSlot["id"]): Promise<{ slot: RecheckSlot; text: string; ics: string }>;
  skipRecheck(): Promise<void>;
  getRecheckItems(): Promise<OnboardingItemView[]>;
  answerRecheck(itemId: string, choice: Choice, latencyMs: number): Promise<void>;
  finishRecheck(): Promise<void>;
  getProposals(): Promise<ProposalsView>;
  decideProposal(topicId: string, decision: "accepted" | "kept" | "disputed", disputeText: string): Promise<void>;
  applyDecisions(mode: "apply" | "keep_old" | "pick_myself"): Promise<void>;
  undoApply(): Promise<void>;

  // data rights
  exportMyData(): Promise<Record<string, unknown>>;
  resetModel(): Promise<void>;
}
