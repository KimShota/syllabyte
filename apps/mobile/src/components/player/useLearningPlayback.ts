import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@syllabyte/core/api/client";
import type { LearningContext, PlaybackSnapshot } from "@syllabyte/core/learning";
import { touch } from "@syllabyte/core/store";
import { uid } from "@syllabyte/core/util";
import { sendLearning } from "@/state/learningOutbox";
import { trackSave } from "./learningSync";

/** How often a playing page saves what it observed. */
const SAVE_EVERY_MS = 5000;

/**
 * Saves one page's playback observations. Snapshots are cumulative, so a duplicate or out-of-order request is harmless
 * and the latest one is retried while the page is mounted. The saves are quiet (no screen refetches while a video
 * plays); screens are woken when a save completes the video or when the page stops being the one playing, so the
 * reflection and the playlist see what was watched.
 */
export function useLearningPlayback(learning: LearningContext, videoId: string | null, measurement: () => PlaybackSnapshot, active: boolean) {
  const [playbackId] = useState(() => uid("playback"));
  const [failed, setFailed] = useState(false);
  const acknowledged = useRef(-1);
  const flush = useCallback(async (wake = false) => {
    const snapshot = measurement();
    // the first save goes even with nothing played: a video swiped straight past is a visit too (moving on early)
    if (!videoId || snapshot.sequence <= acknowledged.current) return;
    const input = { ...learning, playbackId, videoId, snapshot };
    // the last save of a page (it stopped playing or went away) must not be lost: it goes through the outbox, which keeps
    // it until the network is back; the regular saves while it plays are simply sent again 5 s later
    if (wake) {
      await trackSave(sendLearning("recordLearningPlayback", input));
      acknowledged.current = Math.max(acknowledged.current, snapshot.sequence);
      setFailed(false);
      touch(); // the page stopped playing: screens see what was watched
      return;
    }
    try {
      const { completedNow } = await trackSave(api.recordLearningPlayback(input));
      acknowledged.current = Math.max(acknowledged.current, snapshot.sequence);
      setFailed(false);
      if (completedNow) touch();
    } catch { setFailed(true); }
  }, [learning, videoId, playbackId, measurement]);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => { void flush(); }, SAVE_EVERY_MS);
    return () => { clearInterval(timer); void flush(true); };
  }, [active, flush]);
  return { failed, flush };
}
