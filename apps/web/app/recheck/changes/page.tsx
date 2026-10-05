"use client";

import { Loading, Screen } from "@/components/AppShell";
import { BackButton, Eyebrow, Title } from "@/components/ui/primitives";
import { api } from "@/lib/api/client";
import type { DiffRow } from "@/lib/types";
import { useQuery } from "@/lib/api/hooks";
import { useGate } from "@/lib/useGate";

/** Screen 10b: every change the playlist would get, grouped, each with its reason. */
export default function RecheckChanges() {
  const ready = useGate("onboarded");
  const { data } = useQuery(() => api.getProposals(), []);
  if (!ready || !data) return <Loading />;
  const groups: { title: string; rows: DiffRow[] }[] = [
    { title: "New", rows: data.diff.new },
    { title: "Switched level", rows: data.diff.swapped },
    { title: "Removed, already known", rows: data.diff.removed },
  ];
  const total = groups.reduce((n, g) => n + g.rows.length, 0);
  return (
    <Screen>
      <div className="mb-6"><BackButton href="/recheck/results" label="Back to your results" /></div>
      <Eyebrow>Your playlist if you accept</Eyebrow>
      <Title className="mt-1">Every change</Title>
      {total === 0 && <p className="mt-4 text-body text-muted">Nothing would change in your playlist with the choices you have made so far.</p>}
      {groups.map((g) => g.rows.length > 0 && (
        <section key={g.title} className="mt-6" aria-labelledby={`g-${g.title}`}>
          <h2 id={`g-${g.title}`} className="eyebrow mb-2">{g.title} · {g.rows.length}</h2>
          <ul className="flex flex-col gap-2.5">
            {g.rows.map((r) => (
              <li key={r.video_id} className="rounded-card border border-line bg-surface p-4">
                <p className="font-bold">{r.title}</p>
                <p className="meta mt-0.5">{r.topic_title}</p>
                <p className="mt-1 text-body text-ink/85">{r.reason}</p>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </Screen>
  );
}
