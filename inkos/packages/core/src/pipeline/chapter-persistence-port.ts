import { createHash } from "node:crypto";
import type { AuditIssue, AuditResult } from "../agents/continuity.js";
import type { WriteChapterOutput } from "../agents/writer.js";
import type { ChapterMeta } from "../models/chapter.js";
import type { LengthTelemetry } from "../models/length-governance.js";
import { StoryRuntimeClient, StoryRuntimeClientError, type RuntimeChapterArtifactsInput, type RuntimeStoryEventInput } from "../story-runtime/client.js";
import { InkOSReviewAdapter } from "../review-artifacts/adapters.js";
import { StateMutationProposalSchema } from "../review-artifacts/schemas.js";
import { persistChapterArtifacts, type ChapterPersistenceStatus, type ChapterPersistenceUsage } from "./chapter-persistence.js";

export interface ChapterPersistenceInput {
  readonly projectId: string;
  readonly output: WriteChapterOutput;
  readonly status: ChapterPersistenceStatus;
  readonly auditResult: AuditResult;
  readonly finalWordCount: number;
  readonly lengthWarnings: ReadonlyArray<string>;
  readonly lengthTelemetry?: LengthTelemetry;
  readonly degradedIssues: ReadonlyArray<AuditIssue>;
  readonly tokenUsage?: ChapterPersistenceUsage;
  readonly intent: Record<string, unknown>;
  readonly legacy: {
    readonly loadChapterIndex: () => Promise<ReadonlyArray<ChapterMeta>>;
    readonly saveChapter: () => Promise<void>;
    readonly saveTruthFiles: () => Promise<void>;
    readonly saveChapterIndex: (index: ReadonlyArray<ChapterMeta>) => Promise<void>;
    readonly markBookActiveIfNeeded: () => Promise<void>;
    readonly persistAuditDriftGuidance: (issues: ReadonlyArray<AuditIssue>) => Promise<void>;
    readonly snapshotState: () => Promise<void>;
    readonly syncCurrentStateFactHistory: () => Promise<void>;
    readonly logSnapshotStage: () => void;
  };
}

export interface ChapterPersistenceResult {
  readonly entry: ChapterMeta;
  readonly authority: "legacy" | "runtime";
  readonly revision?: number;
  readonly commitId?: string;
}

export interface ChapterPersistencePort {
  persist(input: ChapterPersistenceInput): Promise<ChapterPersistenceResult>;
}

export class LegacyChapterPersistence implements ChapterPersistencePort {
  async persist(input: ChapterPersistenceInput): Promise<ChapterPersistenceResult> {
    const result = await persistChapterArtifacts({
      chapterNumber: input.output.chapterNumber, chapterTitle: input.output.title,
      status: input.status, auditResult: input.auditResult, finalWordCount: input.finalWordCount,
      lengthWarnings: input.lengthWarnings, lengthTelemetry: input.lengthTelemetry,
      degradedIssues: input.degradedIssues, tokenUsage: input.tokenUsage, ...input.legacy,
    });
    return { ...result, authority: "legacy" };
  }
}

export class RuntimeValidationBlockedError extends Error {
  constructor(readonly issues: ReadonlyArray<{ readonly code: string; readonly message: string }>) {
    super(`Story Runtime blocked chapter commit: ${issues.map((issue) => `${issue.code}: ${issue.message}`).join("; ")}`);
    this.name = "RuntimeValidationBlockedError";
  }
}

export class StoryRuntimeChapterPersistence implements ChapterPersistencePort {
  constructor(private readonly client: StoryRuntimeClient, private readonly unifiedReviewEnabled = true) {}

  async persist(input: ChapterPersistenceInput): Promise<ChapterPersistenceResult> {
    const status = await this.client.projectStatus(input.projectId);
    if (status.authority_mode !== "runtime") {
      throw new Error(`Story Runtime project "${input.projectId}" is not Runtime authority.`);
    }
    const artifacts = buildRuntimeArtifacts(input.output, input.auditResult, input.projectId, status.revision);
    const idempotencyKey = `chapter:${input.projectId}:${input.output.chapterNumber}:${artifacts.body_sha256}`;
    if (this.unifiedReviewEnabled) {
      const reviewValidation = await this.client.validateReviews({
        projectId: input.projectId, idempotencyKey: `${idempotencyKey}:review`, expectedRevision: status.revision,
        chapterNumber: input.output.chapterNumber, body: input.output.content, artifacts: [artifacts.review],
      });
      if (reviewValidation.status.status === "blocked" || reviewValidation.status.status === "rejected" || reviewValidation.status.status === "changes_requested") {
        throw new RuntimeValidationBlockedError(reviewValidation.blocking_finding_ids.map((id) => ({ code: "REVIEW_BLOCKED", message: id })));
      }
    }
    const prepared = await this.client.prepareChapter({
      projectId: input.projectId, idempotencyKey, expectedRevision: status.revision,
      chapterNumber: input.output.chapterNumber, intent: input.intent,
    });
    const validated = await this.client.validateChapter({
      projectId: input.projectId, idempotencyKey, expectedRevision: status.revision,
      prepareId: prepared.prepare_id, artifacts,
    });
    const blocking = validated.issues.filter((issue) => issue.severity === "blocking");
    if (blocking.length > 0 || !validated.validation_token) {
      throw new RuntimeValidationBlockedError(blocking);
    }
    const commitInput = {
      projectId: input.projectId, idempotencyKey, expectedRevision: status.revision,
      prepareId: prepared.prepare_id, validationToken: validated.validation_token, artifacts,
    };
    let finalized;
    try {
      finalized = await this.client.commitChapter(commitInput);
    } catch (error) {
      if (!(error instanceof StoryRuntimeClientError) || error.code !== "unavailable") throw error;
      finalized = await this.client.commitChapter(commitInput);
    }
    const now = finalized.finalized_at;
    const entry: ChapterMeta = {
      number: input.output.chapterNumber, title: input.output.title, status: input.status,
      wordCount: input.finalWordCount, createdAt: now, updatedAt: now,
      auditIssues: input.auditResult.issues.map((issue) => `[${issue.severity}] ${issue.description}`),
      lengthWarnings: [...input.lengthWarnings], lengthTelemetry: input.lengthTelemetry,
      tokenUsage: input.tokenUsage,
    };
    return { entry, authority: "runtime", revision: finalized.resulting_revision, commitId: finalized.commit_id };
  }
}

export function buildRuntimeArtifacts(output: WriteChapterOutput, auditResult: AuditResult, projectId = "unbound-project", sourceRevision = 0): RuntimeChapterArtifactsInput {
  const bodyHash = createHash("sha256").update(output.content, "utf8").digest("hex");
  const bodyLength = Array.from(output.content).length;
  const evidence = [{ artifact_id: "chapter-body", start: 0, end: Math.max(1, bodyLength) }];
  const delta = output.runtimeStateDelta;
  const events: RuntimeStoryEventInput[] = [];
  for (const [predicate, value] of Object.entries(delta?.currentStatePatch ?? {})) {
    events.push({ event_type: "fact.upsert", subject: "project", aggregate_type: "fact",
      aggregate_id: `state:${predicate}`, payload: { predicate: `state.${predicate}`, value }, evidence });
  }
  for (const hook of delta?.hookOps.upsert ?? []) {
    events.push({ event_type: "thread.upsert", subject: hook.hookId, aggregate_type: "narrative_thread",
      aggregate_id: hook.hookId, payload: { title: hook.type, status: hook.status,
        introduced_chapter: hook.startChapter, resolved_chapter: hook.status === "resolved" ? output.chapterNumber : null,
        details: hook }, evidence });
  }
  for (const hookId of delta?.hookOps.resolve ?? []) {
    events.push({ event_type: "thread.resolve", subject: hookId, aggregate_type: "narrative_thread",
      aggregate_id: hookId, payload: { title: hookId, status: "resolved", resolved_chapter: output.chapterNumber }, evidence });
  }
  for (const hookId of delta?.hookOps.defer ?? []) {
    events.push({ event_type: "thread.defer", subject: hookId, aggregate_type: "narrative_thread",
      aggregate_id: hookId, payload: { title: hookId, status: "deferred" }, evidence });
  }
  for (const [index, operation] of [...(delta?.subplotOps ?? []), ...(delta?.emotionalArcOps ?? []), ...(delta?.characterMatrixOps ?? [])].entries()) {
    events.push({ event_type: "fact.upsert", subject: "narrative", aggregate_type: "fact",
      aggregate_id: `narrative:${output.chapterNumber}:${index}`, payload: { predicate: `narrative.operation.${index}`, value: operation }, evidence });
  }
  const summaryRow = delta?.chapterSummary;
  const summary = summaryRow
    ? [summaryRow.events, summaryRow.stateChanges, summaryRow.hookActivity].filter(Boolean).join("；") || summaryRow.title
    : output.chapterSummary.trim();
  const review = new InkOSReviewAdapter().fromLegacyAudit({
    projectId, chapterNumber: output.chapterNumber, sourceRevision, body: output.content,
    reviewerKind: "auditor", reviewerVersion: "inkos-1.7", result: auditResult,
  });
  const proposalEvidence = [{
    artifact: "chapter_body" as const, start_offset: 0, end_offset: Math.max(1, bodyLength),
    quoted_hash: bodyHash, locator: `chapter:${output.chapterNumber}:0-${bodyLength}`,
    explanation: "Whole-chapter extraction source.", status: "current" as const,
  }];
  const mutation = (event: RuntimeStoryEventInput) => ({ operation: "update" as const, target_id: event.aggregate_id, value: { ...event.payload } });
  const stateMutationProposal = StateMutationProposalSchema.parse({
    proposal_id: `proposal:${projectId}:${output.chapterNumber}:${bodyHash}`, schema_version: "review-artifacts/v1",
    project_id: projectId, chapter_number: output.chapterNumber, source_revision: sourceRevision, body_sha256: bodyHash,
    entity_mutations: events.filter((event) => event.aggregate_type === "entity").map(mutation),
    relationship_mutations: events.filter((event) => event.aggregate_type === "relationship").map(mutation),
    fact_mutations: events.filter((event) => event.aggregate_type === "fact").map(mutation),
    timeline_events: events.filter((event) => event.aggregate_type === "timeline").map(mutation),
    narrative_thread_mutations: events.filter((event) => event.aggregate_type === "narrative_thread").map(mutation),
    foreshadowing_mutations: [], evidence: proposalEvidence, confidence: 0.8, extraction_source: "observer",
  });
  return {
    chapter_number: output.chapterNumber, title: output.title, body: output.content,
    body_sha256: bodyHash, summary: summary || `${output.title} completed.`, events,
    outline_fulfillment: { planned_node_ids: [], covered_node_ids: [], missed_node_ids: [] },
    review,
    state_mutation_proposal: stateMutationProposal,
    evidence_spans: evidence,
  };
}
