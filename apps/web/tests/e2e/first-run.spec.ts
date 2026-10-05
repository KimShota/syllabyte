import { expect, test } from "@playwright/test";
import { loggedVerbs, stateOf } from "./helpers";

test("welcome → consent → onboarding → result → playlist, with events", async ({ page }) => {
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

  // onboarding: 8 questions, Next is disabled until an answer is chosen, nothing preselected
  await expect(page.getByRole("heading", { name: "A quick check, no grade" })).toBeVisible();
  for (let i = 1; i <= 8; i++) {
    await expect(page.getByText(`Question ${i} of 8`)).toBeVisible();
    const next = page.getByRole("button", { name: i === 8 ? "See my levels" : "Next", exact: true });
    await expect(next).toBeDisabled();
    // alternate: pick the first option, or "Not sure yet"
    if (i % 3 === 0) await page.getByRole("button", { name: "Not sure yet" }).click();
    else await page.locator('section[aria-labelledby="q-stem"] [role=group] button').first().click();
    await expect(next).toBeEnabled();
    await next.click();
  }

  // result: an overall level, per-topic levels with reasons, answers to review
  await expect(page).toHaveURL(/onboarding\/result/);
  await expect(page.getByRole("heading", { name: /We suggest Level \d · / })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Causal questions" })).toBeVisible();
  await page.getByRole("button", { name: "Review my answers" }).click();
  await expect(page.getByText("Right answer:").first()).toBeVisible();
  await page.getByRole("button", { name: "Keep these levels" }).click();
  await expect(page).toHaveURL(/playlist/);

  const verbs = await loggedVerbs(page);
  expect(verbs.filter((v) => v === "onboarding_answered")).toHaveLength(8);
  for (const v of ["consent_given", "level_suggested", "level_kept", "playlist_viewed"]) expect(verbs).toContain(v);
  const s = await stateOf(page);
  expect(s.consent).toBe("research");
  expect(Object.keys(s.levels)).toHaveLength(4);
});

test("a student who declines research still gets the whole app", async ({ page }) => {
  await page.goto("/consent");
  await page.getByRole("button", { name: "Use SyllaByte without research data" }).click();
  await expect(page.getByRole("heading", { name: "A quick check, no grade" })).toBeVisible();
  expect((await stateOf(page)).consent).toBe("no_research");
});

test("'Pick my own level' leaves the quiz and sets every topic", async ({ page }) => {
  await page.goto("/consent");
  await page.getByRole("button", { name: "I agree to take part" }).click();
  await page.getByRole("button", { name: "Pick my own level" }).click();
  await page.getByRole("button", { name: /Level 3 · Advanced/ }).click();
  await page.getByRole("button", { name: "Use this level" }).click();
  await expect(page).toHaveURL(/onboarding\/result/);
  const s = await stateOf(page);
  expect(Object.values(s.levels as Record<string, { level: number; source: string }>).every((l) => l.level === 3 && l.source === "student")).toBe(true);
  expect(s.onboarding.picked_own).toBe(true);
});

test("the gate sends a new visitor to Welcome", async ({ page }) => {
  await page.goto("/playlist");
  await expect(page).toHaveURL(/welcome/);
});
