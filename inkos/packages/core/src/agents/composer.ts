import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { BaseAgent } from "./base.js";
import type { BookConfig } from "../models/book.js";
import {
  type ChapterTrace,
  type ContextPackage,
  type RuleStack,
} from "../models/input-governance.js";
import type { PlanChapterOutput } from "./planner.js";
import {
  buildGovernedRuleStack,
  buildGovernedTrace,
  isProtectedContextSource,
} from "../utils/context-assembly.js";
import { writeGovernedRuntimeArtifacts } from "../utils/runtime-writer.js";
import { estimateTextTokens, type LLMClient } from "../llm/provider.js";
import type { ContextCompressionCallback } from "../models/context-compression.js";
import {
  buildSkillContextPlan,
  createSkillRegistry,
} from "../skills/index.js";
import { StoryRuntimeClient } from "../story-runtime/client.js";
import type { StoryRuntimeConfig } from "../story-runtime/schemas.js";
import {
  contextPackageFromSelected,
  selectContextProvider,
  StoryRuntimeContextProvider,
} from "../story-runtime/context-provider.js";

export interface ComposeChapterInput {
  readonly book: BookConfig;
  readonly bookDir: string;
  readonly chapterNumber: number;
  readonly plan: PlanChapterOutput;
  readonly contextBudget?: ContextBudget;
  readonly compressibleContextCompiler?: CompressibleContextCompiler;
  readonly onContextCompression?: ContextCompressionCallback;
  readonly storyRuntime?: StoryRuntimeConfig;
  readonly storyRuntimeClient?: StoryRuntimeClient;
  readonly expectedRevision?: number;
}
export interface ContextBudget {
  readonly contextWindowTokens: number;
  readonly reservedOutputTokens: number;
}
export interface CompressibleContextCompileRequest {
  readonly chapterNumber: number;
  readonly goal: string;
  readonly language: "zh" | "en";
  readonly maxInputTokens: number;
  readonly protectedEntries: ContextPackage["selectedContext"];
  readonly compressibleEntries: ContextPackage["selectedContext"];
}

export type CompressibleContextCompiler = (request: CompressibleContextCompileRequest) => Promise<string>;

export interface ComposeChapterOutput {
  readonly contextPackage: ContextPackage;
  readonly ruleStack: RuleStack;
  readonly trace: ChapterTrace;
  readonly contextPath: string;
  readonly ruleStackPath: string;
  readonly tracePath: string;
}

export async function composeGovernedChapter(input: ComposeChapterInput): Promise<ComposeChapterOutput> {
  const storyDir = join(input.bookDir, "story");
  const runtimeDir = join(storyDir, "runtime");
  await mkdir(runtimeDir, { recursive: true });
  const longformSkill = createSkillRegistry().getSkill("longform-writing");
  const skillContextPlan = buildSkillContextPlan({
    skills: longformSkill ? [longformSkill] : [],
    appliesTo: "composer",
  });

  const runtimeConfig = input.storyRuntime ?? {
    mode: "story-runtime" as const,
    baseUrl: "http://127.0.0.1:47831",
    timeoutMs: 3_000,
    maxContextTokens: 16_000,
    maxItems: 100,
  };
  const runtimeClient = input.storyRuntimeClient ?? new StoryRuntimeClient({
    baseUrl: runtimeConfig.baseUrl,
    timeoutMs: runtimeConfig.timeoutMs,
    apiToken: runtimeConfig.apiTokenEnv ? process.env[runtimeConfig.apiTokenEnv] : undefined,
  });
  const availableTokens = input.contextBudget
    ? Math.max(256, input.contextBudget.contextWindowTokens - Math.max(0, input.contextBudget.reservedOutputTokens))
    : runtimeConfig.maxContextTokens;
  const selection = await selectContextProvider({
    mode: runtimeConfig.mode,
    runtime: new StoryRuntimeContextProvider(runtimeClient),
    request: {
      book: input.book,
      chapterNumber: input.chapterNumber,
      plan: input.plan,
      maxTokens: Math.min(runtimeConfig.maxContextTokens, availableTokens),
      maxItems: runtimeConfig.maxItems,
      expectedRevision: input.expectedRevision,
    },
  });
  const initialContextPackage = selection.contextPackage;
  const budgeted = await applyContextBudgetIfNeeded({
    contextPackage: initialContextPackage,
    chapterNumber: input.chapterNumber,
    goal: input.plan.intent.goal,
    language: input.book.language ?? "zh",
    contextBudget: input.contextBudget,
    compiler: input.compressibleContextCompiler,
    onContextCompression: input.onContextCompression,
  });
  const contextPackage = budgeted.contextPackage;

  const ruleStack = buildGovernedRuleStack(input.plan, input.chapterNumber);
  const trace = buildGovernedTrace({
    chapterNumber: input.chapterNumber,
    plan: input.plan,
    contextPackage,
    composerInputs: [input.plan.runtimePath],
    notes: [...selection.notes, ...budgeted.notes],
    usedSkills: skillContextPlan.usedSkillIds,
    promptPacks: skillContextPlan.promptPackIds,
    contextNeeds: skillContextPlan.contextNeedIds,
    compression: budgeted.compression,
  });
  const {
    contextPath,
    ruleStackPath,
    tracePath,
  } = await writeGovernedRuntimeArtifacts({
    runtimeDir,
    chapterNumber: input.chapterNumber,
    contextPackage,
    ruleStack,
    trace,
  });

  return {
    contextPackage,
    ruleStack,
    trace,
    contextPath,
    ruleStackPath,
    tracePath,
  };
}

async function applyContextBudgetIfNeeded(params: {
  readonly contextPackage: ContextPackage;
  readonly chapterNumber: number;
  readonly goal: string;
  readonly language: "zh" | "en";
  readonly contextBudget?: ContextBudget;
  readonly compiler?: CompressibleContextCompiler;
  readonly onContextCompression?: ContextCompressionCallback;
}): Promise<{
  readonly contextPackage: ContextPackage;
  readonly notes: string[];
  readonly compression?: ChapterTrace["compression"];
}> {
  const budget = params.contextBudget;
  if (!budget || budget.contextWindowTokens <= 0) {
    return { contextPackage: params.contextPackage, notes: [] };
  }

  const availableInputTokens = budget.contextWindowTokens - Math.max(0, budget.reservedOutputTokens);
  const selectedContext = params.contextPackage.selectedContext;
  const totalTokens = estimateSelectedContextTokens(selectedContext);
  if (totalTokens <= availableInputTokens) {
    return { contextPackage: params.contextPackage, notes: [] };
  }

  const protectedEntries = selectedContext.filter((entry) => isProtectedContextSource(entry.source));
  const compressibleEntries = selectedContext.filter((entry) => !isProtectedContextSource(entry.source));
  const protectedTokens = estimateSelectedContextTokens(protectedEntries);
  if (protectedTokens > availableInputTokens) {
    params.onContextCompression?.({
      category: "story_context",
      phase: "error",
      message: "Protected context exceeds available input budget.",
      protectedTokens,
      compressibleTokens: totalTokens - protectedTokens,
      budgetTokens: availableInputTokens,
      sources: protectedEntries.map((entry) => entry.source),
    });
    throw new Error(
      `Protected context exceeds available input budget (${protectedTokens}/${availableInputTokens} tokens). ` +
      "InkOS will not compress protected author intent, current focus, hard state, or active hook evidence.",
    );
  }
  if (compressibleEntries.length === 0) {
    return { contextPackage: params.contextPackage, notes: ["context-over-budget-no-compressible-entries"] };
  }
  if (!params.compiler) {
    params.onContextCompression?.({
      category: "story_context",
      phase: "error",
      message: "Context exceeds available input budget but no compiler was provided.",
      protectedTokens,
      compressibleTokens: estimateSelectedContextTokens(compressibleEntries),
      budgetTokens: availableInputTokens,
      sources: compressibleEntries.map((entry) => entry.source),
    });
    throw new Error(
      `Context exceeds available input budget (${totalTokens}/${availableInputTokens} tokens), ` +
      "but no compressible context compiler was provided.",
    );
  }

  const compileBudget = Math.max(1, availableInputTokens - protectedTokens);
  const compressibleTokens = estimateSelectedContextTokens(compressibleEntries);
  params.onContextCompression?.({
    category: "story_context",
    phase: "start",
    protectedTokens,
    compressibleTokens,
    budgetTokens: compileBudget,
    sources: compressibleEntries.map((entry) => entry.source),
  });
  let compiled: string;
  try {
    compiled = (await params.compiler({
      chapterNumber: params.chapterNumber,
      goal: params.goal,
      language: params.language,
      maxInputTokens: compileBudget,
      protectedEntries,
      compressibleEntries,
    })).trim();
  } catch (error) {
    params.onContextCompression?.({
      category: "story_context",
      phase: "error",
      message: error instanceof Error ? error.message : String(error),
      protectedTokens,
      compressibleTokens,
      budgetTokens: compileBudget,
      sources: compressibleEntries.map((entry) => entry.source),
    });
    throw error;
  }
  if (!compiled) {
    params.onContextCompression?.({
      category: "story_context",
      phase: "error",
      message: "Compressible context compiler returned empty output.",
      protectedTokens,
      compressibleTokens,
      budgetTokens: compileBudget,
      sources: compressibleEntries.map((entry) => entry.source),
    });
    throw new Error("Compressible context compiler returned empty output.");
  }
  params.onContextCompression?.({
    category: "story_context",
    phase: "end",
    protectedTokens,
    compressibleTokens,
    budgetTokens: compileBudget,
    sources: compressibleEntries.map((entry) => entry.source),
  });

  return {
    contextPackage: contextPackageFromSelected(
      params.contextPackage.chapter,
      [
        ...protectedEntries,
        {
          source: "runtime/compiled-compressible-context",
          reason: "Semantic compilation of lower-priority context after protected context exceeded the input budget.",
          excerpt: compiled,
          layer: "relevant_memory",
          confidence: 0.8,
          updatedAt: new Date().toISOString(),
          importance: 50,
          trust: "trusted",
        },
      ],
      params.contextPackage.conflicts ?? [],
    ),
    notes: ["compiled-compressible-context"],
    compression: {
      compiledSource: "runtime/compiled-compressible-context",
      protectedSources: protectedEntries.map((entry) => entry.source),
      compressedSources: compressibleEntries.map((entry) => entry.source),
      protectedTokens,
      compressibleTokens,
      budgetTokens: compileBudget,
    },
  };
}

function estimateSelectedContextTokens(entries: ContextPackage["selectedContext"]): number {
  return entries.reduce((total, entry) => (
    total + estimateTextTokens([entry.source, entry.reason, entry.excerpt].filter(Boolean).join("\n"))
  ), 0);
}

function renderContextEntries(entries: ContextPackage["selectedContext"]): string {
  return entries.map((entry) =>
    [
      `### ${entry.source}`,
      `Reason: ${entry.reason}`,
      entry.excerpt ? entry.excerpt : "(no excerpt)",
    ].join("\n"),
  ).join("\n\n");
}

export class ComposerAgent extends BaseAgent {
  get name(): string {
    return "composer";
  }

  async composeChapter(input: ComposeChapterInput): Promise<ComposeChapterOutput> {
    const contextBudget = input.contextBudget ?? contextBudgetFromClient(this.ctx.client);
    return composeGovernedChapter({
      ...input,
      contextBudget,
      compressibleContextCompiler: input.compressibleContextCompiler
        ?? (contextBudget ? (request) => this.compileCompressibleContext(request) : undefined),
    });
  }

  async compileCompressibleContext(request: CompressibleContextCompileRequest): Promise<string> {
    const isEn = request.language === "en";
    const protectedBlock = renderContextEntries(request.protectedEntries);
    const compressibleBlock = renderContextEntries(request.compressibleEntries);
    const system = isEn
      ? [
          "You are InkOS's semantic context compiler.",
          "Only compile the COMPRESSIBLE CONTEXT. The PROTECTED CONTEXT is binding reference material and must not be rewritten, summarized as a substitute, or weakened.",
          "Output concise Markdown with source pointers. Preserve names, unresolved promises, evidence, timing, and constraints that may affect the next chapter. Drop low-relevance noise.",
        ].join("\n")
      : [
          "你是 InkOS 的语义上下文编译器。",
          "只能编译【可压缩上下文】。【受保护上下文】是绑定参照，不得改写、不得替代总结、不得削弱。",
          "输出简洁 Markdown，保留来源指针。保留会影响下一章的人名、未兑现承诺、证据、时间点和约束，丢弃低相关噪声。",
        ].join("\n");
    const user = isEn
      ? [
          `Chapter: ${request.chapterNumber}`,
          `Goal: ${request.goal}`,
          `Target budget for compiled context: <= ${request.maxInputTokens} estimated input tokens`,
          "",
          "## Protected Context (reference only, do not compile)",
          protectedBlock || "(none)",
          "",
          "## Compressible Context (compile this)",
          compressibleBlock || "(none)",
        ].join("\n")
      : [
          `章节：第${request.chapterNumber}章`,
          `目标：${request.goal}`,
          `压缩后目标预算：不超过 ${request.maxInputTokens} 估算输入 tokens`,
          "",
          "## 受保护上下文（只作为参照，不要编译它）",
          protectedBlock || "（无）",
          "",
          "## 可压缩上下文（只编译这一部分）",
          compressibleBlock || "（无）",
        ].join("\n");

    const response = await this.chat([
      { role: "system", content: system },
      { role: "user", content: user },
    ], {
      temperature: 0.2,
      maxTokens: Math.min(8192, Math.max(512, request.maxInputTokens)),
    });
    return response.content.trim();
  }
}

export function contextBudgetFromClient(client: LLMClient): ContextBudget | undefined {
  const contextWindowTokens = client._piModel?.contextWindow;
  if (!Number.isFinite(contextWindowTokens) || !contextWindowTokens || contextWindowTokens <= 0) {
    return undefined;
  }
  return {
    contextWindowTokens,
    reservedOutputTokens: Math.max(0, client.defaults.maxTokens),
  };
}
