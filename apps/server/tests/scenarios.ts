import { expect } from "vitest";
import { work } from "./fakeWorker";
import { makeServer } from "./helpers";

/** Scenarios the server tests share: a student with a course, its decks and a finished check. */

export type Server = ReturnType<typeof makeServer>;
export type Student = Awaited<ReturnType<typeof student>>;

export async function student(s: Server, email: string) {
  const st = await s.signIn(email);
  return Object.assign(st, {
    raw: (path: string, init: RequestInit) => s.app.request(path, { ...init, headers: { Authorization: `Bearer ${st.token}` } }),
    json: async (path: string) => (await (await st.get(path)).json()) as any,
  });
}

export async function multipart(who: Student, path: string, field: string, files: { name: string; text: string }[]) {
  const form = new FormData();
  for (const f of files) form.append(field, new File([f.text], f.name));
  return (await who.raw(path, { method: "POST", body: form })).status;
}

export const DECKS = [
  { name: "slides.pdf", text: "Potential outcomes intro\norder 1\nmore" },
  { name: "download (1).pdf", text: "Selection bias explained\norder 2\nmore" },
];

/** Ann has a course with two lectures, has sat the first lecture's check, and so needs its two videos. */
export async function annNeedingVideos(opts: Parameters<typeof makeServer>[0] = {}) {
  const s = makeServer(opts);
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

