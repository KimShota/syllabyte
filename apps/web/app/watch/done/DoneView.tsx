"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useState } from "react";
import { Loading, Screen } from "@/components/AppShell";
import { Replay } from "@/components/ui/icons";
import { Button, Card, Eyebrow, InfoCard, SegmentedRow, TextLink, Title } from "@/components/ui/primitives";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import type { Difficulty, Jol } from "@/lib/types";
import { useGate } from "@/lib/useGate";

/** Screen 7. Nothing here is required; the delayed judgment becomes accurate at the next-day check. */
export function DoneView() {
  const ready = useGate("onboarded");
  const router = useRouter();
  const vid = useSearchParams().get("v");
  const { data: variant } = useQuery(async () => (vid ? api.getVariant(vid) : undefined), [vid]);
  const [jol, setJol] = useState<Jol | null>(null);
  const [diff, setDiff] = useState<Difficulty | null>(null);
  const [blanks, setBlanks] = useState<string[]>([]);
  const [free, setFree] = useState(false);
  const [text, setText] = useState("");
  if (!ready || !variant || !vid) return <Loading />;

  const v = variant.video;
  const name = v.short_title;
  const parts = v.sentence_frame.template.split("___");
  const next = variant.next_video;
  const go = () => router.push(next ? `/watch?v=${encodeURIComponent(next.id)}` : "/playlist");

  async function proceed(save: boolean) {
    const filled = free ? text.trim() : blanks.some((b) => b?.trim()) ? blanks.join(" ") : "";
    if (save && filled) await api.postSelfExplanation(vid!, free ? "free" : "frame", free ? [] : blanks, free ? text.trim() : "");
    go();
  }

  return (
    <Screen>
      <div className="mb-6 flex items-center justify-between gap-3">
        <Link href={`/watch?v=${vid}`} className="inline-flex min-h-14 items-center gap-2 rounded-full bg-surface px-5 font-bold shadow-[0_0_0_1px_var(--color-line)]">
          <Replay size={20} /> Replay
        </Link>
        <p className="eyebrow">
          Video {variant.position ? variant.position.index + 1 : ""}{variant.position ? ` of ${variant.position.total}` : ""} · Done
        </p>
      </div>
      <Eyebrow>{name}</Eyebrow>
      <Title className="mt-1">Before you move on</Title>
      <p className="mt-2 text-body text-muted">Videos feel clearer than they are. A quick guess about tomorrow helps you spot what to revisit.</p>

      <div className="mt-5 flex flex-col gap-3">
        <Card>
          <h2 id="jol" className="mb-3 text-card font-extrabold leading-[1.3]">Without looking back, could you explain {name} to a classmate tomorrow?</h2>
          <SegmentedRow
            label="Could you explain it tomorrow"
            value={jol}
            onChange={(j) => { setJol(j); void api.postJol(vid, j); }}
            options={[{ value: "yes", label: "Yes" }, { value: "maybe", label: "Maybe" }, { value: "no", label: "No" }]}
          />
        </Card>

        <Card>
          <p className="eyebrow">Optional</p>
          <h2 className="mb-3 mt-1 text-body font-extrabold">Say it in one sentence</h2>
          {free ? (
            <label className="block">
              <span className="sr-only">Your sentence</span>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} className="w-full rounded-btn border-2 border-line bg-surface px-4 py-3 text-body" />
            </label>
          ) : (
            <p className="text-body leading-[2.3]">
              {parts.map((p, i) => (
                <Fragment key={i}>
                  {p}
                  {i < parts.length - 1 && (
                    <input
                      aria-label={`Blank ${i + 1} of ${parts.length - 1}`}
                      value={blanks[i] ?? ""}
                      onChange={(e) => setBlanks((b) => { const n = [...b]; n[i] = e.target.value; return n; })}
                      className="mx-1 inline-block min-h-10 w-32 rounded-btn border-2 border-dashed border-muted/70 bg-surface px-3 text-body"
                    />
                  )}
                </Fragment>
              ))}
            </p>
          )}
          <div className="mt-2"><TextLink onClick={() => setFree((f) => !f)}>{free ? "Use the sentence frame" : "Write it my own way"}</TextLink></div>
          <p className="mt-1 text-meta text-muted">Your sentence stays private. It helps us pick tomorrow&apos;s question.</p>
        </Card>

        <Card>
          <h2 className="mb-3 font-bold">This video was</h2>
          <SegmentedRow
            label="How hard was this video"
            value={diff}
            onChange={(d) => { setDiff(d); void api.postDifficulty(vid, d); }}
            options={[{ value: "too_easy", label: "Too easy" }, { value: "just_right", label: "Just right" }, { value: "too_hard", label: "Too hard" }]}
          />
        </Card>

        <InfoCard tone="teal" title="Tomorrow">
          We will ask 1 question on this video. Your guess and your answer will show side by side under My levels.
        </InfoCard>
      </div>

      <div className="mt-6 flex flex-col items-center gap-2">
        <Button onClick={() => void proceed(true)}>{next ? `Next video: ${next.title}` : "Back to playlist"}</Button>
        <TextLink tone="ink" onClick={() => void proceed(false)}>Skip this</TextLink>
      </div>
    </Screen>
  );
}
