import { createServer } from "node:net";
import { describe, expect, it } from "vitest";
import { StoryRuntimeProcessManager } from "../story-runtime/process-manager.js";

describe("StoryRuntimeProcessManager", () => {
  it("discovers an available loopback port", async () => {
    const port = await StoryRuntimeProcessManager.discoverLoopbackPort();
    expect(port).toBeGreaterThan(0);
    const server = createServer();
    await new Promise<void>((resolve, reject) => server.listen(port, "127.0.0.1", resolve).once("error", reject));
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  it("caps consecutive post-handshake crash restarts", async () => {
    const port = await StoryRuntimeProcessManager.discoverLoopbackPort();
    const payload = JSON.stringify({ status: "ok", runtime_version: "test", schema_versions: ["story-runtime/v1"], database: "ready" });
    const script = [
      "const http=require('http');",
      `http.createServer((req,res)=>{if(req.url==='/api/story-runtime/v1/health'){res.setHeader('content-type','application/json');res.end(${JSON.stringify(payload)})}else{res.statusCode=404;res.end()}}).listen(${port},'127.0.0.1');`,
      "setTimeout(()=>process.exit(17),150);",
    ].join("");
    let resolveLimit!: (error: Error) => void;
    const limitReached = new Promise<Error>((resolve) => { resolveLimit = resolve; });
    const manager = new StoryRuntimeProcessManager({
      command: process.execPath,
      args: ["-e", script],
      healthUrl: `http://127.0.0.1:${port}`,
      startupTimeoutMs: 2_000,
      maxRestarts: 2,
      restartBaseDelayMs: 10,
      restartResetAfterMs: 5_000,
      onCrash: (error) => {
        if (error.message.includes("restart limit reached")) resolveLimit(error);
      },
    });
    await manager.start();
    const error = await Promise.race([
      limitReached,
      new Promise<Error>((_, reject) => setTimeout(() => reject(new Error("restart limit was not reached")), 5_000)),
    ]);
    expect(error.message).toContain("restart limit reached");
    await manager.stop();
  });
});
