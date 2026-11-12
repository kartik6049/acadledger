import { defineConfig } from "@playwright/test";

// Needs the backend running and seeded first:
//   docker compose up -d && docker compose exec api python -m app.seed
export default defineConfig({
  testDir: "./e2e",
  // generous: the one test walks the whole demo, and `next dev` compiles each route on first visit
  timeout: 300_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    // Drive the locally installed Chrome; Playwright's bundled Chromium does not
    // support every OS version (macOS 13, for one).
    channel: "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000/login",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
