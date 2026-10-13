"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Screen } from "@/components/AppShell";
import { BackButton, Button, Eyebrow, InfoCard, TextLink, Title } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { api } from "@/lib/api/client";
import { useHydrated } from "@/lib/store";

/** Minimal renderer for the consent file: # / ## headings, "- " bullets, paragraphs. */
export function SimpleMarkdown({ text }: { text: string }) {
  const out: React.ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length) {
      out.push(<ul key={`u${out.length}`} className="list-disc space-y-1 pl-6">{bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>);
      bullets = [];
    }
  };
  text.split("\n").forEach((line, i) => {
    if (line.startsWith("- ")) return void bullets.push(line.slice(2));
    flush();
    if (line.startsWith("## ")) out.push(<h3 key={i} className="mt-4 text-body font-extrabold">{line.slice(3)}</h3>);
    else if (line.startsWith("# ")) out.push(<h2 key={i} className="text-card font-extrabold">{line.slice(2)}</h2>);
    else if (line.trim()) out.push(<p key={i}>{line}</p>);
  });
  flush();
  return <div className="space-y-2 text-body">{out}</div>;
}

export function ConsentView({ markdown }: { markdown: string }) {
  const router = useRouter();
  useHydrated();
  const [full, setFull] = useState(false);
  const [busy, setBusy] = useState(false);

  async function choose(research: boolean) {
    setBusy(true);
    await api.postConsent(research);
    // Research participants answer "About you" (plan I6) before the baseline check; it can be skipped.
    router.push(research ? "/study?b=baseline&next=/onboarding" : "/onboarding");
  }

  return (
    <Screen>
      <div className="mb-6"><BackButton onClick={() => router.push("/welcome")} /></div>
      <Eyebrow>Before we start</Eyebrow>
      <Title className="mt-1">Taking part in the study</Title>
      <p className="mt-3 text-body text-muted">Either choice gives you the full app. Nothing here is graded.</p>

      <div className="mt-6 flex flex-col gap-3">
        <InfoCard eyebrow="What we collect">
          Your answers, how sure you said you were, which videos you skip, how you watch, notes you save, and a few short questionnaires.
        </InfoCard>
        <InfoCard eyebrow="Who sees it">
          The research team, without your name. Your instructor sees reports about video errors, not who sent them.
        </InfoCard>
        <InfoCard eyebrow="How to withdraw">
          Any time, under Course, then Settings. You can also have what we collected deleted.
        </InfoCard>
      </div>

      <div className="mt-3"><TextLink onClick={() => setFull(true)}>Read the full consent form</TextLink></div>

      <div className="mt-6 flex flex-col gap-3">
        <Button variant="secondary" disabled={busy} onClick={() => void choose(true)}>I agree to take part</Button>
        <Button variant="secondary" disabled={busy} onClick={() => void choose(false)}>Use SyllaByte without research data</Button>
      </div>

      <Sheet open={full} onOpenChange={setFull} eyebrow="Consent" title="Full consent form">
        <SimpleMarkdown text={markdown} />
      </Sheet>
    </Screen>
  );
}
