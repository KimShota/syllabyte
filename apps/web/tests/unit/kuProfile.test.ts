import { describe, expect, it } from "vitest";
import { estimateTheta } from "@/lib/logic/cat";
import {
  answersFor, bankItems, evidenceItems, kuLevels, lectureEstimate, levelUpdates, pooledEstimate, toBankItem,
} from "@/lib/logic/kuProfile";
import { lectureTopics } from "@/lib/logic/lectures";
import { answer, bank, course, items, kus } from "./kuHelpers";

const input = (responses: ReturnType<typeof answer>[]) => ({ course, items, responses });

describe("lectures are the topics", () => {
  it("derives one topic per lecture from the course, in order", () => {
    const t = lectureTopics(course);
    expect(t.map((x) => [x.id, x.n, x.title])).toEqual([["lecture-1", 1, "Lecture One"], ["lecture-2", 2, "Lecture Two"], ["lecture-3", 3, "Lecture Three"]]);
    expect(t.map((x) => x.ku_ids)).toEqual([["ku-a", "ku-b"], ["ku-c", "ku-d"], ["ku-e"]]);
  });
});

describe("evidence for a lecture", () => {
  it("is the bank and the video items of that lecture's KUs only", () => {
    expect(evidenceItems(course, items, 1).map((i) => i.id)).toContain("cp-ku-a");
    expect(evidenceItems(course, items, 2).every((i) => ["ku-c", "ku-d"].includes(i.ku_id!))).toBe(true);
    expect(bankItems(course, items, 1)).toHaveLength(6);
    expect(bankItems(course, items, 1).every((i) => i.context === "assessment")).toBe(true);
  });

  it("ignores contexts that are not about a KU (retention)", () => {
    const stray = { ...bank[0], id: "x", context: "retention" as const };
    expect(evidenceItems(course, [...items, stray], 1).map((i) => i.id)).not.toContain("x");
  });
});

describe("answersFor", () => {
  it("keeps the latest answer to a repeated item, ordered by when that answer was given", () => {
    const first = answer("as-ku-a-basic", "wrong");
    const other = answer("as-ku-a-applied", "right");
    const again = answer("as-ku-a-basic", "right"); // Watch again re-asks it
    const got = answersFor(bank.map(toBankItem), [first, other, again]);
    expect(got.map((a) => [a.item_id, a.outcome])).toEqual([["as-ku-a-applied", "correct"], ["as-ku-a-basic", "correct"]]);
  });

  it("maps 'Not sure' and carries the hint flag, and skips items outside the pool", () => {
    const got = answersFor(bank.map(toBankItem), [answer("as-ku-a-basic", "not_sure"), answer("as-ku-b-basic", "right", { hint_used: true }), answer("cp-ku-a", "right")]);
    expect(got).toEqual([
      { item_id: "as-ku-a-basic", outcome: "not_sure", hinted: false },
      { item_id: "as-ku-b-basic", outcome: "correct", hinted: true },
    ]);
  });
});

describe("lecture estimate", () => {
  it("counts answers and matches the engine's own estimate", () => {
    const rs = [answer("as-ku-a-basic", "right"), answer("as-ku-b-applied", "wrong"), answer("as-ku-a-advanced", "not_sure"), answer("as-ku-b-basic", "right")];
    const est = lectureEstimate(input(rs), 1);
    expect(est).toMatchObject({ n_shown: 4, n_scored: 3, n_right: 2, n_not_sure: 1 });
    const pool = evidenceItems(course, items, 1).map(toBankItem);
    expect(est.theta).toBe(estimateTheta(pool, answersFor(pool, rs), 0, 1));
    expect(Number.isFinite(est.se)).toBe(true);
  });

  it("is untouched by answers about other lectures", () => {
    const rs = [answer("as-ku-a-basic", "right"), answer("as-ku-c-basic", "wrong")];
    expect(lectureEstimate(input(rs), 1).n_shown).toBe(1);
    expect(lectureEstimate(input(rs), 3)).toMatchObject({ n_shown: 0, theta: 0, se: Infinity });
  });

  it("counts a quick-check answer from a video toward its lecture, and a hinted one for less", () => {
    const base = [answer("as-ku-a-basic", "right"), answer("as-ku-b-applied", "wrong"), answer("as-ku-b-advanced", "wrong")];
    const plain = lectureEstimate(input([...base, answer("cp-ku-a", "right")]), 1);
    const hinted = lectureEstimate(input([...base, answer("cp-ku-a", "right", { hint_used: true })]), 1);
    expect(plain.n_scored).toBe(4);
    expect(hinted.theta).toBeLessThan(plain.theta);
  });

  it("pools the answers of every lecture", () => {
    const rs = [answer("as-ku-a-basic", "right"), answer("as-ku-c-basic", "wrong"), answer("as-ku-e-applied", "right")];
    expect(pooledEstimate(input(rs))).toMatchObject({ n_shown: 3, n_scored: 3, n_right: 2 });
  });
});

describe("KU levels", () => {
  it("starts everything at Level 1, not checked, before any answer", () => {
    const lv = kuLevels(input([]));
    expect(Object.keys(lv).sort()).toEqual(kus.map((k) => k.id).sort());
    for (const l of Object.values(lv)) {
      expect(l).toMatchObject({ level: 1, not_checked: true, provisional: false, theta: null });
      expect(l.reason).toMatch(/^Not covered yet\. We will check this when “Lecture (One|Two|Three)” comes up\.$/);
    }
  });

  it("rates every KU of an asked lecture from its own items, and borrows the pooled theta for the rest", () => {
    // a student who gets everything right on lecture 1
    const rs = ["as-ku-a-basic", "as-ku-a-applied", "as-ku-b-basic", "as-ku-b-advanced"].map((id) => answer(id, "right"));
    const lv = kuLevels(input(rs));
    expect(lv["ku-a"]).toMatchObject({ provisional: false, not_checked: false, n_scored: 4, n_right: 4 });
    expect(lv["ku-a"].level).toBeGreaterThanOrEqual(2);
    expect(lv["ku-c"]).toMatchObject({ provisional: true, not_checked: false });
    expect(lv["ku-c"].reason).toMatch(/^We have not asked about “Lecture Two” yet\. From your 4 answers so far \(4 right\)/);
    expect(lv["ku-c"].theta).toBe(lv["ku-e"].theta); // one pooled theta for lectures not asked about
  });

  it("gives two KUs of one lecture different levels at the same theta, from their own item difficulties", () => {
    // right on the easy KU's items, wrong on the hard KU's: theta lands between them
    const rs = [answer("as-ku-a-basic", "right"), answer("as-ku-a-applied", "right"), answer("as-ku-a-advanced", "right"),
      answer("as-ku-b-basic", "right"), answer("as-ku-b-applied", "wrong"), answer("as-ku-b-advanced", "wrong")];
    const lv = kuLevels(input(rs));
    expect(lv["ku-a"].theta).toBe(lv["ku-b"].theta);
    expect(lv["ku-a"].level).toBeGreaterThan(lv["ku-b"].level);
  });

  it("makes a lecture answered entirely 'Not sure' novice, and leaves other lectures unchecked", () => {
    const rs = ["as-ku-a-basic", "as-ku-b-basic", "as-ku-a-applied"].map((id) => answer(id, "not_sure"));
    const lv = kuLevels(input(rs));
    expect(lv["ku-a"]).toMatchObject({ level: 1, not_checked: false, provisional: false });
    expect(lv["ku-a"].reason).toBe("You chose “Not sure” on all 3 questions on “Lecture One”, so videos start from the basics with more hints.");
    expect(lv["ku-c"]).toMatchObject({ level: 1, not_checked: true });
  });

  it("says 'both' for two 'Not sure' answers", () => {
    const lv = kuLevels(input(["as-ku-a-basic", "as-ku-b-basic"].map((id) => answer(id, "not_sure"))));
    expect(lv["ku-a"].reason).toContain("on both questions on");
  });

  it("builds every reason from the stored counts (rule 4)", () => {
    const rs = [answer("as-ku-a-basic", "right"), answer("as-ku-b-applied", "wrong"), answer("as-ku-b-basic", "right"), answer("as-ku-a-advanced", "not_sure")];
    const l = kuLevels(input(rs))["ku-a"];
    expect(l).toMatchObject({ n_scored: 3, n_right: 2, n_not_sure: 1 });
    expect(l.reason).toContain("From your 3 answers on “Lecture One” (2 right, and 1 “Not sure” did not count)");
  });

  it("never lets a stronger set of answers produce a lower level for a KU", () => {
    const order = ["as-ku-a-basic", "as-ku-b-basic", "as-ku-a-applied", "as-ku-b-applied", "as-ku-a-advanced", "as-ku-b-advanced"];
    const levelAfter = (right: number) =>
      kuLevels(input(order.map((id, k) => answer(id, k < right ? "right" : "wrong"))))["ku-b"].level;
    for (let k = 1; k < 5; k++) expect(levelAfter(k + 1)).toBeGreaterThanOrEqual(levelAfter(k));
  });
});

describe("level updates (the 'What changed and why' card)", () => {
  const titles = new Map(course.lectures.map((l) => [l.n, l.title]));

  it("lists only KUs whose level moved, with direction and a counted reason", () => {
    const strong = ["as-ku-a-basic", "as-ku-a-applied", "as-ku-a-advanced", "as-ku-b-basic", "as-ku-b-applied"].map((id) => answer(id, "right"));
    const next = kuLevels(input(strong));
    const published = Object.fromEntries(kus.map((k) => [k.id, 1 as const]));
    const ups = levelUpdates(published, next, kus, titles);
    expect(ups.length).toBeGreaterThan(0);
    for (const u of ups) {
      expect(u).toMatchObject({ from: 1, direction: "up" });
      expect(u.to).toBe(next[u.ku_id].level);
      expect(u.reason).toContain(`Level 1 → ${u.to}`);
      expect(u.reason).toContain(`${next[u.ku_id].n_right} of ${next[u.ku_id].n_scored} right`);
    }
    expect(levelUpdates(Object.fromEntries(kus.map((k) => [k.id, next[k.id].level])), next, kus, titles)).toEqual([]);
  });

  it("reports a drop, and skips KUs with nothing checked yet", () => {
    const weak = ["as-ku-a-basic", "as-ku-b-basic"].map((id) => answer(id, "wrong"));
    const next = kuLevels(input(weak));
    const published = Object.fromEntries(kus.map((k) => [k.id, 3 as const]));
    const downs = levelUpdates(published, next, kus, titles);
    expect(downs.every((u) => u.direction === "down" && u.to < u.from)).toBe(true);
    expect(levelUpdates(published, kuLevels(input([])), kus, titles)).toEqual([]); // not_checked is not a change
  });
});
