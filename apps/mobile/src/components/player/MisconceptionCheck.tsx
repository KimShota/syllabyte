import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { api } from "@syllabyte/core/api/client";
import type { LearningContext } from "@syllabyte/core/learning";
import type { MisconceptionRequest } from "@syllabyte/core/types";
import { colors, fonts, radius } from "@/theme/tokens";
import { Button } from "../Button";
import { QuestionText } from "../QuestionText";
import { T } from "../T";

const LETTERS = "ABCDEFGH";
/** One question on the same idea; the answer is recorded once, then the right answer and why are shown. */
export function MisconceptionCheck({ learning, requestId, stem, options, topInset, savedAnswer, correctIndex, explanation, onDone }: {
  learning: LearningContext; requestId: string; stem: string; options: string[]; topInset: number;
  savedAnswer: MisconceptionRequest["follow_up"]; correctIndex: number; explanation: string; onDone: () => void;
}) {
  const [choice, setChoice] = useState<number | null>(savedAnswer?.choice ?? null);
  const [result, setResult] = useState<{ correct: boolean; correct_index: number; explanation: string } | null>(savedAnswer ? { correct: savedAnswer.correct, correct_index: correctIndex, explanation } : null);
  const [error, setError] = useState(false);
  function answer(i: number) {
    if (choice !== null && !error) return;
    setChoice(i);
    setError(false);
    api.answerMisconceptionCheck(learning, requestId, i).then(setResult, () => setError(true));
  }
  return (
    <View style={[StyleSheet.absoluteFill, styles.scrim]} accessibilityViewIsModal>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingTop: topInset }]}>
        <View style={styles.card}>
          <T variant="codeSm" color={colors.player.textMuted}>Quick check</T>
          <QuestionText color="#fff">{stem}</QuestionText>
          <View style={{ gap: 8 }} accessibilityRole="radiogroup">
            {options.map((o, i) => {
              const state = !result ? (choice === i ? "picked" : "idle") : i === result.correct_index ? "correct" : i === choice ? "wrong" : "idle";
              return (
                <Pressable key={i} accessibilityRole="radio" accessibilityState={{ selected: choice === i, disabled: !!result }} disabled={!!result}
                  onPress={() => answer(i)} style={[styles.option, styles[state]]}>
                  <T color="#fff" style={{ fontFamily: fonts.semibold }}>{LETTERS[i]}</T>
                  <QuestionText color="#fff">{o}</QuestionText>
                </Pressable>
              );
            })}
          </View>
          {error ? <T color={colors.errorSoft}>Your answer could not be saved. Tap an option to try again.</T> : null}
          {result ? (
            <View style={{ gap: 8 }} accessibilityLiveRegion="polite">
              <T variant="cardTitle" color={result.correct ? colors.secondaryContainer : colors.errorSoft} style={styles.title}>
                {result.correct ? "Right" : "Not quite"}
              </T>
              <QuestionText color="#e2e8f0">{result.explanation}</QuestionText>
              <Button label="Continue" icon="play-arrow" onPress={onDone} />
            </View>
          ) : (
            <Button label="Skip" kind="secondary" onPress={onDone} />
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: "rgba(0,0,0,0.82)" },
  scroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 16, paddingBottom: 32 },
  card: { gap: 14, padding: 20, borderRadius: radius.xl, backgroundColor: "#18181b", borderWidth: 1, borderColor: "rgba(152,243,224,0.45)" },
  title: { fontFamily: fonts.bold },
  option: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 48, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.md, borderWidth: 1.5 },
  idle: { borderColor: "rgba(255,255,255,0.18)" },
  picked: { borderColor: colors.primaryFixedDim, backgroundColor: colors.primary },
  correct: { borderColor: colors.secondaryContainer, backgroundColor: "rgba(0,107,93,0.45)" },
  wrong: { borderColor: colors.errorSoft, backgroundColor: "rgba(186,26,26,0.35)" },
});
