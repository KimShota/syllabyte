import { useEffect, useState, type ReactNode } from "react";
import { Animated, Easing, KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, View, useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, radius, shadow } from "@/theme/tokens";

/**
 * A bottom sheet over a dimmed backdrop (the upload sheet, the node preview, the player's notes).
 * `edge="top"` drops it from the top instead (the courses drawer).
 */
export function Sheet({
  visible,
  onClose,
  children,
  dark,
  edge = "bottom",
  maxHeightRatio = 0.85,
  accessibilityLabel,
}: {
  visible: boolean;
  onClose: () => void;
  children: ReactNode;
  dark?: boolean;
  edge?: "bottom" | "top";
  maxHeightRatio?: number;
  accessibilityLabel?: string;
}) {
  const { height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const anim = useState(() => new Animated.Value(0))[0];
  const [mounted, setMounted] = useState(visible);
  // mount on open; unmount after the closing animation
  if (visible && !mounted) setMounted(true);

  useEffect(() => {
    Animated.timing(anim, {
      toValue: visible ? 1 : 0,
      duration: visible ? 280 : 200,
      easing: visible ? Easing.out(Easing.cubic) : Easing.in(Easing.cubic),
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (finished && !visible) setMounted(false);
    });
  }, [visible, anim]);

  if (!mounted) return null;

  const offset = anim.interpolate({ inputRange: [0, 1], outputRange: [edge === "bottom" ? height : -height * 0.6, 0] });
  const top = edge === "top";

  return (
    <Modal transparent visible statusBarTranslucent onRequestClose={onClose} animationType="none">
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[styles.root, top && styles.rootTop]}>
        <Animated.View style={[StyleSheet.absoluteFill, { opacity: anim }]}>
          <Pressable
            style={[StyleSheet.absoluteFill, { backgroundColor: dark ? "rgba(0,0,0,0.72)" : "rgba(26,27,35,0.45)" }]}
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel="Close"
          />
        </Animated.View>
        <Animated.View
          accessibilityViewIsModal
          accessibilityLabel={accessibilityLabel}
          style={[
            styles.panel,
            top ? styles.panelTop : styles.panelBottom,
            {
              maxHeight: height * maxHeightRatio,
              backgroundColor: dark ? colors.player.panel : colors.surfaceContainerLowest,
              borderColor: dark ? colors.player.border : colors.surfaceContainerHighest,
              paddingBottom: top ? 0 : insets.bottom,
              paddingTop: top ? insets.top : 0,
              transform: [{ translateY: offset }],
            },
            shadow.float,
          ]}
        >
          {children}
        </Animated.View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

/** The grab handle at the top of a light bottom sheet. */
export function SheetHandle({ dark }: { dark?: boolean }) {
  return <View style={[styles.handle, { backgroundColor: dark ? "rgba(255,255,255,0.3)" : colors.surfaceDim }]} />;
}

const styles = StyleSheet.create({
  root: { flex: 1, justifyContent: "flex-end" },
  rootTop: { justifyContent: "flex-start" },
  panel: { width: "100%", overflow: "hidden" },
  panelBottom: { borderTopLeftRadius: radius.sheet, borderTopRightRadius: radius.sheet, borderTopWidth: 1 },
  panelTop: { borderBottomLeftRadius: radius.card, borderBottomRightRadius: radius.card, borderBottomWidth: 1 },
  handle: { width: 48, height: 6, borderRadius: 3, alignSelf: "center", marginTop: 10, marginBottom: 4 },
});
