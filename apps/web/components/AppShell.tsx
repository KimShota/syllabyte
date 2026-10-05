"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { BarsIcon, DocIcon, ListIcon } from "./ui/icons";

const TABS = [
  { href: "/playlist", label: "Playlist", Icon: ListIcon },
  { href: "/levels", label: "My levels", Icon: BarsIcon },
  { href: "/course", label: "Course", Icon: DocIcon },
];

/** Bottom tab bar on phones, left sidebar from 1024 px (plan Q19). */
export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  return (
    <div className="min-h-dvh lg:pl-64">
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r border-line bg-surface px-4 py-8 lg:flex">
        <p className="mb-8 px-3 text-card font-extrabold tracking-tight">
          Sylla<span className="text-primary">Byte</span>
        </p>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {TABS.map(({ href, label, Icon }) => {
            const active = path.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={clsx("flex min-h-12 items-center gap-3 rounded-btn px-3 font-bold", active ? "bg-primary-tint text-primary" : "text-ink hover:bg-ink/5")}
              >
                <Icon size={22} />
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <main className="mx-auto w-full max-w-[720px] px-5 pb-32 pt-6 lg:pb-16 lg:pt-10">{children}</main>

      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-surface [padding-bottom:env(safe-area-inset-bottom)] lg:hidden">
        {TABS.map(({ href, label, Icon }) => {
          const active = path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={clsx("flex min-h-[72px] flex-1 flex-col items-center justify-center gap-1 text-meta font-bold", active ? "text-primary" : "text-muted")}
            >
              <Icon size={26} />
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

/** A centered page for first-run, quiz and player screens (no tab bar). */
export function Screen({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return <main className={clsx("mx-auto w-full px-5 pb-10 pt-5 lg:pt-10", wide ? "max-w-[1040px]" : "max-w-[600px]")}>{children}</main>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="grid min-h-[50dvh] place-items-center" role="status">
      <p className="meta">{label}</p>
    </div>
  );
}
