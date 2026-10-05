"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Loading, Screen } from "@/components/AppShell";
import { Close } from "@/components/ui/icons";
import { Button, ChoiceCard, Chip, Eyebrow, InfoCard, TextLink, Title } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { api } from "@/lib/api/client";
import { downloadText } from "@/lib/api/demo";
import { useQuery } from "@/lib/api/hooks";
import { FIX } from "@/lib/fixtures";
import { useGate } from "@/lib/useGate";

/** Screen 9: announced early, low-stakes, and the student picks the time (plan Q16). */
export default function RecheckInvite() {
  const ready = useGate("onboarded");
  const router = useRouter();
  const { data: s } = useQuery(() => api.getRecheckStatus(), []);
  const [slot, setSlot] = useState<string | null>(null);
  const [skip, setSkip] = useState(false);
  const [done, setDone] = useState<{ text: string; ics: string } | null>(null);

  useEffect(() => {
    if (ready) void api.markInviteSeen();
  }, [ready]);
  if (!ready || !s) return <Loading />;

  const chosen = s.slots.find((x) => x.id === slot);
  const startNow = chosen?.id === "now";

  async function confirm() {
    if (!chosen) return;
    const r = await api.scheduleRecheck(chosen.id);
    if (chosen.id === "now") router.push("/recheck/quiz");
    else setDone({ text: r.text, ics: r.ics });
  }

  if (done) {
    return (
      <Screen>
        <Eyebrow>{FIX.course.eyebrow} · WEEK 7</Eyebrow>
        <Title className="mt-1">You&apos;re set</Title>
        <p className="mt-2 text-body text-muted">We&apos;ll remind you {done.text}. It takes about 3 minutes and nothing is graded.</p>
        <div className="mt-6 flex flex-col gap-3">
          <Button variant="secondary" onClick={() => downloadText("syllabyte-week-7-check-in.ics", done.ics, "text/calendar")}>Add to calendar (.ics)</Button>
          <Button variant="secondary" onClick={() => router.push("/recheck/quiz")}>Start now instead</Button>
          <Button onClick={() => router.push("/playlist")}>Back to your playlist</Button>
        </div>
      </Screen>
    );
  }

  return (
    <Screen>
      <div className="mb-6 flex items-center justify-between">
        <Link href="/playlist" aria-label="Close" className="grid size-14 place-items-center rounded-full bg-surface shadow-[0_0_0_1px_var(--color-line)]"><Close /></Link>
        <Chip className="!px-4 !py-2">Not graded</Chip>
      </div>
      <Eyebrow data-demo-trigger>{FIX.course.eyebrow} · WEEK {s.week}</Eyebrow>
      <Title className="mt-1">Time to re-check your level</Title>
      <p className="mt-2 text-body text-muted">
        You have watched {s.videos_watched} {s.videos_watched === 1 ? "video" : "videos"} since Week 1. 6 questions, about 3 minutes. Your answers only retune what comes next.
      </p>

      <section aria-labelledby="when" className="mt-5 rounded-card border border-line bg-surface p-5">
        <h2 id="when" className="mb-3 text-body font-extrabold">When do you want to do it?</h2>
        <div role="group" aria-labelledby="when" className="flex flex-col gap-2.5">
          {s.slots.map((x) => <ChoiceCard key={x.id} selected={slot === x.id} onClick={() => setSlot(x.id)}>{x.label}</ChoiceCard>)}
        </div>
      </section>

      <div className="mt-3 flex flex-col gap-3">
        <InfoCard eyebrow="What happens next">
          <p>We rebuild your playlist from the new answers. You will see what changed, and you can keep your current playlist instead.</p>
          <p className="mt-2">Your progress and past answers stay as they are.</p>
        </InfoCard>
        <InfoCard eyebrow="Review videos">Refresher videos wait until you have finished your first pass of this week&apos;s playlist.</InfoCard>
      </div>

      <div className="mt-5 flex flex-col items-center gap-2">
        <Button disabled={!chosen} onClick={() => void confirm()}>
          {!chosen ? "Pick a time" : startNow ? "Start now" : `Schedule for ${chosen.id === "friday" ? "Friday" : chosen.id === "monday" ? "Monday" : chosen.label.toLowerCase()}`}
        </Button>
        <TextLink tone="ink" onClick={() => setSkip(true)}>Skip this check-in</TextLink>
      </div>

      <Sheet
        open={skip}
        onOpenChange={setSkip}
        eyebrow="Skip"
        title="Skip the check-in?"
        description="Your levels stay as they are. You can do the check-in later from My levels."
        footer={
          <div className="flex gap-3">
            <Button variant="secondary" full={false} className="flex-1" onClick={() => setSkip(false)}>Go back</Button>
            <Button full={false} className="flex-1" onClick={async () => { await api.skipRecheck(); router.push("/playlist"); }}>Skip it</Button>
          </div>
        }
      >
        <p className="text-body text-muted">Nothing is lost either way.</p>
      </Sheet>
    </Screen>
  );
}
