import { useCallback, useEffect, useRef, useState } from "react";
import { useEventListener } from "expo";
import { useVideoPlayer, type VideoPlayer } from "expo-video";
import { PlaybackMeter } from "@syllabyte/core/logic/playback";
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
  const [meter] = useState(() => new PlaybackMeter(ku.durationS, hasVideo ? "video" : "demo"));
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

  const running = active && playing && !hold && !ended;
  // read by the player's event listeners, which only count playback while this page is meant to be playing
  const runningNow = useRef(running);
  useEffect(() => {
    runningNow.current = running;
  }, [running]);

  const player = useVideoPlayer(ku.videoUri ?? null, configure);

  useEventListener(player, "timeUpdate", ({ currentTime }) => {
    if (hasVideo) {
      meter.sample(currentTime, performance.now(), runningNow.current && player.playing && player.status === "readyToPlay", rate);
      setTime(currentTime);
    }
  });
  useEventListener(player, "playToEnd", () => {
    if (hasVideo) {
      meter.sample(ku.durationS, performance.now(), runningNow.current, rate);
      meter.boundary();
      setTime(ku.durationS);
      setPlaying(false);
    }
  });

  // The rate is set first, in the same effect, and play or pause last: on iOS setting a playback rate starts playback, so
  // as its own effect (after this one) it started every page the feed had mounted beside the one on screen, and they
  // all played at once.
  useEffect(() => {
    meter.boundary();
    if (!hasVideo) return;
    meter.sample(player.currentTime, performance.now(), running, rate);
    setRate(player, rate);
    if (running) {
      if (player.currentTime >= ku.durationS - 0.1) setPosition(player, 0);
      player.play();
    } else player.pause();
  }, [hasVideo, running, rate, player, ku.durationS, meter]);

  // And whatever starts a page that is not the one playing (a source that finished loading, the system), it is stopped again.
  useEventListener(player, "playingChange", ({ isPlaying }) => {
    meter.boundary();
    if (hasVideo && isPlaying && !runningNow.current) player.pause();
    if (isPlaying && runningNow.current) meter.sample(player.currentTime, performance.now(), true, rate);
  });

  useEventListener(player, "statusChange", () => { meter.boundary(); });

  // Without a file the stand-in clock is the playback: the meter observes it too, as synthetic ("demo") playback, which
  // the research data keeps apart from real video.
  const shown = useRef(time);
  useEffect(() => {
    shown.current = time;
  }, [time]);
  useEffect(() => {
    if (hasVideo || !running) return;
    meter.sample(shown.current, performance.now(), true, rate);
    const id = setInterval(() => {
      const t = Math.min(ku.durationS, shown.current + TICK_S * rate);
      meter.sample(t, performance.now(), true, rate);
      shown.current = t;
      setTime(t);
    }, TICK_S * 1000);
    return () => clearInterval(id);
  }, [hasVideo, running, rate, ku.durationS, meter]);

  const seek = useCallback(
    (t: number) => {
      meter.boundary();
      const clamped = Math.max(0, Math.min(ku.durationS, t));
      setTime(clamped);
      if (hasVideo) setPosition(player, clamped);
      if (clamped < ku.durationS) setPlaying(true);
    },
    [hasVideo, ku.durationS, player, meter],
  );

  const toggle = useCallback(() => {
    if (ended) seek(0);
    else setPlaying((p) => !p);
  }, [ended, seek]);

  const pause = useCallback(() => setPlaying(false), []);

  const measurement = useCallback(() => meter.snapshot(), [meter]);

  return { measurement, player: hasVideo ? player : null, time, playing: playing && !ended, ended, seek, toggle, pause };
}
