import { Screen } from "@/components/AppShell";
import { Eyebrow, InfoCard, LinkButton, Title } from "@/components/ui/primitives";

export default function Welcome() {
  return (
    <Screen>
      <p className="mb-10 mt-6 text-card font-extrabold tracking-tight">
        Sylla<span className="text-primary">Byte</span>
      </p>
      <Eyebrow>Welcome</Eyebrow>
      <Title className="mt-1">Short videos from your own course</Title>
      <p className="mt-3 text-body text-muted">
        SyllaByte makes short animated videos from your course&apos;s own slides, tuned to what you already know.
      </p>
      <ul className="mt-6 flex flex-col gap-3">
        {[
          ["AI-made, with sources", "The videos are AI-made, and you can always see the slides they came from."],
          ["Nothing is graded", "Checks only tune your videos. “Not sure” is always a fine answer."],
          ["You are in charge", "You can correct anything we guess about you."],
        ].map(([t, d]) => (
          <li key={t}>
            <InfoCard title={t}>{d}</InfoCard>
          </li>
        ))}
      </ul>
      <div className="mt-8">
        <LinkButton href="/consent">Get started</LinkButton>
      </div>
    </Screen>
  );
}
