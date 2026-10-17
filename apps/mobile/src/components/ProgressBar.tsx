import { StyleSheet, View, type ViewStyle } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { colors } from "@/theme/tokens";
import type { SegmentState } from "@/data/selectors";

/** A rounded progress track. `value` is 0..1. */
export function ProgressBar({
  value,
  height = 10,
  color = colors.primary,
  track = colors.surfaceContainer,
  gradient,
  label,
  style,
}: {
  value: number;
  height?: number;
  color?: string;
  track?: string;
  /** fill with a violet→teal gradient (the "generating" bar) */
  gradient?: boolean;
  label?: string;
  style?: ViewStyle;
}) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityValue={{ min: 0, max: 100, now: pct }}
      style={[styles.track, { height, borderRadius: height, backgroundColor: track }, style]}
    >
      {gradient ? (
        <LinearGradient
          colors={[colors.primary, colors.secondary]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={{ width: `${pct}%`, height: "100%", borderRadius: height }}
        />
      ) : (
        <View style={{ width: `${pct}%`, height: "100%", borderRadius: height, backgroundColor: color }} />
      )}
    </View>
  );
}

/** The 3-segment level bar on a lecture section. */
export function SegmentBar({ segments, tone = "primary" }: { segments: SegmentState[]; tone?: "primary" | "secondary" }) {
  const full = tone === "secondary" ? colors.secondary : colors.primary;
  return (
    <View style={styles.segments} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {segments.map((s, i) => (
        <View
          key={i}
          style={[
            styles.segment,
            { backgroundColor: s === "done" ? full : s === "partial" ? colors.primaryFixed : colors.surfaceContainerHighest },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  track: { width: "100%", overflow: "hidden" },
  segments: { flexDirection: "row", gap: 6, marginTop: 8 },
  segment: { flex: 1, height: 8, borderRadius: 8 },
});
