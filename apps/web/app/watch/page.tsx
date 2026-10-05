import { Suspense } from "react";
import { Loading } from "@/components/AppShell";
import { WatchView } from "./WatchView";

export default function WatchPage() {
  return (
    <Suspense fallback={<Loading />}>
      <WatchView />
    </Suspense>
  );
}
