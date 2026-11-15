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
  { value: "familiar", label: "I already know what those videos cover" },
  { value: "searching", label: "I'm looking for a specific video" },
];

type Recall = NonNullable<LearningPrompt["recall"]>;
type Step = "probe" | "recall" | "revealed" | "break" | "check" | "checked" | "pick";

/**
 * A prompt the app offers by itself at a decision point, over the paused video (plan/engagement-feedback-implementation-
 * plan.md, "Automatic feedback"). A drift check states what happened and asks where the student's attention was, and each
 * answer leads somewhere useful:
 *  - on something else: recall the last video really watched, then compare with its key points (retrieval between
 *    segments: Szpunar et al. 2013), then continue, rewatch it or take a break;
 *  - "I already know what those videos cover": check that against one of the skipped videos (feeling you know something
 *    is not knowing it: Yang et al. 2022), then skip ahead or watch it;
 *  - looking for a specific video: pick it from this feed and go straight there;
 *  - on the videos: carry on.
 * A welcome back asks for the last idea before where the student stopped. Every step can be skipped; nothing here judges
 * the student.
 */
export function EngagementPrompt({ prompt, feed, currentVideoId, onAnswer, onDone }: {
  prompt: LearningPrompt;
  /** the feed's videos, in order, for "I'm looking for a specific video" */
  feed: { videoId: string; title: string }[];
  currentVideoId: string | null;
  onAnswer: (answer: DriftAnswer) => void;
  onDone: (action: PromptAction, target?: string) => void;
}) {
  const insets = useSafeAreaInsets();
  const recall = prompt.recall;
  const skipped = prompt.skipped ?? null;
  const [step, setStep] = useState<Step>(prompt.kind === "drift_check" ? "probe" : "recall");

  function choose(a: DriftAnswer) {
    onAnswer(a);
    if (a === "drifted") setStep(recall ? "recall" : "break");
    else if (a === "familiar") {
      if (skipped) setStep("check");
      else if (recall) setStep("recall");
      else onDone("continue");
    } else if (a === "searching") setStep("pick");
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
              <Title nativeID="driftQuestion">Just before this, where was your attention?</Title>
              <View style={{ gap: 8 }} accessibilityRole="radiogroup" accessibilityLabelledBy="driftQuestion">
                {ATTENTION.map((o) => (
                  <Option key={o.value} label={o.label} role="radio" onPress={() => choose(o.value)} />
                ))}
              </View>
              <Button label="Not now" kind="secondary" onPress={() => onDone("continue")} />
            </>
          ) : step === "recall" || step === "revealed" ? (
            recall ? <RecallCheck recall={recall} welcome={welcome} revealed={step === "revealed"} onReveal={() => setStep("revealed")}
              onDone={onDone} offerBreak={prompt.kind === "drift_check"} /> : null
          ) : step === "break" ? (
            <>
              <Title>What would help now?</Title>
              <Button label="Continue" icon="play-arrow" onPress={() => onDone("continue")} />
              <Button label="Take a break (keep my place)" kind="secondary" onPress={() => onDone("pause")} />
            </>
          ) : (step === "check" || step === "checked") && skipped ? (
            <>
              <Title>{`Quick check on one you skipped: what is the main idea of “${skipped.title}”?`}</Title>
              {step === "check" ? (
                <>
                  <T color={colors.player.textMuted}>{"Think of your answer first, then compare it with the video's key points."}</T>
                  <Button label="Show the key points" onPress={() => setStep("checked")} />
                  <Button label="Skip" kind="secondary" onPress={() => onDone("continue")} />
                </>
              ) : (
                <>
                  <Points points={skipped.points} />
                  <T color={colors.player.textMuted}>Did your answer match?</T>
                  <Button label="Yes, skip ahead" icon="play-arrow" onPress={() => onDone("continue")} />
                  <Button label={`Not quite, watch “${skipped.title}”`} icon="replay" kind="secondary" onPress={() => onDone("watch", skipped.videoId)} />
                </>
              )}
            </>
          ) : step === "pick" ? (
            <>
              <Title nativeID="pickVideo">Which video are you looking for?</Title>
              <View style={{ gap: 8 }} accessibilityRole="radiogroup" accessibilityLabelledBy="pickVideo">
                {feed.map((v) => (
                  <Option
                    key={v.videoId}
                    label={v.videoId === currentVideoId ? `${v.title} (this one)` : v.title}
                    role="button"
                    onPress={() => onDone(v.videoId === currentVideoId ? "continue" : "jump", v.videoId)}
                  />
                ))}
              </View>
              <Button label="Keep browsing" kind="secondary" onPress={() => onDone("continue")} />
            </>
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

function Title({ children, nativeID }: { children: string; nativeID?: string }) {
  return (
    <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header" nativeID={nativeID}>
      {children}
    </T>
  );
}

function Option({ label, role, onPress }: { label: string; role: "radio" | "button"; onPress: () => void }) {
  return (
    <Pressable accessibilityRole={role} accessibilityLabel={label} onPress={onPress} style={({ pressed }) => [styles.option, pressed && styles.optionOn]}>
      <T color="#fff" style={{ fontFamily: fonts.semibold }}>{label}</T>
    </Pressable>
  );
}

function Points({ points }: { points: string[] }) {
  return (
    <View style={styles.points} accessibilityLiveRegion="polite">
      {points.map((p) => (
        <T key={p} color="#fff">• {p}</T>
      ))}
    </View>
  );
}

/** Recall, then compare with the key points: the last video really watched (drift), or up to where they stopped (welcome back). */
function RecallCheck({ recall, welcome, revealed, onReveal, onDone, offerBreak }: {
  recall: Recall; welcome: boolean; revealed: boolean; onReveal: () => void;
  onDone: (action: PromptAction, target?: string) => void; offerBreak: boolean;
}) {
  return (
    <>
      <Title>{welcome ? "Before you continue: what was the last idea?" : `Without looking back: what was the main idea of “${recall.title}”?`}</Title>
      {!revealed ? (
        <>
          <T color={colors.player.textMuted}>{"Think of your answer first, then compare it with the video's key points."}</T>
          <Button label={welcome ? "Show it" : "Show the key points"} onPress={onReveal} />
          <Button label="Skip" kind="secondary" onPress={() => onDone("continue")} />
        </>
      ) : (
        <>
          <Points points={recall.points} />
          <T color={colors.player.textMuted}>Did your answer match?</T>
          <Button label="Continue" icon="play-arrow" onPress={() => onDone("continue")} />
          {welcome ? (
            <Button label={`Replay from ${formatTime(recall.replayFrom)}`} icon="replay" kind="secondary" onPress={() => onDone("replay")} />
          ) : (
            <Button label={`Rewatch “${recall.title}”`} icon="replay" kind="secondary" onPress={() => onDone("rewatch")} />
          )}
          {offerBreak ? <Button label="Take a break (keep my place)" kind="secondary" onPress={() => onDone("pause")} /> : null}
        </>
      )}
    </>
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
