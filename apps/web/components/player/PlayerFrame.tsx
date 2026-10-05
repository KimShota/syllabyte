"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { Video } from "@/lib/types";
import { VideoSources } from "./VideoSources";

export interface PlayerHandle {
  seek(t: number): void;
  play(): void;
  pause(): void;
  time(): number;
  playing(): boolean;
}

/**
 * The 9:16 frame and its caption band (plan Q3, Q17). Nothing is drawn over the video: the
 * captions sit in a band below it. Captions come from the sidecar VTT through a hidden
 * <track>, so they can be switched off and the Manim visuals are never covered.
 *
 * The checkpoint is detected on every animation frame while playing, not on `timeupdate`
 * (which fires about 4 times a second and would overshoot the pause point).
 */
export const PlayerFrame = forwardRef<
  PlayerHandle,
  {
    video: Video;
    captionsOn: boolean;
    rate: number;
    /** true until the quick check has been shown, answered or skipped */
    checkpointArmed: boolean;
    onCheckpoint: () => void;
    onEnded: () => void;
    onTick: (t: number, playing: boolean) => void;
    onUserEvent: (kind: "play" | "pause" | "seek", t: number, from?: number) => void;
  }
>(function PlayerFrame({ video, captionsOn, rate, checkpointArmed, onCheckpoint, onEnded, onTick, onUserEvent }, ref) {
  const el = useRef<HTMLVideoElement>(null);
  const raf = useRef(0);
  const [caption, setCaption] = useState("");
  const [failed, setFailed] = useState(false);
  const armed = useRef(checkpointArmed);
  const programmatic = useRef(false);
  const ignoreSeek = useRef(false); // seeks the player makes itself are not the student's, and are not logged
  const lastSeekFrom = useRef(0);
  armed.current = checkpointArmed;

  useImperativeHandle(ref, () => ({
    seek: (t) => {
      if (el.current) el.current.currentTime = Math.max(0, Math.min(t, video.duration_s));
    },
    play: () => void el.current?.play().catch(() => undefined),
    pause: () => {
      programmatic.current = true;
      el.current?.pause();
    },
    time: () => el.current?.currentTime ?? 0,
    playing: () => Boolean(el.current && !el.current.paused && !el.current.ended),
  }));

  useEffect(() => {
    if (el.current) el.current.playbackRate = rate;
  }, [rate, video.id]);

  // Plan Q31: a video that won't load says so and offers a retry, with the poster still showing.
  // <source> errors don't bubble, so listen in the capture phase.
  useEffect(() => {
    const v = el.current;
    if (!v) return;
    const onErr = () => setFailed(true);
    v.addEventListener("error", onErr, true);
    return () => v.removeEventListener("error", onErr, true);
  }, [video.id]);

  // Hidden track: cues load and fire `cuechange`, but the browser draws nothing.
  useEffect(() => {
    const v = el.current;
    if (!v) return;
    let cleanup: (() => void) | undefined;
    const attach = () => {
      cleanup?.();
      const tt = v.textTracks[0];
      if (!tt) return;
      tt.mode = "hidden";
      const onCue = () => {
        const cues = tt.activeCues;
        setCaption(cues && cues.length ? Array.from(cues).map((c) => (c as VTTCue).text).join("\n") : "");
      };
      tt.addEventListener("cuechange", onCue);
      cleanup = () => tt.removeEventListener("cuechange", onCue);
    };
    attach();
    v.addEventListener("loadedmetadata", attach);
    return () => {
      cleanup?.();
      v.removeEventListener("loadedmetadata", attach);
    };
  }, [video.id]);

  // rAF loop: time updates for the scrubber and the exact checkpoint pause.
  useEffect(() => {
    const v = el.current;
    if (!v) return;
    const loop = () => {
      const t = v.currentTime;
      onTick(t, !v.paused && !v.ended);
      if (armed.current && !v.paused && t >= video.checkpoint.t) {
        armed.current = false;
        programmatic.current = true;
        v.pause();
        // Land exactly on the checkpoint only when playback overshot it (a seek past it); in the
        // normal case it is within a frame, and re-seeking would add a bogus "seek" to the log.
        if (t - video.checkpoint.t > 0.25) {
          ignoreSeek.current = true;
          v.currentTime = video.checkpoint.t;
        }
        onCheckpoint();
      }
      raf.current = requestAnimationFrame(loop);
    };
    raf.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [video.id]);

  return (
    <div>
      <div className="player-frame mx-auto aspect-[9/16] max-w-full overflow-hidden rounded-card bg-video">
        <video
          ref={el}
          key={video.id}
          poster={video.poster_url}
          // Test builds use tiny videos and load them whole, so seeking in headless browsers is instant.
          preload={process.env.NEXT_PUBLIC_TEST_WEBM === "1" ? "auto" : "metadata"}
          playsInline
          className="size-full object-contain"
          aria-label={`${video.title} (AI-made video)`}
          onPlay={() => onUserEvent("play", el.current?.currentTime ?? 0)}
          onPause={() => {
            if (programmatic.current) programmatic.current = false;
            else onUserEvent("pause", el.current?.currentTime ?? 0);
          }}
          onSeeked={() => {
            if (ignoreSeek.current) {
              ignoreSeek.current = false;
              return;
            }
            onUserEvent("seek", el.current?.currentTime ?? 0, lastSeekFrom.current);
          }}
          onTimeUpdate={() => {
            if (!el.current?.seeking) lastSeekFrom.current = el.current?.currentTime ?? 0;
          }}
          onEnded={onEnded}
        >
          <VideoSources url={video.video_url} />
          <track kind="captions" srcLang="en" label="English" src={video.vtt_url} />
        </video>
      </div>
      {/* Reserved height so the band never makes the page jump. */}
      {failed ? (
        <div role="alert" className="mx-auto mt-3 flex min-h-[4.25rem] max-w-[420px] items-center justify-between gap-3 rounded-btn bg-gap-bg px-4 py-2.5 text-gap-fg">
          <span className="font-bold">Video didn&apos;t load</span>
          <button
            type="button"
            onClick={() => {
              setFailed(false);
              el.current?.load();
            }}
            className="min-h-11 rounded-btn border-2 border-amber-line bg-surface px-4 font-bold text-ink"
          >
            Try again
          </button>
        </div>
      ) : (
      <div
        aria-live="off"
        data-testid="caption-band"
        className={`mx-auto mt-3 flex min-h-[4.25rem] max-w-[420px] items-center justify-center rounded-btn px-4 py-2.5 text-center text-[17px] font-semibold leading-snug transition-colors ${captionsOn && caption ? "bg-ink text-white" : "bg-ink/[0.06] text-muted"}`}
      >
        {captionsOn ? <span className="whitespace-pre-line">{caption}</span> : <span className="text-meta font-medium">Captions are off</span>}
      </div>
      )}
    </div>
  );
});
