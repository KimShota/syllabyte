import { useCallback, useEffect, useState, type ReactNode } from "react";
import { setStatusBarHidden, setStatusBarStyle } from "expo-status-bar";
import { FlatList, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { PlayerPage } from "./PlayerPage";
import { api } from "@syllabyte/core/api/client";
import { kuEyebrow } from "@/data/selectors";
import type { Ku } from "@/data/types";
import { usePrefs, useQuery, type Speed } from "@/state/app";

type FeedItem = { kind: "video"; ku: Ku } | { kind: "end" };

/** Light status bar only while a dark feed is the focused screen. */
export function useDarkStatusBar() {
  useFocusEffect(
    useCallback(() => {
      setStatusBarStyle("light");
      return () => {
        setStatusBarStyle("dark");
        setStatusBarHidden(false, "fade");
      };
    }, []),
  );
}

/**
 * A vertical swipe feed of full-screen videos: one page at a time, and only the page on screen plays. Speed and
 * captions carry from page to page; a quick check waiting for its answer stops the swiping. `end`, if given, is
 * one more page after the last video.
 */
export function VideoFeed({ kus, startIndex, end }: { kus: readonly Ku[]; startIndex: number; end?: ReactNode }) {
  const prefs = usePrefs();
  const me = useQuery(() => api.getMe());
  const [height, setHeight] = useState(0);
  const [activeIndex, setActiveIndex] = useState(startIndex);
  const [speed, setSpeed] = useState<Speed>(prefs.speed);
  // captions start from the student's setting; toggling them here is for this sitting only
  const [captionsHere, setCaptions] = useState<boolean | null>(null);
  const captions = captionsHere ?? me?.settings.captions ?? true;
  // the page on screen is waiting for its quick check to be answered
  const [blocked, setBlocked] = useState(false);

  const items: FeedItem[] = [...kus.map((ku) => ({ kind: "video" as const, ku })), ...(end ? [{ kind: "end" as const }] : [])];
  const onEnd = items[activeIndex]?.kind === "end";
  // the videos hide the status bar with their controls; the end page always shows it
  useEffect(() => {
    if (onEnd) setStatusBarHidden(false, "fade");
  }, [onEnd]);

  // FlatList needs the same function for its whole life
  const [onViewable] = useState(() => ({ viewableItems }: { viewableItems: { index?: number | null; isViewable: boolean }[] }) => {
    const first = viewableItems.find((v) => v.isViewable);
    if (first?.index != null) setActiveIndex(first.index);
  });

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }} onLayout={(e) => setHeight(e.nativeEvent.layout.height)}>
      {height > 0 ? (
        <FlatList
          data={items}
          keyExtractor={(item) => (item.kind === "video" ? item.ku.id : "end")}
          pagingEnabled
          scrollEnabled={!blocked}
          snapToInterval={height}
          snapToAlignment="start"
          decelerationRate="fast"
          disableIntervalMomentum
          showsVerticalScrollIndicator={false}
          initialScrollIndex={Math.min(startIndex, items.length - 1)}
          getItemLayout={(_, index) => ({ length: height, offset: height * index, index })}
          onViewableItemsChanged={onViewable}
          viewabilityConfig={{ itemVisiblePercentThreshold: 60 }}
          windowSize={3}
          initialNumToRender={1}
          maxToRenderPerBatch={2}
          renderItem={({ item, index }) =>
            item.kind === "video" ? (
              <PlayerPage
                ku={item.ku}
                eyebrow={kuEyebrow(item.ku)}
                height={height}
                active={index === activeIndex}
                speed={speed}
                onSpeed={setSpeed}
                captions={captions}
                onCaptions={setCaptions}
                onBlockSwipe={setBlocked}
              />
            ) : (
              <View style={{ height }}>{end}</View>
            )
          }
        />
      ) : null}
    </View>
  );
}
