import { useState } from "react";
import type { UploadFile } from "@syllabyte/core/api/types";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import * as DocumentPicker from "expo-document-picker";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { Icon, type IconName } from "@/components/Icon";
import { T } from "@/components/T";
import { REMOTE } from "@/data/backend";
import { refreshCourse, useMyCourse } from "@/state/course";
import { courseCalls } from "@/state/session";
import { setPendingSlides, SLIDE_TYPES, SYLLABUS_TYPES, toUploadFile } from "@/state/uploads";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const MIME = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  key: "application/x-iwork-keynote-sffkey",
};

/**
 * First run: upload the syllabus and the lecture slides. With a backend (plan/slide-uploads-plan.md) the syllabus is
 * required and sent now; slides are optional (they can be added any time) and are sent once the course exists.
 * Without one, the demo course stands in for whatever is picked.
 */
export default function Welcome() {
  const insets = useSafeAreaInsets();
  const [syllabus, setSyllabus] = useState<UploadFile | null>(null);
  const [slides, setSlides] = useState<UploadFile[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const myCourse = useMyCourse();
  // the last syllabus couldn't be read: say why
  const lastError = myCourse?.status === "failed" ? myCourse.error : null;

  async function start() {
    if (!REMOTE || !courseCalls) {
      router.push({ pathname: "/analyzing", params: { from: "welcome" } });
      return;
    }
    if (!syllabus) return;
    setError(null);
    setSending(true);
    try {
      setPendingSlides(slides);
      await courseCalls.create(syllabus);
      await refreshCourse();
      router.replace("/analyzing");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The syllabus could not be uploaded.");
    } finally {
      setSending(false);
    }
  }

  return (
    <View style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom + 8 }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={styles.logo}>
            <Icon name="menu-book" size={28} color={colors.onPrimary} />
          </View>
          <T variant="titleMobile" style={{ fontFamily: fonts.extraBold, textAlign: "center" }} accessibilityRole="header">
            Welcome to SyllaByte
          </T>
          <T variant="body" color="#606474" style={{ textAlign: "center", marginTop: 8, maxWidth: 300, fontFamily: fonts.medium }}>
            {REMOTE
              ? "Start with your syllabus: it lists your lectures. Add slides now, or as the semester goes."
              : "Upload your course materials to auto-generate interactive study roadmaps."}
          </T>
        </View>

        <View style={styles.card}>
          <Dropzone
            title="Syllabus"
            icon="description"
            tint={colors.primaryTint}
            iconColor={colors.primary}
            formats={["PDF", "DOCX"]}
            file={syllabus?.name ?? null}
            onPick={async () => {
              const res = await DocumentPicker.getDocumentAsync({ type: REMOTE ? SYLLABUS_TYPES : [MIME.pdf, MIME.docx], copyToCacheDirectory: true });
              if (!res.canceled) setSyllabus(toUploadFile(res.assets[0]));
            }}
          />
          <Dropzone
            title={REMOTE ? "Lecture Slides (optional)" : "Lecture Slides"}
            icon="slideshow"
            tint="#e6f7f4"
            iconColor="#0d9488"
            formats={REMOTE ? ["PDF", "PPTX"] : ["PDF", "PPTX", "KEY"]}
            file={slides.length ? slides.map((f) => f.name).join(", ") : null}
            onPick={async () => {
              const res = await DocumentPicker.getDocumentAsync({ type: REMOTE ? SLIDE_TYPES : [MIME.pdf, MIME.pptx, MIME.key], multiple: true, copyToCacheDirectory: true });
              if (!res.canceled) setSlides(res.assets.map(toUploadFile));
            }}
          />
        </View>
      </ScrollView>

      <View style={styles.footer}>
        {error ?? lastError ? (
          <T variant="caption" color={colors.error} style={{ textAlign: "center" }} accessibilityLiveRegion="polite">
            {error ?? lastError}
          </T>
        ) : null}
        <Button
          label={sending ? "Uploading…" : "Get Started"}
          trailingIcon="arrow-forward"
          disabled={REMOTE ? !syllabus || sending : false}
          onPress={start}
        />
        {REMOTE ? (
          !syllabus ? (
            <T variant="caption" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>
              Choose your syllabus to continue.
            </T>
          ) : null
        ) : !syllabus && !slides.length ? (
          <T variant="caption" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>
            No files yet? Continue with the demo course, CS-UH 2219E.
          </T>
        ) : null}
      </View>
    </View>
  );
}

function Dropzone({
  title,
  icon,
  tint,
  iconColor,
  formats,
  file,
  onPick,
}: {
  title: string;
  icon: IconName;
  tint: string;
  iconColor: string;
  formats: string[];
  file: string | null;
  onPick: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={file ? `${title}: ${file}. Choose a different file` : `Upload ${title.toLowerCase()} file`}
      onPress={onPick}
      style={({ pressed }) => [styles.drop, file && styles.dropDone, pressed && { borderColor: colors.primary, backgroundColor: colors.primaryTint }]}
    >
      <View style={[styles.dropIcon, { backgroundColor: file ? colors.secondaryContainer : tint }]}>
        <Icon name={file ? "check" : icon} size={24} color={file ? colors.secondary : iconColor} />
      </View>
      <T variant="bodySemibold" style={{ fontFamily: fonts.bold, fontSize: 16 }}>
        {title}
      </T>
      <T variant="caption" color="#606474" style={{ fontSize: 12, marginTop: 2 }} numberOfLines={1}>
        {file ?? "Select file"}
      </T>
      <View style={styles.formats}>
        {formats.map((f) => (
          <View key={f} style={styles.format}>
            <T variant="codeSm" color="#64748b" style={{ fontSize: 11, fontFamily: fonts.bold }}>
              {f}
            </T>
          </View>
        ))}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f2f3f7" },
  content: { paddingHorizontal: 16, paddingTop: 24, paddingBottom: 24 },
  header: { alignItems: "center", marginBottom: 28 },
  logo: {
    width: 56,
    height: 56,
    borderRadius: radius.xl,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 20,
    ...shadow.glow,
  },
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: 24,
    padding: 16,
    gap: 16,
    borderWidth: 1,
    borderColor: "rgba(243,232,255,0.6)",
    ...shadow.card,
  },
  drop: {
    borderRadius: radius.xl,
    borderWidth: 1.5,
    borderStyle: "dashed",
    borderColor: colors.outlineVariant,
    padding: 20,
    alignItems: "center",
  },
  dropDone: { borderStyle: "solid", borderColor: "rgba(0,107,93,0.35)" },
  dropIcon: { width: 48, height: 48, borderRadius: radius.lg, alignItems: "center", justifyContent: "center", marginBottom: 12 },
  formats: { flexDirection: "row", gap: 8, marginTop: 14 },
  format: { paddingHorizontal: 10, paddingVertical: 2, borderRadius: 6, borderWidth: 1, borderColor: "#e2e8f0", backgroundColor: "#f8fafc" },
  footer: { paddingHorizontal: 16, gap: 10 },
});
