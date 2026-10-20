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
  items: [],
});

/** Questions as the worker saves them (V4): one per KU at each tier. */
function saveQuestions(courses: Courses, courseId: string, deckId: string, kus: string[]) {
  for (const k of kus) for (const q of bank(k, 3)) courses.addQuestion(courseId, deckId, { ...q, tier: (["basic", "applied", "advanced"] as const)[Number(q.id.at(-1))], difficulty_prior: Number(q.id.at(-1)) - 1 }, []);
}

const userId = (db: Db, email: string) => (db.prepare("SELECT id FROM users WHERE email = ?").get(email) as { id: string }).id;

/** A course with lectures 1 and 2 and one deck in lecture 1, joined by `members`. */
function seedCourse(db: Db, courses: Courses, members: string[]) {
  const creator = userId(db, members[0]);
  const id = courses.create({ syllabusKey: "k1", code: "CS-1", name: "Uploaded course", syllabusText: "", syllabusPath: "x", createdBy: creator, status: "ready" });
  courses.addLecture(id, { title: "First" });
  courses.addLecture(id, { title: "Second" });
  const lecture1 = courses.lectures(id)[0].id;
  db.prepare(
    "INSERT INTO decks (id, course_id, lecture_id, content_key, file_name, file_path, parse_json, status, first_user_id, created_at) VALUES ('d1', ?, ?, 'c1', 'one.pdf', 'p', '{}', 'processing', ?, 0)",
  ).run(id, lecture1, creator);
  for (const m of members) courses.addMember(id, userId(db, m));
  return id;
}

describe("a student's own course", () => {
  it("runs the student's requests against their course, and others' against the demo course", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const bob = await s.signIn("bob@nyu.edu");
    const id = seedCourse(s.db, s.courses, ["ann@nyu.edu"]);
    s.courses.setDeckResult("d1", result(["ku-x", "ku-y"]));
    saveQuestions(s.courses, id, "d1", ["ku-x", "ku-y"]);

    const annMap = await ann.rpc<CourseMap>("getCourseMap");
    expect(annMap.lectures.map((l) => l.lecture.title)).toEqual(["First", "Second"]);
    expect(kuIds(annMap)).toEqual(["ku-x", "ku-y"]);
    const annSitting = await ann.rpc<Sitting>("getSitting", "lecture-1");
    expect(annSitting.current!.item.id).toMatch(/^as-ku-[xy]-/);

    const bobSitting = await bob.rpc<Sitting>("getSitting", "week0");
    expect(bobSitting.current!.item.id).not.toMatch(/^as-ku-[xy]-/);
  });

  it("gives every member of a shared course the same KUs and questions", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    const cat = await s.signIn("cat@nyu.edu");
    const id = seedCourse(s.db, s.courses, ["ann@nyu.edu", "cat@nyu.edu"]);
    s.courses.setDeckResult("d1", result(["ku-x"]));
    saveQuestions(s.courses, id, "d1", ["ku-x"]);
    expect(kuIds(await ann.rpc<CourseMap>("getCourseMap"))).toEqual(["ku-x"]);
    expect(kuIds(await cat.rpc<CourseMap>("getCourseMap"))).toEqual(["ku-x"]);
    const a = await ann.rpc<Sitting>("getSitting", "lecture-1");
    const c = await cat.rpc<Sitting>("getSitting", "lecture-1");
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
      "INSERT INTO decks (id, course_id, lecture_id, content_key, file_name, file_path, parse_json, status, first_user_id, created_at) VALUES ('d2', ?, ?, 'c2', 'two.pdf', 'p', '{}', 'processing', ?, 1)",
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

  it("orders lectures by position and gives a new lecture the next number", async () => {
    const s = makeServer();
    await s.signIn("ann@nyu.edu");
    const id = seedCourse(s.db, s.courses, ["ann@nyu.edu"]);
    const between = s.courses.addLecture(id, { title: "Between", position: 1.5 });
    expect(between.n).toBe(3);
    expect(s.courses.lectures(id).map((l) => [l.n, l.title])).toEqual([[1, "First"], [3, "Between"], [2, "Second"]]);
    expect(s.courses.fixtures(id).course.lectures.map((l) => [l.n, l.position])).toEqual([[1, 1], [3, 2], [2, 3]]);
  });
});
