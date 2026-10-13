import { describe, expect, it } from "vitest";
import { ancestorsOf, orderByPrerequisites, prerequisiteNotes } from "@/lib/logic/prereq";
import { kus } from "./kuHelpers";

const slide: Record<string, number> = { "ku-a": 1, "ku-b": 2, "ku-c": 3, "ku-d": 4, "ku-e": 5 };
const bySlide = (a: string, b: string) => slide[a] - slide[b];

describe("prerequisite graph", () => {
  it("collects ancestors through other KUs", () => {
    const a = ancestorsOf(kus);
    expect([...a.get("ku-a")!]).toEqual([]);
    expect([...a.get("ku-c")!].sort()).toEqual(["ku-a", "ku-b"]);
    expect([...a.get("ku-e")!].sort()).toEqual(["ku-a", "ku-b", "ku-c", "ku-d"]);
  });

  it("keeps the given order when the graph says nothing", () => {
    expect(orderByPrerequisites(["ku-d", "ku-a"], (x) => x, kus, bySlide)).toEqual(["ku-a", "ku-d"]);
  });

  it("puts a prerequisite before the KU that builds on it, even against the tie-break", () => {
    const reverse = (a: string, b: string) => slide[b] - slide[a]; // the comparator wants the latest slide first
    expect(orderByPrerequisites(["ku-a", "ku-c"], (x) => x, kus, reverse)).toEqual(["ku-a", "ku-c"]);
  });

  it("follows a prerequisite through a KU that is not in the list", () => {
    // a -> b -> c, and only a and c are listed: a still comes first
    const order = orderByPrerequisites(["ku-c", "ku-a"], (x) => x, kus, (x, y) => slide[y] - slide[x]);
    expect(order).toEqual(["ku-a", "ku-c"]);
  });

  it("orders a whole lecture's worth, tie-breaking only among KUs that are free to go", () => {
    const order = orderByPrerequisites(["ku-e", "ku-d", "ku-c", "ku-b", "ku-a"], (x) => x, kus, bySlide);
    expect(order).toEqual(["ku-a", "ku-b", "ku-c", "ku-d", "ku-e"]);
    expect(order.indexOf("ku-d")).toBeLessThan(order.indexOf("ku-e"));
  });

  it("does not loop on a cycle (the fixtures are checked to be a DAG, this is only a guard)", () => {
    const cyc = kus.map((k) => (k.id === "ku-a" ? { ...k, prerequisites: ["ku-b"] } : k));
    expect(orderByPrerequisites(["ku-a", "ku-b"], (x) => x, cyc, bySlide)).toHaveLength(2);
  });
});

describe("prerequisite notes", () => {
  const name = (id: string) => `Short ${id}`;

  it("explains the pairs that are really in the list, at most two", () => {
    expect(prerequisiteNotes(["ku-a", "ku-b", "ku-c"], (x) => x, kus, name)).toEqual([
      "“Short ku-a” comes first because “Short ku-b” builds on it.",
      "“Short ku-a” comes first because “Short ku-c” builds on it.",
    ]);
    expect(prerequisiteNotes(["ku-a", "ku-b", "ku-c"], (x) => x, kus, name, 3)).toHaveLength(3);
  });

  it("says nothing when nothing in the list builds on anything else", () => {
    expect(prerequisiteNotes(["ku-a", "ku-d"], (x) => x, kus, name)).toEqual([]);
  });
});
