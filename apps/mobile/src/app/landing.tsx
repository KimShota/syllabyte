import { Image, ScrollView, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { T } from "@/components/T";
import { colors, fonts, radius, space } from "@/theme/tokens";

/** The public entry screen. Sign up creates a verified account; sign in returns to an existing one. */
export default function Landing() {
  const insets = useSafeAreaInsets();
  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 32, paddingBottom: insets.bottom + 24 }]}
    >
      <View style={styles.hero}>
        <Image source={require("../../assets/icon.png")} style={styles.logo} accessibilityIgnoresInvertColors />
        <T variant="titleMobile" accessibilityRole="header" style={styles.title}>SyllaByte</T>
        <T variant="body" color={colors.onSurfaceVariant} style={styles.tagline}>Your course. Your pace.</T>
      </View>
      <View style={styles.actions}>
        <Button label="Sign up" height={52} onPress={() => router.push({ pathname: "/signin", params: { mode: "signup" } })} />
        <Button label="Sign in" height={52} kind="ghost" onPress={() => router.push("/signin")} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { flexGrow: 1, paddingHorizontal: space.gutter, alignItems: "center", gap: 32 },
  hero: { flexGrow: 1, justifyContent: "center", alignItems: "center", paddingVertical: 40 },
  logo: { width: 88, height: 88, borderRadius: radius.card, marginBottom: 24 },
  title: { fontFamily: fonts.extraBold, fontSize: 36, lineHeight: 44, letterSpacing: -0.8, textAlign: "center" },
  tagline: { marginTop: 12, textAlign: "center" },
  actions: { width: "100%", maxWidth: 400, gap: 12 },
});
