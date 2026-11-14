import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { DriftAnswer, LearningPrompt, PromptAction } from "@syllabyte/core/learning";
import { formatTime } from "@/data/selectors";
import { colors, fonts, radius } from "@/theme/tokens";
import { Button } from "../Button";
import { Icon } from "../Icon";
import { T } from "../T";

const ATTENTION: { value: DriftAnswer; label: string }[] = [
  { value: "on_task", label: "On the videos" },
  { value: "drifted", label: "On something else" },
  { value: "familiar", label: "These feel familiar" },
  { value: "searching", label: "Looking for a specific topic" },
];

/**
 * A prompt the app offers by itself at a decision point, over the paused video (plan/engagement-feedback-implementation-
 * plan.md, "Automatic feedback"). A drift check states what happened and asks where the student's attention was; a drift
 * or a sense of familiarity leads to recalling the last video they really watched, then comparing with its key points
 * (retrieval between segments: Szpunar et al. 2013). A welcome back asks for the last idea before where they stopped.
 * Every step can be skipped; nothing here judges the student.
 */
export function EngagementPrompt({ prompt, onAnswer, onDone }: {
  prompt: LearningPrompt;
  onAnswer: (answer: DriftAnswer) => void;
  onDone: (action: PromptAction) => void;
}) {
  const insets = useSafeAreaInsets();
  const recall = prompt.recall;
  const [step, setStep] = useState<"probe" | "recall" | "revealed">(prompt.kind === "drift_check" ? "probe" : "recall");
  const [answer, setAnswer] = useState<DriftAnswer | null>(null);

  function choose(a: DriftAnswer) {
    setAnswer(a);
    onAnswer(a);
    if ((a === "drifted" || a === "familiar") && recall) setStep("recall");
    // a drift with nothing to recall (no video really watched yet) still gets a choice
    else if (a === "drifted") setStep("revealed");
    else onDone("continue");
  }

  const welcome = prompt.kind === "welcome_back";
  return (
    <View style={[StyleSheet.absoluteFill, styles.scrim]} accessibilityViewIsModal>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingTop: insets.top + 72 }]}>
        <View style={styles.card}>
          <View style={styles.eyebrow}>
            <Icon name="pause-circle-filled" size={14} color={colors.secondaryContainer} />
            <T variant="codeSm" color={colors.secondaryContainer} style={styles.eyebrowText}>
              Video paused · {welcome ? "Welcome back" : "Check-in"}
            </T>
          </View>
          <T color="#e2e8f0" accessibilityLiveRegion="polite">{prompt.observation}</T>

          {step === "probe" ? (
            <>
              <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header" nativeID="driftQuestion">
                Just before this, where was your attention?
              </T>
              <View style={{ gap: 8 }} accessibilityRole="radiogroup" accessibilityLabelledBy="driftQuestion">
                {ATTENTION.map((o) => (
                  <Pressable
                    key={o.value}
                    accessibilityRole="radio"
                    accessibilityLabel={o.label}
                    accessibilityState={{ selected: answer === o.value }}
                    onPress={() => choose(o.value)}
                    style={({ pressed }) => [styles.option, answer === o.value && styles.optionOn, pressed && { opacity: 0.85 }]}
                  >
                    <T color="#fff" style={{ fontFamily: fonts.semibold }}>{o.label}</T>
                  </Pressable>
                ))}
              </View>
              <Button label="Not now" kind="secondary" onPress={() => onDone("continue")} />
            </>
          ) : recall ? (
            <>
              <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header">
                {welcome ? "Before you continue: what was the last idea?" : `Without looking back: what was the main idea of “${recall.title}”?`}
              </T>
              {step === "recall" ? (
                <>
                  <T color={colors.player.textMuted}>{"Think of your answer first, then compare it with the video's key points."}</T>
                  <Button label={welcome ? "Show it" : "Show the key points"} onPress={() => setStep("revealed")} />
                  <Button label="Skip" kind="secondary" onPress={() => onDone("continue")} />
                </>
              ) : (
                <>
                  <View style={styles.points} accessibilityLiveRegion="polite">
                    {recall.points.map((p) => (
                      <T key={p} color="#fff">• {p}</T>
                    ))}
                  </View>
                  <T color={colors.player.textMuted}>Did your answer match?</T>
                  {welcome ? (
                    <>
                      <Button label="Continue" icon="play-arrow" onPress={() => onDone("continue")} />
                      <Button label={`Replay from ${formatTime(recall.replayFrom)}`} icon="replay" kind="secondary" onPress={() => onDone("replay")} />
                    </>
                  ) : (
                    <>
                      <Button label="Continue" icon="play-arrow" onPress={() => onDone("continue")} />
                      <Button label={`Rewatch “${recall.title}”`} icon="replay" kind="secondary" onPress={() => onDone("rewatch")} />
                      {answer === "drifted" ? <Button label="Take a break (keep my place)" kind="secondary" onPress={() => onDone("pause")} /> : null}
                    </>
                  )}
                </>
              )}
            </>
          ) : (
            <>
              <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header">
                What would help now?
              </T>
              <Button label="Continue" icon="play-arrow" onPress={() => onDone("continue")} />
              <Button label="Take a break (keep my place)" kind="secondary" onPress={() => onDone("pause")} />
            </>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: "rgba(0,0,0,0.72)" },
  scroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 16, paddingBottom: 32 },
  card: { gap: 14, padding: 20, borderRadius: radius.xl, backgroundColor: "#18181b", borderWidth: 1, borderColor: "rgba(91,63,214,0.55)" },
  eyebrow: { flexDirection: "row", alignItems: "center", gap: 6 },
  eyebrowText: { fontSize: 11, fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 },
  title: { fontFamily: fonts.bold },
  option: { minHeight: 48, justifyContent: "center", paddingHorizontal: 16, borderRadius: radius.md, borderWidth: 1.5, borderColor: "rgba(255,255,255,0.18)" },
  optionOn: { borderColor: colors.primaryFixedDim, backgroundColor: colors.primary },
  points: { gap: 8, padding: 14, borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.06)" },
});
