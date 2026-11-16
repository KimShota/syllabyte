import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { BackButton, Header } from "@/components/Header";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { QuestionText } from "@/components/QuestionText";
import { T } from "@/components/T";
import { useCourseVersion } from "@/data/course";
import { findLecture } from "@/data/selectors";
import { useLectureMisconceptionVideos } from "@/state/misconceptions";
import { colors, radius, space } from "@/theme/tokens";

export default function LectureMistakeVideos() {
  const { courseId, n } = useLocalSearchParams<{ courseId: string; n: string }>();
  useCourseVersion();
  const { videos, failed, retry } = useLectureMisconceptionVideos(courseId, Number(n));
  const insets = useSafeAreaInsets();
  const lecture = findLecture(Number(n));
  return (
    <View style={styles.screen}>
      <Header left={<BackButton />} />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 32 }]}>
        <T variant="codeSm" color={colors.primary}>Lecture {n}{lecture ? ` · ${lecture.title}` : ""}</T>
        <T variant="titleMobile" accessibilityRole="header">Videos for your mistakes{videos ? ` · ${videos.length}` : ""}</T>
        {failed ? (
          <View style={styles.card}>
            <T>We couldn’t load your videos. Try again.</T>
            <Button label="Try again" kind="secondary" onPress={retry} />
          </View>
        ) : videos === undefined ? <T color={colors.onSurfaceVariant}>Loading your videos…</T> : null}
        {videos?.length === 0 ? (
          <View style={styles.card}>
            <Icon name="video-library" size={28} color={colors.primary} />
            <T variant="cardTitle">No videos yet</T>
            <T color={colors.onSurfaceVariant}>Videos made to explain your mistakes in this lecture will be saved here.</T>
          </View>
        ) : null}
        {videos?.map(item => {
          const status = item.request.follow_up ? "Follow-up completed" : item.request.action === "watched" ? "Watched" : "Ready to watch";
          return (
            <Pressable key={item.request.id} accessibilityRole="button" accessibilityLabel={`${item.item_title}, ${status}`}
              onPress={() => router.push({ pathname: "/course/[courseId]/lecture/[n]/mistakes-player", params: { courseId, n, requestId: item.request.id } })}
              style={({ pressed }) => [styles.card, pressed && { opacity: 0.75 }]}>
              <View style={styles.row}>
                <Icon name="play-circle-filled" size={32} color={colors.primary} />
                <View style={{ flex: 1 }}>
                  <T variant="cardTitle">{item.item_title}</T>
                  <T variant="caption" color={colors.onSurfaceVariant}>{Math.ceil(item.clip.video.duration_s / 60)} min · {status}</T>
                </View>
                <Icon name="chevron-right" size={24} color={colors.primary} />
              </View>
              {item.question ? <View style={{ gap: 6 }}>
                <T variant="caption" color={colors.onSurfaceVariant}>The question you missed</T>
                <QuestionText>{item.question}</QuestionText>
              </View> : null}
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: space.gutter, paddingTop: 20, gap: 16 },
  card: { gap: 14, padding: 20, borderRadius: radius.xl, backgroundColor: colors.surfaceContainerLowest, borderWidth: 1, borderColor: colors.outlineVariant },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
});
