import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { BackButton, Header, ProfileButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { Bob, PulseAura } from "@/components/Motion";
import { ProgressBar, SegmentBar } from "@/components/ProgressBar";
import { Serpentine, type SerpentineRow, type SpineSegment } from "@/components/Serpentine";
import { T } from "@/components/T";
import { NodePreviewSheet } from "@/components/NodePreviewSheet";
import { COURSE, KUS } from "@/data/course";
import { findLecture, kuMinutes, kuStatuses, lectureProgress, sectionSegments } from "@/data/selectors";
import type { Ku, KuStatus } from "@/data/types";
import { useStore } from "@/state/store";
import { colors, fonts, radius, shadow, space } from "@/theme/tokens";

const NODE = 56;
const NEXT_NODE = 64;
/** horizontal node positions, from the bottom of a section up */
const X_PATTERN = [0.36, 0.66, 0.5, 0.3, 0.68, 0.48];

/** Lecture roadmap: the lecture's KUs, section by section, climbing from the first. */
export default function LectureRoadmap() {
  const { n } = useLocalSearchParams<{ courseId: string; n: string }>();
  const { state } = useStore();
  const insets = useSafeAreaInsets();
  const [preview, setPreview] = useState<Ku | null>(null);

  const lecture = findLecture(Number(n));
  if (!lecture) return null;
  const statuses = kuStatuses(lecture, state.watched);
  const progress = lectureProgress(lecture, state.watched);
  const pct = progress.total ? progress.done / progress.total : 0;

  return (
    <View style={styles.screen}>
      <Header left={<BackButton />} right={<ProfileButton />} />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 40 }]}>
        <View style={styles.overview}>
          <T variant="codeSm" color={colors.primary} style={{ fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 }}>
            {COURSE.roadmapEyebrow}
          </T>
          <T variant="cardTitle" style={{ marginTop: 2, letterSpacing: -0.2 }} accessibilityRole="header">
            Lecture {lecture.n}: {lecture.title}
          </T>
          <View style={styles.pace}>
            <View style={{ flex: 1 }}>
              <T variant="codeSm" color={colors.onSurfaceVariant} style={{ fontFamily: fonts.monoMedium }}>
                TOTAL PACE
              </T>
              <T variant="bodySemibold">
                {progress.done} of {progress.total} topics watched ({Math.round(pct * 100)}%)
              </T>
            </View>
            <ProgressBar value={pct} height={8} color={colors.secondary} track={colors.outlineVariant} style={{ width: 64 }} />
          </View>
        </View>

        {[...lecture.sections].reverse().map((section) => {
          const segs = sectionSegments(section.kuIds, statuses);
          const complete = segs.every((s) => s === "done");
          const started = section.kuIds.some((id) => statuses[id] === "watched" || statuses[id] === "next");
          const rows = buildRows(section.kuIds, statuses, setPreview);
          const segments: SpineSegment[] = rows.slice(0, -1).map((_, i) => {
            const upper = statuses[rows[i].key];
            const lower = statuses[rows[i + 1].key];
            const done = upper === "watched" && lower === "watched";
            return { color: done ? colors.secondary : colors.outlineVariant, dashed: true, width: 4 };
          });
          return (
            <View key={section.id} style={styles.section}>
              <View style={styles.sectionHead}>
                <View style={styles.sectionTitle}>
                  <View style={[styles.sectionDot, { backgroundColor: complete ? colors.secondary : started ? colors.primary : colors.outline }]} />
                  <T variant="bodySemibold">{section.title}</T>
                </View>
                <SegmentBar segments={segs} tone={complete ? "secondary" : "primary"} />
              </View>
              <View style={{ paddingVertical: 16 }}>
                <Serpentine rows={rows} segments={segments} />
              </View>
            </View>
          );
        })}
      </ScrollView>

      <NodePreviewSheet ku={preview} status={preview ? statuses[preview.id] : null} onClose={() => setPreview(null)} />
    </View>
  );
}

function buildRows(kuIds: string[], statuses: Record<string, KuStatus>, onPress: (ku: Ku) => void): SerpentineRow[] {
  // bottom-up: the section's first KU sits at the bottom
  return kuIds
    .map((id, i) => ({ id, x: X_PATTERN[i % X_PATTERN.length] }))
    .reverse()
    .map(({ id, x }) => {
      const status = statuses[id];
      const next = status === "next";
      const height = next ? 160 : 112;
      // START bubble (24) + its margin (8) above the next node
      const nodeY = next ? 8 + 32 + NEXT_NODE / 2 : 14 + NODE / 2;
      return {
        key: id,
        height,
        nodeX: x,
        nodeY,
        render: (width: number) => <KuNode ku={KUS[id]} status={status} centerX={x * width} onPress={() => onPress(KUS[id])} />,
      };
    });
}

const LABEL_W = 150;

function KuNode({ ku, status, centerX, onPress }: { ku: Ku; status: KuStatus; centerX: number; onPress: () => void }) {
  const next = status === "next";
  const size = next ? NEXT_NODE : NODE;
  const stateLabel = { watched: "watched", next: "up next", available: "available", drafting: "being made from slides" }[status];
  return (
    <View style={[styles.kuCol, { left: centerX - LABEL_W / 2, top: next ? 8 : 14 }]}>
      {next ? (
        <Bob>
          <View style={styles.bubble}>
            <View style={styles.bubbleDot} />
            <T variant="codeSm" color="#fff" style={{ fontFamily: fonts.monoSemibold, letterSpacing: 1 }}>
              START
            </T>
            <View style={styles.bubbleTail} />
          </View>
        </Bob>
      ) : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${ku.shortTitle}, ${stateLabel}`}
        onPress={onPress}
        style={({ pressed }) => [{ alignItems: "center", justifyContent: "center", width: size, height: size }, pressed && { transform: [{ scale: 0.95 }] }]}
      >
        {next ? <PulseAura size={size + 20} color={colors.primaryFixed} /> : null}
        <View
          style={[
            styles.node,
            { width: size, height: size, borderRadius: size / 2 },
            status === "watched" && styles.nodeWatched,
            status === "next" && styles.nodeNext,
            status === "available" && styles.nodeAvailable,
            status === "drafting" && styles.nodeDrafting,
          ]}
        >
          <Icon
            name={status === "watched" ? "check" : status === "drafting" ? "hourglass-empty" : "play-arrow"}
            size={next ? 32 : status === "drafting" ? 22 : 26}
            color={status === "watched" || next ? colors.onPrimary : status === "drafting" ? colors.outline : colors.primary}
          />
        </View>
      </Pressable>
      <View style={[styles.label, next && styles.labelNext, status === "drafting" && styles.labelDrafting]}>
        {status === "drafting" ? (
          <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 11, lineHeight: 14, textAlign: "center" }}>
            Drafting from slides
          </T>
        ) : (
          <T
            variant={next ? "bodySemibold" : "codeSm"}
            color={next ? colors.primary : colors.onSurface}
            numberOfLines={2}
            style={[{ textAlign: "center" }, next ? { fontSize: 13, lineHeight: 17, fontFamily: fonts.bold } : { fontFamily: fonts.medium, letterSpacing: 0 }]}
          >
            {ku.shortTitle}
          </T>
        )}
        {next ? (
          <T variant="codeSm" color={colors.onSurfaceVariant} style={{ fontSize: 10, textAlign: "center", textTransform: "uppercase" }}>
            {kuMinutes(ku)} min
          </T>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: space.gutter, paddingTop: 8 },
  overview: { backgroundColor: colors.surfaceContainerLowest, borderRadius: radius.lg, padding: 16, marginBottom: 16, ...shadow.card },
  pace: { marginTop: 16, flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: colors.surfaceContainerLow, borderRadius: radius.md, padding: 10 },
  section: { marginBottom: 24 },
  sectionHead: { backgroundColor: colors.surfaceContainerLowest, borderRadius: radius.lg, padding: 16, ...shadow.card, zIndex: 2 },
  sectionTitle: { flexDirection: "row", alignItems: "center", gap: 8 },
  sectionDot: { width: 10, height: 10, borderRadius: 5 },
  kuCol: { position: "absolute", width: LABEL_W, alignItems: "center" },
  node: { alignItems: "center", justifyContent: "center" },
  nodeWatched: { backgroundColor: colors.secondary, ...shadow.card },
  nodeNext: { backgroundColor: colors.primaryDeep, borderWidth: 4, borderColor: colors.primaryFixed, ...shadow.glow },
  nodeAvailable: { backgroundColor: colors.surfaceContainerLowest, borderWidth: 2, borderColor: colors.primary, ...shadow.card },
  nodeDrafting: { backgroundColor: colors.surfaceContainerLow, borderWidth: 2, borderStyle: "dashed", borderColor: colors.outline },
  label: {
    marginTop: 6,
    maxWidth: LABEL_W,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.sm,
    backgroundColor: "rgba(255,255,255,0.92)",
    ...shadow.card,
  },
  labelNext: { marginTop: 10, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.md, backgroundColor: colors.surfaceContainerLowest },
  labelDrafting: { backgroundColor: "rgba(232,231,243,0.85)" },
  bubble: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.inverseSurface,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: radius.full,
    marginBottom: 8,
    ...shadow.float,
  },
  bubbleDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.secondaryContainer },
  bubbleTail: { position: "absolute", bottom: -4, left: "50%", marginLeft: -4, width: 8, height: 8, backgroundColor: colors.inverseSurface, transform: [{ rotate: "45deg" }] },
});
