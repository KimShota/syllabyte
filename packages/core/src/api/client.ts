import { mockApi } from "./mock";
import type { Api } from "./types";

/**
 * The only API components import. Phase 0: the in-browser mock. Phase 1: swap this for
 * a fetch-based client implementing the same `Api` (types generated from FastAPI's
 * OpenAPI schema) — no component changes (plan Q6).
 */
export const api: Api = mockApi;
