"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Loading, Screen } from "@/components/AppShell";
import { ChangeLevelSheet } from "@/components/LevelSheets";
import { CheckpointPanel } from "@/components/player/CheckpointPanel";
import { AboutSheet, NotesSheet, ReceiptSheet, ReportSheet, TranscriptSheet } from "@/components/player/PlayerSheets";
import { PlayerFrame, type PlayerHandle } from "@/components/player/PlayerFrame";
import { Info, Notes as NotesIcon, Pause, Play, Transcript as TranscriptIcon, Captions } from "@/components/ui/icons";
import { BackButton, Chip, Eyebrow, InfoCard, StatusBadge } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import { track } from "@/lib/events";
import { fmtClock } from "@/lib/util";
import { useGate } from "@/lib/useGate";

const RATES = [1, 1.25, 1.5, 0.75]; // capped at 1.5x: the cost is small to there and significant by 2x (Tharumalingam 2025)
type Sheet = "receipt" | "about" | "report" | "transcript" | "notes" | null;

/** One player per video: the key remounts it, so every video starts with fresh playback and check state. */
export function WatchView() {
  const sp = useSearchParams();
  const vid = sp.get("v");
  return <WatchBody key={vid ?? "none"} vid={vid} initialSheet={(sp.get("sheet") as Sheet) ?? null} />;
}

function WatchBody({ vid, initialSheet }: { vid: string | null; initialSheet: Sheet }) {
  const ready = useGate("onboarded");
  const router = useRouter();
  const toast = useToast();
  const { data: variant } = useQuery(async () => (vid ? api.getVariant(vid) : undefined), [vid]);
  const { data: me } = useQuery(() => api.getMe(), []);
  const { data: pl } = useQuery(() => api.getPlaylist(), []);

  const frame = useRef<PlayerHandle>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [phase, setPhase] = useState<"watching" | "check">("watching");
  const [armed, setArmed] = useState(true);
  const [sheet, setSheet] = useState<Sheet>(initialSheet);
  const [changeKu, setChangeKu] = useState<string | null>(null);
  const [fullNote, setFullNote] = useState(false);
  const ended = useRef(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // The quick check sits under the controls: bring it into view when the video pauses on it.
  useEffect(() => {
    if (phase === "check") panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [phase]);

  const captionsOn = me?.settings.captions ?? true;

  const onTick = useCallback((t: number, p: boolean) => {
    setTime(t);
    setPlaying(p);
  }, []);

  // How far the student has got, every 5 s of playback and when they leave: a video stopped early goes back to
  // the top of the playlist to pick up again (plan D13).
  const latest = useRef({ t: 0, id: "", dur: 0 });
  const recorded = useRef(-1);
  useEffect(() => {
    if (!variant) return;
    latest.current = { t: time, id: variant.video.id, dur: variant.video.duration_s };
    const bucket = Math.floor(time / 5);
    if (!playing || bucket === recorded.current) return;
    recorded.current = bucket;
    void api.recordProgress(variant.video.id, time, variant.video.duration_s);
  }, [time, playing, variant]);
  useEffect(
    () => () => {
      const { t, id, dur } = latest.current;
      if (id && t > 0) void api.recordProgress(id, t, dur);
    },
    [],
  );

  const toggle = useCallback(() => {
    if (!frame.current) return;
    if (frame.current.playing()) frame.current.pause();
    else frame.current.play();
  }, []);

  // Keyboard (plan Q17): Space/K, ←/→ ±5 s, C, T, N. Ignored inside inputs and dialogs.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (t?.closest?.("input, textarea, select, [contenteditable], [role=dialog]")) return;
      const k = e.key.toLowerCase();
      if (k === "k" || (k === " " && t === document.body)) { e.preventDefault(); toggle(); }
      else if (e.key === "ArrowRight") frame.current?.seek((frame.current.time() ?? 0) + 5);
      else if (e.key === "ArrowLeft") frame.current?.seek((frame.current.time() ?? 0) - 5);
      else if (k === "c") void api.updateSettings({ captions: !captionsOn });
      else if (k === "t") openSheet("transcript");
      else if (k === "n") openSheet("notes");
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toggle, captionsOn]);

  function openSheet(s: Exclude<Sheet, null>) {
    if (s !== "transcript") frame.current?.pause();
    if (s === "transcript") track("transcript_opened", { type: "video", id: vid ?? "" });
    if (s === "receipt") track("receipt_opened", { type: "video", id: vid ?? "" });
    if (s === "about") track("about_opened", { type: "video", id: vid ?? "" });
    setSheet(s);
  }

  if (!ready || !variant || !vid) return <Loading />;
  const v = variant.video;
  const entry = pl ? [...pl.cards, ...pl.skipped].find((c) => c.video_id === v.id) : undefined;
  const cp = v.checkpoint;

  const resume = () => {
    setPhase("watching");
    frame.current?.play();
  };

  return (
    <Screen wide>
      <div className="grid gap-x-10 gap-y-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:grid-rows-[auto_auto_1fr] lg:[grid-template-areas:'frame_head''frame_controls''frame_panel']">
        {/* header + chips */}
        <header className="lg:[grid-area:head]">
          <div className="flex items-center gap-3">
            <BackButton href="/playlist" label="Back to your playlist" />
            <div className="min-w-0 flex-1">
              <Eyebrow data-demo-trigger>
                {variant.position ? `Video ${variant.position.index + 1} of ${variant.position.total}` : "Video"}
              </Eyebrow>
              <Chip className="mt-1 !border-primary !text-primary">AI-made</Chip>
            </div>
            <button type="button" onClick={() => openSheet("about")} aria-label="About this video" className="grid size-12 place-items-center rounded-full hover:bg-ink/5">
              <Info />
            </button>
          </div>
          <h1 className="mt-3 text-card font-extrabold leading-[1.2] tracking-tight">{v.short_title}</h1>
          <button
            type="button"
            onClick={() => openSheet("receipt")}
            className="mt-2.5 flex min-h-12 w-full items-center justify-between rounded-btn border-2 border-ok-line bg-new-bg px-4 text-left font-bold text-new-fg"
          >
            <span>Tailored for Level {variant.served_level} · {variant.changes_count} {variant.changes_count === 1 ? "change" : "changes"}</span>
            <span className="underline underline-offset-4 decoration-2">See how</span>
          </button>
          <div className="mt-2"><StatusBadge status={variant.review_status} /></div>
          {fullNote && (
            <InfoCard tone="grey" className="mt-3">Prototype: only one version of this video exists yet, so this is the full version you are already watching. Playing from the start.</InfoCard>
          )}
        </header>

        {/* the frame (video + caption band) */}
        <div className="lg:[grid-area:frame]">
          <PlayerFrame
            ref={frame}
            video={v}
            captionsOn={captionsOn}
            rate={rate}
            checkpointArmed={armed}
            onCheckpoint={() => {
              setArmed(false);
              setPhase("check");
              track("checkpoint_shown", { type: "item", id: cp.item_id });
            }}
            onEnded={async () => {
              if (ended.current) return;
              ended.current = true;
              await api.markWatched(v.id);
              router.push(`/watch/done?v=${encodeURIComponent(v.id)}`);
            }}
            onTick={onTick}
            onUserEvent={(kind, t, from) => {
              if (kind === "play") track("video_play", { type: "video", id: v.id }, { t: Math.round(t * 10) / 10, rate });
              else if (kind === "pause") track("video_pause", { type: "video", id: v.id }, { t: Math.round(t * 10) / 10 });
              else track("video_seek", { type: "video", id: v.id }, { to: Math.round(t * 10) / 10, from: Math.round((from ?? 0) * 10) / 10 });
            }}
          />
        </div>

        {/* controls: under the video on a phone, beside it on a laptop */}
        <div className="lg:[grid-area:controls]">
          <div className="mx-auto flex max-w-[420px] items-center gap-3 lg:mx-0 lg:max-w-none">
            <button type="button" onClick={toggle} aria-label={playing ? "Pause" : "Play"} className="grid size-14 shrink-0 place-items-center rounded-full bg-primary text-white hover:bg-primary-hover">
              {playing ? <Pause size={26} /> : <Play size={26} />}
            </button>
            <div className="relative min-w-0 flex-1">
              <input
                type="range"
                min={0}
                max={v.duration_s}
                step={0.1}
                value={Math.min(time, v.duration_s)}
                onChange={(e) => frame.current?.seek(Number(e.target.value))}
                onKeyDown={(e) => {
                  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                    e.preventDefault();
                    frame.current?.seek((frame.current.time() ?? 0) + (e.key === "ArrowRight" ? 5 : -5));
                  }
                }}
                aria-label="Seek"
                aria-valuetext={`${fmtClock(time)} of ${fmtClock(v.duration_s)}`}
                className="h-11 w-full cursor-pointer accent-primary"
              />
              <span aria-hidden className="pointer-events-none absolute top-1/2 h-4 w-0.5 -translate-y-1/2 bg-ink/60" style={{ left: `${(cp.t / v.duration_s) * 100}%` }} title="Quick check" />
            </div>
            <span className="meta shrink-0" aria-hidden>{fmtClock(time)} / {fmtClock(v.duration_s)}</span>
          </div>

          <div className="mx-auto mt-3 grid max-w-[420px] grid-cols-4 gap-2 lg:mx-0 lg:max-w-none">
            <ControlButton onClick={() => void api.updateSettings({ captions: !captionsOn })} pressed={captionsOn} icon={<Captions size={20} />}>{captionsOn ? "Captions on" : "Captions off"}</ControlButton>
            <ControlButton
              icon={<span className="font-mono text-[15px]">{rate}x</span>}
              onClick={() => {
                const next = RATES[(RATES.indexOf(rate) + 1) % RATES.length];
                setRate(next);
                track("speed_changed", { type: "video", id: v.id }, { rate: next });
              }}
            >
              Speed
            </ControlButton>
            <ControlButton onClick={() => openSheet("transcript")} icon={<TranscriptIcon size={20} />}>Transcript</ControlButton>
            <ControlButton onClick={() => openSheet("notes")} icon={<NotesIcon size={20} />}>Notes</ControlButton>
          </div>
        </div>

        {/* the one panel under the video */}
        <div ref={panelRef} className="scroll-mt-4 lg:[grid-area:panel]" aria-live="polite">
          {phase === "check" && (
            <CheckpointPanel
              key={`${v.id}-cp`}
              variant={variant}
              onContinue={resume}
              onRewatch={() => {
                track("rewatch_part", { type: "video", id: v.id }, { from: cp.rewatch_from });
                frame.current?.seek(cp.rewatch_from);
                resume();
              }}
              onSkip={async () => {
                await api.skipCheckpoint(v.id);
                resume();
              }}
            />
          )}
        </div>
      </div>

      {sheet === "receipt" && (
        <ReceiptSheet
          variant={variant}
          onClose={() => setSheet(null)}
          onFull={() => {
            track("full_version_requested", { type: "video", id: v.id });
            setSheet(null);
            setFullNote(true);
            frame.current?.seek(0);
            frame.current?.play();
          }}
          onWrongLevel={() => {
            setSheet(null);
            setChangeKu(v.ku_id);
          }}
        />
      )}
      {sheet === "about" && (
        <AboutSheet
          variant={variant}
          onClose={() => setSheet(null)}
          onReport={() => openSheet("report")}
          onSkipVideo={
            entry?.entry_id && entry.state !== "skipped"
              ? async () => {
                  await api.skip(entry.entry_id!);
                  toast({
                    message: `Skipped “${v.title}”.`,
                    actions: [{ label: "Undo", onClick: () => void api.undoSkip(entry.entry_id!) }],
                  });
                  router.push("/playlist");
                }
              : null
          }
        />
      )}
      {sheet === "report" && <ReportSheet variant={variant} time={frame.current?.time() ?? time} onClose={() => setSheet(null)} />}
      {sheet === "transcript" && <TranscriptSheet variant={variant} time={time} onSeek={(t) => frame.current?.seek(t)} onClose={() => setSheet(null)} />}
      {sheet === "notes" && <NotesSheet variant={variant} time={time} onSeek={(t) => { frame.current?.seek(t); setSheet(null); }} onClose={() => setSheet(null)} />}
      <ChangeLevelSheet kuId={changeKu} onClose={() => setChangeKu(null)} sourceScreen="receipt" />
    </Screen>
  );
}

function ControlButton({ children, onClick, icon, pressed }: { children: React.ReactNode; onClick: () => void; icon?: React.ReactNode; pressed?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      className={`flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-btn border-2 px-1 text-[13px] font-bold leading-tight hover:border-ink/30 ${pressed ? "border-primary bg-primary-tint" : "border-line bg-surface"}`}
    >
      <span className="grid h-5 place-items-center">{icon}</span>
      <span>{children}</span>
    </button>
  );
}
