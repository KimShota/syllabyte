"use client";

import clsx from "clsx";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Loading, Screen } from "@/components/AppShell";
import { BackButton, Button, Card, Eyebrow, InfoCard, StatusBadge, TextLink, Title } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { api } from "@syllabyte/core/api/client";
import { useQuery } from "@/lib/api/hooks";
import { VideoSources } from "@/components/player/VideoSources";
import { track } from "@/lib/events";
import type { ClaimView } from "@syllabyte/core/types";
import { fmtClock } from "@syllabyte/core/util";
import { useGate } from "@/lib/useGate";

/** Screen 6, slides-only (plan Q11): every claim opens the slide it came from, with the AI video's matching part beside it. */
export function ClaimsView() {
  const ready = useGate("onboarded");
  const router = useRouter();
  const vid = useSearchParams().get("v");
  const { data: variant } = useQuery(async () => (vid ? api.getVariant(vid) : undefined), [vid]);
  const [open, setOpen] = useState<ClaimView | null>(null);
  if (!ready || !variant || !vid) return <Loading />;
  const v = variant.video;

  return (
    <Screen>
      <div className="mb-6 flex items-center justify-between gap-3">
        <BackButton href={`/watch?v=${vid}`} label="Back to the video" />
        <StatusBadge status={variant.review_status} />
      </div>
      <Eyebrow>{v.short_title} · {variant.claims.length} claims</Eyebrow>
      <Title className="mt-1">Check it against the slides</Title>
      <p className="mt-2 text-body text-muted">The video is AI-made. Open the slide behind any claim and tell us if it does not match.</p>

      <ul className="mt-6 flex flex-col gap-3">
        {variant.claims.map((c) => (
          <li key={c.idx}>
            <ClaimCard claim={c} videoId={vid} onOpen={() => { setOpen(c); track("claim_slide_viewed", { type: "claim", id: `${vid}:${c.idx}` }); }} />
          </li>
        ))}
      </ul>

      <InfoCard className="mt-4" eyebrow="What happens to a report">
        It goes to your instructor with the claim and the slide. Until it is checked, the video shows a note that a student flagged it.
      </InfoCard>
      <div className="mt-5"><Button onClick={() => router.push(`/watch?v=${vid}`)}>Back to the video</Button></div>

      {open && <SlideSheet claim={open} video={{ url: v.video_url, poster: v.poster_url, duration: v.duration_s }} onClose={() => setOpen(null)} />}
    </Screen>
  );
}

function ClaimCard({ claim, videoId, onOpen }: { claim: ClaimView; videoId: string; onOpen: () => void }) {
  const [note, setNote] = useState(claim.note);
  const slides = claim.slide_refs.map((r) => r.slide_number);
  const set = (verdict: "matches" | "mismatch", n = note) => void api.postClaimVerdict(videoId, claim.idx, verdict, n);
  return (
    <Card className={claim.verdict ? "border-2 border-primary" : ""}>
      <p className="text-[18px] font-bold leading-[1.3]">{claim.text}</p>
      <p className="meta mt-2">Slides · {slides.length === 1 ? `slide ${slides[0]}` : slides.join(", ")}</p>
      <div className="mt-1"><TextLink onClick={onOpen}>View slide</TextLink></div>
      <div role="group" aria-label="Does this match the slide?" className="mt-3 flex gap-2">
        <button
          type="button"
          aria-pressed={claim.verdict === "matches"}
          onClick={() => set("matches")}
          className={clsx("min-h-12 flex-1 rounded-btn border-2 px-3 font-bold", claim.verdict === "matches" ? "border-ok-line bg-ok-bg" : "border-line bg-surface hover:border-ink/30")}
        >
          Matches
        </button>
        <button
          type="button"
          aria-pressed={claim.verdict === "mismatch"}
          onClick={() => set("mismatch")}
          className={clsx("min-h-12 flex-1 rounded-btn border-2 px-3 font-bold", claim.verdict === "mismatch" ? "border-amber-line bg-gap-bg text-gap-fg" : "border-line bg-surface hover:border-ink/30")}
        >
          Does not match
        </button>
      </div>
      {claim.verdict === "mismatch" && (
        <label className="mt-3 block">
          <span className="mb-1 block font-bold">What doesn&apos;t match? <span className="font-medium text-muted">(optional)</span></span>
          <input value={note} onChange={(e) => setNote(e.target.value)} onBlur={() => set("mismatch")} maxLength={160} className="min-h-12 w-full rounded-btn border-2 border-line bg-surface px-4 text-body" />
        </label>
      )}
    </Card>
  );
}

/** The slide (tap to zoom), its text for screen readers, and a mini-player for just this claim's segment. */
function SlideSheet({ claim, video, onClose }: { claim: ClaimView; video: { url: string; poster: string; duration: number }; onClose: () => void }) {
  const [zoom, setZoom] = useState(false);
  const ref = useRef<HTMLVideoElement>(null);
  const [start, end] = claim.span;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const stop = () => {
      if (el.currentTime >= end) el.pause();
    };
    el.addEventListener("timeupdate", stop);
    return () => el.removeEventListener("timeupdate", stop);
  }, [end]);

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} eyebrow="Claim" title={claim.text}>
      <div className="flex flex-col gap-5">
        {claim.slide_urls.map((s) => (
          <figure key={s.slide}>
            <div className="max-h-[46dvh] overflow-auto rounded-btn border border-line bg-white">
              <button type="button" onClick={() => setZoom((z) => !z)} aria-label={zoom ? "Zoom out" : "Zoom in"} className="block">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={s.url} alt={`Slide ${s.slide}`} className={clsx("h-auto max-w-none", zoom ? "w-[220%]" : "w-full")} />
              </button>
            </div>
            <figcaption className="meta mt-2">Slide {s.slide} · tap the slide to zoom</figcaption>
            {s.text && <p className="mt-2 whitespace-pre-line rounded-btn bg-ink/[0.045] px-4 py-3 text-meta text-ink/85"><span className="font-bold">Slide text: </span>{s.text}</p>}
          </figure>
        ))}
        <div>
          <p className="mb-2 font-bold">What the video says here</p>
          <div className="mx-auto h-64 w-36 overflow-hidden rounded-btn bg-video">
            <video ref={ref} poster={video.poster} preload="metadata" playsInline className="size-full object-contain" aria-label="This part of the video"><VideoSources url={video.url} /></video>
          </div>
          <div className="mt-3">
            <Button variant="secondary" onClick={() => { if (ref.current) { ref.current.currentTime = start; void ref.current.play(); } }}>
              Play this part ({fmtClock(start)}–{fmtClock(end)})
            </Button>
          </div>
        </div>
      </div>
    </Sheet>
  );
}
