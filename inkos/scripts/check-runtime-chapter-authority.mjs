import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const failures = [];

async function source(path) {
  return readFile(resolve(root, path), "utf8");
}

async function forbid(path, patterns) {
  const text = await source(path);
  for (const pattern of patterns) {
    if (pattern.test(text)) failures.push(`${path}: forbidden ${pattern}`);
  }
}

async function requirePattern(path, patterns) {
  const text = await source(path);
  for (const pattern of patterns) {
    if (!pattern.test(text)) failures.push(`${path}: missing ${pattern}`);
  }
}

const productReaders = [
  "packages/core/src/pipeline/runner.ts",
  "packages/core/src/pipeline/scheduler.ts",
  "packages/core/src/utils/book-eval.ts",
  "packages/core/src/interaction/export-artifact.ts",
  "packages/studio/src/api/server.ts",
  "packages/cli/src/commands/analytics.ts",
  "packages/cli/src/commands/status.ts",
  "packages/cli/src/commands/detect.ts",
  "packages/cli/src/commands/book.ts",
  "packages/cli/src/commands/chapter.ts",
];

for (const path of productReaders) {
  await forbid(path, [/loadChapterIndex\s*\(/, /readdir\s*\(\s*chaptersDir/, /readFile\s*\(\s*join\(chaptersDir/]);
}

await forbid("packages/core/src/interaction/export-artifact.ts", [/readFile\s*\(/, /readdir\s*\(/]);
await requirePattern("packages/core/src/interaction/export-artifact.ts", [/chapterService\.exportSnapshot\s*\(/, /collectionChecksum/, /manifestPath/]);
await forbid("packages/studio/src/api/server.ts", [/LegacyChapterReadAdapter/, /\.finalizedChapter\s*\(/]);
await requirePattern("packages/studio/src/api/server.ts", [/createChapterService\s*\(/, /chapterService,\s*\n\s*format:/]);
await requirePattern("packages/core/src/chapter-application-service.ts", [
  /class ChapterApplicationService/,
  /class StoryRuntimeChapterReadAdapter/,
  /class LegacyChapterReadAdapter/,
  /if \(book\.authorityMode === "runtime"\)/,
]);
await requirePattern("packages/cli/src/commands/write.ts", [/RUNTIME_REVISION_REQUIRED/]);
await requirePattern("packages/core/src/interaction/edit-controller.ts", [/book\?\.authorityMode === "runtime"/, /RUNTIME_TYPED_COMMAND_REQUIRED/]);

if (failures.length) {
  process.stderr.write(`Runtime chapter authority gate failed:\n${failures.map((failure) => `- ${failure}`).join("\n")}\n`);
  process.exit(1);
}

process.stdout.write("Runtime chapter authority gate passed.\n");
