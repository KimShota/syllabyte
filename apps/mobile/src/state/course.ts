/**
 * The student's uploaded course, with a backend (plan/slide-uploads-plan.md): whether they have one yet, its syllabus
 * being read, and each lecture's slides. Once the course is ready it replaces the demo course on every screen
 * (data/course.ts). Without a backend there is nothing to load: the app shows the demo course.
 */
import { useEffect, useSyncExternalStore } from "react";
import { api } from "@syllabyte/core/api/client";
import type { MyCourseView } from "@syllabyte/core/api/types";
import { getVersion, subscribe as subscribeStore, touch } from "@syllabyte/core/store";
import { showUploadedCourse } from "@/data/course";
import { courseCalls, useSession } from "./session";

/** how often to look again while a syllabus is read or slides are analyzed */
const POLL_MS = 4000;

let view: MyCourseView | null = null;
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

/** Something is still being read or analyzed, so the course will change by itself. */
export function busy(v: MyCourseView | null): boolean {
  if (!v) return false;
  if (v.status === "reading") return true;
  return v.status === "ready" && v.course.lectures.some((l) => l.state === "analyzing");
}

let inFlight: Promise<MyCourseView | null> | null = null;

/** Fetches the course; when it changed, every screen refetches (levels and the playlist may have moved). */
export function refreshCourse(): Promise<MyCourseView | null> {
  if (!courseCalls) return Promise.resolve(null);
  if (!inFlight) {
    inFlight = (async () => {
      const next = await courseCalls.mine();
      if (next.status === "ready") showUploadedCourse((await api.getMe()).course, next.course.lectures);
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

/** Keeps the course current: at sign-in, after anything the student changes, and every few seconds while busy. */
export function CourseSync(): null {
  const signedIn = useSession().status === "signedIn";
  const current = useMyCourse();
  const storeVersion = useSyncExternalStore(subscribeStore, getVersion, getVersion);
  useEffect(() => {
    if (signedIn) void refreshCourse().catch(() => {});
  }, [signedIn, storeVersion]);
  useEffect(() => {
    if (!signedIn || !busy(current)) return;
    const id = setInterval(() => void refreshCourse().catch(() => {}), POLL_MS);
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

