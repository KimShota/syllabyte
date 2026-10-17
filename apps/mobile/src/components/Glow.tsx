import { useId } from "react";
import { StyleSheet, View, type ViewStyle } from "react-native";
import Svg, { Circle, Defs, RadialGradient, Stop } from "react-native-svg";

/** A soft colour pool fading to transparent (the designs' blurred auras; RN has no CSS blur). */
export function Glow({ size, color, opacity, style }: { size: number; color: string; opacity: number; style?: ViewStyle }) {
  const id = `glow${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <View pointerEvents="none" style={[{ position: "absolute", width: size, height: size }, style]}>
      <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
        <Defs>
          <RadialGradient id={id} cx="50%" cy="50%" r="50%">
            <Stop offset="0" stopColor={color} stopOpacity={opacity} />
            <Stop offset="1" stopColor={color} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Circle cx="50%" cy="50%" r="50%" fill={`url(#${id})`} />
      </Svg>
    </View>
  );
}
