import { describe, expect, it } from "vitest";
import { proposeForTopic, proposeLevels, type ProposalInput } from "@/lib/logic/proposals";
import { course, item, level, resp, T0, topics, video } from "./helpers";

const base = (over: Partial<ProposalInput> = {}): ProposalInput => ({
  course, items: [item("rc-t2-1", "t2", "recheck")], videos: [video("v2", "t2", 1, 10)], responses: [],
  levels: { t1: level("t1", 3), t2: level("t2", 2), t3: level("t3", 1), t4: level("t4", 2) },
  watched: {}, semesterStart: T0 - 6 * 7 * 86_400_000, now: T0, ...over,
});
const R = (ctx: "recheck" | "checkpoint" | "next_session", choice: number | "not_sure", extra = {}) => resp(`i-${Math.random()}`, "t2", ctx, choice, extra);

describe("proposeForTopic (plan §4.4)", () => {
  it("score >= 0.8 with >=3 answered -> up one level, numbers match the data", () => {
    const rs = [R("recheck", 1), R("recheck", 1), R("checkpoint", 1), R("next_session", 1)];
    const p = proposeForTopic(base({ responses: rs }), topics[1]);
    expect(p).toMatchObject({ direction: "up", from: 2, to: 3, answered: 4, correct: 4 });
    expect(p.reason).toContain("4 of 4 right");
  });
  it("score <= 0.4 -> down one level", () => {
    const rs = [R("recheck", 0), R("checkpoint", 0), R("next_session", 1)];
    const p = proposeForTopic(base({ responses: rs }), topics[1]);
    expect(p).toMatchObject({ direction: "down", from: 2, to: 1 });
    expect(p.reason).toContain("1 of 3 right");
  });
  it("in between -> no change", () => {
    const rs = [R("recheck", 1), R("checkpoint", 1), R("next_session", 0)];
    expect(proposeForTopic(base({ responses: rs }), topics[1]).direction).toBe("same");
  });
  it("more than half 'Not sure' -> down, even with few answers (needs >= 3 presented)", () => {
    const rs = [R("recheck", "not_sure"), R("recheck", "not_sure"), R("checkpoint", 1)];
    const p = proposeForTopic(base({ responses: rs }), topics[1]);
    expect(p).toMatchObject({ direction: "down", to: 1, not_sure: 2, answered: 1 });
    expect(p.reason).toContain("2 of 3 answers were “Not sure”");
  });
  it("fewer than 3 presented -> not enough answers, level unchanged", () => {
    const p = proposeForTopic(base({ responses: [R("recheck", 1), R("checkpoint", 1)] }), topics[1]);
    expect(p).toMatchObject({ direction: "not_enough", from: 2, to: 2 });
  });
  it("never goes above 3 or below 1", () => {
    const rs = [R("recheck", 1), R("checkpoint", 1), R("next_session", 1)];
    expect(proposeForTopic(base({ responses: rs, levels: { ...base().levels, t2: level("t2", 3) } }), topics[1]).to).toBe(3);
    const bad = [R("recheck", 0), R("checkpoint", 0), R("next_session", 0)];
    expect(proposeForTopic(base({ responses: bad, levels: { ...base().levels, t2: level("t2", 1) } }), topics[1]).to).toBe(1);
  });
  it("a correct answer after a hint earns half credit", () => {
    // 3 right but all hinted -> credit 1.5 / 3 = 0.5 -> no change, not up
    const rs = [R("recheck", 1, { hint_used: true }), R("checkpoint", 1, { hint_used: true }), R("next_session", 1, { hint_used: true })];
    expect(proposeForTopic(base({ responses: rs }), topics[1])).toMatchObject({ direction: "same", score: 0.5 });
  });
  it("onboarding answers are the Week 1 baseline, not part of the pool", () => {
    const rs = [resp("ob", "t2", "onboarding", 0), R("recheck", 1), R("checkpoint", 1), R("next_session", 1)];
    const p = proposeForTopic(base({ responses: rs }), topics[1]);
    expect(p.answered).toBe(3);
    expect(p.reason).toContain("up from 0 of 1 in Week 1");
  });
  it("a level the student set is flagged on the proposal", () => {
    const set = level("t2", 2, "student", T0 - 3 * 7 * 86_400_000);
    const rs = [R("recheck", 1), R("checkpoint", 1), R("next_session", 1)];
    const p = proposeForTopic(base({ responses: rs, levels: { ...base().levels, t2: set } }), topics[1]);
    expect(p.note).toBe("You set this level in Week 4.");
  });
  it("mentions the videos watched only when all of them were", () => {
    const rs = [R("recheck", 1), R("checkpoint", 1), R("next_session", 1)];
    const watched = { v2: { first_at: T0, last_at: T0, views: 1 } };
    expect(proposeForTopic(base({ responses: rs, watched }), topics[1]).reason).toContain("You watched the “Potential outcomes” video.");
    expect(proposeForTopic(base({ responses: rs }), topics[1]).reason).not.toContain("watched");
  });
  it("proposeLevels returns one proposal per topic", () => {
    expect(proposeLevels(base())).toHaveLength(4);
  });
});
