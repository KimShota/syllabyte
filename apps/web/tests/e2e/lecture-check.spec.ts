import { expect, test } from "@playwright/test";
import { answerCurrent, demoTool, jump, loggedVerbs, stateOf } from "./helpers";

// The check before a lecture (plan/per-ku-profiling-plan.md D8, D9, D11): short, adaptive, no going back, and the
// only moment a level changes, with a card that says what moved and why.

test.describe("the check before a lecture", () => {
  test("is not due right after the baseline, and is due a week later", async ({ page }) => {
    await jump(page, "Playlist");
    await expect(page.getByText("A quick check before this lecture.")).toHaveCount(0);
    await demoTool(page, "Simulate next week (+7 days)");
    await page.goto("/playlist");
    await expect(page.getByText("A quick check before this lecture.")).toBeVisible();
    await expect(page.getByText(/6 questions, about 2 minutes/)).toBeVisible();
  });

  test("runs six adaptive questions, then updates the levels and says what changed", async ({ page }) => {
    await jump(page, "Playlist");
    await demoTool(page, "Simulate next week (+7 days)");
    await page.goto("/playlist");
    await page.getByRole("link", { name: "Start the check" }).click();
    await expect(page).toHaveURL(/check\?l=3/);
    await expect(page.getByRole("heading", { name: "A quick check before this lecture" })).toBeVisible();
    for (let i = 1; i <= 6; i++) {
      await expect(page.getByText(`Question ${i} of 6`)).toBeVisible();
      await expect(page.getByRole("button", { name: "Back", exact: true })).toHaveCount(i === 1 ? 1 : 0);
      await expect(page.getByRole("button", { name: i === 6 ? "Start the lecture" : "Next", exact: true })).toBeDisabled();
      await answerCurrent(page, "not_sure"); // a student who is unsure of everything: levels can only go down
    }
    await expect(page).toHaveURL(/playlist/);
    const verbs = await loggedVerbs(page);
    expect(verbs.filter((v) => v === "cat_answered")).toHaveLength(12 + 6);
    expect(verbs).toEqual(expect.arrayContaining(["cat_finished", "levels_updated"]));
    const s = await stateOf(page);
    expect(s.sittings["lecture-3"].finished_at).not.toBeNull();
    // the check is over, so its card is gone
    await expect(page.getByText("A quick check before this lecture.")).toHaveCount(0);
  });

  test("'Not now' skips it and changes nothing", async ({ page }) => {
    await jump(page, "Playlist");
    const before = (await stateOf(page)).levels;
    await demoTool(page, "Simulate next week (+7 days)");
    await page.goto("/playlist");
    // scoped: a research participant's playlist can also carry a questionnaire card with its own "Not now"
    await page.locator("section").filter({ hasText: "A quick check before this lecture." }).getByRole("button", { name: "Not now" }).click();
    await expect(page.getByText("A quick check before this lecture.")).toHaveCount(0);
    expect((await stateOf(page)).levels).toEqual(before);
  });

  test("closing it part-way and coming back continues where it stopped", async ({ page }) => {
    await jump(page, "Check due");
    await page.getByRole("link", { name: "Start the check" }).click();
    await answerCurrent(page);
    await page.goto("/playlist");
    await expect(page.getByRole("link", { name: "Continue the check" })).toBeVisible();
    await page.getByRole("link", { name: "Continue the check" }).click();
    await expect(page.getByText("Question 2 of 6")).toBeVisible();
  });
});

test.describe("what changed and why", () => {
  test.beforeEach(async ({ page }) => {
    await jump(page, "Levels changed");
  });

  test("lists every level that moved with a sentence built from the student's own answers", async ({ page }) => {
    const card = page.locator("section", { hasText: "What changed and why" });
    await expect(card).toContainText("Your levels moved after the “Randomization” check.");
    await expect(card).toContainText(/Level 1 → 2\. \d+ of \d+ right on “Randomization” so far\./);
    await expect(card).toContainText(/Level 2 → 1\./);
    await expect(card).toContainText("Videos already made keep the level they were made at.");
  });

  test("'Got it' hides it for good, and the levels stay", async ({ page }) => {
    const before = (await stateOf(page)).levels;
    await page.getByRole("button", { name: "Got it" }).click();
    await expect(page.getByText("What changed and why")).toHaveCount(0);
    await page.reload();
    await expect(page.getByText("What changed and why")).toHaveCount(0);
    expect((await stateOf(page)).levels).toEqual(before);
  });

  test("My levels shows the same card, by lecture, with each concept's reason", async ({ page }) => {
    await page.goto("/levels");
    await expect(page.getByText("What changed and why")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Randomization", level: 2 })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Correct this/ })).toHaveCount(20);
  });
});
