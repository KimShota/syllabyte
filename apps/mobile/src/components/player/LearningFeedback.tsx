import { useState } from "react";
import { View } from "react-native";
import { api } from "@syllabyte/core/api/client";
import { learningFeedback, type AttentionReport, type FeedbackAction, type LearningCheckIn, type LearningContext } from "@syllabyte/core/learning";
import type { Confidence, Difficulty } from "@syllabyte/core/types";
import { Button } from "../Button";
import { T } from "../T";

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
    {open && !saved ? <View style={{ gap: 10 }}>
      <T color="#fff">How did this part feel? You can leave either question unanswered.</T>
      {([
        ["too_easy", "Easy"], ["just_right", "About right"], ["too_hard", "Difficult"],
      ] as const).map(([value, label]) => <Button key={value} label={`${difficulty === value ? "✓ " : ""}${label}`} kind="secondary" disabled={submitted || busy} onPress={() => setDifficulty(difficulty === value ? null : value)} />)}
      <T color="#fff">Where was your attention just before the question?</T>
      {([["on_task", "On the learning material"], ["drifted", "My attention drifted"]] as const).map(([value, label]) => <Button key={value} label={`${attention === value ? "✓ " : ""}${label}`} kind="secondary" disabled={submitted || busy} onPress={() => setAttention(attention === value ? null : value)} />)}
      <T color="#cbd5e1">These answers are saved to your learning reflection. They do not change your course level.</T>
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
