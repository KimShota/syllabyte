"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AdaptiveQuiz } from "@/components/AdaptiveQuiz";
import { Loading } from "@/components/AppShell";
import { LevelPickerSheet } from "@/components/LevelSheets";
import { BackButton, Chip, InfoCard, TextLink } from "@/components/ui/primitives";
import { FIX } from "@/lib/fixtures";
import { LEVEL_NAMES } from "@/lib/logic/levels";
import { useGate } from "@/lib/useGate";

/** The Week 0 baseline: a fixed-length adaptive check across the first lectures (plan D8). */
export default function Onboarding() {
  const ready = useGate("consent");
  const router = useRouter();
  const [pick, setPick] = useState<number | null>(null);
  if (!ready) return <Loading />;

  return (
    <>
      <AdaptiveQuiz
        demoTrigger
        sittingId="week0"
        eyebrow={`${FIX.course.eyebrow} · START`}
        title="A quick check, no grade"
        subtitle={(n) => `${n} questions, about ${Math.max(2, Math.round(n / 3))} minutes. It only tunes your videos. “Not sure” is a fine answer.`}
        onFinished={() => router.push("/onboarding/result")}
        onExit={() => router.push("/consent")}
        finishLabel="See my levels"
        topLeft={(answered) => (answered === 0 ? <BackButton onClick={() => router.push("/consent")} /> : <span aria-hidden className="size-14" />)}
        topRight={(answered) => <TextLink onClick={() => setPick(answered + 1)}>Pick my own level</TextLink>}
        below={(n) => (
          <InfoCard eyebrow={`After question ${n}`}>
            <p>We suggest a start level for each concept. You can review your answers first, then keep them or change any one.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {([1, 2, 3] as const).map((l) => (
                <Chip key={l}>Level {l} · {LEVEL_NAMES[l]}</Chip>
              ))}
            </div>
          </InfoCard>
        )}
      />
      <LevelPickerSheet key={pick ?? "closed"} open={pick !== null} fromQuestion={pick ?? 0} onClose={() => setPick(null)} onPicked={() => router.push("/onboarding/result")} />
    </>
  );
}
