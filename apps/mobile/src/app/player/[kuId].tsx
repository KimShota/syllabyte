import { useMemo } from "react";
import { View } from "react-native";
import { Redirect, useLocalSearchParams } from "expo-router";
import { VideoFeed, useDarkStatusBar } from "@/components/player/VideoFeed";
import { precheckHref } from "@/components/TaskCards";
import { KUS, useCourseVersion } from "@/data/course";
import { findLecture, lectureFeed } from "@/data/selectors";
import { usePrecheck } from "@/state/progress";

/**
 * The immersive player as a vertical swipe feed: one full-screen video at a time, swiping up for the
 * next KU of the same lecture that has a video. Only the page on screen plays.
 */
export default function Player() {
  const { kuId } = useLocalSearchParams<{ kuId: string }>();
  useCourseVersion();
  const check = usePrecheck();
  const start = KUS[kuId];
  const lecture = start ? findLecture(start.lectureN) : undefined;
  const feed = useMemo(() => (lecture ? lectureFeed(lecture) : []), [lecture]);
  const startIndex = Math.max(0, feed.findIndex((k) => k.id === kuId));
  useDarkStatusBar();

  if (!start || !lecture) return null;
  // a lecture's videos open only after its check: until it loads show black, then send the student to it
  if (check === undefined) return <View style={{ flex: 1, backgroundColor: "#000" }} />;
  if (check && check.lecture_n === start.lectureN) return <Redirect href={precheckHref(check)} />;

  return <VideoFeed kus={feed} startIndex={startIndex} />;
}
