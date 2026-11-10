import { describe, expect, it } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Item } from "@syllabyte/core/types";
import { openDb } from "../src/db";
import { makeServer } from "./helpers";
import { questionBankOf, work, type Job } from "./fakeWorker";

type Sitting = { current: { item: Item } | null; preparing: string | null; answered: number; total: number };

async function readyCourse() {
  const s = makeServer();
  const ann = await s.signIn("ann@nyu.edu");
  const form = new FormData();
  form.append("syllabus", new File(["Shared algorithms syllabus"], "syllabus.pdf"));
  form.append("slides", new File(["Stacks\norder 1\nmore"], "stacks.pdf"));
  form.append("slides", new File(["Sorting\norder 2\nmore"], "sorting.pdf"));
  const response = await s.app.request("/api/courses", { method: "POST", headers: { Authorization: `Bearer ${ann.token}` }, body: form });
  expect(response.status).toBe(200);
  // Use the old worker kinds here: KUs exist, but the new background jobs have not run yet.
  await work(s);
  const mine = await (await ann.get("/api/courses/mine")).json() as { course: { id: string } };
  return { s, ann, courseId: mine.course.id };
}

async function claimBank(s: ReturnType<typeof makeServer>) {
  const response = await s.worker.post("/api/worker/claim", { kinds: ["question_bank", "question"] });
  const { job } = await response.json() as { job: Job };
  expect(job.kind).toBe("question_bank");
  return job;
}

describe("background pre-check banks", () => {
  it("prepares only the first lecture as its KUs arrive, then serves adaptive questions with no generation between answers", async () => {
    const { s, ann, courseId } = await readyCourse();
    const jobs = s.db.prepare("SELECT target_id FROM jobs WHERE kind = 'question_bank'").all() as { target_id: string }[];
    expect(jobs.map((j) => j.target_id).sort()).toEqual(["ku-stacks-a", "ku-stacks-b"]);
    const completed = await work(s, { kinds: ["question_bank", "question"] });
    expect(completed.map((j) => j.kind)).toEqual(["question_bank", "question_bank"]);
    expect(s.courses.questions(courseId)).toHaveLength(6);
    expect(s.courses.questions(courseId).every((q) => q.item.hint === null)).toBe(true);

    const first = await ann.rpc<Sitting>("getSitting", "lecture-1");
    expect(first.current?.item.tier).toBe("applied");
    expect(first.preparing).toBeNull();
    await ann.rpc("answerSitting", "lecture-1", first.current!.item.id, first.current!.item.correct_index, 4000);
    const second = await ann.rpc<Sitting>("getSitting", "lecture-1");
    expect(second.current).not.toBeNull();
    expect(second.current!.item.ku_id).not.toBe(first.current!.item.ku_id);
    expect(second.preparing).toBeNull();
    expect(await work(s, { kinds: ["question_bank", "question"] })).toEqual([]);

    const bob = await s.signIn("bob@nyu.edu");
    const form = new FormData();
    form.append("syllabus", new File(["Shared algorithms syllabus"], "copy.pdf"));
    await s.app.request("/api/courses", { method: "POST", headers: { Authorization: `Bearer ${bob.token}` }, body: form });
    await work(s, { kinds: ["syllabus"] });
    expect((await bob.rpc<Sitting>("getSitting", "lecture-1")).current!.item.id).toBe(first.current!.item.id);
    expect(s.courses.questions(courseId)).toHaveLength(6);
    expect(await work(s, { kinds: ["question_bank", "question"] })).toEqual([]);
  });

  it("promotes the waiting KU's bank and prevents a duplicate one-question job while that bank is running", async () => {
    const { s, ann, courseId } = await readyCourse();
    expect((await ann.rpc<Sitting>("getSitting", "lecture-1")).preparing).toBe("writing");
    const first = await claimBank(s);
    expect(first.payload.ku.id).toBe("ku-stacks-a");
    const second = await claimBank(s);
    expect(second.payload.ku.id).toBe("ku-stacks-b");
    expect((await (await s.worker.post("/api/worker/claim", { kinds: ["question_bank", "question"] })).json() as { job: Job | null }).job).toBeNull();
    expect((await (await s.worker.post("/api/worker/claim", { kinds: ["question"] })).json() as { job: Job | null }).job).toBeNull();
    expect((await s.worker.post(`/api/worker/jobs/${first.id}/result`, { result: questionBankOf(first.payload) })).status).toBe(200);
    expect((await ann.rpc<Sitting>("getSitting", "lecture-1")).current).not.toBeNull();
    expect(s.db.prepare("SELECT status FROM jobs WHERE course_id = ? AND kind = 'question'").get(courseId)).toEqual({ status: "done" });
  });

  it("warms a later lecture when its check is opened and deduplicates repeated requests", async () => {
    const { s, ann } = await readyCourse();
    await ann.rpc("getSitting", "lecture-2");
    await ann.rpc("getSitting", "lecture-2");
    const queued = s.db.prepare("SELECT target_id FROM jobs WHERE kind = 'question_bank'").all() as { target_id: string }[];
    expect(queued.map((j) => j.target_id).sort()).toEqual(["ku-sorting-a", "ku-sorting-b", "ku-stacks-a", "ku-stacks-b"]);
  });

  it("can adapt downward after Not sure using the prepared bank", async () => {
    const { s, ann } = await readyCourse();
    await work(s, { kinds: ["question_bank", "question"] });
    const first = await ann.rpc<Sitting>("getSitting", "lecture-1");
    await ann.rpc("answerSitting", "lecture-1", first.current!.item.id, "not_sure", 2000);
    const next = await ann.rpc<Sitting>("getSitting", "lecture-1");
    expect(next.current!.item.tier).toBe("basic");
    expect(next.preparing).toBeNull();
    expect(await work(s, { kinds: ["question_bank", "question"] })).toEqual([]);
  });

  it("publishes no part of a bank with unresolved review flags or invalid questions", async () => {
    const { s, courseId } = await readyCourse();
    const job = await claimBank(s);
    const result = questionBankOf(job.payload);
    const flags = [{ id: result.items[0].id, issue: "The stem teaches the answer." }];
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result: { ...result, flags } })).status).toBe(400);
    expect(s.courses.questions(courseId)).toEqual([]);
    const duplicate = questionBankOf(job.payload);
    duplicate.items[2].stem = duplicate.items[0].stem;
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result: duplicate })).status).toBe(400);
    expect(s.courses.questions(courseId)).toEqual([]);
    result.items[2].source_refs[0].slide_number = 999;
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result })).status).toBe(400);
    expect(s.courses.questions(courseId)).toEqual([]);
    result.items[2].source_refs[0].slide_number = 1;
    result.items[2].tier = "basic";
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result })).status).toBe(400);
    expect(s.courses.questions(courseId)).toEqual([]);
  });

  it("does not serve previously flagged questions, and exposes failed banks with a working retry", async () => {
    const { s, ann, courseId } = await readyCourse();
    await ann.rpc("getSitting", "lecture-1");
    const job = await claimBank(s);
    const bank = questionBankOf(job.payload);
    const old = { ...bank.items[1], id: "old-flagged-question" };
    s.courses.addQuestion(courseId, job.payload.deck_id, old, [{ issue: "Answer giveaway" }]);
    expect(s.courses.questions(courseId)).toEqual([]);
    await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "Review failed", user_message: "Review failed" });
    expect((await ann.rpc<Sitting>("getSitting", "lecture-1")).preparing).toBe("failed");
    expect((await ann.post("/api/questions/retry", { ku_id: job.payload.ku.id, tier: "applied" })).status).toBe(200);
    expect((await ann.rpc<Sitting>("getSitting", "lecture-1")).preparing).toBe("writing");
    await work(s, { kinds: ["question_bank", "question"] });
    const first = await ann.rpc<Sitting>("getSitting", "lecture-1");
    expect(first.current?.item.id).not.toBe(old.id);
    expect(first.current).not.toBeNull();
  });

  it("preserves case-sensitive symbols and multiline code in published questions", async () => {
    const { s, ann } = await readyCourse();
    const job = await claimBank(s);
    const bank = questionBankOf(job.payload);
    bank.items[1].stem = "In Python 3:\n```python\nX = 2\nx = 3\n```\nWhich name holds 2?";
    bank.items[1].options = ["X", "x", "y"];
    bank.items[1].correct_index = 0;
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result: bank })).status).toBe(200);
    const sitting = await ann.rpc<Sitting>("getSitting", "lecture-1");
    expect(sitting.current!.item.stem).toBe(bank.items[1].stem);
    expect(sitting.current!.item.options).toEqual(["X", "x", "y"]);
    expect(sitting.current!.item.correct_index).toBe(0);
  });

  it("migrates existing queued jobs to support question banks", () => {
    const path = join(mkdtempSync(join(tmpdir(), "syllabyte-banks-")), "db.sqlite");
    let db = openDb(path);
    const schema = (db.prepare("SELECT sql FROM sqlite_master WHERE name = 'jobs'").get() as { sql: string }).sql;
    db.exec("ALTER TABLE jobs RENAME TO previous_jobs; DROP INDEX jobs_queue;");
    db.exec(schema.replace(", 'question_bank'", ""));
    db.exec("INSERT INTO jobs (id, kind, target_id, status, created_at) VALUES ('old', 'question', 'ku|basic', 'queued', 1); DROP TABLE previous_jobs;");
    db.close();
    db = openDb(path);
    expect(db.prepare("SELECT kind, status FROM jobs WHERE id = 'old'").get()).toEqual({ kind: "question", status: "queued" });
    expect(() => db.exec("INSERT INTO jobs (id, kind, target_id, status, created_at) VALUES ('new', 'question_bank', 'ku', 'queued', 2)")).not.toThrow();
    db.close();
  });
});
