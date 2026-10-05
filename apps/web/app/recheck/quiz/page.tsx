"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loading } from "@/components/AppShell";
import { QuizScreen } from "@/components/QuizScreen";
import { Close } from "@/components/ui/icons";
import { Chip } from "@/components/ui/primitives";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import { FIX } from "@/lib/fixtures";
import { useGate } from "@/lib/useGate";

export default function RecheckQuiz() {
  const ready = useGate("onboarded");
  const router = useRouter();
  const { data: items } = useQuery(() => api.getRecheckItems(), []);
  if (!ready || !items) return <Loading />;
  return (
    <QuizScreen
      demoTrigger
      eyebrow={`${FIX.course.eyebrow} · WEEK 7 CHECK-IN`}
      title="Re-check your level"
      subtitle={`${items.length} questions, about 3 minutes. Not graded. “Not sure yet” is a fine answer.`}
      items={items}
      onAnswer={(id, c, ms) => api.answerRecheck(id, c, ms)}
      onFinish={async () => {
        await api.finishRecheck();
        router.push("/recheck/results");
      }}
      onExit={() => router.push("/recheck")}
      finishLabel="See what changed"
      topLeft={<Link href="/playlist" aria-label="Close" className="grid size-14 place-items-center rounded-full bg-surface shadow-[0_0_0_1px_var(--color-line)]"><Close /></Link>}
      topRight={() => <Chip className="!px-4 !py-2">Not graded</Chip>}
    />
  );
}
