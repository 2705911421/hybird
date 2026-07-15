import { Command } from "commander";
import { ChapterApplicationService, ProjectChapterAuthorityResolver, StoryRuntimeClient, StateManager, formatLengthCount, readGenreProfile, resolveLengthCountingMode } from "@actalk/inkos-core";
import { findProjectRoot, getLegacyMigrationHint, loadConfig, log, logError } from "../utils.js";

export const statusCommand = new Command("status")
  .description("Show project status")
  .argument("[book-id]", "Book ID (optional, shows all if omitted)")
  .option("--chapters", "Show per-chapter status and issues")
  .option("--json", "Output JSON")
  .action(async (bookIdArg: string | undefined, opts) => {
    try {
      const root = findProjectRoot();
      const state = new StateManager(root);
      const config = await loadConfig({ requireApiKey: false, projectRoot: root });
      const runtimeClient = new StoryRuntimeClient({
        baseUrl: config.storyRuntime.baseUrl,
        timeoutMs: config.storyRuntime.timeoutMs,
        apiToken: config.storyRuntime.apiTokenEnv ? process.env[config.storyRuntime.apiTokenEnv] : undefined,
      });
      const runtimeHealth = await runtimeClient.health().then(
        (health) => ({ configuredMode: config.storyRuntime.mode, reachable: true, ...health }),
        (error) => ({ configuredMode: config.storyRuntime.mode, reachable: false, error: String(error) }),
      );
      const chapterService = new ChapterApplicationService(new ProjectChapterAuthorityResolver(state, {
        storyRuntime: config.storyRuntime,
        runtimeClient,
        apiToken: config.storyRuntime.apiTokenEnv ? process.env[config.storyRuntime.apiTokenEnv] : undefined,
      }));

      const allBookIds = await state.listBooks();
      const bookIds = bookIdArg ? [bookIdArg] : allBookIds;

      if (bookIdArg && !allBookIds.includes(bookIdArg)) {
        throw new Error(
          `Book "${bookIdArg}" not found. Available: ${allBookIds.join(", ") || "(none)"}`,
        );
      }

      const booksData = [];

      if (!opts.json) {
        log(`InkOS Project: ${root}`);
        log(`Books: ${allBookIds.length}`);
        log(`Story Runtime: ${runtimeHealth.configuredMode} | ${runtimeHealth.reachable ? ("status" in runtimeHealth ? runtimeHealth.status : "reachable") : "unavailable"}`);
        log("");
      }

      for (const id of bookIds) {
        const book = await state.loadBookConfig(id);
        const [chapterPage, analytics] = await Promise.all([
          chapterService.list(id, { limit: 100 }),
          chapterService.analytics(id),
        ]);
        const migrationHint = await getLegacyMigrationHint(root, id);
        const { profile: genreProfile } = await readGenreProfile(root, book.genre);
        const countingMode = resolveLengthCountingMode(book.language ?? genreProfile.language);

        const approved = (analytics.statusDistribution.approved ?? 0) + (analytics.statusDistribution.finalized ?? 0);
        const pending = analytics.statusDistribution["ready-for-review"] ?? 0;
        const failed = analytics.statusDistribution["audit-failed"] ?? 0;
        const degraded = analytics.statusDistribution["state-degraded"] ?? 0;
        const totalWords = analytics.totalWords;
        const avgWords = analytics.avgWordsPerChapter;

        booksData.push({
          id,
          title: book.title,
          status: book.status,
          genre: book.genre,
          platform: book.platform,
          chapters: chapterPage.totalCount,
          latestChapter: chapterPage.latestChapter,
          projectRevision: chapterPage.projectRevision,
          authority: chapterPage.authority,
          targetChapters: book.targetChapters,
          totalWords,
          avgWordsPerChapter: avgWords,
          approved,
          pending,
          failed,
          degraded,
          ...(migrationHint ? { migrationHint } : {}),
          ...(book.authorityMode === "runtime" ? {
            storyRuntime: await runtimeClient.projectStatus(id),
          } : {}),
          ...(opts.chapters ? {
            chapterList: chapterPage.items.map((ch) => ({
              number: ch.number,
              title: ch.title,
              status: ch.status,
              wordCount: ch.characterCount,
              bodyChecksum: ch.bodyChecksum,
              revision: ch.resultingRevision,
            })),
          } : {}),
        });

        if (!opts.json) {
          log(`  ${book.title} (${id})`);
          log(`    Status: ${book.status}`);
          log(`    Platform: ${book.platform} | Genre: ${book.genre}`);
          log(`    Chapters: ${chapterPage.totalCount} / ${book.targetChapters} (latest ${chapterPage.latestChapter}, revision ${chapterPage.projectRevision})`);
          log(`    Words: ${totalWords.toLocaleString()} (avg ${avgWords}/ch)`);
          log(`    Approved: ${approved} | Pending: ${pending} | Failed: ${failed} | Degraded: ${degraded}`);
          if (migrationHint) {
            log(`    Migration: ${migrationHint}`);
          }

          if (opts.chapters && chapterPage.items.length > 0) {
            log("");
            for (const ch of chapterPage.items) {
              const icon = ch.status === "approved"
                ? "+"
                : ch.status === "audit-failed"
                  ? "!"
                  : ch.status === "state-degraded"
                    ? "x"
                    : "~";
              log(`    [${icon}] Ch.${ch.number} "${ch.title}" | ${formatLengthCount(ch.characterCount, countingMode)} | ${ch.status}`);
              if (ch.auditIssues.length > 0) {
                for (const issue of ch.auditIssues) log(`      ${issue}`);
              }
            }
          }
          log("");
        }
      }

      if (opts.json) {
        log(JSON.stringify({ project: root, storyRuntime: runtimeHealth, books: booksData }, null, 2));
      }
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Failed to get status: ${e}`);
      }
      process.exit(1);
    }
  });
