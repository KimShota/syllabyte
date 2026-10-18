import type { ReactNode } from "react";
import { Pressable, StyleSheet, View, type ViewStyle } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, shadow } from "@/theme/tokens";
import { Avatar } from "./Avatar";
import { Icon, type IconName } from "./Icon";

/** The fixed top bar: 64pt tall under the status bar, on the surface tint. */
export function Header({ left, center, right, bordered }: { left?: ReactNode; center?: ReactNode; right?: ReactNode; bordered?: boolean }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.wrap, { paddingTop: insets.top }, bordered ? styles.bordered : shadow.card]}>
      <View style={styles.bar}>
        <View style={styles.side}>{left}</View>
        <View style={styles.center}>{center}</View>
        <View style={[styles.side, styles.right]}>{right}</View>
      </View>
    </View>
  );
}

export function IconButton({
  icon,
  label,
  onPress,
  color = colors.onSurface,
  size = 22,
  style,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  color?: string;
  size?: number;
  style?: ViewStyle;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={6}
      style={({ pressed }) => [styles.iconBtn, pressed && { backgroundColor: colors.surfaceContainer }, style]}
    >
      <Icon name={icon} size={size} color={color} />
    </Pressable>
  );
}

export function BackButton() {
  return <IconButton icon="arrow-back" label="Go back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} />;
}

/** The violet avatar that opens the student profile. */
export function ProfileButton({ size = 32 }: { size?: number }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Student profile"
      onPress={() => router.push("/profile")}
      hitSlop={8}
      style={styles.profileHit}
    >
      <Avatar size={size} backgroundColor={colors.primaryDeep} fallback={<Icon name="person" size={size * 0.56} color={colors.onPrimary} />} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: colors.surface, zIndex: 10 },
  bordered: { borderBottomWidth: 1, borderBottomColor: "rgba(227,225,237,0.7)" },
  bar: { height: 64, paddingHorizontal: 12, flexDirection: "row", alignItems: "center" },
  side: { minWidth: 44, flexDirection: "row", alignItems: "center", gap: 8 },
  right: { justifyContent: "flex-end" },
  center: { flex: 1, alignItems: "center" },
  iconBtn: { minWidth: 44, minHeight: 44, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  profileHit: { minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" },
});
