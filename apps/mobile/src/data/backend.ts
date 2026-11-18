/**
 * Where the phone finds the backend (apps/server). Two setups (deploy/README.md):
 *
 * Development, on the laptop (Expo Go, Metro running): what the environment says.
 * - `EXPO_PUBLIC_API_BASE=http://<laptop>:8788`: use that server (apps/mobile/.env.local, never part of a build).
 * - `EXPO_PUBLIC_USE_SERVER=1`: use the server on the machine running Metro, port 8788 (`npm run dev` in apps/server);
 *   the simulator and a phone on the same Wi-Fi both reach it.
 * - neither: no backend; the app runs on its own, on the in-app mock (how the UI is built and tested).
 *
 * An installed build (TestFlight, what participants get): always a server, always HTTPS. `EXPO_PUBLIC_API_BASE`
 * from eas.json if it is an HTTPS address, otherwise the production server. It never falls back to the mock or to a
 * laptop: a participant on the mock would see the demo course, and nothing they did would reach the study.
 */
import Constants from "expo-constants";

const SERVER_PORT = 8788;
export const PRODUCTION_API = "https://api.syllabyte.app";

export function backendBase(override: string | undefined, useServer: string | undefined, hostUri: string | undefined, dev = true): string | null {
  const given = override?.trim().replace(/\/+$/, "");
  if (!dev) return given && /^https:\/\//.test(given) ? given : PRODUCTION_API;
  if (given) return given;
  const host = hostUri?.split(":")[0];
  return useServer === "1" && host ? `http://${host}:${SERVER_PORT}` : null;
}

/** Which setup the app is in, in words, for the profile screen: so you can see at a glance which server it uses. */
export function backendLabel(base: string | null, dev = true): string {
  if (!base) return "Demo mode: no server, nothing is saved for the study";
  const host = base.replace(/^https?:\/\//, "");
  if (base === PRODUCTION_API) return `Study server · ${host}${dev ? " (from a development session)" : ""}`;
  return `${dev ? "Development server" : "Server"} · ${host}`;
}

export const BACKEND_BASE = backendBase(process.env.EXPO_PUBLIC_API_BASE, process.env.EXPO_PUBLIC_USE_SERVER, Constants.expoConfig?.hostUri, __DEV__);
export const REMOTE = BACKEND_BASE !== null;
export const BACKEND_LABEL = backendLabel(BACKEND_BASE, __DEV__);
