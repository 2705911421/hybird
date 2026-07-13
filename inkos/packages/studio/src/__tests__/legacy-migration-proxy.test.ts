import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer, type RequestListener } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { createStudioServer } from "../api/server.js";

const roots: string[] = [];
const servers: Array<ReturnType<typeof createServer>> = [];

async function listen(handler: RequestListener) {
  const server = createServer(handler); servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  return `http://127.0.0.1:${typeof address === "object" && address ? address.port : 0}`;
}

async function project(baseUrl: string) {
  const root = await mkdtemp(join(tmpdir(), "inkos-phase7-proxy-")); roots.push(root);
  await writeFile(join(root, "inkos.json"), JSON.stringify({
    name: "phase7", version: "0.1.0", language: "en",
    llm: { provider: "openai", baseUrl: "http://127.0.0.1:9/v1", apiKey: "", model: "test" },
    notify: [], storyRuntime: { mode: "story-runtime", baseUrl },
  }), "utf8");
  return createStudioServer({} as never, root);
}

const job = {
  migration_job_id: "de305d54-75b4-431b-adb2-eb6b9e546014", source_type: "inkos",
  source_path_fingerprint: "a".repeat(64), target_project_id: "book-1", mapping_version: "phase7-map-v1",
  cir_version: "canonical-import/v1", current_stage: "DISCOVERED", progress: 5, warnings: [], conflicts: [],
  decisions: {}, checkpoints: [], audit_log: [], discovery: {}, source_checksum_manifest: [], target_snapshot: null,
  cir: null, dry_run: null, verification: null, cutover_confirmed: false, reused: false,
};

describe("Studio Phase 7 migration proxy", () => {
  afterEach(async () => {
    for (const server of servers.splice(0)) await new Promise<void>((resolve) => server.close(() => resolve()));
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it("passes a source path only through the validated Runtime client", async () => {
    let received: Record<string, unknown> = {};
    const baseUrl = await listen(async (request, response) => {
      const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
      received = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      response.setHeader("content-type", "application/json"); response.end(JSON.stringify(job));
    });
    const app = await project(baseUrl);
    const response = await app.request("/api/v1/story-runtime/migration-jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ sourcePath: "C:\\legacy\\玖安", targetProjectId: "book-1", sourceType: "auto" }) });
    expect(response.status).toBe(200);
    expect(received).toMatchObject({ source_path: "C:\\legacy\\玖安", target_project_id: "book-1", source_type: "auto" });
    expect(JSON.stringify(received)).not.toContain("sqlite");
  });

  it("does not expose an unsafe skip-all conflict action", async () => {
    const app = await project("http://127.0.0.1:9");
    const response = await app.request(`/api/v1/story-runtime/migration-jobs/${job.migration_job_id}/skip-all`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ error: { code: "INVALID_MIGRATION_ACTION" } });
  });
});
