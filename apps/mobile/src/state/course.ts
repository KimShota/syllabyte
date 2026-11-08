/**
 * The student's uploaded course, with a backend (plan/slide-uploads-plan.md): whether they have one yet, its syllabus
 * being read, and each lecture's slides. Once the course is ready it replaces the demo course on every screen
 * (data/course.ts). Without a backend there is nothing to load: the app shows the demo course.
 */
import { useEffect, useSyncExternalStore } from "react";
import { api } from "@syllabyte/core/api/client";
import type { MyCourseView } from "@syllabyte/core/api/types";
import type { Course, Video } from "@syllabyte/core/types";
import { getVersion, subscribe as subscribeStore, touch } from "@syllabyte/core/store";
import { courseStubs, showUploadedCourse } from "@/data/course";
import { busy, onlyVideosPending } from "./courseWait";
import { courseCalls, useSession } from "./session";

/** how often to look again while a syllabus is read or slides are analyzed (the student is waiting on the screen) */
const POLL_MS = 4000;
/** and while only videos are being made: a video that lands needs no sooner a look, and every rebuild is a risk to a screen playing one */
const VIDEO_POLL_MS = 10_000;
/** a made video's details are fetched again after this long: the links in them are signed for 12 hours (server app.ts) */
const VIDEO_TTL_MS = 6 * 60 * 60 * 1000;

let view: MyCourseView | null = null;
/** what the screens last drew. The course is rebuilt only when this changes, so a screen that is playing a video keeps the same objects. */
let shownKey: string | null = null;
const listeners = new Set<() => void>();
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
};

/** null until loaded, and always without a backend. */
export const useMyCourse = (): MyCourseView | null => useSyncExternalStore(subscribe, () => view, () => view);
export const getMyCourse = (): MyCourseView | null => view;

/** by course and video: two courses can each have a KU with the same id, and a video is the student's at their level */
const videoCache = new Map<string, { video: Video; at: number }>();
const cacheKey = (courseId: string, videoId: string) => `${courseId}:${videoId}`;

/**
 * The made videos of the student's course, as the server hands them over at their level (getVariant reads and records
 * nothing). Fetched once and again after VIDEO_TTL_MS; one that fails is left out and tried at the next refresh.
 */
export async function loadVideos(course: Course): Promise<Map<string, Video>> {
  const now = Date.now();
  const wanted = course.kus.flatMap((k) => (k.video_id ? [k.video_id] : []));
  const key = (id: string) => cacheKey(course.id, id);
  await Promise.all(
    wanted
      .filter((id) => !videoCache.has(key(id)) || now - videoCache.get(key(id))!.at > VIDEO_TTL_MS)
      .map((id) =>
        api
          .getVariant(id)
          .then((v) => void videoCache.set(key(id), { video: v.video, at: now }))
          .catch(() => undefined),
      ),
  );
  return new Map(wanted.flatMap((id) => (videoCache.has(key(id)) ? [[id, videoCache.get(key(id))!.video] as const] : [])));
}

let inFlight: Promise<MyCourseView | null> | null = null;

/** Fetches the course; when it changed, every screen refetches (levels and the playlist may have moved). */
export function refreshCourse(): Promise<MyCourseView | null> {
  if (!courseCalls) return Promise.resolve(null);
  if (!inFlight) {
    inFlight = (async () => {
      const next = await courseCalls.mine();
      if (next.status === "ready") {
        const course = (await api.getMe()).course;
        const [videos, list] = await Promise.all([loadVideos(course), courseCalls.list().catch(() => [])]);
        const key = JSON.stringify([
          course.id, course.kus.map((k) => [k.id, k.title, k.short_title, k.lecture_n, k.video_id]), next.course.lectures,
          [...videos].map(([id, v]) => [id, v.video_url, v.duration_s]), list,
        ]);
        if (key !== shownKey) {
          shownKey = key;
          showUploadedCourse(course, next.course.lectures, videos, courseStubs(list));
        }
      }
      const changed = JSON.stringify(next) !== JSON.stringify(view);
      const first = view === null;
      view = next;
      if (changed) {
        listeners.forEach((l) => l());
        if (!first) touch();
      }
      return next;
    })().finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

/**
 * Moves the student to another of their courses: the server switches (their state, questions and videos are that
 * course's from the next call), then the phone shows it. Resolves once the course on screen is the new one.
 */
export async function switchCourse(courseId: string): Promise<void> {
  if (!courseCalls || view?.status === "ready" && view.course.id === courseId) return;
  await courseCalls.activate(courseId);
  shownKey = null;
  await refreshCourse();
}

/** The student signed out: whatever was kept about their courses is not for the next one who signs in on this phone. */
export function resetCourseCaches(): void {
  videoCache.clear();
  shownKey = null;
  view = null;
  listeners.forEach((l) => l());
}

/** Keeps the course current: at sign-in, after anything the student changes, and every few seconds while busy. */
export function CourseSync(): null {
  const signedIn = useSession().status === "signedIn";
  const current = useMyCourse();
  const storeVersion = useSyncExternalStore(subscribeStore, getVersion, getVersion);
  useEffect(() => {
    if (signedIn) void refreshCourse().catch(() => {});
    else resetCourseCaches();
  }, [signedIn, storeVersion]);
  useEffect(() => {
    if (!signedIn || !busy(current)) return;
    const id = setInterval(() => void refreshCourse().catch(() => {}), onlyVideosPending(current) ? VIDEO_POLL_MS : POLL_MS);
    return () => clearInterval(id);
  }, [signedIn, current]);
  return null;
}

/**
 * Where a student without a usable course goes first: the welcome screen (no course, or the syllabus couldn't be
 * read) or the analyzing screen (it is being read). Null once the course exists: its lectures come from the slides
 * (plan/slide-uploads-plan.md V3), so there is no list to confirm.
 */
export function setupRoute(v: MyCourseView | null): "/welcome" | "/analyzing" | null {
  if (!v) return null;
  if (v.status === "none" || v.status === "failed") return "/welcome";
  if (v.status === "reading") return "/analyzing";
  return null;
}

