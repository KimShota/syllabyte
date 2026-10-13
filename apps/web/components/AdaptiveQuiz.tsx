"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import type { Choice } from "@/lib/types";
import { Loading, Screen } from "./AppShell";
import { Button, ChoiceCard, Eyebrow, ProgressSegments, Title } from "./ui/primitives";

/**
 * One adaptive sitting, one question at a time (plan/per-ku-profiling-plan.md D8, D9): the Week 0 baseline and the
 * check before a lecture. Each question is chosen from the answers before it, so there is no going back: a choice
 * can change until Next, then it is locked. "Not sure yet" is always offered and counts toward the length but not
 * toward the estimate. No confidence row: these checks are low-stakes and short.
 */
export function AdaptiveQuiz({
  sittingId, eyebrow, title, subtitle, finishLabel, onFinished, onExit, topLeft, topRight, below, demoTrigger,
}: {
  sittingId: string;
  eyebrow: string;
  title: string;
  subtitle: (total: number) => string;
  finishLabel: string;
  onFinished: () => void;
  onExit: () => void;
  /** gets how many questions are answered, so a Back arrow can go away once the check has started */
  topLeft: (answered: number) => ReactNode;
  topRight?: (answered: number) => ReactNode;
  below?: (total: number) => ReactNode;
  demoTrigger?: boolean;
}) {
  const { data: view } = useQuery(() => api.getSitting(sittingId), [sittingId]);
  const [sel, setSel] = useState<{ itemId: string; choice: Choice } | null>(null);
  const [busy, setBusy] = useState(false);
  const shownAt = useRef(0);
  const itemId = view?.current?.item.id;
  useEffect(() => {
    shownAt.current = Date.now();
  }, [itemId]);

  if (!view) return <Loading />;
  const cur = view.current;
  const picked = cur && sel?.itemId === cur.item.id ? sel.choice : null;
  const last = view.answered + 1 >= view.total;

  async function finish() {
    setBusy(true);
    await api.finishSitting(sittingId);
    onFinished();
  }

  async function next() {
    if (!cur || picked === null) return;
    setBusy(true);
    await api.answerSitting(sittingId, cur.item.id, picked, Date.now() - shownAt.current);
    const after = await api.getSitting(sittingId);
    if (after.current === null) return finish();
    setBusy(false);
  }

  return (
    <Screen>
      <div className="mb-6 flex items-center justify-between">
        {topLeft(view.answered)}
        {topRight?.(view.answered)}
      </div>
      <Eyebrow {...(demoTrigger ? { "data-demo-trigger": true } : {})}>{eyebrow}</Eyebrow>
      <Title className="mt-1">{title}</Title>
      <p className="mt-2 text-body text-muted">{subtitle(view.total)}</p>
      <p className="mt-1 text-meta text-muted">Each question adapts to your last answer, so you can&apos;t go back.</p>

      {cur ? (
        <>
          <ProgressSegments total={view.total} current={view.answered} className="mt-5" />
          <p className="mt-3 font-bold">Question {view.answered + 1} of {view.total}</p>

          <section aria-labelledby="q-stem" className="mt-4 rounded-card border border-line bg-surface p-5">
            <p className="eyebrow !text-primary">{cur.lecture_title}</p>
            <h2 id="q-stem" className="mb-4 mt-2 text-card font-extrabold leading-[1.3]">{cur.item.stem}</h2>
            <div role="group" aria-labelledby="q-stem" className="flex flex-col gap-2.5">
              {cur.item.options.map((o, i) => (
                <ChoiceCard key={i} selected={picked === i} onClick={() => setSel({ itemId: cur.item.id, choice: i })}>
                  {o}
                </ChoiceCard>
              ))}
              {cur.item.allows_not_sure && (
                <ChoiceCard notSure selected={picked === "not_sure"} onClick={() => setSel({ itemId: cur.item.id, choice: "not_sure" })}>
                  Not sure yet
                </ChoiceCard>
              )}
            </div>
          </section>

          {below && <div className="mt-4">{below(view.total)}</div>}

          <div className="mt-5 flex gap-3">
            {view.answered === 0 && (
              <Button variant="secondary" full={false} className="flex-1" onClick={onExit}>
                Back
              </Button>
            )}
            <Button full={false} className="flex-[1.6]" disabled={picked === null || busy} onClick={() => void next()}>
              {last ? finishLabel : "Next"}
            </Button>
          </div>
        </>
      ) : (
        <div className="mt-6">
          <Button disabled={busy} onClick={() => void finish()}>{finishLabel}</Button>
        </div>
      )}
    </Screen>
  );
}
