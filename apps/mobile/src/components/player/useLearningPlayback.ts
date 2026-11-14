import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@syllabyte/core/api/client";
import type { LearningContext, PlaybackSnapshot } from "@syllabyte/core/learning";
import { touch } from "@syllabyte/core/store";
import { uid } from "@syllabyte/core/util";

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
  const acknowledged = useRef(0);
  const flush = useCallback(async (wake = false) => {
    const snapshot = measurement();
    if (!videoId || snapshot.sequence <= acknowledged.current) return;
    try {
      const { completedNow } = await api.recordLearningPlayback({ ...learning, playbackId, videoId, snapshot });
      acknowledged.current = Math.max(acknowledged.current, snapshot.sequence);
      setFailed(false);
      if (completedNow || wake) touch();
    } catch { setFailed(true); }
  }, [learning, videoId, playbackId, measurement]);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => { void flush(); }, SAVE_EVERY_MS);
    return () => { clearInterval(timer); void flush(true); };
  }, [active, flush]);
  return { failed, flush };
}
