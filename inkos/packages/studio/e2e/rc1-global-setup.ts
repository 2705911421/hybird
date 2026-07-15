import { execFileSync } from "node:child_process";
import path from "node:path";

export default function globalSetup(): void {
  const repoRoot = path.resolve(import.meta.dirname, "../../../..");
  execFileSync("pnpm", ["--filter", "@actalk/inkos-core", "build"], { cwd: path.join(repoRoot, "inkos"), stdio: "inherit", shell: process.platform === "win32" });
  execFileSync(process.execPath, [
    path.join(repoRoot, "hybrid", "fixtures", "rc1-ui-verification", "orchestrator.mjs"),
    "prepare", "--root", path.join(repoRoot, "output", "rc1-ui", "project"), "--case", "A",
    "--control", path.join(repoRoot, "output", "rc1-ui", "runtime-control.json"),
  ], { cwd: repoRoot, stdio: "inherit" });
}
