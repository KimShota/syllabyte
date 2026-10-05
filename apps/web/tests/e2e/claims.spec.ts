import { expect, test } from "@playwright/test";
import { jump, loggedVerbs, stateOf, VIDEOS } from "./helpers";

const V = VIDEOS[0];

test.beforeEach(async ({ page }) => {
  await jump(page, "Claim check");
});

test("lists the claims, each with its slides, and starts with no verdict", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Check it against the slides" })).toBeVisible();
  await expect(page.locator("li", { hasText: "View slide" })).toHaveCount(V.claims.length);
  await expect(page.getByText(/Slides · /).first()).toBeVisible();
  await expect(page.getByText("Slides · slides")).toHaveCount(0);
  await expect(page.getByText("What happens to a report")).toBeVisible();
  await expect(page.locator('[aria-pressed="true"]')).toHaveCount(0);
});

test("View slide shows the slide image, its text for screen readers, and plays just this claim's part", async ({ page }) => {
  await page.getByRole("button", { name: "View slide" }).first().click();
  const dlg = page.getByRole("dialog");
  const img = dlg.getByRole("img", { name: /^Slide \d+$/ }).first();
  await expect(img).toBeVisible();
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(100);
  await expect(dlg.getByText("Slide text:").first()).toBeVisible();
  await dlg.getByRole("button", { name: /Play this part/ }).click();
  await expect.poll(() => page.evaluate(() => (document.querySelectorAll("video")[0] as HTMLVideoElement).currentTime)).toBeGreaterThan(0);
  expect(await loggedVerbs(page)).toContain("claim_slide_viewed");
});

test("'Does not match' asks for an optional note and flags the video; 'Matches' does not", async ({ page }) => {
  const first = page.locator("li", { hasText: "View slide" }).first();
  await first.getByRole("button", { name: "Matches", exact: true }).click();
  await expect(first.getByRole("button", { name: "Matches", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("link", { name: "Back to the video" }).click();
  await expect(page).toHaveURL(/\/watch\?v=/); // the badge text also exists on the claims page, so wait for the player
  await expect(page.getByText("Not yet reviewed by your instructor")).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/watch\/claims/);
  await first.getByRole("button", { name: "Does not match" }).click();
  await first.getByRole("textbox").fill("the slide says 4.5, not 4");
  await first.getByRole("textbox").blur();
  const s = await stateOf(page);
  expect(Object.values(s.claims)[0]).toMatchObject({ verdict: "mismatch", note: "the slide says 4.5, not 4" });
  await page.getByRole("button", { name: "Back to the video" }).click();
  await expect(page).toHaveURL(/\/watch\?v=/);
  await expect(page.getByText("A student flagged part of this video · being checked")).toBeVisible();
  expect(await loggedVerbs(page)).toContain("claim_verdict");
});
