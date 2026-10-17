"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AdaptiveQuiz } from "@/components/AdaptiveQuiz";
import { Loading } from "@/components/AppShell";
import { Close } from "@/components/ui/icons";
import { Chip } from "@/components/ui/primitives";
import { FIX, lectureByN } from "@syllabyte/core/fixtures";
import { useGate } from "@/lib/useGate";

/** The check before a lecture's videos: new questions on the lecture, plus a few from earlier lectures (plan D8). */
export function CheckView() {
  const ready = useGate("onboarded");
  const router = useRouter();
  const n = Number(useSearchParams().get("l"));
  if (!ready || !Number.isInteger(n) || !FIX.course.lectures.some((l) => l.n === n)) return <Loading />;
  return (
    <AdaptiveQuiz
      demoTrigger
      sittingId={`lecture-${n}`}
      eyebrow={`${FIX.course.eyebrow} · LECTURE ${n} CHECK`}
      title="A quick check before this lecture"
      subtitle={(total) => `${total} questions about “${lectureByN(n).title}” and a few earlier ideas. Not graded. “Not sure” is a fine answer.`}
      finishLabel="Start the lecture"
      onFinished={() => router.push("/playlist")}
      onExit={() => router.push("/playlist")}
      topLeft={() => <Link href="/playlist" aria-label="Close" className="grid size-14 place-items-center rounded-full bg-surface shadow-[0_0_0_1px_var(--color-line)]"><Close /></Link>}
      topRight={() => <Chip className="!px-4 !py-2">Not graded</Chip>}
    />
  );
}
