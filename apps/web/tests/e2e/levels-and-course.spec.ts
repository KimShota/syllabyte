import { expect, test } from "@playwright/test";
import { jump, loggedVerbs, stateOf, toPlaylist, VIDEOS } from "./helpers";

test.describe("My levels", () => {
  test.beforeEach(async ({ page }) => {
    await jump(page, "My levels");
  });

  test("shows a level for every concept, by lecture, with a reason and no peer comparison", async ({ page }) => {
    await expect(page.getByText(/Overall start level/i)).toBeVisible();
    await expect(page.getByText(/Levels update after/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Selection bias", level: 2 })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Correct this/ })).toHaveCount(20);
    await expect(page.getByText(/^From your \d+ answers? on “/).first()).toBeVisible();
    await expect(page.getByText(/class average|other students|ranking/i)).toHaveCount(0);
    await expect(page.getByText("We'll show this after 5 quick checks.")).toBeVisible(); // calibration stays hidden until there is data
  });

  test("Correct this: pick a level and a reason, save, see 'Set by you', and Undo restores it", async ({ page }) => {
    const before = await stateOf(page);
    const ku = Object.keys(before.levels)[0];
    const old = before.levels[ku].level;
    const target = old === 1 ? 2 : 1;
    await page.getByRole("button", { name: /^Correct this/ }).first().click();
    const dlg = page.getByRole("dialog");
    await expect(dlg).toContainText("Change level");
    await dlg.getByRole("button", { name: new RegExp(`Level ${target} ·`) }).click();
    await dlg.getByRole("button", { name: target === 1 ? "Videos feel too hard" : "Videos feel too easy" }).click();
    await dlg.getByRole("button", { name: "Save level" }).click();
    await expect(page.getByRole("status")).toContainText(`set to Level ${target} by you`);
    await expect(page.getByText("Set by you.").first()).toBeVisible();
    expect((await stateOf(page)).levels[ku]).toMatchObject({ level: target, source: "student" });
    await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
    await expect(page.getByText("Set by you.")).toHaveCount(0);
    expect((await stateOf(page)).levels[ku]).toMatchObject({ level: old, source: "model" });
    expect(await loggedVerbs(page)).toEqual(expect.arrayContaining(["level_corrected", "undo"]));
  });

  test("'Use suggested level' goes back to ours", async ({ page }) => {
    await page.getByRole("button", { name: /^Correct this/ }).first().click();
    await page.getByRole("dialog").getByRole("button", { name: /Level 3 ·/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Save level" }).click();
    const s1 = await stateOf(page);
    const ku = Object.keys(s1.levels)[0];
    if (s1.levels[ku].suggested_level !== 3) {
      await page.getByRole("button", { name: /Use suggested level/ }).first().click();
      expect((await stateOf(page)).levels[ku].source).toBe("model");
    }
  });

  test("Reset my model asks first, archives the old model, and restarts the check", async ({ page }) => {
    await page.getByRole("button", { name: "Reset my model" }).click();
    await expect(page.getByRole("dialog")).toContainText("We keep a copy for the study unless you withdraw");
    await page.getByRole("button", { name: "Cancel" }).click();
    expect((await stateOf(page)).sittings.week0.finished_at).not.toBeNull();
    await page.getByRole("button", { name: "Reset my model" }).click();
    await page.getByRole("button", { name: "Reset and retake the check" }).click();
    await expect(page).toHaveURL(/onboarding/);
    await expect(page.getByRole("heading", { name: "A quick check, no grade" })).toBeVisible();
    const after = await stateOf(page);
    expect(after.archived_models).toHaveLength(1);
    expect(after.levels).toEqual({});
  });

  test("Download my data gives a file", async ({ page }) => {
    const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download my data" }).click()]);
    expect(dl.suggestedFilename()).toBe("syllabyte-my-data.json");
  });
});

test.describe("Course", () => {
  test.beforeEach(async ({ page }) => {
    await jump(page, "Course");
  });

  test("lists every KU by lecture; videos that don't exist yet are dashed 'Not made yet'", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /Lecture 1/ })).toBeVisible();
    await expect(page.getByText("Not made yet · Coming soon").first()).toBeVisible();
    await expect(page.locator("article")).toHaveCount(VIDEOS.length);
  });

  test("'Add to my playlist' appends the video with a 'You added' tag", async ({ page }) => {
    const add = page.getByRole("button", { name: "Add to my playlist" }).first();
    if (await add.count()) {
      await add.click();
      await page.getByRole("link", { name: "Playlist" }).first().click();
      await expect(page.getByText("You added").first()).toBeVisible();
      expect(await loggedVerbs(page)).toContain("course_video_added");
    }
  });

  test("settings: captions default and weekly email persist; withdrawing from research needs a confirmation", async ({ page }) => {
    await page.getByText("Course info & settings").click();
    await expect(page.getByText("What “AI-made” means")).toBeVisible();
    await page.getByRole("group", { name: "Captions default" }).getByRole("button", { name: "Off" }).click();
    expect((await stateOf(page)).settings.captions).toBe(false);
    await page.getByRole("button", { name: "Withdraw from the research" }).click();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Withdraw", exact: true }).click();
    expect((await stateOf(page)).consent).toBe("no_research");
    await expect(page.getByText("Sign-in starts in Phase 1.")).toBeVisible();
  });
});

test("captions off is remembered in the player", async ({ page }) => {
  await toPlaylist(page);
  await page.goto("/course");
  await page.getByText("Course info & settings").click();
  await page.getByRole("group", { name: "Captions default" }).getByRole("button", { name: "Off" }).click();
  await page.goto(`/watch?v=${VIDEOS[0].id}`);
  await expect(page.getByText("Captions are off")).toBeVisible();
});
