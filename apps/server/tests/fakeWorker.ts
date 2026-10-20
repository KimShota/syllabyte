import { expect } from "vitest";
import type { DeckResult } from "@syllabyte/core/logic/assemble";
import type { Item } from "@syllabyte/core/types";
import type { makeServer } from "./helpers";

/** A stand-in for ingestion_agent/worker.py: claims the server's upload jobs and answers them with made-up results. */

type Server = ReturnType<typeof makeServer>;

export interface Job {
  id: string;
  kind: "syllabus" | "deck_read" | "deck" | "link_pass";
  payload: Record<string, any>;
  file_name: string | null;
}

export const SCHEDULE = {
  course_code: "CS-UH 2219E",
  course_name: "Computational Social Science",
  lectures: [
    { n: 1, title: "Potential outcomes", week: 1 },
    { n: 2, title: "Selection bias", week: 2 },
    { n: 3, title: "Randomization", week: 3 },
  ],
};

/** What the Python worker would read from a file: here the file's text is its content (and its key). */
function readOf(text: string) {
  return { content_key: `key:${text}`, page_count: 2, first_title: text.split("\n")[0], pages: text.split("\n") };
}

/** A deterministic stand-in for the deck job: two KUs named after the deck's first line, the first building on the
 * last KU it was shown from earlier lectures (as the real extraction may). */
function deckResultOf(firstLine: string, payload: Record<string, any>): DeckResult {
  const slug = firstLine.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const earlier: { id: string }[] = payload.earlier;
  const a = `ku-${slug}-a`;
  const b = `ku-${slug}-b`;
  const item = (ku: string, tier: string): Item => ({
    id: `as-${ku}-${tier}`, ku_id: ku, topic_id: "", context: "assessment", stem: `${ku} ${tier}?`, options: ["x", "y", "z"], correct_index: 1,
    allows_not_sure: true, explanation: "", hint: null, difficulty_prior: tier === "basic" ? -1 : tier === "applied" ? 0 : 1, discrimination: 1,
    tier: tier as Item["tier"], source_refs: [],
  });
  return {
    kus: [
      { id: a, title: a, short_title: a, summary: "", bloom_level: "understand", prerequisites: earlier.length ? [earlier.at(-1)!.id] : [], source_refs: [] },
      { id: b, title: b, short_title: b, summary: "", bloom_level: "apply", prerequisites: [a], source_refs: [] },
    ],
    items: [a, b].flatMap((k) => ["basic", "applied", "advanced"].map((t) => item(k, t))),
  };
}

/** The fake worker: claims jobs and answers them the way ingestion_agent/worker.py would. */
export async function work(s: Server, opts: { links?: (p: Record<string, any>) => { ku_id: string; prereq_id: string }[]; until?: number } = {}) {
  const done: Job[] = [];
  for (let guard = 0; guard < (opts.until ?? 200); guard++) {
    const { job } = (await (await s.worker.post("/api/worker/claim", {})).json()) as { job: Job | null };
    if (!job) break;
    done.push(job);
    const text = job.file_name ? await (await s.worker.get(`/api/worker/jobs/${job.id}/file`)).text() : "";
    let result: Record<string, unknown>;
    if (job.kind === "syllabus") {
      const key = `syl:${text}`;
      const { is_new } = (await (await s.worker.post(`/api/worker/jobs/${job.id}/syllabus-key`, { key })).json()) as { is_new: boolean };
      result = is_new ? { key, text, schedule: text.includes("no schedule") ? { ...SCHEDULE, lectures: [] } : SCHEDULE } : { key, text };
    } else if (job.kind === "deck_read") {
      result = readOf(text);
    } else if (job.kind === "deck") {
      result = deckResultOf(text.split("\n")[0], job.payload) as unknown as Record<string, unknown>;
    } else {
      result = { links: opts.links?.(job.payload) ?? [] };
    }
    const r = await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result });
    expect(r.status, `${job.kind} result`).toBe(200);
  }
  return done;
}

