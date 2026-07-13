import { Command } from "commander";
import { ChapterApplicationService, ProjectChapterAuthorityResolver, StateManager } from "@actalk/inkos-core";
import { findProjectRoot, loadConfig, log, logError, resolveBookId } from "../utils.js";

async function serviceFor(bookIdArg?: string) {
  const root = findProjectRoot();
  const [config, bookId] = await Promise.all([
    loadConfig({ requireApiKey: false, projectRoot: root }),
    resolveBookId(bookIdArg, root),
  ]);
  const state = new StateManager(root);
  const service = new ChapterApplicationService(new ProjectChapterAuthorityResolver(state, {
    storyRuntime: config.storyRuntime,
    apiToken: config.storyRuntime.apiTokenEnv ? process.env[config.storyRuntime.apiTokenEnv] : undefined,
  }));
  return { bookId, service };
}

function fail(error: unknown): never {
  logError(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

export const chapterCommand = new Command("chapter").description("Read finalized chapters through the project authority service");

chapterCommand.command("list")
  .argument("[book-id]")
  .option("--limit <number>", "Page size", "50")
  .option("--cursor <cursor>")
  .option("--from <chapter>")
  .option("--to <chapter>")
  .option("--volume <volumeId>")
  .option("--json")
  .action(async (bookIdArg: string | undefined, options) => {
    try {
      const { bookId, service } = await serviceFor(bookIdArg);
      const page = await service.list(bookId, {
        limit: Number(options.limit), cursor: options.cursor,
        fromChapter: options.from ? Number(options.from) : undefined,
        toChapter: options.to ? Number(options.to) : undefined,
        volumeId: options.volume,
      });
      if (options.json) return log(JSON.stringify(page, null, 2));
      log(`${page.totalCount} chapters | latest ${page.latestChapter} | revision ${page.projectRevision} | ${page.authority}`);
      for (const chapter of page.items) log(`${chapter.number}\t${chapter.title}\t${chapter.bodyChecksum}\tr${chapter.resultingRevision}`);
      if (page.nextCursor) log(`Next cursor: ${page.nextCursor}`);
    } catch (error) { fail(error); }
  });

chapterCommand.command("show")
  .argument("<chapter>")
  .argument("[book-id]")
  .option("--json")
  .action(async (chapterArg: string, bookIdArg: string | undefined, options) => {
    try {
      const { bookId, service } = await serviceFor(bookIdArg);
      const chapter = await service.get(bookId, Number(chapterArg));
      log(options.json ? JSON.stringify(chapter, null, 2) : chapter.body);
    } catch (error) { fail(error); }
  });

chapterCommand.command("latest")
  .argument("[book-id]")
  .option("--json")
  .action(async (bookIdArg: string | undefined, options) => {
    try {
      const { bookId, service } = await serviceFor(bookIdArg);
      const chapter = await service.latest(bookId);
      log(options.json ? JSON.stringify(chapter, null, 2) : chapter ? `${chapter.number}\t${chapter.title}\t${chapter.bodyChecksum}\tr${chapter.resultingRevision}` : "No finalized chapters.");
    } catch (error) { fail(error); }
  });

chapterCommand.command("search")
  .argument("<query>")
  .argument("[book-id]")
  .option("--limit <number>", "Page size", "25")
  .option("--cursor <cursor>")
  .option("--json")
  .action(async (query: string, bookIdArg: string | undefined, options) => {
    try {
      const { bookId, service } = await serviceFor(bookIdArg);
      const result = await service.search(bookId, { query, limit: Number(options.limit), cursor: options.cursor });
      if (options.json) return log(JSON.stringify(result, null, 2));
      log(`${result.totalCount} matches | revision ${result.projectRevision} | stale=${result.stale}`);
      for (const hit of result.items) log(`${hit.number}\t${hit.title}\t${hit.snippet}`);
    } catch (error) { fail(error); }
  });
