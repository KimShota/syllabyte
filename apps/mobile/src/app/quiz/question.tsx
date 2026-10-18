import { useEffect, useRef, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@syllabyte/core/api/client";
import type { Choice } from "@syllabyte/core/types";
import { Button } from "@/components/Button";
import { IconButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { T } from "@/components/T";
import { useQuery } from "@/state/app";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const LETTERS = ["A", "B", "C", "D", "E"];

/**
 * One question at a time; no going back. The sitting is the baseline before any video ("week0", the default) or
 * the check before a lecture ("lecture-<n>"), plan D8. The adaptive check picks each question from the answers before it, so
 * the next one is only known once this one is locked in.
 */
export default function QuizQuestion() {
  const insets = useSafeAreaInsets();
  const sittingId = useLocalSearchParams<{ sitting?: string }>().sitting ?? "week0";
  const sitting = useQuery(() => api.getSitting(sittingId), [sittingId]);
  const item = sitting?.current?.item ?? null;
  const [itemId, setItemId] = useState<string | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [busy, setBusy] = useState(false);
  if (item && item.id !== itemId) {
    setItemId(item.id);
    setChoice(null);
    setBusy(false);
  }

  const shownAt = useRef(0);
  useEffect(() => {
    shownAt.current = Date.now();
  }, [itemId]);

  // the last answer is in: publish the levels and move on (also when coming back to a check already answered)
  const finishing = useRef(false);
  const over = !!sitting && !sitting.current;
  useEffect(() => {
    if (!over || finishing.current) return;
    finishing.current = true;
    void api
      .finishSitting(sittingId)
      .then(() => router.replace(sittingId === "week0" ? "/quiz/done" : { pathname: "/quiz/checked", params: { sitting: sittingId } }));
  }, [over, sittingId]);

  if (!sitting || !item) return <View style={styles.screen} />;
  const total = sitting.total;
  const index = sitting.answered;
  const last = index + 1 >= total;

  function confirm() {
    if (choice === null || !item || busy) return;
    setBusy(true);
    api.answerSitting(sittingId, item.id, choice, Date.now() - shownAt.current).catch(() => setBusy(false));
  }

  function exit() {
    Alert.alert("Leave the check?", "Your answers so far are kept. You can finish it later.", [
      { text: "Keep going", style: "cancel" },
      { text: "Leave", style: "destructive", onPress: () => (router.canGoBack() ? router.back() : router.replace("/")) },
    ]);
  }

  return (
    <View style={[styles.screen, { paddingBottom: insets.bottom + 16 }]}>
      <View style={[styles.header, { paddingTop: insets.top }, shadow.card]}>
        <View style={styles.headerBar}>
          <View>
            <T variant="eyebrow" color={colors.onSurfaceVariant}>
              {sitting.lecture_n ? `Before Lecture ${sitting.lecture_n}` : "SyllaByte Assessment"}
            </T>
            <T variant="bodySemibold">{sitting.lecture_n ? "Lecture check" : "Active Quiz Session"}</T>
          </View>
          {/* the baseline can't be left (the root layout sends a student who backs out straight back to it) */}
          {sittingId === "week0" ? null : <IconButton icon="close" label="Exit assessment" onPress={exit} />}
        </View>
      </View>

      <View style={styles.progress}>
        <T variant="codeSm" color={colors.primary} style={{ fontFamily: fonts.monoMedium, alignSelf: "flex-end", letterSpacing: 0 }}>
          Question {String(index + 1).padStart(2, "0")} of {total}
        </T>
        <View
          style={styles.segments}
          accessibilityRole="progressbar"
          accessibilityLabel="Questions answered"
          accessibilityValue={{ min: 0, max: total, now: index }}
        >
          {Array.from({ length: total }, (_, i) => (
            <View
              key={i}
              style={[styles.seg, { backgroundColor: i < index ? colors.primary : i === index ? colors.primaryDeep : colors.surfaceContainerHighest }]}
            />
          ))}
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.stemCard}>
          <T variant="cardTitle" style={{ letterSpacing: -0.2 }} accessibilityRole="header">
            {item.stem}
          </T>
        </View>

        <View style={styles.options} accessibilityRole="radiogroup">
          {item.options.map((opt, i) => (
            <Option key={i} letter={LETTERS[i]} label={opt} selected={choice === i} onPress={() => setChoice(i)} />
          ))}
          {item.allows_not_sure ? <NotSure selected={choice === "not_sure"} onPress={() => setChoice("not_sure")} /> : null}
        </View>
      </ScrollView>

      <Button
        label={last ? "Confirm & Finish" : "Confirm & Next"}
        trailingIcon="arrow-forward"
        height={56}
        disabled={choice === null || busy}
        onPress={confirm}
        style={{ marginHorizontal: 16, backgroundColor: choice === null ? colors.primary : colors.primaryDeep }}
      />
    </View>
  );
}

function Option({ letter, label, selected, onPress }: { letter: string; label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      accessibilityLabel={`${letter}. ${label}`}
      onPress={onPress}
      style={({ pressed }) => [styles.option, selected && styles.optionSelected, pressed && !selected && { backgroundColor: colors.surfaceContainer }]}
    >
      <View style={[styles.letter, selected && { backgroundColor: colors.primaryDeep }]}>
        <T variant="codeSm" color={selected ? colors.onPrimary : colors.onSurfaceVariant} style={{ fontFamily: fonts.monoSemibold }}>
          {letter}
        </T>
      </View>
      <T variant="bodySemibold" style={{ flex: 1 }}>
        {label}
      </T>
      <View style={[styles.tick, selected && { backgroundColor: colors.primaryDeep }]}>
        {selected ? <Icon name="check" size={16} color={colors.onPrimary} /> : null}
      </View>
    </Pressable>
  );
}

function NotSure({ selected, onPress }: { selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      accessibilityLabel="Not sure yet. Marks this for a recap video"
      onPress={onPress}
      style={({ pressed }) => [styles.notSure, selected && styles.notSureSelected, pressed && { backgroundColor: colors.surfaceContainer }]}
    >
      <View style={styles.notSureIcon}>
        <Icon name="help-outline" size={16} color={selected ? colors.primary : colors.onSurfaceVariant} />
      </View>
      <View style={{ flex: 1 }}>
        <T variant="bodySemibold" color={selected ? colors.onSurface : colors.onSurfaceVariant}>
          Not sure yet
        </T>
        <T variant="caption" color={colors.outline} style={{ fontSize: 12, lineHeight: 16 }}>
          Marks for customized recap video sequence
        </T>
      </View>
      <View style={[styles.tick, selected && { backgroundColor: colors.primaryDeep }]}>
        {selected ? <Icon name="check" size={16} color={colors.onPrimary} /> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  header: { backgroundColor: colors.surface },
  headerBar: { height: 56, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  progress: { paddingHorizontal: 16, paddingTop: 16, gap: 6 },
  segments: { flexDirection: "row", gap: 4 },
  seg: { flex: 1, height: 6, borderRadius: 3 },
  body: { padding: 16, gap: 24, flexGrow: 1, justifyContent: "center" },
  stemCard: { backgroundColor: colors.surfaceContainerLowest, borderRadius: radius.xl, padding: 20, ...shadow.card },
  options: { gap: 10 },
  option: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    padding: 16,
    borderRadius: radius.xl,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1.5,
    borderColor: "transparent",
    ...shadow.card,
  },
  optionSelected: { backgroundColor: "rgba(229,222,255,0.4)", borderColor: "rgba(67,30,190,0.35)" },
  letter: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.surfaceContainerHigh, alignItems: "center", justifyContent: "center" },
  tick: { width: 24, height: 24, borderRadius: 12, backgroundColor: colors.surfaceContainerHighest, alignItems: "center", justifyContent: "center", marginLeft: 8 },
  notSure: {
    marginTop: 4,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 14,
    borderRadius: radius.xl,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1.5,
    borderStyle: "dashed",
    borderColor: colors.outlineVariant,
  },
  notSureSelected: { borderColor: colors.primary, backgroundColor: colors.primaryTint },
  notSureIcon: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.surfaceContainerHigh, alignItems: "center", justifyContent: "center" },
});
