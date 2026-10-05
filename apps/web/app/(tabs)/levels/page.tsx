"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ChangeLevelSheet } from "@/components/LevelSheets";
import { Button, Card, Eyebrow, LevelBar, TextLink, Title } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { api } from "@/lib/api/client";
import { downloadText } from "@/lib/api/demo";
import { useQuery } from "@/lib/api/hooks";
import { FIX } from "@/lib/fixtures";
import { levelLabel } from "@/lib/logic/levels";

export default function LevelsPage() {
  const router = useRouter();
  const { data } = useQuery(() => api.getLevels(), []);
  const { data: cal } = useQuery(() => api.getCalibration(), []);
  const [change, setChange] = useState<string | null>(null);
  const [reset, setReset] = useState(false);
  if (!data || !cal) return null;
  const updated = data.week7_applied;

  return (
    <>
      <Eyebrow data-demo-trigger>{FIX.course.eyebrow} · MY LEVELS</Eyebrow>
      <Title className="mt-1">What your videos are based on</Title>
      <p className="mt-2 text-body text-muted">This is our best guess, not a grade. If a level looks wrong, correct it.</p>

      <section aria-label="Overall level" className="mt-5 rounded-card bg-ink p-5 text-white">
        <p className="eyebrow !text-white/70">Overall start level</p>
        <p className="mt-1 text-title font-extrabold">{data.overall_level ? levelLabel(data.overall_level) : "Not set yet"}</p>
        <p className="mt-1 text-body text-white/80">
          {updated ? "Updated at your Week 7 check-in." : `Set from your Week 1 check. Next check-in: Week ${FIX.course.config.recheck_week}.`}
        </p>
      </section>

      {data.recheck_due && (
        <div className="mt-3">
          <Link href="/recheck/quiz" className="inline-flex min-h-14 w-full items-center justify-center rounded-btn bg-primary px-6 font-bold text-white">
            Do the Week 7 check-in
          </Link>
        </div>
      )}

      <ul className="mt-4 flex flex-col gap-3">
        {data.topics.map(({ topic, level }) => (
          <li key={topic.id}>
            <Card className={level.not_checked ? "border-dashed border-muted/60" : ""}>
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-card font-bold">{topic.title}</h2>
                <TextLink onClick={() => setChange(topic.id)}>{level.not_checked ? "Set it myself" : "Correct this"}</TextLink>
              </div>
              {!level.not_checked && (
                <div className="mt-2 flex items-center gap-4">
                  <LevelBar level={level.level} />
                  <span className="font-bold">Level {level.level}</span>
                </div>
              )}
              {level.source === "student" ? (
                <p className="mt-3 text-body">
                  Set by you.{" "}
                  <TextLink className="!min-h-0" onClick={() => void api.useSuggestedLevel(topic.id)}>Use suggested level (Level {level.suggested_level})</TextLink>
                </p>
              ) : (
                <p className="mt-3 text-body text-ink/85">{level.reason}</p>
              )}
            </Card>
          </li>
        ))}
      </ul>

      <Card className="mt-3">
        <h2 className="eyebrow mb-2">How sure you were, and how often you were right</h2>
        {cal.block1.ready ? (
          <>
            <ul className="flex flex-col gap-2.5">
              {cal.block1.rows.map((r) => (
                <li key={r.confidence} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 font-bold">{r.label}</span>
                  <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-line" role="img" aria-label={`${r.right} of ${r.n} right`}>
                    <span className="block h-full rounded-full bg-primary" style={{ width: `${r.n ? (100 * r.right) / r.n : 0}%` }} />
                  </span>
                  <span className="w-16 shrink-0 text-right font-bold">{r.right} of {r.n}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-body text-ink/85">{cal.block1.sentences.join(" ")}</p>
          </>
        ) : (
          <p className="text-body text-muted">We&apos;ll show this after 5 quick checks. So far: {cal.block1.rated}.</p>
        )}
      </Card>

      {cal.block2.pairs.length > 0 && (
        <Card className="mt-3">
          <h2 className="eyebrow mb-2">Your guess vs the next day</h2>
          <ul className="flex flex-col gap-2">
            {cal.block2.pairs.map((p, i) => (
              <li key={`${p.video_id}-${i}`} className="text-body">
                <strong>{p.title}</strong> · You said <strong>{p.jol === "yes" ? "Yes" : p.jol === "maybe" ? "Maybe" : "No"}</strong> · Next day: <strong>{p.correct ? "right" : "not quite"}</strong>
              </li>
            ))}
          </ul>
          {cal.block2.summary && <p className="mt-3 text-body text-ink/85">{cal.block2.summary}</p>}
        </Card>
      )}

      <Card className="mt-3">
        <h2 className="eyebrow mb-2">You, since Week 1</h2>
        {data.history_lines.length ? (
          <ul className="flex flex-col gap-1.5 text-body">{data.history_lines.map((l) => <li key={l}>{l}</li>)}</ul>
        ) : (
          <p className="text-body text-muted">No changes yet. Only your own history is shown here.</p>
        )}
      </Card>

      <div className="mt-6 flex items-center justify-between gap-3">
        <TextLink onClick={async () => downloadText("syllabyte-my-data.json", JSON.stringify(await api.exportMyData(), null, 2))}>Download my data</TextLink>
        <TextLink tone="ink" onClick={() => setReset(true)}>Reset my model</TextLink>
      </div>

      <ChangeLevelSheet topicId={change} onClose={() => setChange(null)} sourceScreen="my_levels" />

      <Sheet
        open={reset}
        onOpenChange={setReset}
        eyebrow="Reset my model"
        title="Start your levels over?"
        description="This clears your levels and rebuilds your playlist from scratch. Your watch history, notes and study answers stay. You'll retake the 8-question check. We keep a copy for the study unless you withdraw."
        footer={
          <div className="flex gap-3">
            <Button variant="secondary" full={false} className="flex-1" onClick={() => setReset(false)}>Cancel</Button>
            <Button full={false} className="flex-[1.6]" onClick={async () => { await api.resetModel(); router.push("/onboarding"); }}>Reset and retake the check</Button>
          </div>
        }
      >
        <p className="text-body text-muted">You can still correct any level yourself instead.</p>
      </Sheet>
    </>
  );
}
