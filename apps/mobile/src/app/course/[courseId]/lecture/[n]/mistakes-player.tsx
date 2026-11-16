import { useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import type { MisconceptionVideoView } from "@syllabyte/core/types";
import { BackButton, Header } from "@/components/Header";
import { Button } from "@/components/Button";
import { T } from "@/components/T";
import { VideoFeed, useDarkStatusBar } from "@/components/player/VideoFeed";
import type { Ku } from "@/data/types";
import { useLectureMisconceptionVideos } from "@/state/misconceptions";

const NO_LESSONS: readonly Ku[] = [];

export default function SavedMistakePlayer() {
  const { courseId, n, requestId } = useLocalSearchParams<{ courseId: string; n: string; requestId: string }>();
  const { videos, failed, retry } = useLectureMisconceptionVideos(courseId, Number(n));
  useDarkStatusBar();
  if (!videos?.length) return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <Header left={<BackButton />} />
      <View style={{ padding: 24, gap: 16 }}>
        <T color="#fff">{failed ? "We couldn’t load this video." : videos ? "This video is not available." : "Loading your video…"}</T>
        {failed ? <Button label="Try again" onPress={retry} /> : null}
      </View>
    </View>
  );
  return <SavedFeed key={`${courseId}:${n}:${requestId}`} videos={videos} requestId={requestId} />;
}

function SavedFeed({ videos, requestId }: { videos: MisconceptionVideoView[]; requestId: string }) {
  // Keep this visit's signed sources stable: background list refreshes must not restart a playing video.
  const [saved] = useState(videos);
  return <VideoFeed kus={NO_LESSONS} startIndex={Math.max(0, saved.findIndex(item => item.request.id === requestId))} savedClips={saved} />;
}
