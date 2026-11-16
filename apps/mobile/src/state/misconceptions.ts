import { useCallback, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";
import { api } from "@syllabyte/core/api/client";
import type { MisconceptionVideoView } from "@syllabyte/core/types";
import { COURSE, useCourseVersion } from "@/data/course";

/** Refresh saved explanations while their lecture or library is visible, including newly finished videos. */
export function useLectureMisconceptionVideos(courseId: string, lectureN: number) {
  useCourseVersion();
  const activeCourseId = COURSE.id;
  const key = `${courseId}:${lectureN}`;
  const [view, setView] = useState<{ key: string; videos?: MisconceptionVideoView[]; failed: boolean }>({ key, failed: false });
  const focused = useRef(false);
  const sequence = useRef(0);
  const load = useCallback(() => {
    if (activeCourseId !== courseId) return;
    const request = ++sequence.current;
    api.getLectureMisconceptionVideos(lectureN).then(
      videos => { if (focused.current && sequence.current === request) setView({ key, videos, failed: false }); },
      () => { if (focused.current && sequence.current === request) setView(previous => ({ key, videos: previous.key === key ? previous.videos : undefined, failed: true })); },
    );
  }, [key, lectureN, activeCourseId, courseId]);
  useFocusEffect(useCallback(() => {
    focused.current = true;
    load();
    const timer = setInterval(load, 10_000);
    return () => { focused.current = false; sequence.current++; clearInterval(timer); };
  }, [load]));
  const current = view.key === key && activeCourseId === courseId;
  return { videos: current ? view.videos : undefined, failed: activeCourseId !== courseId || (current && view.failed), retry: load };
}
