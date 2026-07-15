import {
  ChapterApplicationService,
  ProjectChapterAuthorityResolver,
  StateManager,
  loadProjectConfig,
  type ChapterAnalyticsPort,
  type ChapterExportPort,
  type ChapterReadPort,
} from "@actalk/inkos-core";

type TuiChapterService = ChapterReadPort & ChapterAnalyticsPort & ChapterExportPort;

export async function renderTuiChapterCommand(
  service: TuiChapterService,
  bookId: string,
  input: string,
): Promise<string | undefined> {
  if (input === "/chapters") {
    const page = await service.list(bookId, { limit: 100 });
    const rows = page.items.map((chapter) =>
      `${chapter.number}. ${chapter.title} | ${chapter.characterCount} chars | ${chapter.bodyChecksum.slice(0, 12)}`,
    );
    return [`Runtime chapters (${page.totalCount}), latest ${page.latestChapter}, revision ${page.projectRevision}`, ...rows].join("\n");
  }

  const detail = /^\/chapter\s+(\d+)$/.exec(input);
  if (detail) {
    const chapter = await service.get(bookId, Number(detail[1]));
    return [`Chapter ${chapter.number}: ${chapter.title}`, `SHA-256: ${chapter.bodyChecksum}`, "", chapter.body].join("\n");
  }

  if (input === "/stats") {
    const analytics = await service.analytics(bookId);
    return [
      `Runtime stats at revision ${analytics.projectRevision}`,
      `Chapters: ${analytics.totalChapters}`,
      `Characters: ${analytics.totalWords}`,
      `Average: ${analytics.avgWordsPerChapter}`,
    ].join("\n");
  }

  const search = /^\/search\s+(.+)$/.exec(input);
  if (search) {
    const result = await service.search(bookId, { query: search[1], limit: 25 });
    const rows = result.items.map((chapter) =>
      `${chapter.number}. ${chapter.title} | ${chapter.bodyChecksum} | ${chapter.snippet}`,
    );
    return [`Runtime search (${result.totalCount}), revision ${result.projectRevision}, index revision ${result.indexRevision}`, ...rows].join("\n");
  }

  if (input === "/export") {
    const snapshot = await service.exportSnapshot(bookId);
    return [
      `Runtime export: ${snapshot.chapters.length} chapters, revision ${snapshot.projectRevision}`,
      `Collection SHA-256: ${snapshot.collectionChecksum}`,
      ...snapshot.chapters.map((chapter) => `${chapter.number}. ${chapter.title} | ${chapter.bodyChecksum}`),
    ].join("\n");
  }

  return undefined;
}

export async function renderProjectTuiChapterCommand(projectRoot: string, bookId: string, input: string): Promise<string | undefined> {
  const state = new StateManager(projectRoot);
  const config = await loadProjectConfig(projectRoot);
  const service = new ChapterApplicationService(new ProjectChapterAuthorityResolver(state, {
    storyRuntime: config.storyRuntime,
    apiToken: config.storyRuntime.apiTokenEnv ? process.env[config.storyRuntime.apiTokenEnv] : undefined,
  }));
  return renderTuiChapterCommand(service, bookId, input);
}
