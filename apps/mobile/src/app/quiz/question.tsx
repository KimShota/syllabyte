import { useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { IconButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { T } from "@/components/T";
import { BASELINE_ITEMS } from "@/data/quizItems";
import type { Choice } from "@/data/types";
import { useStore } from "@/state/store";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const LETTERS = ["A", "B", "C", "D", "E"];

/** One question at a time; no going back. */
export default function QuizQuestion() {
  const insets = useSafeAreaInsets();
  const { dispatch } = useStore();
  const [index, setIndex] = useState(0);
  const [choice, setChoice] = useState<Choice | null>(null);
  const item = BASELINE_ITEMS[index];
  const total = BASELINE_ITEMS.length;

  function confirm() {
    if (choice === null) return;
    dispatch({ type: "answer", itemId: item.id, choice });
    if (index + 1 >= total) {
      router.replace("/quiz/done");
      return;
    }
    setIndex(index + 1);
    setChoice(null);
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
              SyllaByte Assessment
            </T>
            <T variant="bodySemibold">Active Quiz Session</T>
          </View>
          <IconButton icon="close" label="Exit assessment" onPress={exit} />
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
          {BASELINE_ITEMS.map((it, i) => (
            <View
              key={it.id}
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
        label={index + 1 >= total ? "Confirm & Finish" : "Confirm & Next"}
        trailingIcon="arrow-forward"
        height={56}
        disabled={choice === null}
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
