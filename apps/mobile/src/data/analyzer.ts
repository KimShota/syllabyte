import type { AnalyzerMaterial } from "@syllabyte/core/api/types";

export const MATERIAL_STATUS: Record<AnalyzerMaterial["state"], string> = {
  queued: "Waiting to process", reading: "Reading document", organizing: "Organizing slides",
  analyzing: "Building your learning roadmap", ready: "Processed", failed: "Couldn’t process this file",
};

/** Walk actual uploaded pages in document order; keep each file visible while previews are prepared. */
export function analyzerFrames(materials: readonly AnalyzerMaterial[]) {
  return materials.flatMap((file) => {
    const pages: (AnalyzerMaterial["pages"][number] | null)[] = file.pages.length ? file.pages : [null];
    return pages.map((page) => ({ file, page, key: `${file.id}:${page?.n ?? "pending"}` }));
  });
}
