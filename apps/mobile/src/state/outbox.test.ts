import { describe, expect, it } from "vitest";
import { createOutbox, OUTBOX_MAX, type OutboxDeps } from "./outbox";

class Offline extends Error {}
class Refused extends Error {}

/** An outbox over fake storage and a fake server; `online` and the timers are under the test's control. */
function harness(saved: string | null = null) {
  const store = { raw: saved };
  const sent: { method: string; args: unknown[] }[] = [];
  const timers: (() => void)[] = [];
  const state = { online: true, signedIn: true, refuse: new Set<string>() };
  let n = 0;
  const deps: OutboxDeps = {
    load: async () => store.raw,
    save: async (raw) => {
      store.raw = raw;
    },
    call: async (method, args) => {
      if (!state.online) throw new Offline();
      if (state.refuse.has(method)) throw new Refused();
      sent.push({ method, args });
      return { ok: method };
    },
    retryable: (e) => e instanceof Offline,
    canSend: () => state.signedIn,
    later: (fn) => {
      timers.push(fn);
      return () => timers.splice(timers.indexOf(fn), 1);
    },
    now: () => 1000,
    newId: () => `e-${++n}`,
  };
  const runTimers = async (box: ReturnType<typeof createOutbox>) => {
    for (const fn of timers.splice(0)) fn();
    await box.flush();
  };
  return { box: createOutbox(deps), store, sent, state, timers, runTimers };
}

describe("learning outbox", () => {
  it("sends straight through when online and returns the answer", async () => {
    const h = harness();
    expect(await h.box.send("respondToLearningPrompt", ["ctx", "p-1", { action: "pause" }])).toEqual({ ok: "respondToLearningPrompt" });
    expect(h.box.size()).toBe(0);
  });

  it("keeps a write that could not get through, in storage, and sends it when the network is back", async () => {
    const h = harness();
    h.state.online = false;
    expect(await h.box.send("respondToLearningPrompt", ["ctx", "p-1", { answer: "drifted" }])).toBeUndefined();
    expect(h.box.size()).toBe(1);
    expect(JSON.parse(h.store.raw!)).toHaveLength(1);
    expect(h.timers).toHaveLength(1); // a retry is scheduled
    h.state.online = true;
    await h.runTimers(h.box);
    expect(h.sent.map((s) => s.method)).toEqual(["respondToLearningPrompt"]);
    expect(h.box.size()).toBe(0);
    expect(JSON.parse(h.store.raw!)).toEqual([]);
  });

  it("keeps the order: a write made while others wait joins the end of the line", async () => {
    const h = harness();
    h.state.online = false;
    await h.box.send("respondToLearningPrompt", ["a"]);
    h.state.online = true;
    await h.box.send("finishLearningSession", ["b"]);
    await h.box.flush();
    expect(h.sent.map((s) => s.args[0])).toEqual(["a", "b"]);
  });

  it("drops a write the server refuses instead of retrying it forever, and carries on with the rest", async () => {
    const h = harness();
    h.state.online = false;
    await h.box.send("dismissReflection", ["gone"]);
    await h.box.send("finishLearningSession", ["s-1"]);
    h.state.online = true;
    h.state.refuse.add("dismissReflection");
    await h.box.flush();
    expect(h.sent.map((s) => s.method)).toEqual(["finishLearningSession"]);
    expect(h.box.size()).toBe(0);
  });

  it("survives the app closing: a new outbox picks up what the old one stored", async () => {
    const first = harness();
    first.state.online = false;
    await first.box.send("recordLearningAway", [{ id: "away-1" }]);
    const second = harness(first.store.raw);
    await second.box.flush();
    expect(second.sent).toEqual([{ method: "recordLearningAway", args: [{ id: "away-1" }] }]);
  });

  it("waits while signed out, and sign-out clears what the account left", async () => {
    const h = harness();
    h.state.signedIn = false;
    await h.box.send("respondToLearningPrompt", ["x"]);
    await h.box.flush();
    expect(h.sent).toEqual([]);
    await h.box.clear();
    expect(h.box.size()).toBe(0);
    expect(JSON.parse(h.store.raw!)).toEqual([]);
  });

  it("keeps at most OUTBOX_MAX writes, dropping the oldest and counting them", async () => {
    const h = harness();
    h.state.online = false;
    for (let i = 0; i < OUTBOX_MAX + 3; i++) await h.box.send("recordLearningAway", [i]);
    expect(h.box.size()).toBe(OUTBOX_MAX);
    expect(h.box.dropped()).toBe(3);
    h.state.online = true;
    await h.box.flush();
    expect(h.sent[0].args[0]).toBe(3);
  });

  it("an unreadable stored queue starts empty", async () => {
    const h = harness("{not json");
    await h.box.flush();
    expect(h.box.size()).toBe(0);
  });
});
