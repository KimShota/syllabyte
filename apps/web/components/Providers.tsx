"use client";

import { useEffect, type ReactNode } from "react";
import { hydrate } from "@/lib/store";
import { DemoHost } from "./DemoMenu";
import { ToastProvider } from "./ui/Toast";

export function Providers({ children }: { children: ReactNode }) {
  useEffect(() => hydrate(), []);
  return (
    <ToastProvider>
      {children}
      <DemoHost />
    </ToastProvider>
  );
}
