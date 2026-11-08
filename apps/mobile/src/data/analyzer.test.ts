import { describe, expect, it } from "vitest";
import type { AnalyzerMaterial } from "@syllabyte/core/api/types";
import { analyzerFrames } from "./analyzer";

const document = (id: string, pages: AnalyzerMaterial["pages"], kind: AnalyzerMaterial["kind"] = "slides"): AnalyzerMaterial => ({
  id, file_name: `${id}.pdf`, kind, state: "reading", preview_state: pages.length ? "ready" : "preparing", unit: "page", pages,
});

describe("the analyzer's uploaded pages", () => {
  it("shows every real page of the syllabus and each slide deck, in order", () => {
    const files = [document("syllabus", [{ n: 1, text: "COS 226", image_url: "/syllabus/1" }], "syllabus"),
      document("stacks", [{ n: 1, text: "Stack API", image_url: "/stacks/1" }, { n: 2, text: "Queue API", image_url: "/stacks/2" }])];
    const frames = analyzerFrames(files);
    expect(frames.map((f) => f.key)).toEqual(["syllabus:1", "stacks:1", "stacks:2"]);
    expect(frames.map((f) => f.page?.text)).toEqual(["COS 226", "Stack API", "Queue API"]);
  });

  it("keeps a queued file visible without inventing any pages or page counts", () => {
    const [frame] = analyzerFrames([document("queued", [])]);
    expect(frame.page).toBeNull();
    expect(frame.file.file_name).toBe("queued.pdf");
    expect(analyzerFrames([])).toEqual([]);
  });
});
