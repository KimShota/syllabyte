import { useEffect } from "react";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useFonts } from "expo-font";
import { Manrope_400Regular, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold } from "@expo-google-fonts/manrope";
import { JetBrainsMono_400Regular, JetBrainsMono_500Medium, JetBrainsMono_600SemiBold, JetBrainsMono_700Bold } from "@expo-google-fonts/jetbrains-mono";
import { StoreProvider } from "@/state/store";
import { colors } from "@/theme/tokens";

SplashScreen.preventAutoHideAsync();

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

  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);

  if (!loaded && !error) return null;

  return (
    <SafeAreaProvider>
      <StoreProvider>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }}>
          <Stack.Screen name="index" />
          <Stack.Screen name="welcome" options={{ animation: "fade" }} />
          <Stack.Screen name="analyzing" options={{ animation: "fade", gestureEnabled: false }} />
          <Stack.Screen name="quiz/index" options={{ animation: "slide_from_bottom" }} />
          <Stack.Screen name="quiz/question" options={{ gestureEnabled: false }} />
          <Stack.Screen name="quiz/done" options={{ animation: "fade", gestureEnabled: false }} />
          <Stack.Screen name="player/[kuId]" options={{ animation: "slide_from_bottom", contentStyle: { backgroundColor: "#000" } }} />
        </Stack>
      </StoreProvider>
    </SafeAreaProvider>
  );
}
