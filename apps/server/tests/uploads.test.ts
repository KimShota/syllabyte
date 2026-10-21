import { describe, expect, it } from "vitest";
import { SCHEDULE, work, type Job } from "./fakeWorker";
import { makeServer } from "./helpers";

type Server = ReturnType<typeof makeServer>;
type Student = Awaited<ReturnType<typeof student>>;

async function multipart(who: Student, path: string, field: string, files: { name: string; text: string }[]) {
  const form = new FormData();
  for (const f of files) form.append(field, new File([f.text], f.name));
  const res = await who.raw(path, { method: "POST", body: form });
  return { status: res.status, body: (await res.json()) as any };
}

async function student(s: Server, email: string) {
  const st = await s.signIn(email);
  return Object.assign(st, {
    raw: (path: string, init: RequestInit) => s.app.request(path, { ...init, headers: { Authorization: `Bearer ${st.token}` } }),
    json: async (path: string) => (await (await st.get(path)).json()) as any,
  });
}

/** Ann creates the course from the syllabus. */
async function courseWithAnn(s: Server, syllabus = "Syllabus of CS-UH 2219E") {
  const ann = await student(s, "ann@nyu.edu");
  expect((await multipart(ann, "/api/courses", "syllabus", [{ name: "syllabus.pdf", text: syllabus }])).status).toBe(200);
  expect((await ann.json("/api/courses/mine")).status).toBe("reading");
  await work(s);
  const mine = await ann.json("/api/courses/mine");
  expect(mine.status).toBe("ready");
  return { ann, courseId: mine.course.id as string };
}

/** The review screen's order as suggested: the course's lectures and the new decks, by position. */
async function suggestedOrder(who: Student, courseId: string, titles: Record<string, string> = {}) {
  const mine = await who.json("/api/courses/mine");
  const { uploads } = await who.json(`/api/courses/${courseId}/uploads`);
  const rows = [
    ...mine.course.lectures.map((l: any) => ({ at: l.position, entry: { lecture_n: l.n } })),
    ...uploads
      .filter((u: any) => u.can_place)
      .map((u: any) => ({ at: u.suggested_position, entry: { upload_id: u.id, ...(titles[u.file_name] ? { title: titles[u.file_name] } : {}) } })),
  ];
  return { order: rows.sort((a, b) => a.at - b.at).map((r) => r.entry), uploads };
}

async function uploadAndConfirm(s: Server, who: Student, courseId: string, files: { name: string; text: string }[]) {
  const up = await multipart(who, `/api/courses/${courseId}/slides`, "files", files);
  expect(up.status).toBe(200);
  await work(s, { kinds: ["deck_read", "placement"] });
  const { order, uploads } = await suggestedOrder(who, courseId);
  const res = await who.post(`/api/courses/${courseId}/uploads/confirm`, { order });
  return { res, uploads };
}

// file names that say nothing: placement comes from what the slides teach ("order N" stands in for that)
const DECKS = [
  { name: "slides.pdf", text: "Potential outcomes intro\norder 1\nmore" },
  { name: "download (1).pdf", text: "Selection bias explained\norder 2\nmore" },
  { name: "week-notes.pdf", text: "Randomized trials\norder 3\nmore" },
];

/** A student's saved app state. */
const store = (s: Server, email: string) =>
  JSON.parse((s.db.prepare("SELECT json FROM user_state WHERE user_id = (SELECT id FROM users WHERE email = ?)").get(email) as { json: string }).json);

const titles = async (who: Student) => (await who.json("/api/courses/mine")).course.lectures.map((l: any) => l.title);

describe("a syllabus makes or joins a shared course", () => {
  it("creates the course with no lectures, keeping the syllabus's schedule as topics for placing slides (V3)", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    expect((await ann.json("/api/courses/mine")).course).toEqual({ id: courseId, code: "CS-UH 2219E", name: "Computational Social Science", lectures: [] });
    expect(JSON.parse(s.courses.get(courseId)!.topics_json)).toEqual(SCHEDULE.lectures.map((l) => l.title));
  });

  it("puts a student with the same syllabus in the same course, without reading it again", async () => {
    const s = makeServer();
    const { courseId } = await courseWithAnn(s);
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "my-copy.docx", text: "Syllabus of CS-UH 2219E" }]);
    const jobs = await work(s);
    expect(jobs.map((j) => j.kind)).toEqual(["syllabus"]);
    expect((await bob.json("/api/courses/mine")).course.id).toBe(courseId);
  });

  it("gives a different syllabus its own course", async () => {
    const s = makeServer();
    const { courseId } = await courseWithAnn(s);
    const cat = await student(s, "cat@nyu.edu");
    await multipart(cat, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Another syllabus" }]);
    await work(s);
    expect((await cat.json("/api/courses/mine")).course.id).not.toBe(courseId);
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

describe("slides, all at once or one at a time (V1, V2)", () => {
  it("reads each deck, orders them by what they teach, and processes them in that order", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    const up = await multipart(ann, `/api/courses/${courseId}/slides`, "files", [...DECKS].reverse());
    expect(up.body.uploads.map((u: any) => [u.status, u.placing])).toEqual([["reading", true], ["reading", true], ["reading", true]]);

    const reading = await work(s, { kinds: ["deck_read", "placement"] });
    // one placement call for the whole batch, once every file is read, with what each deck teaches
    expect(reading.map((j) => j.kind)).toEqual(["deck_read", "deck_read", "deck_read", "placement"]);
    expect(reading[0].payload).toMatchObject({ course_name: "Computational Social Science", file_name: "week-notes.pdf" });
    expect(reading[3].payload.topics).toEqual(SCHEDULE.lectures.map((l) => l.title));
    expect(reading[3].payload.new.map((d: any) => d.title)).toEqual(["Randomized trials", "Selection bias explained", "Potential outcomes intro"]);

    const { order, uploads } = await suggestedOrder(ann, courseId);
    expect(uploads.map((u: any) => [u.file_name, u.title, u.placing, u.suggestion_sure, u.can_place])).toEqual([
      ["week-notes.pdf", "Randomized trials", false, true, true],
      ["download (1).pdf", "Selection bias explained", false, true, true],
      ["slides.pdf", "Potential outcomes intro", false, true, true],
    ]);
    expect((await ann.post(`/api/courses/${courseId}/uploads/confirm`, { order })).status).toBe(200);
    const mine = await ann.json("/api/courses/mine");
    expect(mine.course.lectures.map((l: any) => [l.title, l.state])).toEqual([
      ["Potential outcomes intro", "analyzing"],
      ["Selection bias explained", "analyzing"],
      ["Randomized trials", "analyzing"],
    ]);

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
      return { lectures: fx.course.lectures.map((l) => [l.title, l.position]), kus: fx.course.kus.map((k) => [k.id, k.lecture_n, k.prerequisites]) };
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

  it("places a deck that comes earlier before the lectures it precedes, keeps their numbers, and adds links back (U7)", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[2]]);
    await work(s);
    const before = s.courses.fixtures(courseId).course.kus.map((k) => k.id);

    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    const jobs = await work(s, { links: (p) => [{ ku_id: p.later_kus[0].id, prereq_id: p.new_kus[1].id }] });
    const lectures = (await ann.json("/api/courses/mine")).course.lectures;
    // the randomized-trials lecture stays number 1; the one placed before it is number 2
    expect(lectures.map((l: any) => [l.n, l.title])).toEqual([[2, "Potential outcomes intro"], [1, "Randomized trials"]]);
    const pass = jobs.find((j) => j.kind === "link_pass")!;
    expect(pass.payload.new_kus.map((k: any) => k.lecture_n)).toEqual([1, 1]);
    expect(pass.payload.later_kus.map((k: any) => k.lecture_n)).toEqual([2, 2]);

    const kus = s.courses.fixtures(courseId).course.kus;
    expect(kus.find((k) => k.id === "ku-randomized-trials-a")!.prerequisites).toEqual(["ku-potential-outcomes-intro-b"]);
    expect(kus.filter((k) => k.lecture_n === 1).map((k) => k.id)).toEqual(before);
  });

  it("lets the first uploader rename a lecture and change the order, but not the lectures already there", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    await work(s);
    await multipart(ann, `/api/courses/${courseId}/slides`, "files", [DECKS[1], DECKS[2]]);
    await work(s, { kinds: ["deck_read", "placement"] });
    const { order } = await suggestedOrder(ann, courseId, { "week-notes.pdf": "Experiments" });

    const swapped = [order[0], order[2], order[1]];
    // the lectures already there can't be left out or moved
    expect((await ann.post(`/api/courses/${courseId}/uploads/confirm`, { order: order.slice(1) })).status).toBe(409);
    expect((await ann.post(`/api/courses/${courseId}/uploads/confirm`, { order: order.slice(0, 2) })).status).toBe(400);
    expect((await ann.post(`/api/courses/${courseId}/uploads/confirm`, { order: swapped })).status).toBe(200);
    expect(await titles(ann)).toEqual(["Potential outcomes intro", "Experiments", "Selection bias explained"]);
  });

  it("reuses a deck already in the course: no reading by the model, no processing, no cap", async () => {
    const s = makeServer({ caps: { newDecksPerDay: 1 } });
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    await work(s);
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus of CS-UH 2219E" }]);
    await work(s);

    await multipart(bob, `/api/courses/${courseId}/slides`, "files", [{ name: "my download.pdf", text: DECKS[0].text }]);
    const reads = await work(s);
    expect(reads.map((j) => j.kind)).toEqual(["deck_read"]);
    expect(reads[0].payload.known_keys).toContain(`key:${DECKS[0].text}`);
    const { uploads } = await bob.json(`/api/courses/${courseId}/uploads`);
    expect(uploads[0]).toMatchObject({ outcome: "existing", placed_lecture_n: 1, title: "Potential outcomes intro", can_place: false, deck: { status: "ready" } });
    const mine = await bob.json("/api/courses/mine");
    await bob.post(`/api/courses/${courseId}/uploads/confirm`, { order: mine.course.lectures.map((l: any) => ({ lecture_n: l.n })) });
    expect((await work(s)).length).toBe(0);
  });

  it("logs an updated version of slides already in the course and does not process it (V2)", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0]]);
    await work(s);
    const fixed = { name: "slides (fixed).pdf", text: "Potential outcomes intro\norder 1\nmore\na typo fixed" };
    await multipart(ann, `/api/courses/${courseId}/slides`, "files", [fixed]);
    expect((await work(s)).map((j) => j.kind)).toEqual(["deck_read"]);
    const { uploads } = await ann.json(`/api/courses/${courseId}/uploads`);
    expect(uploads[0]).toMatchObject({ outcome: "updated_version", placed_lecture_n: 1, can_place: false, placing: false });
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

  it("puts the decks last, unsure, when the placement call fails", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[2]]);
    await work(s);
    await multipart(ann, `/api/courses/${courseId}/slides`, "files", [DECKS[0], DECKS[1]]);
    await work(s, { kinds: ["deck_read"] });
    for (let i = 0; i < 2; i++) {
      const { job } = (await (await s.worker.post("/api/worker/claim", { kinds: ["placement"] })).json()) as { job: Job };
      await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "overloaded" });
    }
    const { order, uploads } = await suggestedOrder(ann, courseId);
    expect(uploads.map((u: any) => [u.placing, u.suggestion_sure])).toEqual([[false, false], [false, false]]);
    expect(order.map((e: any) => ("lecture_n" in e ? "lecture" : "new"))).toEqual(["lecture", "new", "new"]);
  });

  it("makes a deck with nothing to teach a lecture with no check", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [{ name: "review.pdf", text: "Midterm review\norder 1" }]);
    const { job } = (await (await s.worker.post("/api/worker/claim", {})).json()) as { job: Job };
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result: { kus: [], items: [] } })).status).toBe(200);
    const mine = await ann.json("/api/courses/mine");
    expect(mine.course.lectures.map((l: any) => [l.title, l.state])).toEqual([["Midterm review", "ready"]]);
    expect((await ann.rpc<{ precheck: unknown }>("getPlaylist")).precheck).toBeNull();
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
    expect(((await (await s.worker.post("/api/worker/claim", {})).json()) as any).job).toBeNull();

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
    expect((await s.post("/api/questions/retry", { ku_id: "x", tier: "basic" })).status).toBe(401);
    expect((await s.post("/api/worker/claim", {}, { Authorization: "Bearer wrong" })).status).toBe(401);
  });
});

/** Answers a whole check, letting the worker write each question as the check waits for it. */
async function sitCheck(s: Server, who: Student, sitting: string, finish = true) {
  for (let guard = 0; guard < 40; guard++) {
    const v = await who.rpc<{ current: { item: { id: string; correct_index: number } } | null; preparing: string | null }>("getSitting", sitting);
    if (v.preparing === "writing") {
      await work(s, { kinds: ["question"] });
      continue;
    }
    if (!v.current) break;
    await who.rpc("answerSitting", sitting, v.current.item.id, v.current.item.correct_index, 1000);
  }
  if (finish) await who.rpc("finishSitting", sitting);
}

describe("the student's files (Syllabus & Course Slides)", () => {
  it("lists their syllabus and every slide file, lectures in teaching order, then the rest", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    // uploaded out of teaching order: the file named week-notes.pdf teaches lecture 3
    await uploadAndConfirm(s, ann, courseId, [DECKS[2], DECKS[0]]);
    await work(s);
    // a copy of slides the course has, and new slides not confirmed yet
    await multipart(ann, `/api/courses/${courseId}/slides`, "files", [{ ...DECKS[0], name: "copy.pdf" }, DECKS[1]]);
    await work(s, { kinds: ["deck_read", "placement"] });

    const files = await ann.json(`/api/courses/${courseId}/files`);
    expect(files.syllabus).toMatchObject({ file_name: "syllabus.pdf" });
    expect(files.slides.map((f: any) => [f.file_name, f.state])).toEqual([
      ["slides.pdf", "lecture"],
      ["week-notes.pdf", "lecture"],
      ["copy.pdf", "same_as"],
      ["download (1).pdf", "to_review"],
    ]);
    expect(files.slides[0].lecture.n).toBeLessThan(files.slides[1].lecture.n);
    // the copy names the lecture it duplicates; slides waiting for review are no lecture yet
    expect(files.slides[2].lecture).toEqual(files.slides[0].lecture);
    expect(files.slides[3].lecture).toBeNull();
  });

  it("shows a student only their own course's files", async () => {
    const s = makeServer();
    const { courseId } = await courseWithAnn(s);
    const bob = await student(s, "bob@nyu.edu");
    expect((await bob.get(`/api/courses/${courseId}/files`)).status).toBe(404);
  });

  it("opens a student's own file through a short-lived link, and nobody else's", async () => {
    let now = Date.UTC(2026, 9, 21);
    const s = makeServer({ clock: () => now });
    const { ann, courseId } = await courseWithAnn(s);
    await multipart(ann, `/api/courses/${courseId}/slides`, "files", [DECKS[0]]);
    const files = await ann.json(`/api/courses/${courseId}/files`);
    const slide = files.slides[0].id as string;

    const link = async (who: typeof ann, fileId: string) => who.post(`/api/courses/${courseId}/files/${fileId}/link`, {});
    const { path } = (await (await link(ann, slide)).json()) as { path: string };
    const opened = await s.app.request(path); // no sign-in: the signature is the permission
    expect(opened.status).toBe(200);
    expect(opened.headers.get("Content-Type")).toBe("application/pdf");
    expect(opened.headers.get("Content-Disposition")).toContain("slides.pdf");
    expect(await opened.text()).toBe(DECKS[0].text);
    const syllabus = (await (await link(ann, files.syllabus.id)).json()) as { path: string };
    expect(await (await s.app.request(syllabus.path)).text()).toBe("Syllabus of CS-UH 2219E");

    // a changed link, another file under the same signature, or an old link does not open
    expect((await s.app.request(path.replace(/s=[0-9a-f]{4}/, "s=0000"))).status).toBe(403);
    expect((await s.app.request(path.replace(slide, files.syllabus.id))).status).toBe(403);
    now += 6 * 60 * 1000;
    expect((await s.app.request(path)).status).toBe(403);

    // a classmate cannot get a link to Ann's file
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus of CS-UH 2219E" }]);
    await work(s);
    expect((await link(bob, slide)).status).toBe(404);
  });
});

describe("questions written as checks need them (V4-V6)", () => {
  type Sitting = { current: { item: { id: string; correct_index: number; tier: string } } | null; preparing: string | null; total: number };

  async function readyCourse(decks = [DECKS[0]]) {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, decks);
    await work(s);
    const n = (await ann.json("/api/courses/mine")).course.lectures[0].n as number;
    return { s, ann, courseId, sitting: `lecture-${n}` };
  }

  it("has no baseline: the first check is lecture 1's, and it waits for its first question", async () => {
    const { ann, sitting } = await readyCourse();
    const me = await ann.rpc<{ onboarding_done: boolean; baseline_available: boolean }>("getMe");
    expect(me).toMatchObject({ onboarding_done: true, baseline_available: false });
    expect((await ann.rpc<{ precheck: { sitting_id: string } | null }>("getPlaylist")).precheck?.sitting_id).toBe(sitting);
    const first = await ann.rpc<Sitting>("getSitting", sitting);
    // two KUs in the lecture and nothing earlier: two questions
    expect(first).toMatchObject({ current: null, preparing: "writing", total: 2 });
  });

  it("writes the question a check waits for before anything else, and none ahead of it", async () => {
    const { s, ann, sitting } = await readyCourse();
    await ann.rpc("getSitting", sitting);
    // a deck upload waiting in the queue does not hold the question back
    await multipart(ann, `/api/courses/${(await ann.json("/api/courses/mine")).course.id}/slides`, "files", [DECKS[1]]);
    const { job } = (await (await s.worker.post("/api/worker/claim", {})).json()) as { job: Job };
    expect(job.kind).toBe("question");
    expect(job.payload).toMatchObject({ item_id: "as-ku-potential-outcomes-intro-a-applied-1", tier: "applied", beta: 0, avoid: [] });
    expect(job.file_name).toBe("slides.pdf");
    const text = await (await s.worker.get(`/api/worker/jobs/${job.id}/file`)).text();
    expect(text).toBe(DECKS[0].text);
    await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "retry later" });
    await work(s, { kinds: ["question"] });

    const ready = await ann.rpc<Sitting>("getSitting", sitting);
    expect(ready.current?.item.id).toBe("as-ku-potential-outcomes-intro-a-applied-1");
    // the next question is written only once the student has answered and it is the one the check waits for
    expect(await work(s, { kinds: ["question"] })).toEqual([]);
  });

  it("asks a classmate the saved questions, so nothing is written twice", async () => {
    const { s, ann, sitting } = await readyCourse();
    await sitCheck(s, ann, sitting, false);
    await work(s, { kinds: ["question"] });
    expect(store(s, "ann@nyu.edu").sittings[sitting].answered_ids).toHaveLength(2);
    const written = (s.db.prepare("SELECT COUNT(*) AS n FROM questions").get() as { n: number }).n;

    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus of CS-UH 2219E" }]);
    await work(s);
    const v = await bob.rpc<Sitting>("getSitting", sitting);
    expect(v.current?.item.id).toBe("as-ku-potential-outcomes-intro-a-applied-1");
    expect((s.db.prepare("SELECT COUNT(*) AS n FROM questions").get() as { n: number }).n).toBe(written);
  });

  it("says when a question could not be written, and writes it again on Try again", async () => {
    const { s, ann, sitting } = await readyCourse();
    await ann.rpc("getSitting", sitting);
    for (let i = 0; i < 2; i++) {
      const { job } = (await (await s.worker.post("/api/worker/claim", {})).json()) as { job: Job };
      await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "overloaded" });
    }
    expect((await ann.rpc<Sitting>("getSitting", sitting)).preparing).toBe("failed");
    expect((await ann.post("/api/questions/retry", { ku_id: "ku-potential-outcomes-intro-a", tier: "applied" })).status).toBe(200);
    expect((await ann.rpc<Sitting>("getSitting", sitting)).preparing).toBe("writing");
    await work(s, { kinds: ["question"] });
    expect((await ann.rpc<Sitting>("getSitting", sitting)).current).not.toBeNull();
  });

  it("refuses a question result that is not for the job's KU and tier", async () => {
    const { s, ann, sitting } = await readyCourse();
    await ann.rpc("getSitting", sitting);
    const { job } = (await (await s.worker.post("/api/worker/claim", {})).json()) as { job: Job };
    const bad = { item: { id: "x", ku_id: "ku-other", tier: "basic", context: "assessment", options: ["a", "b", "c"], correct_index: 0 } };
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result: bad })).status).toBe(400);
  });
});

describe("videos students need (U18)", () => {
  it("records a lecture's videos once its check set its levels, shared by course, KU and level", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0], DECKS[1]]);
    await work(s);
    expect(s.courses.videoRequests(courseId)).toEqual([]);
    const first = `lecture-${(await ann.json("/api/courses/mine")).course.lectures[0].n}`;

    const sit = (who: Student) => sitCheck(s, who, first);
    await sit(ann);
    const after = s.courses.videoRequests(courseId);
    // only the checked lecture's KUs: the second lecture's levels are provisional until its own check
    expect(after.map((r) => [r.ku_id, r.lecture_n])).toEqual([
      ["ku-potential-outcomes-intro-a", 1],
      ["ku-potential-outcomes-intro-b", 1],
    ]);

    // a classmate at the same levels adds nothing new
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus of CS-UH 2219E" }]);
    await work(s);
    await sit(bob);
    expect(s.courses.videoRequests(courseId)).toHaveLength(2);
  });

  it("keeps a KU's first prerequisites for its later levels (U8)", async () => {
    const s = makeServer();
    const { ann, courseId } = await courseWithAnn(s);
    await uploadAndConfirm(s, ann, courseId, [DECKS[0], DECKS[1]]);
    await work(s);
    const annId = (s.db.prepare("SELECT id FROM users WHERE email = 'ann@nyu.edu'").get() as { id: string }).id;
    const ku = "ku-selection-bias-explained-b";
    s.courses.requestVideos(courseId, annId, [{ ku_id: ku, lecture_n: 2, level: 1 }]);
    // a later link pass adds a prerequisite from lecture 1
    s.courses.addLinks(courseId, [{ ku_id: ku, prereq_id: "ku-potential-outcomes-intro-a" }]);
    expect(s.courses.fixtures(courseId).course.kus.find((k) => k.id === ku)!.prerequisites).toEqual([
      "ku-selection-bias-explained-a",
      "ku-potential-outcomes-intro-a",
    ]);
    s.courses.requestVideos(courseId, annId, [{ ku_id: ku, lecture_n: 2, level: 3 }]);
    expect(s.courses.videoRequests(courseId).map((r) => [r.level, r.prereq_ids])).toEqual([
      [1, ["ku-selection-bias-explained-a"]],
      [3, ["ku-selection-bias-explained-a"]],
    ]);
  });
});
