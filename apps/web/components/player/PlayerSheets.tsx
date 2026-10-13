"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button, ChoiceCard, InfoCard, StatusBadge, TextLink } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import type { ReportCategory, TailoringKind, VariantView } from "@/lib/types";
import { fmtClock, fmtMinutes } from "@/lib/util";

const KIND_LABEL: Record<TailoringKind, string> = { left_out: "Left out", added: "Added", set_to: "Set to" };
const KIND_CLS: Record<TailoringKind, string> = {
  left_out: "border border-line bg-surface text-ink",
  added: "bg-new-bg text-new-fg",
  set_to: "bg-refresher-bg text-refresher-fg",
};

/** Screen 5. The "what" comes from the video's level skeleton; the "why" is a template over the student's own answers. */
export function ReceiptSheet({ variant, onClose, onFull, onWrongLevel }: { variant: VariantView; onClose: () => void; onFull: () => void; onWrongLevel: () => void }) {
  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      eyebrow="How this video was tailored"
      title={`${variant.video.short_title}, for Level ${variant.served_level}`}
      description={
        variant.made_level !== null && variant.made_level !== variant.level
          ? `Made when you were at Level ${variant.made_level} on this concept. You are now Level ${variant.level}. A video is made once, so it keeps its level; new videos use your new one.`
          : `Made from your Level ${variant.level} on this concept and your last answers. You can undo any of it.`
      }
      footer={
        <div className="flex flex-col gap-2.5">
          <Button onClick={onFull}>Show the full version ({fmtMinutes(variant.video.duration_s)})</Button>
          <Button variant="secondary" onClick={onClose}>Back to the video</Button>
          <div className="text-center"><TextLink onClick={onWrongLevel}>This level is wrong for me</TextLink></div>
        </div>
      }
    >
      <ul className="flex flex-col gap-3">
        {variant.tailoring.map((r, i) => (
          <li key={i} className="rounded-card bg-ink/[0.045] p-4">
            <p className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-0.5 text-meta font-bold ${KIND_CLS[r.kind]}`}>{KIND_LABEL[r.kind]}</span>
              <span className="font-bold">{r.what}</span>
            </p>
            <p className="mt-1.5 text-body text-ink/80">{r.why}</p>
          </li>
        ))}
        {variant.fallback_note && (
          <li className="rounded-card border border-dashed border-muted/60 p-4">
            <p className="font-bold">{variant.fallback_note}</p>
            <p className="mt-1 text-body text-ink/80">This is a prototype: only one version of each video exists so far.</p>
          </li>
        )}
      </ul>
      <p className="mt-4 text-body text-muted">When your answers are mixed, we lean toward including more help, not less.</p>
    </Sheet>
  );
}

/** The ⓘ sheet: source, AI disclosure, review status, and the trust actions. */
export function AboutSheet({ variant, onClose, onReport, onSkipVideo }: { variant: VariantView; onClose: () => void; onReport: () => void; onSkipVideo: (() => void) | null }) {
  const slides = variant.video.source_slides;
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} eyebrow="About this video" title={variant.video.title}>
      <div className="flex flex-col gap-4">
        <InfoCard eyebrow="Source">
          Slides · {slides.length === 1 ? `slide ${slides[0]}` : slides.join(", ")} · Lecture {variant.video.lecture_n}: {variant.lecture_title}
          <p className="mt-2 text-ink/80">The animation is AI-generated from these slides. It was not made by your instructor.</p>
        </InfoCard>
        <div><StatusBadge status={variant.review_status} /></div>
        <div className="flex flex-col gap-2.5">
          <Link href={`/watch/claims?v=${variant.video.id}`} className="inline-flex min-h-14 w-full items-center justify-center rounded-btn bg-primary px-6 font-bold text-white">
            Check the claims in this video
          </Link>
          <Button variant="secondary" onClick={onReport}>Report an error in this video</Button>
          {onSkipVideo && <Button variant="secondary" onClick={onSkipVideo}>Skip this video</Button>}
        </div>
      </div>
    </Sheet>
  );
}

const CATEGORIES: { id: ReportCategory; label: string }[] = [
  { id: "fact", label: "A fact is wrong" },
  { id: "picture", label: "The picture doesn't match what's said" },
  { id: "captions", label: "Captions or audio are off" },
  { id: "layout", label: "Text is cut off or overlaps" },
  { id: "other", label: "Something else" },
];

function parseClock(s: string): number | null {
  const m = /^(\d+):(\d{1,2})$/.exec(s.trim());
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  return /^\d+$/.test(s.trim()) ? Number(s.trim()) : null;
}

export function ReportSheet({ variant, time, onClose }: { variant: VariantView; time: number; onClose: () => void }) {
  const [cat, setCat] = useState<ReportCategory | null>(null);
  const [at, setAt] = useState(fmtClock(time));
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);
  const t = parseClock(at);

  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      eyebrow="Report an error"
      title={sent ? "Thanks" : "What's wrong?"}
      description={sent ? "Your instructor will see this with the clip." : "Until it's checked, the video shows a note that a student flagged it."}
      footer={sent ? <Button onClick={onClose}>Done</Button> : <Button disabled={!cat || t === null} onClick={async () => { await api.postReport(variant.video.id, cat!, t ?? 0, note.trim()); setSent(true); }}>Send report</Button>}
    >
      {sent ? (
        cat === "fact" && <Link href={`/watch/claims?v=${variant.video.id}`} className="font-semibold text-primary underline underline-offset-4 decoration-2">Point to the exact claim</Link>
      ) : (
        <div className="flex flex-col gap-4">
          <div role="group" aria-label="What's wrong" className="flex flex-col gap-2.5">
            {CATEGORIES.map((c) => <ChoiceCard key={c.id} selected={cat === c.id} onClick={() => setCat(c.id)}>{c.label}</ChoiceCard>)}
          </div>
          <label className="block">
            <span className="mb-1 block font-bold">At <span className="font-medium text-muted">(minutes:seconds)</span></span>
            <input value={at} onChange={(e) => setAt(e.target.value)} inputMode="numeric" className="min-h-12 w-32 rounded-btn border-2 border-line bg-surface px-4 text-body" aria-invalid={t === null} />
          </label>
          <label className="block">
            <span className="mb-1 block font-bold">Anything to add? <span className="font-medium text-muted">(optional)</span></span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={400} className="w-full rounded-btn border-2 border-line bg-surface px-4 py-3 text-body" />
          </label>
        </div>
      )}
    </Sheet>
  );
}

/** Described transcript: narration with *[Visual: …]* lines, so the Manim visuals are readable without sight. */
export function TranscriptSheet({ variant, time, onSeek, onClose }: { variant: VariantView; time: number; onSeek: (t: number) => void; onClose: () => void }) {
  const rows = variant.video.transcript;
  let current = 0;
  rows.forEach((r, i) => { if (r.t <= time) current = i; });
  const cur = useRef<HTMLLIElement>(null);
  useEffect(() => cur.current?.scrollIntoView({ block: "nearest" }), [current]);
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} eyebrow="Transcript" title={variant.video.short_title} description="Tap a line to jump there.">
      <ol className="flex flex-col gap-1">
        {rows.map((r, i) => (
          <li key={i} ref={i === current ? cur : undefined}>
            {r.visual && <p className="mb-1 mt-3 rounded-btn bg-ink/[0.045] px-3 py-2 text-meta italic text-ink/80">[Visual: {r.visual}]</p>}
            <button type="button" aria-current={i === current ? "true" : undefined} onClick={() => onSeek(r.t)} className={`flex w-full gap-3 rounded-btn px-3 py-2.5 text-left text-body ${i === current ? "bg-primary-tint font-semibold" : "hover:bg-ink/5"}`}>
              <span className="meta w-10 shrink-0 pt-0.5">{fmtClock(r.t)}</span>
              <span>{r.narration}</span>
            </button>
          </li>
        ))}
      </ol>
    </Sheet>
  );
}

/** Opening this pauses the video (plan Q17). Notes are private and stamped with the video time. */
export function NotesSheet({ variant, time, onSeek, onClose }: { variant: VariantView; time: number; onSeek: (t: number) => void; onClose: () => void }) {
  const { data: notes } = useQuery(() => api.listNotes(variant.video.id), [variant.video.id]);
  const [text, setText] = useState("");
  const [stamp] = useState(time); // the video time when the sheet was opened
  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      eyebrow="Notes · private"
      title={variant.video.short_title}
      footer={<Button disabled={!text.trim()} onClick={async () => { await api.addNote(variant.video.id, stamp, text.trim()); setText(""); }}>Save note at {fmtClock(stamp)}</Button>}
    >
      <label className="block">
        <span className="sr-only">Your note</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="What do you want to remember?" className="w-full rounded-btn border-2 border-line bg-surface px-4 py-3 text-body" />
      </label>
      {notes && notes.length > 0 && (
        <ul className="mt-4 flex flex-col gap-2">
          {notes.map((n) => (
            <li key={n.id} className="flex gap-3 rounded-btn bg-ink/[0.045] px-3 py-2.5 text-body">
              <button type="button" onClick={() => onSeek(n.video_t)} className="meta shrink-0 underline underline-offset-4" aria-label={`Jump to ${fmtClock(n.video_t)}`}>{fmtClock(n.video_t)}</button>
              <span>{n.text}</span>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
