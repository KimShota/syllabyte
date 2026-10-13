import { Suspense } from "react";
import { StudyView } from "./StudyView";

export default function StudyPage() {
  return (
    <Suspense>
      <StudyView />
    </Suspense>
  );
}
