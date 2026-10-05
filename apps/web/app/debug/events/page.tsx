"use client";

import { useState } from "react";
import { Screen } from "@/components/AppShell";
import { Button, Eyebrow, Title } from "@/components/ui/primitives";
import { downloadText, sessionLogJson } from "@/lib/api/demo";
import { getState, useEventCount, useHydrated } from "@/lib/store";

/** Live timeline for facilitators (plan Q20): confirms a click produced the right event. */
export default function DebugEvents() {
  useHydrated();
  useEventCount();
  const [filter, setFilter] = useState("");
  const s = getState();
  const rows = [...s.events].reverse().filter((e) => !filter || e.verb.includes(filter) || e.object.id?.includes(filter));
  return (
    <Screen wide>
      <Eyebrow>Facilitator · not part of the product</Eyebrow>
      <Title className="mt-1">Event timeline</Title>
      <p className="mt-2 text-body text-muted">{s.events.length} events{s.participant_code ? ` for ${s.participant_code}` : ""}. Newest first.</p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input aria-label="Filter by verb or id" placeholder="Filter…" value={filter} onChange={(e) => setFilter(e.target.value)} className="min-h-12 rounded-btn border-2 border-line bg-surface px-4" />
        <Button full={false} variant="secondary" onClick={() => downloadText(`session-${s.participant_code ?? "anon"}.json`, sessionLogJson())}>Download JSON</Button>
      </div>
      <ol className="mt-4 flex flex-col gap-2" data-testid="events">
        {rows.map((e) => (
          <li key={e.id} className="rounded-btn border border-line bg-surface px-4 py-2 font-mono text-meta">
            <span className="text-muted">{e.timestamp.slice(11, 19)}</span> <strong>{e.verb}</strong>{" "}
            <span>{e.object.type}{e.object.id ? `:${e.object.id}` : ""}</span>{" "}
            {e.result && <span className="text-muted">{JSON.stringify(e.result)}</span>}
            <span className="block text-muted">{e.context.screen} · {e.context.device} {e.context.orientation} · week {e.context.week}</span>
          </li>
        ))}
      </ol>
    </Screen>
  );
}
