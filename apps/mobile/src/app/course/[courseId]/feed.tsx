import { useMemo } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { T } from "@/components/T";
import { VideoFeed, useDarkStatusBar } from "@/components/player/VideoFeed";
import { precheckHref } from "@/components/TaskCards";
import type { PrecheckView } from "@syllabyte/core/types";
import { REMOTE } from "@/data/backend";
import { COURSE, useCourseVersion, lectureNumber } from "@/data/course";
import { courseFeed, feedStart } from "@/data/selectors";
import type { LectureDef } from "@/data/types";
import { useQuery } from "@/state/app";
import { fetchProgress, usePrecheck } from "@/state/progress";
import { colors, fonts, radius } from "@/theme/tokens";

/**
 * Every video of the course so far as one swipe feed, in teaching order, opening on the one up next. It stops at
 * the lecture whose check is due: that lecture's videos open only after the check, so its last page leads there.
 * Its own route, so the events from it carry this screen and the analysis can tell it from the lecture player.
 */
export default function CourseFeed() {
  useCourseVersion();
  const check = usePrecheck();
  const progress = useQuery(fetchProgress);
  const feed = useMemo(() => courseFeed(COURSE, check?.lecture_n ?? null), [check]);
  useDarkStatusBar();

  // the stop and the starting video depend on both: black until they load
  if (check === undefined || !progress) return <View style={{ flex: 1, backgroundColor: "#000" }} />;

  return <VideoFeed kus={feed.kus} startIndex={feedStart(feed.kus, progress)} end={<FeedEnd count={feed.kus.length} lockedAt={feed.lockedAt} check={check} />} />;
}

/** The page after the last video: the check that opens the next lecture, or the end of what there is so far. */
function FeedEnd({ count, lockedAt, check }: { count: number; lockedAt: LectureDef | null; check: PrecheckView | null }) {
  const insets = useSafeAreaInsets();
  const locked = lockedAt && check ? { lecture: lockedAt, check } : null;

  return (
    <View style={styles.page}>
      <View style={[styles.top, { paddingTop: insets.top + 12 }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Go back"
          onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}
          style={styles.glassBtn}
        >
          <Icon name="arrow-back" size={20} color="#fff" />
        </Pressable>
      </View>

      <View style={styles.body}>
        <View style={[styles.badge, { backgroundColor: locked ? colors.primary : colors.secondary }]}>
          <Icon name={locked ? "fact-check" : "check"} size={30} color="#fff" />
        </View>
        {locked ? (
          <>
            <T variant="codeSm" color={colors.secondaryContainer} style={styles.eyebrow}>
              Next · Lecture {lectureNumber(locked.lecture.n)}
            </T>
            <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header">
              {locked.lecture.title}
            </T>
            <T variant="body" color="rgba(255,255,255,0.75)" style={styles.text}>
              Its videos open after a short check on what you already know. It isn{"'"}t graded.
            </T>
            <Button label="Take the check" icon="arrow-forward" onPress={() => router.push(precheckHref(locked.check))} style={styles.button} />
          </>
        ) : (
          <>
            <T variant="codeSm" color={colors.secondaryContainer} style={styles.eyebrow}>
              {count === 1 ? "1 video" : `${count} videos`}
            </T>
            <T variant="cardTitle" color="#fff" style={styles.title} accessibilityRole="header">
              {count ? "That's every video so far" : "No videos yet"}
            </T>
            <T variant="body" color="rgba(255,255,255,0.75)" style={styles.text}>
              {REMOTE ? "New ones appear here as you add slides and their videos are made." : "New ones appear here as lectures are added."}
            </T>
            <Button label="Back to the roadmap" kind="secondary" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} style={styles.button} />
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.player.bg },
  top: { paddingHorizontal: 16, flexDirection: "row" },
  glassBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: "rgba(0,0,0,0.4)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.15)",
    alignItems: "center",
    justifyContent: "center",
  },
  body: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 32, paddingBottom: 64 },
  badge: { width: 64, height: 64, borderRadius: radius.full, alignItems: "center", justifyContent: "center", marginBottom: 20 },
  eyebrow: { fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 },
  title: { marginTop: 6, fontFamily: fonts.bold, fontSize: 20, lineHeight: 26, textAlign: "center" },
  text: { marginTop: 10, textAlign: "center" },
  button: { marginTop: 28, alignSelf: "stretch" },
});
