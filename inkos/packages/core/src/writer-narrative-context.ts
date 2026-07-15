import type { ChapterExportPort, ChapterExportSnapshot } from "./chapter-application-service.js";
import { ChapterApplicationError } from "./chapter-application-service.js";
import type { StateManager } from "./state/manager.js";

export type WriterNarrativeAuthority = "runtime" | "legacy";

export interface WriterNarrativeChapter {
  readonly chapterNumber: number;
  readonly title: string;
  readonly summary: string;
  readonly body: string;
  readonly bodyChecksum: string;
  readonly finalizedRevision: number;
}

export interface WriterNarrativeContext {
  readonly projectId: string;
  readonly authorityMode: WriterNarrativeAuthority;
  readonly projectRevision: number;
  readonly latestChapter: number;
  readonly recentChapters: ReadonlyArray<WriterNarrativeChapter>;
  readonly previousChapterEnding: string;
  readonly source: WriterNarrativeAuthority;
}

export interface WriterNarrativeContextRequest {
  readonly projectId: string;
  readonly beforeChapter: number;
  readonly expectedRevision?: number;
  readonly limit?: number;
}

export interface WriterNarrativeContextPort {
  load(request: WriterNarrativeContextRequest): Promise<WriterNarrativeContext>;
}

function fromSnapshot(
  request: WriterNarrativeContextRequest,
  snapshot: ChapterExportSnapshot,
  authority: WriterNarrativeAuthority,
): WriterNarrativeContext {
  if (snapshot.authority !== authority) {
    throw new ChapterApplicationError(
      "invalid_authority_mode",
      `Writer narrative ${authority} adapter received ${snapshot.authority} chapter authority.`,
    );
  }
  if (authority === "runtime" && snapshot.projectRevision !== request.expectedRevision) {
    throw new ChapterApplicationError(
      "revision_changed",
      `Writer narrative revision changed from ${request.expectedRevision} to ${snapshot.projectRevision}.`,
      true,
      snapshot.projectRevision,
    );
  }
  const recentChapters = [...snapshot.chapters]
    .sort((left, right) => left.orderKey - right.orderKey)
    .map((chapter): WriterNarrativeChapter => ({
      chapterNumber: chapter.number,
      title: chapter.title,
      summary: chapter.summary,
      body: chapter.body,
      bodyChecksum: chapter.bodyChecksum,
      finalizedRevision: chapter.resultingRevision,
    }));
  const latest = recentChapters.at(-1);
  return {
    projectId: request.projectId,
    authorityMode: authority,
    projectRevision: snapshot.projectRevision,
    latestChapter: latest?.chapterNumber ?? 0,
    recentChapters,
    previousChapterEnding: latest?.body.slice(-1_200) ?? "",
    source: authority,
  };
}

abstract class ChapterExportWriterNarrativeContextAdapter implements WriterNarrativeContextPort {
  protected abstract readonly authority: WriterNarrativeAuthority;

  constructor(private readonly chapters: ChapterExportPort) {}

  async load(request: WriterNarrativeContextRequest): Promise<WriterNarrativeContext> {
    const limit = Math.max(1, request.limit ?? 5);
    const toChapter = request.beforeChapter - 1;
    if (toChapter < 1) {
      return {
        projectId: request.projectId,
        authorityMode: this.authority,
        projectRevision: request.expectedRevision ?? 0,
        latestChapter: 0,
        recentChapters: [],
        previousChapterEnding: "",
        source: this.authority,
      };
    }
    const snapshot = await this.chapters.exportSnapshot(request.projectId, {
      ...(this.authority === "runtime" ? { expectedRevision: request.expectedRevision } : {}),
      fromChapter: Math.max(1, toChapter - limit + 1),
      toChapter,
    });
    return fromSnapshot(request, snapshot, this.authority);
  }
}

export class StoryRuntimeWriterNarrativeContextAdapter extends ChapterExportWriterNarrativeContextAdapter {
  protected readonly authority = "runtime" as const;
}

export class LegacyWriterNarrativeContextAdapter extends ChapterExportWriterNarrativeContextAdapter {
  protected readonly authority = "legacy" as const;
}

export class ProjectWriterNarrativeContextResolver implements WriterNarrativeContextPort {
  private readonly runtime: StoryRuntimeWriterNarrativeContextAdapter;
  private readonly legacy: LegacyWriterNarrativeContextAdapter;

  constructor(
    private readonly state: Pick<StateManager, "loadBookConfig">,
    chapters: ChapterExportPort,
  ) {
    this.runtime = new StoryRuntimeWriterNarrativeContextAdapter(chapters);
    this.legacy = new LegacyWriterNarrativeContextAdapter(chapters);
  }

  async load(request: WriterNarrativeContextRequest): Promise<WriterNarrativeContext> {
    const book = await this.state.loadBookConfig(request.projectId);
    if (book.authorityMode === "runtime") {
      if (request.expectedRevision === undefined) {
        throw new ChapterApplicationError(
          "revision_changed",
          "Runtime writer narrative requires an explicit expected revision.",
        );
      }
      return this.runtime.load(request);
    }
    if (book.authorityMode === undefined || book.authorityMode === "legacy") {
      return this.legacy.load(request);
    }
    throw new ChapterApplicationError(
      "invalid_authority_mode",
      `Unsupported writer narrative authority: ${String(book.authorityMode)}`,
    );
  }
}

export function renderWriterRecentNarrative(context: WriterNarrativeContext): string {
  return context.recentChapters.map((chapter) => [
    `### Chapter ${chapter.chapterNumber}: ${chapter.title}`,
    chapter.summary ? `Summary: ${chapter.summary}` : "",
    chapter.body,
  ].filter(Boolean).join("\n")).join("\n\n---\n\n");
}
