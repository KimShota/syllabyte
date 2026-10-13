import type { CourseConfig, ProgressRecord, WatchRecord } from "@/lib/types";
import { MINUTE } from "@/lib/util";

/**
 * Engagement adjusts what is delivered, never the ability estimate (plan/per-ku-profiling-plan.md D13): ability
 * comes from answers only. The thresholds are config values and appear in the plan's traceability table.
 */

/** Someone who stopped watching a minute ago may simply be paused; only count a video as dropped after this. */
export const DROPOFF_GRACE_MS = 30 * MINUTE;

/** Left a video unfinished, before `refresher_dropoff_fraction` of it: it goes back to the top to pick up from. */
export function droppedEarly(progress: ProgressRecord | undefined, watched: boolean, cfg: CourseConfig, now: number): boolean {
  if (watched || !progress || progress.max_t <= 0 || progress.duration_s <= 0) return false;
  if (now - progress.last_at < DROPOFF_GRACE_MS) return false;
  return progress.max_t / progress.duration_s < cfg.refresher_dropoff_fraction;
}

/** Watched `refresher_replay_count` times or more: a sign it did not stick, so it is queued as a refresher. */
export function replayedMany(watch: WatchRecord | undefined, cfg: CourseConfig): boolean {
  return (watch?.views ?? 0) >= cfg.refresher_replay_count;
}
