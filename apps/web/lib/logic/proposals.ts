import type { Course, CourseConfig, Item, Level, LevelProposal, ResponseRecord, Topic, TopicLevel, Video, WatchRecord } from "@/lib/types";
import { countsFor } from "./levels";
import { weekOf } from "./time";

/**
 * Week 7 proposal rule (plan §4.4 / Q34).
 *
 * Pool per topic = the topic's re-check answers plus its Weeks 1–6 checkpoint and
 * next-session answers. "Not sure" counts as missing, never wrong; a correct answer
 * given after "Show a hint" earns half credit.
 *
 * Interpretation note: the plan says a proposal "needs ≥3 answered". Read literally,
 * the "more than half 'Not sure'" rule could then never fire (it would need 7+ items),
 * so the minimum is applied like this:
 *   - the Not-sure rule needs ≥ min items PRESENTED (answered + Not sure);
 *   - the score rules need ≥ min items ANSWERED.
 */
const POOL = ["recheck", "checkpoint", "next_session"] as const;

export interface ProposalInput {
  course: Course;
  items: Item[];
  videos: Video[];
  responses: ResponseRecord[];
  levels: Record<string, TopicLevel>;
  watched: Record<string, WatchRecord>;
  /** ms timestamp of the first day of Week 1 */
  semesterStart: number;
  /** ms "now" on the demo clock */
  now: number;
}

function clamp(l: number): Level {
  return Math.max(1, Math.min(3, l)) as Level;
}

export function proposeForTopic(input: ProposalInput, topic: Topic): LevelProposal {
  const cfg: CourseConfig = input.course.config;
  const current = input.levels[topic.id];
  const from = (current?.level ?? 1) as Level;
  const pool = input.responses.filter((r) => r.topic_id === topic.id && (POOL as readonly string[]).includes(r.context));

  let credit = 0;
  let answered = 0;
  let right = 0;
  let notSure = 0;
  for (const r of pool) {
    if (r.choice === "not_sure") {
      notSure += 1;
      continue;
    }
    answered += 1;
    if (r.correct) {
      right += 1;
      credit += r.hint_used ? 0.5 : 1;
    }
  }
  const presented = answered + notSure;
  const score = answered > 0 ? credit / answered : null;

  let to: Level = from;
  let direction: LevelProposal["direction"] = "same";
  let reason: string;

  const studentSet = current?.source === "student";
  const week1 = countsFor(topic.id, input.responses, ["onboarding"]);
  const week1Answered = week1.right + week1.wrong;

  const topicVideos = input.videos.filter((v) => v.topic_id === topic.id);
  const watchedAll = topicVideos.length > 0 && topicVideos.every((v) => input.watched[v.id]);

  const watchedClause = !watchedAll
    ? ""
    : topicVideos.length === 1
      ? ` You watched the “${topic.title}” video.`
      : ` You watched all ${topicVideos.length} “${topic.title}” videos.`;

  if (presented < cfg.recheck_min_answers) {
    direction = "not_enough";
    reason = "Not enough answers yet to say.";
  } else if (notSure / presented > 0.5) {
    if (from > 1) {
      to = clamp(from - 1);
      direction = "down";
    }
    reason =
      `${notSure} of ${presented} answers were “Not sure”. That is useful: your next videos here will go slower and include more help.`;
  } else if (answered >= cfg.recheck_min_answers && score !== null) {
    const base = `${right} of ${answered} right`;
    const baseline = week1Answered > 0 ? `, up from ${week1.right} of ${week1Answered} in Week 1` : "";
    if (score >= cfg.recheck_up_threshold && from < 3) {
      to = clamp(from + 1);
      direction = "up";
      reason = `${base}${week1Answered > 0 && week1.right / week1Answered < score ? baseline : ""}.${watchedClause}`;
    } else if (score <= cfg.recheck_down_threshold && from > 1) {
      to = clamp(from - 1);
      direction = "down";
      reason = `${base}. Your next videos here will go slower and include more help.`;
    } else {
      reason = `${base}.${watchedClause}`;
    }
  } else {
    direction = "not_enough";
    reason = "Not enough answers yet to say.";
  }

  return {
    topic_id: topic.id,
    from,
    to,
    direction,
    score,
    answered,
    correct: right,
    not_sure: notSure,
    reason,
    note: studentSet && direction !== "not_enough" ? `You set this level in Week ${weekOfChange(current, input)}.` : null,
    decision: null,
    dispute_text: "",
  };
}

function weekOfChange(tl: TopicLevel, input: ProposalInput): number {
  const last = [...tl.history].reverse().find((h) => h.source === "student");
  return weekOf(last ? last.at : input.now, input.semesterStart);
}

export function proposeLevels(input: ProposalInput): LevelProposal[] {
  return input.course.topics.map((t) => proposeForTopic(input, t));
}

export function changedProposals(ps: LevelProposal[]): LevelProposal[] {
  return ps.filter((p) => p.direction === "up" || p.direction === "down");
}
