"use client";

import { useState } from "react";
import { api } from "@syllabyte/core/api/client";
import { useQuery } from "@/lib/api/hooks";
import type { Choice } from "@syllabyte/core/types";
import { Button, ChoiceCard, InfoCard, TextLink } from "./ui/primitives";
import { Sheet } from "./ui/Sheet";

const REASONS = [
  { id: "already_know", label: "I already know this" },
  { id: "too_hard", label: "It looks too hard right now" },
  { id: "no_time", label: "No time today" },
  { id: "not_relevant", label: "Not relevant to my course" },
] as const;

/** Screen 3: one-tap reasons that feed the learner model. Optional, never graded. */
export function SkipReasonSheet({ entryId, title, onClose }: { entryId: string | null; title: string; onClose: () => void }) {
  const [reason, setReason] = useState<string | null>(null);
  const [prove, setProve] = useState(false);
  if (!entryId) return null;

  if (prove) return <ProveItSheet entryId={entryId} onClose={onClose} />;

  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      eyebrow="Skipped · optional"
      title="Why skip this one?"
      description="Your reason tunes your playlist and your next check-in. It never affects a grade."
      footer={
        <div className="flex gap-3">
          <Button
            variant="secondary"
            full={false}
            className="flex-1"
            onClick={async () => {
              await api.undoSkip(entryId);
              onClose();
            }}
          >
            Undo skip
          </Button>
          <Button
            full={false}
            className="flex-[1.5]"
            disabled={!reason}
            onClick={async () => {
              await api.setSkipReason(entryId, reason!);
              if (reason === "already_know") setProve(true);
              else onClose();
            }}
          >
            Save reason
          </Button>
        </div>
      }
    >
      <p className="mb-3 font-bold">{title}</p>
      <div role="group" aria-label="Reason" className="flex flex-col gap-2.5">
        {REASONS.map((r) => (
          <ChoiceCard key={r.id} selected={reason === r.id} onClick={() => setReason(r.id)}>{r.label}</ChoiceCard>
        ))}
        <ChoiceCard notSure selected={reason === "rather_not_say"} onClick={() => setReason("rather_not_say")}>Rather not say</ChoiceCard>
      </div>
      <InfoCard tone="grey" title="If you pick “I already know this”" className="mt-4">
        We will offer a one-question check so you can prove it and drop this concept&apos;s level work. You can say no.
      </InfoCard>
    </Sheet>
  );
}

/** "I already know this" → offer one question. Passing leaves the video out; failing puts it back (plan Q12). */
function ProveItSheet({ entryId, onClose }: { entryId: string; onClose: () => void }) {
  const { data: pl } = useQuery(() => api.getPlaylist(), []);
  const videoId = [...(pl?.cards ?? []), ...(pl?.skipped ?? [])].find((c) => c.entry_id === entryId)?.video_id;
  const { data: item } = useQuery(async () => (videoId ? api.getProveIt(videoId) : null), [videoId]);
  const [step, setStep] = useState<"offer" | "ask" | "pass" | "fail">("offer");
  const [choice, setChoice] = useState<Choice | null>(null);

  const copy = {
    offer: { title: "Want to show it?", description: "One question. If you get it, we leave this video out." },
    ask: { title: "One question", description: undefined },
    pass: { title: "Nice", description: "We'll leave this one out." },
    fail: { title: "No problem", description: "It's back in your playlist." },
  }[step];

  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      eyebrow="Prove it"
      title={copy.title}
      description={copy.description}
      footer={
        step === "offer" ? (
          <div className="flex gap-3">
            <Button variant="secondary" full={false} className="flex-1" onClick={onClose}>No thanks</Button>
            <Button full={false} className="flex-1" disabled={!item} onClick={() => setStep("ask")}>Try it</Button>
          </div>
        ) : step === "ask" ? (
          <Button
            disabled={choice === null}
            onClick={async () => {
              const r = await api.answerProveIt(entryId, choice!);
              setStep(r.pass ? "pass" : "fail");
            }}
          >
            Check my answer
          </Button>
        ) : (
          <Button onClick={onClose}>Done</Button>
        )
      }
    >
      {step === "ask" && item && (
        <div>
          <p id="pi-stem" className="mb-3 text-card font-extrabold leading-[1.3]">{item.stem}</p>
          <div role="group" aria-labelledby="pi-stem" className="flex flex-col gap-2.5">
            {item.options.map((o, i) => (
              <ChoiceCard key={i} selected={choice === i} onClick={() => setChoice(i)}>{o}</ChoiceCard>
            ))}
            <ChoiceCard notSure selected={choice === "not_sure"} onClick={() => setChoice("not_sure")}>Not sure yet</ChoiceCard>
          </div>
        </div>
      )}
      {step === "fail" && (
        <TextLink
          onClick={async () => {
            await api.keepSkipped(entryId);
            onClose();
          }}
        >
          Keep it skipped
        </TextLink>
      )}
      {step === "pass" && item && <p className="text-body text-ink/85">{item.explanation}</p>}
    </Sheet>
  );
}
