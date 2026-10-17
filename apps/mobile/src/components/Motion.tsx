import { useEffect, useState, type ReactNode } from "react";
import { AccessibilityInfo, Animated, Easing, type ViewStyle } from "react-native";

/** A looping 0→1→0 value; stays at 0 when the OS asks for reduced motion. */
export function useLoop(duration: number, { yoyo = true }: { yoyo?: boolean } = {}) {
  const v = useState(() => new Animated.Value(0))[0];
  useEffect(() => {
    let loop: Animated.CompositeAnimation | null = null;
    let cancelled = false;
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (cancelled || reduce) return;
      const forward = Animated.timing(v, { toValue: 1, duration, easing: Easing.inOut(Easing.ease), useNativeDriver: true });
      loop = Animated.loop(
        yoyo
          ? Animated.sequence([forward, Animated.timing(v, { toValue: 0, duration, easing: Easing.inOut(Easing.ease), useNativeDriver: true })])
          : Animated.sequence([Animated.timing(v, { toValue: 1, duration, easing: Easing.linear, useNativeDriver: true }), Animated.timing(v, { toValue: 0, duration: 0, useNativeDriver: true })]),
      );
      loop.start();
    });
    return () => {
      cancelled = true;
      loop?.stop();
    };
  }, [v, duration, yoyo]);
  return v;
}

/** The gentle dual-ring aura behind the "up next" node. */
export function PulseAura({ size, color, style }: { size: number; color: string; style?: ViewStyle }) {
  const v = useLoop(1400);
  const scale = v.interpolate({ inputRange: [0, 1], outputRange: [1, 1.18] });
  const opacity = v.interpolate({ inputRange: [0, 1], outputRange: [0.7, 0.25] });
  return (
    <Animated.View
      pointerEvents="none"
      style={[
        { position: "absolute", width: size, height: size, borderRadius: size / 2, backgroundColor: color, opacity, transform: [{ scale }] },
        style,
      ]}
    />
  );
}

/** Floats its child up and down a few points (the START bubble). */
export function Bob({ children, distance = 4 }: { children: ReactNode; distance?: number }) {
  const v = useLoop(700);
  const translateY = v.interpolate({ inputRange: [0, 1], outputRange: [0, -distance] });
  return <Animated.View style={{ transform: [{ translateY }] }}>{children}</Animated.View>;
}

/** Spins its child continuously (sync / progress icons). */
export function Spin({ children, duration = 1600 }: { children: ReactNode; duration?: number }) {
  const v = useLoop(duration, { yoyo: false });
  const rotate = v.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });
  return <Animated.View style={{ transform: [{ rotate }] }}>{children}</Animated.View>;
}
