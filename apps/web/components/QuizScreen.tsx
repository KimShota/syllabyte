"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import type { OnboardingItemView } from "@/lib/api/types";
import type { Choice } from "@/lib/types";
import { Screen } from "./AppShell";
import { Button, ChoiceCard, Eyebrow, ProgressSegments, Title } from "./ui/primitives";

/**
 * One question at a time, shared by onboarding (screen 1) and the Week 7 re-check
 * (screen 9b). "Not sure yet" is always offered here (plan Q5). No confidence row: these
 * checks are low-stakes and short.
 */
export function QuizScreen({
  eyebrow, title, subtitle, items, onAnswer, onFinish, onExit, topLeft, topRight, below, finishLabel, demoTrigger,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  items: OnboardingItemView[];
  onAnswer: (itemId: string, choice: Choice, latencyMs: number) => Promise<void>;
  onFinish: () => Promise<void>;
  onExit: () => void;
  topLeft: ReactNode;
  topRight?: (index: number) => ReactNode;
  below?: ReactNode;
  finishLabel: string;
  demoTrigger?: boolean;
}) {
  const [index, setIndex] = useState(0);
  const shownAt = useRef(0); // set when each question appears (effect below)
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    shownAt.current = Date.now();
  }, [index]);

  const view = items[Math.min(index, items.length - 1)];
  if (!view) return null;
  const { item } = view;
  const last = index === items.length - 1;

  return (
    <Screen>
      <div className="mb-6 flex items-center justify-between">
        {topLeft}
        {topRight?.(index)}
      </div>
      <Eyebrow {...(demoTrigger ? { "data-demo-trigger": true } : {})}>{eyebrow}</Eyebrow>
      <Title className="mt-1">{title}</Title>
      <p className="mt-2 text-body text-muted">{subtitle}</p>

      <ProgressSegments total={items.length} current={index} className="mt-5" />
      <p className="mt-3 font-bold">Question {index + 1} of {items.length}</p>

      <section aria-labelledby="q-stem" className="mt-4 rounded-card border border-line bg-surface p-5">
        <p className="eyebrow !text-primary">{view.topic_title}</p>
        <h2 id="q-stem" className="mb-4 mt-2 text-card font-extrabold leading-[1.3]">{item.stem}</h2>
        <div role="group" aria-labelledby="q-stem" className="flex flex-col gap-2.5">
          {item.options.map((o, i) => (
            <ChoiceCard key={i} selected={view.answer === i} onClick={() => void onAnswer(item.id, i, Date.now() - shownAt.current)}>
              {o}
            </ChoiceCard>
          ))}
          {item.allows_not_sure && (
            <ChoiceCard notSure selected={view.answer === "not_sure"} onClick={() => void onAnswer(item.id, "not_sure", Date.now() - shownAt.current)}>
              Not sure yet
            </ChoiceCard>
          )}
        </div>
      </section>

      {below && <div className="mt-4">{below}</div>}

      <div className="mt-5 flex gap-3">
        <Button variant="secondary" full={false} className="flex-1" onClick={() => (index === 0 ? onExit() : setIndex(index - 1))}>
          Back
        </Button>
        <Button
          full={false}
          className="flex-[1.6]"
          disabled={view.answer === undefined || busy}
          onClick={async () => {
            if (!last) return setIndex(index + 1);
            setBusy(true);
            await onFinish();
          }}
        >
          {last ? finishLabel : "Next"}
        </Button>
      </div>
    </Screen>
  );
}
