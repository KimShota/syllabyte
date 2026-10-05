"use client";

import clsx from "clsx";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Loading, Screen } from "@/components/AppShell";
import { ArrowDown, ArrowUp } from "@/components/ui/icons";
import { Button, Card, Chip, Eyebrow, TextLink, Title } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api/client";
import type { ProposalRow } from "@/lib/api/types";
import { useQuery } from "@/lib/api/hooks";
import { useGate } from "@/lib/useGate";

/** Screen 10: level changes are proposals the student accepts, keeps or disputes; nothing changes until Apply. */
export default function RecheckResults() {
  const ready = useGate("onboarded");
  const router = useRouter();
  const toast = useToast();
  const { data } = useQuery(() => api.getProposals(), []);
  const { data: status } = useQuery(() => api.getRecheckStatus(), []);

  useEffect(() => {
    if (data && status && data.proposals.length === 0) router.replace(status.status === "idle" ? "/recheck" : "/recheck/quiz");
  }, [data, status, router]);
  if (!ready || !data || data.proposals.length === 0) return <Loading />;

  const changed = data.proposals.filter((p) => p.direction === "up" || p.direction === "down");
  const same = data.proposals.filter((p) => p.direction === "same" || p.direction === "not_enough");
  const accepted = changed.filter((p) => p.decision === "accepted").length;
  const undecided = changed.filter((p) => p.decision === null).length;
  const kept = changed.length - accepted;
  const d = data.diff;

  async function apply(mode: "apply" | "keep_old" | "pick_myself") {
    await api.applyDecisions(mode);
    const after = await api.getProposals();
    const sum = after.applied?.summary;
    toast({
      message:
        mode === "keep_old"
          ? "Kept your old playlist. Your levels did not change."
          : `Playlist updated · ${sum?.new ?? 0} new, ${sum?.swapped ?? 0} swapped, ${sum?.removed ?? 0} removed`,
      actions: [{ label: "Undo", onClick: () => void api.undoApply() }],
      duration: 10000,
    });
    router.push(mode === "pick_myself" ? "/course" : "/playlist");
  }

  return (
    <Screen>
      <Eyebrow data-demo-trigger>Week 7 check-in · done</Eyebrow>
      <Title className="mt-1">{changed.length === 0 ? "No changes suggested" : `We suggest ${changed.length} ${changed.length === 1 ? "change" : "changes"}`}</Title>
      <p className="mt-2 text-body text-muted">Compared with your own Week 1 check. Nothing changes until you decide. Each level moves one step at most.</p>

      <ul className="mt-5 flex flex-col gap-3">
        {changed.map((p) => <li key={p.topic_id}><ProposalCard p={p} /></li>)}
        {same.map((p) => (
          <li key={p.topic_id}>
            <Card className="!bg-ink/[0.03]">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-card font-bold">{p.topic_title}</h2>
                <Chip>Same</Chip>
              </div>
              <p className="mt-1 text-body text-muted">
                Level {p.from}, no change{p.direction === "not_enough" ? " · not enough answers yet" : ""}
              </p>
            </Card>
          </li>
        ))}
      </ul>

      <section aria-labelledby="diff" className="mt-4 rounded-card border border-line bg-surface p-5">
        <h2 id="diff" className="eyebrow !text-primary mb-2">Your playlist if you accept</h2>
        <div className="flex flex-wrap gap-2">
          <Chip className="!border-transparent !bg-new-bg !text-new-fg">{d.new.length} new</Chip>
          <Chip className="!border-transparent !bg-refresher-bg !text-refresher-fg">{d.swapped.length} switched level</Chip>
          <Chip>{d.removed.length} removed, already known</Chip>
        </div>
        <div className="mt-2"><Link href="/recheck/changes" className="inline-flex min-h-11 items-center font-semibold text-primary underline underline-offset-4 decoration-2">See every change</Link></div>
      </section>

      <div className="mt-5 flex flex-col gap-3">
        {data.applied && data.mode ? (
          <div className="rounded-card bg-new-bg p-4 text-new-fg">
            <p className="font-bold">You applied your choices.</p>
            {data.undo_available && <TextLink onClick={() => void api.undoApply()}>Undo</TextLink>}
          </div>
        ) : (
          <>
            <Button onClick={() => void apply("apply")}>Apply my choices ({accepted} accepted, {kept} kept)</Button>
            {undecided > 0 && <p className="-mt-1 text-center text-meta text-muted">Anything you haven&apos;t chosen stays as it is.</p>}
            <Button variant="secondary" onClick={() => void apply("keep_old")}>Keep my old playlist</Button>
            <div className="text-center"><TextLink onClick={() => void apply("pick_myself")}>I will pick the videos myself</TextLink></div>
          </>
        )}
      </div>
    </Screen>
  );
}

function ProposalCard({ p }: { p: ProposalRow }) {
  const [why, setWhy] = useState(p.decision === "disputed");
  const [text, setText] = useState(p.dispute_text);
  const up = p.direction === "up";
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-card font-bold">{p.topic_title}</h2>
        <span className={clsx("inline-flex shrink-0 items-center gap-1 rounded-full px-3 py-1 text-meta font-bold", up ? "bg-new-bg text-new-fg" : "bg-gap-bg text-gap-fg")}>
          {up ? <ArrowUp size={14} /> : <ArrowDown size={14} />} {up ? "Up" : "Down"}
        </span>
      </div>
      <p className="mt-2 text-body font-bold">Level {p.from} → Level {p.to} proposed</p>
      <p className="mt-1 text-body text-ink/85">{p.reason}</p>
      {p.note && <p className="mt-1 text-meta text-muted">{p.note}</p>}
      <div role="group" aria-label={`Decision for ${p.topic_title}`} className="mt-3 flex gap-2">
        <button type="button" aria-pressed={p.decision === "accepted"} onClick={() => { setWhy(false); void api.decideProposal(p.topic_id, "accepted", ""); }} className={clsx("min-h-12 flex-1 rounded-btn border-2 px-3 font-bold", p.decision === "accepted" ? "border-primary bg-primary-tint" : "border-line bg-surface hover:border-ink/30")}>Accept</button>
        <button type="button" aria-pressed={p.decision === "kept"} onClick={() => { setWhy(false); void api.decideProposal(p.topic_id, "kept", ""); }} className={clsx("min-h-12 flex-1 rounded-btn border-2 px-3 font-bold", p.decision === "kept" ? "border-primary bg-primary-tint" : "border-line bg-surface hover:border-ink/30")}>Keep Level {p.from}</button>
      </div>
      <div className="mt-1">
        <TextLink onClick={() => setWhy((w) => !w)}>Tell us why we are wrong</TextLink>
      </div>
      {why && (
        <div className="slide-in mt-1">
          <label className="block">
            <span className="sr-only">Why is this wrong?</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={400} placeholder="One or two lines is plenty" className="w-full rounded-btn border-2 border-line bg-surface px-4 py-3 text-body" />
          </label>
          <div className="mt-2 flex items-center gap-3">
            <Button full={false} variant="secondary" disabled={!text.trim()} onClick={() => void api.decideProposal(p.topic_id, "disputed", text.trim())}>Save, keep Level {p.from}</Button>
            {p.decision === "disputed" && <span className="text-meta font-bold text-new-fg">Thanks. We&apos;ll keep Level {p.from}.</span>}
          </div>
        </div>
      )}
    </Card>
  );
}
