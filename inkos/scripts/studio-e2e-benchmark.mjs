import { writeFile } from "node:fs/promises";
import { chromium } from "../packages/studio/node_modules/@playwright/test/index.mjs";

const baseUrl = (process.env.INKOS_STUDIO_URL ?? "http://127.0.0.1:4567").replace(/\/$/, "");
const bookId = process.env.INKOS_RUNTIME_BOOK_ID ?? "lighthouse-fixture";
const commitId = process.env.INKOS_RUNTIME_COMMIT_ID;
const iterations = Number.parseInt(process.env.INKOS_STUDIO_BENCHMARK_ITERATIONS ?? "5", 10);
const output = process.env.INKOS_STUDIO_BENCHMARK_OUTPUT ?? "studio-benchmark.json";

function stats(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const pick = (fraction) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * fraction) - 1))];
  return { p50: pick(.5), p95: pick(.95), p99: pick(.99), max: sorted.at(-1), samples: sorted.length };
}

async function resourceDuration(page, route, match, ready) {
  await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded" });
  await ready(page);
  return await page.evaluate((needle) => {
    const matches = performance.getEntriesByType("resource").filter((entry) => entry.name.includes(needle));
    return matches.at(-1)?.duration ?? null;
  }, match);
}

const browser = await chromium.launch({
  headless: true,
  ...(process.env.INKOS_PLAYWRIGHT_EXECUTABLE ? { executablePath: process.env.INKOS_PLAYWRIGHT_EXECUTABLE } : {}),
});
try {
  const page = await browser.newPage();
  const firstScreen = [];
  const overview = [];
  const events = [];
  const commits = [];
  const details = [];
  const heaps = [];
  for (let index = 0; index < iterations; index += 1) {
    await page.goto(`${baseUrl}/`, { waitUntil: "load" });
    await page.getByRole("heading", { name: "Books" }).waitFor();
    firstScreen.push(await page.evaluate(() => {
      const entry = performance.getEntriesByType("navigation")[0];
      return entry ? (entry.loadEventEnd || entry.domContentLoadedEventEnd) - entry.startTime : 0;
    }));
    heaps.push(await page.evaluate(() => performance.memory?.usedJSHeapSize ?? null));
    overview.push(await resourceDuration(page, `/#/runtime/overview/${encodeURIComponent(bookId)}`, "/overview", (current) => current.getByRole("heading", { name: /healthy|degraded|unavailable/i }).waitFor()));
    events.push(await resourceDuration(page, `/#/runtime/events/${encodeURIComponent(bookId)}`, "/events?", (current) => current.getByRole("group", { name: "Event detail view" }).waitFor()));
    commits.push(await resourceDuration(page, `/#/runtime/commits/${encodeURIComponent(bookId)}`, "/commits?", (current) => current.getByRole("textbox", { name: "Chapter filter" }).waitFor()));
    if (commitId) {
      details.push(await resourceDuration(page, `/#/runtime/commits/${encodeURIComponent(bookId)}/${encodeURIComponent(commitId)}`, `/commits/${commitId}`, (current) => current.getByRole("heading", { name: /Chapter/ }).waitFor()));
    }
  }
  const assets = await page.evaluate(() => performance.getEntriesByType("resource").filter((entry) => ["script", "link"].includes(entry.initiatorType)).reduce((sum, entry) => sum + (entry.transferSize || 0), 0));
  const report = {
    format: "phase-9-studio-benchmark/v1", base_url: baseUrl, book_id: bookId, iterations,
    first_screen_ms: stats(firstScreen), runtime_overview_ms: stats(overview.filter(Number.isFinite)),
    event_page_ms: stats(events.filter(Number.isFinite)), commit_list_ms: stats(commits.filter(Number.isFinite)),
    commit_detail_ms: stats(details.filter(Number.isFinite)), max_js_heap_bytes: Math.max(...heaps.filter(Number.isFinite)),
    transferred_script_and_style_bytes: assets,
  };
  await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
