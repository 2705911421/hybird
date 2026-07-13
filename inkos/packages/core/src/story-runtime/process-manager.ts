import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { StoryRuntimeClient } from "./client.js";
import { STORY_RUNTIME_SCHEMA_VERSION } from "./schemas.js";

export interface StoryRuntimeProcessOptions {
  readonly command: string;
  readonly args?: ReadonlyArray<string>;
  readonly cwd?: string;
  readonly env?: NodeJS.ProcessEnv;
  readonly healthUrl: string;
  readonly startupTimeoutMs?: number;
  readonly expectedRuntimeVersion?: string;
  readonly expectedSchemaVersion?: string;
  readonly tokenEnvName?: string;
  readonly pidFile?: string;
  readonly maxRestarts?: number;
  readonly restartBaseDelayMs?: number;
  readonly restartResetAfterMs?: number;
  readonly onCrash?: (error: Error) => void;
}

export class StoryRuntimeProcessManager {
  private child?: ChildProcess;
  private readonly token = randomBytes(32).toString("base64url");
  private stopping = false;
  private restartCount = 0;
  private restartTimer?: NodeJS.Timeout;
  private restartResetTimer?: NodeJS.Timeout;

  constructor(private readonly options: StoryRuntimeProcessOptions) {}

  static async discoverLoopbackPort(): Promise<number> {
    return await new Promise((resolve, reject) => {
      const server = createServer();
      server.once("error", reject);
      server.listen(0, "127.0.0.1", () => {
        const address = server.address();
        const port = typeof address === "object" && address ? address.port : 0;
        server.close((error) => error ? reject(error) : resolve(port));
      });
    });
  }

  client(): StoryRuntimeClient {
    return new StoryRuntimeClient({ baseUrl: this.options.healthUrl, apiToken: this.token });
  }

  async start(): Promise<void> {
    if (this.child && this.child.exitCode === null) return;
    this.stopping = false;
    this.claimSingleInstance();
    try {
      await this.launchAndHandshake();
    } catch (error) {
      await this.terminateChild();
      this.releasePidFile();
      throw error;
    }
  }

  private async launchAndHandshake(): Promise<void> {
    const tokenEnvName = this.options.tokenEnvName ?? "STORY_RUNTIME_TOKEN";
    this.child = spawn(this.options.command, [...(this.options.args ?? [])], {
      cwd: this.options.cwd,
      env: { ...process.env, ...this.options.env, [tokenEnvName]: this.token },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
    });
    if (!this.child.pid) throw new Error("Story Runtime did not return a process id");
    this.child.stdout?.resume();
    this.child.stderr?.resume();
    let launchError: Error | undefined;
    this.child.once("error", (error) => { launchError = error; });
    this.writePid(this.child.pid);
    const deadline = Date.now() + (this.options.startupTimeoutMs ?? 10_000);
    const client = this.client();
    while (Date.now() < deadline) {
      if (launchError) throw launchError;
      if (this.child.exitCode !== null) throw new Error(`Story Runtime exited during startup (${this.child.exitCode})`);
      try {
        const health = await client.health();
        const expectedSchema = this.options.expectedSchemaVersion ?? STORY_RUNTIME_SCHEMA_VERSION;
        if (!health.schema_versions.includes(expectedSchema)) {
          throw new Error(`Story Runtime schema handshake failed: expected ${expectedSchema}`);
        }
        if (this.options.expectedRuntimeVersion && health.runtime_version !== this.options.expectedRuntimeVersion) {
          throw new Error(`Story Runtime version handshake failed: expected ${this.options.expectedRuntimeVersion}, received ${health.runtime_version}`);
        }
        if (this.restartResetTimer) clearTimeout(this.restartResetTimer);
        this.restartResetTimer = setTimeout(() => {
          this.restartCount = 0;
          this.restartResetTimer = undefined;
        }, this.options.restartResetAfterMs ?? 60_000);
        this.restartResetTimer.unref?.();
        this.child.once("exit", (code, signal) => this.handleUnexpectedExit(code, signal));
        return;
      } catch (error) {
        if (error instanceof Error && error.message.includes("handshake failed")) {
          await this.terminateChild();
          throw error;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
    }
    await this.terminateChild();
    throw new Error("Story Runtime startup timed out");
  }

  private handleUnexpectedExit(code: number | null, signal: NodeJS.Signals | null): void {
    this.child = undefined;
    if (this.restartResetTimer) clearTimeout(this.restartResetTimer);
    this.restartResetTimer = undefined;
    this.releasePidFile();
    if (this.stopping) return;
    const maxRestarts = this.options.maxRestarts ?? 3;
    if (this.restartCount >= maxRestarts) {
      this.options.onCrash?.(new Error(`Story Runtime restart limit reached after exit ${code ?? signal ?? "unknown"}`));
      return;
    }
    const delay = Math.min(30_000, (this.options.restartBaseDelayMs ?? 250) * (2 ** this.restartCount));
    this.restartCount += 1;
    this.restartTimer = setTimeout(() => {
      void this.launchAndHandshake().catch((error: unknown) => {
        this.handleUnexpectedExit(null, null);
        this.options.onCrash?.(error instanceof Error ? error : new Error(String(error)));
      });
    }, delay);
  }

  async stop(timeoutMs = 3_000): Promise<void> {
    this.stopping = true;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    this.restartTimer = undefined;
    if (this.restartResetTimer) clearTimeout(this.restartResetTimer);
    this.restartResetTimer = undefined;
    await this.terminateChild(timeoutMs);
    this.releasePidFile();
  }

  private async terminateChild(timeoutMs = 3_000): Promise<void> {
    const child = this.child;
    this.child = undefined;
    if (!child || child.exitCode !== null) return;
    if (process.platform === "win32" && child.pid) {
      const graceful = await this.killWindowsTree(child.pid, false);
      if (graceful) {
        await Promise.race([
          new Promise<void>((resolve) => child.once("exit", () => resolve())),
          new Promise<void>((resolve) => setTimeout(resolve, Math.min(timeoutMs, 500))),
        ]);
      }
      if (!graceful || child.exitCode === null) await this.killWindowsTree(child.pid, true);
      return;
    }
    this.signal(child, process.platform === "win32" ? "SIGBREAK" : "SIGTERM");
    await Promise.race([
      new Promise<void>((resolve) => child.once("exit", () => resolve())),
      new Promise<void>((resolve) => setTimeout(resolve, timeoutMs)),
    ]);
    if (child.exitCode === null) this.signal(child, "SIGKILL");
  }

  private signal(child: ChildProcess, signal: NodeJS.Signals): void {
    if (process.platform !== "win32" && child.pid) {
      try { process.kill(-child.pid, signal); return; } catch { /* process may already be gone */ }
    }
    try { child.kill(signal); } catch { /* process may already be gone */ }
  }

  private async killWindowsTree(pid: number, force: boolean): Promise<boolean> {
    return await new Promise<boolean>((resolve) => {
      const args = ["/pid", String(pid), "/t"];
      if (force) args.push("/f");
      const killer = spawn("taskkill", args, {
        windowsHide: true,
        stdio: "ignore",
      });
      killer.once("error", () => resolve(false));
      killer.once("exit", (code) => resolve(code === 0));
    });
  }

  private claimSingleInstance(): void {
    const pidFile = this.options.pidFile;
    if (!pidFile || !existsSync(pidFile)) return;
    const pid = Number.parseInt(readFileSync(pidFile, "utf8"), 10);
    if (Number.isInteger(pid) && pid > 0) {
      try {
        process.kill(pid, 0);
        throw new Error(`Story Runtime is already running with process id ${pid}`);
      } catch (error) {
        if (error instanceof Error && error.message.includes("already running")) throw error;
      }
    }
    unlinkSync(pidFile);
  }

  private writePid(pid: number): void {
    if (!this.options.pidFile) return;
    writeFileSync(this.options.pidFile, `${pid}\n`, { encoding: "utf8", mode: 0o600, flag: "wx" });
  }

  private releasePidFile(): void {
    if (this.options.pidFile && existsSync(this.options.pidFile)) unlinkSync(this.options.pidFile);
  }
}
