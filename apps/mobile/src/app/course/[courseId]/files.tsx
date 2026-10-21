import { useEffect, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { CourseFilesView } from "@syllabyte/core/api/types";
import { BackButton, Header } from "@/components/Header";
import { Icon, type IconName } from "@/components/Icon";
import { T } from "@/components/T";
import { BACKEND_BASE } from "@/data/backend";
import { lectureNumber } from "@/data/course";
import { courseCalls } from "@/state/session";
import { colors, fonts, radius, shadow, space } from "@/theme/tokens";

type SlideFile = CourseFilesView["slides"][number];

/** Opens one of the student's files in the in-app browser, which shows PDFs and PowerPoint, through a short-lived link. */
async function openFile(courseId: string, fileId: string) {
  if (!courseCalls || !BACKEND_BASE) return;
  try {
    await WebBrowser.openBrowserAsync(BACKEND_BASE + (await courseCalls.fileLink(courseId, fileId)));
  } catch {
    Alert.alert("Couldn't open this file", "Check your connection and try again.");
  }
}

/** Syllabus & Course Slides: the files this student uploaded, each with what became of it. Tap one to open it. */
export default function CourseFiles() {
  const { courseId } = useLocalSearchParams<{ courseId: string }>();
  const insets = useSafeAreaInsets();
  const [files, setFiles] = useState<CourseFilesView | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    courseCalls?.files(courseId).then(setFiles, () => setFailed(true));
  }, [courseId]);

  return (
    <View style={styles.screen}>
      <Header
        bordered
        left={<BackButton />}
        center={
          <T variant="cardTitle" accessibilityRole="header">
            Syllabus & Course Slides
          </T>
        }
      />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 40 }]}>
        {!courseCalls ? (
          <T variant="body" color={colors.onSurfaceVariant} style={styles.note}>
            The files you upload show here. This demo course came with its slides, so there are none to list.
          </T>
        ) : failed ? (
          <T variant="body" color={colors.error} style={styles.note} accessibilityLiveRegion="polite">
            Your files could not be loaded. Check your connection and open this page again.
          </T>
        ) : !files ? null : (
          <>
            <Group label="Syllabus" />
            {files.syllabus ? (
              <FileRow
                icon="description"
                name={files.syllabus.file_name}
                added={files.syllabus.uploaded_at}
                onPress={() => void openFile(courseId, files.syllabus!.id)}
              />
            ) : (
              <T variant="caption" color={colors.onSurfaceVariant} style={styles.note}>
                Your course came from a classmate{"'"}s syllabus.
              </T>
            )}

            <Group label={`Course slides · ${files.slides.length}`} />
            {files.slides.length === 0 ? (
              <T variant="caption" color={colors.onSurfaceVariant} style={styles.note}>
                No slides yet. Add them from your course page.
              </T>
            ) : (
              files.slides.map((f) => <SlideRow key={f.id} file={f} courseId={courseId} />)
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const day = (ms: number) => new Date(ms).toLocaleDateString(undefined, { day: "numeric", month: "short" });

function SlideRow({ file, courseId }: { file: SlideFile; courseId: string }) {
  const n = file.lecture ? lectureNumber(file.lecture.n) : null;
  const what = {
    lecture: file.lecture ? `Lecture ${n} · ${file.lecture.title}` : "A lecture",
    same_as: `Same slides as Lecture ${n}`,
    updated_version: `Newer version of Lecture ${n}; the earlier slides are kept`,
    to_review: "Waiting for you to place it",
    reading: "Reading…",
    failed: "Couldn't read this file",
  }[file.state];
  return (
    <FileRow
      icon="slideshow"
      name={file.file_name}
      detail={what}
      added={file.uploaded_at}
      tone={file.state === "failed" ? colors.error : file.state === "to_review" ? colors.primary : colors.onSurfaceVariant}
      onPress={() => void openFile(courseId, file.id)}
    />
  );
}

function Group({ label }: { label: string }) {
  return (
    <T variant="codeSm" color={colors.onSurfaceVariant} style={styles.group}>
      {label}
    </T>
  );
}

function FileRow({
  icon,
  name,
  detail,
  added,
  tone = colors.onSurfaceVariant,
  onPress,
}: {
  icon: IconName;
  name: string;
  detail?: string;
  added: number;
  tone?: string;
  onPress?: () => void;
}) {
  const body = (
    <>
      <View style={styles.fileIcon}>
        <Icon name={icon} size={20} color={colors.primary} />
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <T variant="bodySemibold" numberOfLines={2}>
          {name}
        </T>
        {detail ? (
          <T variant="caption" color={tone} numberOfLines={2}>
            {detail}
          </T>
        ) : null}
        <T variant="caption" color={colors.outline}>
          Added {day(added)}
        </T>
      </View>
      {onPress ? <Icon name="open-in-new" size={18} color={colors.outline} /> : null}
    </>
  );
  if (!onPress) return <View style={styles.file}>{body}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Open ${name}`}
      accessibilityHint={detail}
      onPress={onPress}
      style={({ pressed }) => [styles.file, pressed && { backgroundColor: colors.surfaceContainerLow }]}
    >
      {body}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: space.gutter, paddingTop: 8, gap: 8 },
  group: { textTransform: "uppercase", letterSpacing: 1.6, paddingHorizontal: 4, paddingTop: 16, fontFamily: fonts.monoMedium },
  note: { paddingHorizontal: 4 },
  file: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    minHeight: 64,
    padding: 12,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceContainerLowest,
    ...shadow.card,
  },
  fileIcon: { width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.primaryTint, alignItems: "center", justifyContent: "center" },
});
