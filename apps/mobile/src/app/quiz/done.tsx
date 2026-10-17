import { useEffect, useState } from "react";
import { Alert, Animated, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { IconButton } from "@/components/Header";
import { Glow } from "@/components/Glow";
import { Icon } from "@/components/Icon";
import { Spin, useLoop } from "@/components/Motion";
import { ProgressBar } from "@/components/ProgressBar";
import { T } from "@/components/T";
import { firstUpNext } from "@/data/selectors";
import { setPrefs } from "@/state/app";
import { fetchProgress } from "@/state/progress";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const STEPS = ["Reading your answers", "Choosing your first videos", "Synthesizing key topic breakdowns", "Rendering the first video"];
const TICK_MS = 120;

/** Check done: the first video is being made; go to it when it's ready. */
export default function QuizDone() {
  const insets = useSafeAreaInsets();
  const [progress, setProgress] = useState(0.12);
  const ready = progress >= 1;
  const ping = useLoop(1200);

  useEffect(() => {
    if (ready) return;
    const id = setInterval(() => setProgress((p) => Math.min(1, p + 0.012)), TICK_MS);
    return () => clearInterval(id);
  }, [ready]);

  async function goToFirstVideo() {
    setPrefs({ setupDone: true });
    // the levels are published and the playlist built: its first video is the one to start with
    const ku = firstUpNext(await fetchProgress());
    if (router.canDismiss()) router.dismissAll();
    router.replace("/");
    if (ku) router.push({ pathname: "/player/[kuId]", params: { kuId: ku.id } });
  }

  useEffect(() => {
    if (!ready) return;
    const id = setTimeout(() => void goToFirstVideo(), 900);
    return () => clearTimeout(id);
  }, [ready]);

  const step = STEPS[Math.min(STEPS.length - 1, Math.floor(progress * STEPS.length))];
  const secondsLeft = Math.ceil(((1 - progress) / 0.012) * (TICK_MS / 1000));

  return (
    <View style={[styles.screen, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 16 }]}>
      <Glow size={360} color={colors.primary} opacity={0.14} style={{ top: -110, alignSelf: "center" }} />
      <View style={styles.closeRow}>
        <IconButton
          icon="close"
          label="Close and exit"
          style={styles.close}
          color={colors.onSurfaceVariant}
          onPress={() =>
            Alert.alert("Leave now?", "Your first video keeps rendering. You'll find it on your course roadmap.", [
              { text: "Stay", style: "cancel" },
              {
                text: "Go to Home",
                onPress: () => {
                  setPrefs({ setupDone: true });
                  if (router.canDismiss()) router.dismissAll();
                  router.replace("/");
                },
              },
            ])
          }
        />
      </View>

      <View style={styles.hero}>
        <View style={styles.badgeWrap}>
          <Animated.View
            style={[
              styles.ping,
              {
                opacity: ping.interpolate({ inputRange: [0, 1], outputRange: [0.5, 0] }),
                transform: [{ scale: ping.interpolate({ inputRange: [0, 1], outputRange: [1, 1.5] }) }],
              },
            ]}
          />
          <View style={styles.dashedRing} />
          <View style={styles.badge}>
            <Icon name="check" size={32} color={colors.onPrimary} />
          </View>
          <View style={styles.spark}>
            <Icon name="auto-awesome" size={14} color={colors.onSecondaryContainer} />
          </View>
        </View>
        <T variant="eyebrow" color={colors.primary} style={{ marginBottom: 4 }}>
          Quick Assessment
        </T>
        <T variant="title" style={{ textAlign: "center", fontSize: 32, lineHeight: 38 }} accessibilityRole="header">
          Quiz Completed!
        </T>
        <T variant="body" color={colors.onSurfaceVariant} style={{ marginTop: 4 }}>
          {"We're personalizing videos now."}
        </T>
      </View>

      <View style={styles.card} accessibilityLiveRegion="polite">
        <View style={styles.cardHead}>
          <View style={styles.spinner}>
            {ready ? (
              <Icon name="check-circle" size={20} color={colors.secondary} />
            ) : (
              <Spin duration={1200}>
                <Icon name="sync" size={20} color={colors.primary} />
              </Spin>
            )}
          </View>
          <T variant="bodySemibold" style={{ flex: 1, fontSize: 14 }}>
            {ready ? "First video ready" : "Generating first video..."}
          </T>
          <View style={styles.pct}>
            <T variant="codeSm" color={colors.primary} style={{ fontFamily: fonts.monoSemibold }}>
              {Math.round(progress * 100)}%
            </T>
          </View>
        </View>
        <ProgressBar value={progress} height={8} gradient label="First video" />
        <View style={styles.cardFoot}>
          <T variant="codeSm" color={colors.onSurfaceVariant} numberOfLines={1} style={{ flex: 1 }}>
            {step}...
          </T>
          {!ready ? (
            <T variant="codeSm" color={colors.outline}>
              ~{secondsLeft}s left
            </T>
          ) : null}
        </View>
      </View>

      <View style={styles.footer}>
        <Button label="Go to First Video" trailingIcon="arrow-forward" height={56} onPress={() => void goToFirstVideo()} style={{ alignSelf: "stretch" }} />
        <View style={styles.auto}>
          <Icon name="check-circle" size={14} color={colors.secondary} />
          <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 12 }}>
            Taking you to video automatically when ready...
          </T>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: 16, justifyContent: "space-between" },
  closeRow: { alignItems: "flex-end" },
  close: { width: 36, minWidth: 36, minHeight: 36, borderRadius: 18, backgroundColor: colors.surfaceContainer, borderWidth: 1, borderColor: "rgba(201,196,215,0.3)" },
  hero: { alignItems: "center" },
  badgeWrap: { width: 80, height: 80, alignItems: "center", justifyContent: "center", marginBottom: 24 },
  ping: { position: "absolute", width: 80, height: 80, borderRadius: 40, backgroundColor: "rgba(91,63,214,0.15)" },
  dashedRing: { position: "absolute", width: 92, height: 92, borderRadius: 46, borderWidth: 2, borderStyle: "dashed", borderColor: "rgba(91,63,214,0.25)" },
  badge: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center", ...shadow.glow },
  spark: {
    position: "absolute",
    right: -2,
    bottom: -2,
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.secondaryContainer,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: colors.surface,
  },
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: radius.xl,
    padding: 24,
    gap: 16,
    borderWidth: 1,
    borderColor: "rgba(201,196,215,0.3)",
    ...shadow.card,
  },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  spinner: { width: 32, height: 32, borderRadius: 8, backgroundColor: "rgba(91,63,214,0.1)", alignItems: "center", justifyContent: "center" },
  pct: { backgroundColor: "rgba(91,63,214,0.1)", paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.full },
  cardFoot: { flexDirection: "row", justifyContent: "space-between", gap: 8, paddingTop: 6, borderTopWidth: 1, borderTopColor: colors.surfaceContainer },
  footer: { alignItems: "center", gap: 8 },
  auto: { flexDirection: "row", alignItems: "center", gap: 4 },
});
