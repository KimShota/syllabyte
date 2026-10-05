"use client";

import clsx from "clsx";
import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Check, ChevronLeft } from "./icons";

// ---------------------------------------------------------------- buttons

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet"; full?: boolean };

const base =
  "inline-flex items-center justify-center gap-2 min-h-14 px-6 rounded-btn font-bold text-body transition-colors disabled:opacity-45 select-none";

export function Button({ variant = "primary", full = true, className, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        base,
        full && "w-full",
        variant === "primary" && "bg-primary text-white hover:bg-primary-hover",
        variant === "secondary" && "bg-surface text-ink border-2 border-line hover:border-ink/30",
        variant === "quiet" && "bg-transparent text-ink hover:bg-ink/5",
        className,
      )}
      {...rest}
    />
  );
}

export function LinkButton({ href, variant = "primary", className, children, full = true }: { href: string; variant?: ButtonProps["variant"]; className?: string; children: ReactNode; full?: boolean }) {
  return (
    <Link
      href={href}
      className={clsx(
        base,
        full && "w-full",
        variant === "primary" && "bg-primary text-white hover:bg-primary-hover",
        variant === "secondary" && "bg-surface text-ink border-2 border-line hover:border-ink/30",
        variant === "quiet" && "bg-transparent text-ink hover:bg-ink/5",
        className,
      )}
    >
      {children}
    </Link>
  );
}

/** The underlined links of the wireframe ("Change order", "Say why", "Undo"…). 44 px tall hit area. */
export function TextLink({ className, type = "button", tone = "primary", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "ink" | "muted" }) {
  return (
    <button
      type={type}
      className={clsx(
        "inline-flex min-h-11 items-center font-semibold underline underline-offset-4 decoration-2",
        tone === "primary" && "text-primary",
        tone === "ink" && "text-ink",
        tone === "muted" && "text-muted",
        className,
      )}
      {...rest}
    />
  );
}

export function NavLink({ href, children, className, tone = "primary" }: { href: string; children: ReactNode; className?: string; tone?: "primary" | "ink" | "muted" }) {
  return (
    <Link
      href={href}
      className={clsx(
        "inline-flex min-h-11 items-center font-semibold underline underline-offset-4 decoration-2",
        tone === "primary" && "text-primary",
        tone === "ink" && "text-ink",
        tone === "muted" && "text-muted",
        className,
      )}
    >
      {children}
    </Link>
  );
}

export function BackButton({ href, onClick, label = "Back" }: { href?: string; onClick?: () => void; label?: string }) {
  const cls = "grid size-14 shrink-0 place-items-center rounded-full bg-surface text-ink shadow-[0_0_0_1px_var(--color-line)] hover:bg-white";
  if (href) {
    return (
      <Link href={href} aria-label={label} className={cls}>
        <ChevronLeft />
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} aria-label={label} className={cls}>
      <ChevronLeft />
    </button>
  );
}

// ------------------------------------------------------------- cards / text

export function Card({ className, children, as: As = "div", ...rest }: { className?: string; children: ReactNode; as?: "div" | "section" | "li" } & React.HTMLAttributes<HTMLElement>) {
  return (
    <As className={clsx("rounded-card border border-line bg-surface p-5", className)} {...rest}>
      {children}
    </As>
  );
}

export function InfoCard({ eyebrow, title, children, tone = "plain", className }: { eyebrow?: string; title?: string; children?: ReactNode; tone?: "plain" | "teal" | "grey"; className?: string }) {
  return (
    <section
      className={clsx(
        "rounded-card p-5",
        tone === "plain" && "border border-line bg-surface",
        tone === "teal" && "bg-new-bg text-new-fg",
        tone === "grey" && "bg-ink/[0.045]",
        className,
      )}
    >
      {eyebrow && <p className={clsx("eyebrow mb-1.5", tone === "teal" && "!text-new-fg")}>{eyebrow}</p>}
      {title && <h3 className="mb-1 text-body font-bold">{title}</h3>}
      <div className={clsx("text-body", tone !== "teal" && "text-ink/85")}>{children}</div>
    </section>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={clsx("eyebrow", className)}>{children}</p>;
}

export function Title({ children, className, as: As = "h1" }: { children: ReactNode; className?: string; as?: "h1" | "h2" }) {
  return <As className={clsx("text-title font-extrabold tracking-tight text-ink", className)}>{children}</As>;
}

// ----------------------------------------------------------- tags & badges

const TAGS = {
  gap: { label: "Fills a gap", cls: "bg-gap-bg text-gap-fg" },
  refresher: { label: "Refresher", cls: "bg-refresher-bg text-refresher-fg" },
  new: { label: "New for you", cls: "bg-new-bg text-new-fg" },
  you_added: { label: "You added", cls: "bg-added-bg text-added-fg" },
} as const;

export function Tag({ tag }: { tag: keyof typeof TAGS }) {
  return <span className={clsx("inline-block rounded-full px-3 py-1 text-meta font-bold", TAGS[tag].cls)}>{TAGS[tag].label}</span>;
}

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx("inline-flex items-center rounded-full border border-line bg-surface px-3 py-1 text-meta font-bold", className)}>{children}</span>;
}

const STATUS = {
  unreviewed: { text: "Not yet reviewed by your instructor", cls: "border-line bg-surface text-ink" },
  flagged: { text: "A student flagged part of this video · being checked", cls: "border-amber-line bg-gap-bg text-gap-fg" },
  approved: { text: "Reviewed by your instructor", cls: "border-ok-line bg-ok-bg text-new-fg" },
  hidden: { text: "Taken down for fixes", cls: "border-line bg-surface text-muted" },
} as const;

export function StatusBadge({ status, className }: { status: keyof typeof STATUS; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center rounded-full border-[1.5px] px-3 py-1 text-meta font-bold", STATUS[status].cls, className)}>
      {STATUS[status].text}
    </span>
  );
}

// ------------------------------------------------------------ level visuals

export function LevelBar({ level, className }: { level: 1 | 2 | 3; className?: string }) {
  return (
    <div className={clsx("flex flex-1 gap-1.5", className)} role="img" aria-label={`Level ${level} of 3`}>
      {[1, 2, 3].map((n) => (
        <span key={n} className={clsx("h-2 flex-1 rounded-full", n <= level ? "bg-primary" : "bg-line")} />
      ))}
    </div>
  );
}

export function ProgressSegments({ total, current, className }: { total: number; current: number; className?: string }) {
  return (
    <div className={clsx("flex gap-2", className)} role="img" aria-label={`Question ${current + 1} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={clsx("h-2 flex-1 rounded-full", i < current ? "bg-primary" : i === current ? "bg-ink" : "bg-line")} />
      ))}
    </div>
  );
}

// ------------------------------------------------------------- choice inputs

export type ChoiceState = "idle" | "correct" | "wrong" | "reveal-correct" | "dim";

/** A tall, tappable answer. `aria-pressed` toggle in a `role=group`: one clear selection model for every quiz. */
export function ChoiceCard({
  children, selected, notSure, state = "idle", disabled, onClick, className,
}: {
  children: ReactNode; selected?: boolean; notSure?: boolean; state?: ChoiceState; disabled?: boolean; onClick?: () => void; className?: string;
}) {
  const reveal = state !== "idle";
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        "flex min-h-[60px] w-full items-center justify-between gap-3 rounded-btn px-5 py-3 text-left text-body font-semibold transition-colors",
        !reveal && !notSure && !selected && "border-2 border-line bg-surface hover:border-ink/30",
        !reveal && !notSure && selected && "border-2 border-primary bg-primary-tint",
        !reveal && notSure && !selected && "border-[1.5px] border-dashed border-muted/70 bg-surface text-muted hover:border-ink/40",
        !reveal && notSure && selected && "border-2 border-dashed border-primary bg-primary-tint text-ink",
        state === "correct" && "border-2 border-ok-line bg-ok-bg",
        state === "reveal-correct" && "border-2 border-ok-line bg-ok-bg",
        state === "wrong" && "border-2 border-amber-line bg-gap-bg",
        state === "dim" && "border-2 border-line bg-surface opacity-55",
        disabled && !reveal && "opacity-60",
        className,
      )}
    >
      <span className="min-w-0">{children}</span>
      {(state === "correct" || state === "reveal-correct") && <Check className="shrink-0 text-new-fg" />}
    </button>
  );
}

export function SegmentedRow<T extends string>({
  options, value, onChange, label, className,
}: {
  options: { value: T; label: string }[]; value: T | null | undefined; onChange: (v: T) => void; label: string; className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={clsx("flex flex-wrap gap-2", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "min-h-12 flex-1 rounded-full border-2 px-4 text-body font-bold transition-colors",
            value === o.value ? "border-primary bg-primary-tint text-ink" : "border-line bg-surface text-ink hover:border-ink/30",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
