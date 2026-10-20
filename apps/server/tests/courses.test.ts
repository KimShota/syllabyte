import { describe, expect, it } from "vitest";
import type { DeckResult } from "@syllabyte/core/logic/assemble";
import type { Item } from "@syllabyte/core/types";
import type { Courses } from "../src/courses";
import type { Db } from "../src/db";
import { makeServer } from "./helpers";

interface CourseMap {
  lectures: { lecture: { n: number; title: string }; rows: { ku: { id: string } }[] }[];
}
const kuIds = (m: CourseMap) => m.lectures.flatMap((l) => l.rows.map((r) => r.ku.id));

interface Sitting {
  current: { item: { id: string; correct_index: number } } | null;
}

const bank = (kuId: string, n: number): Item[] =>
  Array.from({ length: n }, (_, i) => ({
    id: `as-${kuId}-${i}`, ku_id: kuId, topic_id: "", context: "assessment" as const, stem: `Q ${kuId} ${i}`, options: ["a", "b", "c"],
    correct_index: 1, allows_not_sure: true, explanation: "", hint: null, difficulty_prior: i - n / 2, discrimination: 1,
    tier: "basic" as const, source_refs: [],
  }));

const result = (kus: string[]): DeckResult => ({
  kus: kus.map((id) => ({ id, title: id, short_title: id, summary: "", bloom_level: "understand" as const, prerequisites: [], source_refs: [] })),
  items: kus.flatMap((k) => bank(k, 4)),
});

const userId = (db: Db, email: string) => (db.prepare("SELECT id FROM users WHERE email = ?").get(email) as { id: string }).id;

/** A course with lectures 1 and 2 and one processed deck in lecture 1, joined by `members`. */
function seedCourse(db: Db, courses: Courses, members: string[]) {
  const creator = userId(db, members[0]);
  const id = courses.create({ syllabusKey: "k1", code: "CS-1", name: "Uploaded course", syllabusText: "", syllabusPath: "x", createdBy: creator, status: "ready" });
  courses.setLectures(id, [{ n: 1, title: "First", week: 1 }, { n: 2, title: "Second", week: 2 }], "syllabus");
  const lecture1 = courses.lectures(id)[0].id;
  db.prepare(
    "INSERT INTO decks (id, course_id, lecture_id, content_key, file_name, pdf_path, parse_json, status, first_user_id, created_at) VALUES ('d1', ?, ?, 'c1', 'one.pdf', 'p', '{}', 'processing', ?, 0)",
  ).run(id, lecture1, creator);
  for (const m of members) courses.addMember(id, userId(db, m));
  return id;
}

describe("a student's own course", () => {
  it("runs the student's requests against their course, and others' against the demo course", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const bob = await s.signIn("bob@nyu.edu");
    seedCourse(s.db, s.courses, ["ann@nyu.edu"]);
    s.courses.setDeckResult("d1", result(["ku-x", "ku-y"]));

    const annMap = await ann.rpc<CourseMap>("getCourseMap");
    // every lecture, the one still waiting for slides too
    expect(annMap.lectures.map((l) => l.lecture.title)).toEqual(["First", "Second"]);
    expect(kuIds(annMap)).toEqual(["ku-x", "ku-y"]);
    const annSitting = await ann.rpc<Sitting>("getSitting", "week0");
    expect(annSitting.current!.item.id).toMatch(/^as-ku-[xy]-/);

    const bobSitting = await bob.rpc<Sitting>("getSitting", "week0");
    expect(bobSitting.current!.item.id).not.toMatch(/^as-ku-[xy]-/);
  });

  it("gives every member of a shared course the same KUs and questions", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const cat = await s.signIn("cat@nyu.edu");
    seedCourse(s.db, s.courses, ["ann@nyu.edu", "cat@nyu.edu"]);
    s.courses.setDeckResult("d1", result(["ku-x"]));
    expect(kuIds(await ann.rpc<CourseMap>("getCourseMap"))).toEqual(["ku-x"]);
    expect(kuIds(await cat.rpc<CourseMap>("getCourseMap"))).toEqual(["ku-x"]);
    const a = await ann.rpc<Sitting>("getSitting", "week0");
    const c = await cat.rpc<Sitting>("getSitting", "week0");
    expect(c.current!.item.id).toBe(a.current!.item.id);
  });

  it("sees a newly processed deck on the next request", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const id = seedCourse(s.db, s.courses, ["ann@nyu.edu"]);
    s.courses.setDeckResult("d1", result(["ku-x"]));
    expect(kuIds(await ann.rpc<CourseMap>("getCourseMap"))).toEqual(["ku-x"]);

    const lecture2 = s.courses.lectures(id)[1].id;
    s.db.prepare(
      "INSERT INTO decks (id, course_id, lecture_id, content_key, file_name, pdf_path, parse_json, status, first_user_id, created_at) VALUES ('d2', ?, ?, 'c2', 'two.pdf', 'p', '{}', 'processing', ?, 1)",
    ).run(id, lecture2, userId(s.db, "ann@nyu.edu"));
    s.courses.setDeckResult("d2", result(["ku-z"]));
    expect(kuIds(await ann.rpc<CourseMap>("getCourseMap"))).toEqual(["ku-x", "ku-z"]);
  });

  it("adds prerequisite links to the assembled course", async () => {
    const s = makeServer();
    await s.signIn("ann@nyu.edu");
    const id = seedCourse(s.db, s.courses, ["ann@nyu.edu"]);
    s.courses.setDeckResult("d1", result(["ku-x", "ku-y"]));
    s.courses.addLinks(id, [{ ku_id: "ku-y", prereq_id: "ku-x" }]);
    expect(s.courses.fixtures(id).course.kus.find((k) => k.id === "ku-y")!.prerequisites).toEqual(["ku-x"]);
  });

  it("refuses to replace the lecture list once a deck is placed", async () => {
    const s = makeServer();
    await s.signIn("ann@nyu.edu");
    const id = seedCourse(s.db, s.courses, ["ann@nyu.edu"]);
    expect(() => s.courses.setLectures(id, [{ n: 1, title: "Other", week: null }], "syllabus")).toThrow(/already placed/);
  });
});
