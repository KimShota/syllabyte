import { describe, expect, it } from "vitest";
import { FIX, setFixtures } from "@syllabyte/core/fixtures";
import { track } from "@syllabyte/core/events";
import { freshState, getState, replaceState } from "@syllabyte/core/store";
import { openDb } from "../src/db";
import { moveStudent, mergeCourses } from "../src/courseAdmin";
import { trackClientEvents } from "../src/runner";
import { PROFILE_KEYS, NO_COURSE, StateStore, migrateStates, splitState } from "../src/state";
import { work } from "./fakeWorker";
import { makeServer } from "./helpers";
import { annNeedingVideos, student, type Server, type Student } from "./scenarios";

/** Several courses per student (the migration, the active course, state kept per course). */

const OTHER = "Syllabus of ANOTHER COURSE";
const SAME = "Syllabus of CS-UH 2219E"; // the one annNeedingVideos uploads

async function addSyllabus(who: Student, text: string) {
  const form = new FormData();
  form.append("syllabus", new File([text], "syllabus.pdf"));
  const res = await who.raw("/api/courses", { method: "POST", body: form });
  return { status: res.status, body: (await res.json()) as any };
}
const idOf = (s: Server, email: string) => (s.db.prepare("SELECT id FROM users WHERE email = ?").get(email) as { id: string }).id;
const courses = async (who: Student) => ((await who.json("/api/courses")) as { courses: { id: string; active: boolean; progress: number; lectures: number }[] }).courses;

describe("saved state, in two layers", () => {
  it("splits a whole state into a profile and a course document and joins them again exactly", () => {
    const state = freshState();
    const { profile, course } = splitState(state);
    expect(Object.keys(profile).sort()).toEqual([...PROFILE_KEYS].sort());
    expect(Object.keys(course).some((k) => (PROFILE_KEYS as readonly string[]).includes(k))).toBe(false);
    expect({ ...course, ...profile }).toEqual(state);
  });

  it("keeps what is the student's (consent, questionnaires, events) out of the course", () => {
    const { course } = splitState(freshState());
    for (const k of ["consent", "study", "events", "settings", "participant_code", "condition"]) expect(course).not.toHaveProperty(k);
    for (const k of ["levels", "made", "responses", "playlist", "watched", "sittings"]) expect(course).toHaveProperty(k);
  });

  it("migrates a database that kept one document per student", () => {
    const db = openDb(":memory:");
    const state = { ...freshState(), consent: "research" as const, participant_code: "P-1", levels: { "ku-a": { level: 2 } }, responses: [{ id: 1 }] };
    db.prepare("INSERT INTO users (id, email, participant_code, created_at) VALUES ('u1', 'a@nyu.edu', 'P-1', 0), ('u2', 'b@nyu.edu', 'P-2', 0)").run();
    db.prepare("INSERT INTO courses (id, syllabus_key, code, name, syllabus_text, syllabus_path, status, created_by, created_at) VALUES ('c1', 'k', 'C', 'C', '', '', 'ready', 'u1', 0)").run();
    db.prepare("INSERT INTO course_members (course_id, user_id, joined_at) VALUES ('c1', 'u1', 1)").run();
    db.prepare("INSERT INTO user_state (user_id, json, updated_at) VALUES ('u1', ?, 5), ('u2', ?, 6)").run(JSON.stringify(state), JSON.stringify(freshState()));
    migrateStates(db);
    const store = new StateStore(db);
    expect(store.profile("u1")).toMatchObject({ consent: "research", participant_code: "P-1" });
    expect(store.course("u1", "c1")).toMatchObject({ levels: { "ku-a": { level: 2 } }, responses: [{ id: 1 }] });
    expect(store.course("u1", "c1")).not.toHaveProperty("consent");
    // a student with no course had the demo course
    expect(store.course("u2", NO_COURSE)).not.toBeNull();
    // the old rows stay as a backup, and running it again changes nothing
    expect((db.prepare("SELECT COUNT(*) AS n FROM user_state").get() as { n: number }).n).toBe(2);
    db.prepare("UPDATE course_state SET json = ? WHERE user_id = 'u1'").run(JSON.stringify({ levels: { "ku-z": { level: 3 } } }));
    migrateStates(db);
    expect(store.course("u1", "c1")).toEqual({ levels: { "ku-z": { level: 3 } } });
  });
});

describe("adding a course", () => {
  it("makes the new course the one the student is in, keeps the first, and tells the phone while it is read", async () => {
    const { s, ann, courseId: a } = await annNeedingVideos();
    expect((await addSyllabus(ann, OTHER)).status).toBe(200);
    let mine = await ann.json("/api/courses/mine");
    expect(mine).toMatchObject({ status: "ready", course: { id: a }, adding: { status: "reading" } }); // the phone keeps its course meanwhile
    await work(s);
    mine = await ann.json("/api/courses/mine");
    expect(mine.course.id).not.toBe(a);
    expect(mine.adding).toBeNull();
    const list = await courses(ann);
    expect(list).toHaveLength(2);
    expect(list.map((c) => [c.id === a, c.active])).toEqual([[true, false], [false, true]]); // the first they joined first
  });

  it("joins a course the student is in already instead of making a second one, and switches to it", async () => {
    const { s, ann, courseId: a } = await annNeedingVideos();
    await addSyllabus(ann, OTHER);
    await work(s);
    expect(await courses(ann)).toHaveLength(2);
    await addSyllabus(ann, SAME);
    await work(s);
    const list = await courses(ann);
    expect(list).toHaveLength(2);
    expect(list.find((c) => c.active)!.id).toBe(a);
  });

  it("refuses more courses than the cap, and a syllabus while another is still being read", async () => {
    const { s, ann } = await annNeedingVideos({ caps: { coursesPerStudent: 2 } });
    expect((await addSyllabus(ann, OTHER)).status).toBe(200);
    expect((await addSyllabus(ann, "Syllabus of THIRD")).body.error).toMatch(/still being read/);
    await work(s);
    expect((await addSyllabus(ann, "Syllabus of THIRD")).body.error).toMatch(/up to 2 courses/);
  });

  it("shows why a syllabus failed until the student has seen it; a student with no course sees it as their status", async () => {
    const { s, ann } = await annNeedingVideos();
    await addSyllabus(ann, OTHER);
    const job = ((await (await s.worker.post("/api/worker/claim", { kinds: ["syllabus"] })).json()) as { job: { id: string } }).job;
    await s.worker.post(`/api/worker/jobs/${job.id}/fail`, { error: "scan", user_message: "That file is a scan." });
    expect((await ann.json("/api/courses/mine")).adding).toEqual({ status: "failed", error: "That file is a scan." });
    expect((await ann.post("/api/courses/syllabus-error/seen", {})).status).toBe(200);
    expect((await ann.json("/api/courses/mine")).adding).toBeNull();

    const bob = await student(s, "bob@nyu.edu");
    await addSyllabus(bob, "Syllabus of BOB");
    const bobJob = ((await (await s.worker.post("/api/worker/claim", { kinds: ["syllabus"] })).json()) as { job: { id: string } }).job;
    await s.worker.post(`/api/worker/jobs/${bobJob.id}/fail`, { error: "scan", user_message: "Scan." });
    expect(await bob.json("/api/courses/mine")).toEqual({ status: "failed", error: "Scan." });
  });
});

describe("the course a student is in", () => {
  it("is switched with activate, only to a course they are in", async () => {
    const { s, ann, courseId: a } = await annNeedingVideos();
    await addSyllabus(ann, OTHER);
    await work(s);
    const b = (await ann.json("/api/courses/mine")).course.id as string;
    expect((await ann.post(`/api/courses/${a}/activate`, {})).status).toBe(200);
    expect((await ann.json("/api/courses/mine")).course.id).toBe(a);
    expect((await ann.post(`/api/courses/${b}/activate`, {})).status).toBe(200);
    expect((await ann.json("/api/courses/mine")).course.id).toBe(b);
    const bob = await student(s, "bob@nyu.edu");
    expect((await bob.post(`/api/courses/${a}/activate`, {})).status).toBe(404); // not his
    expect((await ann.post("/api/courses/no-such-course/activate", {})).status).toBe(404);
    expect((await s.app.request(`/api/courses/${a}/activate`, { method: "POST" })).status).toBe(401);
  });

  it("keeps each course's levels, playlist and videos apart, and the student's settings and consent together", async () => {
    const { s, ann, annId, courseId: a } = await annNeedingVideos();
    await work(s, { kinds: ["video"] });
    expect((await ann.rpc<any>("getPlaylist")).cards.length).toBeGreaterThan(0); // course A: videos for their level

    await addSyllabus(ann, OTHER);
    await work(s);
    const b = (await ann.json("/api/courses/mine")).course.id as string;
    expect((await ann.rpc<any>("getPlaylist")).cards).toEqual([]); // course B: nothing yet, and no baseline
    await ann.rpc("updateSettings", { captions: false });
    await ann.rpc("postConsent", true);

    const store = new StateStore(s.db);
    expect(Object.keys(store.course(annId, a)!.levels ?? {}).length).toBeGreaterThan(0);
    expect(Object.keys(store.course(annId, b)!.levels ?? {})).toEqual([]);

    await ann.post(`/api/courses/${a}/activate`, {});
    expect((await ann.rpc<any>("getPlaylist")).cards.length).toBeGreaterThan(0); // back in A, as they left it
    const me = await ann.rpc<any>("getMe");
    expect(me.settings.captions).toBe(false); // the setting made in B is theirs, not B's
    expect(me.consent).toBe("research");
    expect(store.profile(annId)).toMatchObject({ consent: "research", settings: { captions: false } });
    expect(store.course(annId, a)).not.toHaveProperty("settings");
  });

  it("is where a student's questions and videos are asked for", async () => {
    const { s, ann, annId, courseId: a } = await annNeedingVideos();
    await addSyllabus(ann, OTHER);
    await work(s);
    const b = (await ann.json("/api/courses/mine")).course.id as string;
    expect(s.courses.courseOf(annId)).toBe(b);
    s.courses.setActive(annId, a);
    expect(s.courses.fixturesFor(annId)!.course.id).toBe(a);
    expect(s.courses.courseOf(annId)).toBe(a);
  });

  it("falls back to the first course they joined when the chosen one is gone", async () => {
    const { s, ann, annId, courseId: a } = await annNeedingVideos();
    await addSyllabus(ann, OTHER);
    await work(s);
    const b = (await ann.json("/api/courses/mine")).course.id as string;
    s.db.prepare("DELETE FROM course_members WHERE user_id = ? AND course_id = ?").run(annId, b);
    expect(s.courses.courseOf(annId)).toBe(a);
  });
});

describe("the course list", () => {
  it("says how far the student got in each course, from that course's own state", async () => {
    const { s, ann, courseId: a } = await annNeedingVideos();
    await work(s, { kinds: ["video"] });
    const [card] = (await ann.rpc<any>("getPlaylist")).cards;
    await ann.rpc("markWatched", card.video_id);
    const kus = s.courses.fixtures(a).course.kus.length;
    expect((await courses(ann))[0].progress).toBeCloseTo(1 / kus);

    await addSyllabus(ann, OTHER);
    await work(s);
    const list = await courses(ann);
    expect(list[0].progress).toBeCloseTo(1 / kus); // A, no longer the one they are in, keeps its progress
    expect(list[1].progress).toBe(0);
    expect(list[0].lectures).toBe(2);
  });
});

describe("the researcher's export and the facilitator", () => {
  it("exports one state per student however many courses they are in: their profile with the course they are in", async () => {
    const { s, ann, annId, courseId: a } = await annNeedingVideos();
    await ann.rpc("postConsent", true);
    await addSyllabus(ann, OTHER);
    await work(s);
    await ann.rpc("updateSettings", { captions: false }); // saved against the second course
    const states = new StateStore(s.db).allStates((id) => s.courses.courseOf(id));
    expect(states).toHaveLength(1);
    expect(states[0]).toMatchObject({ consent: "research", participant_code: expect.any(String) });
    expect(states[0].levels).toEqual({}); // the second course's document: they are in it now
    s.courses.setActive(annId, a);
    expect(Object.keys(new StateStore(s.db).allStates((id) => s.courses.courseOf(id))[0].levels).length).toBeGreaterThan(0);
  });

  it("moves a student who has answered nothing to one course and drops the others", async () => {
    const s = makeServer();
    const ann = await student(s, "ann@nyu.edu");
    await addSyllabus(ann, SAME);
    await work(s);
    await addSyllabus(ann, OTHER);
    await work(s);
    const [first, second] = await courses(ann);
    const annId = idOf(s, "ann@nyu.edu");
    await ann.rpc("updateSettings", { captions: false }); // saves a document for the course they are in
    moveStudent(s.db, s.courses, "ann@nyu.edu", first.id);
    expect(s.courses.coursesOf(annId)).toEqual([first.id]);
    expect(s.courses.courseOf(annId)).toBe(first.id);
    expect(new StateStore(s.db).courseDocs(annId)).toEqual([]);
    expect(second.id).not.toBe(first.id);
  });

  it("merges a course away without taking the student out of their other courses", async () => {
    const s = makeServer();
    const ann = await student(s, "ann@nyu.edu");
    await addSyllabus(ann, SAME);
    await work(s);
    await addSyllabus(ann, OTHER);
    await work(s);
    await addSyllabus(ann, "Syllabus of THIRD");
    await work(s);
    const [one, two, three] = (await courses(ann)).map((c) => c.id);
    const annId = idOf(s, "ann@nyu.edu");
    s.courses.setActive(annId, three); // the one they are in is not the one merged away
    mergeCourses(s.db, s.courses, two, one);
    expect(s.courses.coursesOf(annId).sort()).toEqual([one, three].sort());
    expect(s.courses.courseOf(annId)).toBe(three);
  });
});

describe("research events say which course they happened in", () => {
  const play = (course_id?: string | null, verb = "video_play") => ({ verb, object: { type: "video", id: "v" }, ...(course_id === undefined ? {} : { course_id }) });
  const saved = (s: Server, userId: string) => (new StateStore(s.db).profile(userId)!.events ?? []) as { verb: string; context: { course_id?: string | null } }[];

  it("take the course the phone says, when the student is in it, else the one they are in; student-level ones carry none", async () => {
    const { s, ann, annId, courseId: a } = await annNeedingVideos();
    await addSyllabus(ann, OTHER);
    await work(s);
    const b = (await ann.json("/api/courses/mine")).course.id as string; // the one they are in now
    // sent in one batch, after they switched to B: the first two happened while they were in A
    const res = await ann.post("/api/events", { events: [play(a), play(b), play("not-their-course"), play(undefined), play(a, "consent_given")] });
    expect(res.status).toBe(200);
    const events = saved(s, annId);
    expect(events.slice(-5).map((e) => [e.verb, e.context.course_id])).toEqual([["video_play", a], ["video_play", b], ["video_play", b], ["video_play", b], ["consent_given", null]]);
    // the API's own events, made while they sat the check in A, say A
    const answers = events.filter((e) => e.verb === "cat_answered");
    expect(answers.length).toBeGreaterThan(0);
    expect(answers.every((e) => e.context.course_id === a)).toBe(true);
  });

  it("never let one event's course carry over to the next event, or to the API calls after", () => {
    replaceState(freshState());
    setFixtures({ ...FIX, course: { ...FIX.course, id: "course-now" } });
    try {
      trackClientEvents([play("course-other")] as never, (id) => id === "course-other");
      track("video_play", { type: "video" }); // an API call's own event, on the course the request runs on
      expect(getState().events.map((e) => e.context.course_id)).toEqual(["course-other", "course-now"]);
    } finally {
      setFixtures(FIX);
    }
  });

  it("are given a course when old state is migrated: the one the student had (the demo course if none), none for the student's own", () => {
    const db = openDb(":memory:");
    const ev = (verb: string) => ({ id: verb, verb, object: { type: "x" }, context: { screen: "", device: "mobile", orientation: "portrait", condition: "A", participant_code: "P", week: 1 }, timestamp: "" });
    const state = (events: unknown[]) => JSON.stringify({ ...freshState(), events });
    db.prepare("INSERT INTO users (id, email, participant_code, created_at) VALUES ('u1', 'a@nyu.edu', 'P-1', 0), ('u2', 'b@nyu.edu', 'P-2', 0)").run();
    db.prepare("INSERT INTO courses (id, syllabus_key, code, name, syllabus_text, syllabus_path, status, created_by, created_at) VALUES ('c1', 'k', 'C', 'C', '', '', 'ready', 'u1', 0)").run();
    db.prepare("INSERT INTO course_members (course_id, user_id, joined_at) VALUES ('c1', 'u1', 1)").run();
    db.prepare("INSERT INTO user_state (user_id, json, updated_at) VALUES ('u1', ?, 5), ('u2', ?, 6)").run(state([ev("video_play"), ev("study_shown")]), state([ev("skipped")]));
    migrateStates(db);
    const store = new StateStore(db);
    expect(store.profile("u1")!.events!.map((e) => [e.verb, e.context.course_id])).toEqual([["video_play", "c1"], ["study_shown", null]]);
    expect(store.profile("u2")!.events!.map((e) => [e.verb, e.context.course_id])).toEqual([["skipped", FIX.course.id]]);
  });
});

describe("the student's data download", () => {
  type Download = { courses: { course_id: string; code: string; name: string; active: boolean; profile: { levels: object; made: object; sittings: object }; responses: unknown[]; notes: unknown[]; self_explanations: unknown[] }[]; responses: unknown[]; events: { verb: string }[]; profile: { levels: object } };

  it("has every course's answers and levels, whichever one they are in when they download", async () => {
    const { s, ann, courseId: a } = await annNeedingVideos(); // course A: they sat the check
    await addSyllabus(ann, OTHER);
    await work(s);
    const b = (await ann.json("/api/courses/mine")).course.id as string;

    const inB = await ann.rpc<Download>("exportMyData"); // in B: the core's own download would stop at B
    const entry = (d: Download, id: string) => d.courses.find((c) => c.course_id === id)!;
    expect(inB.courses.map((c) => [c.course_id, c.active])).toEqual([[a, false], [b, true]]);
    expect(entry(inB, a).responses.length).toBeGreaterThan(0);
    expect(Object.keys(entry(inB, a).profile.levels).length).toBeGreaterThan(0);
    expect(entry(inB, b).responses).toEqual([]);
    expect(inB.responses).toEqual([]); // the top level is still the course they are in, as it always was

    await ann.post(`/api/courses/${a}/activate`, {});
    const inA = await ann.rpc<Download>("exportMyData");
    expect(entry(inA, a).active).toBe(true);
    expect(entry(inA, a).responses).toEqual(inA.responses); // the live course agrees with the top level
    expect(entry(inA, a).responses.length).toBe(entry(inB, a).responses.length);
    expect(inA.events.map((e) => e.verb)).toContain("data_downloaded"); // the student's own parts are still there
  });

  it("says nothing but what is the student's: no syllabus text, file paths or other users", async () => {
    const { s, ann } = await annNeedingVideos();
    await addSyllabus(ann, OTHER);
    await work(s);
    const data = await ann.rpc<Download>("exportMyData");
    for (const c of data.courses) expect(Object.keys(c).sort()).toEqual(["active", "code", "course_id", "name", "notes", "profile", "responses", "self_explanations"]);
    const text = JSON.stringify(data);
    expect(text).not.toContain("syllabus_text");
    expect(text).not.toContain("syllabus_path");
    expect(text).not.toContain("created_by");
  });

  it("leaves out a classmate's data, and covers a student who has no course of their own", async () => {
    const { s, ann, courseId: a } = await annNeedingVideos();
    const bob = await student(s, "bob@nyu.edu");
    const bobs = await bob.rpc<Download>("exportMyData");
    expect(bobs.courses.map((c) => c.course_id)).not.toContain(a); // Ann's course, with her answers, is not in Bob's download
    expect(bobs.courses.flatMap((c) => c.responses)).toEqual([]);
    const annData = await ann.rpc<Download>("exportMyData");
    expect(annData.courses.map((c) => c.course_id)).toEqual([a]);
  });
});
