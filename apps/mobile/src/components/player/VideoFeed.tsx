import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { setStatusBarHidden, setStatusBarStyle } from "expo-status-bar";
import { AppState, FlatList, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { api } from "@syllabyte/core/api/client";
import type { LearningContext, LearningPrompt, PromptAction } from "@syllabyte/core/learning";
import { DRIFT_POLICY } from "@syllabyte/core/logic/engagementDrift";
import { uid } from "@syllabyte/core/util";
import { COURSE } from "@/data/course";
import { kuEyebrow } from "@/data/selectors";
import type { Ku } from "@/data/types";
import { usePrefs, type Speed } from "@/state/app";
import { EngagementPrompt } from "./EngagementPrompt";
import { whenSaved } from "./learningSync";
import { PlayerPage, type PlayerCommand } from "./PlayerPage";

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

const newSession = (): LearningContext => ({ courseId: COURSE.id, sessionId: uid("learning") });

/**
 * A vertical swipe feed of full-screen videos: one page at a time, and only the page on screen plays. Speed
 * carries from page to page; a quick check waiting for its answer stops the swiping. `end`, if given, is one more page
 * after the last video.
 *
 * It is also where the app decides, by itself, when to offer support (plan/engagement-feedback-implementation-plan.md,
 * "Automatic feedback"). One learning session per visit to the feed ties its playback, answers and prompts together. At
 * each decision point the server is asked, once the page left behind has saved its playback, whether a prompt is due:
 *  - moving to the next video: a drift check, when the student's behaviour dropped (core logic/engagementDrift.ts);
 *  - coming back to the app: a welcome-back recall, or a new session after a long gap;
 *  - leaving the feed: the session ends, and its reflection appears by itself if there is something to say
 *    (components/ReflectionSheet.tsx).
 * A page counts as playing only while it is on screen, the route is focused, the app is in front and no prompt is open.
 */
export function VideoFeed({ kus, startIndex, end }: { kus: readonly Ku[]; startIndex: number; end?: ReactNode }) {
  const prefs = usePrefs();
  const [learning, setLearning] = useState(newSession);
  const current = useRef(learning);
  useEffect(() => {
    current.current = learning;
  }, [learning]);
  const [focused, setFocused] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState === "active");
  const [windowFocused, setWindowFocused] = useState(true);
  useFocusEffect(useCallback(() => { setFocused(true); return () => setFocused(false); }, []));
  const [height, setHeight] = useState(0);
  const [activeIndex, setActiveIndex] = useState(startIndex);
  const [speed, setSpeed] = useState<Speed>(prefs.speed);
  // the page on screen is waiting for its quick check to be answered
  const [blocked, setBlocked] = useState(false);
  const [prompt, setPrompt] = useState<LearningPrompt | null>(null);
  const [command, setCommand] = useState<PlayerCommand | null>(null);
  const list = useRef<FlatList<FeedItem>>(null);

  const items: FeedItem[] = [...kus.map((ku) => ({ kind: "video" as const, ku })), ...(end ? [{ kind: "end" as const }] : [])];
  const onEnd = items[activeIndex]?.kind !== "video";
  const activeItem = items[activeIndex];
  const activeVideoId = activeItem?.kind === "video" ? activeItem.ku.videoId : null;
  const activeVideo = useRef(activeVideoId);
  useEffect(() => {
    activeVideo.current = activeVideoId;
  }, [activeVideoId]);
  // the videos hide the status bar with their controls; the end page always shows it
  useEffect(() => {
    if (onEnd) setStatusBarHidden(false, "fade");
  }, [onEnd]);

  // Decision point: the move to another video. The page left behind starts its save as it stops (before this effect runs).
  const shownIndex = useRef(activeIndex);
  useEffect(() => {
    if (shownIndex.current === activeIndex) return;
    shownIndex.current = activeIndex;
    if (!activeVideoId) return;
    let live = true;
    const context = current.current;
    void whenSaved()
      .then(() => api.evaluateLearningBoundary(context, { reason: "next_video", videoId: activeVideoId }))
      .then((p) => { if (live && p) setPrompt(p); }, () => {});
    return () => { live = false; };
  }, [activeIndex, activeVideoId]);

  // Decision point: back in the app. A short absence changes nothing; a long one ends the session and starts another.
  useEffect(() => {
    let leftAt: number | null = null;
    const change = AppState.addEventListener("change", (s) => {
      setForeground(s === "active");
      if (s === "background") leftAt ??= Date.now();
      if (s !== "active" || leftAt === null) return;
      const seconds = (Date.now() - leftAt) / 1000;
      leftAt = null;
      if (seconds < DRIFT_POLICY.awayMinS) return;
      const context = current.current;
      const videoId = activeVideo.current;
      if (seconds * 1000 >= DRIFT_POLICY.sessionGapMs) {
        setPrompt(null);
        setLearning(newSession());
        void whenSaved().then(() => api.finishLearningSession(context, "gap")).catch(() => {});
        return;
      }
      void whenSaved()
        .then(() => api.recordLearningAway(context, { seconds, videoId }))
        .then(() => (videoId ? api.evaluateLearningBoundary(context, { reason: "return", videoId }) : null))
        .then((p) => { if (p && current.current === context) setPrompt(p); }, () => {});
    });
    const blur = AppState.addEventListener("blur", () => setWindowFocused(false));
    const focus = AppState.addEventListener("focus", () => setWindowFocused(true));
    return () => { change.remove(); blur.remove(); focus.remove(); };
  }, []);

  // Decision point: leaving the feed ends the session; its reflection, if any, appears by itself (ReflectionSheet).
  useEffect(() => () => {
    const context = current.current;
    void whenSaved().then(() => api.finishLearningSession(context, "left")).catch(() => {});
  }, []);

  function closePrompt(action: PromptAction) {
    const p = prompt;
    setPrompt(null);
    if (!p) return;
    void api.respondToLearningPrompt(learning, p.id, { action }).catch(() => {});
    if (action === "pause" && activeVideoId) setCommand({ id: Date.now(), videoId: activeVideoId, kind: "pause" });
    const r = p.recall;
    if (!r) return;
    if (action === "replay") setCommand({ id: Date.now(), videoId: r.videoId, kind: "seek", t: r.replayFrom });
    if (action === "rewatch") {
      const index = items.findIndex((it) => it.kind === "video" && it.ku.videoId === r.videoId);
      if (index >= 0) {
        list.current?.scrollToIndex({ index, animated: true });
        setCommand({ id: Date.now(), videoId: r.videoId, kind: "seek", t: r.replayFrom });
      }
    }
  }

  // FlatList needs the same function for its whole life
  const [onViewable] = useState(() => ({ viewableItems }: { viewableItems: { index?: number | null; isViewable: boolean }[] }) => {
    const first = viewableItems.find((v) => v.isViewable);
    if (first?.index != null) setActiveIndex(first.index);
  });

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }} onLayout={(e) => setHeight(e.nativeEvent.layout.height)}>
      {height > 0 ? (
        <FlatList
          ref={list}
          data={items}
          keyExtractor={(item) => (item.kind === "video" ? `${item.ku.id}:${item.ku.videoUri ?? "demo"}` : "end")}
          pagingEnabled
          scrollEnabled={!blocked && !prompt}
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
                active={index === activeIndex && focused && foreground && windowFocused && !prompt}
                speed={speed}
                onSpeed={setSpeed}
                onBlockSwipe={setBlocked}
                command={index === activeIndex ? command : null}
              />
            ) : (
              <View style={{ height }}>{end}</View>
            )
          }
        />
      ) : null}
      {prompt ? (
        <EngagementPrompt
          key={prompt.id}
          prompt={prompt}
          onAnswer={(answer) => { void api.respondToLearningPrompt(learning, prompt.id, { answer }).catch(() => {}); }}
          onDone={closePrompt}
        />
      ) : null}
    </View>
  );
}
