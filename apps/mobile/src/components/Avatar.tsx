import type { ReactNode } from "react";
import { Image, StyleSheet, View } from "react-native";
import { usePrefs } from "@/state/app";

/** A round avatar: the student's photo when they have set one, else `fallback` (initials or an icon) on `backgroundColor`. */
export function Avatar({ size, backgroundColor, fallback }: { size: number; backgroundColor: string; fallback: ReactNode }) {
  const { photoUri } = usePrefs();
  const round = { width: size, height: size, borderRadius: size / 2 };
  return (
    <View style={[styles.base, round, { backgroundColor }]}>
      {photoUri ? <Image source={{ uri: photoUri }} style={round} accessibilityIgnoresInvertColors /> : fallback}
    </View>
  );
}

const styles = StyleSheet.create({
  base: { alignItems: "center", justifyContent: "center", overflow: "hidden" },
});
