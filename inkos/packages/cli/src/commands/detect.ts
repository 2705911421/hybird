import { Command } from "commander";
import {
  StateManager,
  ChapterApplicationService,
  ProjectChapterAuthorityResolver,
  detectChapter,
  loadDetectionHistory,
  analyzeDetectionInsights,
  type DetectionConfig,
} from "@actalk/inkos-core";
import { loadConfig, findProjectRoot, resolveBookId, log, logError } from "../utils.js";

export const detectCommand = new Command("detect")
  .description("Run AIGC detection on chapters")
  .argument("[book-id]", "Book ID (auto-detected if only one book)")
  .argument("[chapter]", "Chapter number (defaults to latest)")
  .option("--all", "Detect all chapters")
  .option("--stats", "Show detection statistics")
  .option("--json", "Output JSON")
  .action(async (bookIdArg: string | undefined, chapterStr: string | undefined, opts) => {
    try {
      const config = await loadConfig();
      const root = findProjectRoot();

      if (!config.detection?.enabled) {
        logError("AIGC detection is not enabled. Add detection config to inkos.json.");
        process.exit(1);
      }

      // If first arg looks like a number, treat it as chapter
      let bookId: string;
      let chapterNumber: number | undefined;
      if (bookIdArg && /^\d+$/.test(bookIdArg)) {
        bookId = await resolveBookId(undefined, root);
        chapterNumber = parseInt(bookIdArg, 10);
      } else {
        bookId = await resolveBookId(bookIdArg, root);
        chapterNumber = chapterStr ? parseInt(chapterStr, 10) : undefined;
      }

      const state = new StateManager(root);
      const bookDir = state.bookDir(bookId);
      const chapterService = new ChapterApplicationService(new ProjectChapterAuthorityResolver(state, {
        storyRuntime: config.storyRuntime,
        apiToken: config.storyRuntime.apiTokenEnv ? process.env[config.storyRuntime.apiTokenEnv] : undefined,
      }));

      if (opts.stats) {
        const history = await loadDetectionHistory(bookDir);
        const stats = analyzeDetectionInsights(history);
        if (opts.json) {
          log(JSON.stringify(stats, null, 2));
        } else {
          log(`Detection Statistics:`);
          log(`  Total detections: ${stats.totalDetections}`);
          log(`  Total rewrites: ${stats.totalRewrites}`);
          log(`  Avg original score: ${stats.avgOriginalScore.toFixed(3)}`);
          log(`  Avg final score: ${stats.avgFinalScore.toFixed(3)}`);
          log(`  Avg score reduction: ${stats.avgScoreReduction.toFixed(3)}`);
          log(`  Pass rate: ${(stats.passRate * 100).toFixed(0)}%`);
          if (stats.chapterBreakdown.length > 0) {
            log(`  Chapters:`);
            for (const ch of stats.chapterBreakdown) {
              log(`    Ch.${ch.chapterNumber}: ${ch.originalScore.toFixed(3)} → ${ch.finalScore.toFixed(3)} (${ch.rewriteAttempts} rewrites)`);
            }
          }
        }
        return;
      }

      const detectionConfig = config.detection as DetectionConfig;

      if (opts.all) {
        const snapshot = await chapterService.exportSnapshot(bookId);
        for (const chapter of snapshot.chapters) {
          const result = await detectChapter(detectionConfig, chapter.body, chapter.number);
          printResult(result, opts.json);
        }
      } else {
        const chapter = chapterNumber
          ? await chapterService.get(bookId, chapterNumber)
          : await chapterService.latest(bookId);
        if (!chapter) {
          logError("No chapters to detect.");
          process.exit(1);
        }
        const result = await detectChapter(detectionConfig, chapter.body, chapter.number);
        printResult(result, opts.json);
      }
    } catch (e) {
      logError(`Detection failed: ${e}`);
      process.exit(1);
    }
  });

function printResult(
  result: { chapterNumber: number; detection: { score: number; provider: string }; passed: boolean },
  json: boolean,
): void {
  if (json) {
    log(JSON.stringify(result, null, 2));
  } else {
    const icon = result.passed ? "✅" : "⚠️";
    log(`  ${icon} Chapter ${result.chapterNumber}: score=${result.detection.score.toFixed(3)} (${result.detection.provider}) ${result.passed ? "PASS" : "FAIL"}`);
  }
}

