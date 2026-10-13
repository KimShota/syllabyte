"use client";

import { useEffect, useState } from "react";
import { LevelUpdatesCard } from "@/components/LevelUpdatesCard";
import { NextSessionCard } from "@/components/NextSessionCard";
import { PrecheckCard } from "@/components/PrecheckCard";
import { SkipReasonSheet } from "@/components/SkipSheets";
import { Button, Eyebrow, InfoCard, LinkButton, TextLink, Title } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { useToast } from "@/components/ui/Toast";
import { VideoCard } from "@/components/VideoCard";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import { track } from "@/lib/events";
import { FIX } from "@/lib/fixtures";
import type { VideoCardView } from "@/lib/types";
import { fmtMinutes, plural } from "@/lib/util";

export default function PlaylistPage() {
  const toast = useToast();
  const { data: pl } = useQuery(() => api.getPlaylist(), []);
  const [edit, setEdit] = useState(false);
  const [menu, setMenu] = useState<VideoCardView | null>(null);
  const [skipFor, setSkipFor] = useState<{ entryId: string; title: string } | null>(null);
  const [showSkipped, setShowSkipped] = useState(false);
  const [watchAgain, setWatchAgain] = useState(false);

  useEffect(() => {
    track("playlist_viewed", { type: "playlist" });
  }, []);

  if (!pl) return null;
  const todo = pl.cards.filter((c) => c.state === "todo");
  const allDone = pl.cards.length > 0 && todo.length === 0;
  const ids = pl.cards.map((c) => c.entry_id!);

  async function move(card: VideoCardView, dir: -1 | 1) {
    const i = ids.indexOf(card.entry_id!);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    const next = [...ids];
    [next[i], next[j]] = [next[j], next[i]];
    await api.reorder(next);
  }

  async function skip(card: VideoCardView) {
    setMenu(null);
    await api.skip(card.entry_id!);
    toast({
      message: `Skipped “${card.title}”.`,
      actions: [
        { label: "Say why", onClick: () => setSkipFor({ entryId: card.entry_id!, title: card.title }) },
        { label: "Undo", onClick: () => void api.undoSkip(card.entry_id!) },
      ],
    });
  }

  return (
    <>
      <Eyebrow data-demo-trigger>{FIX.course.eyebrow}{pl.overall_level ? ` · LEVEL ${pl.overall_level}` : ""}</Eyebrow>
      <Title className="mt-1">Your playlist</Title>
      <p className="mt-2 text-body text-muted">
        {allDone ? "You have watched everything in this week's playlist." : todo.length ? `${plural(todo.length, "video")}, about ${Math.max(1, Math.round(pl.total_seconds / 60))} ${Math.round(pl.total_seconds / 60) <= 1 ? "minute" : "minutes"}. Play them in any order.` : "Nothing to watch right now."}
      </p>

      <div className="mt-5 flex flex-col gap-3">
        {pl.precheck && <PrecheckCard check={pl.precheck} />}
        <LevelUpdatesCard />

        <NextSessionCard />

        {pl.empty_message ? (
          <InfoCard title="Videos are on the way">{pl.empty_message}</InfoCard>
        ) : (
          <section aria-labelledby="why" className="rounded-card border border-line bg-surface p-5">
            <div className="mb-1.5 flex items-center justify-between gap-3">
              <h2 id="why" className="eyebrow !text-primary">Why this order</h2>
              {edit ? (
                <TextLink onClick={() => setEdit(false)}>Done</TextLink>
              ) : (
                <TextLink onClick={() => setEdit(true)}>Change order</TextLink>
              )}
            </div>
            <p className="text-body">{pl.why}</p>
            {edit && pl.manual && (
              <div className="mt-2"><TextLink tone="ink" onClick={() => void api.resetOrder()}>Reset to suggested order</TextLink></div>
            )}
          </section>
        )}

        <ul className="flex flex-col gap-3">
          {pl.cards.map((c, i) => (
            <li key={c.video_id}>
              <VideoCard
                card={c}
                current={c.entry_id === pl.current_entry_id}
                onMenu={edit ? undefined : () => setMenu(c)}
                reorder={edit ? { onUp: i > 0 ? () => void move(c, -1) : undefined, onDown: i < pl.cards.length - 1 ? () => void move(c, 1) : undefined } : undefined}
              />
            </li>
          ))}
        </ul>

        {allDone && (
          <InfoCard title="That's this week's playlist.">
            Nothing else is queued. You can watch any of these again, or look through the Course tab.
          </InfoCard>
        )}

        {pl.skipped.length > 0 && (
          <section aria-label="Skipped videos">
            <button
              type="button"
              aria-expanded={showSkipped}
              onClick={() => setShowSkipped((s) => !s)}
              className="flex min-h-12 w-full items-center justify-between rounded-btn border-2 border-dashed border-muted/60 px-5 font-bold"
            >
              Skipped ({pl.skipped.length})
              <span aria-hidden>{showSkipped ? "−" : "+"}</span>
            </button>
            {showSkipped && (
              <ul className="mt-3 flex flex-col gap-3">
                {pl.skipped.map((c) => (
                  <li key={c.video_id}><VideoCard card={c} onMenu={() => setMenu(c)} /></li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>

      <div className="mt-8 flex items-center justify-between gap-3 text-body text-muted">
        <p>Done so far: {plural(pl.watched_count, "video")}</p>
        <TextLink onClick={() => setWatchAgain(true)}>Watch again</TextLink>
      </div>

      {/* ⋮ menu: a sheet, so every action is a large target */}
      <Sheet open={menu !== null} onOpenChange={(o) => !o && setMenu(null)} eyebrow={menu ? `${fmtMinutes(menu.duration_s)} · Lecture ${menu.lecture_n}` : undefined} title={menu?.title ?? ""}>
        {menu && (
          <div className="flex flex-col gap-2.5">
            {menu.state === "skipped" ? (
              <>
                <LinkButton href={`/watch?v=${menu.video_id}`} variant="secondary">Play it anyway</LinkButton>
                <Button variant="secondary" onClick={async () => { await api.undoSkip(menu.entry_id!); setMenu(null); }}>Undo skip</Button>
                <Button variant="secondary" onClick={() => { setSkipFor({ entryId: menu.entry_id!, title: menu.title }); setMenu(null); }}>Say why</Button>
              </>
            ) : (
              <>
                <Button variant="secondary" onClick={() => void skip(menu)}>Skip this video</Button>
                <Button variant="secondary" disabled={ids.indexOf(menu.entry_id!) <= 0} onClick={async () => { await move(menu, -1); setMenu(null); }}>Move up</Button>
                <Button variant="secondary" disabled={ids.indexOf(menu.entry_id!) >= ids.length - 1} onClick={async () => { await move(menu, 1); setMenu(null); }}>Move down</Button>
              </>
            )}
            <LinkButton href={`/course#${menu.video_id}`} variant="quiet">View in course map</LinkButton>
          </div>
        )}
      </Sheet>

      <SkipReasonSheet key={skipFor?.entryId ?? "closed"} entryId={skipFor?.entryId ?? null} title={skipFor?.title ?? ""} onClose={() => setSkipFor(null)} />

      <WatchAgainSheet open={watchAgain} onClose={() => setWatchAgain(false)} />
    </>
  );
}

function WatchAgainSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: map } = useQuery(() => api.getCourseMap(), []);
  const watched = (map?.lectures ?? []).flatMap((l) => l.rows).filter((r) => r.video && r.status === "watched");
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()} eyebrow="Watch again" title="Videos you have watched">
      {watched.length === 0 ? (
        <p className="text-body text-muted">Nothing yet. Videos you finish will be listed here.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {watched.map((r) => <li key={r.ku.id}><VideoCard card={r.video!} /></li>)}
        </ul>
      )}
    </Sheet>
  );
}
