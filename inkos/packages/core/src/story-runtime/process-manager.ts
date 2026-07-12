import { spawn, type ChildProcess } from "node:child_process";
import { StoryRuntimeClient } from "./client.js";

export interface StoryRuntimeProcessOptions {
  readonly command: string;
  readonly args?: ReadonlyArray<string>;
  readonly cwd?: string;
  readonly env?: NodeJS.ProcessEnv;
  readonly healthUrl: string;
  readonly startupTimeoutMs?: number;
}

export class StoryRuntimeProcessManager {
  private child?: ChildProcess;

  constructor(private readonly options: StoryRuntimeProcessOptions) {}

  async start(): Promise<void> {
    if (this.child && this.child.exitCode === null) return;
    this.child = spawn(this.options.command, [...(this.options.args ?? [])], {
      cwd: this.options.cwd,
      env: { ...process.env, ...this.options.env },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      detached: false,
    });
    const deadline = Date.now() + (this.options.startupTimeoutMs ?? 10_000);
    const client = new StoryRuntimeClient({ baseUrl: this.options.healthUrl, timeoutMs: 500 });
    while (Date.now() < deadline) {
      if (this.child.exitCode !== null) throw new Error(`Story Runtime exited during startup (${this.child.exitCode})`);
      try {
        await client.health();
        return;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
    }
    await this.stop();
    throw new Error("Story Runtime startup timed out");
  }

  async stop(timeoutMs = 3_000): Promise<void> {
    const child = this.child;
    this.child = undefined;
    if (!child || child.exitCode !== null) return;
    child.kill("SIGTERM");
    await Promise.race([
      new Promise<void>((resolve) => child.once("exit", () => resolve())),
      new Promise<void>((resolve) => setTimeout(resolve, timeoutMs)),
    ]);
    if (child.exitCode === null) child.kill("SIGKILL");
  }
}
