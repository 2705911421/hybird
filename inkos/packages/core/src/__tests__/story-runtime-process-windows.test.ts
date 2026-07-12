import { createServer } from "node:net";
import { describe, expect, it } from "vitest";
import { StoryRuntimeProcessManager } from "../story-runtime/process-manager.js";

async function freePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

describe("Story Runtime Windows subprocess lifecycle", () => {
  it.runIf(process.platform === "win32")("starts, health-checks, and terminates a hidden sidecar", async () => {
    const port = await freePort();
    const payload = JSON.stringify({ status: "ok", runtime_version: "test", schema_versions: ["story-runtime/v1"], database: "ready" });
    const script = [
      "const http=require('http');",
      `http.createServer((req,res)=>{if(req.url==='/api/story-runtime/v1/health'){res.setHeader('content-type','application/json');res.end(${JSON.stringify(payload)})}else{res.statusCode=404;res.end()}}).listen(${port},'127.0.0.1');`,
    ].join("");
    const manager = new StoryRuntimeProcessManager({
      command: process.execPath, args: ["-e", script], healthUrl: `http://127.0.0.1:${port}`, startupTimeoutMs: 5_000,
    });
    await manager.start();
    await manager.stop();
    await expect(fetch(`http://127.0.0.1:${port}/api/story-runtime/v1/health`)).rejects.toThrow();
  });
});
