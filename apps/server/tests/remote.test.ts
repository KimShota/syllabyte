import { describe, expect, it, vi } from "vitest";
import { ApiError, createBackend, createEventQueue } from "@syllabyte/core/api/remote";
import type { ClientEvent } from "@syllabyte/core/events";
import { work } from "./fakeWorker";
import { makeServer } from "./helpers";

/** The phone's backend client wired straight to the server app, no network. */
function phone(s: ReturnType<typeof makeServer>) {
  const log = { changed: 0, unauthorized: 0, connection: [] as boolean[] };
  let token: string | null = null;
  const fetchApp = ((url: string, init?: RequestInit) => s.app.request(new URL(url).pathname, init)) as typeof fetch;
  const backend = createBackend({
    base: "http://server",
    token: () => token,
    visit: () => "launch-1",
    onUnauthorized: () => {
      log.unauthorized += 1;
      token = null;
    },
    onChanged: () => {
      log.changed += 1;
    },
    onConnection: (ok) => log.connection.push(ok),
    fetch: fetchApp,
  });
  return {
    backend,
    log,
    setToken: (t: string | null) => (token = t),
    /** sign in the way the app does: ask for a code, read the email, verify */
    async signIn(email: string) {
      s.auth.addToAllowlist(email, "student");
      await backend.requestCode(email);
      const code = /code is (\S+?)\./.exec(s.mailer.sent.findLast((m) => m.to === email)!.text)![1];
      const res = await backend.verifyCode(email, code);
      token = res.token;
      return res;
    },
  };
}

describe("the phone's backend client", () => {
  it("signs in with an emailed code and then calls the Api like the mock", async () => {
    const s = makeServer();
    const p = phone(s);
    const res = await p.signIn("ann@nyu.edu");
    expect(res.participant_code).toMatch(/^S-/);
    const me = await p.backend.api.getMe();
    expect(me.participant_code).toBe(res.participant_code);
    expect(me.consent).toBeNull();
  });

  it("tells the screens to refetch after a write, not after a read", async () => {
    const s = makeServer();
    const p = phone(s);
    await p.signIn("ann@nyu.edu");
    await p.backend.api.getMe();
    await p.backend.api.getPlaylist().catch(() => undefined);
    expect(p.log.changed).toBe(0);
    await p.backend.api.postConsent(true);
    expect(p.log.changed).toBe(1);
    expect((await p.backend.api.getMe()).consent).toBe("research");
  });

  it("rejects a wrong code with a 401 ApiError", async () => {
    const s = makeServer();
    const p = phone(s);
    s.auth.addToAllowlist("ann@nyu.edu", "student");
    await p.backend.requestCode("ann@nyu.edu");
    await expect(p.backend.verifyCode("ann@nyu.edu", "ZZZZZZ")).rejects.toMatchObject({ status: 401 });
  });

  it("does not call the server without a session", async () => {
    const s = makeServer();
    const p = phone(s);
    await expect(p.backend.api.getMe()).rejects.toMatchObject({ status: 401 });
    expect(p.log.connection).toEqual([]);
  });

  it("signs the student out when the server turns the session down", async () => {
    const s = makeServer();
    const p = phone(s);
    p.setToken("a-token-the-server-never-issued");
    await expect(p.backend.api.getMe()).rejects.toBeInstanceOf(ApiError);
    expect(p.log.unauthorized).toBe(1);
  });

  it("passes the rules' error messages through", async () => {
    const s = makeServer();
    const p = phone(s);
    await p.signIn("ann@nyu.edu");
    await expect(p.backend.api.getSitting("not-a-sitting")).rejects.toMatchObject({ status: 400 });
  });

  it("reports an unreachable server instead of throwing something obscure", async () => {
    const log: boolean[] = [];
    const backend = createBackend({
      base: "http://nowhere",
      token: () => "t",
      visit: () => "v",
      onUnauthorized: () => {},
      onChanged: () => {},
      onConnection: (ok) => log.push(ok),
      fetch: (() => Promise.reject(new TypeError("Network request failed"))) as typeof fetch,
    });
    await expect(backend.api.getMe()).rejects.toMatchObject({ status: 0, message: "Can't reach the server" });
    expect(log).toEqual([false]);
  });

  it("is not mistaken for a promise when awaited", async () => {
    const s = makeServer();
    const p = phone(s);
    expect(await Promise.resolve(p.backend.api)).toBe(p.backend.api);
  });

  it("sends events that the server logs with its own context", async () => {
    const s = makeServer();
    const p = phone(s);
    await p.signIn("ann@nyu.edu");
    await p.backend.api.postConsent(true);
    await p.backend.sendEvents([{ verb: "video_play", object: { type: "video", id: "v" }, screen: "/player/v", device: "mobile", orientation: "portrait" }]);
    const data = (await p.backend.api.exportMyData()) as { events: { verb: string }[] };
    expect(data.events.map((e) => e.verb)).toContain("video_play");
  });

  it("logs out", async () => {
    const s = makeServer();
    const p = phone(s);
    const { token } = await p.signIn("ann@nyu.edu");
    await p.backend.logout();
    p.setToken(token);
    await expect(p.backend.session()).rejects.toMatchObject({ status: 401 });
  });
});

const ev = (n: number): ClientEvent => ({ verb: "video_play", object: { type: "video", id: String(n) }, screen: "/", device: "mobile", orientation: "portrait" });

describe("the event queue", () => {
  it("sends a batch once enough are waiting", async () => {
    const send = vi.fn(async (_batch: ClientEvent[]) => {});
    const q = createEventQueue(send, { max: 3, delayMs: 10_000 });
    q.push(ev(1));
    q.push(ev(2));
    expect(send).not.toHaveBeenCalled();
    q.push(ev(3));
    await q.flush();
    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][0]).toHaveLength(3);
  });

  it("sends what is waiting after the delay", async () => {
    vi.useFakeTimers();
    const send = vi.fn(async () => {});
    const q = createEventQueue(send, { delayMs: 4000 });
    q.push(ev(1));
    await vi.advanceTimersByTimeAsync(4001);
    expect(send).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("keeps a failed batch and sends it with the next one", async () => {
    let fail = true;
    const sent: ClientEvent[][] = [];
    const q = createEventQueue(
      async (batch) => {
        if (fail) throw new Error("offline");
        sent.push(batch);
      },
      { delayMs: 10_000 },
    );
    q.push(ev(1));
    await q.flush();
    expect(q.size()).toBe(1);
    fail = false;
    q.push(ev(2));
    await q.flush();
    expect(sent.flat().map((e) => e.object.id)).toEqual(["1", "2"]);
    expect(q.size()).toBe(0);
  });

  it("drops the oldest beyond its cap, and forgets everything on clear", async () => {
    const q = createEventQueue(async () => { throw new Error("offline"); }, { max: 1000, keep: 3, delayMs: 10_000 });
    for (let i = 1; i <= 5; i++) {
      q.push(ev(i));
      await q.flush();
    }
    expect(q.size()).toBe(3);
    q.clear();
    expect(q.size()).toBe(0);
  });
});

describe("the phone's course calls", () => {
  const file = (name: string, text: string) => ({ name, uri: `file:///${name}`, file: new Blob([text]) });

  it("adds a course from the syllabus, uploads slides and places them", async () => {
    const s = makeServer();
    const p = phone(s);
    await p.signIn("ann@nyu.edu");
    expect(await p.backend.courses.mine()).toEqual({ status: "none" });

    await p.backend.courses.create(file("syllabus.pdf", "Syllabus of CS-UH 2219E"));
    expect(await p.backend.courses.mine()).toEqual({ status: "reading" });
    await work(s);
    const mine = await p.backend.courses.mine();
    if (mine.status !== "ready") throw new Error("no course");
    expect(mine.course.lectures).toEqual([]);

    const changedBefore = p.log.changed;
    const added = await p.backend.courses.addSlides(mine.course.id, [file("lecture1.pdf", "Potential outcomes intro\nmore")]);
    expect(added.map((u) => u.status)).toEqual(["reading"]);
    expect(p.log.changed).toBeGreaterThan(changedBefore);
    await work(s);
    const [row] = await p.backend.courses.uploads(mine.course.id);
    expect(row).toMatchObject({ title: "Potential outcomes intro", placing: false, can_place: true });
    await p.backend.courses.confirmUploads(mine.course.id, [{ upload_id: row.id, title: "Potential outcomes" }]);
    await work(s);
    const after = await p.backend.courses.mine();
    expect(after.status === "ready" && after.course.lectures.map((l) => [l.title, l.state])).toEqual([["Potential outcomes", "ready"]]);

    // a check waiting for a question the worker gave up on can ask for it again
    await p.backend.courses.retryQuestion({ ku_id: "ku-potential-outcomes-intro-a", tier: "applied" });
  });

  it("passes the server's message on", async () => {
    const s = makeServer();
    const p = phone(s);
    await p.signIn("ann@nyu.edu");
    await expect(p.backend.courses.create(file("notes.txt", "x"))).rejects.toThrow(/PDF or Word/);
  });
});

