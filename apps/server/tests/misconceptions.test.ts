import { describe, expect, it } from "vitest";
import { work } from "./fakeWorker";
import { annNeedingVideos, multipart, student, type Server } from "./scenarios";

/** Misconception clips (engagement plan, "Misconception clips"): requested by a wrong + Certain answer, made once, shared. */

const claim = async (s: Server, kinds: string[]) =>
  ((await (await s.worker.post("/api/worker/claim", { kinds })).json()) as { job: { id: string; kind: string; payload: any } | null }).job;

/** Ann, with her videos made, answers the first video's checkpoint wrong with "Certain". */
async function annMistaken() {
  const ctx = await annNeedingVideos();
  await work(ctx.s, { kinds: ["video"] });
  const { s, ann, annId, courseId } = ctx;
  const card = (await ann.rpc<any>("getPlaylist")).cards[0];
  const variant = await ann.rpc<any>("getVariant", card.video_id);
  const item = variant.checkpoint_item;
  const wrong = (item.correct_index + 1) % item.options.length;
  const learning = { sessionId: "learning-ann", courseId };
  const res = await ann.rpc<any>("postCheckpointAnswer", { attemptId: "a-1", learning, videoId: card.video_id, choice: wrong, confidence: "certain", hintUsed: false, latencyMs: 900 });
  expect(res.correct).toBe(false);
  return { ...ctx, card, item, wrong, learning, key: `${item.id}|${wrong}`, s, ann, annId, courseId };
}

describe("a misconception clip", () => {
  it("is requested by a wrong + Certain answer, with the question as the student saw it", async () => {
    const { s, courseId, key, item, wrong, card } = await annMistaken();
    const row = s.db.prepare("SELECT ku_id, level, brief_json, status FROM misconception_requests WHERE course_id = ? AND clip_key = ?").get(courseId, key) as any;
    expect(row).toMatchObject({ ku_id: card.ku_id, status: "waiting" });
    expect(JSON.parse(row.brief_json)).toEqual({ stem: item.stem, options: item.options, correct_index: item.correct_index, chosen: wrong, explanation: item.explanation });
  });

  it("is made only by a worker that says it can, before other work, with the misconception in the payload", async () => {
    const { s, key, wrong, card } = await annMistaken();
    expect(await claim(s, ["video", "question"])).toBeNull(); // nothing else waiting, and this worker can't make clips
    const job = (await claim(s, ["misconception"]))!;
    expect(job.kind).toBe("misconception");
    expect(job.payload).toMatchObject({ clip_key: key, ku: { id: card.ku_id }, misconception: { chosen: wrong } });
    expect(job.payload.deck_id).toEqual(expect.any(String));
  });

  it("once made, is offered to the student with signed links that play, and its follow-up question works", async () => {
    const { s, ann, learning, key, courseId } = await annMistaken();
    expect(await ann.rpc("getMisconceptionClips", learning)).toEqual([]); // being made
    await work(s, { kinds: ["misconception"] });
    expect((s.db.prepare("SELECT status FROM misconception_requests WHERE course_id = ? AND clip_key = ?").get(courseId, key) as any).status).toBe("ready");
    const [ready] = await ann.rpc<any[]>("getMisconceptionClips", learning);
    expect(ready.clip.key).toBe(key);
    expect(ready.clip.video.video_url).toMatch(/^\/api\/media\/clips\/.+\/video\.mp4\?e=\d+&s=[0-9a-f]+$/);
    expect((await s.app.request(ready.clip.video.video_url)).status).toBe(200);
    expect((await s.app.request(ready.clip.video.video_url.replace(/s=[0-9a-f]+/, "s=00"))).status).toBe(403);

    const check = ready.clip.check_item;
    expect(check.id).toBe(ready.clip.video.checkpoint.item_id);
    expect(await ann.rpc<any>("answerMisconceptionCheck", learning, ready.request.id, check.correct_index)).toMatchObject({ correct: true });
    await ann.rpc("respondToMisconceptionClip", learning, ready.request.id, { offered: true, action: "watched" });
    expect(await ann.rpc("getMisconceptionClips", learning)).toEqual([]);
  });

  it("is made once: a classmate with the same mistake gets the same clip at once, with no new job", async () => {
    const { s, courseId, key, card, wrong } = await annMistaken();
    await work(s, { kinds: ["misconception"] });
    const bob = await student(s, "bob@nyu.edu");
    await multipart(bob, "/api/courses", "syllabus", [{ name: "s.pdf", text: "Syllabus of CS-UH 2219E" }]);
    await work(s);
    // Bob sat the same check; put him at Ann's level so he gets the same video, then make the same mistake
    const bobId = (s.db.prepare("SELECT id FROM users WHERE email = 'bob@nyu.edu'").get() as { id: string }).id;
    const ann = s.db.prepare("SELECT json FROM course_state WHERE course_id = ? AND user_id != ?").get(courseId, bobId) as { json: string };
    const annState = JSON.parse(ann.json);
    s.db.prepare("INSERT INTO course_state (user_id, course_id, json, updated_at) VALUES (?, ?, ?, 0) ON CONFLICT (user_id, course_id) DO UPDATE SET json = excluded.json")
      .run(bobId, courseId, JSON.stringify({ levels: annState.levels, made: annState.made }));
    const learning = { sessionId: "learning-bob", courseId };
    await bob.rpc("postCheckpointAnswer", { attemptId: "b-1", learning, videoId: card.video_id, choice: wrong, confidence: "certain", hintUsed: false, latencyMs: 900 });
    const [ready] = await bob.rpc<any[]>("getMisconceptionClips", learning);
    expect(ready.clip.key).toBe(key);
    expect(s.uploads.syncMisconceptionJobs()).toBe(0);
    expect(await claim(s, ["misconception"])).toBeNull();
  });

  it("is not requested for a forged answer: the right option, or a question the course doesn't have", async () => {
    const { s, annId, courseId, item } = await annMistaken();
    const state = { misconception_requests: [
      { key: `${item.id}|${item.correct_index}`, item_id: item.id, choice: item.correct_index, ku_id: "x", level: 1 },
      { key: "no-such-item|1", item_id: "no-such-item", choice: 1, ku_id: "x", level: 1 },
      { key: "../../etc|1", item_id: "../../etc", choice: 1, ku_id: "x", level: 1 },
    ] };
    s.courses.recordMisconceptionNeeds(annId, state as never);
    const keys = (s.db.prepare("SELECT clip_key FROM misconception_requests WHERE course_id = ?").all(courseId) as { clip_key: string }[]).map((r) => r.clip_key);
    expect(keys).toHaveLength(1); // only Ann's real one
  });

  it("goes back to waiting when the worker fails it, and is shown failed after the retries", async () => {
    const { s, courseId, key } = await annMistaken();
    const status = () => (s.db.prepare("SELECT status FROM misconception_requests WHERE course_id = ? AND clip_key = ?").get(courseId, key) as any).status;
    const job = (await claim(s, ["misconception"]))!;
    expect(status()).toBe("making");
    await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "render broke" });
    expect(status()).toBe("waiting");
    const again = (await claim(s, ["misconception"]))!;
    await s.worker.post(`/api/worker/jobs/${again.id}/fail`, { error: "render broke" });
    expect(status()).toBe("failed");
  });
});
