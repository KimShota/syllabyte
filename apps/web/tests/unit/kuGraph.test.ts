import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The Knowledge Unit Graph the pipeline builds (Bloom level + prerequisite edges) must reach the app
// intact: per-KU profiling (plan/per-ku-profiling-plan.md) reads both. Fixtures are local-only
// (course material), so without them the suite skips rather than failing a fresh clone.
const haveFixtures = existsSync(resolve(__dirname, "../../fixtures/course.json"));

describe.skipIf(!haveFixtures)("Knowledge Unit graph in the fixtures", () => {
  const BLOOM = ["remember", "understand", "apply", "analyze", "evaluate", "create"];

  async function load() {
    return (await import("@/lib/fixtures")).FIX;
  }

  it("gives every KU a Bloom level", async () => {
    const { course } = await load();
    expect(course.kus.length).toBeGreaterThan(0);
    for (const k of course.kus) expect(BLOOM, k.id).toContain(k.bloom_level);
  });

  it("only lists prerequisites that are KUs of the course, never itself", async () => {
    const { course } = await load();
    const ids = new Set(course.kus.map((k) => k.id));
    for (const k of course.kus) {
      for (const p of k.prerequisites) {
        expect(ids.has(p), `${k.id} -> ${p}`).toBe(true);
        expect(p).not.toBe(k.id);
      }
    }
  });

  it("is acyclic", async () => {
    const { course } = await load();
    const byId = new Map(course.kus.map((k) => [k.id, k]));
    const state = new Map<string, "visiting" | "done">();
    const visit = (id: string, path: string[]) => {
      if (state.get(id) === "done") return;
      expect(state.get(id), `cycle: ${[...path, id].join(" -> ")}`).not.toBe("visiting");
      state.set(id, "visiting");
      for (const p of byId.get(id)!.prerequisites) visit(p, [...path, id]);
      state.set(id, "done");
    };
    for (const k of course.kus) visit(k.id, []);
  });

  it("carries the IRT fields on every item, with discrimination fixed at 1 for now", async () => {
    const { items } = await load();
    for (const it of items) {
      expect(it.discrimination, it.id).toBe(1);
      expect(it.tier === null || ["basic", "applied", "advanced"].includes(it.tier), it.id).toBe(true);
    }
  });
});
