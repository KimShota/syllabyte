"use client";

import clsx from "clsx";
import Link from "next/link";
import type { ReactNode } from "react";
import type { VideoCardView } from "@/lib/types";
import { fmtMinutes } from "@/lib/util";
import { ArrowDown, ArrowUp, Check, More, Play } from "./ui/icons";
import { StatusBadge, Tag } from "./ui/primitives";

/**
 * One video in the playlist, the Course map and Watch again (wireframe screen 2). The whole
 * card is one link (a stretched title link); the ⋮ and ↑/↓ controls sit above it.
 */
export function VideoCard({
  card, current, onMenu, reorder, linkTo, children,
}: {
  card: VideoCardView;
  current?: boolean;
  onMenu?: () => void;
  reorder?: { onUp?: () => void; onDown?: () => void };
  linkTo?: string;
  children?: ReactNode;
}) {
  const href = linkTo ?? `/watch?v=${encodeURIComponent(card.video_id)}`;
  return (
    <article
      className={clsx(
        "relative flex gap-4 rounded-card bg-surface p-4",
        current ? "border-2 border-primary" : "border border-line",
        card.state === "skipped" && "opacity-80",
      )}
    >
      <div className="relative size-[88px] shrink-0 sm:size-[104px] overflow-hidden rounded-[18px] bg-video" aria-hidden>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={card.poster_url} alt="" className="size-full object-cover opacity-60" />
        <span className="absolute inset-0 grid place-items-center text-white">
          {card.state === "watched" ? <Check size={34} /> : <Play size={34} />}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <h3 className="text-[18px] font-bold leading-[1.25]">
          <Link href={href} className="after:absolute after:inset-0 after:rounded-card focus-visible:outline-offset-4">
            {card.title}
          </Link>
        </h3>
        <p className="meta mt-1 !text-[13px] sm:!text-[14px]">
          {fmtMinutes(card.duration_s)} · Lecture {card.lecture_n}
          {card.state === "watched" && " · Watched"}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {card.tag && <Tag tag={card.tag} />}
          {card.review_status !== "unreviewed" && <StatusBadge status={card.review_status} />}
        </div>
        {card.fallback_note && <p className="mt-2 text-[13px] leading-[18px] text-muted">{card.fallback_note}</p>}
        {card.made_level !== null && card.made_level !== card.level && (
          <p className="mt-2 text-[13px] leading-[18px] text-muted">Made at Level {card.made_level} · you are now Level {card.level}</p>
        )}
        {children}
      </div>

      <div className="relative z-10 flex shrink-0 flex-col items-end justify-between">
        {onMenu && (
          <button type="button" onClick={onMenu} aria-label={`More options for ${card.title}`} className="grid size-11 place-items-center rounded-full hover:bg-ink/5">
            <More />
          </button>
        )}
        {reorder && (
          <div className="flex flex-col gap-1">
            <button type="button" disabled={!reorder.onUp} onClick={reorder.onUp} aria-label={`Move ${card.title} up`} className="grid size-11 place-items-center rounded-full border-2 border-line bg-surface disabled:opacity-30">
              <ArrowUp size={20} />
            </button>
            <button type="button" disabled={!reorder.onDown} onClick={reorder.onDown} aria-label={`Move ${card.title} down`} className="grid size-11 place-items-center rounded-full border-2 border-line bg-surface disabled:opacity-30">
              <ArrowDown size={20} />
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
