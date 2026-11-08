import { describe, expect, it } from "vitest";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AnalyzerMaterial } from "@syllabyte/core/api/types";
import { openDb } from "../src/db";
import { makeServer } from "./helpers";
import { work } from "./fakeWorker";

const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
const materials = async (who: Awaited<ReturnType<ReturnType<typeof makeServer>["signIn"]>>) =>
  ((await (await who.get("/api/courses/materials")).json()) as { materials: AnalyzerMaterial[] }).materials;

describe("real uploaded page previews", () => {
  it("shows only the owner's files before a course exists, deduplicates jobs and protects preview images", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const bob = await s.signIn("bob@nyu.edu");
    const form = new FormData();
    form.append("syllabus", new File(["COS 226 syllabus"], "syllabus.pdf"));
    form.append("slides", new File(["Stacks and queues"], "stacks.pdf"));
    expect((await s.app.request("/api/courses", { method: "POST", headers: { Authorization: `Bearer ${ann.token}` }, body: form })).status).toBe(200);
    const files = await materials(ann);
    expect(files.map((f) => [f.file_name, f.kind, f.state, f.preview_state])).toEqual([
      ["syllabus.pdf", "syllabus", "reading", "preparing"], ["stacks.pdf", "slides", "queued", "preparing"],
    ]);
    expect(await materials(bob)).toEqual([]);
    expect((await s.app.request("/api/courses/materials")).status).toBe(401);
    await materials(ann);
    expect(s.db.prepare("SELECT COUNT(*) AS n FROM jobs WHERE kind = 'preview'").get()).toEqual({ n: 2 });
    // Old workers send no kinds: they may read the syllabus but must never be given an unknown preview job.
    const { job: legacy } = await (await s.worker.post("/api/worker/claim", {})).json() as { job: { kind: string } };
    expect(legacy.kind).toBe("syllabus");

    const { job } = await (await s.worker.post("/api/worker/claim", { kinds: ["preview"] })).json() as { job: { id: string; payload: { file_id: string } } };
    expect(await (await s.worker.get(`/api/worker/jobs/${job.id}/file`)).text()).toBe("COS 226 syllabus");
    expect((await s.worker.put(`/api/worker/jobs/${job.id}/pages/0`, jpeg)).status).toBe(400);
    expect((await s.worker.put(`/api/worker/jobs/${job.id}/pages/1`, new TextEncoder().encode("bad"))).status).toBe(400);
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/preview`, { result: { unit: "page", pages: [{ n: 1, text: "Syllabus", image: true }] } })).status).toBe(400);
    expect((await s.worker.put(`/api/worker/jobs/${job.id}/pages/1`, jpeg)).status).toBe(200);
    expect((await s.worker.post(`/api/worker/jobs/${job.id}/preview`, { result: { unit: "page", pages: [{ n: 1, text: "COS 226", image: true }] } })).status).toBe(200);
    const [file] = await materials(ann);
    expect(file.preview_state).toBe("ready");
    expect(file.state).toBe("reading"); // A ready preview is not completed AI processing.
    const url = file.pages[0].image_url!;
    const image = await s.app.request(url);
    expect(image.status).toBe(200);
    expect(image.headers.get("Content-Type")).toBe("image/jpeg");
    expect((await s.app.request(url.split("?")[0])).status).toBe(403);
    expect((await s.app.request(url.replace(file.id, files[1].id))).status).toBe(403);
    expect((await s.worker.put(`/api/worker/jobs/${job.id}/pages/2`, jpeg)).status).toBe(409);
  });

  it("keeps bundled file IDs after course creation and isolates preview failures from ingestion", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const form = new FormData();
    form.append("syllabus", new File(["Algorithms syllabus"], "syllabus.pdf"));
    form.append("slides", new File(["Stacks and queues\norder 1\nmore"], "stacks.pdf"));
    await s.app.request("/api/courses", { method: "POST", headers: { Authorization: `Bearer ${ann.token}` }, body: form });
    const before = await materials(ann);
    const { job } = await (await s.worker.post("/api/worker/claim", { kinds: ["preview"] })).json() as { job: { id: string } };
    await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "Could not render", user_message: "Preview unavailable" });
    expect((await materials(ann))[0].preview_state).toBe("failed");
    expect((await materials(ann))[0].state).toBe("reading");
    await work(s, { kinds: ["syllabus", "deck_read", "placement", "deck"] });
    const after = await materials(ann);
    expect(after.map((f) => f.id)).toEqual(before.map((f) => f.id));
    expect(after.every((f) => f.state === "ready")).toBe(true);
    const next = new FormData();
    next.append("syllabus", new File(["A new physics course"], "physics.pdf"));
    await s.app.request("/api/courses", { method: "POST", headers: { Authorization: `Bearer ${ann.token}` }, body: next });
    expect((await materials(ann)).map((f) => f.file_name)).toEqual(["physics.pdf"]);
  });

  it("migrates the jobs constraint while preserving queued work", () => {
    const path = join(mkdtempSync(join(tmpdir(), "syllabyte-preview-migration-")), "test.db");
    let db = openDb(path);
    const schema = (db.prepare("SELECT sql FROM sqlite_master WHERE name = 'jobs'").get() as { sql: string }).sql;
    db.exec("ALTER TABLE jobs RENAME TO previous_jobs; DROP INDEX jobs_queue;");
    db.exec(schema.replace(", 'preview'", ""));
    db.exec("INSERT INTO jobs (id, kind, target_id, status, created_at) VALUES ('old-job', 'syllabus', 'old-file', 'queued', 1); DROP TABLE previous_jobs;");
    db.close();
    db = openDb(path);
    expect(db.prepare("SELECT kind, status FROM jobs WHERE id = 'old-job'").get()).toEqual({ kind: "syllabus", status: "queued" });
    expect(() => db.exec("INSERT INTO jobs (id, kind, target_id, status, created_at) VALUES ('preview-job', 'preview', 'file', 'queued', 2)")).not.toThrow();
    db.close();
  });
});
