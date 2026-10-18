import { useEffect } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { Stack, router, usePathname } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";
import { useFonts } from "expo-font";
import { Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold } from "@expo-google-fonts/manrope";
import { JetBrainsMono_400Regular, JetBrainsMono_500Medium, JetBrainsMono_600SemiBold, JetBrainsMono_700Bold } from "@expo-google-fonts/jetbrains-mono";
import { api } from "@syllabyte/core/api/client";
import { REMOTE } from "@/data/backend";
import { setScreen, startApp, useAppReady, usePrefs, useQuery } from "@/state/app";
import { retryConnection, useReachable, useSession } from "@/state/session";
import { T } from "@/components/T";
import { colors, fonts } from "@/theme/tokens";

SplashScreen.preventAutoHideAsync();
// read the saved state while the fonts load
void startApp();

/** The quick check is the first thing every student does, and there is no way around it (plan D8, mobile-app-plan). */
const OPEN_BEFORE_BASELINE = (pathname: string) => pathname === "/signin" || pathname === "/welcome" || pathname === "/analyzing" || pathname.startsWith("/quiz");

/**
 * Until the baseline is finished, every screen but the first-run screens and the check itself sends the student
 * back to the check (it resumes where they left off). Leaving the check, swiping back or opening a link to a video
 * all end up there.
 */
function BaselineGate({ pathname }: { pathname: string }) {
  const me = useQuery(() => api.getMe());
  const { setupDone } = usePrefs();
  const locked = !!me && setupDone && !me.onboarding_done && !OPEN_BEFORE_BASELINE(pathname);
  useEffect(() => {
    if (locked) router.replace("/quiz");
  }, [locked]);
  return null;
}

/** With a backend, a student who isn't signed in sees only the sign-in screen; once signed in they leave it. */
function SessionGate({ pathname }: { pathname: string }) {
  const { status } = useSession();
  useEffect(() => {
    if (!REMOTE) return;
    if (status === "signedOut" && pathname !== "/signin") router.replace("/signin");
    if (status === "signedIn" && pathname === "/signin") router.replace("/");
  }, [status, pathname]);
  return null;
}

/** Shown while the server can't be reached; "Try again" asks every screen to refetch. */
function ConnectionBanner({ pathname }: { pathname: string }) {
  const reachable = useReachable();
  const insets = useSafeAreaInsets();
  // the sign-in screen explains the problem itself
  if (!REMOTE || reachable || pathname === "/signin") return null;
  return (
    <View style={[styles.banner, { paddingTop: insets.top + 8 }]} accessibilityRole="alert">
      <T variant="caption" color={colors.onPrimary} style={{ flex: 1 }}>
        {"Can't reach the server. What you just did may not be saved."}
      </T>
      <Pressable accessibilityRole="button" onPress={retryConnection} hitSlop={8}>
        <T variant="caption" color={colors.onPrimary} style={{ fontFamily: fonts.bold, textDecorationLine: "underline" }}>
          Try again
        </T>
      </Pressable>
    </View>
  );
}

export default function RootLayout() {
  const [loaded, error] = useFonts({
    Manrope_400Regular,
    Manrope_500Medium,
    Manrope_600SemiBold,
    Manrope_700Bold,
    Manrope_800ExtraBold,
    JetBrainsMono_400Regular,
    JetBrainsMono_500Medium,
    JetBrainsMono_600SemiBold,
    JetBrainsMono_700Bold,
  });

  const ready = useAppReady() && (loaded || !!error);
  const pathname = usePathname();

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);
  useEffect(() => setScreen(pathname), [pathname]);

  if (!ready) return null;

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <SessionGate pathname={pathname} />
      <BaselineGate pathname={pathname} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="signin" options={{ animation: "fade", gestureEnabled: false }} />
        <Stack.Screen name="welcome" options={{ animation: "fade" }} />
        <Stack.Screen name="analyzing" options={{ animation: "fade", gestureEnabled: false }} />
        <Stack.Screen name="quiz/index" options={{ animation: "slide_from_bottom" }} />
        <Stack.Screen name="quiz/question" options={{ gestureEnabled: false }} />
        <Stack.Screen name="quiz/done" options={{ animation: "fade", gestureEnabled: false }} />
        <Stack.Screen name="quiz/checked" options={{ animation: "fade", gestureEnabled: false }} />
        <Stack.Screen name="study/[id]" options={{ animation: "slide_from_bottom" }} />
        <Stack.Screen name="player/[kuId]" options={{ animation: "slide_from_bottom", contentStyle: { backgroundColor: "#000" } }} />
      </Stack>
      <ConnectionBanner pathname={pathname} />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 16,
    paddingBottom: 10,
    backgroundColor: colors.error,
  },
});
