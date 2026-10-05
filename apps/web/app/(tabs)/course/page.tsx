"use client";

import { useState } from "react";
import { SimpleMarkdown } from "@/app/consent/ConsentView";
import { Button, Card, Eyebrow, SegmentedRow, TextLink, Title } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { VideoCard } from "@/components/VideoCard";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import { FIX } from "@/lib/fixtures";
import { fmtClock } from "@/lib/util";
import { CONSENT_TEXT } from "@/content/consent";

const STATUS_LABEL = { watched: "Watched", in_playlist: "In your playlist", skipped: "Skipped", available: "Available", not_made: "Not made yet" } as const;

export default function CoursePage() {
  const { data: map } = useQuery(() => api.getCourseMap(), []);
  const { data: me } = useQuery(() => api.getMe(), []);
  const [consent, setConsent] = useState(false);
  const [withdraw, setWithdraw] = useState(false);
  const [deletePast, setDeletePast] = useState(false);
  if (!map || !me) return null;

  return (
    <>
      <Eyebrow data-demo-trigger>{FIX.course.eyebrow} · COURSE</Eyebrow>
      <Title className="mt-1">Every video, by lecture</Title>
      <p className="mt-2 text-body text-muted">Open any video, even one that isn&apos;t in your playlist. Add it if you want it there.</p>

      <div className="mt-6 flex flex-col gap-8">
        {map.lectures.map(({ lecture, rows }) => (
          <section key={lecture.n} aria-labelledby={`lec-${lecture.n}`}>
            <h2 id={`lec-${lecture.n}`} className="mb-3">
              <span className="eyebrow block">Lecture {lecture.n}</span>
              <span className="text-card font-extrabold">{lecture.title}</span>
            </h2>
            <ul className="flex flex-col gap-3">
              {rows.map((r) => (
                <li key={r.ku.id} id={r.video?.video_id}>
                  {r.video ? (
                    <VideoCard card={{ ...r.video, tag: r.status === "in_playlist" ? r.video.tag : null }}>
                      <p className="mt-2 text-meta font-bold text-muted">{STATUS_LABEL[r.status]}</p>
                      {r.status === "available" && (
                        <div className="relative z-10 mt-1">
                          <TextLink className="!min-h-11" onClick={() => void api.addToPlaylist(r.video!.video_id)}>Add to my playlist</TextLink>
                        </div>
                      )}
                      {r.notes.length > 0 && (
                        <ul className="relative z-10 mt-2 flex flex-col gap-1 border-t border-line pt-2">
                          {r.notes.map((n) => (
                            <li key={n.id} className="text-meta"><span className="meta">{fmtClock(n.video_t)}</span> {n.text}</li>
                          ))}
                        </ul>
                      )}
                    </VideoCard>
                  ) : (
                    <Card className="border-dashed border-muted/60 !bg-transparent">
                      <h3 className="text-[18px] font-bold leading-[1.25]">{r.ku.short_title}</h3>
                      <p className="meta mt-1">{r.topic_title}</p>
                      <p className="mt-2 text-meta font-bold text-muted">Not made yet · Coming soon</p>
                    </Card>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <details className="mt-10 rounded-card border border-line bg-surface p-5">
        <summary className="min-h-11 cursor-pointer text-card font-extrabold">Course info &amp; settings</summary>
        <div className="mt-4 flex flex-col gap-6">
          <section>
            <h3 className="eyebrow mb-1">Syllabus</h3>
            <p className="text-body">{FIX.course.syllabus_summary}</p>
          </section>
          <section>
            <h3 className="eyebrow mb-1">What “AI-made” means</h3>
            <p className="text-body">The animation and narration are generated from your lecture slides. They have not necessarily been reviewed by your instructor. Open “About this video” on any video to see its slides and check its claims.</p>
          </section>
          <section>
            <h3 className="eyebrow mb-2">Captions</h3>
            <SegmentedRow label="Captions default" value={me.settings.captions ? "on" : "off"} onChange={(v) => void api.updateSettings({ captions: v === "on" })} options={[{ value: "on", label: "On" }, { value: "off", label: "Off" }]} />
          </section>
          <section>
            <h3 className="eyebrow mb-2">Weekly email</h3>
            <p className="mb-2 text-meta text-muted">One email at the start of each lecture week when your playlist is ready.</p>
            <SegmentedRow label="Weekly email" value={me.settings.weekly_email ? "on" : "off"} onChange={(v) => void api.updateSettings({ weekly_email: v === "on" })} options={[{ value: "on", label: "On" }, { value: "off", label: "Off" }]} />
          </section>
          <section>
            <h3 className="eyebrow mb-2">Consent and data</h3>
            <p className="mb-2 text-body">
              {me.consent === "research" ? "You agreed to take part in the study." : "You are using SyllaByte without research data."}
            </p>
            <div className="flex flex-wrap gap-x-5">
              <TextLink onClick={() => setConsent(true)}>View consent</TextLink>
              {me.consent === "research" && <TextLink tone="ink" onClick={() => setWithdraw(true)}>Withdraw from the research</TextLink>}
            </div>
          </section>
          <section>
            <Button variant="secondary" disabled>Sign out</Button>
            <p className="meta mt-2">Sign-in starts in Phase 1.</p>
          </section>
        </div>
      </details>

      <Sheet open={consent} onOpenChange={setConsent} eyebrow="Consent" title="Full consent form"><SimpleMarkdown text={CONSENT_TEXT} /></Sheet>

      <Sheet
        open={withdraw}
        onOpenChange={setWithdraw}
        eyebrow="Withdraw"
        title="Stop taking part?"
        description="You keep full access to SyllaByte. We stop recording your activity for the research from now on."
        footer={
          <div className="flex gap-3">
            <Button variant="secondary" full={false} className="flex-1" onClick={() => setWithdraw(false)}>Cancel</Button>
            <Button full={false} className="flex-1" onClick={async () => { await api.withdrawFromResearch(deletePast); setWithdraw(false); }}>Withdraw</Button>
          </div>
        }
      >
        <label className="flex min-h-12 items-start gap-3 text-body">
          <input type="checkbox" checked={deletePast} onChange={(e) => setDeletePast(e.target.checked)} className="mt-1 size-5 accent-primary" />
          <span>Also delete my past research data. We record that a deletion happened, not what was in it.</span>
        </label>
      </Sheet>
    </>
  );
}
