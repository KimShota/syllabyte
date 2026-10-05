"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loading } from "@/components/AppShell";
import { LevelPickerSheet } from "@/components/LevelSheets";
import { QuizScreen } from "@/components/QuizScreen";
import { BackButton, Chip, InfoCard, TextLink } from "@/components/ui/primitives";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import { FIX } from "@/lib/fixtures";
import { LEVEL_NAMES } from "@/lib/logic/levels";
import { useGate } from "@/lib/useGate";

export default function Onboarding() {
  const ready = useGate("consent");
  const router = useRouter();
  const { data: items } = useQuery(() => api.getOnboardingItems(), []);
  const [pick, setPick] = useState<number | null>(null);
  if (!ready || !items) return <Loading />;
  const n = items.length;

  return (
    <>
      <QuizScreen
        demoTrigger
        eyebrow={`${FIX.course.eyebrow} · START`}
        title="A quick check, no grade"
        subtitle={`${n} questions, about 4 minutes. It only tunes your videos. “Not sure” is a fine answer.`}
        items={items}
        onAnswer={(id, choice, ms) => api.answerOnboarding(id, choice, ms)}
        onFinish={async () => {
          await api.finishOnboarding();
          router.push("/onboarding/result");
        }}
        onExit={() => router.push("/consent")}
        finishLabel="See my levels"
        topLeft={<BackButton onClick={() => router.push("/consent")} />}
        topRight={(i) => <TextLink onClick={() => setPick(i + 1)}>Pick my own level</TextLink>}
        below={
          <InfoCard eyebrow={`After question ${n}`}>
            <p>We suggest a start level. You can review your answers first, then keep it or pick another.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {([1, 2, 3] as const).map((l) => (
                <Chip key={l}>Level {l} · {LEVEL_NAMES[l]}</Chip>
              ))}
            </div>
          </InfoCard>
        }
      />
      <LevelPickerSheet key={pick ?? "closed"} open={pick !== null} fromQuestion={pick ?? 0} onClose={() => setPick(null)} onPicked={() => router.push("/onboarding/result")} />
    </>
  );
}
