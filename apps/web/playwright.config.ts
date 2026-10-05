import { defineConfig, devices } from "@playwright/test";

// Plan §12: mobile (390×844) and desktop (1280×800). Tests run against the
// static export served locally, using the real fixtures.
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3917", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
  ],
  webServer: {
    command: "npx --yes serve@latest out -l 3917 --no-clipboard",
    url: "http://localhost:3917",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
