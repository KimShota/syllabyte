import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setEventEnv, setEventSink, STUDENT_EVENT_VERBS, track, type ClientEvent } from "../src/events";
import { getState, resetState } from "../src/store";

const last = () => getState().events.at(-1)!;

describe("events say which course they happened in", () => {
  beforeEach(() => {
    resetState();
    setEventSink(null);
    setEventEnv({ course: () => "course-a" });
  });
  afterEach(() => setEventSink(null));

  it("carry the course the app or the request is in, and follow the student when they switch", () => {
    track("video_play", { type: "video", id: "v1" });
    expect(last().context.course_id).toBe("course-a");
    setEventEnv({ course: () => "course-b" });
    track("video_play", { type: "video", id: "v2" });
    expect(last().context.course_id).toBe("course-b");
  });

  it("carry none when they are about the student: consent, their data download, the questionnaires", () => {
    expect([...STUDENT_EVENT_VERBS].sort()).toEqual(["consent_given", "data_downloaded", "study_shown", "study_snoozed", "study_started", "study_submitted"]);
    for (const verb of STUDENT_EVENT_VERBS) {
      track(verb, { type: "x" });
      expect(last().context.course_id, verb).toBeNull();
    }
    for (const verb of ["cat_answered", "levels_updated", "skipped", "checkpoint_answered", "model_reset", "captions_toggled"] as const) {
      track(verb, { type: "x" });
      expect(last().context.course_id, verb).toBe("course-a");
    }
  });

  it("are stamped on the phone when they happen, not when the batch is sent", () => {
    const sent: ClientEvent[] = [];
    setEventSink((ev) => sent.push(ev));
    track("video_play", { type: "video", id: "v1" });
    setEventEnv({ course: () => "course-b" }); // the student switches before the batch goes
    track("video_play", { type: "video", id: "v2" });
    track("study_shown", { type: "battery", id: "baseline" });
    expect(sent.map((e) => e.course_id)).toEqual(["course-a", "course-b", null]);
  });
});

const haveFixtures = existsSync(resolve(__dirname, "../fixtures/bank.json"));

describe.skipIf(!haveFixtures)("with the fixtures loaded", () => {
  it("are in the course the fixtures hold, unless an app says otherwise: the demo course, or the student's own", async () => {
    const fx = await import("../src/fixtures");
    resetState();
    setEventSink(null);
    setEventEnv({ course: fx.currentCourseId });
    track("video_play", { type: "video" });
    expect(last().context.course_id).toBe(fx.FIX.course.id);
    fx.setFixtures({ ...fx.FIX, course: { ...fx.FIX.course, id: "a-student-course" } });
    track("video_play", { type: "video" });
    expect(last().context.course_id).toBe("a-student-course");
    fx.setFixtures(fx.FIX);
  });
});
