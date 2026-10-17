"use client";

import type { KuLevelRow, LectureLevels } from "@syllabyte/core/types";
import { Card, LevelBar, TextLink } from "./ui/primitives";

/** The note under a KU when its video was made at a level other than its current one (plan D15). */
export function madeNote(row: KuLevelRow): string | null {
  return row.made_level !== null && row.made_level !== row.level.level
    ? `Its video was made at Level ${row.made_level}. You are now Level ${row.level.level}, so new videos on it use Level ${row.level.level}.`
    : null;
}

/** One Knowledge Unit: its published level, why, and the way to correct it. */
export function KuLevelCard({ row, action, onAction, onUseSuggested }: {
  row: KuLevelRow;
  action: string;
  onAction: () => void;
  onUseSuggested?: () => void;
}) {
  const { ku, level } = row;
  const note = madeNote(row);
  return (
    <Card className={level.not_checked ? "border-dashed border-muted/60" : ""}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[18px] font-bold leading-[1.25]">{ku.short_title}</h3>
        <TextLink aria-label={`${action}: ${ku.short_title}`} onClick={onAction}>{action}</TextLink>
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
          {onUseSuggested && level.suggested_level !== level.level && (
            <TextLink className="!min-h-0" onClick={onUseSuggested}>Use suggested level (Level {level.suggested_level})</TextLink>
          )}
        </p>
      ) : (
        <p className="mt-3 text-body text-ink/85">{level.reason}</p>
      )}
      {note && <p className="mt-2 text-meta text-muted">{note}</p>}
    </Card>
  );
}

/** Every lecture as a section of its KU cards. */
export function LectureLevelList({ lectures, action, onAction, onUseSuggested }: {
  lectures: LectureLevels[];
  action: (row: KuLevelRow) => string;
  onAction: (kuId: string) => void;
  onUseSuggested?: (kuId: string) => void;
}) {
  return (
    <div className="flex flex-col gap-8">
      {lectures.map(({ lecture, rows }) => (
        <section key={lecture.n} aria-labelledby={`lv-${lecture.n}`}>
          <h2 id={`lv-${lecture.n}`} className="mb-3">
            <span className="eyebrow block">Lecture {lecture.n}</span>
            <span className="text-card font-extrabold">{lecture.title}</span>
          </h2>
          <ul className="flex flex-col gap-3">
            {rows.map((r) => (
              <li key={r.ku.id}>
                <KuLevelCard row={r} action={action(r)} onAction={() => onAction(r.ku.id)} onUseSuggested={onUseSuggested ? () => onUseSuggested(r.ku.id) : undefined} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
