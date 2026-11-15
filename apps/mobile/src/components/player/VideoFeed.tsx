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
import { sendLearning } from "@/state/learningOutbox";
import { EngagementPrompt } from "./EngagementPrompt";
import { clipDecision } from "./clipTiming";
import { MisconceptionClipCard, type ReadyClip } from "./MisconceptionClipCard";
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
/** How often an open feed tells the server its session is still going (well inside the 10-minute idle gap). */
const KEEP_OPEN_MS = 60_000;
/** How often an open feed asks whether a misconception clip is ready (one takes about a minute to make). */
const CLIP_POLL_MS = 10_000;
/** A clip put off with "Later" is offered again at the next move to another video, this many times in a feed visit. */
const CLIP_REOFFERS = 1;

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
  // misconception clips (plan: "Misconception clips"): made on demand, offered as soon as they are ready, never mid-video
  const [clips, setClips] = useState<ReadyClip[]>([]);
  const [clip, setClip] = useState<ReadyClip | null>(null);
  const [laterCount, setLaterCount] = useState<Record<string, number>>({});
  const [deferred, setDeferred] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
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
        void whenSaved().then(() => sendLearning("finishLearningSession", context, "gap"));
        return;
      }
      void whenSaved()
        .then(() => sendLearning("recordLearningAway", context, { id: uid("away"), seconds, videoId }))
        .then(() => (videoId ? api.evaluateLearningBoundary(context, { reason: "return", videoId }) : null))
        .then((p) => { if (p && current.current === context) setPrompt(p); }, () => {});
    });
    const blur = AppState.addEventListener("blur", () => setWindowFocused(false));
    const focus = AppState.addEventListener("focus", () => setWindowFocused(true));
    return () => { change.remove(); blur.remove(); focus.remove(); };
  }, []);

  // Misconception clips: ask every few seconds while the feed is open and in front
  useEffect(() => {
    if (!(focused && foreground)) return;
    let alive = true;
    const poll = () => {
      api.getMisconceptionClips(current.current).then((list) => { if (alive) setClips(list); }, () => {});
    };
    poll();
    const timer = setInterval(poll, CLIP_POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [focused, foreground]);

  // When to show a ready clip (clipTiming.ts), decided while rendering: state that follows other state.
  const [clipIndex, setClipIndex] = useState(activeIndex);
  const moved = clipIndex !== activeIndex;
  if (moved) setClipIndex(activeIndex);
  const decision = clipDecision({ clips, deferred, laterCount, moved, canShow: !clip && !prompt && focused && foreground, busy, reoffers: CLIP_REOFFERS });
  if (decision.deferred !== deferred) setDeferred(decision.deferred as Set<string>);
  if (decision.show) setClip(decision.show);
  // the first time each clip is offered is recorded
  const offeredId = clip?.request.id;
  useEffect(() => {
    if (offeredId) void sendLearning("respondToMisconceptionClip", current.current, offeredId, { offered: true });
  }, [offeredId]);

  function closeClip(action: "watched" | "later") {
    const c = clip;
    setClip(null);
    if (!c) return;
    void sendLearning("respondToMisconceptionClip", learning, c.request.id, { action });
    // a watched clip is never offered again in this visit, even if a check lands before the server has recorded it
    setLaterCount((n) => ({ ...n, [c.request.id]: action === "watched" ? Infinity : (n[c.request.id] ?? 0) + 1 }));
    setDeferred((d) => new Set(d).add(c.request.id));
  }

  // Decision point: leaving the feed ends the session; its reflection, if any, appears by itself (ReflectionSheet).
  useEffect(() => () => {
    const context = current.current;
    void whenSaved().then(() => sendLearning("finishLearningSession", context, "left"));
  }, []);

  // While the feed is open with the app in front, the session stays open however long a video stays paused: only a
  // closed or backgrounded app lets it end as idle. If it ended anyway (no keep-alive got through for 10 minutes), what
  // the student does next belongs to a new session.
  const live = focused && foreground;
  useEffect(() => {
    if (!live) return;
    const ping = () => {
      const context = current.current;
      api.keepLearningSessionOpen(context).then(({ ended }) => {
        if (ended && current.current === context) {
          setPrompt(null);
          setLearning(newSession());
        }
      }, () => {});
    };
    ping();
    const timer = setInterval(ping, KEEP_OPEN_MS);
    return () => clearInterval(timer);
  }, [live]);

  /** Scrolls the feed to a video and starts it from `t` once it is the one on screen. */
  function goTo(videoId: string, t: number) {
    const index = items.findIndex((it) => it.kind === "video" && it.ku.videoId === videoId);
    if (index < 0) return;
    // without animation: scrolling past the videos in between would record them as visits left early
    list.current?.scrollToIndex({ index, animated: false });
    setCommand({ id: Date.now(), videoId, kind: "seek", t });
  }

  function closePrompt(action: PromptAction, target?: string) {
    const p = prompt;
    setPrompt(null);
    if (!p) return;
    void sendLearning("respondToLearningPrompt", learning, p.id, target ? { action, target } : { action });
    if ((action === "jump" || action === "watch") && target) {
      goTo(target, 0);
      return;
    }
    if (action === "pause" && activeVideoId) setCommand({ id: Date.now(), videoId: activeVideoId, kind: "pause" });
    const r = p.recall;
    if (!r) return;
    if (action === "replay") setCommand({ id: Date.now(), videoId: r.videoId, kind: "seek", t: r.replayFrom });
    if (action === "rewatch") goTo(r.videoId, r.replayFrom);
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
          scrollEnabled={!blocked && !prompt && !clip}
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
                active={index === activeIndex && focused && foreground && windowFocused && !prompt && !clip}
                speed={speed}
                onSpeed={setSpeed}
                onBlockSwipe={setBlocked}
                command={index === activeIndex ? command : null}
                onBusy={index === activeIndex ? setBusy : undefined}
              />
            ) : (
              <View style={{ height }}>{end}</View>
            )
          }
        />
      ) : null}
      {clip ? <MisconceptionClipCard key={clip.request.id} ready={clip} learning={learning} onDone={closeClip} /> : null}
      {prompt && !clip ? (
        <EngagementPrompt
          key={prompt.id}
          prompt={prompt}
          feed={items.flatMap((it) => (it.kind === "video" && it.ku.videoId ? [{ videoId: it.ku.videoId, title: it.ku.title }] : []))}
          currentVideoId={activeVideoId}
          onAnswer={(answer) => { void sendLearning("respondToLearningPrompt", learning, prompt.id, { answer }); }}
          onDone={closePrompt}
        />
      ) : null}
    </View>
  );
}
