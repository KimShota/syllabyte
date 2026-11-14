import { describe, expect, it } from "vitest";
import { openDb } from "../src/db";
import { makeServer } from "./helpers";

interface Sitting {
  current: { item: { id: string; correct_index: number } } | null;
}
type Rpc = <T = unknown>(method: string, ...args: unknown[]) => Promise<T>;

/** Answer every question of a sitting right, then finish it. */
async function finishBaseline(rpc: Rpc) {
  for (let guard = 0; guard < 200; guard++) {
    const v = await rpc<Sitting>("getSitting", "week0");
    if (!v.current) break;
    await rpc("answerSitting", "week0", v.current.item.id, v.current.item.correct_index, 1500);
  }
  await rpc("finishSitting", "week0");
}

describe("the shared Api over HTTP", () => {
  it("answers getMe with the student's participant code, a fresh state at first", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const me = await ann.rpc<{ participant_code: string; onboarding_done: boolean; consent: string | null }>("getMe");
    expect(me.participant_code).toMatch(/^S-/);
    expect(me.onboarding_done).toBe(false);
    expect(me.consent).toBeNull();
  });

  it("only lets students call the contract's methods", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    for (const m of ["exportStudyCsv", "constructor", "__proto__", "toString", "nope"]) {
      await expect(ann.rpc(m)).rejects.toThrow(/unknown method/);
    }
  });

  it("returns the rules' errors as 400s with their message", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    await expect(ann.rpc("getSitting", "not-a-sitting")).rejects.toThrow();
    const bad = await ann.post("/api/rpc/getMe", { args: "x" });
    expect(bad.status).toBe(400);
  });

  it("saves a student's state, and a restarted server still has it", async () => {
    const dir = (await import("node:fs")).mkdtempSync((await import("node:os")).tmpdir() + "/syllabyte-");
    const path = `${dir}/t.db`;
    const first = makeServer({ db: openDb(path) });
    const ann = await first.signIn("ann@nyu.edu");
    await ann.rpc("postConsent", true);
    await ann.rpc("updateSettings", { captions: false });

    const second = makeServer({ db: openDb(path) });
    const again = await second.signIn("ann@nyu.edu");
    const me = await again.rpc<{ consent: string; settings: { captions: boolean } }>("getMe");
    expect(me.consent).toBe("research");
    expect(me.settings.captions).toBe(false);
  });

  it("runs the whole baseline on the server and publishes the student's levels", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    await ann.rpc("postConsent", true);
    expect((await ann.rpc<{ onboarding_done: boolean }>("getMe")).onboarding_done).toBe(false);
    await finishBaseline(ann.rpc);
    expect((await ann.rpc<{ onboarding_done: boolean }>("getMe")).onboarding_done).toBe(true);
    const levels = await ann.rpc<{ lectures: unknown[] }>("getLevels");
    expect(levels.lectures.length).toBeGreaterThan(0);
  });

  it("keeps two students' states apart, even when their calls arrive together", async () => {
    const s = makeServer();
    const [ann, bob] = await Promise.all([s.signIn("ann@nyu.edu"), s.signIn("bob@nyu.edu")]);
    const calls: Promise<unknown>[] = [];
    for (let i = 0; i < 25; i++) {
      calls.push(ann.rpc("updateSettings", { captions: i % 2 === 0 }));
      calls.push(bob.rpc("updateSettings", { weekly_email: i % 2 === 1 }));
      calls.push(ann.rpc("getMe"), bob.rpc("getMe"));
    }
    await Promise.all(calls);
    await ann.rpc("postConsent", true);
    const [a, b] = await Promise.all([
      ann.rpc<{ consent: string | null; participant_code: string; settings: { captions: boolean; weekly_email: boolean } }>("getMe"),
      bob.rpc<{ consent: string | null; participant_code: string; settings: { captions: boolean; weekly_email: boolean } }>("getMe"),
    ]);
    expect(a.consent).toBe("research");
    expect(b.consent).toBeNull();
    expect(a.participant_code).not.toBe(b.participant_code);
    expect(a.settings.captions).toBe(true); // i = 24, the last write
    expect(a.settings.weekly_email).toBe(true); // never touched: the default
    expect(b.settings.weekly_email).toBe(false); // i = 24 is even
    expect(b.settings.captions).toBe(true); // never touched: the default
  });

  it("starts new students' semester at the configured date", async () => {
    const s = makeServer({ semesterStart: new Date("2026-09-07T12:00:00Z").getTime() });
    const ann = await s.signIn("ann@nyu.edu");
    const me = await ann.rpc<{ week: number }>("getMe");
    expect(me.week).toBeGreaterThan(5);
  });
});

describe("events", () => {
  it("logs the phone's events with the server's condition, week and participant code", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    await ann.rpc("postConsent", true);
    const res = await ann.post("/api/events", {
      events: [
        { verb: "video_play", object: { type: "video", id: "v1" }, screen: "/player/v1" },
        { verb: "video_pause", object: { type: "video", id: "v1" }, result: { t: 12 }, screen: "/player/v1" },
        { nonsense: true },
      ],
    });
    expect(await res.json()).toEqual({ accepted: 2 });
    const data = await ann.rpc<{ events: { verb: string; context: { screen: string; participant_code: string; device: string } }[] }>("exportMyData");
    const play = data.events.find((e) => e.verb === "video_play")!;
    expect(play.context.screen).toBe("/player/v1");
    expect(play.context.participant_code).toMatch(/^S-/);
    expect(play.context.device).toBe("mobile");
  });

  it("refuses a huge batch", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const events = Array.from({ length: 201 }, () => ({ verb: "video_play", object: { type: "video" } }));
    expect((await ann.post("/api/events", { events })).status).toBe(400);
  });
});

describe("the researcher export", () => {
  it("is for researchers only", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    expect((await ann.get("/api/research/study.csv")).status).toBe(403);
  });

  it("covers every consenting participant by code, never by email", async () => {
    const s = makeServer();
    const [ann, bob, dee, res] = await Promise.all([
      s.signIn("ann@nyu.edu"),
      s.signIn("bob@nyu.edu"),
      s.signIn("dee@nyu.edu"),
      s.signIn("researcher@nyu.edu", "researcher"),
    ]);
    for (const p of [ann, bob]) {
      await p.rpc("postConsent", true);
      await p.rpc("saveBatteryAnswers", "baseline", { "demo-experience": "never" });
      await p.rpc("submitBattery", "baseline");
    }
    await dee.rpc("postConsent", false);
    const r = await res.get("/api/research/study.csv");
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toContain("text/csv");
    const csv = await r.text();
    const codes = new Set(csv.split("\n").slice(1).filter(Boolean).map((l) => l.split(",")[1]));
    const [pa, pb, pd] = (await Promise.all([ann, bob, dee].map((p) => p.rpc<{ participant_code: string }>("getMe")))).map((m) => m.participant_code);
    expect(codes).toEqual(new Set([pa, pb]));
    expect(codes.has(pd)).toBe(false);
    expect(csv).not.toContain("@");
  });
});

describe("learning sessions over HTTP", () => {
  it("saves quiet playback observations, isolates students and keeps a retried answer once", async () => {
    const { FIX } = await import("@syllabyte/core/fixtures");
    const dir = (await import("node:fs")).mkdtempSync((await import("node:os")).tmpdir() + "/syllabyte-");
    const path = `${dir}/t.db`;
    const first = makeServer({ db: openDb(path) });
    const [ann, bob] = await Promise.all([first.signIn("ann@nyu.edu"), first.signIn("bob@nyu.edu")]);
    const video = FIX.videos[0];
    const item = FIX.items.find((i) => i.id === video.checkpoint.item_id)!;
    const ctx = { sessionId: "learning-ann", courseId: FIX.course.id };
    const snapshot = { sequence: 1, intervals: [[0, 20]], elapsed_s: 20, exposure_s: 20, position_s: 20, duration_s: video.duration_s, source: "video" };
    // a playback save is quiet (no screen refresh), but it must still reach the database
    expect(await ann.rpc("recordLearningPlayback", { ...ctx, playbackId: "playback-1", videoId: video.id, snapshot })).toEqual({ completedNow: false });
    const answer = { attemptId: "attempt-1", learning: ctx, videoId: video.id, choice: (item.correct_index + 1) % item.options.length, confidence: "certain", hintUsed: false, latencyMs: 800 };
    const a = await ann.rpc<{ responseId: string }>("postCheckpointAnswer", answer);
    const b = await ann.rpc<{ responseId: string }>("postCheckpointAnswer", answer);
    expect(b.responseId).toBe(a.responseId);

    const again = makeServer({ db: openDb(path) });
    const ann2 = await again.signIn("ann@nyu.edu");
    const r = await ann2.rpc<{ videos: { id: string; coverage: number }[]; answers: number }>("getLearningReflection", ctx);
    expect(r.videos.map((v) => v.id)).toEqual([video.id]);
    expect(r.answers).toBe(1);
    // another student naming the same session id sees nothing of it
    const other = await bob.rpc<{ videos: unknown[]; answers: number }>("getLearningReflection", ctx);
    expect(other).toMatchObject({ videos: [], answers: 0 });
  });
});

describe("automatic prompts and reflections over HTTP", () => {
  it("saves a quiet drift prompt and a session's reflection, which waits until it is dismissed", async () => {
    const { FIX } = await import("@syllabyte/core/fixtures");
    const dir = (await import("node:fs")).mkdtempSync((await import("node:os")).tmpdir() + "/syllabyte-");
    const path = `${dir}/t.db`;
    const ann = await makeServer({ db: openDb(path) }).signIn("ann@nyu.edu");
    const ctx = { sessionId: "learning-ann", courseId: FIX.course.id };
    const visit = (i: number, id: string) => ann.rpc("recordLearningPlayback", { ...ctx, playbackId: id, videoId: FIX.videos[i].id,
      snapshot: { sequence: 0, intervals: [], elapsed_s: 0, exposure_s: 0, position_s: 0, duration_s: FIX.videos[i].duration_s, source: "video" } });
    for (const [i, id] of [[1, "p-1"], [2, "p-2"], [3, "p-3"]] as const) await visit(i, id);
    const prompt = await ann.rpc<{ id: string; kind: string }>("evaluateLearningBoundary", ctx, { reason: "next_video", videoId: FIX.videos[0].id });
    expect(prompt.kind).toBe("drift_check");
    await ann.rpc("respondToLearningPrompt", ctx, prompt.id, { answer: "searching", action: "continue" });
    const item = FIX.items.find((i) => i.id === FIX.videos[0].checkpoint.item_id)!;
    await ann.rpc("postCheckpointAnswer", { attemptId: "a-1", learning: ctx, videoId: FIX.videos[0].id, choice: (item.correct_index + 1) % item.options.length, confidence: "certain", hintUsed: false, latencyMs: 700 });
    const summary = await ann.rpc<{ sessionId: string }>("finishLearningSession", ctx, "left");
    expect(summary.sessionId).toBe(ctx.sessionId);

    const again = await makeServer({ db: openDb(path) }).signIn("ann@nyu.edu");
    expect(await again.rpc("getPendingReflection")).toEqual(summary);
    const data = await again.rpc<{ learning_sessions: Record<string, { prompts: { answer: string; action: string }[] }> }>("exportMyData");
    expect(data.learning_sessions[ctx.sessionId].prompts[0]).toMatchObject({ answer: "searching", action: "continue" });
    await again.rpc("dismissReflection", ctx.sessionId);
    expect(await again.rpc("getPendingReflection")).toBeNull();
  });
});
