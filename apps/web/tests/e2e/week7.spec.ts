import { expect, test } from "@playwright/test";
import { jump, loggedVerbs, stateOf } from "./helpers";

// A fixed Wednesday morning, so the invite's time slots are the same every run.
const WED_10AM = new Date("2026-10-07T10:00:00");

test.describe("Week 7 invite", () => {
  test.beforeEach(async ({ page }) => {
    await page.clock.setFixedTime(WED_10AM);
    await jump(page, "Week 7 invite");
  });

  test("announces the check-in, not graded, and offers four concrete times", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Time to re-check your level" })).toBeVisible();
    await expect(page.getByText("Not graded").first()).toBeVisible();
    for (const label of ["Now", "Tonight at 8:00 pm", "Tomorrow morning", "Remind me on Friday"]) await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Pick a time" })).toBeDisabled(); // no default: the student chooses
    await expect(page.getByText("Refresher videos wait until you have finished your first pass")).toBeVisible();
  });

  test("scheduling gives a confirmation and a calendar file, and the playlist then pins the check-in", async ({ page }) => {
    await page.getByRole("button", { name: "Tomorrow morning", exact: true }).click();
    await page.getByRole("button", { name: "Schedule for tomorrow morning" }).click();
    await expect(page.getByText("We'll remind you tomorrow at 9:00 am.")).toBeVisible();
    const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Add to calendar (.ics)" }).click()]);
    expect(dl.suggestedFilename()).toMatch(/\.ics$/);
    await page.getByRole("button", { name: "Back to your playlist" }).click();
    await expect(page.getByText("Week 7 check-in · not graded")).toBeVisible();
    await expect(page.getByText(/Scheduled for tomorrow at 9:00 am/)).toBeVisible();
    expect(await loggedVerbs(page)).toContain("recheck_scheduled");
  });

  test("skipping asks first, changes nothing, and leaves a way back on My levels", async ({ page }) => {
    await page.getByRole("button", { name: "Skip this check-in" }).click();
    await expect(page.getByRole("dialog")).toContainText("Your levels stay as they are");
    await page.getByRole("button", { name: "Skip it" }).click();
    await expect(page).toHaveURL(/playlist/);
    await page.getByRole("link", { name: "My levels" }).first().click();
    await expect(page.getByRole("link", { name: "Do the Week 7 check-in" })).toBeVisible();
  });

  test("the 6-question re-check allows 'Not sure yet' and leads to the results", async ({ page }) => {
    await page.goto("/recheck/quiz");
    await expect(page.getByText("Question 1 of 6")).toBeVisible();
    for (let i = 1; i <= 6; i++) {
      await page.locator('section[aria-labelledby="q-stem"] [role=group] button').nth(i % 2).click();
      await page.getByRole("button", { name: i === 6 ? "See what changed" : "Next", exact: true }).click();
    }
    await expect(page).toHaveURL(/recheck\/results/);
    expect((await loggedVerbs(page)).filter((v) => v === "recheck_answered")).toHaveLength(6);
  });
});

test("the playlist opens the invite on the first Week 7 visit, and only until it has been seen", async ({ page }) => {
  await jump(page, "Week 7 re-check quiz"); // loads the Week 7 student without showing the invite
  await page.goto("/playlist");
  await expect(page).toHaveURL(/\/recheck\/?$/);
  await page.goto("/playlist"); // the invite has now been seen
  await expect(page).toHaveURL(/\/playlist$/);
  await expect(page.getByText("Week 7 check-in · not graded")).toBeVisible(); // pinned instead
});

test.describe("Week 7 results", () => {
  test.beforeEach(async ({ page }) => {
    await jump(page, "Week 7 results");
  });

  test("proposes 3 changes (two up, one down) with reasons built from the student's own answers; unchanged topics say Same", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "We suggest 3 changes" })).toBeVisible();
    await expect(page.getByText("Nothing changes until you decide.")).toBeVisible();
    await expect(page.getByText("Level 2 → Level 3 proposed")).toBeVisible();
    await expect(page.getByText("Level 1 → Level 2 proposed")).toBeVisible();
    await expect(page.getByText("Level 2 → Level 1 proposed")).toBeVisible();
    await expect(page.getByText(/\d of \d right, up from \d of \d in Week 1/).first()).toBeVisible();
    await expect(page.getByText("Level 3, no change")).toBeVisible();
    await expect(page.getByText("Same")).toBeVisible();
    await expect(page.locator('[aria-pressed="true"]')).toHaveCount(0); // nothing is preselected
  });

  test("accept two, keep one, apply: levels change, the playlist is rebuilt, and Undo restores everything", async ({ page }) => {
    const group = (t: string) => page.getByRole("group", { name: `Decision for ${t}` });
    await group("Potential outcomes").getByRole("button", { name: "Accept" }).click();
    await group("Selection bias").getByRole("button", { name: "Accept" }).click();
    await group("Randomization in practice").getByRole("button", { name: /Keep Level 2/ }).click();
    await expect(page.getByRole("button", { name: "Apply my choices (2 accepted, 1 kept)" })).toBeVisible();
    await page.getByRole("button", { name: /Apply my choices/ }).click();
    await expect(page).toHaveURL(/playlist/);
    await expect(page.getByRole("status")).toContainText("Playlist updated");
    let s = await stateOf(page);
    expect(s.levels["potential-outcomes"].level).toBe(3);
    expect(s.levels["selection-bias"].level).toBe(2);
    expect(s.levels["randomization"].level).toBe(2);
    await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
    s = await stateOf(page);
    expect(s.levels["potential-outcomes"].level).toBe(2);
    expect(s.levels["selection-bias"].level).toBe(1);
    const verbs = await loggedVerbs(page);
    expect(verbs).toEqual(expect.arrayContaining(["proposal_decided", "playlist_applied", "undo"]));
  });

  test("after applying, My levels says the levels were updated and lists what changed", async ({ page }) => {
    await page.getByRole("group", { name: "Decision for Potential outcomes" }).getByRole("button", { name: "Accept" }).click();
    await page.getByRole("button", { name: /Apply my choices/ }).click();
    await expect(page).toHaveURL(/playlist/);
    await page.getByRole("link", { name: "My levels" }).first().click(); // client-side, so the toast survives
    await expect(page.getByText("Updated at your Week 7 check-in.")).toBeVisible();
    await expect(page.getByText(/went from Level 2 to Level 3 at your Week 7 check-in/)).toBeVisible();
  });

  test("'Tell us why we are wrong' keeps the level and stores the reason", async ({ page }) => {
    const card = page.locator("li", { hasText: "Randomization in practice" });
    await card.getByRole("button", { name: "Tell us why we are wrong" }).click();
    await card.getByRole("textbox").fill("I rushed that day");
    await card.getByRole("button", { name: /Save, keep Level 2/ }).click();
    await expect(card.getByText("Thanks. We'll keep Level 2.")).toBeVisible();
    const p = (await stateOf(page)).recheck.proposals.find((x: { topic_id: string }) => x.topic_id === "randomization");
    expect(p).toMatchObject({ decision: "disputed", dispute_text: "I rushed that day" });
  });

  test("'Keep my old playlist' changes no level", async ({ page }) => {
    await page.getByRole("button", { name: "Keep my old playlist" }).click();
    await expect(page).toHaveURL(/playlist/);
    const s = await stateOf(page);
    expect(s.levels["potential-outcomes"].level).toBe(2);
    expect(s.recheck.mode).toBe("keep_old");
  });

  test("'I will pick the videos myself' applies accepted levels and opens the Course map", async ({ page }) => {
    await page.getByRole("group", { name: "Decision for Potential outcomes" }).getByRole("button", { name: "Accept" }).click();
    await page.getByRole("button", { name: "I will pick the videos myself" }).click();
    await expect(page).toHaveURL(/course/);
    expect((await stateOf(page)).levels["potential-outcomes"].level).toBe(3);
  });

  test("'See every change' lists new, switched and removed videos with a reason each", async ({ page }) => {
    await page.getByRole("group", { name: "Decision for Selection bias" }).getByRole("button", { name: "Accept" }).click();
    await page.getByRole("link", { name: "See every change" }).click();
    await expect(page.getByRole("heading", { name: "Every change" })).toBeVisible();
    await expect(page.getByText(/moves to Level 2/)).toBeVisible();
  });

  test("My levels afterwards shows 'You, since Week 1' and the calibration blocks", async ({ page }) => {
    await jump(page, "My levels, Week 7 student");
    await expect(page.getByText("How sure you were, and how often you were right")).toBeVisible();
    await expect(page.getByText(/no better than “Pretty sure”/)).toBeVisible();
    await expect(page.getByText("Your guess vs the next day")).toBeVisible();
    await expect(page.getByText(/When you said Yes, you got the next-day question right/)).toBeVisible();
    // the re-check was taken but nothing has been applied yet, so the overall card must not claim an update
    await expect(page.getByText("Updated at your Week 7 check-in.")).toHaveCount(0);
    await expect(page.getByText("Set from your Week 1 check. Next check-in: Week 7.")).toBeVisible();
  });
});
