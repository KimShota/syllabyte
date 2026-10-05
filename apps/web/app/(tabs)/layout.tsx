"use client";

import type { ReactNode } from "react";
import { AppShell, Loading } from "@/components/AppShell";
import { useGate } from "@/lib/useGate";

export default function TabsLayout({ children }: { children: ReactNode }) {
  const ready = useGate("onboarded");
  if (!ready) return <Loading />;
  return <AppShell>{children}</AppShell>;
}
