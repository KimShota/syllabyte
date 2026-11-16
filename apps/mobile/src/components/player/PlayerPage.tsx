import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Animated, Pressable, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { setStatusBarHidden } from "expo-status-bar";
import { VideoView } from "expo-video";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Glow } from "../Glow";
import { Icon, type IconName } from "../Icon";
import { T } from "../T";
import { QuickCheck } from "./QuickCheck";
import { MisconceptionCheck } from "./MisconceptionCheck";
import type { ReadyClip } from "./misconceptionFeed";
import { SceneView } from "./SceneView";
import { useAutoHide } from "./useAutoHide";
import { usePlayback } from "./usePlayback";
import { api } from "@syllabyte/core/api/client";
import { track } from "@syllabyte/core/events";
import { formatTime } from "@/data/selectors";
import type { Ku } from "@/data/types";
import { SPEEDS, speedLabel, useQuery, type Speed } from "@/state/app";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

import type { LearningContext } from "@syllabyte/core/learning";
import { useLearningPlayback } from "./useLearningPlayback";

/** Something the feed asks the page on screen to do (an automatic prompt's action); `id` makes each one new. */
export type PlayerCommand = { id: number; videoId: string; kind: "seek"; t: number } | { id: number; videoId: string; kind: "pause" };

export function PlayerPage({
  ku,
  learning,
  eyebrow,
  height,
  active,
  speed,
  onSpeed,
  onBlockSwipe,
  command,
  onBusy,
  misconception,
}: {
  ku: Ku;
  learning: LearningContext;
  misconception?: { ready: ReadyClip; completed: boolean; onComplete: () => void };
  /** for the page on screen only */
  command?: PlayerCommand | null;
  /** for the page on screen only: whether its video is in progress (playing, or its quick check open), so the feed
   *  holds back anything that would interrupt it */
  onBusy?: (busy: boolean) => void;
  eyebrow: string;
  height: number;
  active: boolean;
  speed: Speed;
  onSpeed: (s: Speed) => void;
  /** the quick check is waiting for an answer: the feed must not swipe away */
  onBlockSwipe: (blocked: boolean) => void;
}) {
  const insets = useSafeAreaInsets();
  const [speedOpen, setSpeedOpen] = useState(false);
  const videoId = ku.videoId;
  const variant = useQuery(async () => (videoId && !misconception ? api.getVariant(videoId) : null), [videoId, !!misconception]);
  // the quick check interrupts the video the first time it reaches the checkpoint, and never again once answered
  const [check, setCheck] = useState<"waiting" | "open" | "closed">("waiting");
  const [answered, setAnswered] = useState(false);
  const checkOpen = check === "open";
  const pb = usePlayback(ku, { active, hold: checkOpen, rate: speed });
  const cp = variant?.video.checkpoint;
  const checkDue = !!variant && !variant.checkpoint_answered && !!cp;
  if (active && check === "waiting" && checkDue && pb.time >= cp!.t) setCheck("open");
  // A misconception clip uses this same player, with its own follow-up only after the video ends.
  if (active && misconception && !misconception.completed && check === "waiting" && pb.ended) {
    setCheck(misconception.ready.clip.check_item ? "open" : "closed");
  }
  const markAnswered = useCallback(() => setAnswered(true), []);
  const blocked = active && checkOpen && (!!misconception || !answered);
  useEffect(() => {
    if (active) onBlockSwipe(blocked);
  }, [active, blocked, onBlockSwipe]);
  // once per opening: keyed on the item, not the checkpoint object, which a refetch of the variant replaces
  const shownItem = checkOpen ? cp?.item_id : undefined;
  useEffect(() => {
    if (shownItem) track("checkpoint_shown", { type: "item", id: shownItem });
  }, [shownItem]);

  const playbackSave = useLearningPlayback(learning, videoId, pb.measurement, pb.restartMeasurement, active && !checkOpen && !misconception);
  const clipFinished = useRef(false);
  useEffect(() => {
    if (!active || !misconception || misconception.completed || clipFinished.current || !pb.ended) return;
    if (misconception.ready.clip.check_item && check !== "closed") return;
    clipFinished.current = true;
    misconception.onComplete();
  }, [active, misconception, pb.ended, check]);

  const busy = (pb.playing && !pb.ended) || checkOpen;
  useEffect(() => {
    onBusy?.(busy);
  }, [onBusy, busy]);

  const { seek, pause } = pb;
  const done = useRef(0);
  useEffect(() => {
    // a command waits for its own video: "rewatch" scrolls back first, then seeks
    if (!command || command.id === done.current || command.videoId !== videoId) return;
    done.current = command.id;
    if (command.kind === "seek") seek(command.t);
    else pause();
  }, [command, seek, pause, videoId]);

  // how far in the student got (drives "pick up where you left off"), saved when they swipe away or leave
  const reached = useRef(0);
  useEffect(() => {
    reached.current = Math.max(reached.current, pb.time);
  }, [pb.time]);
  useEffect(() => {
    if (!active || !videoId) return;
    return () => {
      if (reached.current > 0) void api.recordProgress(videoId, reached.current, ku.durationS).catch(() => {});
    };
  }, [active, videoId, ku.durationS]);

  const [prevActive, setPrevActive] = useState(active);
  if (active !== prevActive) {
    setPrevActive(active);
    if (!active) {
      setSpeedOpen(false);
      if (checkOpen && answered) setCheck("closed");
    }
  }

  // the centre play/pause glyph: always shown while paused, flashes briefly on resume
  const glyph = useState(() => new Animated.Value(0))[0];
  useEffect(() => {
    if (!pb.playing) Animated.timing(glyph, { toValue: 1, duration: 120, useNativeDriver: true }).start();
    else
      Animated.sequence([
        Animated.timing(glyph, { toValue: 1, duration: 80, useNativeDriver: true }),
        Animated.delay(700),
        Animated.timing(glyph, { toValue: 0, duration: 300, useNativeDriver: true }),
      ]).start();
  }, [pb.playing, glyph]);

  // while it plays untouched, the controls fade away
  const [scrubbing, setScrubbing] = useState(false);
  const controls = useAutoHide({ active, pinned: !pb.playing || speedOpen || scrubbing || checkOpen });
  const shown = controls.shown;
  const chrome = useState(() => new Animated.Value(1))[0];
  useEffect(() => {
    Animated.timing(chrome, { toValue: shown ? 1 : 0, duration: shown ? 160 : 450, useNativeDriver: true }).start();
  }, [shown, chrome]);
  useEffect(() => {
    if (active) setStatusBarHidden(!shown, "fade");
  }, [active, shown]);
  const hideable = { opacity: chrome };
  const touchable = shown ? "box-none" : "none";

  return (
    <View
      style={{ height, backgroundColor: colors.player.bg, overflow: "hidden" }}
      onStartShouldSetResponderCapture={() => {
        controls.touched();
        return false;
      }}
    >
      <LinearGradient colors={["#0a0a0a", "#18181b", "#000"]} style={StyleSheet.absoluteFill} />
      <AmbientGlow />

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={!shown ? "Show controls" : pb.playing ? "Pause" : pb.ended ? "Replay" : "Play"}
        onPress={() => {
          if (speedOpen) setSpeedOpen(false);
          else if (!shown) controls.reveal();
          else pb.toggle();
        }}
        style={[StyleSheet.absoluteFill, styles.surface]}
      >
        {pb.player ? (
          <VideoView player={pb.player} nativeControls={false} contentFit="contain" style={StyleSheet.absoluteFill} />
        ) : (
          <SceneView ku={ku} />
        )}
        <Animated.View style={[styles.centerGlyph, { opacity: glyph }]} pointerEvents="none">
          <Icon name={pb.ended ? "replay" : pb.playing ? "pause" : "play-arrow"} size={36} color="#fff" />
        </Animated.View>
      </Pressable>

      {playbackSave.failed && !checkOpen ? (
        <Pressable accessibilityRole="button" onPress={() => { void playbackSave.flush(); }} style={{ position: "absolute", top: insets.top + 72, left: 16, right: 16, padding: 12, backgroundColor: "#18181b" }}>
          <T color="#fff">Playback progress could not be saved. Tap to retry.</T>
        </Pressable>
      ) : null}

      {checkOpen && variant ? (
        <QuickCheck
          variant={variant}
          learning={learning}
          topInset={insets.top + 72}
          onAnswered={markAnswered}
          onContinue={() => setCheck("closed")}
          onRewatch={() => {
            track("rewatch_part", { type: "video", id: variant.video.id }, { from: variant.video.checkpoint.rewatch_from });
            pb.seek(variant.video.checkpoint.rewatch_from);
            setCheck("closed");
          }}
        />
      ) : null}

      {checkOpen && misconception?.ready.clip.check_item ? (
        <MisconceptionCheck
          learning={learning}
          requestId={misconception.ready.request.id}
          stem={misconception.ready.clip.check_item.stem}
          options={misconception.ready.clip.check_item.options}
          savedAnswer={misconception.ready.request.follow_up}
          correctIndex={misconception.ready.clip.check_item.correct_index}
          explanation={misconception.ready.clip.check_item.explanation}
          topInset={insets.top + 72}
          onDone={() => setCheck("closed")}
        />
      ) : null}

      <Animated.View style={[styles.top, hideable]} pointerEvents={touchable}>
        <LinearGradient colors={["rgba(0,0,0,0.8)", "rgba(0,0,0,0.4)", "transparent"]} style={[styles.topBar, { paddingTop: insets.top + 12 }]} pointerEvents={touchable}>
          <GlassButton icon="arrow-back" label="Go back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} />
          <Pressable accessibilityRole="button" accessibilityLabel="Student profile" onPress={() => router.push("/profile")} style={styles.glassBtn}>
            <View style={styles.avatarDot}>
              <Icon name="person" size={16} color="#fff" />
            </View>
          </Pressable>
        </LinearGradient>
      </Animated.View>

      {checkOpen ? null : (
        <Animated.View style={[styles.rail, { bottom: insets.bottom + 128 }, hideable]} pointerEvents={touchable}>
          <RailItem label="Speed">
            <Pressable accessibilityRole="button" accessibilityLabel={`Playback speed, ${speedLabel(speed)}`} onPress={() => setSpeedOpen((o) => !o)} style={styles.railBtn}>
              <T variant="codeSm" color={colors.secondaryContainer} style={{ fontSize: 11, fontFamily: fonts.monoBold, letterSpacing: 0 }}>
                {speedLabel(speed)}
              </T>
            </Pressable>
            {speedOpen ? (
              <View style={styles.speedMenu} accessibilityRole="menu">
                {SPEEDS.map((s) => (
                  <Pressable
                    key={s}
                    accessibilityRole="menuitem"
                    accessibilityState={{ selected: s === speed }}
                    onPress={() => {
                      onSpeed(s);
                      setSpeedOpen(false);
                    }}
                    style={[styles.speedOpt, s === speed && { backgroundColor: colors.primary }]}
                  >
                    <T variant="codeSm" color={s === speed ? "#fff" : "#cbd5e1"} style={{ fontSize: 11, fontFamily: s === speed ? fonts.monoSemibold : fonts.mono }}>
                      {speedLabel(s)}
                    </T>
                  </Pressable>
                ))}
              </View>
            ) : null}
          </RailItem>
        </Animated.View>
      )}

      {checkOpen ? null : (
        <View style={[styles.footer, { paddingBottom: insets.bottom + 8 }]} pointerEvents="box-none">
          <Animated.View style={[StyleSheet.absoluteFill, hideable]} pointerEvents="none">
            <LinearGradient colors={["transparent", "rgba(0,0,0,0.85)", "#000"]} style={StyleSheet.absoluteFill} />
          </Animated.View>
          <Animated.View style={hideable} pointerEvents={touchable}>
            <View style={styles.meta}>
              <T variant="codeSm" color={colors.secondaryContainer} style={{ fontSize: 11, fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 }}>
                {eyebrow}
              </T>
              <T variant="cardTitle" color="#fff" style={{ fontFamily: fonts.bold, fontSize: 18, lineHeight: 24 }} accessibilityRole="header">
                {ku.shortTitle}
              </T>
            </View>
            <Scrubber time={pb.time} duration={ku.durationS} mark={checkDue && check === "waiting" ? cp!.t : null} onSeek={pb.seek} onScrubbing={setScrubbing} />
          </Animated.View>
        </View>
      )}

    </View>
  );
}

/** Two soft colour pools behind the video (the design's blurred auras). */
function AmbientGlow() {
  return (
    <>
      <Glow size={460} color={colors.primary} opacity={0.35} style={{ top: -130, left: -170 }} />
      <Glow size={380} color={colors.secondaryFixedDim} opacity={0.18} style={{ bottom: 90, right: -190 }} />
    </>
  );
}

function GlassButton({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={styles.glassBtn}>
      <Icon name={icon} size={20} color="#fff" />
    </Pressable>
  );
}

function RailItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View style={styles.railItem}>
      {children}
      <T variant="codeSm" color="rgba(255,255,255,0.8)" style={{ fontSize: 10, letterSpacing: 0 }} importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </T>
    </View>
  );
}

function Scrubber({
  time,
  duration,
  mark,
  onSeek,
  onScrubbing,
}: {
  time: number;
  duration: number;
  /** where the quick check waits, if it hasn't been answered */
  mark: number | null;
  onSeek: (t: number) => void;
  onScrubbing: (on: boolean) => void;
}) {
  const [width, setWidth] = useState(1);
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? (duration ? time / duration : 0);
  const fraction = (x: number) => Math.min(1, Math.max(0, x / width));

  return (
    <View style={{ gap: 4, paddingBottom: 4 }}>
      <View
        onStartShouldSetResponder={() => true}
        onResponderTerminationRequest={() => false}
        onResponderGrant={(e) => {
          onScrubbing(true);
          setDrag(fraction(e.nativeEvent.locationX));
        }}
        onResponderMove={(e) => setDrag(fraction(e.nativeEvent.locationX))}
        onResponderRelease={() => {
          if (drag !== null) onSeek(drag * duration);
          setDrag(null);
          onScrubbing(false);
        }}
        onResponderTerminate={() => {
          setDrag(null);
          onScrubbing(false);
        }}
        onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
        style={styles.scrubHit}
        accessible
        accessibilityRole="adjustable"
        accessibilityLabel="Video position"
        accessibilityValue={{ text: `${formatTime(time)} of ${formatTime(duration)}` }}
        accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
        onAccessibilityAction={(e) => onSeek(time + (e.nativeEvent.actionName === "increment" ? 10 : -10))}
      >
        <View style={styles.scrubTrack} pointerEvents="none">
          <View style={[styles.scrubFill, { width: `${shown * 100}%` }]} />
          {mark !== null && duration ? <View style={[styles.mark, { left: `${(mark / duration) * 100}%` }]} /> : null}
          <View style={[styles.knob, { left: `${shown * 100}%` }, drag !== null && { transform: [{ scale: 1.25 }] }]} />
        </View>
      </View>
      <View style={styles.times}>
        <T variant="codeSm" color="#cbd5e1" style={{ fontSize: 11 }}>
          {formatTime(drag !== null ? drag * duration : time)}
        </T>
        <T variant="codeSm" color="#94a3b8" style={{ fontSize: 11 }}>
          {formatTime(duration)}
        </T>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  surface: { alignItems: "center", justifyContent: "center" },
  centerGlyph: {
    position: "absolute",
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: "rgba(0,0,0,0.4)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
    alignItems: "center",
    justifyContent: "center",
  },
  top: { position: "absolute", top: 0, left: 0, right: 0 },
  topBar: { paddingHorizontal: 16, paddingBottom: 24, flexDirection: "row", justifyContent: "space-between" },
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
  avatarDot: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  rail: { position: "absolute", right: 14, alignItems: "center", gap: 14, zIndex: 5 },
  railItem: { alignItems: "center", gap: 4 },
  railBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "rgba(0,0,0,0.5)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
    alignItems: "center",
    justifyContent: "center",
    ...shadow.float,
  },
  speedMenu: {
    position: "absolute",
    right: 58,
    bottom: 0,
    width: 92,
    padding: 6,
    gap: 4,
    borderRadius: radius.xl,
    backgroundColor: "rgba(23,23,23,0.96)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
    ...shadow.float,
  },
  speedOpt: { paddingHorizontal: 8, paddingVertical: 6, borderRadius: radius.md },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: 16, paddingTop: 64 },
  meta: { marginRight: 56, marginBottom: 12, gap: 4 },
  scrubHit: { height: 28, justifyContent: "center" },
  scrubTrack: { height: 6, borderRadius: 3, backgroundColor: "rgba(255,255,255,0.2)" },
  scrubFill: { height: 6, borderRadius: 3, backgroundColor: colors.primary },
  knob: { position: "absolute", top: -4, width: 14, height: 14, marginLeft: -7, borderRadius: 7, backgroundColor: "#fff", ...shadow.card },
  times: { flexDirection: "row", justifyContent: "space-between" },
  mark: { position: "absolute", top: -3, width: 3, height: 12, marginLeft: -1.5, borderRadius: 1.5, backgroundColor: colors.secondaryContainer },
});
