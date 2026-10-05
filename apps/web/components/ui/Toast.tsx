"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

interface ToastAction {
  label: string;
  onClick: () => void;
}
interface ToastItem {
  id: number;
  message: string;
  actions: ToastAction[];
  duration: number;
}

const Ctx = createContext<{ toast: (t: { message: string; actions?: ToastAction[]; duration?: number }) => void } | null>(null);

export function useToast() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useToast outside ToastProvider");
  return c.toast;
}

/**
 * Plan Q12: the toast stays 8 s and does not time out while hovered or focused (WCAG 2.2.1).
 * It sits above the tab bar so it never covers a focused control.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [item, setItem] = useState<ToastItem | null>(null);
  const next = useRef(1);
  const toast = useCallback((t: { message: string; actions?: ToastAction[]; duration?: number }) => {
    setItem({ id: next.current++, message: t.message, actions: t.actions ?? [], duration: t.duration ?? 8000 });
  }, []);
  const value = useMemo(() => ({ toast }), [toast]);
  return (
    <Ctx.Provider value={value}>
      {children}
      {item && <ToastView key={item.id} item={item} onDone={() => setItem((cur) => (cur?.id === item.id ? null : cur))} />}
    </Ctx.Provider>
  );
}

function ToastView({ item, onDone }: { item: ToastItem; onDone: () => void }) {
  const [paused, setPaused] = useState(false);
  const remaining = useRef(item.duration);
  const started = useRef(0);
  useEffect(() => {
    if (paused) return;
    started.current = Date.now();
    const t = setTimeout(onDone, remaining.current);
    return () => {
      clearTimeout(t);
      remaining.current -= Date.now() - started.current;
    };
  }, [paused, onDone]);

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-[92px] z-30 flex justify-center px-4 lg:bottom-6 lg:pl-64">
      <div
        role="status"
        aria-live="polite"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocus={() => setPaused(true)}
        onBlur={() => setPaused(false)}
        className="slide-in pointer-events-auto flex w-full max-w-[680px] items-center justify-between gap-3 rounded-card bg-ink px-5 py-3 text-white"
      >
        <p className="min-w-0 flex-1 text-body font-semibold">{item.message}</p>
        <div className="flex shrink-0 items-center gap-1">
          {item.actions.map((a) => (
            <button
              key={a.label}
              type="button"
              onClick={() => {
                a.onClick();
                onDone();
              }}
              className="min-h-11 px-2 font-semibold text-[#cfc5ff] underline underline-offset-4 decoration-2"
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
