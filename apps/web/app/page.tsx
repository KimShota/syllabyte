"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Loading } from "@/components/AppShell";
import { getState, isOnboarded, useHydrated } from "@/lib/store";

export default function Home() {
  const hydrated = useHydrated();
  const router = useRouter();
  useEffect(() => {
    if (!hydrated) return;
    const s = getState();
    router.replace(s.consent === null ? "/welcome" : !isOnboarded(s) ? "/onboarding" : "/playlist");
  }, [hydrated, router]);
  return <Loading />;
}
