import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { closeAboutYou, jump, toPlaylist, VIDEOS } from "./helpers";

// Plan §11/§12: WCAG 2.2 AA on every route and the sheets, in CI.
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function clean(page: Page, label: string) {
  await page.waitForTimeout(400);
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const summary = violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(summary, `axe violations on ${label}`).toEqual([]);
}

test("first-run screens", async ({ page }) => {
  await page.goto("/welcome");
  await clean(page, "/welcome");
  await page.goto("/consent");
  await clean(page, "/consent");
  await page.getByRole("button", { name: "Read the full consent form" }).click();
  await clean(page, "consent form sheet");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "I agree to take part" }).click();
  await expect(page.getByRole("heading", { name: "About you" })).toBeVisible();
  await clean(page, "/study, About you");
  await closeAboutYou(page);
  await clean(page, "/onboarding");
  await page.getByRole("button", { name: "Not sure yet" }).click();
  await clean(page, "/onboarding answered");
  await page.getByRole("button", { name: "Pick my own level" }).click();
  await clean(page, "level picker sheet");
});

test("the tabs, the result screen and their sheets", async ({ page }) => {
  await jump(page, "Start result");
  await clean(page, "/onboarding/result");
  await page.getByRole("button", { name: "See each concept" }).first().click();
  await clean(page, "/onboarding/result, a lecture open");
  await toPlaylist(page);
  await clean(page, "/playlist");
  await page.getByRole("button", { name: /^More options for/ }).first().click();
  await clean(page, "playlist ⋮ sheet");
  await page.keyboard.press("Escape");
  await page.goto("/levels");
  await clean(page, "/levels");
  await page.getByRole("button", { name: /^Correct this/ }).first().click();
  await clean(page, "change level sheet");
  await page.keyboard.press("Escape");
  await page.goto("/course");
  await page.getByText("Course info & settings").click();
  await clean(page, "/course");
});

test("the player, its sheets and the screens around it", async ({ page }) => {
  await toPlaylist(page);
  await page.goto(`/watch?v=${VIDEOS[0].id}`);
  await clean(page, "/watch");
  for (const sheet of ["receipt", "about"]) {
    await page.goto(`/watch?v=${VIDEOS[0].id}&sheet=${sheet}`);
    await clean(page, `/watch sheet ${sheet}`);
  }
  await page.goto(`/watch?v=${VIDEOS[0].id}`);
  await page.getByRole("button", { name: "Transcript" }).click();
  await clean(page, "transcript sheet");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Notes" }).click();
  await clean(page, "notes sheet");
  await page.keyboard.press("Escape");
  await page.goto(`/watch/claims?v=${VIDEOS[0].id}`);
  await clean(page, "/watch/claims");
  await page.getByRole("button", { name: "View slide" }).first().click();
  await clean(page, "slide sheet");
  await page.keyboard.press("Escape");
  await page.goto(`/watch/done?v=${VIDEOS[0].id}`);
  await clean(page, "/watch/done");
});

test("the quick check, unanswered and revealed", async ({ page }) => {
  await toPlaylist(page);
  const { playToCheckpoint } = await import("./helpers");
  await playToCheckpoint(page, VIDEOS[0].id);
  await clean(page, "quick check");
  await page.locator('section[aria-labelledby="cp-stem"] [role=group]').first().locator("button").first().click();
  await clean(page, "quick check, confidence row");
  await page.getByRole("button", { name: "Pretty sure" }).click();
  await clean(page, "quick check, revealed");
});

test("the lecture check, its card, and the card that says what changed", async ({ page }) => {
  await jump(page, "Check due");
  await expect(page.getByText("A quick check before this lecture.")).toBeVisible();
  await clean(page, "/playlist with the check card");
  await jump(page, "Lecture 3 check quiz");
  await clean(page, "/check");
  await page.getByRole("button", { name: "Not sure yet" }).click();
  await clean(page, "/check answered");
  await jump(page, "Levels changed");
  await expect(page.getByText("What changed and why")).toBeVisible();
  await clean(page, "/playlist with the what-changed card");
  await jump(page, "My levels, mid-course student");
  await clean(page, "/levels (mid-course)");
});

test("the facilitator pages", async ({ page }) => {
  await page.goto("/debug/events");
  await clean(page, "/debug/events");
});
