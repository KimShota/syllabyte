import { ScrollView, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@syllabyte/core/api/client";
import type { LearningCheckIn, LearningContext } from "@syllabyte/core/learning";
import { useQuery } from "@/state/app";
import { colors, fonts, radius } from "@/theme/tokens";
import { T } from "../T";
import { Button } from "../Button";

const MUTED = "rgba(255,255,255,0.72)";

/** "1 min 20 s", "45 s" */
export function formatSeconds(s: number): string {
  const total = Math.round(s);
  const min = Math.floor(total / 60);
  return min ? `${min} min${total % 60 ? ` ${total % 60} s` : ""}` : `${total} s`;
}

function actionText(c: LearningCheckIn): string {
  if (c.action === "replay") return "You chose to replay that part.";
  if (c.action === "continue") return "You chose to continue.";
  return "No next step was recorded.";
}

/**
 * The page after a feed's last video: what this learning session saved (playback observed, checkpoint answers and the
 * optional check-ins with the feedback they led to) and one next step. Descriptive only: playback says what played, not
 * how closely the student followed it, and a few answers are not a measure of their confidence. It refetches when it
 * comes on screen, after the page before it has saved its playback.
 */
export function SessionReflection({ learning, active, more }: { learning: LearningContext; active: boolean; more: boolean }) {
  const insets = useSafeAreaInsets();
  const r = useQuery(() => api.getLearningReflection(learning), [learning.sessionId, active]);
  const empty = r && !r.videos.length && !r.answers && !r.glanced;

  return (
    <ScrollView style={styles.page} contentContainerStyle={[styles.body, { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 48 }]}>
      <T variant="codeSm" color={colors.secondaryContainer} style={styles.eyebrow}>
        This session
      </T>
      <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header">
        Your learning reflection
      </T>
      <T color={MUTED}>What was saved while you watched. Playback shows what played, not how closely you followed it.</T>

      {!r ? (
        <T color={MUTED}>Loading your session…</T>
      ) : empty ? (
        <T color={MUTED}>Nothing has been saved in this session yet.</T>
      ) : (
        <>
          {r.videos.length || r.glanced ? (
            <View style={styles.card}>
              <T color="#fff" style={styles.label}>
                {formatSeconds(r.elapsedSeconds)} of playback
              </T>
              {r.videos.map((v) => (
                <View key={v.id} style={{ gap: 2 }}>
                  <T color="#fff">{v.title}</T>
                  <T variant="caption" color={MUTED}>
                    {Math.round(v.coverage * 100)}% played{v.replaySeconds >= 1 ? ` · ${formatSeconds(v.replaySeconds)} replayed` : ""}
                    {v.completed ? " · counted as watched" : ""}
                    {v.synthetic ? " · stand-in, no video file" : ""}
                  </T>
                </View>
              ))}
              {r.glanced ? (
                <T variant="caption" color={MUTED}>
                  {r.videos.length ? "Also glanced at" : "Glanced at"} {r.glanced === 1 ? "1 video" : `${r.glanced} videos`} for a few seconds.
                </T>
              ) : null}
            </View>
          ) : null}

          {r.answers ? (
            <View style={styles.card}>
              <T color="#fff" style={styles.label}>
                {r.correct} of {r.answers} checkpoint {r.answers === 1 ? "answer" : "answers"} right
              </T>
              {r.certainAnswers ? (
                <T variant="caption" color={MUTED}>
                  When you said “Certain”, {r.certainCorrect} of {r.certainAnswers} {r.certainAnswers === 1 ? "was" : "were"} right. That describes these
                  answers, not how well your confidence works in general.
                </T>
              ) : null}
            </View>
          ) : null}

          {r.checkIns.length ? (
            <View style={styles.card}>
              <T color="#fff" style={styles.label}>
                Your reflections
              </T>
              {r.checkIns.map((c) => (
                <View key={c.id} style={{ gap: 2 }}>
                  <T color="#fff">{c.videoTitle}</T>
                  <T color={MUTED}>{c.recap}</T>
                  <T variant="caption" color={MUTED}>
                    {actionText(c)}
                  </T>
                </View>
              ))}
            </View>
          ) : null}
        </>
      )}

      {r ? (
        <View style={[styles.card, styles.next]}>
          <T color={colors.secondaryContainer} style={styles.label}>
            Next step
          </T>
          <T color="#fff">{r.nextStep}</T>
        </View>
      ) : null}

      {more ? (
        <T variant="caption" color={MUTED} style={{ textAlign: "center" }}>
          Swipe up for what comes next
        </T>
      ) : (
        <Button label="Back to learning" kind="secondary" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} />
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.player.bg },
  body: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 24, gap: 14 },
  eyebrow: { fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 },
  title: { fontFamily: fonts.bold, fontSize: 20, lineHeight: 26 },
  label: { fontFamily: fonts.semibold },
  card: { gap: 8, padding: 16, borderRadius: radius.xl, backgroundColor: colors.player.glass, borderWidth: 1, borderColor: colors.player.border },
  next: { borderColor: "rgba(152,243,224,0.35)" },
});
