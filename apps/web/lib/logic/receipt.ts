import type { Item, KuEntry, Level, ResponseRecord, TailoringRow, Video } from "@/lib/types";
import { kuCounts } from "./kuProfile";

/**
 * The tailoring receipt (screen 5). The *what* comes from the video's per-level
 * skeleton; the *why* is a template over the student's own answers (plan §2 rule 4),
 * so it is true by construction. Evidence is per KU: the prerequisite for the recap rows,
 * the KU itself for the example rows.
 */
export function tailoringRows(video: Video, level: Level, kus: KuEntry[], items: Item[], responses: ResponseRecord[]): TailoringRow[] {
  const standard = `Standard for Level ${level}.`;
  return video.tailoring[String(level) as "1" | "2" | "3"].map((row) => {
    let why = standard;
    if (row.evidence_ku_id) {
      const ku = kus.find((k) => k.id === row.evidence_ku_id);
      const t = `“${ku?.short_title ?? "this concept"}”`;
      const c = kuCounts(row.evidence_ku_id, items, responses);
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
