import { describe, expect, it, vi } from "vitest";
import { renderTuiChapterCommand } from "../tui/chapter-surface.js";

const chapter = {
  chapterId: "runtime-2", number: 2, orderKey: 2, title: "Runtime Two", status: "finalized",
  summary: "summary", body: "Runtime body two", bodyChecksum: "a".repeat(64), artifactChecksum: "b".repeat(64),
  characterCount: 16, resultingRevision: 7, createdAt: "2026-07-14T00:00:00Z",
  updatedAt: "2026-07-14T00:00:00Z", finalizedAt: "2026-07-14T00:00:00Z", auditIssues: [],
};

function service() {
  return {
    list: vi.fn(async () => ({ authority: "runtime" as const, projectRevision: 7, totalCount: 1, latestChapter: 2,
      items: [chapter], hasMore: false })),
    get: vi.fn(async () => chapter),
    summary: vi.fn(),
    search: vi.fn(async () => ({ authority: "runtime" as const, projectRevision: 7, totalCount: 1, latestChapter: 2,
      query: "body", indexRevision: 7, stale: false as const, items: [{ ...chapter, snippet: "Runtime body two" }], hasMore: false })),
    exportSnapshot: vi.fn(async () => ({ authority: "runtime" as const, snapshotId: "snapshot-1", projectRevision: 7,
      collectionChecksum: "c".repeat(64), chapters: [chapter], createdAt: "2026-07-15T00:00:00Z" })),
    analytics: vi.fn(async () => ({ bookId: "runtime-book", totalChapters: 1, totalWords: 16,
      avgWordsPerChapter: 16, auditPassRate: 100, topIssueCategories: [], chaptersWithMostIssues: [],
      statusDistribution: { finalized: 1 }, authority: "runtime" as const, projectRevision: 7, stale: false as const })),
  };
}

describe("TUI Runtime chapter surfaces", () => {
  it("renders browser, detail and stats from one application service", async () => {
    const chapters = service();
    await expect(renderTuiChapterCommand(chapters, "runtime-book", "/chapters")).resolves.toContain("Runtime Two");
    await expect(renderTuiChapterCommand(chapters, "runtime-book", "/chapter 2")).resolves.toContain("Runtime body two");
    await expect(renderTuiChapterCommand(chapters, "runtime-book", "/stats")).resolves.toContain("revision 7");
    await expect(renderTuiChapterCommand(chapters, "runtime-book", "/search body")).resolves.toContain(chapter.bodyChecksum);
    await expect(renderTuiChapterCommand(chapters, "runtime-book", "/export")).resolves.toContain("1 chapters, revision 7");
    expect(chapters.list).toHaveBeenCalledWith("runtime-book", { limit: 100 });
    expect(chapters.get).toHaveBeenCalledWith("runtime-book", 2);
    expect(chapters.analytics).toHaveBeenCalledWith("runtime-book");
    expect(chapters.search).toHaveBeenCalledWith("runtime-book", { query: "body", limit: 25 });
    expect(chapters.exportSnapshot).toHaveBeenCalledWith("runtime-book");
  });
});
