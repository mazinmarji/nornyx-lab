import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  /**
   * One worker, not merely one test at a time per file.
   *
   * `fullyParallel: false` serialises within a file but still runs separate
   * spec files concurrently. Every test here drives the same academy service
   * and the same learner record, and each begins by POSTing
   * /api/v1/progress/reset — so a second worker resets the database underneath
   * a journey already in progress. That surfaced the moment a second spec file
   * existed, as an unrelated-looking failure in the first file.
   */
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  /**
   * Most assertions here follow a real engine execution, not a re-render. A
   * lesson run spawns the Nornyx CLI in an isolated per-run workspace, which
   * takes about 7s on a Windows laptop and slows further as a serial suite
   * loads the service; Playwright's 5s assertion default is under that, so
   * three tests failed locally while passing in 18.9s on Linux CI. These are
   * ceilings, not waits — a passing run is no slower for raising them, and
   * nothing about what is asserted changes.
   */
  timeout: 120_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  /**
   * Two projects, deliberately disjoint.
   *
   * `chromium` is the regression suite. `journey` produces reviewer-facing
   * screenshots and is excluded from it, because capture is not a correctness
   * check: a screenshot shows presentation at a captured state, and the specs
   * remain the evidence that the journey behaved correctly. Running them
   * together would blur that, and would put capture files into every ordinary
   * test run.
   */
  projects: [
    {
      name: "chromium",
      testMatch: /.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "journey",
      testMatch: /.*\.capture\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : [
        {
          command: "uv run --project .. uvicorn nornyx_lab.academy.app:app --host 127.0.0.1 --port 8000",
          url: "http://127.0.0.1:8000/api/v1/health",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
        },
        {
          command: "npm run preview -- --host 127.0.0.1",
          url: "http://127.0.0.1:4173",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
        },
      ],
});
