import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { createStudioServer } from "../api/server.js";

const roots: string[] = [];
const servers: Array<ReturnType<typeof createServer>> = [];
const previousToken = process.env.PHASE6_RUNTIME_TOKEN;

async function project(baseUrl: string, tokenEnv?: string) {
  const root = await mkdtemp(join(tmpdir(), "inkos-phase6-proxy-")); roots.push(root);
  await writeFile(join(root, "inkos.json"), JSON.stringify({
    name: "phase6", version: "0.1.0", language: "en",
    llm: { provider: "openai", baseUrl: "http://127.0.0.1:9/v1", apiKey: "", model: "test" },
    notify: [], storyRuntime: { mode: "story-runtime", baseUrl, ...(tokenEnv ? { apiTokenEnv: tokenEnv } : {}) },
  }), "utf8");
  return createStudioServer({} as never, root);
}

async function listen(handler: Parameters<typeof createServer>[0]) {
  const server = createServer(handler); servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  return `http://127.0.0.1:${typeof address === "object" && address ? address.port : 0}`;
}

const overview = {
  project_id: "runtime-book", runtime_state: "healthy",
  impact: { what_happened: "ok", reads_affected: false, writes_affected: false, retryable: true, user_action: "none", disabled_actions: [] },
  current_revision: 2, latest_chapter: 2, project_phase: "drafting", authority_mode: "runtime",
  active_prepares: 0, blocked_commits: 0, pending_recovery: 0, projection_health: "ready",
  index_health: { status: "ready", lexical_documents: 2, vector_status: "not_configured", last_indexed_chapter: 2, pending_items: 0 },
  last_successful_commit: "2026-07-12T00:00:00Z", last_backup: null,
  schema_version: "story-runtime/v1", runtime_version: "0.1.0",
};

describe("Studio Runtime observability proxy", () => {
  afterEach(async () => {
    if (previousToken === undefined) delete process.env.PHASE6_RUNTIME_TOKEN;
    else process.env.PHASE6_RUNTIME_TOKEN = previousToken;
    delete process.env.INKOS_STUDIO_RUNTIME_PANEL;
    delete process.env.INKOS_STUDIO_RUNTIME_RECOVERY;
    for (const server of servers.splice(0)) await new Promise<void>((resolve) => server.close(() => resolve()));
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it("keeps the bearer server-side and proxies a validated overview", async () => {
    process.env.PHASE6_RUNTIME_TOKEN = "server-only-token";
    let authorization: string | undefined;
    const baseUrl = await listen((request, response) => {
      authorization = request.headers.authorization;
      response.setHeader("content-type", "application/json"); response.end(JSON.stringify(overview));
    });
    const app = await project(baseUrl, "PHASE6_RUNTIME_TOKEN");
    const response = await app.request("/api/v1/story-runtime/projects/runtime-book/overview");
    expect(response.status).toBe(200);
    expect(authorization).toBe("Bearer server-only-token");
    const text = await response.text();
    expect(JSON.parse(text)).toMatchObject({ runtime_state: "healthy", current_revision: 2 });
    expect(text).not.toContain("server-only-token");
  });

  it("preserves bounded pagination parameters", async () => {
    let requested = "";
    const baseUrl = await listen((request, response) => {
      requested = request.url ?? ""; response.setHeader("content-type", "application/json");
      response.end(JSON.stringify({ items: [], page: { limit: 10, has_more: false, next_cursor: null } }));
    });
    const app = await project(baseUrl);
    const response = await app.request("/api/v1/story-runtime/projects/runtime-book/commits?cursor=opaque&limit=10&chapter=3&state=FINALIZED");
    expect(response.status).toBe(200);
    expect(requested).toContain("cursor=opaque"); expect(requested).toContain("limit=10"); expect(requested).toContain("chapter=3"); expect(requested).toContain("state=FINALIZED");
  });

  it.each([
    ["locked", 503, { code: "DATABASE_LOCKED", message: "sqlite internal", retryable: true }, 423, "database_locked"],
    ["malformed", 200, { unexpected: "dto" }, 502, "version_mismatch"],
  ])("maps %s Runtime responses without exposing internal messages", async (_name, runtimeStatus, payload, studioStatus, state) => {
    const baseUrl = await listen((_request, response) => {
      response.statusCode = runtimeStatus as number; response.setHeader("content-type", "application/json"); response.end(JSON.stringify(payload));
    });
    const app = await project(baseUrl);
    const response = await app.request("/api/v1/story-runtime/projects/runtime-book/overview");
    expect(response.status).toBe(studioStatus);
    const text = await response.text(); expect(JSON.parse(text)).toMatchObject({ runtimeState: state }); expect(text).not.toContain("sqlite internal");
  });

  it("maps connection failure to unavailable", async () => {
    const app = await project("http://127.0.0.1:9");
    const response = await app.request("/api/v1/story-runtime/projects/runtime-book/overview");
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ runtimeState: "unavailable", error: { code: "RUNTIME_UNAVAILABLE", retryable: true } });
  });

  it("forwards only the recovery confirmation value and can disable recovery", async () => {
    let received: Record<string, unknown> = {};
    const baseUrl = await listen(async (request, response) => {
      const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
      received = JSON.parse(Buffer.concat(chunks).toString("utf8")); response.setHeader("content-type", "application/json");
      response.end(JSON.stringify({ job_id: "job-1", project_id: "runtime-book", operation: "clear_retry_queue", state: "completed", requires_confirmation: true, confirmation_token: null, preview: {}, result: {}, progress: 100, cancellable: false, error: null, created_at: "2026-07-12T00:00:00Z", updated_at: "2026-07-12T00:00:01Z", completed_at: "2026-07-12T00:00:01Z", audit_trail: [] }));
    });
    const app = await project(baseUrl);
    const response = await app.request("/api/v1/story-runtime/projects/runtime-book/recovery-jobs/job-1/execute", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ confirmationToken: "preview-token", injected: "ignored" }) });
    expect(response.status).toBe(200);
    expect(received).toEqual({ actor: "studio-user", confirmation_token: "preview-token" });

    process.env.INKOS_STUDIO_RUNTIME_RECOVERY = "0";
    const disabled = await project(baseUrl);
    const blocked = await disabled.request("/api/v1/story-runtime/projects/runtime-book/recovery-jobs/job-1/execute", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    expect(blocked.status).toBe(403);
  });
});
