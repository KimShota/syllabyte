"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loading, Screen } from "@/components/AppShell";
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
  const { data } = useQuery(() => api.getOnboardingResult(), []);
  const [change, setChange] = useState<string | null>(null);
  const [chooseTopic, setChooseTopic] = useState(false);
  const [pickAll, setPickAll] = useState(false);
  const [review, setReview] = useState(false);
  if (!ready || !data) return <Loading />;

  return (
    <Screen>
      <Eyebrow data-demo-trigger>{FIX.course.eyebrow} · YOUR START</Eyebrow>
      <Title className="mt-1">We suggest {levelLabel(data.overall_level)}</Title>
      <p className="mt-2 text-body text-muted">This is our best guess, not a grade. Each topic has its own level, and your videos use it.</p>

      <ul className="mt-6 flex flex-col gap-3">
        {data.topics.map(({ topic, level }) => (
          <li key={topic.id}>
            <Card className={level.not_checked ? "border-dashed border-muted/60" : ""}>
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-card font-bold">{topic.title}</h2>
                <TextLink onClick={() => setChange(topic.id)}>{level.not_checked ? "Set it myself" : "Change"}</TextLink>
              </div>
              {!level.not_checked && (
                <div className="mt-2 flex items-center gap-4">
                  <LevelBar level={level.level} />
                  <span className="font-bold">Level {level.level}</span>
                </div>
              )}
              <p className="mt-3 text-body text-ink/85">{level.source === "student" ? "Set by you." : level.reason}</p>
            </Card>
          </li>
        ))}
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
        <Button variant="secondary" onClick={() => setChooseTopic(true)}>Change a topic</Button>
        <div className="text-center"><TextLink onClick={() => setPickAll(true)}>Pick one level for everything</TextLink></div>
      </div>

      <Sheet open={chooseTopic} onOpenChange={setChooseTopic} eyebrow="Change a topic" title="Which topic?">
        <div role="group" aria-label="Topics" className="flex flex-col gap-2.5">
          {data.topics.map(({ topic, level }) => (
            <ChoiceCard key={topic.id} onClick={() => { setChooseTopic(false); setChange(topic.id); }}>
              <span className="block font-bold">{topic.title}</span>
              <span className="text-meta font-medium text-muted">Level {level.level} · {LEVEL_NAMES[level.level]}</span>
            </ChoiceCard>
          ))}
        </div>
      </Sheet>
      <ChangeLevelSheet topicId={change} onClose={() => setChange(null)} sourceScreen="onboarding_result" />
      <LevelPickerSheet open={pickAll} fromQuestion={data.review.length} onClose={() => setPickAll(false)} onPicked={() => setPickAll(false)} />
    </Screen>
  );
}
