import { describe, expect, it } from "vitest";
import { courseDetail, mergeCourses, moveLecture, moveStudent, renameLecture } from "../src/courseAdmin";
import { work } from "./fakeWorker";
import { makeServer } from "./helpers";

type Server = ReturnType<typeof makeServer>;

async function upload(s: Server, token: string, path: string, field: string, files: { name: string; text: string }[]) {
  const form = new FormData();
  for (const f of files) form.append(field, new File([f.text], f.name));
  return s.app.request(path, { method: "POST", body: form, headers: { Authorization: `Bearer ${token}` } });
}

/** Uploads slide files and confirms them where the placement call put them. */
async function addSlides(s: Server, st: { token: string; get: (p: string) => Response | Promise<Response>; post: (p: string, b: unknown) => Response | Promise<Response> }, courseId: string, files: { name: string; text: string }[]) {
  await upload(s, st.token, `/api/courses/${courseId}/slides`, "files", files);
  await work(s, { kinds: ["deck_read", "placement"] });
  const mine = (await (await st.get("/api/courses/mine")).json()) as any;
  const { uploads } = (await (await st.get(`/api/courses/${courseId}/uploads`)).json()) as any;
  const order = [
    ...mine.course.lectures.map((l: any) => ({ at: l.position, e: { lecture_n: l.n } })),
    ...uploads.filter((u: any) => u.can_place).map((u: any) => ({ at: u.suggested_position, e: { upload_id: u.id } })),
  ].sort((a, b) => a.at - b.at).map((r) => r.e);
  await st.post(`/api/courses/${courseId}/uploads/confirm`, { order });
  await work(s);
}

async function withCourse(s: Server, email: string, syllabus: string) {
  const st = await s.signIn(email);
  await upload(s, st.token, "/api/courses", "syllabus", [{ name: "s.pdf", text: syllabus }]);
  await work(s);
  const mine = (await (await st.get("/api/courses/mine")).json()) as any;
  return { st, courseId: mine.course.id as string };
}

describe("the researcher's fixes", () => {
  it("renames a lecture and moves it in the teaching order, keeping its number", async () => {
    const s = makeServer();
    const { st, courseId } = await withCourse(s, "ann@nyu.edu", "Syllabus A");
    await addSlides(s, st, courseId, [
      { name: "a.pdf", text: "Potential outcomes intro\norder 1" },
      { name: "b.pdf", text: "Selection bias\norder 2" },
      { name: "c.pdf", text: "Randomized trials\norder 3" },
    ]);
    renameLecture(s.courses, courseId, 2, "Bias");
    moveLecture(s.courses, s.db, courseId, 3, 0);
    const d = courseDetail(s.db, s.courses, courseId);
    expect(d.lectures.map((l) => [l.position, l.n, l.title])).toEqual([
      [1, 3, "Randomized trials"],
      [2, 1, "Potential outcomes intro"],
      [3, 2, "Bias"],
    ]);
    moveLecture(s.courses, s.db, courseId, 3, 2);
    expect(courseDetail(s.db, s.courses, courseId).lectures.map((l) => l.n)).toEqual([1, 2, 3]);
    expect(() => moveLecture(s.courses, s.db, courseId, 9, 0)).toThrow(/no lecture 9/);
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
    await addSlides(s, a.st, a.courseId, [{ name: "lecture1.pdf", text: "Potential outcomes intro" }]);
    await a.st.rpc("getSitting", "lecture-1");
    await work(s);
    const sitting = await a.st.rpc<{ current: { item: { id: string } } }>("getSitting", "lecture-1");
    await a.st.rpc("answerSitting", "lecture-1", sitting.current.item.id, 0, 1000);
    expect(() => moveStudent(s.db, s.courses, "ann@nyu.edu", b.courseId)).toThrow(/already answered/);
  });

  it("refuses to merge a course that already has slides placed", async () => {
    const s = makeServer();
    const a = await withCourse(s, "ann@nyu.edu", "Syllabus A");
    const b = await withCourse(s, "bob@nyu.edu", "Syllabus B");
    await addSlides(s, b.st, b.courseId, [{ name: "lecture1.pdf", text: "x" }]);
    expect(() => mergeCourses(s.db, s.courses, b.courseId, a.courseId)).toThrow(/slides placed/);
  });
});
