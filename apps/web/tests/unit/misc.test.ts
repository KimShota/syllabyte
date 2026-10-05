import { describe, expect, it } from "vitest";
import { calibrationBlock1, calibrationBlock2 } from "@/lib/logic/calibration";
import { icsFor } from "@/lib/logic/ics";
import { createTask, currentNextSession, isEligible } from "@/lib/logic/nextSession";
import { changesCount, tailoringRows } from "@/lib/logic/receipt";
import { describeSlot, recheckSlots, startOfWeek, weekOf } from "@/lib/logic/time";
import { DAY, HOUR } from "@/lib/util";
import { course, resp, T0, topics, video } from "./helpers";

describe("next-session check (plan Q13)", () => {
  const v = video("a", "t1", 1, 6);
  const cfg = course.config;
  it("is due 12 h after watching and expires after 7 days", () => {
    const task = createTask(v, T0, cfg);
    expect(isEligible(task, T0 + 11 * HOUR)).toBe(false);
    expect(isEligible(task, T0 + 12 * HOUR)).toBe(true);
    expect(isEligible(task, T0 + 7 * DAY)).toBe(false);
  });
  it("shows the oldest first and at most 2 per visit", () => {
    const a = createTask(video("a", "t1", 1, 6), T0, cfg);
    const b = createTask(video("b", "t2", 1, 10), T0 + HOUR, cfg);
    const c = createTask(video("c", "t3", 2, 18), T0 + 2 * HOUR, cfg);
    const now = T0 + 20 * HOUR;
    expect(currentNextSession([c, b, a], now, cfg, { handled: 0 })?.task.video_id).toBe("a");
    expect(currentNextSession([c, b, a], now, cfg, { handled: 1 })?.remaining).toBe(0);
    expect(currentNextSession([c, b, a], now, cfg, { handled: 2 })).toBeNull();
  });
  it("skips answered tasks", () => {
    const a = { ...createTask(v, T0, cfg), done: true };
    expect(currentNextSession([a], T0 + 20 * HOUR, cfg, { handled: 0 })).toBeNull();
  });
});

describe("calibration (plan Q35)", () => {
  const cp = (conf: "guess" | "pretty" | "certain", choice: number, hint = false) => resp("cp", "t1", "checkpoint", choice, { confidence: conf, hint_used: hint });
  it("block 1 stays hidden below 5 rated answers", () => {
    const b = calibrationBlock1([cp("certain", 1), cp("guess", 0)]);
    expect(b.ready).toBe(false);
    expect(b.sentences).toEqual([]);
  });
  it("block 1 counts a correct-after-hint answer as right and writes the matching sentences", () => {
    const rs = [cp("certain", 1), cp("certain", 0), cp("certain", 1, true), cp("pretty", 1), cp("pretty", 1), cp("guess", 0), cp("guess", 0)];
    const b = calibrationBlock1(rs);
    expect(b.ready).toBe(true);
    expect(b.rows.find((r) => r.confidence === "certain")).toMatchObject({ right: 2, n: 3 });
    expect(b.sentences[0]).toBe("Your “Certain” answers were right 2 times in 3, no better than “Pretty sure”.");
    expect(b.sentences[1]).toMatch(/guesses were honest/);
  });
  it("block 1 says confidence matches when nothing is off", () => {
    const rs = [cp("certain", 1), cp("certain", 1), cp("pretty", 1), cp("pretty", 0), cp("guess", 0), cp("guess", 1)];
    expect(calibrationBlock1(rs).sentences).toEqual(["Your confidence matches your results well."]);
  });
  it("block 2 pairs a guess with the next-day result and summarises after 3 pairs", () => {
    const vids = [video("a", "t1", 1, 6), video("b", "t2", 1, 10), video("c", "t3", 2, 18)];
    const mk = (vid: string, jol: "yes" | "maybe" | "no", correct: boolean, at: number) => ({
      id: vid, video_id: vid, item_id: "", jol, due_after: 0, expires_at: 0, done: true, flagged_guess: false, result: { choice: 1, correct, at },
    });
    const b = calibrationBlock2([mk("a", "yes", true, 1), mk("b", "yes", false, 2), mk("c", "maybe", true, 3)], vids);
    expect(b.pairs).toHaveLength(3);
    expect(b.summary).toBe("When you said Yes, you got the next-day question right 1 of 2 times.");
    expect(calibrationBlock2([mk("a", "yes", true, 1)], vids).summary).toBeNull();
  });
});

describe("tailoring receipt (plan §2 rule 4)", () => {
  const v = video("a", "t1", 1, 6);
  it("every 'why' is true to the stored answers", () => {
    const rs = [resp("o1", "t1", "onboarding", 1), resp("o2", "t1", "onboarding", 1)];
    const rows = tailoringRows(v, 2, topics, rs);
    expect(rows[0].why).toBe("You answered both questions on “Causal questions” correctly.");
    expect(rows[1].why).toBe("Standard for Level 2."); // nothing missed, so no extra example is justified
    expect(changesCount(rows)).toBe(2);
  });
  it("explains an added example by a 'Not sure' answer", () => {
    const rows = tailoringRows(v, 2, topics, [resp("o1", "t1", "onboarding", "not_sure")]);
    expect(rows[1].why).toBe("You marked “Not sure” on a question on “Causal questions”.");
    expect(rows[0].why).toBe("Standard for Level 2.");
  });
  it("falls back to 'Standard for Level N' with no evidence", () => {
    expect(tailoringRows(v, 3, topics, []).every((r) => r.why === "Standard for Level 3.")).toBe(true);
  });
});

describe("time helpers", () => {
  const at = (iso: string) => new Date(iso).getTime();
  it("weekOf counts from the semester start", () => {
    expect(weekOf(T0, T0)).toBe(1);
    expect(weekOf(T0 + 6 * 7 * DAY + DAY, T0)).toBe(7);
  });
  it("startOfWeek is Monday 00:00 local", () => {
    const m = new Date(startOfWeek(at("2026-10-08T15:00:00"))); // a Thursday
    expect([m.getDay(), m.getHours()]).toEqual([1, 0]);
  });
  it("offers Now, Tonight, Tomorrow and Friday on a Wednesday morning", () => {
    expect(recheckSlots(at("2026-10-07T10:00:00")).map((s) => s.id)).toEqual(["now", "tonight", "tomorrow", "friday"]);
  });
  it("hides 'Tonight' after 7 pm", () => {
    expect(recheckSlots(at("2026-10-07T19:30:00")).map((s) => s.id)).toEqual(["now", "tomorrow", "friday"]);
  });
  it("switches Friday to Monday from Thursday on", () => {
    for (const d of ["2026-10-08T10:00:00", "2026-10-09T10:00:00", "2026-10-10T10:00:00"]) {
      expect(recheckSlots(at(d)).map((s) => s.id)).toContain("monday");
    }
    expect(recheckSlots(at("2026-10-11T10:00:00")).map((s) => s.id)).toContain("friday"); // Sunday
  });
  it("the Monday slot really is a Monday at 9 am", () => {
    const m = recheckSlots(at("2026-10-09T10:00:00")).find((s) => s.id === "monday")!;
    const d = new Date(m.at);
    expect([d.getDay(), d.getHours()]).toEqual([1, 9]);
  });
  it("describes a slot in words", () => {
    const now = at("2026-10-07T10:00:00");
    const s = recheckSlots(now);
    expect(describeSlot(s[1], now)).toBe("tonight at 8:00 pm");
    expect(describeSlot(s[2], now)).toBe("tomorrow at 9:00 am");
    expect(describeSlot(s[3], now)).toBe("Friday at 9:00 am");
  });
});

describe("ics", () => {
  it("makes a valid one-event file", () => {
    const ics = icsFor({ title: "Check-in, Week 7", description: "a;b", start: T0, minutes: 5, uid: "x" });
    expect(ics).toContain("BEGIN:VCALENDAR");
    expect(ics).toContain("SUMMARY:Check-in\\, Week 7");
    expect(ics).toMatch(/DTEND:\d{8}T\d{6}Z/);
    expect(ics.endsWith("\r\n")).toBe(true);
  });
});
