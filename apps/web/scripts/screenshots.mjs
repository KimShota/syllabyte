// Dev tool: drives the built static site through the demo menu and saves a screenshot of every
// screen at phone and desktop sizes. Usage: node scripts/screenshots.mjs [outDir]
// Needs the site served on :3917 (npx serve out -l 3917) and a test build (see `npm run shots`).
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium } from "@playwright/test";

const out = resolve(process.argv[2] ?? "shots");
mkdirSync(out, { recursive: true });
const base = process.env.BASE_URL ?? "http://localhost:3917";
const sizes = { mobile: { width: 390, height: 844 }, desktop: { width: 1280, height: 800 } };

const browser = await chromium.launch();
for (const [name, viewport] of Object.entries(sizes)) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: name === "mobile" ? 2 : 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));
  const shot = async (label) => {
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(out, `${name}-${label}.png`), fullPage: false });
  };
  const jump = async (label, file) => {
    await page.goto(`${base}/welcome?demo=1`);
    await page.getByRole("button", { name: label, exact: true }).click();
    await page.waitForLoadState("networkidle");
    await shot(file);
  };

  await page.goto(`${base}/welcome`);
  await shot("01-welcome");
  await page.getByRole("link", { name: "Get started" }).click();
  await shot("02-consent");
  await page.getByRole("button", { name: "I agree to take part" }).click();
  await page.waitForURL("**/onboarding");
  await shot("03-onboarding-q1");
  await page.getByRole("button", { name: "Not sure yet" }).click();
  await shot("04-onboarding-q1-answered");

  await jump("Start result", "05-start-result");
  await jump("Playlist", "06-playlist");
  await jump("My levels", "07-levels-fresh");
  await jump("Course", "08-course");
  await jump("Player: Reading a Difference-in-Means Table", "09-player");
  await jump("Tailoring receipt", "10-receipt");
  await jump("About this video", "11-about");
  await jump("Claim check", "12-claims");
  await jump("Before you move on", "13-done");
  await jump("Check due", "14-playlist-check-due");
  await jump("Lecture 3 check quiz", "15-lecture-check");
  await jump("Levels changed", "16-playlist-levels-changed");
  await jump("My levels, mid-course student", "17-levels-midcourse");
  await jump("Empty playlist", "18-empty-playlist");
  if (errors.length) console.log(`[${name}] browser errors:\n  ` + [...new Set(errors)].join("\n  "));
  await ctx.close();
}
await browser.close();
console.log("screenshots in", out);
