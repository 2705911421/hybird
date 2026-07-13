import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const SUPPORTED_NODE_MAJOR = 22;
const NODE_PIN_VERSION = String(SUPPORTED_NODE_MAJOR);
const NODE_PIN_FILES = [".nvmrc", ".node-version"] as const;

export interface NodeRuntimePinStatus {
  readonly ok: boolean;
  readonly detail: string;
  readonly missing: ReadonlyArray<string>;
}
export interface NodeRuntimePinRepairResult {
  readonly updated: boolean;
  readonly written: ReadonlyArray<string>;
}

export async function inspectNodeRuntimePinFiles(root: string): Promise<NodeRuntimePinStatus> {
  const missing: string[] = [];

  for (const file of NODE_PIN_FILES) {
    try {
      const content = await readFile(join(root, file), "utf-8");
      if (content.trim() !== NODE_PIN_VERSION) {
        missing.push(file);
      }
    } catch {
      missing.push(file);
    }
  }

  if (missing.length === 0) {
    return {
      ok: true,
      detail: `Pinned to Node ${NODE_PIN_VERSION} via ${NODE_PIN_FILES.join(", ")}.`,
      missing,
    };
  }

  return {
    ok: false,
    detail: `Missing or outdated: ${missing.join(", ")}. Run 'inkos doctor --repair-node-runtime'.`,
    missing,
  };
}

export async function ensureNodeRuntimePinFiles(root: string): Promise<NodeRuntimePinRepairResult> {
  const written: string[] = [];

  for (const file of NODE_PIN_FILES) {
    const path = join(root, file);
    let content = "";
    try {
      content = await readFile(path, "utf-8");
    } catch {
      content = "";
    }

    if (content.trim() === NODE_PIN_VERSION) {
      continue;
    }

    await writeFile(path, `${NODE_PIN_VERSION}\n`, "utf-8");
    written.push(file);
  }

  return {
    updated: written.length > 0,
    written,
  };
}
