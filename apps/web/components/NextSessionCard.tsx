"use client";

import { useState } from "react";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import type { Item, Jol } from "@/lib/types";
import { Button, ChoiceCard, InfoCard, TextLink } from "./ui/primitives";

const JOL_WORD: Record<Jol, string> = { yes: "Yes", maybe: "Maybe", no: "No" };

/**
 * The next-day check (plan Q13, §3.3.3): one retrieval question with feedback, at a delay.
 * Shows what the student guessed, then what happened, so the guess and the result sit side
 * by side. No "Not sure", no confidence row.
 */
export function NextSessionCard() {
  const { data: card } = useQuery(() => api.getNextSession(), []);
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<number | null>(null);
  const [result, setResult] = useState<{ correct: boolean; item: Item; jol: Jol | null } | null>(null);
  if (!card && !result) return null;
  const jol = (result?.jol ?? card?.task.jol) ?? null;
  const title = card?.video_title ?? "";

  if (result) {
    return (
      <InfoCard eyebrow="Next-day check" tone={result.correct ? "teal" : "plain"} className={result.correct ? "" : "border-2 !border-amber-line"}>
        <p className="font-bold">{result.correct ? "Right." : "Not quite."}{jol && ` You said ${JOL_WORD[jol]}.`}</p>
        <p className="mt-1">{result.item.options[result.item.correct_index]}</p>
        <p className="mt-2 text-ink/85">{result.item.explanation}</p>
        <div className="mt-3">
          <Button
            variant="secondary"
            onClick={() => {
              setResult(null);
              setChoice(null);
              setOpen(false);
            }}
          >
            Done
          </Button>
        </div>
      </InfoCard>
    );
  }

  return (
    <InfoCard eyebrow="Next-day check">
      <p>
        You watched <strong>{title}</strong>.{jol && <> You said <strong>{JOL_WORD[jol]}</strong> when asked if you could explain it.</>} Try one question?
      </p>
      {!open ? (
        <div className="mt-3 flex items-center gap-4">
          <Button full={false} onClick={() => setOpen(true)}>Try it</Button>
          <TextLink tone="muted" onClick={() => void api.dismissNextSession(card!.task.id)}>Not now</TextLink>
        </div>
      ) : (
        <div className="mt-4">
          <p className="mb-3 text-card font-extrabold leading-[1.3]" id="ns-stem">{card!.item.stem}</p>
          <div role="group" aria-labelledby="ns-stem" className="flex flex-col gap-2.5">
            {card!.item.options.map((o, i) => (
              <ChoiceCard key={i} selected={choice === i} onClick={() => setChoice(i)}>{o}</ChoiceCard>
            ))}
          </div>
          <div className="mt-3">
            <Button
              disabled={choice === null}
              onClick={async () => setResult(await api.answerNextSession(card!.task.id, choice!))}
            >
              Check my answer
            </Button>
          </div>
        </div>
      )}
    </InfoCard>
  );
}
