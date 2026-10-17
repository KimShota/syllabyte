import { describe, expect, it } from "vitest";
import { DEMOGRAPHICS, EFFICACY, INSTRUMENTS, PREFER_NOT, SUS, TLX, TRUST } from "../src/content/instruments";
import {
  batteryInstruments, CSV_COLUMNS, dueModules, moduleEnded, moduleEndTime, newBattery, scoreBattery, scoreInstrument, studyCsv, studyModules,
  visibleItems,
} from "../src/logic/instruments";
import type { BatteryRecord, Course } from "../src/types";
import { DAY } from "../src/util";
import { course } from "./kuHelpers";

const withLectures = (n: number, modules: Course["config"]["study_modules"] = null): Course => ({
  ...course,
  config: { ...course.config, study_modules: modules },
  lectures: Array.from({ length: n }, (_, i) => ({ n: i + 1, title: `L${i + 1}`, week: i + 1, slide_start: 1, slide_end: 2 })),
});
const fill = (ids: string[], v: number): BatteryRecord["answers"] => Object.fromEntries(ids.map((id) => [id, v]));
const ids = (i: { items: { id: string }[] }) => i.items.map((x) => x.id);

describe("the instruments (plan I3-I7)", () => {
  it("have the planned number of items", () => {
    expect(TLX.items).toHaveLength(6);
    expect(SUS.items).toHaveLength(10);
    expect(EFFICACY.items).toHaveLength(12);
    expect(TRUST.items).toHaveLength(16);
    expect(DEMOGRAPHICS.items.filter((i) => !i.showIf)).toHaveLength(8);
  });

  it("use unique item ids across every instrument", () => {
    const all = Object.values(INSTRUMENTS).flatMap(ids);
    expect(new Set(all).size).toBe(all.length);
  });

  it("ask trust of Condition A only, and everything else of both", () => {
    expect(TRUST.conditions).toEqual(["A"]);
    for (const i of [DEMOGRAPHICS, TLX, SUS, EFFICACY]) expect(i.conditions).toEqual(["A", "B"]);
  });

  it("reverse exactly Jian et al.'s five distrust items", () => {
    expect(TRUST.items.filter((i) => i.reverse).map((i) => i.id)).toEqual(["trust_1", "trust_2", "trust_3", "trust_4", "trust_5"]);
    expect(TRUST.items[0].text).toBe("SyllaByte is deceptive.");
    expect(TRUST.items[11].text).toBe("I am familiar with SyllaByte.");
  });

  it("rate TLX 0-100 in steps of 5 with NASA's anchors, performance running Perfect to Failure", () => {
    for (const it of TLX.items) expect(it.response).toMatchObject({ kind: "scale", min: 0, max: 100, step: 5 });
    expect(TLX.items.find((i) => i.id === "tlx_performance")!.response).toMatchObject({ anchors: ["Perfect", "Failure"] });
  });

  it("offer “Prefer not to say” on every demographic choice", () => {
    for (const it of DEMOGRAPHICS.items) if (it.response.kind === "choice") expect(it.response.options).toContainEqual(PREFER_NOT);
  });

  it("say “app” in the SUS and drop ReelEd's comparisons to lectures from the efficacy items", () => {
    for (const it of SUS.items) expect(it.text).not.toMatch(/system/);
    for (const it of EFFICACY.items) expect(it.text).not.toMatch(/lecture|traditional/i);
  });
});

describe("modules (plan I2)", () => {
  it("default to the lectures split in two, the first half rounded up", () => {
    expect(studyModules(withLectures(3)).map((m) => m.lectures)).toEqual([[1, 2], [3]]);
    expect(studyModules(withLectures(4)).map((m) => m.lectures)).toEqual([[1, 2], [3, 4]]);
    expect(studyModules(withLectures(1)).map((m) => m.lectures)).toEqual([[1]]);
  });

  it("use the configured modules when there are any", () => {
    const configured = [{ id: "module-1", title: "Part A", lectures: [1] }, { id: "module-2", title: "Part B", lectures: [2, 3, 4] }];
    expect(studyModules(withLectures(4, configured))).toEqual(configured);
  });

  it("end once the schedule has moved past their last lecture's week", () => {
    const c = withLectures(4);
    const [m1] = studyModules(c); // lectures 1-2, weeks 1-2
    expect(moduleEnded(c, m1, 2, null)).toBe(false);
    expect(moduleEnded(c, m1, 3, null)).toBe(true);
    expect(dueModules(c, 3, null).map((m) => m.id)).toEqual(["module-1"]);
    expect(dueModules(c, 5, null).map((m) => m.id)).toEqual(["module-1", "module-2"]);
  });

  it("can be ended sooner by the demo's upcoming-lecture override, and the weeks still end them", () => {
    const c = withLectures(4);
    const [m1] = studyModules(c);
    expect(moduleEnded(c, m1, 1, 3)).toBe(true);
    expect(moduleEnded(c, m1, 1, 2)).toBe(false);
    expect(moduleEnded(c, m1, 3, 2)).toBe(true);
  });

  it("date a module's end to the start of the week after its last lecture, or now if the demo ended it sooner", () => {
    const c = withLectures(4);
    const [m1] = studyModules(c); // last lecture in week 2
    expect(moduleEndTime(c, m1, 0, 30 * DAY)).toBe(14 * DAY);
    expect(moduleEndTime(c, m1, 0, 3 * DAY)).toBe(3 * DAY);
  });
});

describe("batteries", () => {
  it("ask the module battery's four scales of Condition A and three of Condition B", () => {
    expect(batteryInstruments("module-1", "A").map((i) => i.id)).toEqual(["tlx", "efficacy", "sus", "trust"]);
    expect(batteryInstruments("module-2", "B").map((i) => i.id)).toEqual(["tlx", "efficacy", "sus"]);
    expect(batteryInstruments("baseline", "B").map((i) => i.id)).toEqual(["demographics"]);
  });

  it("show the gender self-description only when it is chosen", () => {
    expect(visibleItems(DEMOGRAPHICS, {}).map((i) => i.id)).not.toContain("gender_text");
    expect(visibleItems(DEMOGRAPHICS, { gender: "prefer_to_self_describe" }).map((i) => i.id)).toContain("gender_text");
  });
});

describe("scoring (plan I10)", () => {
  it("scores the SUS by Brooke's formula", () => {
    const sus = (odd: number, even: number) =>
      scoreInstrument(SUS, Object.fromEntries(SUS.items.map((it, i) => [it.id, i % 2 === 0 ? odd : even])))[0].score;
    expect(sus(5, 1)).toBe(100);
    expect(sus(1, 5)).toBe(0);
    expect(sus(3, 3)).toBe(50);
    expect(sus(4, 2)).toBe(75);
  });

  it("scores Raw TLX as the unweighted mean", () => {
    const answers = { tlx_mental: 70, tlx_physical: 5, tlx_temporal: 40, tlx_performance: 25, tlx_effort: 60, tlx_frustration: 30 };
    expect(scoreInstrument(TLX, answers)[0]).toMatchObject({ id: "tlx_raw", complete: true, score: 38.33 });
  });

  it("scores Jian's 12 with the distrust items reversed, and the 4 study items separately", () => {
    const [jian, study] = scoreInstrument(TRUST, fill(ids(TRUST), 7));
    expect(jian).toMatchObject({ id: "trust_jian", total: 12, score: 4.5 }); // (5 x 1 + 7 x 7) / 12
    expect(study).toMatchObject({ id: "trust_study", total: 4, score: 7 });
  });

  it("gives no score to a scale with a skipped or missing item, but keeps the count", () => {
    const answers = { ...fill(ids(EFFICACY), 5), eff_4: null };
    expect(scoreInstrument(EFFICACY, answers)[0]).toMatchObject({ complete: false, answered: 11, total: 12, score: null });
    const missing = fill(ids(EFFICACY).slice(0, 11), 5);
    expect(scoreInstrument(EFFICACY, missing)[0]).toMatchObject({ complete: false, score: null });
  });

  it("scores a skipped trust study item without touching Jian's score", () => {
    const [jian, study] = scoreInstrument(TRUST, { ...fill(ids(TRUST), 4), trust_16: null });
    expect(jian.complete).toBe(true);
    expect(study).toMatchObject({ complete: false, score: null });
  });

  it("scores a battery for the participant's condition", () => {
    const rec = { ...newBattery("module-1", "v", 0), answers: fill([...ids(TLX), ...ids(SUS), ...ids(EFFICACY), ...ids(TRUST)], 3) };
    expect(scoreBattery(rec, "A").map((s) => s.id)).toEqual(["tlx_raw", "efficacy", "sus", "trust_jian", "trust_study"]);
    expect(scoreBattery(rec, "B").map((s) => s.id)).toEqual(["tlx_raw", "efficacy", "sus"]);
  });
});

describe("the researcher export (plan I12)", () => {
  const parse = (csv: string) => csv.trim().split("\n").map((l) => l.split(","));

  it("has one row per item asked and one per score, with the timings", () => {
    const rec: BatteryRecord = {
      ...newBattery("module-1", "v1", 0), started_at: DAY, submitted_at: 2 * DAY,
      answers: { ...fill(ids(TLX), 50), ...fill(ids(EFFICACY), 6), ...fill(ids(SUS), 3), tlx_effort: null },
    };
    const rows = parse(studyCsv([{ participant_code: "P07", condition: "B", study: { "module-1": rec } }]));
    expect(rows[0]).toEqual([...CSV_COLUMNS]);
    const items = rows.filter((r) => r[0] === "item");
    expect(items).toHaveLength(6 + 12 + 10);
    const effort = items.find((r) => r[6] === "tlx_effort")!;
    expect(effort.slice(7, 9)).toEqual(["", "true"]);
    const scores = rows.filter((r) => r[0] === "score");
    expect(scores.map((r) => [r[6], r[7], r[9]])).toEqual([["tlx_raw", "", "false"], ["efficacy", "6", "true"], ["sus", "50", "true"]]);
    expect(rows[1].slice(1, 5)).toEqual(["P07", "B", "module-1", "v1"]);
    expect(rows[1][13]).toBe("2");
  });

  it("leaves out items never reached in an unsubmitted battery, but counts them as skipped once submitted", () => {
    const open: BatteryRecord = { ...newBattery("module-1", "v", 0), answers: { tlx_mental: 10 } };
    const itemRows = (r: BatteryRecord) => parse(studyCsv([{ participant_code: "P", condition: "A", study: { m: r } }])).filter((x) => x[0] === "item");
    expect(itemRows(open)).toHaveLength(1);
    expect(itemRows({ ...open, submitted_at: 1 })).toHaveLength(6 + 12 + 10 + 16);
  });

  it("quotes free text that contains commas or quotes", () => {
    const rec: BatteryRecord = { ...newBattery("baseline", "v", 0), answers: { major: 'Econ, "maybe" CS' } };
    expect(studyCsv([{ participant_code: "P", condition: "A", study: { baseline: rec } }])).toContain('"Econ, ""maybe"" CS"');
  });
});
