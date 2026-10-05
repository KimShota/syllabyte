import type { CourseConfig, NextSessionTask, Video } from "@/lib/types";
import { DAY, HOUR, uid } from "@/lib/util";

/** Plan Q13: first visit ≥ 12 h after watching; oldest first; max 2 per visit; expires after 7 days. */
export function createTask(video: Video, now: number, cfg: CourseConfig, flaggedGuess = false): NextSessionTask {
  return {
    id: uid("ns"),
    video_id: video.id,
    item_id: video.next_session_item_id,
    jol: null,
    due_after: now + cfg.next_session_min_hours * HOUR,
    expires_at: now + cfg.next_session_expiry_days * DAY,
    done: false,
    flagged_guess: flaggedGuess,
    result: null,
  };
}

export function isEligible(task: NextSessionTask, now: number): boolean {
  return !task.done && now >= task.due_after && now < task.expires_at;
}

export function currentNextSession(
  tasks: NextSessionTask[],
  now: number,
  cfg: CourseConfig,
  visit: { handled: number },
): { task: NextSessionTask; remaining: number } | null {
  const left = cfg.next_session_max_per_visit - visit.handled;
  if (left <= 0) return null;
  const eligible = tasks.filter((t) => isEligible(t, now)).sort((a, b) => a.due_after - b.due_after);
  if (eligible.length === 0) return null;
  return { task: eligible[0], remaining: Math.min(left, eligible.length) - 1 };
}
