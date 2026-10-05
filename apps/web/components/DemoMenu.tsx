"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { downloadText, fastOnboard, loadPersona, resetDemo, sessionLogJson, setLogDeclined, setParticipantCode, showEmptyPlaylist, simulateNextDay } from "@/lib/api/demo";
import { FIX } from "@/lib/fixtures";
import { getState, useEventCount, useStoreVersion } from "@/lib/store";
import { Button, SegmentedRow, TextLink } from "./ui/primitives";
import { Sheet } from "./ui/Sheet";

/**
 * Facilitator controls (plan §3.17). Opens with ?demo=1, a 1-second long-press on any
 * course eyebrow, or Ctrl+Alt+D. Hidden from Phase 1+ builds unless NEXT_PUBLIC_DEMO=1.
 */
const ALLOWED = process.env.NEXT_PUBLIC_BACKEND !== "api" || process.env.NEXT_PUBLIC_DEMO === "1";

export function DemoHost() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!ALLOWED) return;
    const fromUrl = new URLSearchParams(window.location.search).get("demo") === "1" ? setTimeout(() => setOpen(true), 0) : null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const clear = () => {
      if (timer) clearTimeout(timer);
      timer = null;
    };
    const down = (e: PointerEvent) => {
      if ((e.target as HTMLElement | null)?.closest?.("[data-demo-trigger]")) timer = setTimeout(() => setOpen(true), 1000);
    };
    const key = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.altKey && e.key.toLowerCase() === "d") setOpen((o) => !o);
    };
    document.addEventListener("pointerdown", down);
    document.addEventListener("pointerup", clear);
    document.addEventListener("pointercancel", clear);
    document.addEventListener("pointermove", clear);
    document.addEventListener("keydown", key);
    return () => {
      if (fromUrl) clearTimeout(fromUrl);
      clear();
      document.removeEventListener("pointerdown", down);
      document.removeEventListener("pointerup", clear);
      document.removeEventListener("pointercancel", clear);
      document.removeEventListener("pointermove", clear);
      document.removeEventListener("keydown", key);
    };
  }, []);
  if (!ALLOWED || !open) return null;
  return <DemoMenu onClose={() => setOpen(false)} />;
}

function DemoMenu({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  useStoreVersion();
  const events = useEventCount();
  const s = getState();
  const [code, setCode] = useState(s.participant_code ?? "");
  const [confirmReset, setConfirmReset] = useState(false);
  const [busy, setBusy] = useState(false);

  async function go(path: string, prep?: () => Promise<void> | void) {
    setBusy(true);
    await prep?.();
    setBusy(false);
    onClose();
    router.push(path);
  }
  const ensureConsent = async () => {
    if (getState().consent === null) await api.postConsent(true);
  };
  const onboarded = async () => {
    if (!getState().onboarding.done) await fastOnboard();
  };
  const first = FIX.videos[0];

  const groups: { title: string; items: { label: string; run: () => Promise<void> }[] }[] = [
    {
      title: "First run",
      items: [
        { label: "Welcome", run: () => go("/welcome") },
        { label: "Consent", run: () => go("/consent") },
        { label: "Onboarding quiz", run: () => go("/onboarding", ensureConsent) },
        { label: "Onboarding result", run: () => go("/onboarding/result", onboarded) },
      ],
    },
    {
      title: "Tabs (onboarding fast-forwarded if needed)",
      items: [
        { label: "Playlist", run: () => go("/playlist", onboarded) },
        { label: "Empty playlist", run: () => go("/playlist", showEmptyPlaylist) },
        { label: "My levels", run: () => go("/levels", onboarded) },
        { label: "Course", run: () => go("/course", onboarded) },
      ],
    },
    {
      title: "Player",
      items: [
        ...FIX.videos.map((v) => ({ label: `Player: ${v.title.split(":")[0]}`, run: () => go(`/watch?v=${v.id}`, onboarded) })),
        { label: "Tailoring receipt", run: () => go(`/watch?v=${first.id}&sheet=receipt`, onboarded) },
        { label: "About this video", run: () => go(`/watch?v=${first.id}&sheet=about`, onboarded) },
        { label: "Claim check", run: () => go(`/watch/claims?v=${first.id}`, onboarded) },
        { label: "Before you move on", run: () => go(`/watch/done?v=${first.id}`, onboarded) },
      ],
    },
    {
      title: "Week 7 (scripted student)",
      items: [
        { label: "Week 7 invite", run: () => go("/recheck", () => loadPersona("invite")) },
        { label: "Week 7 re-check quiz", run: () => go("/recheck/quiz", () => loadPersona("invite")) },
        { label: "Week 7 results", run: () => go("/recheck/results", () => loadPersona("results")) },
        { label: "My levels, Week 7 student", run: () => go("/levels", () => loadPersona("results")) },
      ],
    },
  ];

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} eyebrow="Facilitator only" title="Demo menu" description="Hidden from students. Nothing here is part of the product.">
      <div className="flex flex-col gap-6">
        <section aria-label="Participant">
          <label className="mb-1 block text-body font-bold" htmlFor="pcode">Participant code</label>
          <div className="flex gap-2">
            <input id="pcode" value={code} onChange={(e) => setCode(e.target.value)} placeholder="P03" className="min-h-12 flex-1 rounded-btn border-2 border-line bg-surface px-4 text-body" />
            <Button full={false} variant="secondary" onClick={() => setParticipantCode(code)}>Save</Button>
          </div>
          <p className="meta mt-2">Stamped on every event. {events} events logged this session.</p>
        </section>

        {groups.map((g) => (
          <section key={g.title} aria-label={g.title}>
            <h3 className="eyebrow mb-2">{g.title}</h3>
            <div className="flex flex-wrap gap-2">
              {g.items.map((it) => (
                <button key={it.label} type="button" disabled={busy} onClick={() => void it.run()} className="min-h-11 rounded-full border-2 border-line bg-surface px-4 text-meta font-bold hover:border-primary">
                  {it.label}
                </button>
              ))}
            </div>
          </section>
        ))}

        <section aria-label="Tools" className="flex flex-col gap-3">
          <h3 className="eyebrow">Tools</h3>
          <Button variant="secondary" onClick={() => { simulateNextDay(); onClose(); }}>Simulate next day (+24 h)</Button>
          <div>
            <p className="mb-1 font-bold">Log events even if consent was declined</p>
            <SegmentedRow label="Log declined" value={s.flags.log_declined ? "on" : "off"} onChange={(v) => setLogDeclined(v === "on")} options={[{ value: "on", label: "On (usability sessions)" }, { value: "off", label: "Off (research rule)" }]} />
          </div>
          <Button variant="secondary" onClick={() => downloadText(`session-${s.participant_code ?? "anon"}.json`, sessionLogJson())}>Download session log (JSON)</Button>
          <Button variant="secondary" onClick={() => go("/debug/events")}>Open live event timeline</Button>
          {confirmReset ? (
            <div className="rounded-card bg-gap-bg p-4">
              <p className="mb-3 font-bold text-gap-fg">Clear all demo state and the event log?</p>
              <div className="flex gap-2">
                <Button full={false} className="flex-1" onClick={() => go("/welcome", resetDemo)}>Yes, reset</Button>
                <Button full={false} variant="secondary" className="flex-1" onClick={() => setConfirmReset(false)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <TextLink tone="ink" onClick={() => setConfirmReset(true)}>Reset demo…</TextLink>
          )}
        </section>
      </div>
    </Sheet>
  );
}
