import type {
  Course,
  Item,
  KuEntry,
  Level,
  PlaylistEntry,
  PlaylistState,
  PlaylistTag,
  ProgressRecord,
  ResponseRecord,
  ReviewStatus,
  Video,
  WatchRecord,
} from "../types";
import { joinAnd } from "../util";
import { droppedEarly, replayedMany } from "./engagement";
import { lecturesInOrder } from "./lectures";
import { orderByPrerequisites, prerequisiteNotes } from "./prereq";

/** The lecture whose videos are "new". Phase 0 pins it (the fixture has 3 lectures). */
export function upcomingLecture(course: Course, week: number): number {
  const override = course.config.upcoming_lecture_override;
  if (override) return override;
  const ordered = lecturesInOrder(course);
  const next = ordered.find((l) => l.week >= week);
  // 0: an uploaded course with no slides yet has no lectures
  return next ? next.n : (ordered[ordered.length - 1]?.n ?? 0);
}

export interface BuildInput {
  course: Course;
  videos: Video[];
  items: Item[];
  /** the published level of every KU */
  levels: Record<string, { level: Level }>;
  responses: ResponseRecord[];
  watched: Record<string, WatchRecord>;
  progress: Record<string, ProgressRecord>;
  review: Record<string, ReviewStatus>;
  prev: PlaylistEntry[];
  /** videos skipped as "I already know this" with the prove-it passed */
  known: string[];
  added: string[];
  week: number;
  now: number;
  /** the lecture treated as upcoming, when not taken from the schedule (the demo's "next lecture") */
  upcoming?: number;
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
 * Plan §4.3, with per-KU levels (plan/per-ku-profiling-plan.md D13, D14). Tags:
 *   gap        unwatched, and the video's KU is at Level 1
 *   new        unwatched, from the upcoming lecture (or one the student started and left, to pick up again)
 *   refresher  watched, and the KU is at Level 1, or the student missed it, or watched it several times (it did
 *              not stick): only added once every gap/new video is watched or skipped (first pass first)
 *   you_added  put there from the Course map
 * Order inside a group: prerequisites first (the KU graph), then the upcoming lecture's gaps, then earlier slides.
 * A video the student stopped watching early goes to the very top. Cap: 6 videos or 600 s, whichever comes first.
 */
export function buildEntries(input: BuildInput): PlaylistEntry[] {
  const { course, videos, levels, responses, watched, review, prev, progress } = input;
  const upcoming = input.upcoming ?? upcomingLecture(course, input.week);
  const eligibleLectures = new Set([upcoming, upcoming - 1, upcoming - 2].filter((n) => n >= 1));
  const prevSkipped = new Map(prev.filter((e) => e.state === "skipped").map((e) => [e.video_id, e]));
  const levelOf = (v: Video) => levels[v.ku_id]?.level ?? 1;
  const dropped = (v: Video) => droppedEarly(progress[v.id], Boolean(watched[v.id]), course.config, input.now);

  const candidates = videos.filter(
    (v) => eligibleLectures.has(v.lecture_n) && review[v.id] !== "hidden" && !input.known.includes(v.id) && !prevSkipped.has(v.id),
  );

  const byTag: Record<Exclude<PlaylistTag, "you_added">, Video[]> = { gap: [], new: [], refresher: [] };
  for (const v of candidates) {
    const isWatched = Boolean(watched[v.id]);
    const weak = levelOf(v) === 1 || missedVideo(v, responses) || replayedMany(watched[v.id], course.config);
    if (!isWatched && levelOf(v) === 1) byTag.gap.push(v);
    else if (!isWatched && (v.lecture_n === upcoming || dropped(v))) byTag.new.push(v);
    else if (isWatched && weak) byTag.refresher.push(v);
  }

  const bySlide = (a: Video, b: Video) => firstSlide(a) - firstSlide(b);
  const gapOrder = (a: Video, b: Video) => Number(b.lecture_n === upcoming) - Number(a.lecture_n === upcoming) || bySlide(a, b);
  const prereqFirst = (list: Video[], cmp: (a: Video, b: Video) => number) => orderByPrerequisites(list, (v) => v.ku_id, course.kus, cmp);

  // First pass first: refreshers wait until every gap/new video is watched or skipped.
  const firstPassDone = [...byTag.gap, ...byTag.new].every((v) => watched[v.id]);
  const grouped: { video: Video; tag: PlaylistTag }[] = [
    ...prereqFirst(byTag.gap, gapOrder).map((video) => ({ video, tag: "gap" as const })),
    ...prereqFirst(byTag.new, bySlide).map((video) => ({ video, tag: "new" as const })),
    ...(firstPassDone ? prereqFirst(byTag.refresher, bySlide).map((video) => ({ video, tag: "refresher" as const })) : []),
  ];
  // Left a video early: it goes back to the top, ahead of the cap, to pick up where it stopped.
  const ordered = [...grouped.filter((o) => dropped(o.video)), ...grouped.filter((o) => !dropped(o.video))];

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
  kus: KuEntry[];
  /** videos the student stopped partway: they are back at the top */
  resumeIds?: string[];
}): string {
  if (args.manual) return "You set this order. Use “Reset to suggested order” to go back to ours.";
  const byVideo = (e: PlaylistEntry) => args.videos.find((v) => v.id === e.video_id)!;
  const gaps = args.entries.filter((e) => e.tag === "gap");
  const hasNew = args.entries.some((e) => e.tag === "new");
  const hasRefresher = args.entries.some((e) => e.tag === "refresher");
  if (args.entries.length === 0) return `Lecture ${args.upcoming} is next.`;
  const gapNames = [...new Set(gaps.map((e) => byVideo(e).short_title))];
  const shown = gapNames.length > 3 ? `${gapNames.slice(0, 3).join(", ")} and ${gapNames.length - 3} more` : joinAnd(gapNames);
  let text = `Lecture ${args.upcoming} is next`;
  if (gapNames.length) text += `, and your levels show ${shown} ${gapNames.length === 1 ? "as a gap" : "as gaps"}`;
  text += ".";
  if (gaps.length && hasNew) text += ` We put those first, then new videos from Lecture ${args.upcoming}`;
  else if (gaps.length) text += " We put those first";
  else if (hasNew) text += ` Here are its new videos`;
  if (hasRefresher) text += gaps.length || hasNew ? ", then a short refresher" : " Here is a short refresher";
  if (gaps.length || hasNew || hasRefresher) text += ".";
  const resumed = (args.resumeIds ?? []).map((id) => args.videos.find((v) => v.id === id)?.short_title).filter(Boolean) as string[];
  if (resumed.length) text += ` You stopped ${joinAnd(resumed.map((t) => `“${t}”`))} partway, so ${resumed.length === 1 ? "it is" : "they are"} back at the top.`;
  const ku = (id: string) => args.kus.find((k) => k.id === id)?.short_title ?? id;
  const notes = prerequisiteNotes(args.entries.filter((e) => e.state !== "skipped").map(byVideo), (v) => v.ku_id, args.kus, ku, 1);
  if (notes.length) text += ` ${notes[0]}`;
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
