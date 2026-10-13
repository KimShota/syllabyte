"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { getState, isOnboarded, useHydrated } from "@/lib/store";

/**
 * Sends the student to the first-run screen they still owe (Welcome → Consent → Onboarding)
 * and tells the page when it is safe to render. Waiting for hydration avoids a flash of
 * redirects on a reload.
 */
export function useGate(need: "consent" | "onboarded"): boolean {
  const hydrated = useHydrated();
  const router = useRouter();
  const s = getState();
  const ok = need === "consent" ? s.consent !== null : s.consent !== null && isOnboarded(s);
  useEffect(() => {
    if (!hydrated || ok) return;
    router.replace(s.consent === null ? "/welcome" : "/onboarding");
  }, [hydrated, ok, router, s.consent]);
  return hydrated && ok;
}
