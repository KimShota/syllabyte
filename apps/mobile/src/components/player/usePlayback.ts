import { useCallback, useEffect, useState } from "react";
import { useEventListener } from "expo";
import { useVideoPlayer, type VideoPlayer } from "expo-video";
import type { Ku } from "@/data/types";

const TICK_S = 0.25;

// expo-video is driven by assigning to the player; these keep that out of the component body.
function configure(p: VideoPlayer) {
  p.timeUpdateEventInterval = TICK_S;
  p.loop = false;
}
function setRate(p: VideoPlayer, rate: number) {
  p.playbackRate = rate;
}
function setPosition(p: VideoPlayer, t: number) {
  p.currentTime = t;
}

/**
 * One page's playback. With a rendered file (`ku.videoUri`) it drives expo-video; without one it runs a
 * clock so the motion-graphic frame, captions, scrubber and transcript still behave like a video.
 */
export function usePlayback(ku: Ku, { active, hold, rate }: { active: boolean; hold: boolean; rate: number }) {
  const hasVideo = !!ku.videoUri;
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [prevActive, setPrevActive] = useState(active);
  const ended = time >= ku.durationS - 0.05;

  // reaching the end pauses; leaving the page and coming back starts it again
  if (active !== prevActive) {
    setPrevActive(active);
    if (active && ended) {
      setTime(0);
      setPlaying(true);
    }
  }

  const player = useVideoPlayer(ku.videoUri ?? null, configure);

  useEventListener(player, "timeUpdate", ({ currentTime }) => {
    if (hasVideo) setTime(currentTime);
  });
  useEventListener(player, "playToEnd", () => {
    if (hasVideo) {
      setTime(ku.durationS);
      setPlaying(false);
    }
  });

  const running = active && playing && !hold && !ended;

  useEffect(() => {
    if (!hasVideo) return;
    if (running) {
      if (player.currentTime >= ku.durationS - 0.1) setPosition(player, 0);
      player.play();
    } else player.pause();
  }, [hasVideo, running, player, ku.durationS]);

  useEffect(() => {
    if (hasVideo) setRate(player, rate);
  }, [hasVideo, rate, player]);

  useEffect(() => {
    if (hasVideo || !running) return;
    const id = setInterval(() => setTime((t) => Math.min(ku.durationS, t + TICK_S * rate)), TICK_S * 1000);
    return () => clearInterval(id);
  }, [hasVideo, running, rate, ku.durationS]);

  const seek = useCallback(
    (t: number) => {
      const clamped = Math.max(0, Math.min(ku.durationS, t));
      setTime(clamped);
      if (hasVideo) setPosition(player, clamped);
      if (clamped < ku.durationS) setPlaying(true);
    },
    [hasVideo, ku.durationS, player],
  );

  const toggle = useCallback(() => {
    if (ended) seek(0);
    else setPlaying((p) => !p);
  }, [ended, seek]);

  return { player: hasVideo ? player : null, time, playing: playing && !ended, ended, seek, toggle };
}
