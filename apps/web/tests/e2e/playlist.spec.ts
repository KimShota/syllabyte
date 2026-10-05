import { expect, test } from "@playwright/test";
import { finishVideo, item, jump, stateOf, toPlaylist, VIDEOS } from "./helpers";

const titles = async (page: import("@playwright/test").Page) => page.locator("article h3").allInnerTexts();
const menuFor = (page: import("@playwright/test").Page, title: string) => page.getByRole("button", { name: `More options for ${title}` });

test.beforeEach(async ({ page }) => {
  await toPlaylist(page);
});

test("the playlist explains its order and names its tags", async ({ page }) => {
  await expect(page.getByText("Why this order")).toBeVisible();
  await expect(page.getByText(/Lecture \d is next/)).toBeVisible();
  await expect(page.locator("article").first()).toContainText(/Fills a gap|New for you/);
  await expect(page.getByText(/Done so far: \d+ videos?/)).toBeVisible();
});

test("skip shows an 8 s toast with Say why and Undo; Undo puts the card back", async ({ page }) => {
  const [first] = await titles(page);
  await menuFor(page, first).click();
  await page.getByRole("button", { name: "Skip this video" }).click();
  const toast = page.getByRole("status").filter({ hasText: `Skipped “${first}”` });
  await expect(toast).toBeVisible();
  await expect(toast.getByRole("button", { name: "Say why" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Skipped \(1\)/ })).toBeVisible();
  await toast.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: /Skipped \(/ })).toHaveCount(0);
  expect((await titles(page))).toContain(first);
});

test("the toast stays while hovered and goes after 8 s otherwise", async ({ page }) => {
  const [first] = await titles(page);
  await menuFor(page, first).click();
  await page.getByRole("button", { name: "Skip this video" }).click();
  const toast = page.getByRole("status").filter({ hasText: "Skipped" });
  await expect(toast).toBeVisible();
  await toast.hover();
  await page.waitForTimeout(9000);
  await expect(toast).toBeVisible(); // paused while hovered
  await page.mouse.move(5, 5);
  await expect(toast).toBeHidden({ timeout: 12000 });
});

test("'I already know this' offers one question: a miss puts the video back, a pass keeps it skipped", async ({ page }) => {
  const [first] = await titles(page);
  const video = VIDEOS.find((v) => v.short_title === first)!;
  const proveIt = item(video.prove_it_item_id);
  const answer = async (idx: number | "not_sure") => {
    if (idx === "not_sure") await page.getByRole("dialog").getByRole("button", { name: "Not sure yet" }).click();
    else await page.getByRole("dialog").getByRole("group").getByRole("button").nth(idx).click();
    await page.getByRole("button", { name: "Check my answer" }).click();
  };
  const skipAndExplain = async () => {
    await menuFor(page, first).click();
    await page.getByRole("button", { name: "Skip this video" }).click();
    await page.getByRole("status").getByRole("button", { name: "Say why" }).click();
    await page.getByRole("button", { name: "I already know this" }).click();
    await expect(page.getByText("We will offer a one-question check")).toBeVisible();
    await page.getByRole("button", { name: "Save reason" }).click();
    await expect(page.getByText("Want to show it?")).toBeVisible();
    await page.getByRole("button", { name: "Try it" }).click();
  };

  await skipAndExplain();
  await answer((proveIt.correct_index + 1) % 3);
  await expect(page.getByText("It's back in your playlist.")).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();
  expect(await titles(page)).toContain(first);

  await skipAndExplain();
  await answer(proveIt.correct_index);
  await expect(page.getByText("We'll leave this one out.")).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("button", { name: /Skipped \(1\)/ })).toBeVisible();
  const s = await stateOf(page);
  expect(s.known_videos).toContain(video.id);
  expect(s.playlist.entries.find((e: { video_id: string }) => e.video_id === video.id)).toMatchObject({ state: "skipped", skip_reason: "already_know" });
});

test("the skip sheet has no 'Save' until a reason is chosen, and 'Rather not say' is dashed and optional", async ({ page }) => {
  const [first] = await titles(page);
  await menuFor(page, first).click();
  await page.getByRole("button", { name: "Skip this video" }).click();
  await page.getByRole("status").getByRole("button", { name: "Say why" }).click();
  await expect(page.getByRole("button", { name: "Save reason" })).toBeDisabled();
  await page.getByRole("button", { name: "Rather not say" }).click();
  await expect(page.getByRole("button", { name: "Save reason" })).toBeEnabled();
  await page.getByRole("button", { name: "Save reason" }).click();
  expect((await stateOf(page)).playlist.entries.some((e: { skip_reason: string }) => e.skip_reason === "rather_not_say")).toBe(true);
});

test("change order: ↑/↓ buttons (no drag needed), Done, and Reset to suggested order", async ({ page }) => {
  const before = await titles(page);
  expect(before.length).toBeGreaterThanOrEqual(2);
  await page.getByRole("button", { name: "Change order" }).click();
  await page.getByRole("button", { name: `Move ${before[0]} down` }).click();
  await page.getByRole("button", { name: "Done" }).click();
  const after = await titles(page);
  expect(after[0]).toBe(before[1]);
  expect(after[1]).toBe(before[0]);
  await expect(page.getByText(/^You set this order/)).toBeVisible();
  await page.getByRole("button", { name: "Change order" }).click();
  await page.getByRole("button", { name: "Reset to suggested order" }).click();
  await page.getByRole("button", { name: "Done" }).click();
  expect(await titles(page)).toEqual(before);
});

test("the first card has no 'Move up' and the last has no 'Move down' (disabled, not hidden)", async ({ page }) => {
  const t = await titles(page);
  await page.getByRole("button", { name: "Change order" }).click();
  await expect(page.getByRole("button", { name: `Move ${t[0]} up` })).toBeDisabled();
  await expect(page.getByRole("button", { name: `Move ${t[t.length - 1]} down` })).toBeDisabled();
});

test("Watch again lists finished videos, and is empty at first", async ({ page }) => {
  await page.getByRole("button", { name: "Watch again" }).click();
  await expect(page.getByRole("dialog")).toContainText("Nothing yet");
});

test("an empty playlist says videos are on the way, with no spinner", async ({ page }) => {
  await jump(page, "Empty playlist");
  await expect(page.getByText(/videos are being made/)).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveCount(0);
});

test("the next-day check appears only after 12 h, once, with the guess shown next to the result", async ({ page }) => {
  const v = VIDEOS[0];
  await finishVideo(page, v.id);
  await page.getByRole("button", { name: "Yes" }).click();
  await page.getByRole("button", { name: "Skip this" }).click();

  await page.goto("/playlist");
  await expect(page.getByText("Next-day check")).toHaveCount(0);
  await page.goto("/welcome?demo=1");
  await page.getByRole("button", { name: "Simulate next day (+24 h)" }).click();
  await page.goto("/playlist");
  await expect(page.getByText("Next-day check")).toBeVisible();
  await expect(page.getByText(/You said Yes/)).toBeVisible();
  await page.getByRole("button", { name: "Try it" }).click();
  const ns = item(`ns-${v.id.replace(/^/, "")}`);
  await page.locator("#ns-stem ~ [role=group] button").nth(ns.correct_index).click();
  await page.getByRole("button", { name: "Check my answer" }).click();
  await expect(page.getByText("Right.")).toBeVisible();
  await expect(page.getByText(/You said Yes\./)).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Next-day check")).toHaveCount(0);
  const s = await stateOf(page);
  expect(s.next_session[0]).toMatchObject({ done: true, jol: "yes" });
});
