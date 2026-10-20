import { describe, expect, it } from "vitest";
import { DAY } from "@syllabyte/core/util";
import { advanceClock, getClock } from "../src/clock";
import { openDb } from "../src/db";
import { makeServer } from "./helpers";

type Me = { now: number; participant_code: string };
type Task = { battery_id: string };

async function setup() {
  const s = makeServer();
  const [ann, bob, res] = await Promise.all([s.signIn("ann@nyu.edu"), s.signIn("bob@nyu.edu"), s.signIn("researcher@nyu.edu", "researcher")]);
  // saved state exists for both, so the clock is tested on returning students (a first visit takes a different path)
  await Promise.all([ann, bob].map((p) => p.rpc("postConsent", true)));
  const code = async (p: typeof ann) => (await p.rpc<Me>("getMe")).participant_code;
  return { s, ann, bob, res, annCode: await code(ann), bobCode: await code(bob) };
}

describe("the facilitator's study clock", () => {
  it("is for researchers only", async () => {
    const { ann, annCode } = await setup();
    expect((await ann.post("/api/research/clock", { participant_code: annCode, days: 7 })).status).toBe(403);
  });

  it("moves one student's clock forward and keeps it there across requests and a restart", async () => {
    const { s, ann, res, annCode } = await setup();
    const before = (await ann.rpc<Me>("getMe")).now;
    const r = await res.post("/api/research/clock", { participant_code: annCode, days: 7 });
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ participant_code: annCode, offset_days: 7 });

    const after = (await ann.rpc<Me>("getMe")).now;
    expect(after - before).toBeGreaterThan(7 * DAY - 60_000);
    expect(after - before).toBeLessThan(7 * DAY + 60_000);

    // a second move adds to the first
    await res.post("/api/research/clock", { participant_code: annCode, days: 7 });
    expect((await ann.rpc<Me>("getMe")).now - before).toBeGreaterThan(14 * DAY - 60_000);

    // a new server on the same database (a restart) and a fresh sign-in still see it
    expect(getClock(s.db, annCode)?.offset_days).toBe(14);
    const again = await makeServer({ db: s.db }).signIn("ann@nyu.edu");
    expect((await again.rpc<Me>("getMe")).now - before).toBeGreaterThan(14 * DAY - 60_000);
  });

  it("applies to a student who has signed in but not yet saved anything", async () => {
    const s = makeServer();
    const [cat, res] = await Promise.all([s.signIn("cat@nyu.edu"), s.signIn("researcher@nyu.edu", "researcher")]);
    const { participant_code } = (await (await cat.get("/api/session")).json()) as { participant_code: string };
    const t0 = Date.now();
    await res.post("/api/research/clock", { participant_code, days: 10 });
    expect((await cat.rpc<Me>("getMe")).now - t0).toBeGreaterThan(10 * DAY - 60_000);
  });

  it("leaves other students on real time", async () => {
    const { bob, res, annCode } = await setup();
    const before = (await bob.rpc<Me>("getMe")).now;
    await res.post("/api/research/clock", { participant_code: annCode, days: 30 });
    expect((await bob.rpc<Me>("getMe")).now - before).toBeLessThan(60_000);
  });

  it("will not go back, and rejects unknown codes and missing input", async () => {
    const { res, annCode } = await setup();
    expect((await res.post("/api/research/clock", { participant_code: annCode, days: -1 })).status).toBe(400);
    expect((await res.post("/api/research/clock", { participant_code: annCode, days: 9999 })).status).toBe(400);
    expect((await res.post("/api/research/clock", { participant_code: "S-NOONE", days: 1 })).status).toBe(404);
    expect((await res.post("/api/research/clock", { days: 1 })).status).toBe(400);
  });

  it("reads the clock with no action, and resets it", async () => {
    const { res, annCode } = await setup();
    await res.post("/api/research/clock", { participant_code: annCode, days: 3 });
    expect(await (await res.post("/api/research/clock", { participant_code: annCode })).json()).toEqual({ participant_code: annCode, offset_days: 3 });
    expect(await (await res.post("/api/research/clock", { participant_code: annCode, reset: true })).json()).toEqual({ participant_code: annCode, offset_days: 0 });
  });

  it("makes module 1's questionnaire due when asked to jump to the end of module 1", async () => {
    const { ann, res, annCode } = await setup();
    const before = (await ann.rpc<Task[]>("getStudyTasks")).map((t) => t.battery_id);
    expect(before).toEqual(["baseline"]);

    const r = await res.post("/api/research/clock", { participant_code: annCode, module: 1 });
    expect(r.status).toBe(200);
    const after = (await ann.rpc<Task[]>("getStudyTasks")).map((t) => t.battery_id);
    expect(after.length).toBeGreaterThan(1);
    expect(after).toContain("baseline");

    // asking again does not move it further
    const again = (await (await res.post("/api/research/clock", { participant_code: annCode, module: 1 })).json()) as { offset_days: number };
    expect(again.offset_days).toBe(((await r.json()) as { offset_days: number }).offset_days);
  });

  it("refuses a module jump for someone who has not opened the app yet", async () => {
    const db = openDb(":memory:");
    db.prepare("INSERT INTO users (id, email, participant_code, created_at) VALUES ('u1', 'x@nyu.edu', 'S-XXXXX', 0)").run();
    expect(() => advanceClock(db, "S-XXXXX", -5)).toThrow();
    const { advanceToModuleEnd } = await import("../src/clock");
    expect(() => advanceToModuleEnd(db, "S-XXXXX", 1)).toThrow(/not opened/);
  });
});
