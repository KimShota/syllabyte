import { Suspense } from "react";
import { Loading } from "@/components/AppShell";
import { ClaimsView } from "./ClaimsView";

export default function ClaimsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ClaimsView />
    </Suspense>
  );
}
