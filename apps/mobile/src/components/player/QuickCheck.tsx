import type { LearningContext } from "@syllabyte/core/learning";
import { uid } from "@syllabyte/core/util";
import { LearningFeedback } from "./LearningFeedback";
import { QuestionText } from "../QuestionText";
import { questionLabel } from "@syllabyte/core/questionContent";
import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { api } from "@syllabyte/core/api/client";
import type { Confidence, VariantView } from "@syllabyte/core/types";
import { Button } from "../Button";
import { Icon } from "../Icon";
import { T } from "../T";
import { colors, fonts, radius } from "@/theme/tokens";

const P = colors.player;
const LETTERS = ["A", "B", "C", "D", "E"];
const CONF: { value: Confidence; label: string }[] = [
  { value: "guess", label: "Guessing" },
  { value: "pretty", label: "Pretty sure" },
  { value: "certain", label: "Certain" },
];

/**
 * The video's one quick check, over the paused video (plan Q4, Q10, Q29). Pick an answer, then "How sure?"; the
 * result appears by itself once both are set. It can't be skipped and has no "Not sure yet" (the "Guessing" rating
 * carries that). There is no hint.
 */
export function QuickCheck({
  variant,
  learning,
  topInset,
  onAnswered,
  onContinue,
  onRewatch,
}: {
  variant: VariantView;
  learning: LearningContext;
  /** room for the player's top bar */
  topInset: number;
  onAnswered: () => void;
  onContinue: () => void;
  onRewatch: () => void;
}) {
  const item = variant.checkpoint_item;
  const [choice, setChoice] = useState<number | null>(null);
  const [conf, setConf] = useState<Confidence | null>(null);
  const [result, setResult] = useState<{ correct: boolean; queued: boolean; responseId: string } | null>(null);
  const shownAt = useRef(0);
  const sent = useRef(false);
  const [attemptId] = useState(() => uid("attempt"));
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState(false);
  const latency = useRef<number | null>(null);
  const locked = conf !== null;

  useEffect(() => {
    shownAt.current = Date.now();
    AccessibilityInfo.announceForAccessibility("Video paused. Quick check.");
  }, []);

  useEffect(() => {
    if (choice === null || conf === null || sent.current) return;
    sent.current = true;
    setError(false);
    latency.current ??= Date.now() - shownAt.current;
    void api
      .postCheckpointAnswer({ attemptId, learning, videoId: variant.video.id, choice, confidence: conf, hintUsed: false, latencyMs: latency.current })
      .then((r) => {
        setResult({ correct: r.correct, queued: r.queuedForTomorrow, responseId: r.responseId });
        onAnswered();
      }).catch(() => { setError(true); });
  }, [choice, conf, variant.video.id, onAnswered, learning, attemptId, retry]);

  const revealed = result !== null;

  return (
    <View style={[StyleSheet.absoluteFill, styles.scrim]}>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingTop: topInset }]} keyboardShouldPersistTaps="handled">
        <View style={styles.card} accessibilityViewIsModal>
          <View style={styles.eyebrow}>
            <Icon name="pause-circle-filled" size={14} color={colors.secondaryContainer} />
            <T variant="codeSm" color={colors.secondaryContainer} style={styles.eyebrowText}>
              Video paused · Quick check
            </T>
          </View>
          <QuestionText variant="cardTitle" accessibilityRole="header" color="#fff" textStyle={{ fontFamily: fonts.bold, lineHeight: 28 }}>{item.stem}</QuestionText>

          <View style={styles.options} accessibilityRole="radiogroup">
            {item.options.map((o, i) => {
              const state = !revealed ? (choice === i ? "selected" : "idle") : i === item.correct_index ? "correct" : choice === i ? "wrong" : "dim";
              return (
                <Pressable
                  key={i}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: choice === i, disabled: revealed || locked }}
                  accessibilityLabel={`${LETTERS[i]}. ${questionLabel(o)}${state === "correct" ? ", right answer" : state === "wrong" ? ", your answer, not right" : ""}`}
                  disabled={revealed || locked}
                  onPress={() => setChoice(i)}
                  style={({ pressed }) => [styles.option, styles[state], pressed && { opacity: 0.85 }]}
                >
                  <View style={[styles.letter, (state === "selected" || state === "correct" || state === "wrong") && styles.letterOn]}>
                    {state === "correct" ? (
                      <Icon name="check" size={16} color="#fff" />
                    ) : state === "wrong" ? (
                      <Icon name="close" size={16} color="#fff" />
                    ) : (
                      <T variant="codeSm" color="#fff" style={{ fontFamily: fonts.monoSemibold }}>
                        {LETTERS[i]}
                      </T>
                    )}
                  </View>
                  <QuestionText color={state === "dim" ? "rgba(255,255,255,0.5)" : "#fff"} style={{ flex: 1 }} textStyle={{ fontSize: 15, lineHeight: 21 }}>{o}</QuestionText>
                </Pressable>
              );
            })}
          </View>

          {choice !== null && !revealed ? (
            <View style={{ gap: 8 }}>
              <T variant="bodySemibold" color="#fff" nativeID="howSure">
                How sure are you in that answer?
              </T>
              <View style={styles.segments} accessibilityRole="radiogroup" accessibilityLabelledBy="howSure">
                {CONF.map((c) => (
                  <Pressable
                    key={c.value}
                    accessibilityRole="radio"
                    disabled={locked}
                    accessibilityState={{ selected: conf === c.value, disabled: locked }}
                    onPress={() => setConf(c.value)}
                    style={[styles.segment, conf === c.value && styles.segmentOn]}
                  >
                    <T variant="caption" color="#fff" style={{ fontFamily: fonts.semibold }}>
                      {c.label}
                    </T>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}

          {error ? <View style={{ gap: 8 }}>
            <T color={colors.errorSoft} accessibilityLiveRegion="polite">Your answer could not be saved. Retry to continue; your answer will only be counted once.</T>
            <Button label="Retry saving answer" onPress={() => { sent.current = false; setRetry((r) => r + 1); }} />
          </View> : locked && !revealed ? <T color={P.textMuted}>Saving your answer…</T> : null}

          {revealed ? (
            <View style={{ gap: 8 }} accessibilityLiveRegion="polite">
              <T variant="cardTitle" color={result.correct ? colors.secondaryContainer : colors.errorSoft} style={{ fontFamily: fonts.bold }}>
                {result.correct ? "Right" : "Not quite"}
              </T>
              {conf ? (
                <T variant="codeSm" color={P.textMuted}>
                  You said: {CONF.find((c) => c.value === conf)?.label}
                </T>
              ) : null}
              {!result.correct ? (
                <View style={{ gap: 4 }}>
                  <T color={P.textMuted}>Right answer:</T>
                  <QuestionText color="#e2e8f0">{item.options[item.correct_index]}</QuestionText>
                </View>
              ) : null}
              <QuestionText color="#e2e8f0">{item.explanation}</QuestionText>
              {result.queued ? (
                <View style={styles.queued}>
                  <T variant="caption" color={colors.onSecondaryContainer} style={{ fontSize: 14, lineHeight: 20 }}>
                    {"You got it, but you said you were guessing. We'll check this again tomorrow."}
                  </T>
                </View>
              ) : null}
              <LearningFeedback learning={learning} responseId={result.responseId} correct={result.correct} confidence={conf} onContinue={onContinue} onRewatch={onRewatch} />
            </View>
          ) : (
            <T variant="caption" color={P.textMuted} style={{ fontSize: 12 }}>
              Answer to keep watching. Not graded.
            </T>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: "rgba(0,0,0,0.72)" },
  scroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 16, paddingBottom: 32 },
  card: {
    gap: 16,
    padding: 20,
    borderRadius: radius.xl,
    backgroundColor: "#18181b",
    borderWidth: 1,
    borderColor: "rgba(91,63,214,0.55)",
  },
  eyebrow: { flexDirection: "row", alignItems: "center", gap: 6 },
  eyebrowText: { fontSize: 11, fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 },
  options: { gap: 10 },
  option: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 14,
    minHeight: 56,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: "rgba(255,255,255,0.14)",
    backgroundColor: "rgba(255,255,255,0.06)",
  },
  idle: {},
  selected: { borderColor: colors.primaryFixedDim, backgroundColor: "rgba(91,63,214,0.28)" },
  correct: { borderColor: colors.secondaryContainer, backgroundColor: "rgba(0,107,93,0.35)" },
  wrong: { borderColor: colors.errorSoft, backgroundColor: "rgba(186,26,26,0.25)" },
  dim: { opacity: 0.6 },
  letter: { width: 30, height: 30, borderRadius: 15, backgroundColor: "rgba(255,255,255,0.12)", alignItems: "center", justifyContent: "center" },
  letterOn: { backgroundColor: "rgba(255,255,255,0.25)" },
  segments: { flexDirection: "row", gap: 6 },
  segment: {
    flex: 1,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: "rgba(255,255,255,0.18)",
  },
  segmentOn: { borderColor: colors.primaryFixedDim, backgroundColor: colors.primary },
  queued: { padding: 12, borderRadius: radius.md, backgroundColor: colors.secondaryContainer },
});
