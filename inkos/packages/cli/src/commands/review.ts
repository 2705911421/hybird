import { Command } from "commander";
import { randomUUID } from "node:crypto";
import { ChapterApplicationService, ProjectChapterAuthorityResolver, ReviewArtifactMapper, RuntimeReviewClient, StateManager, formatLengthCount, readGenreProfile, resolveLengthCountingMode } from "@actalk/inkos-core";
import { findProjectRoot, resolveBookId, loadConfig, log, logError } from "../utils.js";

async function runtimeReviewClient(root: string): Promise<RuntimeReviewClient> {
  const config = await loadConfig({ requireApiKey: false, projectRoot: root });
  return new RuntimeReviewClient({
    baseUrl: config.storyRuntime.baseUrl, timeoutMs: config.storyRuntime.timeoutMs,
    apiToken: config.storyRuntime.apiTokenEnv ? process.env[config.storyRuntime.apiTokenEnv] : undefined,
  });
}

async function storeRuntimeDecision(input: { root: string; bookId: string; chapter: number; decision: "approve" | "reject" | "request_changes"; comment: string }) {
  const client = await runtimeReviewClient(input.root);
  const status = await client.reviewStatus(input.bookId, input.chapter);
  return client.storeReviewDecision({
    projectId: input.bookId, idempotencyKey: `cli-review-${randomUUID()}`, expectedRevision: status.revision,
    decision: {
      decision_id: randomUUID(), schema_version: "review-artifacts/v1", project_id: input.bookId,
      chapter_number: input.chapter, reviewer: process.env.USERNAME || process.env.USER || "cli-user",
      decision: input.decision, finding_decisions: {}, comment: input.comment,
      timestamp: new Date().toISOString(), source_revision: status.revision,
    },
  });
}

export const reviewCommand = new Command("review")
  .description("Review and approve chapters");

reviewCommand
  .command("list")
  .description("List chapters pending review")
  .argument("[book-id]", "Book ID (optional, lists all books if omitted)")
  .option("--json", "Output JSON")
  .action(async (bookId: string | undefined, opts) => {
    try {
      const root = findProjectRoot();
      const state = new StateManager(root);
      const config = await loadConfig({ requireApiKey: false, projectRoot: root });
      const chapterService = new ChapterApplicationService(new ProjectChapterAuthorityResolver(state, {
        storyRuntime: config.storyRuntime,
        apiToken: config.storyRuntime.apiTokenEnv ? process.env[config.storyRuntime.apiTokenEnv] : undefined,
      }));

      const bookIds = bookId ? [bookId] : await state.listBooks();
      const allPending: Array<{
        readonly bookId: string;
        readonly title: string;
        readonly chapter: number;
        readonly chapterTitle: string;
        readonly wordCount: number;
        readonly status: string;
        readonly issues: ReadonlyArray<string>;
      }> = [];

      for (const id of bookIds) {
        const book = await state.loadBookConfig(id);
        const chapterPage = await chapterService.list(id, { limit: 100 });
        if (book.authorityMode === "runtime") {
          const client = await runtimeReviewClient(root);
          for (const ch of chapterPage.items) {
            const [artifacts, status] = await Promise.all([client.chapterReviews(id, ch.number), client.reviewStatus(id, ch.number)]);
            if (status.status === "clear") continue;
            const view = ReviewArtifactMapper.toUnifiedViewModel(artifacts, status);
            const issues = view.findings.map((finding) => `[${finding.source}/${finding.severity}${finding.blocking ? "/blocking" : ""}] ${finding.message}`);
            allPending.push({ bookId: id, title: book.title, chapter: ch.number, chapterTitle: ch.title, wordCount: ch.characterCount, status: status.status, issues });
            if (!opts.json) {
              log(`  Ch.${ch.number} "${ch.title}" | ${ch.characterCount} | ${status.status}`);
              for (const issue of issues) log(`    - ${issue}`);
              for (const reason of view.blockingReasons) log(`    blocked: ${reason}`);
            }
          }
          continue;
        }
        const pending = chapterPage.items.filter(
          (ch) =>
            ch.status === "ready-for-review" || ch.status === "audit-failed",
        );

        if (pending.length === 0) continue;

        const { profile: genreProfile } = await readGenreProfile(root, book.genre);
        const countingMode = resolveLengthCountingMode(book.language ?? genreProfile.language);

        if (!opts.json) {
          log(`\n${book.title} (${id}):`);
        }
        for (const ch of pending) {
          allPending.push({
            bookId: id,
            title: book.title,
            chapter: ch.number,
            chapterTitle: ch.title,
            wordCount: ch.characterCount,
            status: ch.status,
            issues: ch.auditIssues,
          });
          if (!opts.json) {
            log(
              `  Ch.${ch.number} "${ch.title}" | ${formatLengthCount(ch.characterCount, countingMode)} | ${ch.status}`,
            );
            if (ch.auditIssues.length > 0) {
              for (const issue of ch.auditIssues) {
                log(`    - ${issue}`);
              }
            }
          }
        }
      }

      if (opts.json) {
        log(JSON.stringify({ pending: allPending }, null, 2));
      } else if (allPending.length === 0) {
        log("No chapters pending review.");
      }
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Failed to list reviews: ${e}`);
      }
      process.exit(1);
    }
  });

/**
 * Parse "[book-id] <chapter>" style arguments from variadic args.
 * Supports: "3" (auto-detect book) or "my-book 3"
 */
function parseBookAndChapter(
  args: ReadonlyArray<string>,
): { readonly bookIdArg: string | undefined; readonly chapterNum: number } {
  if (args.length === 1) {
    const num = parseInt(args[0]!, 10);
    if (isNaN(num)) {
      throw new Error(`Expected chapter number, got "${args[0]}"`);
    }
    return { bookIdArg: undefined, chapterNum: num };
  }
  if (args.length === 2) {
    const num = parseInt(args[1]!, 10);
    if (isNaN(num)) {
      throw new Error(`Expected chapter number as second argument, got "${args[1]}"`);
    }
    return { bookIdArg: args[0], chapterNum: num };
  }
  throw new Error("Usage: inkos review approve [book-id] <chapter>");
}

reviewCommand
  .command("approve")
  .description("Approve a chapter and commit its state: approve [book-id] <chapter>")
  .argument("<args...>", "Book ID (optional) and chapter number")
  .option("--json", "Output JSON")
  .action(async (args: ReadonlyArray<string>, opts) => {
    try {
      const root = findProjectRoot();
      const { bookIdArg, chapterNum } = parseBookAndChapter(args);
      const bookId = await resolveBookId(bookIdArg, root);

      const state = new StateManager(root);
      const book = await state.loadBookConfig(bookId);
      if (book.authorityMode === "runtime") {
        await storeRuntimeDecision({ root, bookId, chapter: chapterNum, decision: "approve", comment: "Approved from InkOS CLI." });
        if (opts.json) log(JSON.stringify({ bookId, chapter: chapterNum, status: "approved", authority: "runtime" }));
        else log(`Chapter ${chapterNum} approved by Story Runtime.`);
        return;
      }
      const index = [...(await state.loadChapterIndex(bookId))];
      const idx = index.findIndex((ch) => ch.number === chapterNum);
      if (idx === -1) {
        throw new Error(`Chapter ${chapterNum} not found in "${bookId}"`);
      }

      index[idx] = {
        ...index[idx]!,
        status: "approved",
        updatedAt: new Date().toISOString(),
      };
      await state.saveChapterIndex(bookId, index);

      if (opts.json) {
        log(JSON.stringify({ bookId, chapter: chapterNum, status: "approved" }));
      } else {
        log(`Chapter ${chapterNum} approved (state committed).`);
      }
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Failed to approve: ${e}`);
      }
      process.exit(1);
    }
  });

reviewCommand
  .command("approve-all")
  .description("Approve all pending chapters for a book")
  .argument("[book-id]", "Book ID (auto-detected if only one book)")
  .option("--json", "Output JSON")
  .action(async (bookIdArg: string | undefined, opts) => {
    try {
      const root = findProjectRoot();
      const bookId = await resolveBookId(bookIdArg, root);
      const state = new StateManager(root);
      const book = await state.loadBookConfig(bookId);
      if (book.authorityMode === "runtime") {
        throw new Error("Bulk approval is disabled for Runtime-authority books; review each chapter and its blocking findings explicitly.");
      }

      const index = [...(await state.loadChapterIndex(bookId))];
      let count = 0;
      const now = new Date().toISOString();

      const updated = index.map((ch) => {
        if (ch.status === "ready-for-review" || ch.status === "audit-failed") {
          count++;
          return { ...ch, status: "approved" as const, updatedAt: now };
        }
        return ch;
      });

      await state.saveChapterIndex(bookId, updated);

      if (opts.json) {
        log(JSON.stringify({ bookId, approvedCount: count }));
      } else {
        log(`${count} chapter(s) approved.`);
      }
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Failed to approve: ${e}`);
      }
      process.exit(1);
    }
  });

reviewCommand
  .command("reject")
  .description("Reject a chapter and roll back state: reject [book-id] <chapter>")
  .argument("<args...>", "Book ID (optional) and chapter number")
  .option("--reason <reason>", "Rejection reason")
  .option("--keep-subsequent", "Only reject this chapter, do not discard subsequent chapters")
  .option("--json", "Output JSON")
  .action(async (args: ReadonlyArray<string>, opts) => {
    try {
      const root = findProjectRoot();
      const { bookIdArg, chapterNum } = parseBookAndChapter(args);
      const bookId = await resolveBookId(bookIdArg, root);

      const state = new StateManager(root);
      const book = await state.loadBookConfig(bookId);
      if (book.authorityMode === "runtime") {
        await storeRuntimeDecision({ root, bookId, chapter: chapterNum, decision: "reject", comment: opts.reason ?? "Rejected from InkOS CLI." });
        if (opts.json) log(JSON.stringify({ bookId, chapter: chapterNum, status: "rejected", authority: "runtime" }));
        else log(`Chapter ${chapterNum} rejected by Story Runtime. No local Truth or chapter rollback was performed.`);
        return;
      }
      const index = await state.loadChapterIndex(bookId);
      const idx = index.findIndex((ch) => ch.number === chapterNum);
      if (idx === -1) {
        throw new Error(`Chapter ${chapterNum} not found in "${bookId}"`);
      }

      if (opts.keepSubsequent) {
        // Legacy behavior: only mark as rejected, no state rollback
        const updated = [...index];
        updated[idx] = {
          ...updated[idx]!,
          status: "rejected",
          reviewNote: opts.reason ?? "Rejected without reason",
          updatedAt: new Date().toISOString(),
        };
        await state.saveChapterIndex(bookId, updated);

        if (opts.json) {
          log(JSON.stringify({ bookId, chapter: chapterNum, status: "rejected", discarded: [] }));
        } else {
          log(`Chapter ${chapterNum} rejected (state not rolled back).`);
        }
        return;
      }

      // Default: roll back state to before the rejected chapter and discard
      // it along with all subsequent chapters that depend on its state.
      const rollbackTarget = chapterNum - 1;
      const discarded = await state.rollbackToChapter(bookId, rollbackTarget);

      if (opts.json) {
        log(JSON.stringify({
          bookId,
          chapter: chapterNum,
          status: "rejected",
          rolledBackTo: rollbackTarget,
          discarded,
        }));
      } else {
        log(`Chapter ${chapterNum} rejected. State rolled back to chapter ${rollbackTarget}.`);
        if (discarded.length > 1) {
          log(`  Also discarded ${discarded.length - 1} subsequent chapter(s): ${discarded.filter((n) => n !== chapterNum).join(", ")}`);
        }
      }
    } catch (e) {
      if (opts.json) {
        log(JSON.stringify({ error: String(e) }));
      } else {
        logError(`Failed to reject: ${e}`);
      }
      process.exit(1);
    }
  });
