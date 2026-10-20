import { expect } from "vitest";
import type { DeckResult } from "@syllabyte/core/logic/assemble";
import type { Item, ItemTier } from "@syllabyte/core/types";
import type { makeServer } from "./helpers";

/** A stand-in for ingestion_agent/worker.py: claims the server's upload jobs and answers them with made-up results. */

type Server = ReturnType<typeof makeServer>;

export interface Job {
  id: string;
  kind: "syllabus" | "deck_read" | "placement" | "deck" | "question" | "link_pass";
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

/**
 * What the Python worker would read from a file. Here a file's text is its content: each line a page, the first line
 * what it teaches (the reader's title), and an "order N" line where it comes in the course (what the real placement
 * call works out from the summaries). File names say nothing.
 */
function readOf(text: string, payload: Record<string, any>) {
  const pages = text.split("\n");
  const base = { content_key: `key:${text}`, page_count: pages.length, first_title: pages[0], pages, page_keys: pages.map((p) => `page:${p}`) };
  if ((payload.known_keys ?? []).includes(base.content_key)) return base;
  return { ...base, summary: { title: pages[0], summary: text, lecture_number: null, is_lecture: true } };
}

const orderOf = (summary: string) => Number(/order (\d+)/.exec(summary)?.[1] ?? 999);

/** The placement call: lectures keep their order; each new deck goes where its "order N" puts it. */
function placementOf(p: Record<string, any>) {
  const all = [...p.lectures.map((l: any) => ({ ...l, fixed: true })), ...p.new.map((d: any) => ({ ...d, fixed: false }))];
  const fresh = all.filter((x) => !x.fixed).sort((a, b) => orderOf(a.summary) - orderOf(b.summary));
  const order: string[] = [];
  for (const l of all.filter((x) => x.fixed)) {
    while (fresh.length && orderOf(fresh[0].summary) < orderOf(l.summary)) order.push(fresh.shift()!.id);
    order.push(l.id);
  }
  order.push(...fresh.map((d) => d.id));
  return { order, unsure: p.new.filter((d: any) => d.summary.includes("unsure")).map((d: any) => d.id) };
}

/** A deterministic stand-in for the deck job: two KUs named after the deck's first line, the first building on the
 * last KU it was shown from earlier lectures (as the real extraction may). No questions: they are written on demand. */
function deckResultOf(firstLine: string, payload: Record<string, any>): DeckResult {
  const slug = firstLine.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const earlier: { id: string }[] = payload.earlier;
  const a = `ku-${slug}-a`;
  const b = `ku-${slug}-b`;
  const tier_difficulty = { basic: -1, applied: 0, advanced: 1 };
  return {
    kus: [
      { id: a, title: a, short_title: a, summary: "", bloom_level: "understand", prerequisites: earlier.length ? [earlier.at(-1)!.id] : [], source_refs: [], tier_difficulty },
      { id: b, title: b, short_title: b, summary: "", bloom_level: "apply", prerequisites: [a], source_refs: [], tier_difficulty },
    ],
    items: [],
  };
}

/** The question job: one item at the KU and tier, keyed where the server asked. */
function questionOf(p: Record<string, any>): { item: Item; flags: [] } {
  const options = ["x", "y", "z"];
  return {
    item: {
      id: p.item_id, ku_id: p.ku.id, topic_id: "", context: "assessment", stem: `${p.item_id}?`, options, correct_index: p.target_index,
      allows_not_sure: true, explanation: "", hint: null, difficulty_prior: p.beta, discrimination: 1, tier: p.tier as ItemTier, source_refs: [],
    },
    flags: [],
  };
}

/** The fake worker: claims jobs and answers them the way ingestion_agent/worker.py would. */
export async function work(
  s: Server,
  opts: { links?: (p: Record<string, any>) => { ku_id: string; prereq_id: string }[]; until?: number; kinds?: Job["kind"][] } = {},
) {
  const done: Job[] = [];
  for (let guard = 0; guard < (opts.until ?? 200); guard++) {
    const { job } = (await (await s.worker.post("/api/worker/claim", opts.kinds ? { kinds: opts.kinds } : {})).json()) as { job: Job | null };
    if (!job) break;
    done.push(job);
    const text = job.file_name ? await (await s.worker.get(`/api/worker/jobs/${job.id}/file`)).text() : "";
    let result: Record<string, unknown>;
    if (job.kind === "syllabus") {
      const key = `syl:${text}`;
      const { is_new } = (await (await s.worker.post(`/api/worker/jobs/${job.id}/syllabus-key`, { key })).json()) as { is_new: boolean };
      result = is_new ? { key, text, schedule: text.includes("no schedule") ? { ...SCHEDULE, lectures: [] } : SCHEDULE } : { key, text };
    } else if (job.kind === "deck_read") {
      result = readOf(text, job.payload);
    } else if (job.kind === "placement") {
      result = placementOf(job.payload);
    } else if (job.kind === "deck") {
      result = deckResultOf(text.split("\n")[0], job.payload) as unknown as Record<string, unknown>;
    } else if (job.kind === "question") {
      result = questionOf(job.payload);
    } else {
      result = { links: opts.links?.(job.payload) ?? [] };
    }
    const r = await s.worker.post(`/api/worker/jobs/${job.id}/result`, { result });
    expect(r.status, `${job.kind} result`).toBe(200);
  }
  return done;
}
