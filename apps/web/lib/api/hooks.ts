"use client";

import { useEffect, useRef, useState } from "react";
import { useStoreVersion } from "@/lib/store";

/**
 * Re-runs `fn` on mount and whenever the store changes (the mock) or `deps` change.
 * Keeps the previous data while refetching, so lists don't flash empty.
 */
export function useQuery<T>(fn: () => Promise<T>, deps: readonly unknown[] = []): { data: T | undefined; loading: boolean } {
  const version = useStoreVersion();
  const [data, setData] = useState<T | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const run = useRef(0);
  useEffect(() => {
    const id = ++run.current;
    fn().then((d) => {
      if (id === run.current) {
        setData(d);
        setLoading(false);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, ...deps]);
  return { data, loading };
}
