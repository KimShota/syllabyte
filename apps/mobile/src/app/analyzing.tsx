import { useEffect, useState } from "react";
import { Animated, Easing, Modal, Pressable, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { IconButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { useLoop } from "@/components/Motion";
import { T } from "@/components/T";
import { REMOTE } from "@/data/backend";
import { ANALYZER_SLIDES, ANALYZER_TOTAL_SLIDES } from "@/data/course";
import { setPrefs } from "@/state/app";
import { useMyCourse } from "@/state/course";
import { finishSetup } from "@/state/uploads";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const SLIDE_MS = 1800;

/**
 * "Analyzing your materials…": a scan over each slide, then on to the baseline check. With a backend
 * (plan/slide-uploads-plan.md) it runs while the server reads the syllabus, then goes to the lecture list (for the
 * student who added the course) or on into the course; a syllabus that couldn't be read goes back to the welcome
 * screen, which says why.
 */
export default function Analyzing() {
  const insets = useSafeAreaInsets();
  const [index, setIndex] = useState(0);
  const [exitOpen, setExitOpen] = useState(false);
  const [cardHeight, setCardHeight] = useState(0);
  const enter = useState(() => new Animated.Value(1))[0];
  const sweep = useLoop(1400);
  const myCourse = useMyCourse();

  useEffect(() => {
    if (!REMOTE || !myCourse || myCourse.status === "reading") return;
    if (myCourse.status !== "ready") {
      router.replace("/welcome");
      return;
    }
    const c = myCourse.course;
    if (c.is_creator && !c.lectures_confirmed) {
      router.replace("/setup/lectures");
      return;
    }
    void finishSetup(c.id).then((next) => router.replace(next), () => router.replace("/"));
  }, [myCourse]);

  useEffect(() => {
    if (exitOpen) return;
    const id = setTimeout(() => {
      if (index + 1 >= ANALYZER_SLIDES.length) {
        // with a backend the scan keeps going until the syllabus has been read
        if (!REMOTE) {
          router.replace("/quiz");
          return;
        }
      }
      Animated.timing(enter, { toValue: 0, duration: 220, easing: Easing.in(Easing.cubic), useNativeDriver: true }).start(() => {
        setIndex((i) => (i + 1) % ANALYZER_SLIDES.length);
        Animated.timing(enter, { toValue: 1, duration: 380, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
      });
    }, SLIDE_MS);
    return () => clearTimeout(id);
  }, [index, exitOpen, enter]);

  const slide = ANALYZER_SLIDES[index];
  const laserY = sweep.interpolate({ inputRange: [0, 1], outputRange: [0, Math.max(0, cardHeight - 4)] });
  const cardStyle = {
    opacity: enter,
    transform: [
      { translateY: enter.interpolate({ inputRange: [0, 1], outputRange: [-22, 0] }) },
      { scale: enter.interpolate({ inputRange: [0, 1], outputRange: [0.96, 1] }) },
    ],
  };

  return (
    <View style={[styles.screen, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 16 }]}>
      <View style={styles.top}>
        <View style={styles.tag}>
          <Icon name="psychology" size={18} color={colors.outline} />
          <T variant="codeSm" color={colors.outline} style={{ fontFamily: fonts.monoMedium }}>
            ANALYZER
          </T>
        </View>
        {REMOTE ? <View style={styles.close} /> : <IconButton icon="close" label="Close and return to the app" onPress={() => setExitOpen(true)} style={styles.close} />}
      </View>
      <T variant="titleMobile" style={{ textAlign: "center", marginBottom: 16 }} accessibilityRole="header" accessibilityLiveRegion="polite">
        Analyzing your materials...
      </T>

      <View style={styles.deck}>
        <View style={[styles.deckBack, { left: 16, right: 16, bottom: -8, backgroundColor: "rgba(232,231,243,0.6)" }]} />
        <View style={[styles.deckBack, { left: 8, right: 8, bottom: -4, backgroundColor: "rgba(238,236,248,0.8)" }]} />
        <Animated.View style={[styles.card, cardStyle]} onLayout={(e) => setCardHeight(e.nativeEvent.layout.height)}>
          <View style={styles.slideHeader}>
            <Icon name="layers" size={17} color={colors.primary} />
            <T variant="codeSm" color={colors.primary} style={{ fontFamily: fonts.monoSemibold, flexShrink: 1 }} numberOfLines={1}>
              Slide {slide.n} of {ANALYZER_TOTAL_SLIDES} • {slide.title}
            </T>
          </View>
          <View style={styles.graphic}>
            {slide.boxes.map((b, i) => (
              <View key={i} style={styles.graphicRow}>
                <View style={[styles.box, i === 1 && styles.boxHot]}>
                  <T variant="codeSm" color={i === 1 ? colors.primary : colors.outline} style={{ fontSize: 10, textAlign: "center", textTransform: "uppercase" }}>
                    {slide.captions[i]}
                  </T>
                  <T variant="codeSm" color={i === 1 ? colors.primary : colors.onSurface} style={{ fontFamily: fonts.monoSemibold, textAlign: "center", marginTop: 2 }}>
                    {b}
                  </T>
                </View>
                {i < 2 ? <Icon name="arrow-forward" size={14} color={colors.outlineVariant} /> : null}
              </View>
            ))}
          </View>
          <Animated.View pointerEvents="none" style={[styles.laser, { transform: [{ translateY: laserY }] }]}>
            <LinearGradient colors={["transparent", colors.primary, colors.secondary]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={{ flex: 1 }} />
          </Animated.View>
        </Animated.View>
      </View>

      <Modal transparent visible={exitOpen} animationType="fade" onRequestClose={() => setExitOpen(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard} accessibilityViewIsModal>
            <View style={styles.modalHead}>
              <View style={styles.modalIcon}>
                <Icon name="logout" size={20} color={colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <T variant="bodySemibold" style={{ fontFamily: fonts.bold, fontSize: 14 }}>
                  Exit Analysis?
                </T>
                <T variant="caption" color={colors.outline} style={{ fontSize: 12 }}>
                  Progress will be saved in background.
                </T>
              </View>
            </View>
            <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 12, marginBottom: 16 }}>
              Return to the Course Roadmap now? You can check results in your study hub later.
            </T>
            <View style={styles.modalActions}>
              <Pressable accessibilityRole="button" onPress={() => setExitOpen(false)} style={[styles.modalBtn, styles.modalBtnGhost]}>
                <T variant="caption" style={{ fontFamily: fonts.semibold, fontSize: 12 }}>
                  Keep Waiting
                </T>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setExitOpen(false);
                  setPrefs({ setupDone: true });
                  router.replace("/");
                }}
                style={[styles.modalBtn, { backgroundColor: colors.primary }]}
              >
                <T variant="caption" color={colors.onPrimary} style={{ fontFamily: fonts.semibold, fontSize: 12 }}>
                  Exit to Hub
                </T>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: 24 },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  tag: { flexDirection: "row", alignItems: "center", gap: 8 },
  close: { width: 36, minWidth: 36, minHeight: 36, borderRadius: 18, backgroundColor: "rgba(232,231,243,0.6)", borderWidth: 1, borderColor: "rgba(201,196,215,0.3)" },
  deck: { flex: 1, marginBottom: 8 },
  deckBack: { position: "absolute", top: 8, borderRadius: radius.xl },
  card: {
    flex: 1,
    borderRadius: radius.xl,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    borderColor: "rgba(201,196,215,0.3)",
    padding: 24,
    overflow: "hidden",
    ...shadow.raised,
  },
  slideHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 24 },
  graphic: {
    flex: 1,
    borderRadius: radius.lg,
    backgroundColor: "rgba(244,242,254,0.7)",
    borderWidth: 1,
    borderColor: "rgba(201,196,215,0.2)",
    padding: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
  },
  graphicRow: { flexDirection: "row", alignItems: "center", flex: 1, gap: 4 },
  box: {
    flex: 1,
    paddingVertical: 10,
    paddingHorizontal: 4,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: "rgba(201,196,215,0.3)",
  },
  boxHot: { borderColor: "rgba(91,63,214,0.25)", backgroundColor: "rgba(91,63,214,0.05)" },
  laser: { position: "absolute", left: 0, right: 0, top: 0, height: 3, ...shadow.glow },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(26,27,35,0.4)", alignItems: "center", justifyContent: "center", padding: 24 },
  modalCard: { width: "100%", maxWidth: 320, backgroundColor: colors.surfaceContainerLowest, borderRadius: radius.xl, padding: 20, ...shadow.float },
  modalHead: { flexDirection: "row", gap: 12, alignItems: "center", marginBottom: 12 },
  modalIcon: { width: 36, height: 36, borderRadius: 18, backgroundColor: "rgba(91,63,214,0.1)", alignItems: "center", justifyContent: "center" },
  modalActions: { flexDirection: "row", gap: 8 },
  modalBtn: { flex: 1, minHeight: 40, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  modalBtnGhost: { borderWidth: 1, borderColor: "rgba(201,196,215,0.4)", backgroundColor: colors.surface },
});
