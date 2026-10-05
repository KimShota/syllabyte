"use client";

import { useState } from "react";
import { api } from "@/lib/api/client";
import { useQuery } from "@/lib/api/hooks";
import { LEVEL_BLURBS, LEVEL_NAMES } from "@/lib/logic/levels";
import type { Level, LevelsView } from "@/lib/types";
import { Button, ChoiceCard, SegmentedRow } from "./ui/primitives";
import { Sheet } from "./ui/Sheet";
import { useToast } from "./ui/Toast";

const LEVELS: Level[] = [1, 2, 3];

function LevelCards({ value, onChange }: { value: Level | null; onChange: (l: Level) => void }) {
  return (
    <div role="group" aria-label="Level" className="flex flex-col gap-2.5">
      {LEVELS.map((l) => (
        <ChoiceCard key={l} selected={value === l} onClick={() => onChange(l)}>
          <span className="block font-bold">Level {l} · {LEVEL_NAMES[l]}</span>
          <span className="mt-0.5 block text-meta font-medium text-muted">{LEVEL_BLURBS[l]}</span>
        </ChoiceCard>
      ))}
    </div>
  );
}

const REASONS = [
  { value: "too_easy", label: "Videos feel too easy" },
  { value: "too_hard", label: "Videos feel too hard" },
  { value: "learned_elsewhere", label: "I learned this elsewhere" },
  { value: "other", label: "Other" },
] as const;

/**
 * The one "Change level" sheet (plan Q14), opened from My levels ("Correct this", "Set it myself"),
 * the tailoring receipt ("This level is wrong for me") and the onboarding result ("Change a topic").
 */
export function ChangeLevelSheet({ topicId, onClose, sourceScreen }: { topicId: string | null; onClose: () => void; sourceScreen: string }) {
  const { data } = useQuery(() => api.getLevels(), []);
  const row = data?.topics.find((t) => t.topic.id === topicId);
  if (!topicId || !row) return null;
  // keyed by topic: each opening starts from that topic's current level, with no reset effect
  return <ChangeLevelForm key={topicId} row={row} onClose={onClose} sourceScreen={sourceScreen} />;
}

function ChangeLevelForm({ row, onClose, sourceScreen }: { row: LevelsView["topics"][number]; onClose: () => void; sourceScreen: string }) {
  const toast = useToast();
  const { topic, level: current } = row;
  const [level, setLevel] = useState<Level | null>(current.level);
  const [reason, setReason] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const title = topic.title;

  async function save() {
    if (!level) return;
    const { previous } = await api.correctLevel(topic.id, level, reason, note.trim(), sourceScreen);
    onClose();
    toast({
      message: `${title} set to Level ${level} by you. Your playlist will update.`,
      actions: [{ label: "Undo", onClick: () => void api.restoreLevel(previous) }],
    });
  }

  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      eyebrow="Change level"
      title={title}
      description={
        current.not_checked
          ? current.reason
          : `Now: Level ${current.level} · ${LEVEL_NAMES[current.level]}. ${current.source === "student" ? "Set by you." : current.reason}`
      }
      footer={
        <Button onClick={save} disabled={!level || (level === current.level && current.source === "student" && !reason)}>
          Save level
        </Button>
      }
    >
      <div className="flex flex-col gap-5">
        <LevelCards value={level} onChange={setLevel} />
        <div>
          <p className="mb-2 text-body font-bold">Why? <span className="font-medium text-muted">(optional)</span></p>
          <SegmentedRow label="Reason" value={reason as (typeof REASONS)[number]["value"] | null} onChange={setReason} options={REASONS.map((r) => ({ ...r }))} className="[&>button]:flex-none" />
          {reason === "other" && (
            <label className="mt-3 block">
              <span className="sr-only">Tell us more</span>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={140}
                placeholder="One line is plenty"
                className="min-h-12 w-full rounded-btn border-2 border-line bg-surface px-4 text-body"
              />
            </label>
          )}
        </div>
      </div>
    </Sheet>
  );
}

/** "Pick my own level" / "Pick one level for everything": one level for all topics. */
export function LevelPickerSheet({ open, onClose, fromQuestion, onPicked }: { open: boolean; onClose: () => void; fromQuestion: number; onPicked: () => void }) {
  const [level, setLevel] = useState<Level | null>(null);
  return (
    <Sheet
      open={open}
      onOpenChange={(o) => !o && onClose()}
      eyebrow="Pick my own level"
      title="Which level suits you?"
      description="This sets every topic. You can change any topic later."
      footer={
        <Button
          disabled={!level}
          onClick={async () => {
            await api.pickAllLevels(level!, fromQuestion);
            onPicked();
          }}
        >
          Use this level
        </Button>
      }
    >
      <LevelCards value={level} onChange={setLevel} />
    </Sheet>
  );
}
