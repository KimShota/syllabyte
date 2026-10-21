import { ScrollView, StyleSheet, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { Glow } from "@/components/Glow";
import { Icon, type IconName } from "@/components/Icon";
import { T } from "@/components/T";
import { api } from "@syllabyte/core/api/client";
import { useQuery } from "@/state/app";
import { colors, radius, shadow } from "@/theme/tokens";
import { lectureNumber } from "@/data/course";

const RULES: { icon: IconName; tone: string; text: string }[] = [
  { icon: "arrow-forward", tone: colors.primary, text: "You can't go back to the previous question once you answer" },
  { icon: "help-outline", tone: colors.primary, text: "Choose “Not sure yet” if you don't know the answer" },
  { icon: "schedule", tone: colors.secondary, text: "It isn't timed, so take your time" },
  { icon: "public-off", tone: colors.secondary, text: "Don't search the internet; we won't grade you" },
  { icon: "auto-awesome", tone: colors.primary, text: "Results personalize your video lessons to maximize learning outcomes" },
];

/**
 * A check's intro: no grade, the rules. The baseline ("week0", the default) or the check before a lecture
 * ("lecture-<n>"); the questions come from the core's adaptive sittings.
 */
export default function QuizIntro() {
  const insets = useSafeAreaInsets();
  const id = useLocalSearchParams<{ sitting?: string }>().sitting ?? "week0";
  const sitting = useQuery(() => api.getSitting(id), [id]);
  const lecture = sitting?.lecture_n ?? null;
  const started = (sitting?.answered ?? 0) > 0;
  return (
    <View style={[styles.screen, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 16 }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={styles.badgeWrap}>
            <Glow size={150} color={colors.primaryFixedDim} opacity={0.7} />
            <View style={styles.badge}>
              <Icon name="psychology-alt" size={40} color={colors.primary} />
            </View>
          </View>
          <T variant="titleMobile" style={{ textAlign: "center", maxWidth: 280 }} accessibilityRole="header">
            {lecture ? `A quick check before Lecture ${lectureNumber(lecture)}` : "A quick check, no grade"}
          </T>
          {lecture ? (
            <T variant="body" color={colors.onSurfaceVariant} style={{ textAlign: "center", marginTop: 6, maxWidth: 300 }}>
              It tunes this lecture&apos;s videos to what you know now. No grade.
            </T>
          ) : null}
          <View style={styles.countChip}>
            <Icon name="quiz" size={18} color={colors.primary} />
            <T variant="bodySemibold" color={colors.primary}>
              Only {sitting?.total ?? "a few"} questions
            </T>
          </View>
        </View>

        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Icon name="rule" size={20} color={colors.primary} />
            <T variant="cardTitle">Rules</T>
          </View>
          {RULES.map((r) => (
            <View key={r.text} style={styles.rule}>
              <View style={{ marginTop: 1 }}>
                <Icon name={r.icon} size={20} color={r.tone} />
              </View>
              <T variant="body" color={colors.onSurfaceVariant} style={{ flex: 1 }}>
                {r.text}
              </T>
            </View>
          ))}
        </View>
      </ScrollView>
      <Button
        label={started ? `Continue (${sitting!.answered} of ${sitting!.total} done)` : "Start"}
        trailingIcon="arrow-forward"
        disabled={!sitting}
        onPress={() => router.replace({ pathname: "/quiz/question", params: { sitting: id } })}
        style={{ marginHorizontal: 20 }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: 20, flexGrow: 1, justifyContent: "space-between", gap: 32, paddingBottom: 24 },
  header: { alignItems: "center", paddingTop: 16 },
  badgeWrap: { alignItems: "center", justifyContent: "center", marginBottom: 20 },
  badge: {
    width: 80,
    height: 80,
    borderRadius: radius.xl,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.surfaceContainerHighest,
    alignItems: "center",
    justifyContent: "center",
    ...shadow.card,
  },
  countChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 12,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: radius.full,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.surfaceContainerHighest,
  },
  card: {
    padding: 20,
    borderRadius: radius.xl,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: colors.surfaceContainerHighest,
    gap: 16,
    ...shadow.card,
  },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 8, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: colors.surfaceContainerHighest },
  rule: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
});
