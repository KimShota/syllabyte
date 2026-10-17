"use client";

import { api } from "@syllabyte/core/api/client";
import type { PrecheckView } from "@syllabyte/core/types";
import { InfoCard, LinkButton, TextLink } from "./ui/primitives";

/** The check before a lecture's videos (plan D8): short, adaptive, not graded, and the student can skip it. */
export function PrecheckCard({ check }: { check: PrecheckView }) {
  const started = check.answered > 0;
  return (
    <InfoCard eyebrow={`Before “${check.title}”`} tone="teal">
      <p className="font-bold">A quick check before this lecture.</p>
      <p className="mt-1">
        {check.total} questions, about {Math.max(1, Math.round(check.total / 3))} {Math.round(check.total / 3) <= 1 ? "minute" : "minutes"}. It tunes this lecture&apos;s videos. Not graded.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-4">
        <LinkButton href={`/check?l=${check.lecture_n}`} full={false}>{started ? "Continue the check" : "Start the check"}</LinkButton>
        <TextLink tone="ink" onClick={() => void api.skipSitting(check.sitting_id)}>Not now</TextLink>
      </div>
    </InfoCard>
  );
}
