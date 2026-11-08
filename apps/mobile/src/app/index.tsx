import { useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Header, ProfileButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { Spin } from "@/components/Motion";
import { ProgressBar } from "@/components/ProgressBar";
import { T } from "@/components/T";
import { TaskCards } from "@/components/TaskCards";
import { UploadSheet } from "@/components/UploadSheet";
import { api } from "@syllabyte/core/api/client";
import { REMOTE } from "@/data/backend";
import { COURSE, OTHER_COURSES, useCourseVersion } from "@/data/course";
import { courseProgress } from "@/data/selectors";
import { usePrefs, useQuery } from "@/state/app";
import { refreshCourse, setupRoute, switchCourse, useMyCourse } from "@/state/course";
import { courseCalls } from "@/state/session";
import { useProgress } from "@/state/progress";
import { colors, fonts, radius, shadow, space } from "@/theme/tokens";

/** Home: the enrolled courses with their progress. */
export default function Home() {
  const prefs = usePrefs();
  const me = useQuery(() => api.getMe());
  const myCourse = useMyCourse();
  useCourseVersion();
  const progress = useProgress();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ upload?: string }>();
  const [manualOpen, setManualOpen] = useState(false);
  // "Add New Course" in the drawer comes back here with ?upload=<stamp>; closing dismisses that stamp
  const [dismissed, setDismissed] = useState<string | undefined>();
  const uploadOpen = manualOpen || (!!params.upload && params.upload !== dismissed);
  const setUploadOpen = (open: boolean) => {
    setManualOpen(open);
    if (!open) setDismissed(params.upload);
  };

  if (!me || (REMOTE && !myCourse)) return <View style={styles.screen} />;
  // Offer the first upload once; students can leave it to explore Home without adding a course.
  const setup = REMOTE ? setupRoute(myCourse, prefs.setupDone) : null;
  if (setup) return <Redirect href={setup} />;
  if (!REMOTE && !prefs.setupDone && !me.onboarding_done) return <Redirect href="/welcome" />;

  const adding = REMOTE
    ? myCourse?.status === "ready" ? myCourse.adding
      : myCourse?.status === "reading" || myCourse?.status === "failed" ? myCourse : null
    : null;
  const processing = adding?.status === "reading" || (REMOTE && myCourse?.status === "ready" &&
    ((myCourse.course.slides_pending ?? 0) > 0 || myCourse.course.lectures.some((l) => l.state === "analyzing")));
  // with a backend the student is in one course at a time: opening another switches the server to it first
  async function openCourse(id: string) {
    if (REMOTE && id !== COURSE.id) await switchCourse(id).catch(() => undefined);
    router.push({ pathname: "/course/[courseId]", params: { courseId: id } });
  }
  const main = courseProgress(COURSE, progress);
  // The demo or a previous account's course must not appear while the first uploaded course is being created.
  const courses = REMOTE && myCourse?.status !== "ready" ? [] : [
    { id: COURSE.id, name: COURSE.name, progress: main.fraction, analyzing: undefined as number | undefined },
    ...OTHER_COURSES.map((c) => ({ id: c.id, name: c.name, progress: c.progress, analyzing: c.analyzing?.progress })),
  ];

  return (
    <View style={styles.screen}>
      <Header
        bordered
        left={
          <View style={styles.brand}>
            <Image source={require("../../assets/icon.png")} style={styles.logo} accessibilityIgnoresInvertColors />
            <View>
              <T variant="eyebrow" color={colors.primary} style={{ fontSize: 12, lineHeight: 16, fontFamily: fonts.monoSemibold }}>
                SyllaByte
              </T>
              <T variant="bodySemibold" style={{ fontFamily: fonts.bold, fontSize: 18, lineHeight: 22 }}>
                Home
              </T>
            </View>
          </View>
        }
        right={<ProfileButton size={40} />}
      />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 40 }]}>
        <View style={styles.titleRow}>
          <View style={{ flex: 1 }}>
            <T variant="title" accessibilityRole="header">
              My Courses
            </T>
            <T variant="caption" color={colors.onSurfaceVariant} style={{ marginTop: 2 }}>
              See your enrolled courses & track progress for each
            </T>
          </View>
        </View>

        <TaskCards />

        <View style={styles.list}>
          {REMOTE && myCourse?.status === "none" ? (
            <T variant="body" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>
              No courses yet. Upload a syllabus when you’re ready.
            </T>
          ) : null}
          {courses.map((c) => (
            <CourseCard
              key={c.id}
              name={c.name}
              progress={c.progress}
              analyzing={c.analyzing}
              onPress={() => void openCourse(c.id)}
            />
          ))}
          {processing ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Processing your materials. View progress in the analyzer"
              onPress={() => router.push({ pathname: "/analyzing", params: { from: "home" } })}
              style={({ pressed }) => [styles.card, styles.cardAnalyzing, pressed && { backgroundColor: colors.surfaceContainerLow }]}
            >
              <View style={styles.cardTop}>
                <View style={styles.cardName}>
                  <Spin>
                    <Icon name="sync" size={20} color={colors.primary} />
                  </Spin>
                  <T variant="cardTitle" style={{ fontSize: 17, lineHeight: 23, flexShrink: 1 }}>
                    Processing your materials…
                  </T>
                </View>
                <View style={styles.analyzingChip}>
                  <T variant="codeSm" color={colors.onSecondaryFixedVariant} style={{ fontSize: 11, fontFamily: fonts.monoSemibold, letterSpacing: 1 }}>
                    ANALYZING
                  </T>
                </View>
              </View>
              <T variant="caption" color={colors.onSurfaceVariant}>
                You can keep exploring. Your course will update here when it is ready.
              </T>
              <View style={styles.viewProgress}>
                <T variant="caption" color={colors.primary} style={{ fontFamily: fonts.semibold }}>
                  View progress
                </T>
                <Icon name="arrow-forward" size={16} color={colors.primary} />
              </View>
            </Pressable>
          ) : null}
          {adding?.status === "failed" ? (
            <View style={styles.card} accessibilityRole="alert">
              <T variant="cardTitle" style={{ fontSize: 17, lineHeight: 23 }}>
                We could not add that course
              </T>
              <T variant="caption" color={colors.error}>
                {adding.error ?? "Your syllabus could not be read. Please try uploading it again."}
              </T>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  if (myCourse?.status === "failed") router.push("/welcome");
                  else void courseCalls?.syllabusErrorSeen().then(() => refreshCourse()).catch(() => undefined);
                }}
                style={({ pressed }) => [styles.okButton, pressed && { backgroundColor: colors.surfaceContainerHigh }]}
              >
                <T variant="bodySemibold" color={colors.primary} style={{ fontSize: 14 }}>
                  {myCourse?.status === "failed" ? "Try again" : "OK"}
                </T>
              </Pressable>
            </View>
          ) : null}
          <Pressable
            accessibilityRole="button"
            onPress={() => (REMOTE ? router.push("/welcome") : setUploadOpen(true))}
            style={({ pressed }) => [styles.another, pressed && { backgroundColor: colors.surfaceContainer }]}
          >
            <Icon name="upload-file" size={20} color={colors.primary} />
            <T variant="bodySemibold" color={colors.primary} style={{ fontSize: 14 }}>
              {REMOTE && myCourse?.status === "none" ? "+ Upload a Course" : "+ Upload Another Course"}
            </T>
          </Pressable>
        </View>
      </ScrollView>

      <UploadSheet
        visible={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSubmit={() => {
          setUploadOpen(false);
          router.push({ pathname: "/analyzing", params: { from: "home" } });
        }}
      />
    </View>
  );
}

function CourseCard({ name, progress, analyzing, onPress }: { name: string; progress: number; analyzing?: number; onPress: () => void }) {
  const pct = Math.round((analyzing ?? progress) * 100);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={analyzing !== undefined ? `${name}, analyzing, ${pct} percent` : `${name}, ${pct} percent complete`}
      onPress={onPress}
      disabled={analyzing !== undefined}
      style={({ pressed }) => [styles.card, analyzing !== undefined && styles.cardAnalyzing, pressed && { backgroundColor: colors.surfaceContainerLow }]}
    >
      <View style={styles.cardTop}>
        <View style={styles.cardName}>
          {analyzing !== undefined ? (
            <Spin>
              <Icon name="sync" size={20} color={colors.primary} />
            </Spin>
          ) : null}
          <T variant="cardTitle" style={{ fontSize: 17, lineHeight: 23, flexShrink: 1 }}>
            {name}
          </T>
        </View>
        {analyzing !== undefined ? (
          <View style={styles.analyzingChip}>
            <T variant="codeSm" color={colors.onSecondaryFixedVariant} style={{ fontSize: 11, fontFamily: fonts.monoSemibold, letterSpacing: 1 }}>
              ANALYZING
            </T>
          </View>
        ) : (
          <T variant="bodySemibold" color={colors.primary} style={{ fontFamily: fonts.bold }}>
            {pct}%
          </T>
        )}
      </View>
      {analyzing !== undefined ? (
        <View style={styles.analyzingRow}>
          <T variant="caption" color={colors.onSurfaceVariant}>
            Analyzing content...
          </T>
          <T variant="caption" color={colors.primary} style={{ fontFamily: fonts.bold }}>
            {pct}%
          </T>
        </View>
      ) : null}
      <ProgressBar value={analyzing ?? progress} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  brand: { flexDirection: "row", alignItems: "center", gap: 12, paddingLeft: 4 },
  logo: { width: 40, height: 40, borderRadius: radius.lg },
  content: { paddingHorizontal: space.gutter, paddingTop: 24 },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  list: { marginTop: 28, gap: 16 },
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: radius.xl,
    padding: 20,
    gap: 14,
    borderWidth: 1,
    borderColor: colors.surfaceContainerHighest,
    ...shadow.card,
  },
  cardAnalyzing: { borderColor: "rgba(91,63,214,0.3)" },
  viewProgress: { flexDirection: "row", alignItems: "center", gap: 6 },
  cardTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  cardName: { flexDirection: "row", alignItems: "center", gap: 8, flex: 1 },
  analyzingChip: { backgroundColor: colors.secondaryContainer, borderRadius: radius.full, paddingHorizontal: 8, paddingVertical: 2 },
  okButton: { alignSelf: "flex-end", paddingVertical: 8, paddingHorizontal: 20, borderRadius: radius.full, backgroundColor: colors.surfaceContainer },
  analyzingRow: { flexDirection: "row", justifyContent: "space-between", marginTop: -4 },
  another: {
    marginTop: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 18,
    borderRadius: radius.xl,
    borderWidth: 2,
    borderStyle: "dashed",
    borderColor: colors.outlineVariant,
    backgroundColor: "rgba(244,242,254,0.6)",
  },
});
