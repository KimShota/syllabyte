import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { jump, loggedVerbs, stateOf } from "./helpers";

// The study questionnaires (plan/study-instruments-plan.md): in the app, by module, never blocking, any question skippable.

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
async function clean(page: Page, label: string) {
  await page.waitForTimeout(400);
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`), `axe on ${label}`).toEqual([]);
}

/** The questions on the current page, each as its own region. */
const questions = (page: Page) => page.locator("main section[aria-labelledby]");

async function setCondition(page: Page, c: "A" | "B") {
  await page.goto("/welcome?demo=1");
  await page.getByRole("group", { name: "Study condition" }).getByRole("button", { name: new RegExp(`^${c} ·`) }).click();
  await page.keyboard.press("Escape");
}

test("a research participant answers “About you” before the baseline, and skipping is a deliberate step", async ({ page }) => {
  await page.goto("/consent");
  await page.getByRole("button", { name: "I agree to take part" }).click();
  await expect(page.getByRole("heading", { name: "About you" })).toBeVisible();
  await expect(page.getByText("Every question has “Prefer not to say”.")).toBeVisible();

  await page.getByRole("group", { name: /: Year of study$/ }).getByRole("button", { name: "2nd year" }).click();
  await page.getByRole("textbox", { name: "Major or intended major" }).fill("Economics, maybe CS");
  await page.getByRole("group", { name: /: Age$/ }).getByRole("button", { name: "Prefer not to say" }).click();
  // the self-description appears only when chosen
  await expect(page.getByRole("textbox", { name: "In your own words (optional)" })).toHaveCount(0);
  await page.getByRole("group", { name: /: Gender$/ }).getByRole("button", { name: "Prefer to self-describe" }).click();
  await expect(page.getByRole("textbox", { name: "In your own words (optional)" })).toBeVisible();

  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page.getByRole("heading", { name: "Skip 5 questions?" })).toBeVisible();
  await clean(page, "skip sheet");
  await page.getByRole("button", { name: "Go back" }).click();
  await page.getByRole("button", { name: "Finish" }).click();
  await page.getByRole("button", { name: "Skip them" }).click();

  await expect(page.getByRole("heading", { name: "Thank you" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "A quick check, no grade" })).toBeVisible();

  const b = (await stateOf(page)).study.baseline;
  expect(b.submitted_at).not.toBeNull();
  expect(b.answers).toMatchObject({ year: "2nd_year", major: "Economics, maybe CS", age: "prefer_not", gender: "prefer_to_self_describe", gender_text: null, prior_course: null });
  expect(await loggedVerbs(page)).toEqual(expect.arrayContaining(["study_started", "study_submitted"]));
});

test("someone who declines is never asked a questionnaire", async ({ page }) => {
  await page.goto("/consent");
  await page.getByRole("button", { name: "Use SyllaByte without research data" }).click();
  await expect(page.getByRole("heading", { name: "A quick check, no grade" })).toBeVisible();
  await jump(page, "Questionnaire card on Playlist");
  await expect(page.getByRole("heading", { name: "Your playlist" })).toBeVisible();
  await expect(page.getByText("For the study")).toHaveCount(0);
  expect((await stateOf(page)).study).toEqual({});
});

test("module 1's battery: a card on the playlist once the module ends, then four pages for Condition A", async ({ page }) => {
  await setCondition(page, "A");
  await jump(page, "Questionnaire card on Playlist");
  const card = page.locator("section").filter({ hasText: "Module 1 questionnaire" });
  await expect(card).toBeVisible();
  await expect(card.getByText("Not graded, and you can skip any question.")).toBeVisible();
  await clean(page, "/playlist with study cards");
  await card.getByRole("link", { name: "Start" }).click();

  // page 1: Raw TLX, a 0-100 line with nothing preselected
  await expect(page.getByText("Page 1 of 4")).toBeVisible();
  await expect(page.getByRole("heading", { name: "How demanding was it?", exact: true })).toBeVisible();
  const sliders = page.getByRole("slider");
  await expect(sliders).toHaveCount(6);
  await expect(page.getByText("Tap the line")).toHaveCount(6);
  await clean(page, "/study TLX");
  for (let i = 0; i < 6; i++) {
    await sliders.nth(i).scrollIntoViewIfNeeded();
    const box = (await sliders.nth(i).boundingBox())!;
    await page.mouse.click(box.x + box.width * (i === 0 ? 0.85 : 0.5), box.y + box.height / 2);
  }
  await expect(page.getByText("Tap the line")).toHaveCount(0);
  await page.getByRole("button", { name: "Next" }).click();

  // page 2: learning efficacy, 12 items on 1-7
  await expect(page.getByRole("heading", { name: "Learning with these videos", exact: true })).toBeVisible();
  await expect(questions(page)).toHaveCount(12);
  for (let i = 0; i < 12; i++) await questions(page).nth(i).getByRole("button", { name: "6", exact: true }).click();
  await clean(page, "/study efficacy");
  await page.getByRole("button", { name: "Next" }).click();

  // page 3: SUS, 10 items on 1-5; leave one blank
  await expect(page.getByRole("heading", { name: "Using the app", exact: true })).toBeVisible();
  for (let i = 0; i < 9; i++) await questions(page).nth(i).getByRole("button", { name: /^4/ }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("heading", { name: "Skip 1 question?" })).toBeVisible();
  await page.getByRole("button", { name: "Skip it" }).click();

  // page 4: trust, Condition A only
  await expect(page.getByRole("heading", { name: "Trust in SyllaByte", exact: true })).toBeVisible();
  await expect(page.getByText("SyllaByte here means the AI system that made your videos.")).toBeVisible();
  await expect(questions(page)).toHaveCount(16);
  for (let i = 0; i < 16; i++) await questions(page).nth(i).getByRole("button", { name: /^5/ }).click();
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page.getByRole("heading", { name: "Thank you" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Your playlist" })).toBeVisible();
  await expect(page.getByText("Module 1 questionnaire")).toHaveCount(0);
  const m1 = (await stateOf(page)).study["module-1"];
  expect(m1.answers.tlx_mental).toBeGreaterThan(70);
  expect(m1.answers.tlx_physical).toBe(50);
  expect(m1.answers.eff_12).toBe(6);
  expect(m1.answers.sus_10).toBeNull();
  expect(m1.answers.trust_16).toBe(5);
});

test("Condition B gets three pages, with no trust scale", async ({ page }) => {
  await setCondition(page, "B");
  await jump(page, "Module 1 questionnaire");
  await expect(page.getByText("Page 1 of 3")).toBeVisible();
  expect((await stateOf(page)).condition).toBe("B");
});

test("“Not now” hides a questionnaire until the next visit, and leaving mid-way resumes where it stopped", async ({ page }) => {
  await setCondition(page, "A");
  await jump(page, "Questionnaire card on Playlist");
  const card = page.locator("section").filter({ hasText: "Module 1 questionnaire" });
  await card.getByRole("link", { name: "Start" }).click();
  await expect(page.getByText("Page 1 of 4")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Skip them" }).click();
  await expect(page.getByText("Page 2 of 4")).toBeVisible();
  await page.getByRole("button", { name: "Close, your answers are saved" }).click();

  await expect(card.getByRole("link", { name: "Continue" })).toBeVisible();
  await card.getByRole("link", { name: "Continue" }).click();
  await expect(page.getByText("Page 2 of 4")).toBeVisible();
  await page.getByRole("button", { name: "Close, your answers are saved" }).click();

  await card.getByRole("button", { name: "Not now" }).click();
  await expect(page.getByText("Module 1 questionnaire")).toHaveCount(0);
  expect(await loggedVerbs(page)).toContain("study_snoozed");
});
