import { StyleSheet, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@syllabyte/core/api/client";
import { Button } from "@/components/Button";
import { Glow } from "@/components/Glow";
import { Icon } from "@/components/Icon";
import { T } from "@/components/T";
import { firstUpNext } from "@/data/selectors";
import { useQuery } from "@/state/app";
import { fetchProgress } from "@/state/progress";
import { colors, radius, shadow } from "@/theme/tokens";
import { lectureNumber } from "@/data/course";

/** After the check before a lecture: the levels are published and the playlist rebuilt (plan D11). */
export default function LectureChecked() {
  const insets = useSafeAreaInsets();
  const id = useLocalSearchParams<{ sitting?: string }>().sitting ?? "";
  const sitting = useQuery(() => api.getSitting(id), [id]);
  const n = sitting?.lecture_n;

  function home() {
    if (router.canDismiss()) router.dismissAll();
    router.replace("/");
  }

  async function watch() {
    const ku = firstUpNext(await fetchProgress());
    home();
    if (ku) router.push({ pathname: "/player/[kuId]", params: { kuId: ku.id } });
  }

  return (
    <View style={[styles.screen, { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 16 }]}>
      <Glow size={360} color={colors.secondary} opacity={0.12} style={{ top: -80, alignSelf: "center" }} />
      <View style={styles.hero}>
        <View style={styles.badge}>
          <Icon name="check" size={32} color={colors.onPrimary} />
        </View>
        <T variant="eyebrow" color={colors.secondary}>
          {n ? `Before Lecture ${lectureNumber(n)}` : "Lecture check"}
        </T>
        <T variant="title" style={{ textAlign: "center" }} accessibilityRole="header">
          Check done
        </T>
        <T variant="body" color={colors.onSurfaceVariant} style={{ textAlign: "center", maxWidth: 300 }}>
          {n ? `Your Lecture ${lectureNumber(n)} videos are now tuned to what you know.` : "Your videos are now tuned to what you know."} Nothing here is graded.
        </T>
      </View>
      <View style={{ gap: 10 }}>
        <Button label="Watch Next Video" trailingIcon="arrow-forward" height={56} onPress={() => void watch()} />
        <Button label="Back to Home" kind="secondary" onPress={home} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: 20, justifyContent: "space-between" },
  hero: { alignItems: "center", gap: 8 },
  badge: {
    width: 64,
    height: 64,
    borderRadius: radius.full,
    backgroundColor: colors.secondary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
    ...shadow.raised,
  },
});
