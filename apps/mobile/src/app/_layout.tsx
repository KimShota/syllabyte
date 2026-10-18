import { useEffect } from "react";
import { Stack, router, usePathname } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useFonts } from "expo-font";
import { Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold } from "@expo-google-fonts/manrope";
import { JetBrainsMono_400Regular, JetBrainsMono_500Medium, JetBrainsMono_600SemiBold, JetBrainsMono_700Bold } from "@expo-google-fonts/jetbrains-mono";
import { api } from "@syllabyte/core/api/client";
import { setScreen, startApp, useAppReady, usePrefs, useQuery } from "@/state/app";
import { colors } from "@/theme/tokens";

SplashScreen.preventAutoHideAsync();
// read the saved state while the fonts load
void startApp();

/** The quick check is the first thing every student does, and there is no way around it (plan D8, mobile-app-plan). */
const OPEN_BEFORE_BASELINE = (pathname: string) => pathname === "/welcome" || pathname === "/analyzing" || pathname.startsWith("/quiz");

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
      <BaselineGate pathname={pathname} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="welcome" options={{ animation: "fade" }} />
        <Stack.Screen name="analyzing" options={{ animation: "fade", gestureEnabled: false }} />
        <Stack.Screen name="quiz/index" options={{ animation: "slide_from_bottom" }} />
        <Stack.Screen name="quiz/question" options={{ gestureEnabled: false }} />
        <Stack.Screen name="quiz/done" options={{ animation: "fade", gestureEnabled: false }} />
        <Stack.Screen name="quiz/checked" options={{ animation: "fade", gestureEnabled: false }} />
        <Stack.Screen name="study/[id]" options={{ animation: "slide_from_bottom" }} />
        <Stack.Screen name="player/[kuId]" options={{ animation: "slide_from_bottom", contentStyle: { backgroundColor: "#000" } }} />
      </Stack>
    </SafeAreaProvider>
  );
}
