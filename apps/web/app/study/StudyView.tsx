"use client";

import clsx from "clsx";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useMemo, useState } from "react";
import type { Instrument, InstrumentItem, ResponseFormat } from "@/content/instruments";
import { Loading, Screen } from "@/components/AppShell";
import { Close } from "@/components/ui/icons";
import { Button, Eyebrow, ProgressSegments, Title } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/Sheet";
import { api } from "@/lib/api/client";
import type { BatteryView } from "@/lib/api/types";
import { visibleItems } from "@/lib/logic/instruments";
import type { BatteryRecord } from "@/lib/types";
import { useGate } from "@/lib/useGate";

type Answers = BatteryRecord["answers"];
type Value = number | string | null;

/**
 * A questionnaire battery (plan/study-instruments-plan.md): one instrument per page, one tap per item, and any
 * question can be skipped, but on purpose (I10). Answers save as they are given, so leaving and coming back resumes.
 */
export function StudyView() {
  const ready = useGate("consent");
  const router = useRouter();
  const params = useSearchParams();
  const id = params.get("b") ?? "";
  const nextParam = params.get("next");
  const next = nextParam?.startsWith("/") ? nextParam : "/playlist";
  const [battery, setBattery] = useState<BatteryView | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    if (!ready || !id) return;
    api.getBattery(id).then(setBattery, () => setUnavailable(true));
  }, [ready, id]);

  if (!ready || (!battery && !unavailable)) return <Loading />;
  if (unavailable || !battery) {
    return (
      <Screen>
        <Title>Nothing to answer here</Title>
        <p className="mt-3 text-body text-muted">This questionnaire isn’t open for you.</p>
        <Button className="mt-6" onClick={() => router.push(next)}>Continue</Button>
      </Screen>
    );
  }
  return <Battery battery={battery} onDone={() => router.push(next)} />;
}

function firstOpenPage(instruments: Instrument[], answers: Answers): number {
  const i = instruments.findIndex((ins) => visibleItems(ins, answers).some((it) => !(it.id in answers)));
  return i === -1 ? instruments.length - 1 : i;
}

function Battery({ battery, onDone }: { battery: BatteryView; onDone: () => void }) {
  const { instruments } = battery;
  const [answers, setAnswers] = useState<Answers>(battery.answers);
  const [page, setPage] = useState(() => firstOpenPage(instruments, battery.answers));
  const [confirmSkip, setConfirmSkip] = useState(false);
  const [finished, setFinished] = useState(battery.submitted);
  const [busy, setBusy] = useState(false);
  const instrument = instruments[page];
  const items = useMemo(() => visibleItems(instrument, answers), [instrument, answers]);
  const blank = items.filter((it) => answers[it.id] === undefined);
  const last = page === instruments.length - 1;

  function answer(itemId: string, value: Value) {
    setAnswers((a) => ({ ...a, [itemId]: value }));
    void api.saveBatteryAnswers(battery.id, { [itemId]: value });
  }

  async function advance() {
    setConfirmSkip(false);
    if (!last) {
      setPage((p) => p + 1);
      window.scrollTo({ top: 0 });
      return;
    }
    setBusy(true);
    await api.submitBattery(battery.id);
    setBusy(false);
    setFinished(true);
  }

  async function skipBlankAndAdvance() {
    const skipped = Object.fromEntries(blank.map((it) => [it.id, null]));
    setAnswers((a) => ({ ...a, ...skipped }));
    await api.saveBatteryAnswers(battery.id, skipped);
    await advance();
  }

  if (finished) {
    return (
      <Screen>
        <Eyebrow>For the study</Eyebrow>
        <Title className="mt-1">Thank you</Title>
        <p className="mt-3 text-body">Your answers are saved for the study. They don’t affect your levels or your grade.</p>
        <Button className="mt-8" onClick={onDone}>Continue</Button>
      </Screen>
    );
  }

  return (
    <Screen>
      <div className="mb-5 flex items-center justify-between gap-3">
        <button type="button" onClick={onDone} aria-label="Close, your answers are saved" className="grid size-14 place-items-center rounded-full bg-surface shadow-[0_0_0_1px_var(--color-line)]">
          <Close />
        </button>
        <p className="meta">Page {page + 1} of {instruments.length}</p>
      </div>
      {instruments.length > 1 && <ProgressSegments total={instruments.length} current={page} className="mb-5" />}
      <Eyebrow>For the study · {battery.title}</Eyebrow>
      <Title className="mt-1">{instrument.title}</Title>
      <p className="mt-2 text-body text-muted">{instrument.intro} Not graded. You can skip any question.</p>

      <div className="mt-6 flex flex-col gap-7">
        {items.map((it, i) => (
          <Question key={it.id} n={i + 1} item={it} value={answers[it.id]} onAnswer={(v) => answer(it.id, v)} />
        ))}
      </div>

      <Button className="mt-8" disabled={busy} onClick={() => (blank.length ? setConfirmSkip(true) : void advance())}>
        {last ? "Finish" : "Next"}
      </Button>

      <Sheet
        open={confirmSkip}
        onOpenChange={setConfirmSkip}
        eyebrow="Skipping is fine"
        title={`Skip ${blank.length} ${blank.length === 1 ? "question" : "questions"}?`}
        footer={
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1" onClick={() => setConfirmSkip(false)}>Go back</Button>
            <Button className="flex-1" disabled={busy} onClick={() => void skipBlankAndAdvance()}>Skip {blank.length === 1 ? "it" : "them"}</Button>
          </div>
        }
      >
        <p className="text-body">You left these blank. We’ll record them as skipped.</p>
        <ul className="mt-3 list-disc space-y-1 pl-6 text-body text-ink/85">
          {blank.slice(0, 5).map((it) => <li key={it.id}>{it.text}</li>)}
          {blank.length > 5 && <li>and {blank.length - 5} more</li>}
        </ul>
      </Sheet>
    </Screen>
  );
}

function Question({ n, item, value, onAnswer }: { n: number; item: InstrumentItem; value: Value | undefined; onAnswer: (v: Value) => void }) {
  const labelId = useId();
  return (
    <section aria-labelledby={labelId}>
      <h2 id={labelId} className="mb-3 text-body font-bold">
        <span className="sr-only">Question {n}: </span>{item.text}
      </h2>
      <Answer format={item.response} labelId={labelId} value={value} onAnswer={onAnswer} />
      {value === null && <p className="meta mt-2">Skipped. Answer it any time before you finish.</p>}
    </section>
  );
}

function Answer({ format, labelId, value, onAnswer }: { format: ResponseFormat; labelId: string; value: Value | undefined; onAnswer: (v: Value) => void }) {
  if (format.kind === "choice") {
    return (
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {format.options.map((o) => (
          <Pill key={o.value} pressed={value === o.value} onClick={() => onAnswer(o.value)} muted={o.value === "prefer_not"}>{o.label}</Pill>
        ))}
      </div>
    );
  }
  if (format.kind === "text") return <TextAnswer labelId={labelId} placeholder={format.placeholder} value={typeof value === "string" ? value : ""} onAnswer={onAnswer} />;
  if (format.max - format.min > 10) return <SliderAnswer format={format} labelId={labelId} value={typeof value === "number" ? value : null} onAnswer={onAnswer} />;
  const points = Array.from({ length: (format.max - format.min) / format.step + 1 }, (_, i) => format.min + i * format.step);
  return (
    <div>
      <div role="group" aria-labelledby={labelId} className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
        {points.map((p, i) => (
          <button
            key={p}
            type="button"
            aria-pressed={value === p}
            aria-label={`${p}${i === 0 ? `, ${format.anchors[0]}` : i === points.length - 1 ? `, ${format.anchors[1]}` : ""}`}
            onClick={() => onAnswer(p)}
            className={clsx(
              "min-h-12 rounded-btn border-2 text-body font-bold transition-colors",
              value === p ? "border-primary bg-primary-tint text-ink" : "border-line bg-surface text-ink hover:border-ink/30",
            )}
          >
            {p}
          </button>
        ))}
      </div>
      <div className="meta mt-1.5 flex justify-between gap-4" aria-hidden>
        <span>{format.anchors[0]}</span>
        <span className="text-right">{format.anchors[1]}</span>
      </div>
    </div>
  );
}

function Pill({ pressed, muted, onClick, children }: { pressed: boolean; muted?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={clsx(
        "min-h-12 rounded-full border-2 px-4 text-body font-bold transition-colors",
        pressed ? "border-primary bg-primary-tint text-ink" : muted ? "border-dashed border-muted/70 bg-surface text-muted hover:border-ink/40" : "border-line bg-surface text-ink hover:border-ink/30",
      )}
    >
      {children}
    </button>
  );
}

/** Saved when the field loses focus, so typing doesn't write on every key. */
function TextAnswer({ labelId, placeholder, value, onAnswer }: { labelId: string; placeholder?: string; value: string; onAnswer: (v: Value) => void }) {
  const [text, setText] = useState(value);
  return (
    <input
      aria-labelledby={labelId}
      value={text}
      placeholder={placeholder}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => text.trim() !== value && onAnswer(text.trim() || null)}
      className="min-h-12 w-full rounded-btn border-2 border-line bg-surface px-4 text-body"
    />
  );
}

/**
 * The TLX's 0-100 scale in steps of 5. It starts with no answer and no visible thumb, so nothing is preselected;
 * the first tap or key press sets it. A tap on the middle, which moves nothing, still counts as answering 50.
 */
function SliderAnswer({ format, labelId, value, onAnswer }: { format: Extract<ResponseFormat, { kind: "scale" }>; labelId: string; value: number | null; onAnswer: (v: Value) => void }) {
  const mid = (format.min + format.max) / 2;
  const set = (raw: string) => onAnswer(Number(raw));
  return (
    <div>
      <input
        type="range"
        min={format.min}
        max={format.max}
        step={format.step}
        value={value ?? mid}
        aria-labelledby={labelId}
        aria-valuetext={value === null ? "Not answered" : `${value} of ${format.max}`}
        onChange={(e) => set(e.target.value)}
        // A tap that lands on the current position changes nothing, so no change event: answer on the tap itself.
        onPointerUp={(e) => value === null && set(e.currentTarget.value)}
        onClick={(e) => value === null && set(e.currentTarget.value)}
        onKeyDown={(e) => value === null && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key) && set(String(mid))}
        className={clsx("tlx-range w-full", value === null && "tlx-range-unset")}
      />
      <div className="meta mt-1 flex justify-between gap-4">
        <span aria-hidden>{format.anchors[0]}</span>
        <span className="font-bold text-ink">{value === null ? "Tap the line" : value}</span>
        <span aria-hidden className="text-right">{format.anchors[1]}</span>
      </div>
    </div>
  );
}
