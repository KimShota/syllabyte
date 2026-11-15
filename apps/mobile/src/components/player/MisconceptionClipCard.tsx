import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useEventListener } from "expo";
import { useVideoPlayer, VideoView, type VideoPlayer } from "expo-video";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@syllabyte/core/api/client";
import type { LearningContext } from "@syllabyte/core/learning";
import type { MisconceptionClip, MisconceptionRequest } from "@syllabyte/core/types";
import { colors, fonts, radius } from "@/theme/tokens";
import { Button } from "../Button";
import { Icon } from "../Icon";
import { QuestionText } from "../QuestionText";
import { T } from "../T";

export interface ReadyClip {
  request: MisconceptionRequest;
  clip: MisconceptionClip;
  item_title: string;
}

const LETTERS = "ABCDEFGH";
const startPlaying = (p: VideoPlayer) => {
  p.loop = false;
  p.play();
};

/**
 * A misconception clip, offered by the feed as soon as it is made (plan/engagement-feedback-implementation-plan.md,
 * "Misconception clips"): the offer (watch now or later), the clip, then its follow-up question, which records whether
 * the correction worked. The feed shows it only between videos, never over one that is playing.
 */
export function MisconceptionClipCard({ ready, learning, onDone }: {
  ready: ReadyClip;
  learning: LearningContext;
  /** "watched": seen (whether or not the question was answered); "later": offer it again at the next chance */
  onDone: (action: "watched" | "later") => void;
}) {
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState<"offer" | "watch" | "check">("offer");
  const check = ready.clip.check_item;

  return (
    <View style={[StyleSheet.absoluteFill, styles.scrim]} accessibilityViewIsModal>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingTop: insets.top + 56, paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.card}>
          <View style={styles.eyebrow}>
            <Icon name="lightbulb" size={14} color={colors.secondaryContainer} />
            <T variant="codeSm" color={colors.secondaryContainer} style={styles.eyebrowText}>
              A closer look
            </T>
          </View>
          {step === "offer" ? (
            <>
              <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header">
                {`A short video about the question you missed in “${ready.item_title}”`}
              </T>
              <T color="#e2e8f0">You were certain of an answer that wasn{"'"}t right. This video walks through why that idea seems right, where it breaks, and what holds instead.</T>
              <Button label="Watch now" icon="play-arrow" onPress={() => setStep("watch")} />
              <Button label="Later" kind="secondary" onPress={() => onDone("later")} />
            </>
          ) : step === "watch" ? (
            <ClipPlayer uri={ready.clip.video.video_url} onEnd={() => setStep(check ? "check" : "watch")}
              onFinish={() => (check ? setStep("check") : onDone("watched"))} hasCheck={!!check} />
          ) : check ? (
            <FollowUp learning={learning} requestId={ready.request.id} stem={check.stem} options={check.options} onDone={() => onDone("watched")} />
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

function ClipPlayer({ uri, onEnd, onFinish, hasCheck }: { uri: string; onEnd: () => void; onFinish: () => void; hasCheck: boolean }) {
  const player = useVideoPlayer(uri, startPlaying);
  useEventListener(player, "playToEnd", onEnd);
  return (
    <>
      <View style={styles.video}>
        <VideoView player={player} nativeControls contentFit="contain" style={StyleSheet.absoluteFill} />
      </View>
      <Button label={hasCheck ? "Done, check my understanding" : "Done"} onPress={() => { player.pause(); onFinish(); }} />
    </>
  );
}

/** One question on the same idea; the answer is recorded once, then the right answer and why are shown. */
function FollowUp({ learning, requestId, stem, options, onDone }: {
  learning: LearningContext; requestId: string; stem: string; options: string[]; onDone: () => void;
}) {
  const [choice, setChoice] = useState<number | null>(null);
  const [result, setResult] = useState<{ correct: boolean; correct_index: number; explanation: string } | null>(null);
  const [error, setError] = useState(false);
  function answer(i: number) {
    if (choice !== null && !error) return;
    setChoice(i);
    setError(false);
    api.answerMisconceptionCheck(learning, requestId, i).then(setResult, () => setError(true));
  }
  return (
    <>
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
    </>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: "rgba(0,0,0,0.82)" },
  scroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 16 },
  card: { gap: 14, padding: 20, borderRadius: radius.xl, backgroundColor: "#18181b", borderWidth: 1, borderColor: "rgba(152,243,224,0.45)" },
  eyebrow: { flexDirection: "row", alignItems: "center", gap: 6 },
  eyebrowText: { fontSize: 11, fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 },
  title: { fontFamily: fonts.bold },
  video: { width: "100%", aspectRatio: 9 / 16, maxHeight: 460, borderRadius: radius.md, overflow: "hidden", backgroundColor: "#000" },
  option: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 48, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.md, borderWidth: 1.5 },
  idle: { borderColor: "rgba(255,255,255,0.18)" },
  picked: { borderColor: colors.primaryFixedDim, backgroundColor: colors.primary },
  correct: { borderColor: colors.secondaryContainer, backgroundColor: "rgba(0,107,93,0.45)" },
  wrong: { borderColor: colors.errorSoft, backgroundColor: "rgba(186,26,26,0.35)" },
});
