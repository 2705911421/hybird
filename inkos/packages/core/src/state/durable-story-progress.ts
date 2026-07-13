import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

export async function resolveDurableStoryProgress(params: {
  readonly bookDir: string;
  readonly fallbackChapter?: number;
}): Promise<number> {
  const explicitFallback = normalizeExplicitChapter(params.fallbackChapter);
  const chapterNumbers = await loadDurableArtifactChapterNumbers(params.bookDir);
  return Math.max(resolveContiguousChapterPrefix(chapterNumbers), explicitFallback);
}

async function loadDurableArtifactChapterNumbers(bookDir: string): Promise<number[]> {
  const chaptersDir = join(bookDir, "chapters");
  const [indexChapters, fileChapters] = await Promise.all([
    readFile(join(chaptersDir, "index.json"), "utf-8")
      .then((raw) => {
        const parsed = JSON.parse(raw) as Array<{ number?: unknown }>;
        return parsed
          .map((entry) => entry?.number)
          .filter((entry): entry is number => typeof entry === "number" && Number.isInteger(entry) && entry > 0);
      })
      .catch(() => [] as number[]),
    readdir(chaptersDir)
      .then((entries) => entries.flatMap((entry) => {
        const match = entry.match(/^(\d+)_/);
        return match ? [Number.parseInt(match[1]!, 10)] : [];
      }))
      .catch(() => [] as number[]),
  ]);
  return [...indexChapters, ...fileChapters];
}

function resolveContiguousChapterPrefix(chapterNumbers: ReadonlyArray<number>): number {
  const chapters = new Set(chapterNumbers.filter((chapter) => Number.isInteger(chapter) && chapter > 0));
  let contiguousChapter = 0;
  while (chapters.has(contiguousChapter + 1)) contiguousChapter += 1;
  return contiguousChapter;
}

function normalizeExplicitChapter(value: number | undefined): number {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : 0;
}
