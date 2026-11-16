import type { MisconceptionClip, MisconceptionRequest } from "@syllabyte/core/types";
import { backendMediaUrl } from "@/data/media";
import type { Ku } from "@/data/types";

export interface ReadyClip {
  request: MisconceptionRequest;
  clip: MisconceptionClip;
  item_title: string;
}

export type FeedItem = { kind: "video"; ku: Ku } | { kind: "misconception"; ku: Ku; ready: ReadyClip } | { kind: "end" };
export interface ClipInsertion { after: string; ready: ReadyClip }

export function feedKey(item: FeedItem): string {
  return item.kind === "end" ? "end" : item.kind === "misconception" ? `misconception:${item.ready.request.id}` : `video:${item.ku.id}`;
}

/** Keep the course order and any ending page, inserting accepted clips directly after the page they interrupted. */
export function buildFeedItems(kus: readonly Ku[], hasEnd: boolean, insertions: readonly ClipInsertion[]): FeedItem[] {
  const items: FeedItem[] = kus.map(ku => ({ kind: "video", ku }));
  if (hasEnd) items.push({ kind: "end" });
  for (const { after, ready } of insertions) {
    if (items.some(item => item.kind === "misconception" && item.ready.request.id === ready.request.id)) continue;
    const video = ready.clip.video;
    const anchor = items.findIndex(item => feedKey(item) === after);
    const end = items.findIndex(item => item.kind === "end");
    const index = anchor >= 0 && items[anchor].kind !== "end" ? anchor + 1 : end >= 0 ? end : items.length;
    items.splice(index, 0, {
      kind: "misconception", ready,
      ku: {
        id: `misconception:${ready.request.id}`, title: video.title, shortTitle: video.short_title,
        lectureN: video.lecture_n, slides: [video.source_slides[0] ?? 1, video.source_slides.at(-1) ?? 1],
        durationS: video.duration_s, videoId: null,
        videoUri: backendMediaUrl(video.video_url) ?? video.video_url,
        captionsBurnedIn: video.captions_burned_in, transcript: [],
        scene: { kind: "statement", framework: "Video for your mistake", headline: video.short_title, points: [] },
      },
    });
  }
  return items;
}
