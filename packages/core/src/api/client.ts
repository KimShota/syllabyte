import { mockApi } from "./mock";
import type { Api } from "./types";

/**
 * The only API components import. By default the in-browser mock (the web demo, and the phone while it works on its
 * own); an app that talks to the backend calls `setApi(remote.api)` once at start-up (api/remote.ts). Components
 * never know which one they have (plan Q6).
 */
let current: Api = mockApi;

export function setApi(next: Api): void {
  current = next;
}

export const api: Api = new Proxy({} as Api, {
  get: (_target, method) => (typeof method === "string" && method !== "then" ? (current as unknown as Record<string, unknown>)[method] : undefined),
});
