"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loading, Screen } from "@/components/AppShell";
import { LectureLevelList } from "@/components/LectureLevels";
import { ChangeLevelSheet, LevelPickerSheet } from "@/components/LevelSheets";
import { ChevronDown } from "@/components/ui/icons";
import { Button, Card, ChoiceCard, Eyebrow, LevelBar, TextLink, Title } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import { FIX } from "@/lib/fixtures";
import { LEVEL_NAMES, levelLabel } from "@/lib/logic/levels";
import { useGate } from "@/lib/useGate";

export default function OnboardingResult() {
  const ready = useGate("onboarded");
  const router = useRouter();
  const { data } = useQuery(() => api.getStartResult(), []);
  const [change, setChange] = useState<string | null>(null);
  const [chooseKu, setChooseKu] = useState(false);
  const [pickAll, setPickAll] = useState(false);
  const [review, setReview] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  if (!ready || !data) return <Loading />;

  return (
    <Screen>
      <Eyebrow data-demo-trigger>{FIX.course.eyebrow} · YOUR START</Eyebrow>
      <Title className="mt-1">We suggest {levelLabel(data.overall_level)}</Title>
      <p className="mt-2 text-body text-muted">This is our best guess, not a grade. Each concept has its own level, and your videos use it. We check again before each lecture.</p>

      <ul className="mt-6 flex flex-col gap-3">
        {data.lectures.map(({ lecture, rows }) => {
          const counts = ([3, 2, 1] as const).map((l) => [l, rows.filter((r) => r.level.level === l).length] as const).filter(([, n]) => n > 0);
          const unchecked = rows.every((r) => r.level.not_checked);
          const expanded = open === lecture.n;
          return (
            <li key={lecture.n}>
              <Card className={unchecked ? "border-dashed border-muted/60" : ""}>
                <p className="eyebrow">Lecture {lecture.n}</p>
                <h2 className="text-card font-bold">{lecture.title}</h2>
                {!unchecked && (
                  <div className="mt-2 flex items-center gap-4">
                    <LevelBar level={Math.round(rows.reduce((n, r) => n + r.level.level, 0) / rows.length) as 1 | 2 | 3} />
                  </div>
                )}
                <p className="mt-3 text-body text-ink/85">
                  {unchecked
                    ? "Not covered yet. We will check this when its lecture comes up."
                    : counts.map(([l, n]) => `${n} ${n === 1 ? "concept" : "concepts"} at Level ${l}`).join(" · ")}
                </p>
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : lecture.n)}
                  className="mt-3 flex min-h-11 w-full items-center justify-between font-semibold text-primary"
                >
                  {expanded ? "Hide the concepts" : "See each concept"}
                  <ChevronDown className={expanded ? "rotate-180" : ""} />
                </button>
                {expanded && (
                  <div className="mt-3">
                    <LectureLevelList
                      lectures={[{ lecture, rows }]}
                      action={(r) => (r.level.not_checked ? "Set it myself" : "Change")}
                      onAction={setChange}
                    />
                  </div>
                )}
              </Card>
            </li>
          );
        })}
      </ul>

      <button
        type="button"
        aria-expanded={review}
        onClick={() => setReview((r) => !r)}
        className="mt-5 flex min-h-12 w-full items-center justify-between rounded-btn border-2 border-line bg-surface px-5 font-bold"
      >
        Review my answers
        <ChevronDown className={review ? "rotate-180" : ""} />
      </button>
      {review && (
        <ol className="mt-3 flex flex-col gap-3">
          {data.review.map(({ item, choice }, i) => (
            <li key={item.id}>
              <Card>
                <p className="eyebrow !text-primary">Question {i + 1}</p>
                <p className="mt-1 font-bold">{item.stem}</p>
                <p className="mt-2 text-body">
                  <span className="text-muted">You chose: </span>
                  {choice === undefined || choice === "not_sure" ? "Not sure yet" : item.options[choice]}
                </p>
                <p className="text-body">
                  <span className="text-muted">Right answer: </span>
                  {item.options[item.correct_index]}
                </p>
                <p className="mt-2 text-body text-ink/85">{item.explanation}</p>
              </Card>
            </li>
          ))}
        </ol>
      )}

      <div className="mt-6 flex flex-col gap-3">
        <Button
          onClick={async () => {
            await api.keepLevels();
            router.push("/playlist");
          }}
        >
          Keep these levels
        </Button>
        <Button variant="secondary" onClick={() => setChooseKu(true)}>Change a concept</Button>
        <div className="text-center"><TextLink onClick={() => setPickAll(true)}>Pick one level for everything</TextLink></div>
      </div>

      <Sheet open={chooseKu} onOpenChange={setChooseKu} eyebrow="Change a concept" title="Which concept?">
        <div className="flex flex-col gap-5">
          {data.lectures.map(({ lecture, rows }) => (
            <div key={lecture.n} role="group" aria-label={`Lecture ${lecture.n} concepts`} className="flex flex-col gap-2.5">
              <p className="eyebrow">Lecture {lecture.n}</p>
              {rows.map(({ ku, level }) => (
                <ChoiceCard key={ku.id} onClick={() => { setChooseKu(false); setChange(ku.id); }}>
                  <span className="block font-bold">{ku.short_title}</span>
                  <span className="text-meta font-medium text-muted">Level {level.level} · {LEVEL_NAMES[level.level]}</span>
                </ChoiceCard>
              ))}
            </div>
          ))}
        </div>
      </Sheet>
      <ChangeLevelSheet kuId={change} onClose={() => setChange(null)} sourceScreen="onboarding_result" />
      <LevelPickerSheet open={pickAll} fromQuestion={data.review.length} onClose={() => setPickAll(false)} onPicked={() => setPickAll(false)} />
    </Screen>
  );
}
