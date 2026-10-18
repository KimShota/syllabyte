import { api } from "@syllabyte/core/api/client";
import type { PrecheckView } from "@syllabyte/core/types";
import { NO_PROGRESS, type Progress } from "@/data/selectors";
import { useQuery } from "./app";

/** The KUs watched and the playlist's up-next, through the API. */
export async function fetchProgress(): Promise<Progress> {
  const [map, playlist] = await Promise.all([api.getCourseMap(), api.getPlaylist()]);
  const rows = map.lectures.flatMap((l) => l.rows);
  const current = playlist.cards.find((c) => c.entry_id === playlist.current_entry_id);
  return {
    watched: rows.filter((r) => r.status === "watched").map((r) => r.ku.id),
    upNext: current?.ku_id ?? null,
  };
}

/** What the roadmaps need from the API: the KUs watched and the playlist's up-next. Empty until it loads. */
export function useProgress(): Progress {
  return useQuery(fetchProgress) ?? NO_PROGRESS;
}

/**
 * The check due before the upcoming lecture's videos, if any. `undefined` while it loads, so a screen that gates
 * on it can wait instead of flashing what it is about to hide.
 */
export function usePrecheck(): PrecheckView | null | undefined {
  return useQuery(async () => (await api.getPlaylist()).precheck);
}
