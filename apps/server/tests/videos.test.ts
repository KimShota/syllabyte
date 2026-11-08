import { mkdtempSync, readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { openDb } from "../src/db";
import { videoOf, work } from "./fakeWorker";
import { makeServer } from "./helpers";

/** Videos made by the pipeline (plan/participant-ready-plan.md S1-S4): the job, the files, what a student is handed. */

type Server = ReturnType<typeof makeServer>;
type Student = Awaited<ReturnType<typeof student>>;

async function student(s: Server, email: string) {
  const st = await s.signIn(email);
  return Object.assign(st, {
    raw: (path: string, init: RequestInit) => s.app.request(path, { ...init, headers: { Authorization: `Bearer ${st.token}` } }),
    json: async (path: string) => (await (await st.get(path)).json()) as any,
  });
}

async function multipart(who: Student, path: string, field: string, files: { name: string; text: string }[]) {
  const form = new FormData();
  for (const f of files) form.append(field, new File([f.text], f.name));
  return (await who.raw(path, { method: "POST", body: form })).status;
}

const DECKS = [
  { name: "slides.pdf", text: "Potential outcomes intro\norder 1\nmore" },
  { name: "download (1).pdf", text: "Selection bias explained\norder 2\nmore" },
];

/** Ann has a course with two lectures, has sat the first lecture's check, and so needs its two videos. */
async function annNeedingVideos() {
  const s = makeServer();
  const ann = await student(s, "ann@nyu.edu");
  expect(await multipart(ann, "/api/courses", "syllabus", [{ name: "syllabus.pdf", text: "Syllabus of CS-UH 2219E" }])).toBe(200);
  await work(s);
  const courseId = (await ann.json("/api/courses/mine")).course.id as string;
  expect(await multipart(ann, `/api/courses/${courseId}/slides`, "files", DECKS)).toBe(200);
  await work(s, { kinds: ["deck_read", "placement"] });
  const { uploads } = await ann.json(`/api/courses/${courseId}/uploads`);
  const mine = await ann.json("/api/courses/mine");
  const order = [
    ...mine.course.lectures.map((l: any) => ({ at: l.position, entry: { lecture_n: l.n } })),
    ...uploads.filter((u: any) => u.can_place).map((u: any) => ({ at: u.suggested_position, entry: { upload_id: u.id } })),
  ]
    .sort((a, b) => a.at - b.at)
    .map((r) => r.entry);
  expect((await ann.post(`/api/courses/${courseId}/uploads/confirm`, { order })).status).toBe(200);
  await work(s, { kinds: ["deck"] });
  const first = `lecture-${(await ann.json("/api/courses/mine")).course.lectures[0].n}`;
  for (let guard = 0; guard < 40; guard++) {
    const v = await ann.rpc<{ current: { item: { id: string; correct_index: number } } | null; preparing: string | null }>("getSitting", first);
    if (v.preparing === "writing") {
      await work(s, { kinds: ["question"] });
      continue;
    }
    if (!v.current) break;
    await ann.rpc("answerSitting", first, v.current.item.id, v.current.item.correct_index, 1000);
  }
  await ann.rpc("finishSitting", first);
  const annId = (s.db.prepare("SELECT id FROM users WHERE email = 'ann@nyu.edu'").get() as { id: string }).id;
  return { s, ann, annId, courseId };
}

/** the fields of core's Video (packages/core/src/types.ts) */
const VIDEO_FIELDS = [
  "id", "ku_id", "title", "short_title", "topic_id", "lecture_n", "file_level", "duration_s", "video_url", "poster_url", "vtt_url", "segments",
  "checkpoint", "next_session_item_id", "prove_it_item_id", "sentence_frame", "claims", "tailoring", "transcript", "captions_burned_in",
  "source_slides", "prerequisite_titles", "review_status",
];

const claim = async (s: Server, kinds: string[] = ["video"]) =>
  ((await (await s.worker.post("/api/worker/claim", { kinds })).json()) as { job: { id: string; kind: string; payload: any; file_name: string | null } | null }).job;

describe("a video request becomes a job for the worker", () => {
  it("queues one job per waiting request, earliest lecture first, with what the pipeline needs", async () => {
    const { s, courseId } = await annNeedingVideos();
    const requests = s.courses.videoRequests(courseId);
    expect(requests.map((r) => r.status)).toEqual(["waiting", "waiting"]);

    const job = (await claim(s))!;
    expect(job.kind).toBe("video");
    const [first] = requests;
    expect(job.payload).toMatchObject({ ku: { id: first.ku_id }, level: first.level, lecture_n: first.lecture_n, course_name: expect.any(String), prereqs: [] });
    expect(job.payload.deck_id).toEqual(expect.any(String));
    expect(job.file_name).toBe("slides.pdf"); // the KU's deck, which the worker renders
    expect(s.courses.videoRequests(courseId).map((r) => r.status).sort()).toEqual(["making", "waiting"]);

    // a second claim gets the other request; nothing is queued twice
    expect((await claim(s))!.payload.ku.id).not.toBe(first.ku_id);
    expect(await claim(s)).toBeNull();
    expect(s.uploads.syncVideoJobs()).toBe(0);
  });

  it("tells the phone how many videos are still being made, so it keeps looking", async () => {
    const { s, ann } = await annNeedingVideos();
    const pending = async () => (await ann.json("/api/courses/mine")).course.videos_pending;
    expect(await pending()).toBe(2);
    await claim(s); // one worker holds a video and has not finished it
    expect(await pending()).toBe(2);
    await work(s, { kinds: ["video"] }); // another finishes the other
    expect(await pending()).toBe(1);
  });

  it("stores the files and the result, and marks the request ready", async () => {
    const { s, courseId } = await annNeedingVideos();
    const done = await work(s, { kinds: ["video"] });
    expect(done).toHaveLength(2);
    expect(s.courses.videoRequests(courseId).map((r) => r.status)).toEqual(["ready", "ready"]);
    const rows = s.db.prepare("SELECT ku_id, level, video_json, items_json FROM videos WHERE course_id = ?").all(courseId) as any[];
    expect(rows).toHaveLength(2);
    expect(JSON.parse(rows[0].items_json).map((i: any) => i.context).sort()).toEqual(["checkpoint", "next_session", "prove_it"]);
    expect(JSON.parse(rows[0].video_json)).not.toHaveProperty("video_url"); // the urls are the server's to make
    expect(s.uploads.videoFile(courseId, rows[0].ku_id, rows[0].level, "video.mp4")).not.toBeNull();
  });

  it("refuses a result with a missing file, another KU, or an item it does not carry", async () => {
    const { s, courseId } = await annNeedingVideos();
    const job = (await claim(s))!;
    const result = videoOf(job.payload);
    const post = async (r: unknown) => (await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result: r })).status;
    expect(await post(result)).toBe(400); // no file was sent
    for (const name of ["video.mp4", "poster.jpg", "captions.vtt"]) expect((await s.worker.put(`/api/worker/jobs/${job.id}/files/${name}`, new Uint8Array([1, 2, 3]))).status).toBe(200);
    expect(await post({ ...result, video: { ...result.video, ku_id: "ku-other" } })).toBe(400);
    expect(await post({ ...result, video: { ...result.video, file_level: result.video.file_level === 1 ? 2 : 1 } })).toBe(400);
    expect(await post({ ...result, items: result.items.slice(1) })).toBe(400); // the checkpoint's item is missing
    expect(await post(result)).toBe(200);
    expect(s.courses.videoRequests(courseId).filter((r) => r.status === "ready")).toHaveLength(1);
  });

  it("accepts what the Python worker's video job returns, and hands it on as a complete Video", async () => {
    // apps/server/tests/fixtures/video-result.json is written by tests/test_video_job.py from the real job code
    const { s, annId, courseId } = await annNeedingVideos();
    const job = (await claim(s))!;
    for (const name of ["video.mp4", "poster.jpg", "captions.vtt"]) await s.worker.put(`/api/worker/jobs/${job.id}/files/${name}`, new Uint8Array([1, 2, 3]));
    const text = readFileSync(new URL("./fixtures/video-result.json", import.meta.url), "utf8").replaceAll("ku-bst-insert", job.payload.ku.id);
    const result = JSON.parse(text);
    result.video.file_level = job.payload.level;
    result.video.topic_id = job.payload.topic_id;
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result })).status).toBe(200);

    const v = s.courses.fixturesFor(annId)!.videos.find((x) => x.ku_id === job.payload.ku.id)!;
    expect(Object.keys(v).sort()).toEqual([...VIDEO_FIELDS].sort()); // every field core's Video has, the three urls included
    expect(v.claims).toHaveLength(3);
    expect(v.checkpoint.item_id).toBe(`cp-${job.payload.ku.id}`);
    expect(v.transcript.map((r) => r.speaker)).toContain("Peter");
    expect(s.courses.fixturesFor(annId)!.items.filter((i) => i.ku_id === v.ku_id && ["checkpoint", "next_session", "prove_it"].includes(i.context))).toHaveLength(3);
    expect(courseId).toBeTruthy();
  });

  it("takes files only for a claimed video job, from the worker, with a known name", async () => {
    const { s } = await annNeedingVideos();
    const put = (id: string, name: string, token = true) =>
      s.app.request(`/api/worker/jobs/${id}/files/${name}`, { method: "PUT", headers: token ? { Authorization: "Bearer worker-test-token" } : {}, body: new Uint8Array([1]) });
    const job = (await claim(s))!;
    expect((await put(job.id, "video.mp4", false)).status).toBe(401);
    expect((await put(job.id, "notes.txt")).status).toBe(400);
    expect((await put(job.id, "../video.mp4")).status).toBeGreaterThanOrEqual(400);
    expect((await put(job.id, "video.mp4")).status).toBe(200);
    const unclaimed = s.db.prepare("SELECT id FROM jobs WHERE kind = 'video' AND status = 'queued'").get() as { id: string };
    expect((await put(unclaimed.id, "video.mp4")).status).toBe(409);
  });

  it("retries a failed video once, then shows it failed until the researcher retries it", async () => {
    const { s, courseId } = await annNeedingVideos();
    const [first] = s.courses.videoRequests(courseId);
    const status = () => s.courses.videoRequests(courseId).find((r) => r.ku_id === first.ku_id)!.status;
    let job = (await claim(s))!;
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "render crashed" })).status).toBe(200);
    expect(status()).toBe("waiting"); // queued again
    job = (await claim(s))!;
    expect(job.payload.ku.id).toBe(first.ku_id);
    await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "render crashed again" });
    expect(status()).toBe("failed");
    s.uploads.retry(job.id);
    expect(status()).toBe("waiting");
    expect((await claim(s))!.payload.ku.id).toBe(first.ku_id);
  });
});

describe("what a student is handed", () => {
  it("is the video at their level, with signed links and the questions it asks", async () => {
    const { s, annId, courseId } = await annNeedingVideos();
    await work(s, { kinds: ["video"] });
    const fx = s.courses.fixturesFor(annId)!;
    expect(fx.videos).toHaveLength(2);
    const v = fx.videos[0];
    expect(v.id).toBe(v.ku_id); // one video per KU, as the demo course has
    expect(v.video_url).toMatch(new RegExp(`^/api/media/${courseId}/${v.ku_id}/${v.file_level}/video\\.mp4\\?e=\\d+&s=[0-9a-f]+$`));
    expect(v.poster_url).toContain("/poster.jpg?e=");
    expect(fx.items.filter((i) => i.context === "checkpoint")).toHaveLength(2);
    expect(fx.course.kus.find((k) => k.id === v.ku_id)!.video_id).toBe(v.id);
    // the KU of the lecture not checked yet has no video
    expect(fx.course.kus.filter((k) => k.video_id)).toHaveLength(2);
  });

  it("is nothing for a student whose levels no video was made at", async () => {
    const { s, courseId } = await annNeedingVideos();
    await work(s, { kinds: ["video"] });
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus of CS-UH 2219E" }]);
    await work(s);
    const bobId = (s.db.prepare("SELECT id FROM users WHERE email = 'bob@nyu.edu'").get() as { id: string }).id;
    expect(s.courses.fixturesFor(bobId)!.videos).toEqual([]);
    // and one at another level than the video's gets nothing either (the video is made at the level their answers set)
    const rows = s.db.prepare("SELECT ku_id, level FROM videos WHERE course_id = ?").all(courseId) as { ku_id: string; level: number }[];
    const other = rows[0].level === 1 ? 2 : 1;
    s.db
      .prepare("INSERT INTO user_state (user_id, json, updated_at) VALUES (?, ?, 0) ON CONFLICT (user_id) DO UPDATE SET json = excluded.json")
      .run(bobId, JSON.stringify({ levels: { [rows[0].ku_id]: { level: other } }, made: {} }));
    expect(s.courses.fixturesFor(bobId)!.videos.map((v) => v.ku_id)).not.toContain(rows[0].ku_id);
    // once a video was made for them it is theirs whatever their level becomes later (D15)
    s.db
      .prepare("UPDATE user_state SET json = ? WHERE user_id = ?")
      .run(JSON.stringify({ levels: { [rows[0].ku_id]: { level: other } }, made: { [rows[0].ku_id]: rows[0].level } }), bobId);
    expect(s.courses.fixturesFor(bobId)!.videos.map((v) => v.ku_id)).toContain(rows[0].ku_id);
  });
});

describe("the student's app", () => {
  it("lists a made video in the playlist, plays it from the server, and records it as made for them", async () => {
    const { s, ann, annId, courseId } = await annNeedingVideos();
    expect((await ann.rpc<any>("getPlaylist")).cards).toEqual([]); // nothing is made yet
    await work(s, { kinds: ["video"] });
    const playlist = await ann.rpc<any>("getPlaylist");
    expect(playlist.cards.length).toBeGreaterThan(0);
    const card = playlist.cards[0];
    expect((await ann.rpc<any>("getPlaylist")).cards.map((c: any) => c.video_id)).toEqual(playlist.cards.map((c: any) => c.video_id)); // the order doesn't move on a second look
    expect(card.poster_url).toContain(`/api/media/${courseId}/`);

    const variant = await ann.rpc<any>("getVariant", card.video_id);
    expect(variant.video.video_url).toMatch(/^\/api\/media\/.+\/video\.mp4\?e=\d+&s=[0-9a-f]+$/);
    expect(variant.checkpoint_item.context).toBe("checkpoint");
    expect(variant.made_level).toBe(variant.video.file_level);
    expect((await s.app.request(variant.video.video_url)).status).toBe(200); // the link the phone gets plays

    // made for them once and never again: no new request, and the saved state says so
    const saved = JSON.parse((s.db.prepare("SELECT json FROM user_state WHERE user_id = ?").get(annId) as { json: string }).json);
    expect(saved.made[card.ku_id]).toBe(variant.video.file_level);
    expect(s.uploads.syncVideoJobs()).toBe(0);
  });
});

describe("the media route", () => {
  async function madeVideo() {
    const ctx = await annNeedingVideos();
    await work(ctx.s, { kinds: ["video"] });
    const [v] = ctx.s.courses.fixturesFor(ctx.annId)!.videos;
    return { ...ctx, v, onDisk: readFileSync(ctx.s.uploads.videoFile(ctx.courseId, v.ku_id, v.file_level, "video.mp4")!) };
  }

  it("serves the file behind a signed link, with no sign-in", async () => {
    const { s, v, onDisk } = await madeVideo();
    const res = await s.app.request(v.video_url);
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("video/mp4");
    expect(res.headers.get("Accept-Ranges")).toBe("bytes");
    expect(Buffer.from(await res.arrayBuffer())).toEqual(onDisk);
    const poster = await s.app.request(v.poster_url);
    expect(poster.headers.get("Content-Type")).toBe("image/jpeg");
    expect((await s.app.request(v.vtt_url)).headers.get("Content-Type")).toBe("text/vtt");
  });

  it("answers range requests with 206, as iOS's player needs", async () => {
    const { s, v, onDisk } = await madeVideo();
    const get = (range: string) => s.app.request(v.video_url, { headers: { Range: range } });
    const part = await get("bytes=3-8");
    expect(part.status).toBe(206);
    expect(part.headers.get("Content-Range")).toBe(`bytes 3-8/${onDisk.length}`);
    expect(Buffer.from(await part.arrayBuffer())).toEqual(onDisk.subarray(3, 9));
    const open = await get("bytes=5-");
    expect(Buffer.from(await open.arrayBuffer())).toEqual(onDisk.subarray(5));
    const tail = await get("bytes=-4");
    expect(Buffer.from(await tail.arrayBuffer())).toEqual(onDisk.subarray(onDisk.length - 4));
    expect((await get(`bytes=${onDisk.length + 10}-`)).status).toBe(416);
  });

  it("refuses a link without a valid signature, another video's signature, or an expired one", async () => {
    let now = 1_000_000;
    const clock = () => now;
    const s = makeServer({ clock });
    // a video made by hand: the route only needs the files and a signature
    const { courseId } = { courseId: "course-x" };
    const sig = (subject: string) => s.courses.mediaSigner(subject);
    expect(s.courses.mediaSigner("media:a/b/L1")).toMatch(/^e=\d+&s=[0-9a-f]+$/);
    const noFile = await s.app.request(`/api/media/${courseId}/ku-a/2/video.mp4?${sig(`media:${courseId}/ku-a/L2`)}`);
    expect(noFile.status).toBe(404); // signed, but there is no such file
    expect((await s.app.request(`/api/media/${courseId}/ku-a/2/video.mp4`)).status).toBe(403);
    expect((await s.app.request(`/api/media/${courseId}/ku-a/2/video.mp4?e=${now + 9999}&s=deadbeef`)).status).toBe(403);
    expect((await s.app.request(`/api/media/${courseId}/ku-a/2/video.mp4?${sig(`media:${courseId}/ku-b/L2`)}`)).status).toBe(403); // another video's
    expect((await s.app.request(`/api/media/${courseId}/ku-a/2/video.mp4?${sig(`media:${courseId}/ku-a/L3`)}`)).status).toBe(403); // another level's
    const old = sig(`media:${courseId}/ku-a/L2`);
    now += 13 * 60 * 60 * 1000;
    expect((await s.app.request(`/api/media/${courseId}/ku-a/2/video.mp4?${old}`)).status).toBe(403); // expired
  });
});

describe("a database from before the video job", () => {
  it("keeps its jobs and gains the video kind and table", () => {
    const path = mkdtempSync(tmpdir() + "/syllabyte-db-") + "/old.db";
    const old = new DatabaseSync(path);
    old.exec(`CREATE TABLE jobs (
      id TEXT PRIMARY KEY,
      kind TEXT NOT NULL CHECK (kind IN ('syllabus', 'deck_read', 'placement', 'deck', 'question', 'link_pass')),
      target_id TEXT NOT NULL, course_id TEXT, status TEXT NOT NULL CHECK (status IN ('queued', 'claimed', 'done', 'failed')),
      priority INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, claimed_at INTEGER, created_at INTEGER NOT NULL,
      finished_at INTEGER, error TEXT);
      INSERT INTO jobs (id, kind, target_id, status, created_at) VALUES ('j1', 'question', 'ku|basic', 'queued', 1);`);
    old.close();
    const db = openDb(path);
    expect(db.prepare("SELECT id, kind FROM jobs").all()).toEqual([{ id: "j1", kind: "question" }]);
    db.prepare("INSERT INTO jobs (id, kind, target_id, status, created_at) VALUES ('j2', 'video', 'ku|2', 'queued', 2)").run();
    expect(db.prepare("SELECT COUNT(*) AS n FROM videos").get()).toEqual({ n: 0 });
  });
});
