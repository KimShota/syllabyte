import type { Level, ResponseRecord, TailoringRow, Topic, Video } from "@/lib/types";
import { countsFor } from "./levels";

/**
 * The tailoring receipt (screen 5). The *what* comes from the video's per-level
 * skeleton; the *why* is a template over the student's own answers (plan §2 rule 4),
 * so it is true by construction.
 */
export function tailoringRows(video: Video, level: Level, topics: Topic[], responses: ResponseRecord[]): TailoringRow[] {
  const standard = `Standard for Level ${level}.`;
  return video.tailoring[String(level) as "1" | "2" | "3"].map((row) => {
    let why = standard;
    if (row.evidence_topic_id) {
      const topic = topics.find((t) => t.id === row.evidence_topic_id);
      const t = `“${topic?.title ?? "this topic"}”`;
      const c = countsFor(row.evidence_topic_id, responses);
      const total = c.right + c.wrong + c.notSure;
      if (row.kind === "left_out") {
        if (c.right >= 1 && c.wrong === 0 && c.notSure === 0) {
          why = c.right === 1 ? `You answered the question on ${t} correctly.` : `You answered ${c.right === 2 ? "both" : `all ${c.right}`} questions on ${t} correctly.`;
        }
      } else if (row.kind === "added" && total > 0) {
        if (c.notSure > 0) why = c.notSure === 1 ? `You marked “Not sure” on a question on ${t}.` : `You marked “Not sure” on ${c.notSure} questions on ${t}.`;
        else if (c.wrong > 0) why = c.wrong === 1 ? `You missed a question on ${t}.` : `You missed ${c.wrong} questions on ${t}.`;
      }
    }
    return { kind: row.kind, what: row.what, why };
  });
}

export function changesCount(rows: TailoringRow[]): number {
  return rows.filter((r) => r.kind !== "set_to").length;
}
