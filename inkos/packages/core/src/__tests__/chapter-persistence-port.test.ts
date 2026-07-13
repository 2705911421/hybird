import { readFile } from "node:fs/promises";
import { describe, expect, it, vi } from "vitest";
import type { WriteChapterOutput } from "../agents/writer.js";
import { RuntimeValidationBlockedError, StoryRuntimeChapterPersistence, buildRuntimeArtifacts } from "../pipeline/chapter-persistence-port.js";
import { StoryRuntimeClientError } from "../story-runtime/client.js";

function output(): WriteChapterOutput {
  return {
    chapterNumber: 1, title: "钥匙", content: "林舟拾起钥匙。", wordCount: 8,
    preWriteCheck: "ok", postSettlement: "ok",
    runtimeStateDelta: {
      chapter: 1,
      currentStatePatch: { currentLocation: "码头" },
      hookOps: { upsert: [{ hookId: "key", startChapter: 1, type: "钥匙来源", status: "open", lastAdvancedChapter: 1, expectedPayoff: "", notes: "" }], mention: [], resolve: [], defer: [] },
      newHookCandidates: [],
      chapterSummary: { chapter: 1, title: "钥匙", characters: "林舟", events: "拾起钥匙", stateChanges: "位置在码头", hookActivity: "钥匙来源", mood: "紧张", chapterType: "主线" },
      subplotOps: [], emotionalArcOps: [], characterMatrixOps: [], notes: [],
    },
    updatedState: "must-not-write", updatedLedger: "must-not-write", updatedHooks: "must-not-write",
    chapterSummary: "summary", updatedSubplots: "", updatedEmotionalArcs: "", updatedCharacterMatrix: "",
    postWriteErrors: [], postWriteWarnings: [],
  };
}

function input() {
  return {
    projectId: "runtime-book", output: output(), status: "ready-for-review" as const,
    auditResult: { passed: true, issues: [], summary: "passed" }, finalWordCount: 8,
    lengthWarnings: [], degradedIssues: [], intent: { goal: "find key" },
  };
}

function runtimeClient(): any {
  return {
    projectStatus: vi.fn(async () => ({ project_id: "runtime-book", revision: 0, phase: "drafting", latest_chapter: 0, projection_health: {}, schema_version: "story-runtime/v1", active_prepare_ids: [], authority_mode: "runtime" })),
    prepareChapter: vi.fn(async () => ({ commit_id: "d7db31dc-cc22-4788-b263-5787db9505bb", prepare_id: "d7db31dc-cc22-4788-b263-5787db9505bb", project_id: "runtime-book", chapter_number: 1, state: "PREPARED", current_revision: 0, expected_revision: 0, required_artifact_schema: "chapter-artifacts.json", replayed: false })),
    validateChapter: vi.fn(async () => ({ commit_id: "d7db31dc-cc22-4788-b263-5787db9505bb", project_id: "runtime-book", chapter_number: 1, state: "VALIDATED", artifact_sha256: "a".repeat(64), validation_token: "token-token-token-token", issues: [], replayed: false })),
    commitChapter: vi.fn(async () => ({ commit_id: "d7db31dc-cc22-4788-b263-5787db9505bb", project_id: "runtime-book", chapter_number: 1, state: "FINALIZED", expected_revision: 0, resulting_revision: 1, body_sha256: "b".repeat(64), artifact_sha256: "a".repeat(64), event_count: 2, projection_hash: "c".repeat(64), finalized_at: "2026-07-12T08:00:00.000Z", replayed: false })),
    validateReviews: vi.fn(async () => ({ project_id: "runtime-book", chapter_number: 1, accepted_artifact_ids: ["a"], stale_finding_ids: [], blocking_finding_ids: [], fingerprints: {}, status: { project_id: "runtime-book", chapter_number: 1, revision: 0, status: "clear", blocking_finding_ids: [], requires_human: false, reasons: [] }, replayed: false })),
  };
}

describe("ChapterPersistencePort", () => {
  it("commits only through Runtime authority", async () => {
    const request = input();
    const client = runtimeClient();
    const result = await new StoryRuntimeChapterPersistence(client as never).persist(request);
    expect(result).toMatchObject({ authority: "runtime", revision: 1 });
    expect(client.prepareChapter).toHaveBeenCalledOnce();
    expect(client.validateReviews).toHaveBeenCalledOnce();
    expect(client.validateChapter).toHaveBeenCalledOnce();
    expect(client.commitChapter).toHaveBeenCalledOnce();
  });

  it("does not commit blocking validation", async () => {
    const client = runtimeClient();
    client.validateChapter.mockResolvedValueOnce({ ...(await client.validateChapter()), state: "REJECTED", validation_token: null, issues: [{ severity: "blocking", code: "CONFLICT", message: "conflict", event_ordinal: null }] });
    await expect(new StoryRuntimeChapterPersistence(client as never).persist(input())).rejects.toBeInstanceOf(RuntimeValidationBlockedError);
    expect(client.commitChapter).not.toHaveBeenCalled();
  });

  it("rolls back unified review consumption without restoring legacy Truth authority", async () => {
    const request = input();
    const client = runtimeClient();
    const result = await new StoryRuntimeChapterPersistence(client as never, false).persist(request);
    expect(result.authority).toBe("runtime");
    expect(client.validateReviews).not.toHaveBeenCalled();
    expect(client.commitChapter).toHaveBeenCalledOnce();
  });

  it("retries a lost commit response with the same idempotent input", async () => {
    const client = runtimeClient();
    const finalized = await client.commitChapter();
    client.commitChapter.mockReset().mockRejectedValueOnce(new StoryRuntimeClientError("lost", "unavailable")).mockResolvedValueOnce(finalized);
    await new StoryRuntimeChapterPersistence(client as never).persist(input());
    expect(client.commitChapter).toHaveBeenCalledTimes(2);
    expect(client.commitChapter.mock.calls[0]?.[0]).toEqual(client.commitChapter.mock.calls[1]?.[0]);
  });

  it("maps typed state delta and UTF-8 body hash", () => {
    const artifacts = buildRuntimeArtifacts(output(), { passed: true, issues: [], summary: "ok" });
    expect(artifacts.events.some((event) => event.aggregate_type === "narrative_thread")).toBe(true);
    expect(artifacts.events.some((event) => event.payload.predicate === "state.currentLocation")).toBe(true);
    expect(artifacts.body_sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(artifacts.summary).toContain("拾起钥匙");
  });

  it("does not access Runtime SQLite or legacy Truth storage", async () => {
    const source = await readFile(new URL("../pipeline/chapter-persistence-port.ts", import.meta.url), "utf-8");
    expect(source).not.toContain("node:sqlite");
    expect(source).not.toContain("memory.db");
    expect(source).not.toContain("current_state.md");
  });
});
