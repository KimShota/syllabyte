import { ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts, radius } from "@/theme/tokens";
import { Button } from "../Button";
import { Icon } from "../Icon";
import { T } from "../T";
import type { ReadyClip } from "./misconceptionFeed";

/** The offer only: accepting it scrolls to the clip in the full-screen feed. */
export function MisconceptionClipCard({ ready, onWatch, onLater }: {
  ready: ReadyClip;
  onWatch: () => void;
  onLater: () => void;
}) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[StyleSheet.absoluteFill, styles.scrim]} accessibilityViewIsModal>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingTop: insets.top + 56, paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.card}>
          <View style={styles.eyebrow}>
            <Icon name="lightbulb" size={14} color={colors.secondaryContainer} />
            <T variant="codeSm" color={colors.secondaryContainer} style={styles.eyebrowText}>Video for your mistake</T>
          </View>
          <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header">
            We made a video to explain the answer you missed.
          </T>
          <T color="#e2e8f0">{`This explanation addresses the idea behind your answer in “${ready.item_title}”.`}</T>
          <Button label="Watch now" icon="play-arrow" onPress={onWatch} />
          <Button label="Watch later" kind="secondary" onPress={onLater} />
          <T variant="caption" color="#cbd5e1">Saved under “Videos for your mistakes” in this lecture.</T>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: "rgba(0,0,0,0.82)" },
  scroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: 16 },
  card: { gap: 14, padding: 20, borderRadius: radius.xl, backgroundColor: "#18181b", borderWidth: 1, borderColor: "rgba(152,243,224,0.45)" },
  eyebrow: { flexDirection: "row", alignItems: "center", gap: 6 },
  eyebrowText: { fontSize: 11, fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 },
  title: { fontFamily: fonts.bold },
});
