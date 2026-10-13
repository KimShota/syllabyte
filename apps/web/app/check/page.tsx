import { Suspense } from "react";
import { CheckView } from "./CheckView";

export default function CheckPage() {
  return (
    <Suspense>
      <CheckView />
    </Suspense>
  );
}
