import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // The E2E API imports the compiled core package, so rebuild it before the
  // server starts to keep runtime behavior aligned with the TypeScript source.
  globalSetup: "./e2e/global-setup.ts",
  timeout: 60_000,
  // Specs share one API process. Serial execution avoids contention in the
  // streaming authoring flow and makes the deterministic stub reproducible.
  workers: 1,
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  use: {
    baseURL: "http://localhost:4580",
    headless: true,
    screenshot: "only-on-failure",
  },
  // Existing servers are never reused, so a developer process without the
  // deterministic stub cannot issue a real LLM request with test credentials.
  webServer: [
    {
      command: "pnpm exec tsx watch --clear-screen=false src/api/index.ts",
      port: 4581,
      reuseExistingServer: false,
      timeout: 120_000,
      cwd: ".",
      env: {
        INKOS_AGENT_LLM_STUB: "1",
        INKOS_STUDIO_PORT: "4581",
        INKOS_PROJECT_ROOT: "../../test-project",
      },
    },
    {
      command: "pnpm exec vite --host --port 4580",
      url: "http://localhost:4580",
      reuseExistingServer: false,
      timeout: 120_000,
      cwd: ".",
      env: {
        INKOS_AGENT_LLM_STUB: "1",
        INKOS_STUDIO_PORT: "4581",
        INKOS_PROJECT_ROOT: "../../test-project",
      },
    },
  ],
});
