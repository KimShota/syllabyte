import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Header, ProfileButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { Spin } from "@/components/Motion";
import { ProgressBar } from "@/components/ProgressBar";
import { T } from "@/components/T";
import { UploadSheet } from "@/components/UploadSheet";
import { COURSE, OTHER_COURSES } from "@/data/course";
import { courseProgress } from "@/data/selectors";
import { useStore } from "@/state/store";
import { colors, fonts, radius, shadow, space } from "@/theme/tokens";

/** Home: the enrolled courses with their progress. */
export default function Home() {
  const { state } = useStore();
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

  if (!state.onboarded) return <Redirect href="/welcome" />;

  const main = courseProgress(COURSE, state.watched);
  const courses = [
    { id: COURSE.id, name: COURSE.name, progress: main.fraction, analyzing: undefined as number | undefined },
    ...OTHER_COURSES.map((c) => ({ id: c.id, name: c.name, progress: c.progress, analyzing: c.analyzing?.progress })),
  ];

  return (
    <View style={styles.screen}>
      <Header
        bordered
        left={
          <View style={styles.brand}>
            <View style={styles.logo}>
              <Icon name="auto-stories" size={22} color={colors.onPrimary} />
            </View>
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
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Upload course"
            onPress={() => setUploadOpen(true)}
            style={({ pressed }) => [styles.uploadBtn, pressed && { backgroundColor: colors.primaryPressed }]}
          >
            <Icon name="add" size={18} color={colors.onPrimary} />
            <T variant="caption" color={colors.onPrimary} style={{ fontFamily: fonts.semibold }}>
              Upload Course
            </T>
          </Pressable>
        </View>

        <View style={styles.list}>
          {courses.map((c) => (
            <CourseCard
              key={c.id}
              name={c.name}
              progress={c.progress}
              analyzing={c.analyzing}
              onPress={() => router.push({ pathname: "/course/[courseId]", params: { courseId: c.id } })}
            />
          ))}
          <Pressable
            accessibilityRole="button"
            onPress={() => setUploadOpen(true)}
            style={({ pressed }) => [styles.another, pressed && { backgroundColor: colors.surfaceContainer }]}
          >
            <Icon name="upload-file" size={20} color={colors.primary} />
            <T variant="bodySemibold" color={colors.primary} style={{ fontSize: 14 }}>
              + Upload Another Course
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
  logo: { width: 40, height: 40, borderRadius: radius.lg, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  content: { paddingHorizontal: space.gutter, paddingTop: 24 },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  uploadBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: radius.lg,
    backgroundColor: colors.primary,
    minHeight: 44,
  },
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
  cardTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  cardName: { flexDirection: "row", alignItems: "center", gap: 8, flex: 1 },
  analyzingChip: { backgroundColor: colors.secondaryContainer, borderRadius: radius.full, paddingHorizontal: 8, paddingVertical: 2 },
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
