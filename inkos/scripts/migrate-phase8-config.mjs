import { copyFile, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const targets = process.argv.slice(2);
if (targets.length === 0) {
  console.error("Usage: pnpm migrate:phase8-config -- <project-root-or-inkos.json> [...]");
  process.exitCode = 2;
} else {
  for (const target of targets) await migrate(target);
}

async function migrate(target) {
  const path = target.toLowerCase().endsWith(".json") ? resolve(target) : resolve(target, "inkos.json");
  const raw = JSON.parse((await readFile(path, "utf8")).replace(/^\uFEFF/, ""));
  const warnings = [];
  const storyRuntime = raw.storyRuntime ?? {};

  if (storyRuntime.mode !== "story-runtime") {
    warnings.push(`storyRuntime.mode=${JSON.stringify(storyRuntime.mode ?? "(missing)")} is retired for long-form writes`);
  }
  if (storyRuntime.fallbackOnUnavailable === true) {
    warnings.push("storyRuntime.fallbackOnUnavailable=true is retired; Runtime failures now fail closed");
  }
  raw.storyRuntime = { ...storyRuntime, mode: "story-runtime", fallbackOnUnavailable: false };

  for (const key of ["legacyTruthAuthority", "memoryAuthority", "jsonAuthority", "stateMirror", "legacyDashboard", "claudePluginPath"]) {
    if (key in raw) {
      warnings.push(`${key} was removed from the Phase 8 product configuration`);
      delete raw[key];
    }
  }

  if (warnings.length === 0) {
    console.log(`${path}: already Phase 8 compatible`);
    return;
  }
  const backup = `${path}.pre-phase8.bak`;
  await copyFile(path, backup);
  await writeFile(path, `${JSON.stringify(raw, null, 2)}\n`, "utf8");
  console.warn(`${path}: migrated with explicit changes:`);
  for (const warning of warnings) console.warn(`  - ${warning}`);
  console.warn(`  backup: ${backup}`);
}
