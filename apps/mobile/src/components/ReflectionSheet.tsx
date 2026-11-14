import { useState } from "react";
import { Modal, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@syllabyte/core/api/client";
import { useQuery } from "@/state/app";
import { colors, fonts, radius } from "@/theme/tokens";
import { Button } from "./Button";
import { T } from "./T";

/** Screens a reflection must not cover: signing in, first run, and the checks. */
const QUIET_PATHS = /^\/(landing|signin|welcome|analyzing|quiz|study)/;

/**
 * The session reflection, shown by the app itself, never opened by the student (plan/engagement-feedback-implementation-
 * plan.md, "Automatic feedback"). It appears when a learning session ends with something worth reflecting on: right
 * after the student leaves a feed, or the next time they open the app if they left by closing it (the server ends a
 * session idle for 10 minutes). One observation, one next step, once: dismissing it marks it seen.
 */
export function ReflectionSheet({ pathname }: { pathname: string }) {
  const insets = useSafeAreaInsets();
  const summary = useQuery(() => api.getPendingReflection(), []);
  const [closed, setClosed] = useState<string | null>(null);
  if (!summary || closed === summary.sessionId || QUIET_PATHS.test(pathname)) return null;

  const close = () => {
    setClosed(summary.sessionId);
    void api.dismissReflection(summary.sessionId).catch(() => {});
  };
  return (
    <Modal transparent animationType="slide" visible onRequestClose={close}>
      <Pressable style={styles.scrim} onPress={close} accessibilityLabel="Close reflection" />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + 20 }]} accessibilityViewIsModal>
        <View style={styles.handle} />
        <T variant="codeSm" color={colors.primary} style={styles.eyebrow}>
          {summary.reason === "gap" ? "Your last session" : "Your session"}
        </T>
        <T variant="cardTitle" color={colors.onSurface} style={styles.title} accessibilityRole="header">
          {summary.observation}
        </T>
        <View style={styles.next}>
          <T variant="codeSm" color={colors.secondary} style={styles.eyebrow}>
            Next step
          </T>
          <T color={colors.onSurface}>{summary.nextStep}</T>
        </View>
        <T variant="caption" color={colors.onSurfaceVariant}>
          {summary.stats}
        </T>
        <Button label="Got it" onPress={close} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)" },
  sheet: {
    gap: 14,
    paddingHorizontal: 24,
    paddingTop: 12,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    backgroundColor: colors.surface,
  },
  handle: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.outlineVariant, marginBottom: 6 },
  eyebrow: { fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 },
  title: { fontFamily: fonts.bold, fontSize: 20, lineHeight: 27 },
  next: { gap: 6, padding: 16, borderRadius: radius.md, backgroundColor: colors.surfaceContainerLow, borderWidth: 1, borderColor: colors.outlineVariant },
});
