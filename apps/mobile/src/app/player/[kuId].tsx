import { useCallback, useMemo, useState } from "react";
import { setStatusBarHidden, setStatusBarStyle } from "expo-status-bar";
import { FlatList, View } from "react-native";
import { Redirect, useFocusEffect, useLocalSearchParams } from "expo-router";
import { PlayerPage } from "@/components/player/PlayerPage";
import { precheckHref } from "@/components/TaskCards";
import { api } from "@syllabyte/core/api/client";
import { KUS } from "@/data/course";
import { findLecture, lectureFeed } from "@/data/selectors";
import { usePrefs, useQuery, type Speed } from "@/state/app";
import { usePrecheck } from "@/state/progress";

/**
 * The immersive player as a vertical swipe feed: one full-screen video at a time, swiping up for the
 * next KU of the same lecture that has a video. Only the page on screen plays.
 */
export default function Player() {
  const { kuId } = useLocalSearchParams<{ kuId: string }>();
  const prefs = usePrefs();
  const me = useQuery(() => api.getMe());
  const check = usePrecheck();
  const start = KUS[kuId];
  const lecture = start ? findLecture(start.lectureN) : undefined;
  const feed = useMemo(() => (lecture ? lectureFeed(lecture) : []), [lecture]);
  const startIndex = Math.max(0, feed.findIndex((k) => k.id === kuId));

  const [height, setHeight] = useState(0);
  const [activeIndex, setActiveIndex] = useState(startIndex);
  const [speed, setSpeed] = useState<Speed>(prefs.speed);
  // captions start from the student's setting; toggling them here is for this sitting only
  const [captionsHere, setCaptions] = useState<boolean | null>(null);
  const captions = captionsHere ?? me?.settings.captions ?? true;

  // FlatList needs the same function for its whole life
  // the page on screen is waiting for its quick check to be answered
  const [blocked, setBlocked] = useState(false);

  const [onViewable] = useState(() => ({ viewableItems }: { viewableItems: { index?: number | null; isViewable: boolean }[] }) => {
    const first = viewableItems.find((v) => v.isViewable);
    if (first?.index != null) setActiveIndex(first.index);
  });

  // light status bar only while the dark player is the focused screen
  useFocusEffect(
    useCallback(() => {
      setStatusBarStyle("light");
      return () => {
        setStatusBarStyle("dark");
        setStatusBarHidden(false, "fade");
      };
    }, []),
  );

  const sectionTitle = useCallback(
    (id: string) => lecture?.sections.find((s) => s.kuIds.includes(id))?.title ?? lecture?.title ?? "",
    [lecture],
  );

  if (!start || !lecture) return null;
  // a lecture's videos open only after its check: until it loads show black, then send the student to it
  // (own keys: the player's root measures itself with onLayout, which only fires on a freshly mounted view)
  if (check === undefined) return <View key="waiting" style={{ flex: 1, backgroundColor: "#000" }} />;
  if (check && check.lecture_n === start.lectureN) return <Redirect href={precheckHref(check)} />;

  return (
    <View key="player" style={{ flex: 1, backgroundColor: "#000" }} onLayout={(e) => setHeight(e.nativeEvent.layout.height)}>
      {height > 0 ? (
        <FlatList
          data={feed}
          keyExtractor={(k) => k.id}
          pagingEnabled
          scrollEnabled={!blocked}
          snapToInterval={height}
          snapToAlignment="start"
          decelerationRate="fast"
          disableIntervalMomentum
          showsVerticalScrollIndicator={false}
          initialScrollIndex={startIndex}
          getItemLayout={(_, index) => ({ length: height, offset: height * index, index })}
          onViewableItemsChanged={onViewable}
          viewabilityConfig={{ itemVisiblePercentThreshold: 60 }}
          windowSize={3}
          initialNumToRender={1}
          maxToRenderPerBatch={2}
          renderItem={({ item, index }) => (
            <PlayerPage
              ku={item}
              eyebrow={`Lecture ${lecture.n} · ${sectionTitle(item.id)}`}
              height={height}
              active={index === activeIndex}
              speed={speed}
              onSpeed={setSpeed}
              captions={captions}
              onCaptions={setCaptions}
              onBlockSwipe={setBlocked}
            />
          )}
        />
      ) : null}
    </View>
  );
}
