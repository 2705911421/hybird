import { AsyncLocalStorage } from "node:async_hooks";
import type { LLMClient, OnStreamProgress } from "../llm/provider.js";
import { chatCompletion, createLLMClient } from "../llm/provider.js";
import type { Logger } from "../utils/logger.js";
import type { BookConfig, FanficMode, RevisionGate } from "../models/book.js";
import type { ChapterMeta } from "../models/chapter.js";
import type { NotifyChannel, LLMConfig, AgentLLMOverride, InputGovernanceMode } from "../models/project.js";
import type { GenreProfile } from "../models/genre-profile.js";
import { ArchitectAgent, type ArchitectOutput } from "../agents/architect.js";
import { FoundationReviewerAgent } from "../agents/foundation-reviewer.js";
import { PlannerAgent, type PlanChapterOutput } from "../agents/planner.js";
import { ComposerAgent, composeGovernedChapter, contextBudgetFromClient, type ComposeChapterOutput } from "../agents/composer.js";
import { WriterAgent, type WriteChapterInput, type WriteChapterOutput } from "../agents/writer.js";
import { LengthNormalizerAgent } from "../agents/length-normalizer.js";
import { ChapterAnalyzerAgent } from "../agents/chapter-analyzer.js";
import { ContinuityAuditor } from "../agents/continuity.js";
import { ReviserAgent, DEFAULT_REVISE_MODE, type ReviseMode } from "../agents/reviser.js";
import { RadarAgent } from "../agents/radar.js";
import type { RadarSource } from "../agents/radar-source.js";
import { readGenreProfile } from "../agents/rules-reader.js";
import { analyzeAITells } from "../agents/ai-tells.js";
import { analyzeSensitiveWords } from "../agents/sensitive-words.js";
import { StateManager } from "../state/manager.js";
import { dispatchNotification, dispatchWebhookEvent } from "../notify/dispatcher.js";
import type { WebhookEvent } from "../notify/webhook.js";
import type { AgentContext } from "../agents/base.js";
import type { AuditResult, AuditIssue } from "../agents/continuity.js";
import type { RadarResult } from "../agents/radar.js";
import type { LengthSpec, LengthTelemetry } from "../models/length-governance.js";
import type { ChapterMemo, ContextPackage, RuleStack } from "../models/input-governance.js";
import type { ContextCompressionCallback } from "../models/context-compression.js";
import type { StoryRuntimeConfig } from "../story-runtime/schemas.js";
import { StoryRuntimeClient } from "../story-runtime/client.js";
import { ChapterApplicationService, ProjectChapterAuthorityResolver } from "../chapter-application-service.js";
import { ProjectWriterNarrativeContextResolver } from "../writer-narrative-context.js";
import { buildLengthSpec, countChapterLength, formatLengthCount, isOutsideHardRange, resolveLengthCountingMode, type LengthLanguage } from "../utils/length-metrics.js";
import { analyzeLongSpanFatigue } from "../utils/long-span-fatigue.js";
import { buildWritingMethodologySection } from "../utils/writing-methodology.js";
import {
  isNewLayoutBook,
  readCharacterContext,
  readVolumeMap,
} from "../utils/outline-paths.js";
import { readFile, readdir, writeFile, mkdir, rename, rm, stat } from "node:fs/promises";
import { join } from "node:path";
import {
  parseStateDegradedReviewNote,
  resolveStateDegradedBaseStatus,
  retrySettlementAfterValidationFailure,
} from "./chapter-state-recovery.js";
import { StoryRuntimeChapterPersistence } from "./chapter-persistence-port.js";
import { InkOSReviewAdapter, InkOSRevisionAdapter } from "../review-artifacts/adapters.js";
import { runChapterReviewCycle } from "./chapter-review-cycle.js";
import { loadPersistedPlan, relativeToBookDir, savePersistedPlan } from "./persisted-governed-plan.js";

const SEQUENCE_LEVEL_CATEGORIES = new Set([
  "Pacing Monotony", "节奏单调",
  "Mood Monotony", "情绪单调",
  "Title Collapse", "标题重复",
  "Title Clustering", "标题聚集",
  "Opening Pattern Repetition", "开头同构",
  "Ending Pattern Repetition", "结尾同构",
]);

function isSequenceLevelCategory(category: string): boolean {
  return SEQUENCE_LEVEL_CATEGORIES.has(category);
}

/** Human-readable description of each manual-revision gate, surfaced in revisionDiagnostics. */
const REVISION_GATE_STANDARDS: Record<RevisionGate, string> = {
  strict: "A revision is applied only when blocking, critical, and AI-tell counts do not worsen, and at least blocking or AI-tell issues improve.",
  lenient: "A revision is applied whenever blocking, critical, and AI-tell counts do not worsen; no improvement is required (lenient gate).",
  always: "Manual revisions are always applied; audit counts are recorded for reference only (always gate).",
};

export interface PipelineConfig {
  readonly client: LLMClient;
  readonly model: string;
  readonly projectRoot: string;
  readonly defaultLLMConfig?: LLMConfig;
  readonly foundationReviewRetries?: number;
  readonly writingReviewRetries?: number;
  /**
   * "auto" (default): writeNextChapter runs the audit→revise loop inline.
   * "manual": stop right after the draft (no auto audit/revise) so review/revise
   * become explicit, user-driven checkpoint actions — chapter write stays fast.
   */
  readonly chapterReviewMode?: "auto" | "manual";
  /**
   * Gate for applying manual revisions (default "strict"):
   * - "strict": apply only when blocking/critical/AI-tell counts do not worsen
   *   AND at least one of blocking or AI-tell improves.
   * - "lenient": apply whenever the counts do not worsen (no improvement required).
   * - "always": always apply; audit counts are recorded but never block.
   */
  readonly revisionGate?: RevisionGate;
  readonly notifyChannels?: ReadonlyArray<NotifyChannel>;
  readonly radarSources?: ReadonlyArray<RadarSource>;
  readonly externalContext?: string;
  readonly modelOverrides?: Record<string, string | AgentLLMOverride>;
  readonly inputGovernanceMode?: InputGovernanceMode;
  readonly logger?: Logger;
  readonly onStreamProgress?: OnStreamProgress;
  readonly onContextCompression?: ContextCompressionCallback;
  readonly storyRuntime?: StoryRuntimeConfig;
  readonly unifiedReviewEnabled?: boolean;
  readonly writerFactory?: (context: AgentContext) => Pick<WriterAgent, "writeChapter">;
}

export interface TokenUsageSummary {
  readonly promptTokens: number;
  readonly completionTokens: number;
  readonly totalTokens: number;
}

export interface ChapterPipelineResult {
  readonly chapterNumber: number;
  readonly title: string;
  readonly wordCount: number;
  readonly auditResult: AuditResult;
  readonly revised: boolean;
  readonly status: "ready-for-review" | "audit-failed" | "state-degraded";
  readonly lengthWarnings?: ReadonlyArray<string>;
  readonly lengthTelemetry?: LengthTelemetry;
  readonly tokenUsage?: TokenUsageSummary;
}

// Atomic operation results
export interface DraftResult {
  readonly chapterNumber: number;
  readonly title: string;
  readonly wordCount: number;
  readonly filePath: string;
  readonly lengthWarnings?: ReadonlyArray<string>;
  readonly lengthTelemetry?: LengthTelemetry;
  readonly tokenUsage?: TokenUsageSummary;
}

export interface PlanChapterResult {
  readonly bookId: string;
  readonly chapterNumber: number;
  readonly intentPath: string;
  readonly goal: string;
  readonly conflicts: ReadonlyArray<string>;
}

export interface ComposeChapterResult extends PlanChapterResult {
  readonly contextPath: string;
  readonly ruleStackPath: string;
  readonly tracePath: string;
}

export interface ReviseResult {
  readonly chapterNumber: number;
  readonly wordCount: number;
  readonly fixedIssues: ReadonlyArray<string>;
  readonly applied: boolean;
  readonly status: "unchanged" | "ready-for-review" | "audit-failed";
  readonly skippedReason?: string;
  readonly revisionDiagnostics?: {
    readonly standard: string;
    readonly before: {
      readonly blockingCount: number;
      readonly criticalCount: number;
      readonly aiTellCount: number;
    };
    readonly after: {
      readonly blockingCount: number;
      readonly criticalCount: number;
      readonly aiTellCount: number;
    };
    readonly remainingIssues: ReadonlyArray<{
      readonly severity: AuditIssue["severity"];
      readonly category: string;
      readonly description: string;
      readonly suggestion?: string;
    }>;
  };
  readonly lengthWarnings?: ReadonlyArray<string>;
  readonly lengthTelemetry?: LengthTelemetry;
}

export interface TruthFiles {
  readonly currentState: string;
  readonly particleLedger: string;
  readonly pendingHooks: string;
  readonly storyBible: string;
  readonly volumeOutline: string;
  readonly bookRules: string;
}

export interface BookStatusInfo {
  readonly bookId: string;
  readonly title: string;
  readonly genre: string;
  readonly platform: string;
  readonly status: string;
  readonly chaptersWritten: number;
  readonly totalWords: number;
  readonly nextChapter: number;
  readonly chapters: ReadonlyArray<ChapterMeta>;
}

interface MergedAuditEvaluation {
  readonly auditResult: AuditResult;
  readonly aiTellCount: number;
  readonly blockingCount: number;
  readonly criticalCount: number;
  readonly revisionBlockingIssues: ReadonlyArray<AuditIssue>;
}

export interface ImportChaptersInput {
  readonly bookId: string;
  readonly chapters: ReadonlyArray<{ readonly title: string; readonly content: string }>;
  readonly resumeFrom?: number;
  /** "continuation" (default) = pick up where the text left off, no new spacetime.
   *  "series" = shared universe but independent new story, requires new spacetime. */
  readonly importMode?: "continuation" | "series";
}

export interface ImportChaptersResult {
  readonly bookId: string;
  readonly importedCount: number;
  readonly totalWords: number;
  readonly nextChapter: number;
}

export interface InitBookOptions {
  readonly externalContext?: string;
  readonly authorIntent?: string;
  readonly currentFocus?: string;
}

export class PipelineRunner {
  private readonly state: StateManager;
  private readonly config: PipelineConfig;
  private readonly chapters: ChapterApplicationService;
  private readonly writerNarrative: ProjectWriterNarrativeContextResolver;
  private readonly agentClients = new Map<string, LLMClient>();
  private readonly operationContext = new AsyncLocalStorage<{ readonly signal?: AbortSignal }>();

  constructor(config: PipelineConfig) {
    this.config = config;
    this.state = new StateManager(config.projectRoot);
    this.chapters = new ChapterApplicationService(new ProjectChapterAuthorityResolver(this.state, {
      storyRuntime: config.storyRuntime,
      apiToken: config.storyRuntime?.apiTokenEnv ? process.env[config.storyRuntime.apiTokenEnv] : undefined,
    }));
    this.writerNarrative = new ProjectWriterNarrativeContextResolver(this.state, this.chapters);
  }

  async runWithAbortSignal<T>(
    signal: AbortSignal | undefined,
    task: () => Promise<T>,
  ): Promise<T> {
    signal?.throwIfAborted();
    return this.operationContext.run({ signal }, async () => {
      signal?.throwIfAborted();
      return task();
    });
  }

  private currentAbortSignal(): AbortSignal | undefined {
    return this.operationContext.getStore()?.signal;
  }

  private throwIfOperationAborted(): void {
    this.currentAbortSignal()?.throwIfAborted();
  }

  private localize(language: LengthLanguage, messages: { zh: string; en: string }): string {
    return language === "en" ? messages.en : messages.zh;
  }

  private async resolveBookLanguage(
    book: Pick<BookConfig, "genre" | "language">,
  ): Promise<LengthLanguage> {
    if (book.language) {
      return book.language;
    }

    try {
      const { profile } = await this.loadGenreProfile(book.genre);
      return profile.language;
    } catch {
      return "zh";
    }
  }

  private async resolveBookLanguageById(bookId: string): Promise<LengthLanguage> {
    try {
      const book = await this.state.loadBookConfig(bookId);
      return await this.resolveBookLanguage(book);
    } catch {
      return "zh";
    }
  }

  private languageFromLengthSpec(lengthSpec: Pick<LengthSpec, "countingMode">): LengthLanguage {
    return lengthSpec.countingMode === "en_words" ? "en" : "zh";
  }

  private logStage(language: LengthLanguage, message: { zh: string; en: string }): void {
    this.config.logger?.info(
      `${this.localize(language, { zh: "阶段：", en: "Stage: " })}${this.localize(language, message)}`,
    );
  }

  private logInfo(language: LengthLanguage, message: { zh: string; en: string }): void {
    this.config.logger?.info(this.localize(language, message));
  }

  private logWarn(language: LengthLanguage, message: { zh: string; en: string }): void {
    this.config.logger?.warn(this.localize(language, message));
  }

  private async tryGenerateStyleGuide(
    bookId: string,
    referenceText: string,
    sourceName: string | undefined,
    language?: LengthLanguage,
  ): Promise<void> {
    try {
      await this.generateStyleGuide(bookId, referenceText, sourceName);
    } catch (error) {
      const resolvedLanguage = language ?? await this.resolveBookLanguageById(bookId);
      const detail = error instanceof Error ? error.message : String(error);
      this.logWarn(resolvedLanguage, {
        zh: `风格指纹提取失败，已跳过：${detail}`,
        en: `Style fingerprint extraction failed and was skipped: ${detail}`,
      });
    }
  }

  private async generateAndReviewFoundation(params: {
    readonly generate: (reviewFeedback?: string) => Promise<ArchitectOutput>;
    readonly reviewer: FoundationReviewerAgent;
    readonly mode: "original" | "fanfic" | "series";
    readonly sourceCanon?: string;
    readonly styleGuide?: string;
    readonly language: "zh" | "en";
    readonly stageLanguage: LengthLanguage;
    readonly targetChapters?: number;
    readonly maxRetries?: number;
  }): Promise<ArchitectOutput> {
    const maxRetries = params.maxRetries ?? this.config.foundationReviewRetries ?? 2;
    let foundation = await params.generate();

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      this.logStage(params.stageLanguage, {
        zh: `审核基础设定（第${attempt + 1}轮）`,
        en: `reviewing foundation (round ${attempt + 1})`,
      });

      const review = await params.reviewer.review({
        foundation,
        mode: params.mode,
        sourceCanon: params.sourceCanon,
        styleGuide: params.styleGuide,
        language: params.language,
        targetChapters: params.targetChapters,
      });

      this.config.logger?.info(
        `Foundation review: ${review.totalScore}/100 ${review.passed ? "PASSED" : "REJECTED"}`,
      );
      for (const dim of review.dimensions) {
        this.config.logger?.info(`  [${dim.score}] ${dim.name.slice(0, 40)}`);
      }

      if (review.passed) {
        return foundation;
      }

      this.logWarn(params.stageLanguage, {
        zh: `基础设定未通过审核（${review.totalScore}分），正在重新生成...`,
        en: `Foundation rejected (${review.totalScore}/100), regenerating...`,
      });

      foundation = await params.generate(this.buildFoundationReviewFeedback(review, params.language));
    }

    // Final review
    const finalReview = await params.reviewer.review({
      foundation,
      mode: params.mode,
      sourceCanon: params.sourceCanon,
      styleGuide: params.styleGuide,
      language: params.language,
      targetChapters: params.targetChapters,
    });
    this.config.logger?.info(
      `Foundation final review: ${finalReview.totalScore}/100 ${finalReview.passed ? "PASSED" : "ACCEPTED (max retries)"}`,
    );

    return foundation;
  }

  private buildFoundationReviewFeedback(
    review: {
      readonly dimensions: ReadonlyArray<{
        readonly name: string;
        readonly score: number;
        readonly feedback: string;
      }>;
      readonly overallFeedback: string;
    },
    language: "zh" | "en",
  ): string {
    const dimensionLines = review.dimensions
      .map((dimension) => (
        language === "en"
          ? `- ${dimension.name} [${dimension.score}]: ${dimension.feedback}`
          : `- ${dimension.name}（${dimension.score}分）：${dimension.feedback}`
      ))
      .join("\n");

    return language === "en"
      ? [
          "## Overall Feedback",
          review.overallFeedback,
          "",
          "## Dimension Notes",
          dimensionLines || "- none",
        ].join("\n")
      : [
          "## 总评",
          review.overallFeedback,
          "",
          "## 分项问题",
          dimensionLines || "- 无",
        ].join("\n");
  }

  private agentCtx(bookId?: string): AgentContext {
    return {
      client: this.config.client,
      model: this.config.model,
      projectRoot: this.config.projectRoot,
      bookId,
      logger: this.config.logger,
      onStreamProgress: this.config.onStreamProgress,
    };
  }

  private resolveOverride(agentName: string): { model: string; client: LLMClient } {
    const override = this.config.modelOverrides?.[agentName];
    if (!override) {
      return { model: this.config.model, client: this.config.client };
    }
    if (typeof override === "string") {
      return { model: override, client: this.config.client };
    }
    // Full override — needs its own client if baseUrl differs
    if (!override.baseUrl) {
      return { model: override.model, client: this.config.client };
    }
    const base = this.config.defaultLLMConfig;
    const provider = override.provider ?? base?.provider ?? "custom";
    const apiKeySource = override.apiKeyEnv
      ? `env:${override.apiKeyEnv}`
      : `base:${base?.apiKey ?? ""}`;
    const stream = override.stream ?? base?.stream ?? true;
    const apiFormat = base?.apiFormat ?? "chat";
    const cacheKey = [
      provider,
      override.baseUrl,
      apiKeySource,
      `stream:${stream}`,
      `format:${apiFormat}`,
    ].join("|");
    let client = this.agentClients.get(cacheKey);
    if (!client) {
      const apiKey = override.apiKeyEnv
        ? process.env[override.apiKeyEnv] ?? ""
        : base?.apiKey ?? "";
      client = createLLMClient({
        provider,
        service: base?.service ?? "custom",
        configSource: base?.configSource ?? "env",
        baseUrl: override.baseUrl,
        apiKey,
        model: override.model,
        temperature: base?.temperature ?? 0.7,
        thinkingBudget: base?.thinkingBudget ?? 0,
        apiFormat,
        stream,
      });
      this.agentClients.set(cacheKey, client);
    }
    return { model: override.model, client };
  }

  private agentCtxFor(agent: string, bookId?: string): AgentContext {
    const { model, client } = this.resolveOverride(agent);
    return {
      client,
      model,
      projectRoot: this.config.projectRoot,
      bookId,
      logger: this.config.logger?.child(agent),
      onStreamProgress: this.config.onStreamProgress,
      signal: this.currentAbortSignal(),
    };
  }

  public createAgentContext(agent: string, bookId?: string): AgentContext {
    return this.agentCtxFor(agent, bookId);
  }

  private async pathExists(path: string): Promise<boolean> {
    try {
      await stat(path);
      return true;
    } catch {
      return false;
    }
  }

  private async loadGenreProfile(genre: string): Promise<{ profile: GenreProfile }> {
    const parsed = await readGenreProfile(this.config.projectRoot, genre);
    return { profile: parsed.profile };
  }

  // ---------------------------------------------------------------------------
  // Atomic operations (composable by OpenClaw or agent mode)
  // ---------------------------------------------------------------------------

  async runRadar(): Promise<RadarResult> {
    const radar = new RadarAgent(this.agentCtxFor("radar"), this.config.radarSources);
    return radar.scan();
  }

  async initBook(book: BookConfig, options: InitBookOptions = {}): Promise<void> {
    if (book.authorityMode !== "runtime" || this.config.storyRuntime?.mode !== "story-runtime") {
      throw new Error("LEGACY_LONG_FORM_READ_ONLY: Phase 8 creates long-form books only with Story Runtime authority.");
    }
    const architect = new ArchitectAgent(this.agentCtxFor("architect", book.id));
    const bookDir = this.state.bookDir(book.id);
    const stagingBookDir = join(
      this.state.booksDir,
      `.tmp-book-create-${book.id}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    );
    const stageLanguage = await this.resolveBookLanguage(book);
    const effectiveExternalContext = options.externalContext ?? this.config.externalContext;

    this.logStage(stageLanguage, { zh: "生成基础设定", en: "generating foundation" });
    const { profile: gp } = await this.loadGenreProfile(book.genre);
    const reviewer = new FoundationReviewerAgent(this.agentCtxFor("foundation-reviewer", book.id));
    const resolvedLanguage = (book.language ?? gp.language) === "en" ? "en" as const : "zh" as const;
    const foundation = await this.generateAndReviewFoundation({
      generate: (reviewFeedback) => architect.generateFoundation(
        book,
        effectiveExternalContext,
        reviewFeedback,
      ),
      reviewer,
      mode: "original",
      language: resolvedLanguage,
      stageLanguage,
      targetChapters: book.targetChapters,
    });
    try {
      this.logStage(stageLanguage, { zh: "保存书籍配置", en: "saving book config" });
      await this.state.saveBookConfigAt(stagingBookDir, book);

      this.logStage(stageLanguage, { zh: "写入基础设定文件", en: "writing foundation files" });
      await architect.writeFoundationFiles(
        stagingBookDir,
        foundation,
        gp.numericalSystem,
        book.language ?? gp.language,
      );

      if (effectiveExternalContext && effectiveExternalContext.trim().length > 0) {
        const storyDir = join(stagingBookDir, "story");
        await mkdir(storyDir, { recursive: true });
        await writeFile(join(storyDir, "brief.md"), effectiveExternalContext, "utf-8");
      }

      this.logStage(stageLanguage, { zh: "初始化控制文档", en: "initializing control documents" });
      await this.state.ensureControlDocumentsAt(
        stagingBookDir,
        book.language ?? gp.language,
        options.authorIntent ?? effectiveExternalContext,
      );
      if (options.currentFocus?.trim()) {
        await writeFile(
          join(stagingBookDir, "story", "current_focus.md"),
          options.currentFocus.trimEnd() + "\n",
          "utf-8",
        );
      }

      await this.state.saveChapterIndexAt(stagingBookDir, []);

      this.logStage(stageLanguage, { zh: "创建初始快照", en: "creating initial snapshot" });
      await this.state.snapshotStateAt(stagingBookDir, 0);

      if (await this.pathExists(bookDir)) {
        if (await this.state.isCompleteBookDirectory(bookDir)) {
          throw new Error(`Book "${book.id}" already exists at books/${book.id}/. Use a different title or delete the existing book first.`);
        }
        await rm(bookDir, { recursive: true, force: true });
      }

      const runtime = this.config.storyRuntime!;
      await new StoryRuntimeClient({
        baseUrl: runtime.baseUrl,
        timeoutMs: runtime.timeoutMs,
        apiToken: runtime.apiTokenEnv ? process.env[runtime.apiTokenEnv] : undefined,
      }).createProject({ projectId: book.id, idempotencyKey: `init:${book.id}:runtime-authority` });

      await rename(stagingBookDir, bookDir);
    } catch (error) {
      await rm(stagingBookDir, { recursive: true, force: true }).catch(() => undefined);
      throw error;
    }
  }

  async reviseFoundation(bookId: string, feedback: string): Promise<void> {
    void bookId;
    void feedback;
    throw new Error(
      "Legacy foundation rewrite was removed in Phase 8; submit a typed diff command to Story Runtime.",
    );
  }

  async importFanficCanon(
    bookId: string,
    sourceText: string,
    sourceName: string,
    fanficMode: FanficMode,
  ): Promise<string> {
    const { FanficCanonImporter } = await import("../agents/fanfic-canon-importer.js");
    const importer = new FanficCanonImporter(this.agentCtxFor("fanfic-canon-importer", bookId));
    const result = await importer.importFromText(sourceText, sourceName, fanficMode);

    const bookDir = this.state.bookDir(bookId);
    const storyDir = join(bookDir, "story");
    await mkdir(storyDir, { recursive: true });
    await writeFile(join(storyDir, "fanfic_canon.md"), result.fullDocument, "utf-8");

    return result.fullDocument;
  }

  /** One-step fanfic book creation: create book + import canon + generate foundation */
  async initFanficBook(
    book: BookConfig,
    sourceText: string,
    sourceName: string,
    fanficMode: FanficMode,
  ): Promise<void> {
    const { FanficCanonImporter } = await import("../agents/fanfic-canon-importer.js");
    const importer = new FanficCanonImporter(this.agentCtxFor("fanfic-canon-importer", book.id));
    const imported = await importer.importFromText(sourceText, sourceName, fanficMode);
    await this.initBook(book, {
      externalContext: `${this.config.externalContext ?? ""}\n\n${imported.fullDocument}`.trim(),
    });
    const bookDir = this.state.bookDir(book.id);
    await writeFile(join(bookDir, "story", "fanfic_canon.md"), imported.fullDocument, "utf-8");

    if (sourceText.length >= 500) {
      const stageLanguage = await this.resolveBookLanguage(book);
      this.logStage(stageLanguage, { zh: "提取原作风格指纹", en: "extracting source style fingerprint" });
      await this.tryGenerateStyleGuide(book.id, sourceText, sourceName, stageLanguage);
    }
  }

  /**
   * Create a side-story (番外) book: a standalone companion that inherits a
   * parent book's world/characters via parent_canon.md, but tells an INDEPENDENT
   * side plot that does not advance or contradict the parent's main-line state.
   * Reuses importCanon (which already builds the parent-canon reference for
   * side-story writing) + the standard original-foundation architect path.
   */
  async initSpinoffBook(book: BookConfig, parentBookId: string, direction?: string): Promise<void> {
    await this.initBook(book, { externalContext: direction?.trim() || this.config.externalContext });
    await this.importCanon(book.id, parentBookId);
  }

  /**
   * Create an imitation (仿写) book: an ORIGINAL story whose prose imitates the
   * voice of a reference work. The architect builds an original foundation from
   * the user's story idea; the reference text becomes the book's style_guide.md
   * so the writer mimics its style. The style guide is mandatory here (imitation
   * is the whole point), so a failure to generate it surfaces rather than being
   * silently skipped.
   */
  async initImitationBook(
    book: BookConfig,
    referenceText: string,
    storyIdea: string,
    sourceName?: string,
  ): Promise<void> {
    await this.initBook(book, { externalContext: storyIdea });
    const stageLanguage = await this.resolveBookLanguage(book);
    this.logStage(stageLanguage, { zh: "提取参考作品风格指纹", en: "extracting reference style fingerprint" });
    await this.generateStyleGuide(book.id, referenceText, sourceName?.trim() || "reference");
  }

  /** Write a single draft chapter. Saves chapter file + truth files + index + snapshot. */
  async writeDraft(bookId: string, context?: string, wordCount?: number): Promise<DraftResult> {
    void bookId; void context; void wordCount;
    throw new Error("LEGACY_LONG_FORM_READ_ONLY: drafts must be generated as proposals and committed through Story Runtime.");
  }

  async planChapter(bookId: string, context?: string): Promise<PlanChapterResult> {
    const book = await this.state.loadBookConfig(bookId);
    if (book.authorityMode !== "runtime") {
      throw new Error("LEGACY_LONG_FORM_READ_ONLY: migrate this book before planning another chapter.");
    }
    const bookDir = this.state.bookDir(bookId);
    const chapterNumber = (await this.chapters.summary(bookId)).latestChapter + 1;
    const stageLanguage = await this.resolveBookLanguage(book);
    this.logStage(stageLanguage, { zh: "规划下一章意图", en: "planning next chapter intent" });
    const { plan } = await this.createGovernedArtifacts(
      book,
      bookDir,
      chapterNumber,
      context ?? this.config.externalContext,
      { reuseExistingIntentWhenContextMissing: false },
    );

    return {
      bookId,
      chapterNumber,
      intentPath: relativeToBookDir(bookDir, plan.runtimePath),
      goal: plan.intent.goal,
      conflicts: [],
    };
  }

  async composeChapter(bookId: string, context?: string): Promise<ComposeChapterResult> {
    const book = await this.state.loadBookConfig(bookId);
    if (book.authorityMode !== "runtime") {
      throw new Error("LEGACY_LONG_FORM_READ_ONLY: migrate this book before composing another chapter.");
    }
    const bookDir = this.state.bookDir(bookId);
    const chapterNumber = (await this.chapters.summary(bookId)).latestChapter + 1;
    const stageLanguage = await this.resolveBookLanguage(book);
    this.logStage(stageLanguage, { zh: "组装章节运行时上下文", en: "composing chapter runtime context" });
    const { plan, composed } = await this.createGovernedArtifacts(
      book,
      bookDir,
      chapterNumber,
      context ?? this.config.externalContext,
      { reuseExistingIntentWhenContextMissing: true },
    );

    return {
      bookId,
      chapterNumber,
      intentPath: relativeToBookDir(bookDir, plan.runtimePath),
      goal: plan.intent.goal,
      conflicts: (composed.contextPackage.conflicts ?? []).map((conflict) => conflict.message),
      contextPath: relativeToBookDir(bookDir, composed.contextPath),
      ruleStackPath: relativeToBookDir(bookDir, composed.ruleStackPath),
      tracePath: relativeToBookDir(bookDir, composed.tracePath),
    };
  }

  /** Audit the latest (or specified) chapter. Read-only, no lock needed. */
  async auditDraft(bookId: string, chapterNumber?: number): Promise<AuditResult & { readonly chapterNumber: number }> {
    const book = await this.state.loadBookConfig(bookId);
    const bookDir = this.state.bookDir(bookId);
    const chapter = chapterNumber ? await this.chapters.get(bookId, chapterNumber) : await this.chapters.latest(bookId);
    if (!chapter) {
      throw new Error(`No chapters to audit for "${bookId}"`);
    }
    const targetChapter = chapter.number;

    const content = chapter.body;
    const auditor = new ContinuityAuditor(this.agentCtxFor("auditor", bookId));
    const { profile: gp } = await this.loadGenreProfile(book.genre);
    const language = book.language ?? gp.language;
    this.logStage(language, {
      zh: `审计第${targetChapter}章`,
      en: `auditing chapter ${targetChapter}`,
    });
    const evaluation = await this.evaluateMergedAudit({
      auditor,
      book,
      bookDir,
      chapterContent: content,
      chapterNumber: targetChapter,
      language,
    });
    const result = evaluation.auditResult;

    await this.emitWebhook(
      result.passed ? "audit-passed" : "audit-failed",
      bookId,
      targetChapter,
      { summary: result.summary, issueCount: result.issues.length },
    );

    return { ...result, chapterNumber: targetChapter };
  }

  /** Revise the latest (or specified) chapter based on audit issues. */
  async reviseDraft(bookId: string, chapterNumber?: number, mode: ReviseMode = DEFAULT_REVISE_MODE, externalContext?: string): Promise<ReviseResult> {
    void bookId; void chapterNumber; void mode; void externalContext;
    throw new Error("LEGACY_LONG_FORM_READ_ONLY: revisions must use the Story Runtime review, revision, and commit chain.");
  }

  async readTruthFiles(bookId: string): Promise<TruthFiles> {
    const bookDir = this.state.bookDir(bookId);
    const storyDir = join(bookDir, "story");
    const readSafe = async (path: string): Promise<string> => {
      try {
        return await readFile(path, "utf-8");
      } catch {
        return "(文件不存在)";
      }
    };

    // Phase 5: prefer the new prose outline files; fall back to legacy paths.
    const readOutline = async (newRel: string, legacyRel: string): Promise<string> => {
      const preferred = await readSafe(join(storyDir, newRel));
      if (preferred.trim() && preferred !== "(文件不存在)") return preferred;
      return readSafe(join(storyDir, legacyRel));
    };

    const [currentState, particleLedger, pendingHooks, storyBible, volumeOutline, bookRules] =
      await Promise.all([
        readSafe(join(storyDir, "current_state.md")),
        readSafe(join(storyDir, "particle_ledger.md")),
        readSafe(join(storyDir, "pending_hooks.md")),
        readOutline("outline/story_frame.md", "story_bible.md"),
        readOutline("outline/volume_map.md", "volume_outline.md"),
        readSafe(join(storyDir, "book_rules.md")),
      ]);

    return { currentState, particleLedger, pendingHooks, storyBible, volumeOutline, bookRules };
  }

  /** Get book status overview. */
  async getBookStatus(bookId: string): Promise<BookStatusInfo> {
    const book = await this.state.loadBookConfig(bookId);
    const [chapterPage, analytics] = await Promise.all([this.chapters.listAll(bookId), this.chapters.analytics(bookId)]);
    const chapters: ChapterMeta[] = chapterPage.items.map((chapter) => ({
      number: chapter.number, title: chapter.title,
      status: chapter.status === "finalized" ? "published" : chapter.status as ChapterMeta["status"],
      wordCount: chapter.characterCount, createdAt: chapter.createdAt, updatedAt: chapter.updatedAt,
      auditIssues: [...chapter.auditIssues], lengthWarnings: [],
    }));

    return {
      bookId,
      title: book.title,
      genre: book.genre,
      platform: book.platform,
      status: book.status,
      chaptersWritten: chapters.length,
      totalWords: analytics.totalWords,
      nextChapter: chapterPage.latestChapter + 1,
      chapters: [...chapters],
    };
  }

  // ---------------------------------------------------------------------------
  // Full pipeline (convenience — runs draft + audit + revise in one shot)
  // ---------------------------------------------------------------------------

  async writeNextChapter(bookId: string, wordCount?: number, temperatureOverride?: number): Promise<ChapterPipelineResult> {
    this.throwIfOperationAborted();
    const releaseLock = await this.state.acquireBookLock(bookId);
    try {
      return await this._writeNextChapterLocked(bookId, wordCount, temperatureOverride, this.config.externalContext);
    } finally {
      await releaseLock();
    }
  }

  async repairChapterState(bookId: string, chapterNumber?: number): Promise<ChapterPipelineResult> {
    void bookId; void chapterNumber;
    throw new Error("LEGACY_LONG_FORM_READ_ONLY: state repair is retired; use Story Runtime doctor/replay.");
  }

  async resyncChapterArtifacts(bookId: string, chapterNumber?: number): Promise<ChapterPipelineResult> {
    void bookId; void chapterNumber;
    throw new Error("LEGACY_LONG_FORM_READ_ONLY: Markdown resync is retired; use Story Runtime replay.");
  }

  private async _writeNextChapterLocked(
    bookId: string,
    wordCount?: number,
    temperatureOverride?: number,
    externalContext?: string,
  ): Promise<ChapterPipelineResult> {
    this.throwIfOperationAborted();
    const book = await this.state.loadBookConfig(bookId);
    const runtimeAuthority = book.authorityMode === "runtime";
    if (!runtimeAuthority) {
      throw new Error("LEGACY_LONG_FORM_READ_ONLY: migrate this book with the Runtime migration wizard before writing another chapter.");
    }
    const bookDir = this.state.bookDir(bookId);
    if (!runtimeAuthority) await this.assertNoPendingStateRepair(bookId);
    const runtimeConfig = this.config.storyRuntime;
    if (!runtimeConfig || runtimeConfig.mode !== "story-runtime") {
      throw new Error("Runtime authority requires a configured Story Runtime connection.");
    }
    const runtimeClient = new StoryRuntimeClient({ baseUrl: runtimeConfig.baseUrl, timeoutMs: runtimeConfig.timeoutMs,
      apiToken: runtimeConfig.apiTokenEnv ? process.env[runtimeConfig.apiTokenEnv] : undefined });
    await runtimeClient.assertCompatible();
    const runtimeStatus = await runtimeClient.projectStatus(bookId);
    if (runtimeStatus.authority_mode !== "runtime") {
      throw new Error(`Story Runtime project "${bookId}" is not Runtime authority.`);
    }
    const chapterNumber = runtimeStatus.latest_chapter + 1;
    const narrativeContext = await this.writerNarrative.load({
      projectId: bookId,
      beforeChapter: chapterNumber,
      expectedRevision: runtimeStatus.revision,
      limit: 5,
    });
    const stageLanguage = await this.resolveBookLanguage(book);
    this.logStage(stageLanguage, { zh: "准备章节输入", en: "preparing chapter inputs" });
    const writeInput = await this.prepareWriteInput(
      book,
      bookDir,
      chapterNumber,
      externalContext,
      runtimeStatus.revision,
    );
    const reducedControlInput = writeInput.chapterIntent && writeInput.contextPackage && writeInput.ruleStack
      ? {
          chapterIntent: writeInput.chapterIntent,
          chapterMemo: writeInput.chapterMemo,
          chapterIntentData: writeInput.chapterIntentData,
          contextPackage: writeInput.contextPackage,
          ruleStack: writeInput.ruleStack,
        }
      : undefined;
    const { profile: gp } = await this.loadGenreProfile(book.genre);
    const pipelineLang = book.language ?? gp.language;
    const lengthSpec = buildLengthSpec(
      wordCount ?? book.chapterWordCount,
      pipelineLang,
    );
    const {
      normalizePostWriteSurface,
      validatePostWrite: postWriteValidate,
    } = await import("../agents/post-write-validator.js");
    const { validateHookLedger } = await import("../utils/hook-ledger-validator.js");
    const { readBookRules } = await import("../agents/rules-reader.js");
    const parsedBookRules = (await readBookRules(bookDir))?.rules ?? null;

    // 1. Write chapter
    const writerContext = this.agentCtxFor("writer", bookId);
    const writer = this.config.writerFactory?.(writerContext) ?? new WriterAgent(writerContext);
    this.logStage(stageLanguage, { zh: "撰写章节草稿", en: "writing chapter draft" });
    const output = await writer.writeChapter({
      book,
      bookDir,
      chapterNumber,
      narrativeContext,
      ...writeInput,
      lengthSpec,
      ...(wordCount ? { wordCountOverride: wordCount } : {}),
      ...(temperatureOverride ? { temperatureOverride } : {}),
    });
    this.throwIfOperationAborted();
    const writerCount = countChapterLength(output.content, lengthSpec.countingMode);

    // Token usage accumulator
    let totalUsage: TokenUsageSummary = output.tokenUsage ?? { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
    let finalContent: string;
    let finalWordCount: number;
    let revised: boolean;
    let auditResult: AuditResult;
    let postReviseCount: number;
    let normalizeApplied: boolean;
    let preAuditNormalizedWordCount: number | undefined;

    if ((this.config.chapterReviewMode ?? "auto") === "manual") {
      // C4a: write-only checkpoint. Stop right after the draft — skip the
      // automatic audit→revise loop (which silently doubled chapter time when it
      // fired). The user drives review / revise / accept afterwards.
      this.logStage(stageLanguage, { zh: "写完即停（手动审查模式）", en: "draft written — stopping for manual review" });
      finalContent = normalizePostWriteSurface(output.content, pipelineLang);
      this.assertChapterContentNotEmpty(finalContent, chapterNumber, "manual write");
      finalWordCount = countChapterLength(finalContent, lengthSpec.countingMode);
      revised = false;
      postReviseCount = 0;
      normalizeApplied = finalContent !== output.content;
      preAuditNormalizedWordCount = writerCount;
      auditResult = {
        passed: false,
        issues: [],
        summary: pipelineLang === "en"
          ? "Not reviewed yet (manual mode: stopped after writing — run review when ready)."
          : "尚未审查（手动模式：写完即停，需要时点“审查”）。",
      };
    } else {
      const auditor = new ContinuityAuditor(this.agentCtxFor("auditor", bookId));
      const reviewResult = await runChapterReviewCycle({
        book: { genre: book.genre },
        bookDir,
        chapterNumber,
        initialOutput: output,
        reducedControlInput,
        lengthSpec,
        initialUsage: totalUsage,
        strictArtifactParsing: Boolean(runtimeClient && (this.config.unifiedReviewEnabled ?? true)),
        createReviser: () => new ReviserAgent(this.agentCtxFor("reviser", bookId)),
        auditor,
        normalizeDraftLengthIfNeeded: (chapterContent) => this.normalizeDraftLengthIfNeeded({
          bookId,
          chapterNumber,
          chapterContent,
          lengthSpec,
          chapterIntent: writeInput.chapterIntent,
        }),
        normalizePostWriteSurface: (chapterContent) =>
          normalizePostWriteSurface(chapterContent, pipelineLang),
        assertChapterContentNotEmpty: (content, stage) =>
          this.assertChapterContentNotEmpty(content, chapterNumber, stage),
        addUsage: PipelineRunner.addUsage,
        analyzeAITells: (content) => analyzeAITells(content, pipelineLang),
        analyzeSensitiveWords: (content) => analyzeSensitiveWords(content, undefined, pipelineLang),
        runPostWriteChecks: (content) => {
          const baseIssues = postWriteValidate(content, gp, parsedBookRules, pipelineLang)
            .filter((v) => v.severity === "error")
            .map((v) => ({
              severity: "critical" as const,
              category: v.rule,
              description: v.description,
              suggestion: v.suggestion,
            }));
          // Phase 9-3: verify the draft acts on every hook the memo committed to.
          const memoBody = writeInput.chapterMemo?.body ?? "";
          const ledgerIssues = memoBody
            ? validateHookLedger(memoBody, content)
            : [];
          return [...baseIssues, ...ledgerIssues];
        },
        maxReviewIterations: this.config.writingReviewRetries,
        logWarn: (message) => this.logWarn(pipelineLang, message),
        logStage: (message) => this.logStage(stageLanguage, message),
      });
      totalUsage = reviewResult.totalUsage;
      finalContent = reviewResult.finalContent;
      finalWordCount = reviewResult.finalWordCount;
      revised = reviewResult.revised;
      auditResult = reviewResult.auditResult;
      postReviseCount = reviewResult.postReviseCount;
      normalizeApplied = reviewResult.normalizeApplied;
      preAuditNormalizedWordCount = reviewResult.preAuditNormalizedWordCount;
      if (runtimeClient && reviewResult.revised && (this.config.unifiedReviewEnabled ?? true)) {
        const reviewAdapter = new InkOSReviewAdapter();
        const revisionAdapter = new InkOSRevisionAdapter();
        const initialArtifact = reviewAdapter.fromLegacyAudit({
          projectId: bookId, chapterNumber, sourceRevision: runtimeStatus!.revision,
          body: reviewResult.originalContent, reviewerKind: "auditor", reviewerVersion: "inkos-1.7",
          result: reviewResult.initialAuditResult,
        });
        await runtimeClient.validateReviews({
          projectId: bookId, expectedRevision: runtimeStatus!.revision,
          idempotencyKey: `review-before-revision:${chapterNumber}:${initialArtifact.body_sha256}`,
          chapterNumber, body: reviewResult.originalContent, artifacts: [initialArtifact],
        });
        const plan = revisionAdapter.createPlan({
          projectId: bookId, chapterNumber, sourceRevision: runtimeStatus!.revision,
          body: reviewResult.originalContent, findings: initialArtifact.findings,
          allowedScopes: ["chapter_body"], forbiddenHardFacts: [],
          targetOutcomes: initialArtifact.findings.map((finding) => finding.message),
        });
        const revisionResult = revisionAdapter.toResult({
          plan, originalBody: reviewResult.originalContent,
          output: {
            revisedContent: reviewResult.finalContent, wordCount: reviewResult.finalWordCount,
            fixedIssues: reviewResult.auditResult.passed ? plan.finding_ids : [],
            updatedState: "", updatedLedger: "", updatedHooks: "",
          },
        });
        await runtimeClient.validateRevision({
          projectId: bookId, expectedRevision: runtimeStatus!.revision,
          idempotencyKey: `revision:${chapterNumber}:${revisionResult.revised_body_sha256}`,
          chapterNumber, originalBody: reviewResult.originalContent, revisedBody: reviewResult.finalContent,
          plan, result: revisionResult,
        });
      }
    }

    this.throwIfOperationAborted();
    // 4. Save the final chapter and truth files from a single persistence source
    this.logStage(stageLanguage, { zh: "落盘最终章节", en: "persisting final chapter" });
    this.logStage(stageLanguage, { zh: "生成最终真相文件", en: "rebuilding final truth files" });
    const chapterIndexBeforePersist = await this.chapters.listAll(bookId);
    const { resolveDuplicateTitle } = await import("../agents/post-write-validator.js");
    const initialTitleResolution = resolveDuplicateTitle(
      output.title,
      chapterIndexBeforePersist.items.map((chapter) => chapter.title),
      pipelineLang,
      { content: finalContent },
    );
    let persistenceOutput = await this.buildPersistenceOutput(
      bookId,
      book,
      bookDir,
      chapterNumber,
      initialTitleResolution.title === output.title
        ? output
        : { ...output, title: initialTitleResolution.title },
      finalContent,
      lengthSpec.countingMode,
      reducedControlInput,
    );
    const finalTitleResolution = resolveDuplicateTitle(
      persistenceOutput.title,
      chapterIndexBeforePersist.items.map((chapter) => chapter.title),
      pipelineLang,
      { content: finalContent },
    );
    if (finalTitleResolution.title !== persistenceOutput.title) {
      persistenceOutput = {
        ...persistenceOutput,
        title: finalTitleResolution.title,
      };
    }
    if (persistenceOutput.title !== output.title) {
      const description = pipelineLang === "en"
        ? `Chapter title "${output.title}" was auto-adjusted to "${persistenceOutput.title}".`
        : `章节标题"${output.title}"已自动调整为"${persistenceOutput.title}"。`;
      this.config.logger?.warn(`[title] ${description}`);
      auditResult = {
        ...auditResult,
        issues: [...auditResult.issues, {
          severity: "warning",
          category: "title-dedup",
          description,
          suggestion: pipelineLang === "en"
            ? "If the auto-renamed title is weak, revise the chapter title manually."
            : "如果自动改名不理想，可以在后续手动修订章节标题。",
        }],
      };
    }
    const longSpanFatigue = await analyzeLongSpanFatigue({
      bookDir,
      chapterNumber,
      chapterContent: finalContent,
      chapterSummary: persistenceOutput.chapterSummary,
      language: pipelineLang,
      narrativeChapters: narrativeContext.recentChapters,
    });
    auditResult = {
      ...auditResult,
      issues: [
        ...auditResult.issues,
        ...longSpanFatigue.issues,
        ...(persistenceOutput.hookHealthIssues ?? []),
      ],
    };
    finalWordCount = persistenceOutput.wordCount;
    const lengthWarnings = this.buildLengthWarnings(
      chapterNumber,
      finalWordCount,
      lengthSpec,
    );
    const lengthTelemetry = this.buildLengthTelemetry({
      lengthSpec,
      writerCount,
      postWriterNormalizeCount: preAuditNormalizedWordCount,
      postReviseCount,
      finalCount: finalWordCount,
      normalizeApplied,
      lengthWarning: lengthWarnings.length > 0,
    });
    this.logLengthWarnings(lengthWarnings);

    // Runtime is the only long-form truth owner. Local truth projections are never
    // loaded as validation inputs and may be absent.
    const truthValidation = {
      chapterStatus: null,
      degradedIssues: [] as ReadonlyArray<AuditIssue>,
      persistenceOutput,
      auditResult,
    };
    let chapterStatus: ChapterPipelineResult["status"] | null = truthValidation.chapterStatus;
    let degradedIssues: ReadonlyArray<AuditIssue> = truthValidation.degradedIssues;
    persistenceOutput = truthValidation.persistenceOutput;
    auditResult = truthValidation.auditResult;

    // 4.2 Final paragraph shape check on persisted content (post-normalize, post-revise)
    {
      const {
        detectParagraphLengthDrift,
        detectParagraphShapeWarnings,
      } = await import("../agents/post-write-validator.js");
      const summary = await this.chapters.summary(bookId);
      const recentSnapshot = summary.latestChapter > 0
        ? await this.chapters.exportSnapshot(bookId, { fromChapter: Math.max(1, summary.latestChapter - 4), toChapter: summary.latestChapter })
        : null;
      const recentContent = recentSnapshot?.chapters.map((chapter) => chapter.body).join("\n\n") ?? "";
      const paragraphIssues = [
        ...detectParagraphShapeWarnings(finalContent, pipelineLang),
        ...detectParagraphLengthDrift(finalContent, recentContent, pipelineLang),
      ];
      if (paragraphIssues.length > 0) {
        for (const issue of paragraphIssues) {
          this.config.logger?.warn(`[paragraph] ${issue.description}`);
        }
        auditResult = {
          ...auditResult,
          issues: [...auditResult.issues, ...paragraphIssues.map((v) => ({
            severity: v.severity as "warning",
            category: "paragraph-shape",
            description: v.description,
            suggestion: v.suggestion,
          }))],
        };
      }
    }

    const resolvedStatus = chapterStatus ?? (auditResult.passed ? "ready-for-review" : "audit-failed");
    if (!runtimeClient) throw new Error("Story Runtime client is required for long-form persistence.");
    const persistence = new StoryRuntimeChapterPersistence(runtimeClient, this.config.unifiedReviewEnabled ?? true);
    await persistence.persist({
      projectId: bookId,
      output: persistenceOutput,
      status: resolvedStatus,
      auditResult,
      finalWordCount,
      lengthWarnings,
      lengthTelemetry,
      degradedIssues,
      tokenUsage: totalUsage,
      intent: (reducedControlInput?.chapterIntentData ?? {}) as Record<string, unknown>,
    });

    // 6. Send notification
    if (this.config.notifyChannels && this.config.notifyChannels.length > 0) {
      const statusEmoji = auditResult.passed ? "✅" : "⚠️";
      const chapterLength = formatLengthCount(finalWordCount, lengthSpec.countingMode);
      await dispatchNotification(this.config.notifyChannels, {
        title: `${statusEmoji} ${book.title} 第${chapterNumber}章`,
        body: [
          `**${persistenceOutput.title}** | ${chapterLength}`,
          revised ? "📝 已自动修正" : "",
          `审稿: ${auditResult.passed ? "通过" : "需人工审核"}`,
          ...auditResult.issues
            .filter((i) => i.severity !== "info")
            .map((i) => `- [${i.severity}] ${i.description}`),
        ]
          .filter(Boolean)
          .join("\n"),
      });
    }

    await this.emitWebhook("pipeline-complete", bookId, chapterNumber, {
      title: persistenceOutput.title,
      wordCount: finalWordCount,
      passed: auditResult.passed,
      revised,
      status: resolvedStatus,
    });

    return {
      chapterNumber,
      title: persistenceOutput.title,
      wordCount: finalWordCount,
      auditResult,
      revised,
      status: resolvedStatus,
      lengthWarnings,
      lengthTelemetry,
      tokenUsage: totalUsage,
    };
  }

  async generateStyleGuide(bookId: string, referenceText: string, sourceName?: string): Promise<string> {
    const sample = referenceText.trim();
    if (!sample) {
      throw new Error("Reference text is required for style extraction.");
    }

    const { analyzeStyle } = await import("../agents/style-analyzer.js");
    const bookDir = this.state.bookDir(bookId);
    const storyDir = join(bookDir, "story");
    await mkdir(storyDir, { recursive: true });

    const book = await this.state.loadBookConfig(bookId);
    const { profile: gp } = await this.loadGenreProfile(book.genre);
    const lang = (book.language ?? gp.language) === "en" ? "en" as const : "zh" as const;

    // Statistical fingerprint (language-aware: words for en, characters for zh)
    const profile = analyzeStyle(sample, sourceName, lang);
    await writeFile(join(storyDir, "style_profile.json"), JSON.stringify(profile, null, 2), "utf-8");

    let qualitativeGuide: string;
    if (sample.length < 500) {
      qualitativeGuide = this.buildDeterministicStyleGuide(profile, {
        language: lang,
        reason: lang === "en"
          ? `The sample is short (${sample.length} chars), so this guide uses the statistical fingerprint instead of LLM qualitative extraction.`
          : `样本文本较短（${sample.length}字），本次先使用统计指纹生成文风指南，不强行调用 LLM 做定性拆解。`,
      });
    } else {
      try {
        // LLM qualitative extraction (language-aware prompt)
        const styleSystemPrompt = lang === "en"
          ? `You are a literary style analyst. Analyze the writing style of the reference text and extract qualitative, imitable features.

Output format (Markdown):
## Narrative Voice & Tone
(detached / fervent / ironic / warm / ..., with 1-2 quoted lines from the text)

## Dialogue Style
(shared traits in how characters speak: sentence length, verbal tics, dialect markers, dialogue rhythm)

## Scene Description
(sensory preferences, choice of imagery, description density, how setting ties to emotion)

## Transitions & Connective Technique
(how scenes switch, how time jumps are handled, paragraph-to-paragraph transitions)

## Pacing
(distribution of long vs short sentences, paragraph-length preference, how climaxes and lulls alternate)

## Diction
(signature high-frequency word choices, figurative/rhetorical tendencies, degree of colloquialism)

## Emotional Expression
(direct lyricism vs externalized action, frequency and style of interior monologue)

## Distinctive Habits
(any personal writing habits worth imitating)

Base the analysis on the text's actual features, not generalities. Support each section with 1-2 quoted lines from the original.`
          : `你是一位文学风格分析专家。分析参考文本的写作风格，提取可供模仿的定性特征。

输出格式（Markdown）：
## 叙事声音与语气
（冷峻/热烈/讽刺/温情/...，附1-2个原文例句）

## 对话风格
（角色说话的共性特征：句子长短、口头禅倾向、方言痕迹、对话节奏）

## 场景描写特征
（五感偏好、意象选择、描写密度、环境与情绪的关联方式）

## 转折与衔接手法
（场景如何切换、时间跳跃的处理方式、段落间的过渡特征）

## 节奏特征
（长短句分布、段落长度偏好、高潮/舒缓的交替方式）

## 词汇偏好
（高频特色用词、比喻/修辞倾向、口语化程度）

## 情绪表达方式
（直白抒情 vs 动作外化、内心独白的频率和风格）

## 独特习惯
（任何值得模仿的个人写作习惯）

分析必须基于原文实际特征，不要泛泛而谈。每个部分用1-2个原文例句佐证。`;
        const styleUserPrompt = lang === "en"
          ? `Analyze the writing style of the following reference text:\n\n${sample}`
          : `分析以下参考文本的写作风格：\n\n${sample}`;
        const response = await chatCompletion(this.config.client, this.config.model, [
          { role: "system", content: styleSystemPrompt },
          { role: "user", content: styleUserPrompt },
        ], { temperature: 0.3, signal: this.currentAbortSignal() });
        qualitativeGuide = response.content.trim()
          ? response.content
          : this.buildDeterministicStyleGuide(profile, {
              language: lang,
              reason: lang === "en"
                ? "The LLM returned empty style analysis; using the statistical fingerprint fallback."
                : "LLM 未返回有效文风分析，本次使用统计指纹兜底生成文风指南。",
            });
      } catch (error) {
        qualitativeGuide = this.buildDeterministicStyleGuide(profile, {
          language: lang,
          reason: lang === "en"
            ? `LLM qualitative extraction failed: ${error instanceof Error ? error.message : String(error)}. Using the statistical fingerprint fallback.`
            : `LLM 定性拆解失败：${error instanceof Error ? error.message : String(error)}。本次使用统计指纹兜底生成文风指南。`,
        });
      }
    }

    const craftMethodology = buildWritingMethodologySection(lang);
    const fullStyleGuide = `${qualitativeGuide}\n\n${craftMethodology}`;
    await writeFile(join(storyDir, "style_guide.md"), fullStyleGuide, "utf-8");
    return fullStyleGuide;
  }

  private buildDeterministicStyleGuide(
    profile: {
      readonly avgSentenceLength: number;
      readonly sentenceLengthStdDev: number;
      readonly avgParagraphLength: number;
      readonly vocabularyDiversity: number;
      readonly topPatterns: ReadonlyArray<string>;
      readonly rhetoricalFeatures: ReadonlyArray<string>;
      readonly sourceName?: string;
    },
    options: { readonly language: "zh" | "en"; readonly reason: string },
  ): string {
    if (options.language === "en") {
      return [
        "# Style Guide",
        "",
        `> ${options.reason}`,
        "",
        "## Statistical Fingerprint",
        `- Source: ${profile.sourceName ?? "unknown"}`,
        `- Average sentence length: ${profile.avgSentenceLength}`,
        `- Sentence length variance: ${profile.sentenceLengthStdDev}`,
        `- Average paragraph length: ${profile.avgParagraphLength}`,
        `- Vocabulary diversity: ${Math.round(profile.vocabularyDiversity * 100)}%`,
        profile.topPatterns.length > 0 ? `- Repeated openings: ${profile.topPatterns.join(", ")}` : "- Repeated openings: none obvious in this sample",
        profile.rhetoricalFeatures.length > 0 ? `- Rhetorical features: ${profile.rhetoricalFeatures.join(", ")}` : "- Rhetorical features: none obvious in this sample",
        "",
        "## How To Use",
        "- Treat this as a lightweight style fingerprint, not a full imitation bible.",
        "- Keep sentence and paragraph rhythm close to the sample when drafting.",
        "- If this guide feels too thin, import a longer excerpt later; the file will be replaced.",
      ].join("\n");
    }

    return [
      "# 文风指南",
      "",
      `> ${options.reason}`,
      "",
      "## 统计风格指纹",
      `- 来源：${profile.sourceName ?? "unknown"}`,
      `- 平均句长：${profile.avgSentenceLength}`,
      `- 句长波动：${profile.sentenceLengthStdDev}`,
      `- 平均段落长度：${profile.avgParagraphLength}`,
      `- 词汇多样性：${Math.round(profile.vocabularyDiversity * 100)}%`,
      profile.topPatterns.length > 0 ? `- 高频句首/模式：${profile.topPatterns.join("、")}` : "- 高频句首/模式：样本内不明显",
      profile.rhetoricalFeatures.length > 0 ? `- 修辞特征：${profile.rhetoricalFeatures.join("、")}` : "- 修辞特征：样本内不明显",
      "",
      "## 使用方式",
      "- 这是一份轻量文风指纹，不是完整仿写圣经。",
      "- 后续写作优先参考句长、段落长度、节奏波动和可见修辞。",
      "- 如果想得到更稳定的定性拆解，后续可以导入更长片段覆盖本文件。",
    ].join("\n");
  }

  /**
   * Import canon from parent book for spinoff writing.
   * Reads parent's truth files, uses LLM to generate parent_canon.md in target book.
   */
  async importCanon(targetBookId: string, parentBookId: string): Promise<string> {
    // Validate both books exist
    const bookIds = await this.state.listBooks();
    if (!bookIds.includes(parentBookId)) {
      throw new Error(`Parent book "${parentBookId}" not found. Available: ${bookIds.join(", ") || "(none)"}`);
    }
    if (!bookIds.includes(targetBookId)) {
      throw new Error(`Target book "${targetBookId}" not found. Available: ${bookIds.join(", ") || "(none)"}`);
    }

    const parentDir = this.state.bookDir(parentBookId);
    const targetDir = this.state.bookDir(targetBookId);
    const storyDir = join(targetDir, "story");
    await mkdir(storyDir, { recursive: true });

    const readSafe = async (path: string): Promise<string> => {
      try { return await readFile(path, "utf-8"); } catch { return "(无)"; }
    };

    const parentBook = await this.state.loadBookConfig(parentBookId);

    // Phase 5: parent book may be on the new prose layout; prefer outline/.
    const readParentOutline = async (newRel: string, legacyRel: string): Promise<string> => {
      const preferred = await readSafe(join(parentDir, "story", newRel));
      if (preferred.trim() && preferred !== "(无)") return preferred;
      return readSafe(join(parentDir, "story", legacyRel));
    };

    const [storyBible, currentState, ledger, hooks, summaries, subplots, emotions, matrix] =
      await Promise.all([
        readParentOutline("outline/story_frame.md", "story_bible.md"),
        readSafe(join(parentDir, "story/current_state.md")),
        readSafe(join(parentDir, "story/particle_ledger.md")),
        readSafe(join(parentDir, "story/pending_hooks.md")),
        readSafe(join(parentDir, "story/chapter_summaries.md")),
        readSafe(join(parentDir, "story/subplot_board.md")),
        readSafe(join(parentDir, "story/emotional_arcs.md")),
        readSafe(join(parentDir, "story/character_matrix.md")),
      ]);

    const response = await chatCompletion(this.config.client, this.config.model, [
      {
        role: "system",
        content: `你是一位网络小说架构师。基于正传的全部设定和状态文件，生成一份完整的"正传正典参照"文档，供番外写作和审计使用。

输出格式（Markdown）：
# 正传正典（《{正传书名}》）

## 世界规则（完整，来自正传设定）
（力量体系、地理设定、阵营关系、核心规则——完整复制，不压缩）

## 正典约束（不可违反的事实）
| 约束ID | 类型 | 约束内容 | 严重性 |
|---|---|---|---|
| C01 | 人物存亡 | ... | critical |
（列出所有硬性约束：谁活着、谁死了、什么事件已经发生、什么规则不可违反）

## 角色快照
| 角色 | 当前状态 | 性格底色 | 对话特征 | 已知信息 | 未知信息 |
|---|---|---|---|---|---|
（从状态卡和角色矩阵中提取每个重要角色的完整快照）

## 角色双态处理原则
- 未来会变强的角色：写潜力暗示
- 未来会黑化的角色：写微小裂痕
- 未来会死的角色：写导致死亡的性格底色

## 关键事件时间线
| 章节 | 事件 | 涉及角色 | 对番外的约束 |
|---|---|---|---|
（从章节摘要中提取关键事件）

## 伏笔状态
| Hook ID | 类型 | 状态 | 内容 | 预期回收 |
|---|---|---|---|---|

## 资源账本快照
（当前资源状态）

---
meta:
  parentBookId: "{parentBookId}"
  parentTitle: "{正传书名}"
  generatedAt: "{ISO timestamp}"

要求：
1. 世界规则完整复制，不压缩——准确性优先
2. 正典约束必须穷尽，遗漏会导致番外与正传矛盾
3. 角色快照必须包含信息边界（已知/未知），防止番外中角色引用不该知道的信息`,
      },
      {
        role: "user",
        content: `正传书名：${parentBook.title}
正传ID：${parentBookId}

## 正传世界设定
${storyBible}

## 正传当前状态卡
${currentState}

## 正传资源账本
${ledger}

## 正传伏笔池
${hooks}

## 正传章节摘要
${summaries}

## 正传支线进度
${subplots}

## 正传情感弧线
${emotions}

## 正传角色矩阵
${matrix}`,
      },
    ], { temperature: 0.3, signal: this.currentAbortSignal() });

    // Append deterministic meta block (LLM may hallucinate timestamps)
    const metaBlock = [
      "",
      "---",
      "meta:",
      `  parentBookId: "${parentBookId}"`,
      `  parentTitle: "${parentBook.title}"`,
      `  generatedAt: "${new Date().toISOString()}"`,
    ].join("\n");
    const canon = response.content + metaBlock;

    await writeFile(join(storyDir, "parent_canon.md"), canon, "utf-8");

    // Also generate style guide from parent's chapter text if available
    const parentChapterText = (await this.chapters.exportSnapshot(parentBookId, { fromChapter: 1, toChapter: 5 }))
      .chapters.map((chapter) => chapter.body)
      .join("\n\n---\n\n")
      .slice(0, 20_000);
    if (parentChapterText.length >= 500) {
      await this.tryGenerateStyleGuide(targetBookId, parentChapterText, parentBook.title);
    }

    return canon;
  }

  // ---------------------------------------------------------------------------
  // Chapter import (for continuation writing from existing chapters)
  // ---------------------------------------------------------------------------

  /**
   * Import existing chapters into a book. Reverse-engineers all truth files
   * via sequential replay so the Writer and Auditor can continue naturally.
   *
   * Step 1: Generate foundation (story_frame, volume_map, book_rules) from all chapters.
   * Step 2: Sequentially replay each chapter through ChapterAnalyzer to build truth files.
   */
  async importChapters(input: ImportChaptersInput): Promise<ImportChaptersResult> {
    void input;
    throw new Error("LEGACY_LONG_FORM_READ_ONLY: chapter import is available only through the controlled Runtime migration workflow.");
  }

  private static addUsage(
    a: TokenUsageSummary,
    b?: { readonly promptTokens: number; readonly completionTokens: number; readonly totalTokens: number },
  ): TokenUsageSummary {
    if (!b) return a;
    return {
      promptTokens: a.promptTokens + b.promptTokens,
      completionTokens: a.completionTokens + b.completionTokens,
      totalTokens: a.totalTokens + b.totalTokens,
    };
  }

  private async buildPersistenceOutput(
    bookId: string,
    book: BookConfig,
    bookDir: string,
    chapterNumber: number,
    output: WriteChapterOutput,
    finalContent: string,
    countingMode: Parameters<typeof countChapterLength>[1],
    reducedControlInput?: {
      chapterIntent: string;
      contextPackage: ContextPackage;
      ruleStack: RuleStack;
    },
  ): Promise<WriteChapterOutput> {
    if (finalContent === output.content) {
      return output;
    }

    const analyzer = new ChapterAnalyzerAgent(this.agentCtxFor("chapter-analyzer", bookId));
    const analyzed = await analyzer.analyzeChapter({
      book,
      bookDir,
      chapterNumber,
      chapterContent: finalContent,
      chapterTitle: output.title,
      chapterIntent: reducedControlInput?.chapterIntent,
      contextPackage: reducedControlInput?.contextPackage,
      ruleStack: reducedControlInput?.ruleStack,
    });

    return {
      ...analyzed,
      content: finalContent,
      wordCount: countChapterLength(finalContent, countingMode),
      postWriteErrors: [],
      postWriteWarnings: [],
      hookHealthIssues: output.hookHealthIssues,
      tokenUsage: output.tokenUsage,
    };
  }

  private async assertNoPendingStateRepair(bookId: string): Promise<void> {
    const latestChapter = await this.chapters.latest(bookId);
    if (latestChapter?.status !== "state-degraded") {
      return;
    }

    throw new Error(
      `Latest chapter ${latestChapter.number} is state-degraded. Repair state or rewrite that chapter before continuing.`,
    );
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  private async prepareWriteInput(
    book: BookConfig,
    bookDir: string,
    chapterNumber: number,
    externalContext?: string,
    expectedRevision?: number,
  ): Promise<Pick<WriteChapterInput, "externalContext" | "chapterIntent" | "chapterMemo" | "chapterIntentData" | "contextPackage" | "ruleStack">> {
    if ((this.config.inputGovernanceMode ?? "v2") === "legacy") {
      return { externalContext };
    }

    const { plan, composed } = await this.createGovernedArtifacts(
      book,
      bookDir,
      chapterNumber,
      externalContext,
      { reuseExistingIntentWhenContextMissing: true, expectedRevision },
    );

    return {
      externalContext,
      chapterIntent: plan.intentMarkdown,
      chapterMemo: plan.memo,
      chapterIntentData: plan.intent,
      contextPackage: composed.contextPackage,
      ruleStack: composed.ruleStack,
    };
  }

  private async normalizeDraftLengthIfNeeded(params: {
    bookId: string;
    chapterNumber: number;
    chapterContent: string;
    lengthSpec: LengthSpec;
    chapterIntent?: string;
  }): Promise<{
    content: string;
    wordCount: number;
    applied: boolean;
    tokenUsage?: TokenUsageSummary;
  }> {
    const writerCount = countChapterLength(
      params.chapterContent,
      params.lengthSpec.countingMode,
    );
    if (!isOutsideHardRange(writerCount, params.lengthSpec)) {
      return {
        content: params.chapterContent,
        wordCount: writerCount,
        applied: false,
      };
    }

    const normalizer = new LengthNormalizerAgent(
      this.agentCtxFor("length-normalizer", params.bookId),
    );
    const normalized = await normalizer.normalizeChapter({
      chapterContent: params.chapterContent,
      lengthSpec: params.lengthSpec,
      chapterIntent: params.chapterIntent,
    });

    // Safety net: if normalizer output is less than 25% of original, it was too destructive.
    // Reject and keep original content.
    if (normalized.finalCount < writerCount * 0.25) {
      this.logWarn(this.languageFromLengthSpec(params.lengthSpec), {
        zh: `字数归一化被拒绝：第${params.chapterNumber}章 ${writerCount} -> ${normalized.finalCount}（砍了${Math.round((1 - normalized.finalCount / writerCount) * 100)}%，超过安全阈值）`,
        en: `Length normalization rejected for chapter ${params.chapterNumber}: ${writerCount} -> ${normalized.finalCount} (cut ${Math.round((1 - normalized.finalCount / writerCount) * 100)}%, exceeds safety threshold)`,
      });
      return {
        content: params.chapterContent,
        wordCount: writerCount,
        applied: false,
      };
    }

    this.logInfo(this.languageFromLengthSpec(params.lengthSpec), {
      zh: `审计前字数归一化：第${params.chapterNumber}章 ${writerCount} -> ${normalized.finalCount}`,
      en: `Length normalization before audit for chapter ${params.chapterNumber}: ${writerCount} -> ${normalized.finalCount}`,
    });

    return {
      content: normalized.normalizedContent,
      wordCount: normalized.finalCount,
      applied: normalized.applied,
      tokenUsage: normalized.tokenUsage,
    };
  }

  private assertChapterContentNotEmpty(content: string, chapterNumber: number, stage: string): void {
    if (content.trim().length > 0) return;
    throw new Error(`Chapter ${chapterNumber} has empty chapter content after ${stage}`);
  }

  private buildLengthWarnings(
    chapterNumber: number,
    finalCount: number,
    lengthSpec: LengthSpec,
  ): string[] {
    if (!isOutsideHardRange(finalCount, lengthSpec)) {
      return [];
    }
    return [
      this.localize(this.languageFromLengthSpec(lengthSpec), {
        zh: `第${chapterNumber}章经过一次字数归一化后仍超出硬区间（${lengthSpec.hardMin}-${lengthSpec.hardMax}，实际 ${finalCount}）。`,
        en: `Chapter ${chapterNumber} remains outside hard range (${lengthSpec.hardMin}-${lengthSpec.hardMax}, actual ${finalCount}) after a single normalization pass.`,
      }),
    ];
  }

  private buildLengthTelemetry(params: {
    lengthSpec: LengthSpec;
    writerCount: number;
    postWriterNormalizeCount: number;
    postReviseCount: number;
    finalCount: number;
    normalizeApplied: boolean;
    lengthWarning: boolean;
  }): LengthTelemetry {
    return {
      target: params.lengthSpec.target,
      softMin: params.lengthSpec.softMin,
      softMax: params.lengthSpec.softMax,
      hardMin: params.lengthSpec.hardMin,
      hardMax: params.lengthSpec.hardMax,
      countingMode: params.lengthSpec.countingMode,
      writerCount: params.writerCount,
      postWriterNormalizeCount: params.postWriterNormalizeCount,
      postReviseCount: params.postReviseCount,
      finalCount: params.finalCount,
      normalizeApplied: params.normalizeApplied,
      lengthWarning: params.lengthWarning,
    };
  }

  private logLengthWarnings(lengthWarnings: ReadonlyArray<string>): void {
    for (const warning of lengthWarnings) {
      this.config.logger?.warn(warning);
    }
  }

  private restoreLostAuditIssues(previous: AuditResult, next: AuditResult): AuditResult {
    if (next.passed || next.issues.length > 0 || previous.issues.length === 0) {
      return next;
    }

    return {
      ...next,
      issues: previous.issues,
      summary: next.summary || previous.summary,
    };
  }

  private restoreActionableAuditIfLost(
    previous: {
      auditResult: AuditResult;
      aiTellCount: number;
      blockingCount: number;
      criticalCount: number;
      revisionBlockingIssues: ReadonlyArray<AuditIssue>;
    },
    next: {
      auditResult: AuditResult;
      aiTellCount: number;
      blockingCount: number;
      criticalCount: number;
      revisionBlockingIssues: ReadonlyArray<AuditIssue>;
    },
  ): MergedAuditEvaluation {
    const auditResult = this.restoreLostAuditIssues(previous.auditResult, next.auditResult);
    if (auditResult === next.auditResult) {
      return next;
    }

    return {
      ...next,
      auditResult,
      revisionBlockingIssues: previous.revisionBlockingIssues,
      blockingCount: previous.blockingCount,
      criticalCount: previous.criticalCount,
    };
  }

  private async evaluateMergedAudit(params: {
    auditor: ContinuityAuditor;
    book: BookConfig;
    bookDir: string;
    chapterContent: string;
    chapterNumber: number;
    language: LengthLanguage;
    auditOptions?: {
      temperature?: number;
      chapterIntent?: string;
      chapterMemo?: ChapterMemo;
      contextPackage?: ContextPackage;
      ruleStack?: RuleStack;
      truthFileOverrides?: {
        currentState?: string;
        ledger?: string;
        hooks?: string;
      };
    };
  }): Promise<MergedAuditEvaluation> {
    const llmAudit = await params.auditor.auditChapter(
      params.bookDir,
      params.chapterContent,
      params.chapterNumber,
      params.book.genre,
      params.auditOptions,
    );
    const aiTells = analyzeAITells(params.chapterContent, params.language);
    const sensitiveResult = analyzeSensitiveWords(params.chapterContent, undefined, params.language);
    const longSpanFatigue = await analyzeLongSpanFatigue({
      bookDir: params.bookDir,
      chapterNumber: params.chapterNumber,
      chapterContent: params.chapterContent,
      language: params.language,
    });
    const hasBlockedWords = sensitiveResult.found.some((f) => f.severity === "block");
    const issues: ReadonlyArray<AuditIssue> = [
      ...llmAudit.issues,
      ...aiTells.issues,
      ...sensitiveResult.issues,
      ...longSpanFatigue.issues,
    ];
    // revisionBlockingIssues excludes long-span-fatigue issues by
    // construction (not by category name) so that an LLM-reported issue
    // sharing a category label with a long-span issue is still counted.
    const revisionBlockingIssues: ReadonlyArray<AuditIssue> = [
      ...llmAudit.issues,
      ...aiTells.issues,
      ...sensitiveResult.issues,
    ];

    return {
      auditResult: {
        passed: hasBlockedWords ? false : llmAudit.passed,
        issues,
        summary: llmAudit.summary,
        tokenUsage: llmAudit.tokenUsage,
      },
      aiTellCount: aiTells.issues.length,
      blockingCount: revisionBlockingIssues.filter((issue) => issue.severity === "warning" || issue.severity === "critical").length,
      criticalCount: revisionBlockingIssues.filter((issue) => issue.severity === "critical").length,
      revisionBlockingIssues,
    };
  }

  private async markBookActiveIfNeeded(bookId: string): Promise<void> {
    const book = await this.state.loadBookConfig(bookId);
    if (book.status !== "outlining") return;

    await this.state.saveBookConfig(bookId, {
      ...book,
      status: "active",
      updatedAt: new Date().toISOString(),
    });
  }

  private async createGovernedArtifacts(
    book: BookConfig,
    bookDir: string,
    chapterNumber: number,
    externalContext?: string,
    options?: {
      readonly reuseExistingIntentWhenContextMissing?: boolean;
      readonly expectedRevision?: number;
    },
  ): Promise<{
    plan: PlanChapterOutput;
    composed: ComposeChapterOutput;
  }> {
    const plan = await this.resolveGovernedPlan(book, bookDir, chapterNumber, externalContext, options);
    const composerCtx = this.agentCtxFor("composer", book.id);
    const composer = new ComposerAgent(composerCtx);
    const composed = await composeGovernedChapter({
      book,
      bookDir,
      chapterNumber,
      plan,
      contextBudget: contextBudgetFromClient(composerCtx.client),
      compressibleContextCompiler: (request) => composer.compileCompressibleContext(request),
      onContextCompression: this.config.onContextCompression,
      storyRuntime: book.authorityMode === "runtime" && this.config.storyRuntime
        ? { ...this.config.storyRuntime, mode: "story-runtime" }
        : this.config.storyRuntime,
      expectedRevision: options?.expectedRevision,
    });

    return { plan, composed };
  }

  private async resolveGovernedPlan(
    book: BookConfig,
    bookDir: string,
    chapterNumber: number,
    externalContext?: string,
    options?: {
      readonly reuseExistingIntentWhenContextMissing?: boolean;
    },
  ): Promise<PlanChapterOutput> {
    if (
      options?.reuseExistingIntentWhenContextMissing &&
      (!externalContext || externalContext.trim().length === 0)
    ) {
      const persisted = await loadPersistedPlan(bookDir, chapterNumber);
      if (persisted) return persisted;
    }

    const planner = new PlannerAgent(this.agentCtxFor("planner", book.id));
    const plan = await planner.planChapter({
      book,
      bookDir,
      chapterNumber,
      externalContext,
    });
    // Persist in the new memo format so subsequent compose/write phases can
    // skip the planner LLM call when no new context is supplied.
    await savePersistedPlan(bookDir, plan);
    return plan;
  }

  private async emitWebhook(
    event: WebhookEvent,
    bookId: string,
    chapterNumber?: number,
    data?: Record<string, unknown>,
  ): Promise<void> {
    if (!this.config.notifyChannels || this.config.notifyChannels.length === 0) return;
    await dispatchWebhookEvent(this.config.notifyChannels, {
      event,
      bookId,
      chapterNumber,
      timestamp: new Date().toISOString(),
      data,
    });
  }

}
