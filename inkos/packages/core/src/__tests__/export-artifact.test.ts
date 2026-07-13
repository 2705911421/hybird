import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChapterExportPort, ChapterExportSnapshot, ChapterDetail } from "../chapter-application-service.js";
import { writeExportArtifact } from "../interaction/export-artifact.js";

const sha256 = (value: string) => createHash("sha256").update(value, "utf8").digest("hex");
const createdRoots: string[] = [];

function chapter(number: number, body: string): ChapterDetail {
  const now = "2026-07-13T00:00:00.000Z";
  return {
    chapterId: `runtime-${number}`,
    number,
    orderKey: number,
    title: `Runtime Chapter ${number}`,
    status: "finalized",
    summary: `Summary ${number}`,
    body,
    bodyChecksum: sha256(body),
    artifactChecksum: sha256(`artifact-${number}`),
    characterCount: [...body].length,
    commitId: `commit-${number}`,
    resultingRevision: 7,
    createdAt: now,
    updatedAt: now,
    finalizedAt: now,
    auditIssues: [],
  };
}

afterEach(async () => {
  await Promise.all(createdRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("Runtime-backed export artifact", () => {
  it("writes CJK and large bodies with a revision-bound manifest without local chapter reads", async () => {
    const root = await mkdtemp(join(tmpdir(), "inkos-runtime-export-"));
    createdRoots.push(root);
    const bodies = ["Runtime chapter one.", "\u7b2c\u4e8c\u7ae0\uff1a\u96e8\u591c\u7801\u5934\u3002", "x".repeat(512_000)];
    const chapters = bodies.map((body, index) => chapter(index + 1, body));
    const collectionChecksum = sha256(chapters.map((item) => `${item.number}:${item.bodyChecksum}`).join("\n"));
    const snapshot: ChapterExportSnapshot = {
      authority: "runtime",
      snapshotId: `runtime-book:7:${collectionChecksum.slice(0, 16)}`,
      projectRevision: 7,
      collectionChecksum,
      chapters,
      createdAt: "2026-07-13T00:00:00.000Z",
    };
    const exportSnapshot = vi.fn(async () => snapshot);
    const chapterService: ChapterExportPort = { exportSnapshot };
    const outputPath = join(root, "runtime-book.txt");
    const state = {
      bookDir: (bookId: string) => join(root, "books", bookId),
      loadBookConfig: vi.fn(async () => ({ title: "Runtime Book", language: "zh" })),
    };

    const result = await writeExportArtifact(state, "runtime-book", { chapterService, outputPath });
    const output = await readFile(result.outputPath, "utf8");
    const manifest = JSON.parse(await readFile(result.manifestPath, "utf8")) as Record<string, unknown>;

    expect(exportSnapshot).toHaveBeenCalledWith("runtime-book", { approvedOnly: undefined });
    expect(output).toContain(bodies[1]);
    expect(output).toContain(bodies[2]);
    expect(result).toMatchObject({ chaptersExported: 3, projectRevision: 7 });
    expect(manifest).toMatchObject({
      authority: "runtime",
      projectRevision: 7,
      collectionChecksum,
      chapterCount: 3,
      chapters: chapters.map((item) => ({ number: item.number, bodyChecksum: item.bodyChecksum })),
    });
  });
});
