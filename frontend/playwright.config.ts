import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  timeout: 90000,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  snapshotPathTemplate: "{testDir}/{testFilePath}-snapshots/{arg}{ext}",
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:43129", actionTimeout: 15000, navigationTimeout: 45000, trace: "retain-on-failure", screenshot: "only-on-failure", locale: "en-US", timezoneId: "UTC" },
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVER ? undefined : {
    command: "node .next/standalone/server.js",
    url: "http://127.0.0.1:43129/login",
    reuseExistingServer: !process.env.CI,
    env: { PORT: "43129", HOSTNAME: "127.0.0.1", AUTH_MODE: "demo", DEMO_AUTH_ENABLED: "true", ALLOW_PRODUCTION_DEMO: "true", SESSION_SECRET: "playwright-session-secret-at-least-32-characters", BACKEND_API_URL: "http://127.0.0.1:8000" },
    timeout: 120000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "tablet-chromium", use: { ...devices["iPad Mini"], browserName: "chromium" } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
});
