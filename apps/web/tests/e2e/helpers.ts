import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const fx = (f: string) => JSON.parse(readFileSync(join(__dirname, "../../fixtures", f), "utf8"));
export const VIDEOS = fx("videos.json") as { id: string; short_title: string; duration_s: number; checkpoint: { t: number; rewatch_from: number; item_id: string }; lecture_n: number; prove_it_item_id: string; claims: { text: string }[] }[];
export const ITEMS = fx("items.json") as { id: string; correct_index: number; options: string[]; stem: string; hint: string | null }[];
export const item = (id: string) => ITEMS.find((i) => i.id === id)!;

/** Opens the hidden demo menu and runs one jump (plan §3.17). */
export async function jump(page: Page, label: string) {
  await page.goto("/welcome?demo=1");
  await page.getByRole("button", { name: label, exact: true }).click();
  await page.waitForLoadState("networkidle");
}

/** Verbs of every event stored so far (the demo's local log). Persistence is debounced, so wait for it. */
export async function loggedVerbs(page: Page): Promise<string[]> {
  await page.waitForTimeout(150);
  return page.evaluate(() => (JSON.parse(localStorage.getItem("syllabyte.demo.v2") ?? "{}").events ?? []).map((e: { verb: string }) => e.verb));
}

export async function stateOf(page: Page) {
  await page.waitForTimeout(120); // persistence is debounced
  return page.evaluate(() => JSON.parse(localStorage.getItem("syllabyte.demo.v2") ?? "{}"));
}

/** Fast-forwards the Week 0 baseline (a mixed student) and lands on the playlist. */
export async function toPlaylist(page: Page) {
  await jump(page, "Playlist");
  await expect(page.getByRole("heading", { name: "Your playlist" })).toBeVisible();
}

/** Seeks to just before the quick check and plays until it appears. */
export async function playToCheckpoint(page: Page, videoId: string) {
  const v = VIDEOS.find((x) => x.id === videoId)!;
  await page.goto(`/watch?v=${videoId}`);
  const el = page.locator("video");
  await expect(el).toHaveJSProperty("readyState", 4, { timeout: 15000 }).catch(() => undefined);
  await page.waitForFunction(() => ((document.querySelector("video") as HTMLVideoElement | null)?.readyState ?? 0) >= 1, undefined, { timeout: 15000 });
  await page.evaluate((t) => ((document.querySelector("video") as HTMLVideoElement).currentTime = t), v.checkpoint.t - 1.2);
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByText("Video paused · quick check")).toBeVisible({ timeout: 15000 });
  return v;
}

/** Watches a video to its end: seeking past the quick check still shows it first, so answer-skip it, then finish. */
export async function finishVideo(page: Page, videoId: string) {
  const v = VIDEOS.find((x) => x.id === videoId)!;
  await page.goto(`/watch?v=${videoId}`);
  await page.waitForFunction(() => ((document.querySelector("video") as HTMLVideoElement | null)?.readyState ?? 0) >= 1, undefined, { timeout: 15000 });
  const toEnd = () => page.evaluate((d) => ((document.querySelector("video") as HTMLVideoElement).currentTime = d - 0.8), v.duration_s);
  await toEnd();
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByText("Video paused · quick check")).toBeVisible({ timeout: 15000 });
  await toEnd();
  await page.getByRole("button", { name: "Skip this check" }).click();
  await expect(page).toHaveURL(/watch\/done/, { timeout: 20000 });
}

/** Opens the demo menu on any screen and runs one tool (e.g. "Simulate next week (+7 days)"). */
export async function demoTool(page: Page, label: string, path = "/playlist") {
  await page.goto(`${path}${path.includes("?") ? "&" : "?"}demo=1`);
  await page.getByRole("button", { name: label, exact: true }).click();
  await page.waitForLoadState("networkidle");
}

/** Answers the question a sitting is on with its first option (or "Not sure yet"), then presses the footer button. */
export async function answerCurrent(page: Page, how: "first" | "not_sure" = "first") {
  if (how === "not_sure") await page.getByRole("button", { name: "Not sure yet" }).click();
  else await page.locator('section[aria-labelledby="q-stem"] [role=group] button').first().click();
  await page.getByRole("button", { name: /^(Next|See my levels|Start the lecture)$/ }).click();
}

/** After "I agree", research participants get "About you" first (plan/study-instruments-plan.md I6); close it for later. */
export async function closeAboutYou(page: Page) {
  await expect(page.getByRole("heading", { name: "About you" })).toBeVisible();
  await page.getByRole("button", { name: "Close, your answers are saved" }).click();
  await expect(page).toHaveURL(/onboarding/);
}
