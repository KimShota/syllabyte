/**
 * Picking and sending course files (plan/slide-uploads-plan.md). Slides chosen on the welcome screen wait here
 * until the course exists, then go up like any other slides and land on the review screen.
 */
import * as DocumentPicker from "expo-document-picker";
import type { UploadFile, UploadView } from "@syllabyte/core/api/types";
import { setPrefs } from "./app";
import { courseCalls } from "./session";

export const MIME = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
};
/** Keynote can't be read: the server asks for a PDF instead, so the picker does not offer it. */
export const SLIDE_TYPES = [MIME.pdf, MIME.pptx];
export const SYLLABUS_TYPES = [MIME.pdf, MIME.docx];

export function toUploadFile(a: DocumentPicker.DocumentPickerAsset): UploadFile {
  return { name: a.name, uri: a.uri, mimeType: a.mimeType ?? null, file: a.file ?? null };
}

/** The system picker; null when the student cancels. */
export async function pickFiles(types: string[], multiple: boolean): Promise<UploadFile[] | null> {
  const res = await DocumentPicker.getDocumentAsync({ type: types, multiple, copyToCacheDirectory: true });
  return res.canceled ? null : res.assets.map(toUploadFile);
}

let pending: UploadFile[] = [];

/** Slides picked before the course exists (the welcome screen). */
export function setPendingSlides(files: UploadFile[]): void {
  pending = files;
}

/** Sends the slides picked on the welcome screen, if any; true when there were some. */
export async function sendPendingSlides(courseId: string): Promise<boolean> {
  if (!courseCalls || pending.length === 0) return false;
  const files = pending;
  await courseCalls.addSlides(courseId, files);
  pending = [];
  return true;
}

/** "Add slides": pick one or more files and upload them; false when the student cancelled. Throws the server's message. */
export async function pickAndAddSlides(courseId: string): Promise<UploadView[] | false> {
  if (!courseCalls) return false;
  const files = await pickFiles(SLIDE_TYPES, true);
  if (!files) return false;
  return courseCalls.addSlides(courseId, files);
}

/**
 * The course is ready: the first run is over. Slides picked on the welcome screen go up
 * now and the student places them on the review screen; otherwise Home.
 */
export async function finishSetup(courseId: string): Promise<{ pathname: "/course/[courseId]/review"; params: { courseId: string } } | "/"> {
  setPrefs({ setupDone: true });
  return (await sendPendingSlides(courseId)) ? { pathname: "/course/[courseId]/review", params: { courseId } } : "/";
}
