import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  ensureNodeRuntimePinFiles,
  inspectNodeRuntimePinFiles,
} from "../runtime-requirements.js";

let tempRoot: string;

describe("runtime requirements", () => {
  beforeEach(async () => {
    tempRoot = await mkdtemp(join(tmpdir(), "inkos-runtime-requirements-"));
  });

  afterEach(async () => {
    await rm(tempRoot, { recursive: true, force: true });
  });

  it("reports missing node runtime pin files", async () => {
    const status = await inspectNodeRuntimePinFiles(tempRoot);

    expect(status.ok).toBe(false);
    expect(status.detail).toContain(".nvmrc");
    expect(status.detail).toContain(".node-version");
  });

  it("writes node runtime pin files for old projects", async () => {
    const repair = await ensureNodeRuntimePinFiles(tempRoot);

    expect(repair.updated).toBe(true);
    expect(repair.written).toEqual([".nvmrc", ".node-version"]);
    await expect(readFile(join(tempRoot, ".nvmrc"), "utf-8")).resolves.toBe("22\n");
    await expect(readFile(join(tempRoot, ".node-version"), "utf-8")).resolves.toBe("22\n");

    const status = await inspectNodeRuntimePinFiles(tempRoot);
    expect(status.ok).toBe(true);
  });
});
