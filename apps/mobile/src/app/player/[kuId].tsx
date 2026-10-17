import { useCallback, useMemo, useState } from "react";
import { setStatusBarHidden, setStatusBarStyle } from "expo-status-bar";
import { FlatList, View } from "react-native";
import { useFocusEffect, useLocalSearchParams } from "expo-router";
import { PlayerPage } from "@/components/player/PlayerPage";
import { KUS } from "@/data/course";
import { findLecture, lectureFeed } from "@/data/selectors";
import { useStore, type Speed } from "@/state/store";

/**
 * The immersive player as a vertical swipe feed: one full-screen video at a time, swiping up for the
 * next KU of the same lecture. Only the page on screen plays.
 */
export default function Player() {
  const { kuId } = useLocalSearchParams<{ kuId: string }>();
  const { state } = useStore();
  const start = KUS[kuId];
  const lecture = start ? findLecture(start.lectureN) : undefined;
  const feed = useMemo(() => (lecture ? lectureFeed(lecture) : []), [lecture]);
  const startIndex = Math.max(0, feed.findIndex((k) => k.id === kuId));

  const [height, setHeight] = useState(0);
  const [activeIndex, setActiveIndex] = useState(startIndex);
  const [speed, setSpeed] = useState<Speed>(state.prefs.speed);
  const [captions, setCaptions] = useState(state.prefs.captions);

  // FlatList needs the same function for its whole life
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

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }} onLayout={(e) => setHeight(e.nativeEvent.layout.height)}>
      {height > 0 ? (
        <FlatList
          data={feed}
          keyExtractor={(k) => k.id}
          pagingEnabled
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
            />
          )}
        />
      ) : null}
    </View>
  );
}
