import { describe, expect, it } from "vitest";
import { FIX } from "@syllabyte/core/fixtures";
import { allReports, reportsCsv } from "../src/reports";
import { makeServer } from "./helpers";

type Row = { participant_code: string; target: string; target_id: string; about: string; note: string; research_consent: boolean; category_label: string; lecture_n: number | null; course: string };

describe("error reports", () => {
  it("are sent by students and listed for researchers by study code, never by email", async () => {
    const s = makeServer();
    const [ann, bob, res] = await Promise.all([s.signIn("ann@nyu.edu"), s.signIn("bob@nyu.edu"), s.signIn("researcher@nyu.edu", "researcher")]);
    await ann.rpc("postConsent", true);
    await bob.rpc("postConsent", false);
    const video = FIX.videos[0];
    const item = FIX.items[0];
    await ann.rpc("reportProblem", { target: "video", video_id: video.id, category: "fact", video_t: 42, note: "Says O(n), slide 4 says O(log n)" });
    await ann.rpc("reportProblem", { target: "question", item_id: item.id, category: "unclear", note: "" });
    await bob.rpc("reportProblem", { target: "app", category: "bug", note: "Upload never finishes", screen: "/profile" });

    expect((await ann.get("/api/research/reports")).status).toBe(403);
    const r = await res.get("/api/research/reports");
    expect(r.status).toBe(200);
    const { reports } = (await r.json()) as { reports: Row[] };
    const [pa, pb] = (await Promise.all([ann, bob].map((p) => p.rpc<{ participant_code: string }>("getMe")))).map((m) => m.participant_code);
    expect(reports).toHaveLength(3);
    expect(reports.find((x) => x.target === "video")).toMatchObject({
      participant_code: pa, research_consent: true, target_id: video.id, about: video.title, lecture_n: video.lecture_n, category_label: "A fact is wrong",
      note: "Says O(n), slide 4 says O(log n)",
    });
    expect(reports.find((x) => x.target === "question")).toMatchObject({ participant_code: pa, target_id: item.id, about: item.stem });
    // a student who declined research can still report a problem; the column says so
    expect(reports.find((x) => x.target === "app")).toMatchObject({ participant_code: pb, research_consent: false, target_id: "", note: "Upload never finishes" });
    expect(reports.every((x) => x.course.includes(FIX.course.name))).toBe(true);
    expect(JSON.stringify(reports)).not.toContain("@nyu.edu");

    const csv = await (await res.get("/api/research/reports?format=csv")).text();
    expect(csv.split("\n")[0]).toContain("participant_code");
    expect(csv).toContain('"Says O(n), slide 4 says O(log n)"');
    expect(csv).not.toContain("@nyu.edu");
  });

  it("are refused when the form could not have sent them, and nothing is stored", async () => {
    const s = makeServer();
    const [ann, res] = await Promise.all([s.signIn("ann@nyu.edu"), s.signIn("researcher@nyu.edu", "researcher")]);
    await expect(ann.rpc("reportProblem", { target: "video", video_id: "not-a-video", category: "fact", video_t: null, note: "" })).rejects.toThrow(/unknown video/);
    await expect(ann.rpc("reportProblem", { target: "app", category: "bug", note: "" })).rejects.toThrow(/say what happened/);
    await expect(ann.rpc("reportProblem", "nonsense")).rejects.toThrow(/report/);
    const { reports } = (await (await res.get("/api/research/reports")).json()) as { reports: Row[] };
    expect(reports).toEqual([]);
  });

  it("are in the student's own data download", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    await ann.rpc("postConsent", true);
    await ann.rpc("reportProblem", { target: "app", category: "other", note: "The font is tiny" });
    const data = await ann.rpc<{ courses: { reports: { note: string }[] }[] }>("exportMyData");
    expect(data.courses.flatMap((c) => c.reports).map((r) => r.note)).toEqual(["The font is tiny"]);
  });

  it("keep a spreadsheet from reading a note as a formula", async () => {
    const s = makeServer();
    const ann = await s.signIn("ann@nyu.edu");
    await ann.rpc("reportProblem", { target: "app", category: "bug", note: '=HYPERLINK("http://x","y")' });
    const csv = reportsCsv(allReports(s.db, () => "Demo"));
    expect(csv).toContain(`"'=HYPERLINK(""http://x"",""y"")"`);
  });
});
