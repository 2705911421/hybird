import { createHash, randomUUID } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import {
  ChapterApplicationService,
  ProjectChapterAuthorityResolver,
} from "../chapter-application-service.js";
import { StoryRuntimeClient } from "../story-runtime/client.js";

const now = "2026-07-13T00:00:00.000Z";
const sha = (body: string) => createHash("sha256").update(body, "utf8").digest("hex");
const bodies = ["Runtime 第一章", "Runtime 第二章", "Runtime 第三章"];
const ids = [randomUUID(), randomUUID(), randomUUID()];
const items = bodies.map((body, index) => ({
  chapter_id: ids[index]!, chapter_number: index + 1, order_key: index + 1, state: "FINALIZED" as const,
  title: `第${index + 1}章`, summary: `摘要${index + 1}`, body_sha256: sha(body), artifact_sha256: sha(`artifact-${index}`),
  character_count: [...body].length, commit_id: ids[index]!, resulting_revision: index + 1,
  volume_id: null, created_at: now, updated_at: now, finalized_at: now,
}));

function runtimeClient(overrides: { readonly malformed?: boolean; readonly unavailable?: boolean } = {}) {
  const fetchImpl = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    if (overrides.unavailable) throw new Error("offline");
    const url = new URL(String(input));
    if (overrides.malformed) return new Response(JSON.stringify({ unexpected: true }), { status: 200, headers: { "content-type": "application/json" } });
    if (url.pathname.endsWith("/chapters")) {
      return Response.json({ project_id: "runtime-book", revision: 7, finalized_only: true, total_count: 3, latest_chapter: 3, items, page: { limit: 50, has_more: false, next_cursor: null } });
    }
    if (url.pathname.endsWith("/chapter-aggregate")) {
      return Response.json({ project_id: "runtime-book", revision: 7, chapter_count: 3, latest_chapter: 3, total_characters: items.reduce((sum, item) => sum + item.character_count, 0), chapters: items.map((item) => ({ chapter_number: item.chapter_number, character_count: item.character_count, volume_id: null, created_at: now, updated_at: now, finalized_at: now })), volumes: [] });
    }
    if (url.pathname.endsWith("/chapter-export")) {
      return Response.json({ snapshot_id: "runtime-book:7:snapshot", project_id: "runtime-book", revision: 7, finalized_only: true, collection_sha256: sha(items.map((item) => `${item.chapter_number}:${item.body_sha256}`).join("\n")), chapter_count: 3, chapters: items.map((item, index) => ({ ...item, body: bodies[index] })), created_at: now });
    }
    if (url.pathname.endsWith("/chapter-search")) {
      return Response.json({ project_id: "runtime-book", revision: 7, index_revision: 7, stale: false, query: "第二", total_count: 1, items: [{ ...items[1], body: bodies[1], snippet: bodies[1] }], page: { limit: 25, has_more: false, next_cursor: null } });
    }
    const chapter = Number(url.pathname.split("/").at(-1));
    const item = items[chapter - 1]!;
    return Response.json({ project_id: "runtime-book", chapter_id: item.chapter_id, chapter_number: chapter, revision: item.resulting_revision, commit_id: item.commit_id, title: item.title, body: bodies[chapter - 1], summary: item.summary, body_sha256: item.body_sha256, artifact_sha256: item.artifact_sha256, volume_id: null, created_at: now, updated_at: now, finalized_at: now });
  });
  return { client: new StoryRuntimeClient({ baseUrl: "http://runtime.test", fetchImpl: fetchImpl as typeof fetch }), fetchImpl };
}

function runtimeState(loadChapterIndex = vi.fn(async () => { throw new Error("Runtime authority must not read local chapters"); })) {
  return {
    loadBookConfig: vi.fn(async () => ({ authorityMode: "runtime" as const })),
    loadChapterIndex,
    bookDir: vi.fn(() => "C:/fixture/books/runtime-book"),
  };
}

describe("ChapterApplicationService", () => {
  it("uses Runtime for list, detail, analytics, search and fixed-revision export", async () => {
    const state = runtimeState();
    const { client } = runtimeClient();
    const service = new ChapterApplicationService(new ProjectChapterAuthorityResolver(state as never, { runtimeClient: client }));

    await expect(service.list("runtime-book")).resolves.toMatchObject({ totalCount: 3, latestChapter: 3, projectRevision: 7 });
    await expect(service.get("runtime-book", 2)).resolves.toMatchObject({ body: bodies[1], bodyChecksum: sha(bodies[1]!) });
    await expect(service.analytics("runtime-book")).resolves.toMatchObject({ totalChapters: 3, authority: "runtime", projectRevision: 7 });
    await expect(service.search("runtime-book", { query: "第二" })).resolves.toMatchObject({ totalCount: 1, stale: false });
    await expect(service.exportSnapshot("runtime-book", { expectedRevision: 7 })).resolves.toMatchObject({ projectRevision: 7, chapters: [{ number: 1 }, { number: 2 }, { number: 3 }] });
    expect(state.loadChapterIndex).not.toHaveBeenCalled();
  });

  it("fails closed when Runtime is unavailable and never selects legacy", async () => {
    const local = vi.fn(async () => [{ number: 4 }]);
    const state = runtimeState(local);
    const { client } = runtimeClient({ unavailable: true });
    const service = new ChapterApplicationService(new ProjectChapterAuthorityResolver(state as never, { runtimeClient: client }));
    await expect(service.list("runtime-book")).rejects.toMatchObject({ code: "runtime_unavailable" });
    expect(local).not.toHaveBeenCalled();
  });

  it("reports malformed Runtime DTOs as contract mismatch without local fallback", async () => {
    const local = vi.fn(async () => [{ number: 2 }]);
    const state = runtimeState(local);
    const { client } = runtimeClient({ malformed: true });
    const service = new ChapterApplicationService(new ProjectChapterAuthorityResolver(state as never, { runtimeClient: client }));
    await expect(service.list("runtime-book")).rejects.toMatchObject({ code: "runtime_contract_mismatch" });
    expect(local).not.toHaveBeenCalled();
  });
});
