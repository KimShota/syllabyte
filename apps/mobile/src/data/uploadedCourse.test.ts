import type { LectureStateView } from "@syllabyte/core/api/types";
import type { Course, Video } from "@syllabyte/core/types";
import { beforeAll, describe, expect, it, vi } from "vitest";

// the server's address is read when the data layer loads (data/backend.ts)
let uploadedCourseDef: typeof import("./course").uploadedCourseDef;
let courseStubs: typeof import("./course").courseStubs;
beforeAll(async () => {
  vi.stubEnv("EXPO_PUBLIC_API_BASE", "http://10.0.0.5:8788");
  ({ uploadedCourseDef, courseStubs } = await import("./course"));
});

const COURSE = {
  id: "c1", code: "CS-1", name: "Data structures", eyebrow: "", syllabus_summary: "", config: {}, topics: [], lectures: [],
  kus: [
    { id: "ku-a", title: "Insert", short_title: "Insert", topic_id: "lecture-1", lecture_n: 1, video_id: "ku-a", bloom_level: "apply", prerequisites: [] },
    { id: "ku-b", title: "Search", short_title: "Search", topic_id: "lecture-1", lecture_n: 1, video_id: null, bloom_level: "apply", prerequisites: [] },
  ],
} as unknown as Course;
const LECTURES = [{ n: 1, title: "Trees", state: "ready" }] as unknown as LectureStateView[];
const VIDEO = {
  id: "ku-a", ku_id: "ku-a", duration_s: 98.5, video_url: "/api/media/c1/ku-a/2/video.mp4?e=9&s=ab", captions_burned_in: true, source_slides: [7, 4, 5],
  transcript: [{ t: 0, narration: "Hi.", visual: "Diagram: Tree — a tree", speaker: "Peter" }],
} as unknown as Video;

describe("an uploaded course's KUs", () => {
  it("play the made video from the server, with its length, transcript and slides", () => {
    const { kus } = uploadedCourseDef(COURSE, LECTURES, new Map([["ku-a", VIDEO]]));
    expect(kus["ku-a"].videoId).toBe("ku-a");
    expect(kus["ku-a"].videoUri).toBe("http://10.0.0.5:8788/api/media/c1/ku-a/2/video.mp4?e=9&s=ab");
    expect(kus["ku-a"]).toMatchObject({ durationS: 98.5, slides: [4, 7], captionsBurnedIn: true });
    expect(kus["ku-a"].transcript).toEqual([{ t: 0, text: "Hi.", heading: "Tree", speaker: "Peter" }]);
  });

  it("show the stand-in frame while a KU has no video, or its details haven't arrived", () => {
    const { kus } = uploadedCourseDef(COURSE, LECTURES, new Map([["ku-a", VIDEO]]));
    expect(kus["ku-b"]).toMatchObject({ videoId: null, videoUri: undefined, transcript: [] });
    const none = uploadedCourseDef(COURSE, LECTURES).kus["ku-a"];
    expect(none.videoId).toBe("ku-a"); // the KU has a video; its file isn't known yet
    expect(none.videoUri).toBeUndefined();
    expect(none.transcript).toEqual([]);
  });
});

describe("the student's other courses", () => {
  const list = [
    { id: "a", code: "CS-1", name: "Data structures", active: true, lectures: 5, lectures_ready: 3, progress: 0.4 },
    { id: "b", code: "ML-2", name: "Machine learning", active: false, lectures: 8, lectures_ready: 6, progress: 0.25 },
  ];

  it("are everything but the one they are in, with the counts the drawer and Home show", () => {
    expect(courseStubs(list)).toEqual([{ id: "b", code: "ML-2", name: "Machine learning", term: "", progress: 0.25, lecturesDone: 6, lecturesPlanned: 8 }]);
  });

  it("are none for a student with one course", () => {
    expect(courseStubs([list[0]])).toEqual([]);
    expect(courseStubs([])).toEqual([]);
  });
});
