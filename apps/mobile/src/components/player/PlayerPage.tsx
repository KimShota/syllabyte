import { useEffect, useRef, useState, type ReactNode } from "react";
import { Animated, Pressable, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { setStatusBarHidden } from "expo-status-bar";
import { VideoView } from "expo-video";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Glow } from "../Glow";
import { Icon, type IconName } from "../Icon";
import { T } from "../T";
import { SceneView } from "./SceneView";
import { StudySheet, activeLine, type StudyMode } from "./StudySheet";
import { useAutoHide } from "./useAutoHide";
import { usePlayback } from "./usePlayback";
import { api } from "@syllabyte/core/api/client";
import { formatTime } from "@/data/selectors";
import type { Ku, Note } from "@/data/types";
import { SPEEDS, speedLabel, useQuery, type Speed } from "@/state/app";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

/** Watched once this share of the video has played. */
const WATCHED_AT = 0.9;

export function PlayerPage({
  ku,
  eyebrow,
  height,
  active,
  speed,
  onSpeed,
  captions,
  onCaptions,
}: {
  ku: Ku;
  eyebrow: string;
  height: number;
  active: boolean;
  speed: Speed;
  onSpeed: (s: Speed) => void;
  captions: boolean;
  onCaptions: (on: boolean) => void;
}) {
  const insets = useSafeAreaInsets();
  const [sheet, setSheet] = useState<StudyMode | null>(null);
  const [speedOpen, setSpeedOpen] = useState(false);
  const pb = usePlayback(ku, { active, hold: sheet !== null, rate: speed });
  const videoId = ku.videoId;
  const notes = useQuery<Note[]>(
    async () => (videoId ? (await api.listNotes(videoId)).map((n) => ({ id: n.id, at: n.video_t, text: n.text })) : []),
    [videoId],
  ) ?? [];
  const noteCount = notes.length;
  const lineIdx = activeLine(ku.transcript, pb.time);
  const caption = lineIdx >= 0 ? ku.transcript[lineIdx].text : null;

  // a view counts once per visit to this page, the first time it passes WATCHED_AT
  const counted = useRef(false);
  useEffect(() => {
    if (!videoId || counted.current || pb.time < ku.durationS * WATCHED_AT) return;
    counted.current = true;
    void api.markWatched(videoId);
  }, [pb.time, ku.durationS, videoId]);

  // how far in the student got (drives "pick up where you left off"), saved when they swipe away or leave
  const reached = useRef(0);
  useEffect(() => {
    reached.current = Math.max(reached.current, pb.time);
  }, [pb.time]);
  useEffect(() => {
    if (!active || !videoId) return;
    return () => {
      if (reached.current > 0) void api.recordProgress(videoId, reached.current, ku.durationS);
    };
  }, [active, videoId, ku.durationS]);

  const [prevActive, setPrevActive] = useState(active);
  if (active !== prevActive) {
    setPrevActive(active);
    if (!active) {
      setSheet(null);
      setSpeedOpen(false);
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

  // while it plays untouched, everything but the video (and captions, if on) fades away
  const [scrubbing, setScrubbing] = useState(false);
  const controls = useAutoHide({ active, pinned: !pb.playing || sheet !== null || speedOpen || scrubbing });
  const shown = controls.shown;
  const chrome = useState(() => new Animated.Value(1))[0];
  const [metaHeight, setMetaHeight] = useState(0);
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

      <Animated.View style={[styles.rail, { bottom: insets.bottom + 128 }, hideable]} pointerEvents={touchable}>
        <RailItem label="Notes">
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Open study notes, ${noteCount} saved`}
            onPress={() => setSheet("notes")}
            style={[styles.railBtn, sheet === "notes" && styles.railBtnOn]}
          >
            <Icon name="edit-note" size={22} color="#fff" />
            {noteCount > 0 ? (
              <View style={styles.badge}>
                <T variant="codeSm" color="#fff" style={{ fontSize: 10, fontFamily: fonts.monoBold, letterSpacing: 0 }}>
                  {noteCount}
                </T>
              </View>
            ) : null}
          </Pressable>
        </RailItem>
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
        <RailItem label="Captions">
          <Pressable
            accessibilityRole="switch"
            accessibilityState={{ checked: captions }}
            accessibilityLabel="Captions"
            onPress={() => onCaptions(!captions)}
            style={[styles.railBtn, captions && { backgroundColor: "rgba(255,255,255,0.2)", borderColor: "rgba(255,255,255,0.3)" }]}
          >
            <T variant="codeSm" color={captions ? colors.secondaryContainer : "rgba(255,255,255,0.5)"} style={{ fontFamily: fonts.monoBold, letterSpacing: 1 }}>
              CC
            </T>
          </Pressable>
        </RailItem>
      </Animated.View>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 8 }]} pointerEvents="box-none">
        <Animated.View style={[StyleSheet.absoluteFill, hideable]} pointerEvents="none">
          <LinearGradient colors={["transparent", "rgba(0,0,0,0.85)", "#000"]} style={StyleSheet.absoluteFill} />
        </Animated.View>
        {captions && caption ? (
          <Animated.View
            style={[styles.caption, { transform: [{ translateY: chrome.interpolate({ inputRange: [0, 1], outputRange: [metaHeight, 0] }) }] }]}
            accessibilityLiveRegion="polite"
            pointerEvents="none"
          >
            <T variant="caption" color="#fff" style={{ fontSize: 13 }}>
              <T variant="codeSm" color={colors.secondaryContainer} style={{ fontFamily: fonts.monoSemibold }}>
                [AI Voice]:{" "}
              </T>
              “{caption}”
            </T>
          </Animated.View>
        ) : null}
        <Animated.View style={hideable} pointerEvents={touchable} onLayout={(e) => setMetaHeight(e.nativeEvent.layout.height)}>
          <View style={styles.meta}>
            <T variant="codeSm" color={colors.secondaryContainer} style={{ fontSize: 11, fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1 }}>
              {eyebrow}
            </T>
            <T variant="cardTitle" color="#fff" style={{ fontFamily: fonts.bold, fontSize: 18, lineHeight: 24 }} accessibilityRole="header">
              {ku.shortTitle}
            </T>
            {ku.transcript.length ? (
              <Pressable accessibilityRole="button" onPress={() => setSheet("transcript")} hitSlop={8} style={styles.transcriptLink}>
                <Icon name="notes" size={14} color="rgba(255,255,255,0.7)" />
                <T variant="caption" color="rgba(255,255,255,0.7)" style={{ fontSize: 12 }}>
                  Transcript
                </T>
              </Pressable>
            ) : null}
          </View>
          <Scrubber time={pb.time} duration={ku.durationS} onSeek={pb.seek} onScrubbing={setScrubbing} />
        </Animated.View>
      </View>

      <StudySheet ku={ku} notes={notes} mode={sheet} time={pb.time} onClose={() => setSheet(null)} onSeek={pb.seek} />
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

function Scrubber({ time, duration, onSeek, onScrubbing }: { time: number; duration: number; onSeek: (t: number) => void; onScrubbing: (on: boolean) => void }) {
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
  railBtnOn: { backgroundColor: colors.primary, borderColor: "rgba(255,255,255,0.3)" },
  badge: {
    position: "absolute",
    top: -4,
    right: -4,
    minWidth: 18,
    height: 18,
    paddingHorizontal: 4,
    borderRadius: 9,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
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
  caption: {
    marginRight: 56,
    marginBottom: 12,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.lg,
    backgroundColor: "rgba(0,0,0,0.75)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
  },
  meta: { marginRight: 56, marginBottom: 12, gap: 4 },
  transcriptLink: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2, alignSelf: "flex-start", minHeight: 24 },
  scrubHit: { height: 28, justifyContent: "center" },
  scrubTrack: { height: 6, borderRadius: 3, backgroundColor: "rgba(255,255,255,0.2)" },
  scrubFill: { height: 6, borderRadius: 3, backgroundColor: colors.primary },
  knob: { position: "absolute", top: -4, width: 14, height: 14, marginLeft: -7, borderRadius: 7, backgroundColor: "#fff", ...shadow.card },
  times: { flexDirection: "row", justifyContent: "space-between" },
});
