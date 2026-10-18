/**
 * Where the phone finds the backend (apps/server). Without a backend the app runs on its own, on the in-app mock:
 * that is how the UI is built and tested.
 *
 * - `EXPO_PUBLIC_API_BASE=https://api.example.com`: use that server (a real build).
 * - `EXPO_PUBLIC_USE_SERVER=1`: use the server on the machine running Metro, port 8788 (`npm run dev` in apps/server);
 *   the simulator and a phone on the same Wi-Fi both reach it.
 * - neither: no backend.
 */
import Constants from "expo-constants";

const SERVER_PORT = 8788;

export function backendBase(override: string | undefined, useServer: string | undefined, hostUri: string | undefined): string | null {
  if (override) return override.replace(/\/+$/, "");
  const host = hostUri?.split(":")[0];
  return useServer === "1" && host ? `http://${host}:${SERVER_PORT}` : null;
}

export const BACKEND_BASE = backendBase(process.env.EXPO_PUBLIC_API_BASE, process.env.EXPO_PUBLIC_USE_SERVER, Constants.expoConfig?.hostUri);
export const REMOTE = BACKEND_BASE !== null;
