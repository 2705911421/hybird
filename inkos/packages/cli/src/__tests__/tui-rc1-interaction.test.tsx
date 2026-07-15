import { spawn, type ChildProcess } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import React from "react";
import { render } from "ink-testing-library";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { InteractionSession } from "@actalk/inkos-core";
import { InkTuiApp } from "../tui/dashboard.js";

const repoRoot = path.resolve(import.meta.dirname, "../../../../..");
const orchestrator = path.join(repoRoot, "hybrid", "fixtures", "rc1-ui-verification", "orchestrator.mjs");
const port = 47941;
const body = "Runtime chapter two authority sentinel.";
const bodyHash = createHash("sha256").update(body).digest("hex");
let root = "";
let controlPath = "";
let runtime: ChildProcess | undefined;

async function waitFor(predicate: () => boolean | Promise<boolean>, timeoutMs = 5_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error("Timed out waiting for interactive TUI frame");
}

async function prepare(localCase: string, fault = "healthy") {
  const mod = await import(pathToFileURL(orchestrator).href);
  await mod.prepareFixtureProject(root, localCase, { runtimePort: port, fault, controlPath });
}

function session(): InteractionSession {
  return {
    sessionId: "rc1-tui", projectRoot: root, activeBookId: "rc1-ui-verification",
    automationMode: "semi", messages: [], events: [], draftRounds: [],
  };
}

async function drive(command: string, expected: RegExp | string) {
  const view = render(<InkTuiApp locale="en" projectRoot={root} projectName="RC-1" modelLabel="fixture" initialSession={session()} />);
  view.stdin.write(command);
  await new Promise((resolve) => setTimeout(resolve, 20));
  view.stdin.write("\r");
  try {
    await waitFor(() => typeof expected === "string"
      ? (view.lastFrame() ?? "").includes(expected)
      : expected.test(view.lastFrame() ?? ""));
  } catch {
    throw new Error(`TUI command ${command} did not render expected output. Last frame:\n${view.lastFrame() ?? "<empty>"}`);
  }
  const frame = view.lastFrame() ?? "";
  view.unmount();
  return frame;
}

beforeAll(async () => {
  root = await mkdtemp(path.join(tmpdir(), "inkos-rc1-tui-"));
  controlPath = path.join(root, "..", `${path.basename(root)}-control.json`);
  await prepare("A");
  runtime = spawn(process.execPath, [orchestrator, "serve", "--port", String(port), "--control", controlPath], {
    cwd: repoRoot, stdio: "ignore",
  });
  await waitFor(async () => {
    try { return (await fetch(`http://127.0.0.1:${port}/health`)).ok; } catch { return false; }
  }, 10_000);
}, 20_000);

afterAll(async () => {
  runtime?.kill();
  await rm(root, { recursive: true, force: true });
  await rm(controlPath, { force: true });
});

describe("interactive TUI RC-1 authority matrix", () => {
  for (const localCase of ["A", "B", "C", "D", "E", "F"]) {
    it(`drives browser/detail/stats/search/export for local case ${localCase}`, async () => {
      await prepare(localCase);
      const chapters = await drive("/chapters", "Runtime chapters (3), latest 3, revision 7");
      expect(chapters).not.toMatch(/Local Chapter 4|latest 99|LOCAL FAKE/);
      const detail = await drive("/chapter 2", body);
      expect(detail).toContain(bodyHash);
      const stats = await drive("/stats", "Runtime stats at revision 7");
      expect(stats).toContain("Chapters: 3");
      const search = await drive("/search authority sentinel", "Runtime search (1), revision 7");
      expect(search).toContain(bodyHash);
      const exported = await drive("/export", "Runtime export: 3 chapters, revision 7");
      expect(exported).toContain(bodyHash);
    }, 20_000);
  }

  for (const fault of ["connection_refused", "timeout", "degraded", "malformed_dto", "version_mismatch", "authorization", "db_locked"]) {
    it(`presents ${fault} without fallback and recovers through /retry`, async () => {
      await prepare("D", fault);
      const view = render(<InkTuiApp locale="en" projectRoot={root} projectName="RC-1" modelLabel="fixture" initialSession={session()} />);
      view.stdin.write("/chapters");
      await new Promise((resolve) => setTimeout(resolve, 20));
      view.stdin.write("\r");
      await waitFor(() => /error|unavailable|locked|mismatch|degraded|authorization/i.test(view.lastFrame() ?? ""), 5_000);
      expect(view.lastFrame() ?? "").not.toMatch(/Local Chapter 4|LOCAL FAKE|latest 99/);

      await prepare("D", "healthy");
      view.stdin.write("/retry");
      await new Promise((resolve) => setTimeout(resolve, 20));
      view.stdin.write("\r");
      await waitFor(() => (view.lastFrame() ?? "").includes("Runtime chapters (3), latest 3, revision 7"), 5_000);
      expect(view.lastFrame() ?? "").not.toMatch(/Local Chapter 4|LOCAL FAKE|latest 99/);
      view.unmount();
    }, 15_000);
  }
});
