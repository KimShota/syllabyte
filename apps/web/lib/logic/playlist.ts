import type {
  Course,
  Item,
  Level,
  PlaylistEntry,
  PlaylistState,
  PlaylistTag,
  ResponseRecord,
  ReviewStatus,
  TopicLevel,
  Video,
  WatchRecord,
} from "@/lib/types";
import { joinAnd } from "@/lib/util";

/** The lecture whose videos are "new". Phase 0 pins it (the fixture has 3 lectures). */
export function upcomingLecture(course: Course, week: number): number {
  const override = course.config.upcoming_lecture_override;
  if (override) return override;
  const next = course.lectures.find((l) => l.week >= week);
  return next ? next.n : course.lectures[course.lectures.length - 1].n;
}

export interface BuildInput {
  course: Course;
  videos: Video[];
  items: Item[];
  levels: Record<string, TopicLevel>;
  responses: ResponseRecord[];
  watched: Record<string, WatchRecord>;
  review: Record<string, ReviewStatus>;
  prev: PlaylistEntry[];
  /** videos skipped as "I already know this" with the prove-it passed */
  known: string[];
  added: string[];
  week: number;
}

function firstSlide(v: Video): number {
  return v.source_slides.length ? Math.min(...v.source_slides) : 0;
}

/** The student missed this video's checkpoint or next-session question (latest answer wins). */
export function missedVideo(video: Video, responses: ResponseRecord[]): boolean {
  const ids = [video.checkpoint.item_id, video.next_session_item_id];
  const latest: Record<string, ResponseRecord> = {};
  for (const r of responses) {
    if (!ids.includes(r.item_id)) continue;
    if (!latest[r.item_id] || r.at >= latest[r.item_id].at) latest[r.item_id] = r;
  }
  return Object.values(latest).some((r) => r.choice !== "not_sure" && r.correct === false);
}

/**
 * Plan §4.3. Tags:
 *   gap        unwatched, and the topic is at Level 1
 *   new        unwatched, from the upcoming lecture
 *   refresher  watched, and the topic is a gap or the student missed it — but only
 *              once every gap/new video has been watched or skipped (first pass first)
 *   you_added  put there from the Course map
 * Order: gaps (upcoming lecture first, then earlier slides = prerequisites first) →
 * new → refreshers → you_added. Cap: 6 videos or 600 s, whichever comes first.
 */
export function buildEntries(input: BuildInput): PlaylistEntry[] {
  const { course, videos, levels, responses, watched, review, prev } = input;
  const upcoming = upcomingLecture(course, input.week);
  const eligibleLectures = new Set([upcoming, upcoming - 1, upcoming - 2].filter((n) => n >= 1));
  const prevSkipped = new Map(prev.filter((e) => e.state === "skipped").map((e) => [e.video_id, e]));
  const levelOf = (topicId: string) => levels[topicId]?.level ?? 1;

  const candidates = videos.filter(
    (v) => eligibleLectures.has(v.lecture_n) && review[v.id] !== "hidden" && !input.known.includes(v.id) && !prevSkipped.has(v.id),
  );

  const byTag: Record<Exclude<PlaylistTag, "you_added">, Video[]> = { gap: [], new: [], refresher: [] };
  for (const v of candidates) {
    const isWatched = Boolean(watched[v.id]);
    const weak = levelOf(v.topic_id) === 1 || missedVideo(v, responses);
    if (!isWatched && levelOf(v.topic_id) === 1) byTag.gap.push(v);
    else if (!isWatched && v.lecture_n === upcoming) byTag.new.push(v);
    else if (isWatched && weak) byTag.refresher.push(v);
  }

  const bySlide = (a: Video, b: Video) => firstSlide(a) - firstSlide(b);
  byTag.gap.sort((a, b) => Number(b.lecture_n === upcoming) - Number(a.lecture_n === upcoming) || bySlide(a, b));
  byTag.new.sort(bySlide);
  byTag.refresher.sort(bySlide);

  // First pass first: refreshers wait until every gap/new video is watched or skipped.
  const firstPassDone = [...byTag.gap, ...byTag.new].every((v) => watched[v.id]);
  const ordered: { video: Video; tag: PlaylistTag }[] = [
    ...byTag.gap.map((video) => ({ video, tag: "gap" as const })),
    ...byTag.new.map((video) => ({ video, tag: "new" as const })),
    ...(firstPassDone ? byTag.refresher.map((video) => ({ video, tag: "refresher" as const })) : []),
  ];

  // Cap: 6 videos or max_seconds, whichever first (always keep at least one).
  const capped: typeof ordered = [];
  let seconds = 0;
  for (const o of ordered) {
    if (capped.length >= course.config.playlist_max_videos) break;
    if (capped.length > 0 && seconds + o.video.duration_s > course.config.playlist_max_seconds) break;
    capped.push(o);
    seconds += o.video.duration_s;
  }

  // "You added" videos are appended beyond the cap.
  for (const id of input.added) {
    const video = videos.find((v) => v.id === id);
    if (!video || review[id] === "hidden" || prevSkipped.has(id) || capped.some((c) => c.video.id === id)) continue;
    capped.push({ video, tag: "you_added" });
  }

  const entries: PlaylistEntry[] = capped.map((o, i) => ({
    id: `pl-${o.video.id}`,
    video_id: o.video.id,
    tag: o.tag,
    state: watched[o.video.id] ? "watched" : "todo",
    skip_reason: null,
    pos: i,
  }));
  // Skipped entries stay (still playable) in their own group.
  for (const e of prevSkipped.values()) entries.push({ ...e, pos: entries.length });
  return entries;
}

export function buildPlaylistState(input: BuildInput): PlaylistState {
  return { entries: buildEntries(input), manual_order: null, built_at_week: input.week };
}

/** Entries in display order: a manual order wins until it is reset or rebuilt. */
export function displayOrder(state: PlaylistState): { active: PlaylistEntry[]; skipped: PlaylistEntry[] } {
  const skipped = state.entries.filter((e) => e.state === "skipped");
  const active = state.entries.filter((e) => e.state !== "skipped").sort((a, b) => a.pos - b.pos);
  if (state.manual_order) {
    const rank = new Map(state.manual_order.map((id, i) => [id, i]));
    active.sort((a, b) => (rank.get(a.id) ?? 1e6 + a.pos) - (rank.get(b.id) ?? 1e6 + b.pos));
  }
  return { active, skipped };
}

export function currentEntry(state: PlaylistState): PlaylistEntry | null {
  return displayOrder(state).active.find((e) => e.state === "todo") ?? null;
}

/** "Why this order" text, templated from the facts (plan §4.3). */
export function whyOrder(args: {
  upcoming: number;
  manual: boolean;
  entries: PlaylistEntry[];
  videos: Video[];
  topicTitle: (id: string) => string;
}): string {
  if (args.manual) return "You set this order. Use “Reset to suggested order” to go back to ours.";
  const byVideo = (e: PlaylistEntry) => args.videos.find((v) => v.id === e.video_id)!;
  const gaps = args.entries.filter((e) => e.tag === "gap");
  const hasNew = args.entries.some((e) => e.tag === "new");
  const hasRefresher = args.entries.some((e) => e.tag === "refresher");
  if (args.entries.length === 0) return `Lecture ${args.upcoming} is next.`;
  const gapTopics = [...new Set(gaps.map((e) => args.topicTitle(byVideo(e).topic_id)))];
  let text = `Lecture ${args.upcoming} is next`;
  if (gapTopics.length) text += `, and your levels show ${joinAnd(gapTopics)} ${gapTopics.length === 1 ? "as a gap" : "as gaps"}`;
  text += ".";
  if (gaps.length && hasNew) text += ` We put those first, then new videos from Lecture ${args.upcoming}`;
  else if (gaps.length) text += " We put those first";
  else if (hasNew) text += ` Here are its new videos`;
  if (hasRefresher) text += gaps.length || hasNew ? ", then a short refresher" : " Here is a short refresher";
  if (gaps.length || hasNew || hasRefresher) text += ".";
  return text;
}

/** Fall back toward more support when a level's file doesn't exist (plan Q31). */
export function servedLevel(wanted: Level, available: Level[]): { level: Level; note: string | null } {
  if (available.includes(wanted)) return { level: wanted, note: null };
  const order: Record<Level, Level[]> = { 3: [2, 1], 2: [1, 3], 1: [2, 3] };
  const pick = order[wanted].find((l) => available.includes(l));
  if (!pick) return { level: wanted, note: null };
  return { level: pick, note: `Level ${pick} version · Level ${wanted} coming soon` };
}
