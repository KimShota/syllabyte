import { expect, test } from "@playwright/test";
import { answerCurrent, closeAboutYou, loggedVerbs, stateOf } from "./helpers";

test("welcome → consent → baseline → result → playlist, with events", async ({ page }) => {
  await page.goto("/welcome");
  await expect(page.getByRole("heading", { name: "Short videos from your own course" })).toBeVisible();
  await page.getByRole("link", { name: "Get started" }).click();

  // consent: two equal choices, and the full text is one tap away
  await expect(page.getByRole("button", { name: "I agree to take part" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Use SyllaByte without research data" })).toBeVisible();
  await page.getByRole("button", { name: "Read the full consent form" }).click();
  await expect(page.getByText("TODO: replace this placeholder")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "I agree to take part" }).click();
  await closeAboutYou(page);

  // the baseline: 12 adaptive questions, Next is disabled until an answer is chosen, nothing preselected, no going back
  await expect(page.getByRole("heading", { name: "A quick check, no grade" })).toBeVisible();
  await expect(page.getByText("Each question adapts to your last answer, so you can't go back.")).toBeVisible();
  for (let i = 1; i <= 12; i++) {
    await expect(page.getByText(`Question ${i} of 12`)).toBeVisible();
    const next = page.getByRole("button", { name: i === 12 ? "See my levels" : "Next", exact: true });
    await expect(next).toBeDisabled();
    // Back (the arrow and the footer button) exists on the first question only; after that there is no going back
    await expect(page.getByRole("button", { name: "Back", exact: true })).toHaveCount(i === 1 ? 2 : 0);
    // alternate: pick the first option, or "Not sure yet"
    if (i % 3 === 0) await page.getByRole("button", { name: "Not sure yet" }).click();
    else await page.locator('section[aria-labelledby="q-stem"] [role=group] button').first().click();
    await expect(next).toBeEnabled();
    await next.click();
  }

  // result: an overall level, a summary per lecture that opens into its concepts, answers to review
  await expect(page).toHaveURL(/onboarding\/result/);
  await expect(page.getByRole("heading", { name: /We suggest Level \d · / })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Causal questions and potential outcomes" })).toBeVisible();
  await page.getByRole("button", { name: "See each concept" }).first().click();
  await expect(page.getByRole("heading", { name: "Random assignment" })).toBeVisible();
  await page.getByRole("button", { name: "Review my answers" }).click();
  await expect(page.getByText("Right answer:").first()).toBeVisible();
  await page.getByRole("button", { name: "Keep these levels" }).click();
  await expect(page).toHaveURL(/playlist/);

  const verbs = await loggedVerbs(page);
  expect(verbs.filter((v) => v === "cat_answered")).toHaveLength(12);
  for (const v of ["consent_given", "cat_finished", "level_suggested", "level_kept", "playlist_viewed"]) expect(verbs).toContain(v);
  const s = await stateOf(page);
  expect(s.consent).toBe("research");
  expect(s.sittings.week0.finished_at).not.toBeNull();
  expect(Object.keys(s.levels)).toHaveLength(20); // one level per Knowledge Unit
});

test("closing the tab mid-check resumes on the same question", async ({ page }) => {
  await page.goto("/consent");
  await page.getByRole("button", { name: "I agree to take part" }).click();
  await closeAboutYou(page);
  await answerCurrent(page);
  await answerCurrent(page);
  await expect(page.getByText("Question 3 of 12")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Question 3 of 12")).toBeVisible();
});

test("a student who declines research still gets the whole app", async ({ page }) => {
  await page.goto("/consent");
  await page.getByRole("button", { name: "Use SyllaByte without research data" }).click();
  await expect(page.getByRole("heading", { name: "A quick check, no grade" })).toBeVisible();
  expect((await stateOf(page)).consent).toBe("no_research");
});

test("'Pick my own level' leaves the check and sets every concept", async ({ page }) => {
  await page.goto("/consent");
  await page.getByRole("button", { name: "I agree to take part" }).click();
  await closeAboutYou(page);
  await page.getByRole("button", { name: "Pick my own level" }).click();
  await page.getByRole("button", { name: /Level 3 · Advanced/ }).click();
  await page.getByRole("button", { name: "Use this level" }).click();
  await expect(page).toHaveURL(/onboarding\/result/);
  const s = await stateOf(page);
  expect(Object.values(s.levels as Record<string, { level: number; source: string }>).every((l) => l.level === 3 && l.source === "student")).toBe(true);
  expect(s.picked_own).toBe(true);
  expect(Object.keys(s.levels)).toHaveLength(20);
});

test("the gate sends a new visitor to Welcome", async ({ page }) => {
  await page.goto("/playlist");
  await expect(page).toHaveURL(/welcome/);
});
