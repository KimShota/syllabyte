/**
 * Picking and sending course files. The server saves, organizes and analyzes slides in the background.
 */
import * as DocumentPicker from "expo-document-picker";
import { File } from "expo-file-system";
import { Platform } from "react-native";
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
  return { name: a.name, uri: a.uri, mimeType: a.mimeType ?? null, file: Platform.OS === "web" ? a.file ?? null : new File(a.uri) };
}

/** The system picker; null when the student cancels. */
export async function pickFiles(types: string[], multiple: boolean): Promise<UploadFile[] | null> {
  const res = await DocumentPicker.getDocumentAsync({ type: types, multiple, copyToCacheDirectory: true });
  return res.canceled ? null : res.assets.map(toUploadFile);
}

/** "Add slides": pick one or more files and upload them; false when the student cancelled. Throws the server's message. */
export async function pickAndAddSlides(courseId: string): Promise<UploadView[] | false> {
  if (!courseCalls) return false;
  const files = await pickFiles(SLIDE_TYPES, true);
  if (!files) return false;
  return courseCalls.addSlides(courseId, files);
}

/**
 * The course exists: open its roadmap while the server organizes and analyzes the already saved slides.
 */
export async function finishSetup(courseId: string): Promise<{ pathname: "/course/[courseId]"; params: { courseId: string } }> {
  setPrefs({ setupDone: true });
  return { pathname: "/course/[courseId]", params: { courseId } };
}
