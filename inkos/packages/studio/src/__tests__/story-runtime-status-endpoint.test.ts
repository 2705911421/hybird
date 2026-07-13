import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { createStudioServer } from "../api/server.js";

const roots: string[] = [];
const servers: Array<ReturnType<typeof createServer>> = [];

async function writeConfig(root: string, storyRuntime: Record<string, unknown>) {
  await writeFile(join(root, "inkos.json"), JSON.stringify({
    name: "runtime-status", version: "0.1.0", language: "zh",
    llm: { provider: "openai", baseUrl: "http://127.0.0.1:9/v1", apiKey: "", model: "test" },
    notify: [], storyRuntime,
  }), "utf-8");
}

describe("Studio Story Runtime status endpoints", () => {
  afterEach(async () => {
    for (const server of servers.splice(0)) await new Promise<void>((resolve) => server.close(() => resolve()));
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it("shows disabled health in legacy mode", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-studio-runtime-")); roots.push(root);
    await writeConfig(root, { mode: "legacy" });
    const app = createStudioServer({} as never, root);
    const response = await app.request("/api/v1/story-runtime/status");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ mode: "legacy", enabled: false, health: null, featureFlags: { panel: true, recovery: true } });
  });

  it("displays live runtime health through the public client", async () => {
    const server = createServer((request, response) => {
      response.setHeader("content-type", "application/json");
      if (request.url === "/api/story-runtime/v1/health") {
        response.end(JSON.stringify({ status: "ok", runtime_version: "0.2-test", schema_versions: ["story-runtime/v1"], database: "ready" }));
      } else {
        response.statusCode = 404; response.end(JSON.stringify({ error: "not found" }));
      }
    });
    servers.push(server);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    const port = typeof address === "object" && address ? address.port : 0;
    const root = await mkdtemp(join(tmpdir(), "inkos-studio-runtime-")); roots.push(root);
    await writeConfig(root, { mode: "shadow", baseUrl: `http://127.0.0.1:${port}` });
    const app = createStudioServer({} as never, root);
    const response = await app.request("/api/v1/story-runtime/status");
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ mode: "shadow", enabled: true, health: { status: "ok", database: "ready" } });
  });

  it("rejects direct chapter and Truth writes for Runtime-authority books", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-studio-runtime-")); roots.push(root);
    await writeConfig(root, { mode: "story-runtime", baseUrl: "http://127.0.0.1:9" });
    const bookDir = join(root, "books", "runtime-book");
    await mkdir(join(bookDir, "chapters"), { recursive: true });
    await mkdir(join(bookDir, "story"), { recursive: true });
    await writeFile(join(bookDir, "book.json"), JSON.stringify({
      id: "runtime-book", title: "Runtime", platform: "other", genre: "other", status: "active",
      targetChapters: 10, chapterWordCount: 3000, authorityMode: "runtime",
      createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
    }), "utf-8");
    await writeFile(join(bookDir, "chapters", "0001_Test.md"), "old", "utf-8");
    const app = createStudioServer({} as never, root);
    const chapter = await app.request("/api/v1/books/runtime-book/chapters/1", {
      method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ content: "new" }),
    });
    const truth = await app.request("/api/v1/books/runtime-book/truth/current_state.md", {
      method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ content: "new" }),
    });
    expect(chapter.status).toBe(409);
    expect(truth.status).toBe(409);
  });

  it("maps Runtime reviews for Studio and stores revision-bound human decisions", async () => {
    const received: unknown[] = [];
    const artifact = {
      artifact_id: "review-a", schema_version: "review-artifacts/v1", project_id: "runtime-book",
      chapter_number: 1, source_revision: 0, body_sha256: "a".repeat(64), reviewer_kind: "runtime_validator",
      reviewer_version: "1", generated_at: "2026-07-12T00:00:00Z", dimensions: {},
      findings: [{ finding_id: "finding-a", category: "continuity", severity: "critical", blocking: true,
        message: "conflict", rationale: "authority mismatch", evidence_spans: [], affected_entities: ["char-a"],
        affected_facts: ["location"], proposed_resolution: null, confidence: 1, source: "runtime_validator",
        deterministic_rule_id: "FACT.CONFLICT", supersedes: [], status: "open" }],
      summary: "blocked", recommended_action: "human_review", model_metadata: {}, prompt_template_version: "runtime/v1",
    };
    const status = { project_id: "runtime-book", chapter_number: 1, revision: 0, status: "blocked",
      blocking_finding_ids: ["finding-a"], requires_human: true, reasons: ["unresolved blocking findings"] };
    const server = createServer(async (request, response) => {
      response.setHeader("content-type", "application/json");
      if (request.method === "GET" && request.url?.endsWith("/reviews")) return response.end(JSON.stringify([artifact]));
      if (request.method === "GET" && request.url?.endsWith("/review-status")) return response.end(JSON.stringify(status));
      if (request.method === "POST" && request.url?.endsWith("/reviews/decisions")) {
        const chunks: Buffer[] = [];
        for await (const chunk of request) chunks.push(Buffer.from(chunk));
        const payload = JSON.parse(Buffer.concat(chunks).toString("utf8")); received.push(payload);
        return response.end(JSON.stringify(payload.decision));
      }
      response.statusCode = 404; return response.end(JSON.stringify({ error: "not found" }));
    });
    servers.push(server);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    const port = typeof address === "object" && address ? address.port : 0;
    const root = await mkdtemp(join(tmpdir(), "inkos-studio-review-")); roots.push(root);
    await writeConfig(root, { mode: "story-runtime", baseUrl: `http://127.0.0.1:${port}` });
    const bookDir = join(root, "books", "runtime-book");
    await mkdir(bookDir, { recursive: true });
    await writeFile(join(bookDir, "book.json"), JSON.stringify({ id: "runtime-book", title: "Runtime", platform: "other", genre: "other", status: "active", targetChapters: 10, chapterWordCount: 3000, authorityMode: "runtime", createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }), "utf8");
    const app = createStudioServer({} as never, root);

    const reviewResponse = await app.request("/api/v1/books/runtime-book/chapters/1/reviews?severity=critical");
    expect(reviewResponse.status).toBe(200);
    const reviewBody = await reviewResponse.json() as { view: { deterministicFindings: unknown[]; literarySuggestions: unknown[]; blocked: boolean } };
    expect(reviewBody.view).toMatchObject({ blocked: true, literarySuggestions: [] });
    expect(reviewBody.view.deterministicFindings).toHaveLength(1);

    const decisionResponse = await app.request("/api/v1/books/runtime-book/chapters/1/review-decisions", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({
        decisionId: "decision-a", idempotencyKey: "studio-decision-key", reviewer: "editor",
        decision: "approve", findingDecisions: { "finding-a": "accept" }, comment: "verified",
      }),
    });
    expect(decisionResponse.status).toBe(200);
    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({ expected_revision: 0, decision: { source_revision: 0, decision: "approve" } });
  });
});
