/**
 * Where the rendered videos come from while the app runs on mock data: `npm run media` (scripts/serve-media.mjs)
 * serves apps/web/public on the machine running Metro. The phone reaches it at the host it loaded the JS bundle
 * from, so the simulator and a phone on the same Wi-Fi both work. Set EXPO_PUBLIC_MEDIA_BASE to point elsewhere
 * (the Phase 1 backend / S3 later); the fixtures' `/fixtures/<ku>/video.mp4` paths are appended to it.
 */
import Constants from "expo-constants";
import { BACKEND_BASE } from "./backend";

const MEDIA_PORT = 8787;

export function mediaBase(override: string | undefined, hostUri: string | undefined): string | null {
  if (override) return override.replace(/\/+$/, "");
  const host = hostUri?.split(":")[0];
  return host ? `http://${host}:${MEDIA_PORT}` : null;
}

/** A path the server hands out for a made video (`/api/media/...`, signed): on the server, not the media script's host. */
export function backendMediaUrl(path: string, base: string | null = BACKEND_BASE): string | undefined {
  return base ? `${base}${path.startsWith("/") ? "" : "/"}${path}` : undefined;
}

export function mediaUrl(path: string, base = mediaBase(process.env.EXPO_PUBLIC_MEDIA_BASE, Constants.expoConfig?.hostUri)): string | undefined {
  return base ? `${base}${path.startsWith("/") ? "" : "/"}${path}` : undefined;
}
