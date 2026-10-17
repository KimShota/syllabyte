import { Pressable, StyleSheet, View, type ViewStyle } from "react-native";
import { colors, fonts, radius, shadow } from "@/theme/tokens";
import { Icon, type IconName } from "./Icon";
import { T } from "./T";

type Kind = "primary" | "secondary" | "tonal" | "ghost" | "success";

const KIND: Record<Kind, { bg: string; fg: string; pressed: string; border?: string }> = {
  primary: { bg: colors.primary, fg: colors.onPrimary, pressed: colors.primaryPressed },
  secondary: { bg: colors.primaryTint, fg: colors.primary, pressed: "#e0dbfa" },
  tonal: { bg: colors.surfaceContainer, fg: colors.onSurfaceVariant, pressed: colors.surfaceContainerHighest },
  ghost: { bg: "transparent", fg: colors.onSurface, pressed: colors.surfaceContainerLow, border: colors.outlineVariant },
  success: { bg: colors.secondary, fg: colors.onPrimary, pressed: colors.onSecondaryFixedVariant },
};

export function Button({
  label,
  onPress,
  kind = "primary",
  icon,
  trailingIcon,
  height = 48,
  disabled,
  style,
  accessibilityHint,
}: {
  label: string;
  onPress?: () => void;
  kind?: Kind;
  icon?: IconName;
  trailingIcon?: IconName;
  height?: number;
  disabled?: boolean;
  style?: ViewStyle;
  accessibilityHint?: string;
}) {
  const k = KIND[kind];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        { height, backgroundColor: pressed ? k.pressed : k.bg, borderColor: k.border ?? "transparent", borderWidth: k.border ? 1 : 0 },
        kind === "primary" && !disabled && shadow.raised,
        disabled && styles.disabled,
        pressed && styles.pressed,
        style,
      ]}
    >
      <View style={styles.row}>
        {icon ? <Icon name={icon} size={19} color={k.fg} /> : null}
        <T variant="bodySemibold" color={k.fg} style={{ fontFamily: fonts.semibold }}>
          {label}
        </T>
        {trailingIcon ? <Icon name={trailingIcon} size={19} color={k.fg} /> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { borderRadius: radius.xl, alignItems: "center", justifyContent: "center", paddingHorizontal: 20 },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  disabled: { opacity: 0.45 },
  pressed: { transform: [{ scale: 0.99 }] },
});
