import { describe, expect, it, vi } from "vitest";
import type { StorageAdapter } from "../src/store";

// Each test gets a fresh copy of the store module: hydrate binds one adapter for the module's life.
async function freshStore() {
  vi.resetModules();
  return import("../src/store");
}

function memory(initial: string | null, visit = "v1"): StorageAdapter & { saved: string[] } {
  const saved: string[] = [];
  return { saved, load: () => initial, save: (raw) => void saved.push(raw), visitId: () => visit };
}

describe("store persistence through a StorageAdapter", () => {
  it("keeps state in memory until an adapter is given", async () => {
    vi.useFakeTimers();
    const store = await freshStore();
    store.mutate((s) => {
      s.participant_code = "P1";
    });
    vi.runAllTimers();
    expect(store.getState().participant_code).toBe("P1");
    expect(store.isHydrated()).toBe(false);
    vi.useRealTimers();
  });

  it("loads the saved document, starts a new visit, and saves later changes", async () => {
    vi.useFakeTimers();
    const store = await freshStore();
    const saved = { ...store.freshState(), participant_code: "P7", visit: { id: "old", handled: 2 } };
    const adapter = memory(JSON.stringify(saved), "new");
    store.hydrate(adapter);
    expect(store.isHydrated()).toBe(true);
    expect(store.getState().participant_code).toBe("P7");
    expect(store.getState().visit).toEqual({ id: "new", handled: 0 });

    store.mutate((s) => {
      s.condition = "B";
    });
    expect(adapter.saved).toHaveLength(0); // debounced
    vi.runAllTimers();
    expect(JSON.parse(adapter.saved.at(-1)!).condition).toBe("B");
    vi.useRealTimers();
  });

  it("flush writes a pending change at once", async () => {
    vi.useFakeTimers();
    const store = await freshStore();
    const adapter = memory(null);
    store.hydrate(adapter);
    store.mutate((s) => {
      s.participant_code = "P2";
    });
    store.flush();
    expect(JSON.parse(adapter.saved.at(-1)!).participant_code).toBe("P2");
    vi.useRealTimers();
  });

  it("waits for an async load (AsyncStorage) and ignores a corrupt document", async () => {
    const store = await freshStore();
    const listener = vi.fn();
    store.subscribe(listener);
    const done = store.hydrate({ load: async () => "{not json", save: () => {}, visitId: () => "v" });
    expect(done).toBeInstanceOf(Promise);
    expect(store.isHydrated()).toBe(false);
    await done;
    expect(store.isHydrated()).toBe(true);
    expect(store.getState().v).toBe(2);
    expect(listener).toHaveBeenCalled();
  });

  it("ignores a document from another schema version", async () => {
    const store = await freshStore();
    store.hydrate(memory(JSON.stringify({ v: 1, participant_code: "OLD" })));
    expect(store.getState().participant_code).toBeNull();
  });
});
