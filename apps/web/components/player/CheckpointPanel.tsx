"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { track } from "@/lib/events";
import type { Confidence, VariantView } from "@/lib/types";
import { Button, ChoiceCard, SegmentedRow, TextLink, type ChoiceState } from "@/components/ui/primitives";

const CONF: { value: Confidence; label: string }[] = [
  { value: "guess", label: "Guessing" },
  { value: "pretty", label: "Pretty sure" },
  { value: "certain", label: "Certain" },
];

/**
 * The one quick check per video (plan Q4, Q10, Q29). Order: pick an answer, then "How sure?",
 * and the result appears by itself once both are set (no Submit button). In-video checks have
 * no "Not sure yet": the "Guessing" rating carries that uncertainty without hiding partial
 * knowledge. The video stays paused underneath.
 *
 * Hints by the student's level (Q29): Level 1 shows the hint inline from the start, Level 2
 * has a "Show a hint" link, Level 3 has none. A hint that was visible when the student
 * answered counts as used, and a correct answer after a hint earns half credit at Week 7.
 */
export function CheckpointPanel({
  variant, onContinue, onRewatch, onSkip,
}: {
  variant: VariantView;
  onContinue: () => void;
  onRewatch: () => void;
  onSkip: () => void;
}) {
  const item = variant.checkpoint_item;
  const [choice, setChoice] = useState<number | null>(null);
  const [conf, setConf] = useState<Confidence | null>(null);
  const [hintOpen, setHintOpen] = useState(variant.level === 1);
  const [result, setResult] = useState<{ correct: boolean; queued: boolean } | null>(null);
  const shownAt = useRef(0);
  const sent = useRef(false);
  const headRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    shownAt.current = Date.now();
    headRef.current?.focus();
  }, []);

  useEffect(() => {
    if (choice === null || conf === null || sent.current) return;
    sent.current = true;
    void api
      .postCheckpointAnswer({ videoId: variant.video.id, choice, confidence: conf, hintUsed: hintOpen && Boolean(item.hint), latencyMs: Date.now() - shownAt.current })
      .then((r) => setResult({ correct: r.correct, queued: r.queuedForTomorrow }));
  }, [choice, conf, hintOpen, item.hint, variant.video.id]);

  const revealed = result !== null;
  const stateOf = (i: number): ChoiceState => {
    if (!revealed) return "idle";
    if (i === item.correct_index) return choice === i ? "correct" : "reveal-correct";
    return choice === i ? "wrong" : "dim";
  };

  return (
    <section aria-labelledby="cp-stem" className="slide-in rounded-card border-2 border-primary bg-surface p-5">
      <p className="eyebrow !text-primary">Video paused · quick check</p>
      <h2 id="cp-stem" ref={headRef} tabIndex={-1} className="mb-4 mt-2 text-card font-extrabold leading-[1.3] outline-none">{item.stem}</h2>

      <div role="group" aria-labelledby="cp-stem" className="flex flex-col gap-2.5">
        {item.options.map((o, i) => (
          <ChoiceCard key={i} selected={choice === i} state={stateOf(i)} disabled={revealed} onClick={() => setChoice(i)}>
            {o}
          </ChoiceCard>
        ))}
      </div>

      {choice !== null && !revealed && (
        <div className="slide-in mt-4">
          <p className="mb-2 font-bold" id="conf-label">How sure are you in that answer?</p>
          <SegmentedRow label="How sure are you" value={conf} onChange={setConf} options={CONF} />
        </div>
      )}
      {revealed && conf && <p className="meta mt-3">You said: {CONF.find((c) => c.value === conf)?.label}</p>}

      {!revealed && item.hint && variant.level !== 3 && (
        <div className="mt-4">
          {hintOpen ? (
            <p className="rounded-btn bg-ink/[0.045] px-4 py-3 text-body"><span className="font-bold">Hint: </span>{item.hint}</p>
          ) : (
            <TextLink onClick={() => { setHintOpen(true); track("hint_used", { type: "item", id: item.id }); }}>Show a hint</TextLink>
          )}
        </div>
      )}

      {revealed ? (
        <div className="slide-in mt-4" role="status">
          <p className={`text-card font-extrabold ${result.correct ? "text-new-fg" : "text-gap-fg"}`}>{result.correct ? "Right" : "Not quite"}</p>
          {!result.correct && <p className="mt-1 text-body"><span className="text-muted">Right answer: </span>{item.options[item.correct_index]}</p>}
          <p className="mt-2 text-body text-ink/85">{item.explanation}</p>
          {result.queued && (
            <p className="mt-3 rounded-btn bg-new-bg px-4 py-3 text-body text-new-fg">
              You got it, but you said you were guessing. We&apos;ll check this again tomorrow.
            </p>
          )}
          <div className="mt-4 flex flex-col gap-2.5">
            <Button onClick={onContinue}>Continue video</Button>
            {!result.correct && <Button variant="secondary" onClick={onRewatch}>Rewatch this part</Button>}
          </div>
        </div>
      ) : (
        <div className="mt-4 flex justify-end">
          <TextLink tone="muted" onClick={onSkip}>Skip this check</TextLink>
        </div>
      )}
    </section>
  );
}
