import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const repoRoot = path.resolve(import.meta.dirname, "../../../..");
const projectRoot = path.join(repoRoot, "output", "rc1-ui", "project");
const controlPath = path.join(repoRoot, "output", "rc1-ui", "runtime-control.json");
const orchestrator = path.join(repoRoot, "hybrid", "fixtures", "rc1-ui-verification", "orchestrator.mjs");
const projectId = "rc1-ui-verification";
const runtimeBody = "Runtime chapter two authority sentinel.";
const runtimeHash = createHash("sha256").update(runtimeBody).digest("hex");

function prepare(localCase: string, fault = "healthy") {
  execFileSync(process.execPath, [orchestrator, "prepare", "--root", projectRoot, "--case", localCase, "--fault", fault, "--control", controlPath], { stdio: "pipe" });
}

function recover() {
  prepare("D", "healthy");
}

async function openSettings(page: Page) {
  await page.goto("/#/");
  await page.goto(`/#/book/${projectId}/settings`);
}

test.describe("RC-1 Studio Chromium authority matrix", () => {
  for (const localCase of ["A", "B", "C", "D", "E", "F"]) {
    test(`case ${localCase} keeps every Studio chapter surface on Runtime revision 7`, async ({ page }) => {
      prepare(localCase);
      await page.goto("/#/");
      await expect(page.getByText("RC-1 UI Verification", { exact: true }).first()).toBeVisible();
      await expect(page.getByText(/3 chapters/i).first()).toBeVisible();
      await expect(page.getByText(/99 chapters/i)).toHaveCount(0);

      await openSettings(page);
      await expect(page.getByTestId("runtime-count")).toHaveText("3");
      await expect(page.getByTestId("runtime-latest")).toHaveText("3");
      await expect(page.getByTestId("runtime-revision")).toHaveText("7");
      await expect(page.getByText("Runtime Chapter 4")).toHaveCount(0);
      await expect(page.getByText(/LOCAL FAKE|LOCAL CONFLICTING|latest 99/i)).toHaveCount(0);

      await page.getByRole("button", { name: "Runtime Chapter 2" }).click();
      const detail = page.getByTestId("runtime-chapter-detail");
      await expect(detail).toContainText(runtimeBody);
      await expect(detail).toHaveAttribute("data-runtime-hash", runtimeHash);
      await expect(detail).toHaveAttribute("data-runtime-revision", "7");

      await openSettings(page);
      await page.getByRole("button", { name: /analytics/i }).click();
      await expect(page.getByTestId("runtime-analytics")).toHaveAttribute("data-runtime-revision", "7");
      await expect(page.getByTestId("runtime-analytics")).toContainText("3");

      await openSettings(page);
      await page.getByTestId("runtime-search-input").fill("authority sentinel");
      await page.getByTestId("runtime-search-submit").click();
      await expect(page.getByTestId("runtime-search-results")).toContainText("1 result(s) · revision 7");
      await expect(page.getByTestId("runtime-search-results")).toContainText(runtimeHash);

      let dialogText = "";
      page.once("dialog", async (dialog) => { dialogText = dialog.message(); await dialog.accept(); });
      await page.getByRole("button", { name: /export/i }).click();
      await expect.poll(() => dialogText).toMatch(/3/);

      await page.reload();
      await expect(page.getByTestId("runtime-count")).toHaveText("3");
      await expect(page.getByTestId("runtime-revision")).toHaveText("7");
    });
  }

  for (const fault of ["connection_refused", "timeout", "degraded", "malformed_dto", "version_mismatch", "authorization", "db_locked"]) {
    test(`fault ${fault} fails closed and recovers`, async ({ page }) => {
      prepare("D", fault);
      await openSettings(page);
      const unavailable = page.getByTestId("runtime-unavailable");
      await expect(unavailable).toBeVisible();
      await expect(unavailable).toContainText(/Runtime unavailable|Runtime authorization|locked|mismatch|degraded/i);
      await expect(unavailable).toContainText("export is blocked");
      await expect(unavailable).toContainText("writes are disabled");
      await expect(page.getByText(/LOCAL FAKE CHAPTER FOUR|Local Chapter 4/)).toHaveCount(0);
      await expect(page.getByRole("button", { name: /export/i })).toHaveCount(0);
      await expect(page.getByRole("button", { name: /write next/i })).toHaveCount(0);

      recover();
      await page.getByTestId("runtime-retry").click();
      await expect(page.getByTestId("runtime-count")).toHaveText("3");
      await expect(page.getByTestId("runtime-revision")).toHaveText("7");
      await expect(page.getByText("Runtime Chapter 4")).toHaveCount(0);
    });
  }
});
