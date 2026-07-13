import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { EPub } from "epub-gen-memory";
import type { ChapterExportPort, ChapterExportSnapshot } from "../chapter-application-service.js";

export interface ExportStateLike {
  readonly bookDir: (bookId: string) => string;
  readonly loadBookConfig: (bookId: string) => Promise<{ readonly title: string; readonly language?: string }>;
}

export interface ExportManifest {
  readonly authority: "runtime" | "legacy";
  readonly projectRevision: number;
  readonly snapshotId: string;
  readonly collectionChecksum: string;
  readonly chapterCount: number;
  readonly generatedAt: string;
  readonly chapters: ReadonlyArray<{ readonly number: number; readonly bodyChecksum: string }>;
}

export interface ExportArtifact {
  readonly outputPath: string;
  readonly fileName: string;
  readonly chaptersExported: number;
  readonly totalWords: number;
  readonly format: "txt" | "md" | "epub";
  readonly contentType: string;
  readonly payload: string | Buffer;
  readonly manifest: ExportManifest;
  readonly manifestPath: string;
}

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function markdownToSimpleHtml(markdown: string): { title: string; html: string } {
  const title = markdown.match(/^#\s+(.+)/m)?.[1]?.trim() ?? "Untitled Chapter";
  const html = markdown
    .split("\n")
    .filter((line) => !line.startsWith("#"))
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => `<p>${escapeHtml(line)}</p>`)
    .join("\n");
  return { title, html };
}

export async function buildExportArtifact(
  state: ExportStateLike,
  bookId: string,
  options: {
    readonly chapterService: ChapterExportPort;
    readonly format?: "txt" | "md" | "epub";
    readonly approvedOnly?: boolean;
    readonly outputPath?: string;
  },
): Promise<ExportArtifact> {
  const format = options.format ?? "txt";
  const book = await state.loadBookConfig(bookId);
  const snapshot: ChapterExportSnapshot = await options.chapterService.exportSnapshot(bookId, {
    approvedOnly: options.approvedOnly,
  });
  const chapters = snapshot.chapters;

  if (chapters.length === 0) {
    throw new Error("No chapters to export.");
  }

  const bookDir = state.bookDir(bookId);
  const projectRoot = dirname(dirname(bookDir));
  const outputPath = options.outputPath ?? join(projectRoot, `${bookId}_export.${format}`);
  const manifestPath = `${outputPath}.manifest.json`;
  const totalWords = chapters.reduce((sum, chapter) => sum + chapter.characterCount, 0);
  const manifest: ExportManifest = {
    authority: snapshot.authority,
    projectRevision: snapshot.projectRevision,
    snapshotId: snapshot.snapshotId,
    collectionChecksum: snapshot.collectionChecksum,
    chapterCount: chapters.length,
    generatedAt: snapshot.createdAt,
    chapters: chapters.map((chapter) => ({ number: chapter.number, bodyChecksum: chapter.bodyChecksum })),
  };

  if (format === "epub") {
    const epubChapters: Array<{ title: string; content: string }> = [];
    for (const chapter of chapters) {
      const { title, html } = markdownToSimpleHtml(chapter.body);
      epubChapters.push({ title: title === "Untitled Chapter" ? chapter.title : title, content: html });
    }
    const epubInstance = new EPub(
      { title: book.title, lang: book.language === "en" ? "en" : "zh-CN" },
      epubChapters,
    );
    return {
      outputPath,
      fileName: `${bookId}.epub`,
      chaptersExported: chapters.length,
      totalWords,
      format,
      contentType: "application/epub+zip",
      payload: await epubInstance.genEpub(),
      manifest,
      manifestPath,
    };
  }

  const parts: string[] = [];
  parts.push(format === "md" ? `# ${book.title}\n\n---\n` : `${book.title}\n\n`);
  for (const chapter of chapters) {
    parts.push(chapter.body);
    parts.push("\n\n");
  }

  return {
    outputPath,
    fileName: `${bookId}.${format}`,
    chaptersExported: chapters.length,
    totalWords,
    format,
    contentType: format === "md" ? "text/markdown; charset=utf-8" : "text/plain; charset=utf-8",
    payload: parts.join(format === "md" ? "\n---\n\n" : "\n"),
    manifest,
    manifestPath,
  };
}

export async function writeExportArtifact(
  state: ExportStateLike,
  bookId: string,
  options: {
    readonly chapterService: ChapterExportPort;
    readonly format?: "txt" | "md" | "epub";
    readonly approvedOnly?: boolean;
    readonly outputPath?: string;
  },
): Promise<{
  readonly outputPath: string;
  readonly chaptersExported: number;
  readonly totalWords: number;
  readonly format: "txt" | "md" | "epub";
  readonly manifestPath: string;
  readonly projectRevision: number;
}> {
  const artifact = await buildExportArtifact(state, bookId, options);
  await mkdir(dirname(artifact.outputPath), { recursive: true });
  await writeFile(artifact.outputPath, artifact.payload);
  await writeFile(artifact.manifestPath, JSON.stringify(artifact.manifest, null, 2), "utf8");
  return {
    outputPath: artifact.outputPath,
    chaptersExported: artifact.chaptersExported,
    totalWords: artifact.totalWords,
    format: artifact.format,
    manifestPath: artifact.manifestPath,
    projectRevision: artifact.manifest.projectRevision,
  };
}
