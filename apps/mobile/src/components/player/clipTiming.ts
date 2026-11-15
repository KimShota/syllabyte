/**
 * When the feed shows a ready misconception clip (plan/engagement-feedback-implementation-plan.md, "Misconception
 * clips"): never over a video in progress or another card.
 *  1. At the move to another video (a natural pause, before the new one gets going): a waiting clip, including one put
 *     off with "Later", which is offered again at most `reoffers` times; after that, and once watched, it stays put off.
 *  2. Otherwise as soon as it is ready if no video is in progress, else when the video ends.
 */
export function clipDecision<C extends { request: { id: string } }>(i: {
  clips: C[];
  /** clips put off ("Later") or watched in this feed visit */
  deferred: ReadonlySet<string>;
  /** how often each was put off (Infinity once watched) */
  laterCount: Readonly<Record<string, number>>;
  /** the feed just moved to another video */
  moved: boolean;
  /** no other card is open and the feed is on screen */
  canShow: boolean;
  /** a video is in progress (playing, or its quick check open) */
  busy: boolean;
  reoffers: number;
}): { show: C | null; deferred: ReadonlySet<string> } {
  let deferred = i.deferred;
  if (i.moved) {
    const still = new Set([...i.deferred].filter((id) => (i.laterCount[id] ?? 0) > i.reoffers));
    if (still.size !== i.deferred.size) deferred = still;
  }
  if (!i.canShow || (!i.moved && i.busy)) return { show: null, deferred };
  return { show: i.clips.find((c) => !deferred.has(c.request.id)) ?? null, deferred };
}
