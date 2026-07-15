import { defineConfig, devices } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

const repoRoot = path.resolve(import.meta.dirname, "../../..");
const projectRoot = path.join(repoRoot, "output", "rc1-ui", "project");
const controlPath = path.join(repoRoot, "output", "rc1-ui", "runtime-control.json");
const orchestrator = path.join(repoRoot, "hybrid", "fixtures", "rc1-ui-verification", "orchestrator.mjs");

// Playwright starts web servers before globalSetup, so materialize the fully
// deterministic project while loading this dedicated config.
execFileSync(process.execPath, [orchestrator, "prepare", "--root", projectRoot, "--case", "A", "--control", controlPath], {
  cwd: repoRoot,
  stdio: "ignore",
});

export default defineConfig({
  testDir: "./e2e",
  testMatch: "rc1-chapter-authority.spec.ts",
  globalSetup: "./e2e/rc1-global-setup.ts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  use: { baseURL: "http://127.0.0.1:4590", headless: true, screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: [
    {
      command: `node "${orchestrator}" serve --port 47931 --control "${controlPath}"`,
      port: 47931, reuseExistingServer: false, timeout: 30_000, cwd: repoRoot,
    },
    {
      command: "pnpm exec tsx src/api/index.ts",
      port: 4591, reuseExistingServer: false, timeout: 120_000, cwd: import.meta.dirname,
      env: { INKOS_AGENT_LLM_STUB: "1", INKOS_STUDIO_PORT: "4591", INKOS_PROJECT_ROOT: projectRoot },
    },
    {
      command: "pnpm exec vite --host 127.0.0.1 --port 4590",
      url: "http://127.0.0.1:4590", reuseExistingServer: false, timeout: 120_000, cwd: import.meta.dirname,
      env: { INKOS_AGENT_LLM_STUB: "1", INKOS_STUDIO_PORT: "4591", INKOS_PROJECT_ROOT: projectRoot },
    },
  ],
});
