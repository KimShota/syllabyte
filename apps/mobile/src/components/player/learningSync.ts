/**
 * The playback saves still on their way to the server. A decision point (the move to the next video, the return to the
 * app, the end of a session) waits for them first, so the server decides on everything the student did, not on what
 * happened to arrive (plan/engagement-feedback-implementation-plan.md: boundary evaluation must not depend on a save
 * racing it). The server handles one request at a time, in order, so waiting here is enough.
 */
const pending = new Set<Promise<unknown>>();

export function trackSave<T>(p: Promise<T>): Promise<T> {
  pending.add(p);
  const done = () => pending.delete(p);
  p.then(done, done);
  return p;
}

export async function whenSaved(): Promise<void> {
  while (pending.size) await Promise.allSettled([...pending]);
}
