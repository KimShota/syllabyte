import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { CoursesDrawer } from "@/components/CoursesDrawer";
import { Header, IconButton, ProfileButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { PulseAura } from "@/components/Motion";
import { ProgressBar } from "@/components/ProgressBar";
import { Serpentine, type SerpentineRow, type SpineSegment } from "@/components/Serpentine";
import { T } from "@/components/T";
import { REMOTE } from "@/data/backend";
import { COURSE, OTHER_COURSES, useCourseVersion } from "@/data/course";
import { courseLectures, type LectureNodeView } from "@/data/selectors";
import type { LectureStatus } from "@/data/types";
import { useProgress } from "@/state/progress";
import { pickAndAddSlides } from "@/state/uploads";
import { colors, fonts, radius, shadow, space } from "@/theme/tokens";

const NODE = 56;
const LEFT = 0.2;
const RIGHT = 0.8;

/** Course roadmap: the lectures as a path climbing from Lecture 1 to the final exam. */
export default function CourseRoadmap() {
  const { courseId } = useLocalSearchParams<{ courseId: string }>();
  const progress = useProgress();
  const insets = useSafeAreaInsets();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  useCourseVersion();

  const stub = OTHER_COURSES.find((c) => c.id === courseId);
  const lectures = courseLectures(COURSE, progress);

  return (
    <View style={styles.screen}>
      <Header
        left={<IconButton icon="home" label="Return to Home" color={colors.onSurfaceVariant} onPress={() => router.dismissTo("/")} />}
        center={
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Switch or view courses"
            onPress={() => setDrawerOpen(true)}
            style={({ pressed }) => [styles.switcher, pressed && { backgroundColor: colors.surfaceContainer }]}
          >
            <Icon name="menu-book" size={20} color={colors.primary} />
            <T variant="cardTitle" style={{ letterSpacing: -0.2 }}>
              My Courses
            </T>
            <Icon name="expand-more" size={20} color={colors.onSurfaceVariant} />
          </Pressable>
        }
        right={<ProfileButton />}
      />

      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 48 }]}>
        <T variant="codeSm" color={colors.onSurfaceVariant} style={{ textTransform: "uppercase", letterSpacing: 1.2 }}>
          Course Overview
        </T>
        <T variant="titleMobile" style={{ marginTop: 10 }} accessibilityRole="header">
          {stub ? stub.name : COURSE.name}
        </T>
        <View style={styles.meta}>
          {stub || !COURSE.professor ? null : (
            <>
              <T variant="caption" color={colors.onSurfaceVariant}>
                {COURSE.professor}
              </T>
              <View style={styles.dot} />
            </>
          )}
          <T variant="codeSm" color={colors.onSurfaceVariant}>
            {stub ? `${stub.code} · ${stub.term}` : [COURSE.code, COURSE.term].filter(Boolean).join(" · ")}
          </T>
        </View>

        {/* an uploaded course: slides are added here, all at once or a lecture at a time (plan/slide-uploads-plan.md) */}
        {REMOTE && !stub ? (
          <View style={styles.addSlides}>
            <Button
              label={adding ? "Uploading…" : "Add slides"}
              icon="upload-file"
              kind="secondary"
              height={44}
              disabled={adding}
              onPress={async () => {
                setAddError(null);
                setAdding(true);
                try {
                  const added = await pickAndAddSlides(COURSE.id);
                  if (added) router.push({ pathname: "/course/[courseId]/review", params: { courseId: COURSE.id } });
                } catch (e) {
                  setAddError(e instanceof Error ? e.message : "The files could not be uploaded.");
                } finally {
                  setAdding(false);
                }
              }}
            />
            <T variant="caption" color={addError ? colors.error : colors.onSurfaceVariant} style={{ textAlign: "center" }} accessibilityLiveRegion="polite">
              {addError ?? "PDF or PowerPoint, one file per lecture. Add them all now or as the semester goes."}
            </T>
          </View>
        ) : null}

        {stub ? (
          <View style={styles.stub}>
            <Icon name="school" size={32} color={colors.primary} />
            <T variant="cardTitle" style={{ textAlign: "center" }}>
              No lectures in this demo
            </T>
            <T variant="body" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>
              Only Computational Social Science has slides and videos in this build.
            </T>
            <Button label="Open Computational Social Science" kind="secondary" onPress={() => router.setParams({ courseId: COURSE.id })} />
          </View>
        ) : (
          <View style={{ marginTop: 24 }}>
            <Path lectures={lectures} />
          </View>
        )}
      </ScrollView>

      <CoursesDrawer visible={drawerOpen} onClose={() => setDrawerOpen(false)} currentId={courseId} />
    </View>
  );
}

function segmentFor(upper: LectureStatus, lower: LectureStatus): SpineSegment {
  if (lower === "completed") return { color: colors.secondary, width: 3 };
  if (lower === "active") return { color: colors.primaryFixedDim, dashed: true, width: 3 };
  return { color: colors.outlineVariant, dashed: true, width: 2.5 };
}

function Path({ lectures }: { lectures: LectureNodeView[] }) {
  const top = [...lectures].reverse();
  const exam = COURSE.finalExam;
  const rows: SerpentineRow[] = [
    ...(exam ? [{
      key: "final",
      height: 170,
      nodeX: 0.5,
      nodeY: 10 + NODE / 2,
      render: () => (
        <View style={styles.finalRow}>
          <View style={[styles.node, styles.finalNode]}>
            <Icon name="school" size={28} color={colors.tertiary} />
          </View>
          <View style={styles.finalCard}>
            <T variant="bodySemibold">{exam.title}</T>
            <T variant="codeSm" color={colors.onSurfaceVariant} style={{ marginTop: 4 }}>
              {exam.subtitle}
            </T>
          </View>
        </View>
      ),
    }] : []),
    ...top.map((view) => {
      const nodeRight = view.lecture.n % 2 === 1;
      return {
        key: `l${view.lecture.n}`,
        height: view.status === "active" ? 170 : 150,
        nodeX: nodeRight ? RIGHT : LEFT,
        render: (width: number) => <LectureRow view={view} nodeRight={nodeRight} width={width} />,
      };
    }),
  ];
  // the segment below each row but the last; without the exam row, the first row is a lecture
  const offset = exam ? 1 : 0;
  const segments: SpineSegment[] = rows.slice(0, -1).map((_, i) => {
    const upper = i - offset < 0 ? "awaiting" : top[i - offset].status;
    return segmentFor(upper, top[i + 1 - offset].status);
  });
  return <Serpentine rows={rows} segments={segments} />;
}

function LectureRow({ view, nodeRight, width }: { view: LectureNodeView; nodeRight: boolean; width: number }) {
  const { lecture, status, progress } = view;
  const cardWidth = Math.min(230, width * 0.62);
  const openLecture = () => router.push({ pathname: "/course/[courseId]/lecture/[n]", params: { courseId: COURSE.id, n: String(lecture.n) } });
  const label = `Lecture ${lecture.n}: ${lecture.title}`;

  const node = (() => {
    switch (status) {
      case "completed":
        return (
          <Pressable accessibilityRole="button" accessibilityLabel={`Review ${label}`} onPress={openLecture} style={[styles.node, styles.nodeDone]}>
            <Icon name="check" size={26} color={colors.onPrimary} />
          </Pressable>
        );
      case "active":
        return (
          <View style={styles.nodeWrap}>
            <PulseAura size={NODE + 16} color={colors.primaryFixed} />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={progress.nextKu ? `Continue with ${progress.nextKu.shortTitle}` : `Continue ${label}`}
              onPress={() =>
                progress.nextKu ? router.push({ pathname: "/player/[kuId]", params: { kuId: progress.nextKu.id } }) : openLecture()
              }
              style={[styles.node, styles.nodeActive]}
            >
              <Icon name="play-arrow" size={28} color={colors.onPrimary} />
            </Pressable>
          </View>
        );
      case "available":
        return (
          <Pressable accessibilityRole="button" accessibilityLabel={`Open ${label}`} onPress={openLecture} style={[styles.node, styles.nodeOpen]}>
            <T variant="eyebrow" color={colors.primaryDeep} style={{ fontFamily: fonts.monoSemibold, letterSpacing: 0.5 }}>
              {String(lecture.n).padStart(2, "0")}
            </T>
          </Pressable>
        );
      case "awaiting":
        return (
          <View accessible accessibilityLabel={`${label}, awaiting slides`} style={[styles.node, styles.nodeAwaiting]}>
            <Icon name="hourglass-empty" size={24} color={colors.onSurfaceVariant} />
          </View>
        );
    }
  })();

  const card = (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={status === "awaiting"}
      onPress={openLecture}
      style={({ pressed }) => [
        styles.card,
        { width: cardWidth },
        status === "active" && styles.cardActive,
        status === "awaiting" && styles.cardAwaiting,
        pressed && { backgroundColor: colors.surfaceContainerLow },
      ]}
    >
      <CardBody view={view} alignRight={!nodeRight && status === "awaiting"} />
    </Pressable>
  );

  return (
    <View style={styles.lectureRow}>
      <View style={[StyleSheet.absoluteFill, styles.centerY, { alignItems: nodeRight ? "flex-start" : "flex-end" }]}>{card}</View>
      <View style={[StyleSheet.absoluteFill, styles.centerY]} pointerEvents="box-none">
        <View style={{ marginLeft: (nodeRight ? RIGHT : LEFT) * width - NODE / 2, width: NODE, alignItems: "center" }}>{node}</View>
      </View>
    </View>
  );
}

function CardBody({ view, alignRight }: { view: LectureNodeView; alignRight: boolean }) {
  const { lecture, status, progress } = view;
  const align = alignRight ? ({ textAlign: "right" } as const) : undefined;
  const eyebrowColor = status === "completed" ? colors.secondary : status === "awaiting" ? colors.onSurfaceVariant : colors.primary;
  const eyebrowRight =
    status === "completed" ? "Completed" : status === "active" ? "In Progress" : lecture.date ?? "";

  return (
    <View style={{ alignItems: alignRight ? "flex-end" : "flex-start" }}>
      <View style={styles.eyebrowRow}>
        <T variant="codeSm" color={eyebrowColor} style={[styles.eyebrow, status === "active" && { fontFamily: fonts.monoSemibold }]}>
          Lecture {lecture.n}
          {eyebrowRight ? ` · ${eyebrowRight}` : ""}
        </T>
      </View>
      <T variant="bodySemibold" style={[{ marginTop: 4 }, align]}>
        {lecture.title}
      </T>

      {status === "completed" ? (
        <View style={[styles.chip, { backgroundColor: colors.secondaryContainer }]}>
          <Icon name="check-circle" size={13} color={colors.onSecondaryContainer} />
          <T variant="codeSm" color={colors.onSecondaryContainer}>
            {progress.total} of {progress.total} completed
          </T>
        </View>
      ) : null}
      {status === "active" ? (
        <View style={{ alignSelf: "stretch" }}>
          <View style={styles.progressRow}>
            <ProgressBar value={progress.total ? progress.done / progress.total : 0} height={6} style={{ flex: 1, width: "auto" }} />
            <T variant="codeSm" color={colors.primary} style={{ fontFamily: fonts.monoSemibold }}>
              {progress.done}/{progress.total}
            </T>
          </View>
          {progress.nextKu ? (
            <View style={styles.next}>
              <T variant="codeSm" color={colors.onSurfaceVariant} numberOfLines={1} style={{ flex: 1 }}>
                Next: {progress.nextKu.shortTitle}
              </T>
              <Icon name="arrow-forward" size={16} color={colors.primary} />
            </View>
          ) : null}
        </View>
      ) : null}
      {status === "available" ? (
        <View style={[styles.chip, { backgroundColor: colors.surfaceContainer }]}>
          <View style={styles.chipDot} />
          <T variant="codeSm" color={colors.onSurfaceVariant}>
            Not started (0/{progress.total})
          </T>
        </View>
      ) : null}
      {status === "awaiting" ? <AwaitingChip state={lecture.state} /> : null}
    </View>
  );
}

/** Where an uploaded lecture's slides are (U14); the demo's lectures are simply awaiting them. */
function AwaitingChip({ state }: { state: LectureNodeView["lecture"]["state"] }) {
  const look =
    state === "analyzing"
      ? { icon: "autorenew" as const, text: "Analyzing slides…", color: colors.primary, bg: colors.primaryTint }
      : state === "failed"
        ? { icon: "error-outline" as const, text: "Couldn't read these slides", color: colors.error, bg: colors.errorContainer }
        : { icon: "schedule" as const, text: state === "waiting" ? "Waiting for slides" : "Awaiting slides", color: colors.onSurfaceVariant, bg: colors.surfaceContainerHigh };
  return (
    <View style={[styles.chip, { backgroundColor: look.bg }]}>
      <Icon name={look.icon} size={12} color={look.color} />
      <T variant="codeSm" color={look.color} style={{ fontSize: 10 }}>
        {look.text}
      </T>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  switcher: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.lg, minHeight: 44 },
  content: { paddingHorizontal: space.gutter, paddingTop: 12 },
  meta: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 2 },
  dot: { width: 4, height: 4, borderRadius: 2, backgroundColor: colors.outline },
  addSlides: { marginTop: 16, gap: 8 },
  stub: { marginTop: 32, padding: 24, gap: 12, alignItems: "center", backgroundColor: colors.surfaceContainerLowest, borderRadius: radius.card, ...shadow.card },
  finalRow: { alignItems: "center" },
  finalNode: { backgroundColor: colors.tertiaryFixed, marginTop: 10 },
  finalCard: { marginTop: 12, backgroundColor: colors.surfaceContainerLowest, paddingHorizontal: 16, paddingVertical: 12, borderRadius: radius.lg, alignItems: "center", ...shadow.card },
  lectureRow: { flex: 1 },
  centerY: { justifyContent: "center" },
  nodeWrap: { alignItems: "center", justifyContent: "center" },
  node: {
    width: NODE,
    height: NODE,
    borderRadius: NODE / 2,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 4,
    borderColor: colors.surface,
  },
  nodeDone: { backgroundColor: colors.secondary },
  nodeActive: { backgroundColor: colors.primary, ...shadow.glow },
  nodeOpen: { backgroundColor: colors.surfaceContainerLowest, ...shadow.raised },
  nodeAwaiting: { backgroundColor: colors.surfaceContainerLow },
  card: { backgroundColor: colors.surfaceContainerLowest, borderRadius: radius.lg, padding: 14, ...shadow.card },
  cardActive: { padding: 16, ...shadow.raised },
  cardAwaiting: { opacity: 0.75 },
  eyebrowRow: { flexDirection: "row", alignItems: "center", alignSelf: "stretch" },
  eyebrow: { textTransform: "uppercase", letterSpacing: 0.8 },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.full, marginTop: 10 },
  chipDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.outline },
  next: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 10 },
  progressRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 10 },
});
