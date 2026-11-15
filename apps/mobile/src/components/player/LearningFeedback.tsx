import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { api } from "@syllabyte/core/api/client";
import { learningFeedback, type AttentionReport, type FeedbackAction, type LearningCheckIn, type LearningContext } from "@syllabyte/core/learning";
import type { Confidence, Difficulty } from "@syllabyte/core/types";
import { colors, fonts, radius } from "@/theme/tokens";
import { Button } from "../Button";
import { T } from "../T";

const DIFFICULTY: readonly (readonly [Difficulty, string])[] = [["too_easy", "Easy"], ["just_right", "About right"], ["too_hard", "Difficult"]];
const ATTENTION: readonly (readonly [AttentionReport, string])[] = [["on_task", "On the learning material"], ["drifted", "My attention drifted"]];

/**
 * One optional question as a row of radio segments, styled like the checkpoint's "How sure are you?". Tapping the
 * selected option again clears it: either question may be left unanswered.
 */
function Segments<V extends string>({ id, label, options, value, onChange, disabled }: {
  id: string; label: string; options: readonly (readonly [V, string])[]; value: V | null; onChange: (v: V | null) => void; disabled: boolean;
}) {
  return (
    <View style={{ gap: 8 }}>
      <T color="#fff" nativeID={id}>{label}</T>
      <View style={styles.segments} accessibilityRole="radiogroup" accessibilityLabelledBy={id}>
        {options.map(([v, text]) => {
          const on = value === v;
          return (
            <Pressable
              key={v}
              accessibilityRole="radio"
              accessibilityLabel={text}
              accessibilityState={{ selected: on, disabled }}
              disabled={disabled}
              onPress={() => onChange(on ? null : v)}
              style={({ pressed }) => [styles.segment, on && styles.segmentOn, pressed && { opacity: 0.85 }, disabled && !on && { opacity: 0.5 }]}
            >
              <T variant="caption" color="#fff" style={{ fontFamily: fonts.semibold, textAlign: "center" }}>
                {text}
              </T>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** Student-initiated reflection; never interrupts playback or forces an engagement rating. */
export function LearningFeedback({ learning, responseId, correct, confidence, onContinue, onRewatch }: {
  learning: LearningContext; responseId: string; correct: boolean; confidence: Confidence | null;
  onContinue: () => void; onRewatch: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null);
  const [attention, setAttention] = useState<AttentionReport | null>(null);
  const [saved, setSaved] = useState<LearningCheckIn | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const initial = learningFeedback({ correct, confidence, hintUsed: false, difficulty: null, attention: null, replaySeconds: 0, replayFrom: 0 });
  async function save() {
    if (busy) return;
    setBusy(true); setSubmitted(true); setError(null);
    try { setSaved(await api.postLearningCheckIn({ ...learning, responseId, difficulty, attention })); }
    catch { setError("Your reflection could not be saved. Retry with the same answers, or continue without saving."); }
    finally { setBusy(false); }
  }
  async function finish(action: FeedbackAction) {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      if (saved) await api.recordLearningFeedbackAction(learning, saved.id, action);
      (action === "replay" ? onRewatch : onContinue)();
    } catch { setError("Your next step could not be saved. Try again, or continue without saving."); }
    finally { setBusy(false); }
  }
  return <View style={{ gap: 10, marginTop: 8 }}>
    {saved ? <T color="#e2e8f0" accessibilityLiveRegion="polite">{saved.feedback.message}</T> : initial.rule === "confidence_mismatch" ? <T color="#e2e8f0">{initial.message}</T> : null}
    {!open && !saved ? <Button label="Reflect on this part (optional)" kind="secondary" onPress={() => setOpen(true)} /> : null}
    {open && !saved ? <View style={{ gap: 14 }}>
      <Segments id="reflectFeel" label="How did this part feel?" options={DIFFICULTY} value={difficulty} onChange={setDifficulty} disabled={submitted || busy} />
      <Segments id="reflectAttention" label="Where was your attention just before the question?" options={ATTENTION} value={attention} onChange={setAttention} disabled={submitted || busy} />
      <Button label={busy ? "Saving…" : submitted ? "Retry saving reflection" : "Save reflection"} disabled={busy} onPress={() => { void save(); }} />
    </View> : null}
    {error ? <>
      <T color="#ffcdd2" accessibilityLiveRegion="polite">{error}</T>
      <Button label="Continue without saving" kind="secondary" onPress={onContinue} disabled={busy} />
    </> : null}
    <Button label="Continue video" icon="play-arrow" disabled={busy} onPress={() => { void finish("continue"); }} />
    {!correct || saved ? <Button label="Rewatch this part" icon="replay" kind="secondary" disabled={busy} onPress={() => { void finish("replay"); }} /> : null}
  </View>;
}

const styles = StyleSheet.create({
  segments: { flexDirection: "row", gap: 6 },
  segment: {
    flex: 1,
    minHeight: 44,
    paddingHorizontal: 6,
    paddingVertical: 8,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: "rgba(255,255,255,0.18)",
  },
  segmentOn: { borderColor: colors.primaryFixedDim, backgroundColor: colors.primary },
});
