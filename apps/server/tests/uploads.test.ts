import { describe, expect, it } from "vitest";
import type { DeckResult } from "@syllabyte/core/logic/assemble";
import type { Item } from "@syllabyte/core/types";
import { suggestLecture } from "../src/uploads";
import { makeServer } from "./helpers";

type Server = ReturnType<typeof makeServer>;
type Student = Awaited<ReturnType<typeof student>>;

interface Job {
  id: string;
  kind: "syllabus" | "deck_read" | "deck" | "link_pass";
  payload: Record<string, any>;
  file_name: string | null;
}

const SCHEDULE = {
  course_code: "CS-UH 2219E",
  course_name: "Computational Social Science",
  lectures: [
    { n: 1, title: "Potential outcomes", week: 1 },
    { n: 2, title: "Selection bias", week: 2 },
    { n: 3, title: "Randomization", week: 3 },
  ],
};

/** What the Python worker would read from a file: here the file's text is its content (and its key). */
function readOf(text: string) {
  return { content_key: `key:${text}`, page_count: 2, first_title: text.split("\n")[0], pages: text.split("\n") };
}

/** A deterministic stand-in for the deck job: two KUs named after the deck's first line, the first building on the
 * last KU it was shown from earlier lectures (as the real extraction may). */
function deckResultOf(firstLine: string, payload: Record<string, any>): DeckResult {
  const slug = firstLine.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const earlier: { id: string }[] = payload.earlier;
  const a = `ku-${slug}-a`;
  const b = `ku-${slug}-b`;
  const item = (ku: string, tier: string): Item => ({
    id: `as-${ku}-${tier}`, ku_id: ku, topic_id: "", context: "assessment", stem: `${ku} ${tier}?`, options: ["x", "y", "z"], correct_index: 1,
    allows_not_sure: true, explanation: "", hint: null, difficulty_prior: tier === "basic" ? -1 : tier === "applied" ? 0 : 1, discrimination: 1,
    tier: tier as Item["tier"], source_refs: [],
  });
  return {
    kus: [
      { id: a, title: a, short_title: a, summary: "", bloom_level: "understand", prerequisites: earlier.length ? [earlier.at(-1)!.id] : [], source_refs: [] },
      { id: b, title: b, short_title: b, summary: "", bloom_level: "apply", prerequisites: [a], source_refs: [] },
    ],
    items: [a, b].flatMap((k) => ["basic", "applied", "advanced"].map((t) => item(k, t))),
  };
}

async function multipart(who: Student, path: string, field: string, files: { name: string; text: string }[]) {
  const form = new FormData();
  for (const f of files) form.append(field, new File([f.text], f.name));
  const res = await who.raw(path, { method: "POST", body: form });
  return { status: res.status, body: (await res.json()) as any };
}

/** The fake worker: claims jobs and answers them the way ingestion_agent/worker.py would. */
async function work(s: Server, opts: { links?: (p: Record<string, any>) => { ku_id: string; prereq_id: string }[]; until?: number } = {}) {
  const done: Job[] = [];
  for (let guard = 0; guard < (opts.until ?? 200); guard++) {
    const { job } = (await (await s.worker.post("/api/worker/claim", {})).json()) as { job: Job | null };
    if (!job) break;
    done.push(job);
    const text = job.file_name ? await (await s.worker.get(`/api/worker/jobs/${job.id}/file`)).text() : "";
    let result: Record<string, unknown>;
    if (job.kind === "syllabus") {
      const key = `syl:${text}`;
      const { is_new } = (await (await s.worker.post(`/api/worker/jobs/${job.id}/syllabus-key`, { key })).json()) as { is_new: boolean };
      result = is_new ? { key, text, schedule: text.includes("no schedule") ? { ...SCHEDULE, lectures: [] } : SCHEDULE } : { key, text };
    } else if (job.kind === "deck_read") {
      result = readOf(text);
    } else if (job.kind === "deck") {
      result = deckResultOf(text.split("\n")[0], job.payload) as unknown as Record<string, unknown>;
    } else {
      result = { links: opts.links?.(job.payload) ?? [] };
    }
    const r = await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result });
    expect(r.status, `${job.kind} result`).toBe(200);
  }
  return done;
}

async function student(s: Server, email: string) {
  const st = await s.signIn(email);
  return Object.assign(st, {
    raw: (path: string, init: RequestInit) => s.app.request(path, { ...init, headers: { Authorization: `Bearer ${st.token}` } }),
    json: async (path: string) => (await (await st.get(path)).json()) as any,
  });
}

/** Ann creates the course from the syllabus and confirms the lecture list as read. */
async function courseWithAnn(s: Server, syllabus = "Syllabus of CS-UH 2219E") {
  const ann = await student(s, "ann@nyu.edu");
  expect((await multipart(ann, "/api/courses", "syllabus", [{ name: "syllabus.pdf", text: syllabus }])).status).toBe(200);
  expect((await ann.json("/api/courses/mine")).status).toBe("reading");
  await work(s);
  const mine = await ann.json("/api/courses/mine");
  expect(mine.status).toBe("ready");
  await ann.post(`/api/courses/${mine.course.id}/lectures`, {});
  return { ann, courseId: mine.course.id as string };
}

async function uploadAndConfirm(s: Server, who: Student, courseId: string, files: { name: string; text: string }[], kinds: Record<string, string> = {}) {
  const up = await multipart(who, `/api/courses/${courseId}/slides`, "files", files);
  expect(up.status).toBe(200);
  await work(s, { until: files.length });
  const { uploads } = await who.json(`/api/courses/${courseId}/uploads`);
  const choices = uploads
    .filter((u: any) => u.status === "read")
    .map((u: any) => ({ upload_id: u.id, lecture_n: u.placed_lecture_n ?? u.suggested_lecture_n, ...(kinds[u.file_name] ? { kind: kinds[u.file_name] } : {}) }));
  const res = await who.post(`/api/courses/${courseId}/uploads/confirm`, { choices });
  return { res, uploads };
}

const DECKS = [
  { name: "lecture1.pdf", text: "Potential outcomes intro\nmore" },
  { name: "lecture2.pdf", text: "Selection bias explained\nmore" },
  { name: "lecture3.pdf", text: "Randomized trials\nmore" },
];

describe("a syllabus makes or joins a shared course", () => {
  it("creates the course with the lecture list read from the syllabus", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    const mine = await ann.json("/api/courses/mine");
    expect(mine.course).toMatchObject({ id: courseId, code: "CS-UH 2219E", name: "Computational Social Science", is_creator: true, lectures_confirmed: true, schedule_found: true });
    expect(mine.course.lectures.map((l: any) => [l.n, l.title, l.state])).toEqual([
      [1, "Potential outcomes", "waiting"],
      [2, "Selection bias", "waiting"],
      [3, "Randomization", "waiting"],
    ]);
  });

  it("puts a student with the same syllabus in the same course, without reading the lecture list again", async () => {
    const s = makeServer();
    const { courseId } = await courseWithAnn(s);
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "my-copy.docx", text: "Syllabus of CS-UH 2219E" }]);
    const jobs = await work(s);
    expect(jobs.map((j) => j.kind)).toEqual(["syllabus"]);
    const mine = await bob.json("/api/courses/mine");
    expect(mine.course).toMatchObject({ id: courseId, is_creator: false });
  });

  it("gives a different syllabus its own course", async () => {
    const s = makeServer();
    const { courseId } = await courseWithAnn(s);
    const cat = await student(s, "cat@nyu.edu");
    await multipart(cat, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Another course's syllabus" }]);
    await work(s);
    expect((await cat.json("/api/courses/mine")).course.id).not.toBe(courseId);
  });

  it("lets only the creator change the lecture list, and only before confirming it", async () => {
    const s = makeServer();
    const ann = await student(s, "ann@nyu.edu");
    await multipart(ann, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus X" }]);
    await work(s);
    const courseId = (await ann.json("/api/courses/mine")).course.id;
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus X" }]);
    await work(s);
    expect((await bob.post(`/api/courses/${courseId}/lectures`, {})).status).toBe(403);

    const edited = [{ n: 1, title: "Potential outcomes and causal questions", week: 1 }, { n: 2, title: "Bias", week: null }];
    const res = await ann.post(`/api/courses/${courseId}/lectures`, { lectures: edited });
    expect(res.status).toBe(200);
    expect((await res.json() as any).course.lectures.map((l: any) => l.title)).toEqual(["Potential outcomes and causal questions", "Bias"]);
    expect((await ann.post(`/api/courses/${courseId}/lectures`, {})).status).toBe(409);
  });

  it("refuses a second course for now, and files that are not a syllabus", async () => {
    const s = makeServer();
    const { ann } = await courseWithAnn(s);
    expect((await multipart(ann, "/api/courses", "syllabus", [{ name: "other.pdf", text: "x" }])).status).toBe(409);
    const bob = await student(s, "bob@nyu.edu");
    const bad = await multipart(bob, "/api/courses", "syllabus", [{ name: "s.txt", text: "x" }]);
    expect(bad).toMatchObject({ status: 400, body: { error: expect.stringMatching(/PDF or Word/) } });
  });

  it("shows the reason when the syllabus could not be read", async () => {
    const s = makeServer();
    const ann = await student(s, "ann@nyu.edu");
    await multipart(ann, "/api/courses", "syllabus", [{ name: "scan.pdf", text: "x" }]);
    const { job } = (await (await s.worker.post("/api/worker/claim", {})).json()) as { job: Job };
    await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "no text", user_message: "No text could be read from this syllabus." });
    expect(await ann.json("/api/courses/mine")).toEqual({ status: "failed", error: "No text could be read from this syllabus." });
  });
});

describe("slides, all at once or one at a time", () => {
  it("suggests each deck's lecture and processes the decks in lecture order", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    const up = await multipart(ann, `/api/courses/${courseId}/slides`, "files", [...DECKS].reverse());
    expect(up.body.uploads.map((u: any) => u.status)).toEqual(["reading", "reading", "reading"]);
    await work(s, { until: 3 });
    const { uploads } = await ann.json(`/api/courses/${courseId}/uploads`);
    expect(uploads.map((u: any) => [u.file_name, u.suggested_lecture_n, u.suggestion_sure, u.can_place])).toEqual([
      ["lecture3.pdf", 3, true, true],
      ["lecture2.pdf", 2, true, true],
      ["lecture1.pdf", 1, true, true],
    ]);
    await ann.post(`/api/courses/${courseId}/uploads/confirm`, { choices: uploads.map((u: any) => ({ upload_id: u.id, lecture_n: u.suggested_lecture_n })) });
    expect((await ann.json("/api/courses/mine")).course.lectures.map((l: any) => l.state)).toEqual(["analyzing", "analyzing", "analyzing"]);

    const jobs = await work(s);
    // uploaded last-first, processed first-last, each seeing the lectures before it
    expect(jobs.filter((j) => j.kind === "deck").map((j) => [j.payload.lecture_n, j.payload.earlier.map((k: any) => k.lecture_n)])).toEqual([
      [1, []],
      [2, [1, 1]],
      [3, [1, 1, 2, 2]],
    ]);
    expect(jobs.some((j) => j.kind === "link_pass")).toBe(false);
    expect((await ann.json("/api/courses/mine")).course.lectures.map((l: any) => l.state)).toEqual(["ready", "ready", "ready"]);
  });

  it("ends with the same course whether the slides came all at once or one at a time", async () => {
    const atOnce = makeServer();
    const a = await courseWithAnn(atOnce);
    await uploadAndConfirm(atOnce, a.ann, a.courseId, DECKS);
    await work(atOnce);

    const oneByOne = makeServer();
    const b = await courseWithAnn(oneByOne);
    for (const d of DECKS) {
      await uploadAndConfirm(oneByOne, b.ann, b.courseId, [d]);
      await work(oneByOne);
    }

    const shape = (s: Server, id: string) => {
      const fx = s.courses.fixtures(id);
      return { kus: fx.course.kus.map((k) => [k.id, k.lecture_n, k.prerequisites]), items: fx.items.map((i) => [i.id, i.topic_id]) };
    };
    expect(shape(oneByOne, b.courseId)).toEqual(shape(atOnce, a.courseId));
    expect(shape(atOnce, a.courseId).kus).toEqual([
      ["ku-potential-outcomes-intro-a", 1, []],
      ["ku-potential-outcomes-intro-b", 1, ["ku-potential-outcomes-intro-a"]],
      ["ku-selection-bias-explained-a", 2, ["ku-potential-outcomes-intro-b"]],
      ["ku-selection-bias-explained-b", 2, ["ku-selection-bias-explained-a"]],
      ["ku-randomized-trials-a", 3, ["ku-selection-bias-explained-b"]],
      ["ku-randomized-trials-b", 3, ["ku-randomized-trials-a"]],
    ]);
  });

  it("adds links back when an earlier lecture arrives after a later one, and changes nothing else", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[2]]);
    await work(s);
    const before = s.courses.fixtures(courseId).course.kus.map((k) => k.id);

    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    const jobs = await work(s, { links: (p) => [{ ku_id: p.later_kus[0].id, prereq_id: p.new_kus[1].id }] });
    const pass = jobs.find((j) => j.kind === "link_pass")!;
    expect(pass.payload.new_kus.map((k: any) => k.lecture_n)).toEqual([1, 1]);
    expect(pass.payload.later_kus.map((k: any) => k.lecture_n)).toEqual([3, 3]);

    const kus = s.courses.fixtures(courseId).course.kus;
    expect(kus.find((k) => k.id === "ku-randomized-trials-a")!.prerequisites).toEqual(["ku-potential-outcomes-intro-b"]);
    expect(kus.filter((k) => k.lecture_n === 3).map((k) => k.id)).toEqual(before);
  });

  it("reuses a deck already in the course: no processing, no cap, placed where it already is", async () => {
    const s = makeServer({ caps: { newDecksPerDay: 1 } });
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    await work(s);
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus of CS-UH 2219E" }]);
    await work(s);

    await multipart(bob, `/api/courses/${courseId}/slides`, "files", [{ name: "my download.pdf", text: DECKS[0].text }]);
    await work(s);
    const { uploads } = await bob.json(`/api/courses/${courseId}/uploads`);
    expect(uploads[0]).toMatchObject({ outcome: "existing", placed_lecture_n: 1, can_place: false, deck: { status: "ready" } });
    await bob.post(`/api/courses/${courseId}/uploads/confirm`, { choices: [{ upload_id: uploads[0].id }] });
    expect((await work(s)).length).toBe(0);
  });

  it("stops new decks at the daily cap with a message", async () => {
    const s = makeServer({ caps: { newDecksPerDay: 2 } });
    const { ann, courseId } = await courseWithAnn(s);
    await multipart(ann, `/api/courses/${courseId}/slides`, "files", DECKS);
    await work(s);
    const { uploads } = await ann.json(`/api/courses/${courseId}/uploads`);
    expect(uploads.map((u: any) => u.outcome)).toEqual(["new", "new", "over_cap"]);
    expect(uploads[2].error).toMatch(/up to 2 new slide files a day/);
  });

  it("asks whether a second deck for a lecture is an extra part or an updated version", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    await work(s);

    const part2 = { name: "lecture1-part2.pdf", text: "Potential outcomes part two\nmore" };
    const asked = await uploadAndConfirm(s, ann, courseId, [part2]);
    expect(asked.res.status).toBe(409);
    expect(((await asked.res.json()) as any).error).toMatch(/extra part, or an updated version/);

    const extra = await ann.post(`/api/courses/${courseId}/uploads/confirm`, { choices: [{ upload_id: asked.uploads[0].id, lecture_n: 1, kind: "extra_part" }] });
    expect(extra.status).toBe(200);
    const jobs = await work(s);
    // part two sees part one's KUs (U10)
    expect(jobs.find((j) => j.kind === "deck")!.payload.earlier.map((k: any) => k.id)).toEqual(["ku-potential-outcomes-intro-a", "ku-potential-outcomes-intro-b"]);

    const fixed = { name: "lecture1-fixed.pdf", text: "Potential outcomes intro, typo fixed\nmore" };
    const again = await uploadAndConfirm(s, ann, courseId, [fixed], { "lecture1-fixed.pdf": "updated_version" });
    expect(again.res.status).toBe(200);
    expect((await work(s)).length).toBe(0);
    const row = s.db.prepare("SELECT outcome FROM deck_uploads WHERE file_name = 'lecture1-fixed.pdf'").get() as { outcome: string };
    expect(row.outcome).toBe("updated_version");
  });

  it("adds a lecture per deck when the syllabus has no schedule", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s, "Syllabus with no schedule");
    expect((await ann.json("/api/courses/mine")).course.lectures).toEqual([]);
    const { uploads } = await (async () => {
      await multipart(ann, `/api/courses/${courseId}/slides`, "files", [DECKS[0]]);
      await work(s);
      return ann.json(`/api/courses/${courseId}/uploads`);
    })();
    expect(uploads[0]).toMatchObject({ suggested_lecture_n: null, suggestion_sure: false });
    expect((await ann.post(`/api/courses/${courseId}/uploads/confirm`, { choices: [{ upload_id: uploads[0].id, lecture_n: 2 }] })).status).toBe(400);
    expect((await ann.post(`/api/courses/${courseId}/uploads/confirm`, { choices: [{ upload_id: uploads[0].id, lecture_n: 1 }] })).status).toBe(200);
    expect((await ann.json("/api/courses/mine")).course.lectures.map((l: any) => [l.n, l.title])).toEqual([[1, "Potential outcomes intro"]]);
  });

  it("refuses Keynote and other files with a message", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    const key = await multipart(ann, `/api/courses/${courseId}/slides`, "files", [{ name: "deck.key", text: "x" }]);
    expect(key).toMatchObject({ status: 400, body: { error: expect.stringMatching(/Export To > PDF/) } });
    const png = await multipart(ann, `/api/courses/${courseId}/slides`, "files", [{ name: "deck.png", text: "x" }]);
    expect(png.status).toBe(400);
  });

  it("retries a deck once after a worker error, then shows it as failed until the researcher retries it", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    for (let i = 0; i < 2; i++) {
      const { job } = (await (await s.worker.post("/api/worker/claim", {})).json()) as { job: Job };
      expect(job.kind).toBe("deck");
      await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "API overloaded" });
    }
    expect((await ann.json("/api/courses/mine")).course.lectures[0].state).toBe("failed");
    expect((await (await s.worker.post("/api/worker/claim", {})).json() as any).job).toBeNull();

    const failed = s.db.prepare("SELECT id FROM jobs WHERE status = 'failed'").get() as { id: string };
    const res = await (await s.signIn("res@nyu.edu", "researcher")).post(`/api/research/jobs/${failed.id}/retry`, {});
    expect(res.status).toBe(200);
    await work(s);
    expect((await ann.json("/api/courses/mine")).course.lectures[0].state).toBe("ready");
  });

  it("keeps other students and the worker without its token out", async () => {
    const s = makeServer();
    const { courseId } = await courseWithAnn(s);
    const eve = await student(s, "eve@nyu.edu");
    expect((await multipart(eve, `/api/courses/${courseId}/slides`, "files", [DECKS[0]])).status).toBe(404);
    expect((await s.post("/api/worker/claim", {})).status).toBe(401);
    expect((await s.post("/api/worker/claim", {}, { Authorization: "Bearer wrong" })).status).toBe(401);
  });

  it("runs a member's study requests on the course once a deck is ready", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    await work(s);
    const sitting = await ann.rpc<{ current: { item: { id: string } } }>("getSitting", "week0");
    expect(sitting.current.item.id).toMatch(/^as-ku-potential-outcomes-intro-/);
  });
});

describe("suggestLecture", () => {
  const lectures = SCHEDULE.lectures;
  it("reads lecture and week numbers in file names", () => {
    expect(suggestLecture("Lecture 02 - slides.pdf", "", lectures)).toEqual({ n: 2, sure: true });
    expect(suggestLecture("wk_3.pdf", "", lectures)).toEqual({ n: 3, sure: true });
    expect(suggestLecture("03_randomization.pptx", "", lectures)).toEqual({ n: 3, sure: true });
    expect(suggestLecture("L1.pdf", "", lectures)).toEqual({ n: 1, sure: true });
  });
  it("otherwise matches titles, sure only on a good match", () => {
    expect(suggestLecture("deck.pdf", "Selection Bias in observational data", lectures)).toEqual({ n: 2, sure: true });
    expect(suggestLecture("potential.pdf", "", [{ n: 1, title: "Potential outcomes and causal effects", week: 1 }])).toEqual({ n: 1, sure: false });
    expect(suggestLecture("deck.pdf", "Welcome!", lectures)).toEqual({ n: null, sure: false });
  });
  it("ignores a number that is not a lecture in the list", () => {
    expect(suggestLecture("lecture12.pdf", "Randomization", lectures)).toEqual({ n: 3, sure: true });
  });
});
