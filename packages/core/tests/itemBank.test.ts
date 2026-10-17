import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { Item } from "../src/types";

// The per-KU item bank written by scripts/build_item_bank.py: three items per KU, one per tier, with CAT-ready
// parameters. It is local-only (course material), so without it the suite skips. Mirrors validate_bank() in
// assessment_agent/bank.py.
const path = resolve(__dirname, "../fixtures/bank.json");

describe.skipIf(!existsSync(path))("item bank", () => {
  // read lazily: a skipped suite's body still runs while tests are collected
  const load = () => {
    const bank: Item[] = JSON.parse(readFileSync(path, "utf8"));
    const byKu = new Map<string, Item[]>();
    for (const it of bank) byKu.set(it.ku_id!, [...(byKu.get(it.ku_id!) ?? []), it]);
    return { bank, byKu };
  };

  it("has unique ids and only bank items", () => {
    const { bank } = load();
    expect(new Set(bank.map((i) => i.id)).size).toBe(bank.length);
    for (const it of bank) {
      expect(it.context, it.id).toBe("assessment");
      expect(it.tier, it.id).not.toBeNull();
      expect(it.options, it.id).toHaveLength(3);
      expect(it.allows_not_sure, it.id).toBe(true);
      expect(it.discrimination, it.id).toBe(1);
      expect(it.topic_id, it.id).toMatch(/^lecture-\d+$/);
    }
  });

  it("gives every KU one item per tier, with difficulties in tier order", () => {
    const { byKu } = load();
    expect(byKu.size).toBeGreaterThan(0);
    for (const [ku, items] of byKu) {
      const tiers = items.map((i) => i.tier).sort();
      expect(tiers, ku).toEqual(["advanced", "applied", "basic"]);
      const b = (t: string) => items.find((i) => i.tier === t)!.difficulty_prior;
      expect(b("applied"), ku).toBeGreaterThan(b("basic"));
      expect(b("advanced"), ku).toBeGreaterThan(b("applied"));
    }
  });

  it("keeps each KU's three items in one topic", () => {
    const { byKu } = load();
    for (const [ku, items] of byKu) expect(new Set(items.map((i) => i.topic_id)).size, ku).toBe(1);
  });

  it("spreads the keyed answer over all three slots", () => {
    const { bank } = load();
    const counts = [0, 1, 2].map((s) => bank.filter((i) => i.correct_index === s).length);
    expect(Math.max(...counts) - Math.min(...counts)).toBeLessThanOrEqual(2);
  });
});
