import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import type { StateManager } from "./state/manager.js";
import type { StoryRuntimeConfig } from "./story-runtime/schemas.js";
import { StoryRuntimeClient, StoryRuntimeClientError } from "./story-runtime/client.js";
import { computeAnalytics, type AnalyticsData } from "./utils/analytics.js";

export type ChapterAuthority = "runtime" | "legacy";
export type ChapterApplicationErrorCode =
  | "runtime_unavailable"
  | "runtime_timeout"
  | "runtime_contract_mismatch"
  | "runtime_version_mismatch"
  | "runtime_unauthorized"
  | "invalid_authority_mode"
  | "database_locked"
  | "revision_changed"
  | "checksum_mismatch"
  | "not_found"
  | "legacy_read_failed";

export class ChapterApplicationError extends Error {
  constructor(
    readonly code: ChapterApplicationErrorCode,
    message: string,
    readonly retryable = false,
    readonly currentRevision?: number,
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = "ChapterApplicationError";
  }
}

export interface ChapterListItem {
  readonly chapterId: string;
  readonly number: number;
  readonly orderKey: number;
  readonly title: string;
  readonly status: string;
  readonly summary: string;
  readonly bodyChecksum: string;
  readonly artifactChecksum: string;
  readonly characterCount: number;
  readonly commitId?: string;
  readonly resultingRevision: number;
  readonly volumeId?: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly finalizedAt: string;
  readonly auditIssues: ReadonlyArray<string>;
}

export interface ChapterDetail extends ChapterListItem {
  readonly body: string;
}

export interface ChapterPage {
  readonly authority: ChapterAuthority;
  readonly projectRevision: number;
  readonly totalCount: number;
  readonly latestChapter: number;
  readonly items: ReadonlyArray<ChapterListItem>;
  readonly hasMore: boolean;
  readonly nextCursor?: string;
}

export interface ChapterCollectionSummary {
  readonly authority: ChapterAuthority;
  readonly projectRevision: number;
  readonly chapterCount: number;
  readonly latestChapter: number;
  readonly totalCharacters: number;
  readonly chapters: ReadonlyArray<{
    readonly number: number;
    readonly characterCount: number;
    readonly volumeId?: string;
    readonly createdAt: string;
    readonly updatedAt: string;
    readonly finalizedAt: string;
  }>;
  readonly volumes: ReadonlyArray<{ readonly volumeId: string; readonly chapterCount: number; readonly characterCount: number }>;
}

export interface ChapterExportSnapshot {
  readonly authority: ChapterAuthority;
  readonly snapshotId: string;
  readonly projectRevision: number;
  readonly collectionChecksum: string;
  readonly chapters: ReadonlyArray<ChapterDetail>;
  readonly createdAt: string;
}

export interface ChapterSearchPage extends ChapterPage {
  readonly query: string;
  readonly indexRevision: number;
  readonly stale: boolean;
  readonly items: ReadonlyArray<ChapterDetail & { readonly snippet: string }>;
}

export interface ChapterReadPort {
  list(projectId: string, query?: { readonly cursor?: string; readonly limit?: number; readonly fromChapter?: number; readonly toChapter?: number; readonly volumeId?: string }): Promise<ChapterPage>;
  get(projectId: string, chapterNumber: number): Promise<ChapterDetail>;
  summary(projectId: string): Promise<ChapterCollectionSummary>;
  search(projectId: string, request: { readonly query: string; readonly cursor?: string; readonly limit?: number }): Promise<ChapterSearchPage>;
}

export interface ChapterExportPort {
  exportSnapshot(projectId: string, request?: { readonly expectedRevision?: number; readonly fromChapter?: number; readonly toChapter?: number; readonly volumeId?: string; readonly approvedOnly?: boolean }): Promise<ChapterExportSnapshot>;
}

export interface ChapterAnalyticsPort {
  analytics(projectId: string): Promise<AnalyticsData & { readonly authority: ChapterAuthority; readonly projectRevision: number; readonly stale: false }>;
}

type ChapterPort = ChapterReadPort & ChapterExportPort & ChapterAnalyticsPort;

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function runtimeItem(item: {
  readonly chapter_id: string; readonly chapter_number: number; readonly order_key: number;
  readonly title: string; readonly summary: string; readonly body_sha256: string; readonly artifact_sha256: string;
  readonly character_count: number; readonly commit_id: string; readonly resulting_revision: number;
  readonly volume_id: string | null; readonly created_at: string; readonly updated_at: string; readonly finalized_at: string;
}): ChapterListItem {
  return {
    chapterId: item.chapter_id,
    number: item.chapter_number,
    orderKey: item.order_key,
    title: item.title,
    status: "finalized",
    summary: item.summary,
    bodyChecksum: item.body_sha256,
    artifactChecksum: item.artifact_sha256,
    characterCount: item.character_count,
    commitId: item.commit_id,
    resultingRevision: item.resulting_revision,
    ...(item.volume_id ? { volumeId: item.volume_id } : {}),
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    finalizedAt: item.finalized_at,
    auditIssues: [],
  };
}

function verifyBody(chapter: ChapterDetail): ChapterDetail {
  if (sha256(chapter.body) !== chapter.bodyChecksum) {
    throw new ChapterApplicationError("checksum_mismatch", `Chapter ${chapter.number} body checksum mismatch.`);
  }
  return chapter;
}

function mapRuntimeError(error: unknown): never {
  if (!(error instanceof StoryRuntimeClientError)) throw error;
  if (error.code === "malformed_response") {
    throw new ChapterApplicationError("runtime_contract_mismatch", error.message, false, error.currentRevision, error);
  }
  if (error.runtimeCode === "DATABASE_LOCKED") {
    throw new ChapterApplicationError("database_locked", error.message, true, error.currentRevision, error);
  }
  if (error.runtimeCode === "REVISION_CHANGED") {
    throw new ChapterApplicationError("revision_changed", error.message, true, error.currentRevision, error);
  }
  if (error.runtimeCode === "VERSION_MISMATCH") {
    throw new ChapterApplicationError("runtime_version_mismatch", error.message, false, error.currentRevision, error);
  }
  if (error.status === 401 || error.status === 403) {
    throw new ChapterApplicationError("runtime_unauthorized", "Story Runtime rejected the configured credentials.", false, error.currentRevision, error);
  }
  if (error.status === 404) {
    throw new ChapterApplicationError("not_found", error.message, false, error.currentRevision, error);
  }
  const aborted = error.cause instanceof Error && error.cause.name === "AbortError";
  throw new ChapterApplicationError(aborted ? "runtime_timeout" : "runtime_unavailable", error.message, true, error.currentRevision, error);
}

export class StoryRuntimeChapterReadAdapter implements ChapterPort {
  constructor(private readonly client: StoryRuntimeClient) {}

  async list(projectId: string, query: Parameters<ChapterReadPort["list"]>[1] = {}): Promise<ChapterPage> {
    try {
      await this.client.assertCompatible();
      const result = await this.client.finalizedChapters(projectId, query);
      return {
        authority: "runtime", projectRevision: result.revision, totalCount: result.total_count,
        latestChapter: result.latest_chapter, items: result.items.map(runtimeItem),
        hasMore: result.page.has_more, ...(result.page.next_cursor ? { nextCursor: result.page.next_cursor } : {}),
      };
    } catch (error) { return mapRuntimeError(error); }
  }

  async get(projectId: string, chapterNumber: number): Promise<ChapterDetail> {
    try {
      await this.client.assertCompatible();
      const result = await this.client.finalizedChapter(projectId, chapterNumber);
      return verifyBody({
        chapterId: result.chapter_id, number: result.chapter_number, orderKey: result.chapter_number,
        title: result.title, status: "finalized", summary: result.summary, body: result.body,
        bodyChecksum: result.body_sha256, artifactChecksum: result.artifact_sha256,
        characterCount: [...result.body].length, commitId: result.commit_id,
        resultingRevision: result.revision, ...(result.volume_id ? { volumeId: result.volume_id } : {}),
        createdAt: result.created_at, updatedAt: result.updated_at, finalizedAt: result.finalized_at, auditIssues: [],
      });
    } catch (error) { return mapRuntimeError(error); }
  }

  async listAll(projectId: string, query: Omit<NonNullable<Parameters<ChapterReadPort["list"]>[1]>, "cursor" | "limit"> = {}): Promise<ChapterPage> {
    const items: ChapterListItem[] = [];
    let cursor: string | undefined;
    let first: ChapterPage | undefined;
    do {
      const page = await this.list(projectId, { ...query, cursor, limit: 100 });
      first ??= page;
      if (page.projectRevision !== first.projectRevision) {
        throw new ChapterApplicationError("revision_changed", "Project revision changed while collecting chapter pages.", true, page.projectRevision);
      }
      items.push(...page.items);
      cursor = page.nextCursor;
    } while (cursor);
    return first ? { ...first, items, hasMore: false, nextCursor: undefined } : {
      authority: "legacy", projectRevision: 0, totalCount: 0, latestChapter: 0, items: [], hasMore: false,
    };
  }

  async summary(projectId: string): Promise<ChapterCollectionSummary> {
    try {
      await this.client.assertCompatible();
      const result = await this.client.chapterAggregate(projectId);
      return {
        authority: "runtime", projectRevision: result.revision, chapterCount: result.chapter_count,
        latestChapter: result.latest_chapter, totalCharacters: result.total_characters,
        chapters: result.chapters.map((chapter) => ({
          number: chapter.chapter_number, characterCount: chapter.character_count,
          ...(chapter.volume_id ? { volumeId: chapter.volume_id } : {}),
          createdAt: chapter.created_at, updatedAt: chapter.updated_at, finalizedAt: chapter.finalized_at,
        })),
        volumes: result.volumes.map((volume) => ({
          volumeId: volume.volume_id, chapterCount: volume.chapter_count, characterCount: volume.character_count,
        })),
      };
    } catch (error) { return mapRuntimeError(error); }
  }

  async exportSnapshot(projectId: string, request: Parameters<ChapterExportPort["exportSnapshot"]>[1] = {}): Promise<ChapterExportSnapshot> {
    try {
      await this.client.assertCompatible();
      const result = await this.client.chapterExport(projectId, request);
      return {
        authority: "runtime", snapshotId: result.snapshot_id, projectRevision: result.revision,
        collectionChecksum: result.collection_sha256, createdAt: result.created_at,
        chapters: result.chapters.map((chapter) => verifyBody({ ...runtimeItem(chapter), body: chapter.body })),
      };
    } catch (error) { return mapRuntimeError(error); }
  }

  async search(projectId: string, request: Parameters<ChapterReadPort["search"]>[1]): Promise<ChapterSearchPage> {
    try {
      await this.client.assertCompatible();
      const result = await this.client.searchChapters(projectId, request);
      return {
        authority: "runtime", projectRevision: result.revision, indexRevision: result.index_revision,
        stale: result.stale, query: result.query, totalCount: result.total_count,
        latestChapter: result.items.at(-1)?.chapter_number ?? 0,
        items: result.items.map((chapter) => ({ ...verifyBody({ ...runtimeItem(chapter), body: chapter.body }), snippet: chapter.snippet })),
        hasMore: result.page.has_more, ...(result.page.next_cursor ? { nextCursor: result.page.next_cursor } : {}),
      };
    } catch (error) { return mapRuntimeError(error); }
  }

  async analytics(projectId: string): Promise<AnalyticsData & { readonly authority: "runtime"; readonly projectRevision: number; readonly stale: false }> {
    const summary = await this.summary(projectId);
    return {
      bookId: projectId, totalChapters: summary.chapterCount, totalWords: summary.totalCharacters,
      avgWordsPerChapter: summary.chapterCount ? Math.round(summary.totalCharacters / summary.chapterCount) : 0,
      auditPassRate: null, topIssueCategories: [], chaptersWithMostIssues: [],
      statusDistribution: { finalized: summary.chapterCount }, authority: "runtime",
      projectRevision: summary.projectRevision, stale: false,
    };
  }
}

/** Deprecated/import-only adapter for projects that have not cut over to Runtime authority. */
export class LegacyChapterReadAdapter implements ChapterPort {
  constructor(private readonly state: Pick<StateManager, "bookDir" | "loadChapterIndex">) {}

  private async records(projectId: string): Promise<ReadonlyArray<ChapterDetail & { readonly status: string; readonly auditIssues: ReadonlyArray<string> }>> {
    try {
      const index = await this.state.loadChapterIndex(projectId);
      const chaptersDir = join(this.state.bookDir(projectId), "chapters");
      const files = await readdir(chaptersDir).catch(() => [] as string[]);
      const byNumber = new Map<number, string>();
      for (const file of files) {
        const match = file.match(/^(\d+)[_-]?.*\.md$/);
        if (match && !byNumber.has(Number(match[1]))) byNumber.set(Number(match[1]), file);
      }
      return Promise.all(index.map(async (chapter) => {
        const body = byNumber.has(chapter.number) ? await readFile(join(chaptersDir, byNumber.get(chapter.number)!), "utf8") : "";
        const checksum = sha256(body);
        return {
          chapterId: `legacy:${projectId}:${chapter.number}`, number: chapter.number, orderKey: chapter.number,
          title: chapter.title, status: chapter.status, summary: "", body, bodyChecksum: checksum, artifactChecksum: checksum,
          characterCount: body ? [...body].length : chapter.wordCount, resultingRevision: 0,
          createdAt: chapter.createdAt, updatedAt: chapter.updatedAt, finalizedAt: chapter.updatedAt,
          auditIssues: chapter.auditIssues,
        };
      }));
    } catch (error) {
      throw new ChapterApplicationError("legacy_read_failed", `Legacy chapter read failed: ${String(error)}`, false, undefined, error);
    }
  }

  async list(projectId: string, query: Parameters<ChapterReadPort["list"]>[1] = {}): Promise<ChapterPage> {
    const records = (await this.records(projectId)).filter((item) =>
      (query.fromChapter === undefined || item.number >= query.fromChapter)
      && (query.toChapter === undefined || item.number <= query.toChapter)
      && query.volumeId === undefined,
    );
    const offset = query.cursor ? Number(query.cursor) : 0;
    const limit = query.limit ?? 50;
    const items = records.slice(offset, offset + limit);
    const hasMore = offset + limit < records.length;
    return {
      authority: "legacy", projectRevision: 0, totalCount: records.length,
      latestChapter: records.at(-1)?.number ?? 0, items, hasMore,
      ...(hasMore ? { nextCursor: String(offset + limit) } : {}),
    };
  }

  async get(projectId: string, chapterNumber: number): Promise<ChapterDetail> {
    const record = (await this.records(projectId)).find((item) => item.number === chapterNumber);
    if (!record) throw new ChapterApplicationError("not_found", `Chapter ${chapterNumber} was not found.`);
    return record;
  }

  async summary(projectId: string): Promise<ChapterCollectionSummary> {
    const records = await this.records(projectId);
    return {
      authority: "legacy", projectRevision: 0, chapterCount: records.length,
      latestChapter: records.at(-1)?.number ?? 0,
      totalCharacters: records.reduce((sum, chapter) => sum + chapter.characterCount, 0),
      chapters: records.map((chapter) => ({
        number: chapter.number, characterCount: chapter.characterCount,
        createdAt: chapter.createdAt, updatedAt: chapter.updatedAt, finalizedAt: chapter.finalizedAt,
      })), volumes: [],
    };
  }

  async exportSnapshot(projectId: string, request: Parameters<ChapterExportPort["exportSnapshot"]>[1] = {}): Promise<ChapterExportSnapshot> {
    const records = (await this.records(projectId)).filter((item) =>
      (request.fromChapter === undefined || item.number >= request.fromChapter)
      && (request.toChapter === undefined || item.number <= request.toChapter)
      && request.volumeId === undefined,
    ).filter((item) => !request.approvedOnly || item.status === "approved" || item.status === "published");
    const collectionChecksum = sha256(records.map((item) => `${item.number}:${item.bodyChecksum}`).join("\n"));
    return {
      authority: "legacy", snapshotId: `legacy:${projectId}:${collectionChecksum.slice(0, 16)}`,
      projectRevision: 0, collectionChecksum, chapters: records, createdAt: new Date().toISOString(),
    };
  }

  async search(projectId: string, request: Parameters<ChapterReadPort["search"]>[1]): Promise<ChapterSearchPage> {
    const matches = (await this.records(projectId)).filter((item) =>
      `${item.title}\n${item.summary}\n${item.body}`.toLocaleLowerCase().includes(request.query.toLocaleLowerCase()),
    );
    const offset = request.cursor ? Number(request.cursor) : 0;
    const limit = request.limit ?? 25;
    const items = matches.slice(offset, offset + limit).map((item) => ({ ...item, snippet: item.summary || item.body.slice(0, 240) }));
    const hasMore = offset + limit < matches.length;
    return {
      authority: "legacy", projectRevision: 0, indexRevision: 0, stale: false,
      query: request.query, totalCount: matches.length, latestChapter: matches.at(-1)?.number ?? 0,
      items, hasMore, ...(hasMore ? { nextCursor: String(offset + limit) } : {}),
    };
  }

  async analytics(projectId: string): Promise<AnalyticsData & { readonly authority: "legacy"; readonly projectRevision: 0; readonly stale: false }> {
    const records = await this.records(projectId);
    return {
      ...computeAnalytics(projectId, records.map((item) => ({
        number: item.number, status: item.status, wordCount: item.characterCount, auditIssues: item.auditIssues,
      }))), authority: "legacy", projectRevision: 0, stale: false,
    };
  }
}

export class ProjectChapterAuthorityResolver {
  private readonly runtimeAdapter?: StoryRuntimeChapterReadAdapter;

  constructor(
    private readonly state: Pick<StateManager, "loadBookConfig" | "bookDir" | "loadChapterIndex">,
    options: { readonly storyRuntime?: StoryRuntimeConfig; readonly runtimeClient?: StoryRuntimeClient; readonly apiToken?: string } = {},
  ) {
    const config = options.storyRuntime;
    if (config && config.mode !== "story-runtime") {
      throw new ChapterApplicationError("invalid_authority_mode", `Unsupported chapter authority mode: ${String(config.mode)}`);
    }
    if (options.runtimeClient) this.runtimeAdapter = new StoryRuntimeChapterReadAdapter(options.runtimeClient);
    else if (config?.mode === "story-runtime") {
      this.runtimeAdapter = new StoryRuntimeChapterReadAdapter(new StoryRuntimeClient({
        baseUrl: config.baseUrl, timeoutMs: config.timeoutMs, apiToken: options.apiToken,
      }));
    }
  }

  async resolve(projectId: string): Promise<ChapterPort> {
    const book = await this.state.loadBookConfig(projectId);
    if (book.authorityMode === "runtime") {
      if (!this.runtimeAdapter) {
        throw new ChapterApplicationError("runtime_unavailable", "Runtime authority is configured but no Runtime client is available.", true);
      }
      return this.runtimeAdapter;
    }
    if (book.authorityMode !== undefined && book.authorityMode !== "legacy") {
      throw new ChapterApplicationError("invalid_authority_mode", `Unsupported project chapter authority: ${String(book.authorityMode)}`);
    }
    return new LegacyChapterReadAdapter(this.state);
  }
}

export class ChapterApplicationService implements ChapterReadPort, ChapterExportPort, ChapterAnalyticsPort {
  constructor(private readonly resolver: ProjectChapterAuthorityResolver) {}

  async list(projectId: string, query?: Parameters<ChapterReadPort["list"]>[1]): Promise<ChapterPage> {
    return (await this.resolver.resolve(projectId)).list(projectId, query);
  }

  async get(projectId: string, chapterNumber: number): Promise<ChapterDetail> {
    return (await this.resolver.resolve(projectId)).get(projectId, chapterNumber);
  }

  async listAll(projectId: string, query: Omit<NonNullable<Parameters<ChapterReadPort["list"]>[1]>, "cursor" | "limit"> = {}): Promise<ChapterPage> {
    const items: ChapterListItem[] = [];
    let cursor: string | undefined;
    let first: ChapterPage | undefined;
    do {
      const page = await this.list(projectId, { ...query, cursor, limit: 100 });
      first ??= page;
      if (page.projectRevision !== first.projectRevision) {
        throw new ChapterApplicationError("revision_changed", "Project revision changed while collecting chapter pages.", true, page.projectRevision);
      }
      items.push(...page.items);
      cursor = page.nextCursor;
    } while (cursor);
    return { ...first!, items, hasMore: false };
  }

  async latest(projectId: string): Promise<ChapterDetail | null> {
    const page = await this.list(projectId, { limit: 1 });
    if (page.latestChapter === 0) return null;
    return (await this.resolver.resolve(projectId)).get(projectId, page.latestChapter);
  }

  async summary(projectId: string): Promise<ChapterCollectionSummary> {
    return (await this.resolver.resolve(projectId)).summary(projectId);
  }

  async analytics(projectId: string): Promise<AnalyticsData & { readonly authority: ChapterAuthority; readonly projectRevision: number; readonly stale: false }> {
    return (await this.resolver.resolve(projectId)).analytics(projectId);
  }

  async exportSnapshot(projectId: string, request?: Parameters<ChapterExportPort["exportSnapshot"]>[1]): Promise<ChapterExportSnapshot> {
    return (await this.resolver.resolve(projectId)).exportSnapshot(projectId, request);
  }

  async search(projectId: string, request: Parameters<ChapterReadPort["search"]>[1]): Promise<ChapterSearchPage> {
    return (await this.resolver.resolve(projectId)).search(projectId, request);
  }
}
