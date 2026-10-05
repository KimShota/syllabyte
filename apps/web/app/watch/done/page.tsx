import { Suspense } from "react";
import { Loading } from "@/components/AppShell";
import { DoneView } from "./DoneView";

export default function DonePage() {
  return (
    <Suspense fallback={<Loading />}>
      <DoneView />
    </Suspense>
  );
}
