import type { KuEntry } from "../types";

/**
 * The Knowledge Unit Graph orders the playlist (plan/per-ku-profiling-plan.md D14): a KU's prerequisites come
 * before it. It never caps a level.
 */

/** Every KU a KU builds on, directly or through others. */
export function ancestorsOf(kus: KuEntry[]): Map<string, Set<string>> {
  const byId = new Map(kus.map((k) => [k.id, k]));
  const memo = new Map<string, Set<string>>();
  const visit = (id: string, path: Set<string>): Set<string> => {
    const known = memo.get(id);
    if (known) return known;
    const out = new Set<string>();
    if (!path.has(id)) {
      path.add(id);
      for (const p of byId.get(id)?.prerequisites ?? []) {
        out.add(p);
        for (const a of visit(p, path)) out.add(a);
      }
      path.delete(id);
    }
    memo.set(id, out);
    return out;
  };
  for (const k of kus) visit(k.id, new Set());
  return memo;
}

/**
 * `entries` with prerequisites first. Among entries that are free to go next (nothing in the list is still a
 * prerequisite of them), `compare` decides, so the existing order (slide order, gaps before new...) is kept
 * wherever the graph does not say otherwise.
 */
export function orderByPrerequisites<T>(
  entries: readonly T[],
  kuOf: (t: T) => string,
  kus: KuEntry[],
  compare: (a: T, b: T) => number,
): T[] {
  const anc = ancestorsOf(kus);
  const remaining = [...entries].sort(compare);
  const out: T[] = [];
  while (remaining.length > 0) {
    const free = remaining.findIndex((e) => !remaining.some((o) => o !== e && anc.get(kuOf(e))?.has(kuOf(o))));
    out.push(...remaining.splice(free === -1 ? 0 : free, 1)); // free === -1 only if the graph had a cycle
  }
  return out;
}

/** "“A” comes first because “B” builds on it." for each prerequisite pair that is actually in the list, in list order. */
export function prerequisiteNotes<T>(
  ordered: readonly T[],
  kuOf: (t: T) => string,
  kus: KuEntry[],
  name: (kuId: string) => string,
  max = 2,
): string[] {
  const anc = ancestorsOf(kus);
  const notes: string[] = [];
  for (let i = 0; i < ordered.length && notes.length < max; i++) {
    for (let j = i + 1; j < ordered.length && notes.length < max; j++) {
      if (anc.get(kuOf(ordered[j]))?.has(kuOf(ordered[i]))) {
        notes.push(`“${name(kuOf(ordered[i]))}” comes first because “${name(kuOf(ordered[j]))}” builds on it.`);
      }
    }
  }
  return notes;
}
