"use client";

import Link from "next/link";
import { api } from "@syllabyte/core/api/client";
import { useQuery } from "@/lib/api/hooks";
import { Button, InfoCard } from "./ui/primitives";

/**
 * "What changed and why" (plan D11): levels move only at a lecture boundary, and when they do this says which
 * ones, with a sentence built from the student's own answers. Videos already made keep the level they were made at.
 */
export function LevelUpdatesCard({ showLink = true }: { showLink?: boolean }) {
  const { data: card } = useQuery(() => api.getLevelUpdates(), []);
  if (!card) return null;
  return (
    <InfoCard eyebrow="What changed and why" tone="teal">
      <p className="font-bold">Your levels moved after the “{card.lecture_title}” check.</p>
      <ul className="mt-2 flex flex-col gap-1.5">
        {card.updates.map((u) => (
          <li key={u.ku_id}>{u.reason}</li>
        ))}
      </ul>
      <p className="mt-2 text-meta">Videos already made keep the level they were made at. You can correct any level yourself.</p>
      <div className="mt-3 flex flex-wrap items-center gap-4">
        <Button full={false} onClick={() => void api.dismissLevelUpdates(card.id)}>Got it</Button>
        {showLink && <Link href="/levels" className="inline-flex min-h-11 items-center font-semibold underline underline-offset-4 decoration-2">See my levels</Link>}
      </div>
    </InfoCard>
  );
}
