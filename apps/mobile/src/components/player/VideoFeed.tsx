import { useCallback, useEffect, useState, type ReactNode } from "react";
import { setStatusBarHidden, setStatusBarStyle } from "expo-status-bar";
import { AppState, FlatList, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { PlayerPage } from "./PlayerPage";
import { kuEyebrow } from "@/data/selectors";
import type { Ku } from "@/data/types";
import { usePrefs, type Speed } from "@/state/app";

import { COURSE } from "@/data/course";
import { uid } from "@syllabyte/core/util";
import { SessionReflection } from "./SessionReflection";

type FeedItem = { kind: "video"; ku: Ku } | { kind: "reflection" } | { kind: "end" };

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
 * A vertical swipe feed of full-screen videos: one page at a time, and only the page on screen plays. Speed
 * carries from page to page; a quick check waiting for its answer stops the swiping. After the last video comes the
 * session's reflection (what was observed in this visit to the feed: plan/engagement-feedback-implementation-plan.md),
 * then `end`, if given.
 *
 * One learning session per mounted feed: its id ties the playback observations, checkpoint answers and check-ins of this
 * visit together. A page counts as playing only while it is on screen, the route is focused and the app is in front.
 */
export function VideoFeed({ kus, startIndex, end }: { kus: readonly Ku[]; startIndex: number; end?: ReactNode }) {
  const prefs = usePrefs();
  const [learning] = useState(() => ({ courseId: COURSE.id, sessionId: uid("learning") }));
  const [focused, setFocused] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState === "active");
  const [windowFocused, setWindowFocused] = useState(true);
  useFocusEffect(useCallback(() => { setFocused(true); return () => setFocused(false); }, []));
  useEffect(() => {
    const state = AppState.addEventListener("change", (s) => setForeground(s === "active"));
    const blur = AppState.addEventListener("blur", () => setWindowFocused(false));
    const focus = AppState.addEventListener("focus", () => setWindowFocused(true));
    return () => { state.remove(); blur.remove(); focus.remove(); };
  }, []);
  const [height, setHeight] = useState(0);
  const [activeIndex, setActiveIndex] = useState(startIndex);
  const [speed, setSpeed] = useState<Speed>(prefs.speed);
  // the page on screen is waiting for its quick check to be answered
  const [blocked, setBlocked] = useState(false);

  const items: FeedItem[] = [...kus.map((ku) => ({ kind: "video" as const, ku })), { kind: "reflection" as const }, ...(end ? [{ kind: "end" as const }] : [])];
  const onEnd = items[activeIndex]?.kind !== "video";
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
          keyExtractor={(item) => (item.kind === "video" ? `${item.ku.id}:${item.ku.videoUri ?? "demo"}` : item.kind)}
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
                learning={learning}
                eyebrow={kuEyebrow(item.ku)}
                height={height}
                active={index === activeIndex && focused && foreground && windowFocused}
                speed={speed}
                onSpeed={setSpeed}
                onBlockSwipe={setBlocked}
              />
            ) : item.kind === "reflection" ? (
              <View style={{ height }}>
                <SessionReflection learning={learning} active={index === activeIndex && focused} more={!!end} />
              </View>
            ) : (
              <View style={{ height }}>{end}</View>
            )
          }
        />
      ) : null}
    </View>
  );
}
