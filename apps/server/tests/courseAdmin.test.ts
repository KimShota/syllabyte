import { describe, expect, it } from "vitest";
import { courseDetail, mergeCourses, moveDeck, moveStudent, renameLecture } from "../src/courseAdmin";
import { work } from "./fakeWorker";
import { makeServer } from "./helpers";

type Server = ReturnType<typeof makeServer>;

async function upload(s: Server, token: string, path: string, field: string, files: { name: string; text: string }[]) {
  const form = new FormData();
  for (const f of files) form.append(field, new File([f.text], f.name));
  return s.app.request(path, { method: "POST", body: form, headers: { Authorization: `Bearer ${token}` } });
}

async function withCourse(s: Server, email: string, syllabus: string) {
  const st = await s.signIn(email);
  await upload(s, st.token, "/api/courses", "syllabus", [{ name: "s.pdf", text: syllabus }]);
  await work(s);
  const mine = (await (await st.get("/api/courses/mine")).json()) as any;
  return { st, courseId: mine.course.id as string };
}

describe("the researcher's fixes", () => {
  it("renames a lecture and moves a deck to another lecture", async () => {
    const s = makeServer();
    const { st, courseId } = await withCourse(s, "ann@nyu.edu", "Syllabus A");
    await st.post(`/api/courses/${courseId}/lectures`, {});
    await upload(s, st.token, `/api/courses/${courseId}/slides`, "files", [{ name: "lecture1.pdf", text: "Potential outcomes intro" }]);
    await work(s);
    const [u] = ((await (await st.get(`/api/courses/${courseId}/uploads`)).json()) as any).uploads;
    await st.post(`/api/courses/${courseId}/uploads/confirm`, { choices: [{ upload_id: u.id, lecture_n: 1 }] });
    await work(s);

    renameLecture(s.courses, courseId, 2, "Bias");
    moveDeck(s.db, s.courses, u.deck.id, 2);
    const d = courseDetail(s.db, s.courses, courseId);
    expect(d.lectures.map((l) => [l.n, l.title, l.decks.length])).toEqual([
      [1, "Potential outcomes", 0],
      [2, "Bias", 1],
      [3, "Randomization", 0],
    ]);
    expect(s.courses.fixtures(courseId).course.kus.every((k) => k.lecture_n === 2)).toBe(true);
  });

  it("merges a course split off by a slightly different syllabus, and later copies of it join too", async () => {
    const s = makeServer();
    const a = await withCourse(s, "ann@nyu.edu", "Syllabus A");
    const b = await withCourse(s, "bob@nyu.edu", "Syllabus A (last year's copy)");
    expect(b.courseId).not.toBe(a.courseId);

    mergeCourses(s.db, s.courses, b.courseId, a.courseId);
    expect(((await (await b.st.get("/api/courses/mine")).json()) as any).course.id).toBe(a.courseId);
    const cat = await withCourse(s, "cat@nyu.edu", "Syllabus A (last year's copy)");
    expect(cat.courseId).toBe(a.courseId);
  });

  it("moves a student only before they have answered anything", async () => {
    const s = makeServer();
    const a = await withCourse(s, "ann@nyu.edu", "Syllabus A");
    const b = await withCourse(s, "bob@nyu.edu", "Syllabus B");
    moveStudent(s.db, s.courses, "bob@nyu.edu", a.courseId);
    expect(s.courses.courseOf((s.db.prepare("SELECT id FROM users WHERE email = 'bob@nyu.edu'").get() as { id: string }).id)).toBe(a.courseId);

    // Ann answers a question in her course, then can't be moved
    await a.st.post(`/api/courses/${a.courseId}/lectures`, {});
    await upload(s, a.st.token, `/api/courses/${a.courseId}/slides`, "files", [{ name: "lecture1.pdf", text: "Potential outcomes intro" }]);
    await work(s);
    const [u] = ((await (await a.st.get(`/api/courses/${a.courseId}/uploads`)).json()) as any).uploads;
    await a.st.post(`/api/courses/${a.courseId}/uploads/confirm`, { choices: [{ upload_id: u.id, lecture_n: 1 }] });
    await work(s);
    const sitting = await a.st.rpc<{ current: { item: { id: string } } }>("getSitting", "week0");
    await a.st.rpc("answerSitting", "week0", sitting.current.item.id, 0, 1000);
    expect(() => moveStudent(s.db, s.courses, "ann@nyu.edu", b.courseId)).toThrow(/already answered/);
  });

  it("refuses to merge a course that already has slides placed", async () => {
    const s = makeServer();
    const a = await withCourse(s, "ann@nyu.edu", "Syllabus A");
    const b = await withCourse(s, "bob@nyu.edu", "Syllabus B");
    await b.st.post(`/api/courses/${b.courseId}/lectures`, {});
    await upload(s, b.st.token, `/api/courses/${b.courseId}/slides`, "files", [{ name: "lecture1.pdf", text: "x" }]);
    await work(s);
    const [u] = ((await (await b.st.get(`/api/courses/${b.courseId}/uploads`)).json()) as any).uploads;
    await b.st.post(`/api/courses/${b.courseId}/uploads/confirm`, { choices: [{ upload_id: u.id, lecture_n: 1 }] });
    expect(() => mergeCourses(s.db, s.courses, b.courseId, a.courseId)).toThrow(/slides placed/);
  });
});
