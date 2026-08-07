import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
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
