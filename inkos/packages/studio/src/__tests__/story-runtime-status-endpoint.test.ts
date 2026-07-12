import { mkdtemp, rm, writeFile } from "node:fs/promises";
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
    expect(await response.json()).toEqual({ mode: "legacy", enabled: false, health: null });
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
});
