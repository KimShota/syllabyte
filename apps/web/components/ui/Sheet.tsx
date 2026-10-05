"use client";

import * as Dialog from "@radix-ui/react-dialog";
import clsx from "clsx";
import type { ReactNode } from "react";
import { Close } from "./icons";

/**
 * Bottom sheet on phones, right-hand panel from 1024 px (plan Q19). Radix gives the focus
 * trap, Esc, aria-modal and focus return; we add the drag-handle look and a visible close
 * button (a drag handle alone is not an accessible way to close).
 */
export function Sheet({
  open, onOpenChange, eyebrow, title, description, children, footer,
}: {
  open: boolean; onOpenChange: (o: boolean) => void; eyebrow?: string; title: string; description?: string; children: ReactNode; footer?: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="sheet-overlay fixed inset-0 z-40 bg-ink/45" />
        <Dialog.Content
          aria-describedby={description ? undefined : undefined}
          className={clsx(
            "sheet-content fixed z-50 flex flex-col bg-surface text-ink outline-none",
            "inset-x-0 bottom-0 max-h-[90dvh] rounded-t-[28px]",
            "lg:inset-y-0 lg:left-auto lg:right-0 lg:max-h-none lg:w-[460px] lg:rounded-none lg:rounded-l-[28px]",
          )}
        >
          <div className="mx-auto mt-3 h-1.5 w-12 shrink-0 rounded-full bg-line lg:hidden" aria-hidden />
          <div className="flex items-start justify-between gap-3 px-6 pt-4">
            <div className="min-w-0">
              {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
              <Dialog.Title className="text-card font-extrabold leading-[1.25] tracking-tight">{title}</Dialog.Title>
            </div>
            <Dialog.Close aria-label="Close" className="grid size-11 shrink-0 place-items-center rounded-full bg-ink/5 hover:bg-ink/10">
              <Close size={20} />
            </Dialog.Close>
          </div>
          {description ? (
            <Dialog.Description className="px-6 pt-2 text-body text-muted">{description}</Dialog.Description>
          ) : (
            <Dialog.Description className="sr-only">{title}</Dialog.Description>
          )}
          {/* A scrolling region must be reachable by keyboard (WCAG 2.1.1), even when it holds only text. */}
          <div role="region" aria-label={title} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
          {footer && <div className="border-t border-line bg-surface px-6 pb-6 pt-4 [padding-bottom:max(1.5rem,env(safe-area-inset-bottom))]">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
