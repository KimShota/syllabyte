import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

// The study questionnaires through the real mock API (plan/study-instruments-plan.md). Needs the local fixtures.
const haveFixtures = existsSync(resolve(__dirname, "../fixtures/bank.json"));

describe.skipIf(!haveFixtures)("study questionnaires through the mock API", () => {
  let api: typeof import("../src/api/client").api;
  let store: typeof import("../src/store");
  let demo: typeof import("../src/api/demo");
  let DAY: number;

  beforeEach(async () => {
    api = (await import("../src/api/client")).api;
    store = await import("../src/store");
    demo = await import("../src/api/demo");
    DAY = (await import("../src/util")).DAY;
    store.resetState();
    store.mutate((s) => {
      s.condition = "A";
    });
  });

  const tasks = async () => (await api.getStudyTasks()).map((t) => t.battery_id);
  /** The dev course has lectures in weeks 1-3: module 1 (lectures 1-2) ends at the start of week 3. */
  const toWeek3 = () => {
    demo.simulateNextWeek();
    demo.simulateNextWeek();
  };

  it("asks nothing of someone who declined, or before consent", async () => {
    expect(await tasks()).toEqual([]);
    await api.postConsent(false);
    toWeek3();
    expect(await tasks()).toEqual([]);
    await expect(api.getBattery("baseline")).rejects.toThrow(/research participants/);
  });

  it("opens the baseline at consent and each module's battery once the schedule passes its last lecture", async () => {
    await api.postConsent(true);
    expect(await tasks()).toEqual(["baseline"]);
    demo.simulateNextWeek();
    expect(await tasks()).toEqual(["baseline"]);
    demo.simulateNextWeek();
    expect(await tasks()).toEqual(["baseline", "module-1"]);
    const start = store.getState().semester_start;
    expect(store.getState().study["module-1"].opened_at).toBe(start + 14 * DAY);
  });

  it("keeps the researcher's condition through consent, and only asks Condition A about trust", async () => {
    store.mutate((s) => {
      s.condition = "B";
    });
    await api.postConsent(true);
    expect(store.getState().condition).toBe("B");
    toWeek3();
    expect((await api.getBattery("module-1")).instruments.map((i) => i.id)).toEqual(["tlx", "efficacy", "sus"]);
    demo.setCondition("A");
    expect((await api.getBattery("module-1")).instruments.map((i) => i.id)).toEqual(["tlx", "efficacy", "sus", "trust"]);
  });

  it("saves answers as they come, then records every unanswered item as skipped on submit", async () => {
    await api.postConsent(true);
    await api.saveBatteryAnswers("baseline", { year: "2nd_year", age: "prefer_not", major: null });
    let b = await api.getBattery("baseline");
    expect(b.answers).toEqual({ year: "2nd_year", age: "prefer_not", major: null });
    expect(store.getState().study.baseline.started_at).not.toBeNull();
    await api.submitBattery("baseline");
    b = await api.getBattery("baseline");
    expect(b.submitted).toBe(true);
    expect(b.answers.gender).toBeNull();
    expect("gender_text" in b.answers).toBe(false); // never shown: self-description not chosen
    expect(await tasks()).toEqual([]);
    const submitted = store.getState().events.find((e) => e.verb === "study_submitted");
    expect(submitted?.result).toMatchObject({ asked: 8, skipped: 6 });
  });

  it("hides a battery put off with “Not now” until the app is opened again, and keeps it reachable meanwhile", async () => {
    await api.postConsent(true);
    await api.snoozeBattery("baseline");
    expect(await tasks()).toEqual([]);
    // the profile still opens it
    expect((await api.getBattery("baseline")).submitted).toBe(false);
    store.startVisit("a-new-visit");
    expect(store.getState().visit).toEqual({ id: "a-new-visit", handled: 0 });
    expect(await tasks()).toEqual(["baseline"]);
  });

  it("estimates the time from the items this participant is asked", async () => {
    await api.postConsent(true);
    toWeek3();
    const a = (await api.getStudyTasks()).find((t) => t.battery_id === "module-1")!;
    demo.setCondition("B");
    const b = (await api.getStudyTasks()).find((t) => t.battery_id === "module-1")!;
    expect(a.minutes).toBeGreaterThan(b.minutes); // 44 items vs 28
    expect(a.title).toBe("Module 1 questionnaire");
  });

  it("deletes questionnaire answers when a participant withdraws and asks for deletion, and only then", async () => {
    await api.postConsent(true);
    await api.saveBatteryAnswers("baseline", { year: "1st_year" });
    await api.withdrawFromResearch(false);
    expect(store.getState().study.baseline.answers).toEqual({ year: "1st_year" });
    expect(await tasks()).toEqual([]);
    await api.withdrawFromResearch(true);
    expect(store.getState().study).toEqual({});
  });

  it("exports the participant's answers as the researcher CSV, and includes them in “Download my data”", async () => {
    demo.setParticipantCode("P42");
    await api.postConsent(true);
    await api.saveBatteryAnswers("baseline", { year: "3rd_year" });
    await api.submitBattery("baseline");
    const csv = await api.exportStudyCsv();
    expect(csv.split("\n")[1]).toMatch(/^item,P42,A,baseline,/);
    expect((await api.exportMyData()).study).toHaveProperty("baseline");
  });

  it("keeps the researcher's condition through Reset demo", async () => {
    demo.setCondition("B");
    demo.resetDemo();
    expect(store.getState().condition).toBe("B");
  });
});
