import { afterEach, describe, expect, it } from "vitest";
import { mkdtemp, mkdir, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { composeGovernedChapter } from "../agents/composer.js";
import type { BookConfig } from "../models/book.js";
import type { PlanChapterOutput } from "../agents/planner.js";
import type { StoryRuntimeClient } from "../story-runtime/client.js";

const now = "2026-07-13T00:00:00.000Z";
const book: BookConfig = {
  id: "runtime-book", title: "Runtime Book", platform: "other", genre: "other", status: "active",
  targetChapters: 20, chapterWordCount: 3000, authorityMode: "runtime", createdAt: now, updatedAt: now,
};
const plan: PlanChapterOutput = {
  intent: { chapter: 1, goal: "Open the vault", mustKeep: ["Ada has the key"], mustAvoid: [], styleEmphasis: [] },
  memo: { chapter: 1, goal: "Open the vault", isGoldenOpening: true, body: "", threadRefs: [] },
  intentMarkdown: "# Intent", plannerInputs: [], runtimePath: "story/runtime/chapter-0001.intent.md",
};

describe("Runtime-authority composer", () => {
  const roots: string[] = [];
  afterEach(async () => Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))));

  it("uses only Runtime context and writes rebuildable governed artifacts", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-runtime-composer-")); roots.push(root);
    await mkdir(join(root, "story"), { recursive: true });
    const client = { queryContext: async () => ({
      request_id: "a59dc75f-6b04-49ea-bd56-3d231bc9d885", project_id: book.id, revision: 3,
      authoritative_facts: [], retrieval_candidates: [], untrusted_materials: [], conflicts: [],
      layers: { hard_constraints: [{ item_id: "fact-key", layer: "hard_constraints", content: "Ada has the key",
        source: { kind: "structured_query", id: "fact-key" }, confidence: 1, updated_at: now, importance: 100,
        trust: "trusted", subject: "ada", predicate: "inventory.key" }],
        plot_commitments: [], relevant_memory: [], recent_narrative: [], style_guidance: [] },
      trace: { budget_used: 8, selected_source_ids: ["fact-key"] },
    }) } as unknown as StoryRuntimeClient;

    const result = await composeGovernedChapter({ book, bookDir: root, chapterNumber: 1, plan,
      storyRuntime: { mode: "story-runtime", baseUrl: "http://127.0.0.1:47831", timeoutMs: 3000,
        maxContextTokens: 16000, maxItems: 100, fallbackOnUnavailable: false }, storyRuntimeClient: client });
    expect(result.contextPackage.selectedContext.some((entry) => entry.source.includes("fact-key"))).toBe(true);
    await expect(readFile(result.contextPath, "utf-8")).resolves.toContain("Ada has the key");
  });

  it("fails closed for legacy mode", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-legacy-composer-")); roots.push(root);
    await expect(composeGovernedChapter({ book: { ...book, authorityMode: "legacy" }, bookDir: root,
      chapterNumber: 1, plan, storyRuntime: { mode: "legacy", baseUrl: "http://127.0.0.1:47831",
        timeoutMs: 3000, maxContextTokens: 16000, maxItems: 100, fallbackOnUnavailable: false } }))
      .rejects.toThrow("LEGACY_LONG_FORM_READ_ONLY");
  });
});
