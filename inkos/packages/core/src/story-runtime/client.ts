import type { z } from "zod";
import { randomUUID } from "node:crypto";
import {
  ContextQueryResultSchema,
  ChapterArtifactResultSchema,
  HealthResponseSchema,
  ProjectStatusResponseSchema,
  ProjectCreatedResultSchema,
  FinalizedCommitResultSchema,
  PrepareChapterResultSchema,
  ValidateChapterResultSchema,
  CommitDetailSchema,
  CommitListSchema,
  DiagnosticReportSchema,
  DoctorSchema,
  EventTimelineSchema,
  MigrationStatusSchema,
  ProjectionListSchema,
  RecoveryJobListSchema,
  RecoveryJobSchema,
  ReviewOverviewSchema,
  RuntimeConfigurationStatusSchema,
  RuntimeOverviewSchema,
  STORY_RUNTIME_SCHEMA_VERSION,
  type RuntimeContextResult,
  type RuntimeHealth,
  type RuntimeProjectStatus,
  type FinalizedCommitResult,
  type PrepareChapterResult,
  type ValidateChapterResult,
  type ProjectCreatedResult,
  type ChapterArtifactResult,
  type RuntimeCommitDetail,
  type RuntimeCommitList,
  type RuntimeDiagnosticReport,
  type RuntimeDoctor,
  type RuntimeEventTimeline,
  type RuntimeMigrationStatus,
  type RuntimeProjectionList,
  type RuntimeRecoveryJob,
  type RuntimeRecoveryJobList,
  type RuntimeRecoveryOperation,
  type RuntimeReviewOverview,
  type RuntimeConfigurationStatus,
  type RuntimeOverview,
} from "./schemas.js";
import {
  ChapterReviewArtifactSchema, HumanReviewDecisionSchema, ReviewStatusResultSchema,
  ReviewValidationResultSchema, RevisionResultSchema, RevisionDiffResultSchema,
  type ChapterReviewArtifact, type HumanReviewDecision, type ReviewStatusResult,
  type ReviewValidationResult, type RevisionPlan, type RevisionResult,
  type StateMutationProposal, type RevisionDiffResult,
} from "../review-artifacts/schemas.js";
import { z as zod } from "zod";

export class StoryRuntimeClientError extends Error {
  constructor(
    message: string,
    readonly code: "unavailable" | "http_error" | "malformed_response",
    readonly cause?: unknown,
    readonly status?: number,
    readonly runtimeCode?: string,
    readonly currentRevision?: number,
  ) {
    super(message);
    this.name = "StoryRuntimeClientError";
  }
}

export interface StoryRuntimeClientOptions {
  readonly baseUrl: string;
  readonly timeoutMs?: number;
  readonly apiToken?: string;
  readonly fetchImpl?: typeof fetch;
}

export interface QueryContextInput {
  readonly projectId: string;
  readonly chapterNumber: number;
  readonly intent: string;
  readonly entityIds?: ReadonlyArray<string>;
  readonly maxTokens: number;
  readonly maxItems: number;
  readonly includeRetrievalCandidates?: boolean;
}

export interface RuntimeStoryEventInput {
  readonly event_type: string;
  readonly subject: string;
  readonly aggregate_type: "entity" | "relationship" | "fact" | "timeline" | "narrative_thread" | "project";
  readonly aggregate_id: string;
  readonly payload: Record<string, unknown>;
  readonly evidence: ReadonlyArray<{ readonly artifact_id: string; readonly start: number; readonly end: number }>;
  readonly confidence?: number;
}

export interface RuntimeChapterArtifactsInput {
  readonly chapter_number: number;
  readonly title: string;
  readonly body: string;
  readonly body_sha256: string;
  readonly summary: string;
  readonly events: ReadonlyArray<RuntimeStoryEventInput>;
  readonly outline_fulfillment: Record<string, unknown>;
  readonly review: ChapterReviewArtifact;
  readonly state_mutation_proposal: StateMutationProposal;
  readonly evidence_spans: ReadonlyArray<{ readonly artifact_id: string; readonly start: number; readonly end: number }>;
  readonly agent_trace_id?: string;
}

export class StoryRuntimeClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly apiToken?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: StoryRuntimeClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 3_000;
    this.apiToken = options.apiToken;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
  }

  health(): Promise<RuntimeHealth> {
    return this.request("/api/story-runtime/v1/health", HealthResponseSchema);
  }

  projectStatus(projectId: string): Promise<RuntimeProjectStatus> {
    return this.request(
      `/api/story-runtime/v1/projects/${encodeURIComponent(projectId)}/status`,
      ProjectStatusResponseSchema,
    );
  }

  overview(projectId: string): Promise<RuntimeOverview> {
    return this.request(`/api/story-runtime/v1/projects/${encodeURIComponent(projectId)}/overview`, RuntimeOverviewSchema);
  }

  commits(projectId: string, query: { readonly cursor?: string; readonly limit?: number; readonly chapter?: number; readonly state?: string; readonly fromDate?: string; readonly toDate?: string } = {}): Promise<RuntimeCommitList> {
    return this.request(`${this.projectPath(projectId)}/commits${this.query({ cursor: query.cursor, limit: query.limit, chapter: query.chapter, state: query.state, from_date: query.fromDate, to_date: query.toDate })}`, CommitListSchema);
  }

  commitDetail(projectId: string, commitId: string): Promise<RuntimeCommitDetail> {
    return this.request(`${this.projectPath(projectId)}/commits/${encodeURIComponent(commitId)}`, CommitDetailSchema);
  }

  events(projectId: string, query: { readonly cursor?: string; readonly limit?: number; readonly eventType?: string; readonly aggregate?: string; readonly chapter?: number; readonly revision?: number; readonly view?: "summary" | "evidence" } = {}): Promise<RuntimeEventTimeline> {
    return this.request(`${this.projectPath(projectId)}/events${this.query({ cursor: query.cursor, limit: query.limit, event_type: query.eventType, aggregate: query.aggregate, chapter: query.chapter, revision: query.revision, view: query.view })}`, EventTimelineSchema);
  }

  projections(projectId: string): Promise<RuntimeProjectionList> {
    return this.request(`${this.projectPath(projectId)}/projections`, ProjectionListSchema);
  }

  doctor(projectId: string, deep = false): Promise<RuntimeDoctor> {
    return this.request(`${this.projectPath(projectId)}/doctor?deep=${deep ? "true" : "false"}`, DoctorSchema);
  }

  reviewOverview(projectId: string): Promise<RuntimeReviewOverview> {
    return this.request(`${this.projectPath(projectId)}/reviews/status`, ReviewOverviewSchema);
  }

  migrationStatus(): Promise<RuntimeMigrationStatus> {
    return this.request("/api/story-runtime/v1/migration/status", MigrationStatusSchema);
  }

  configurationStatus(): Promise<RuntimeConfigurationStatus> {
    return this.request("/api/story-runtime/v1/configuration/status", RuntimeConfigurationStatusSchema);
  }

  diagnostics(projectId: string): Promise<RuntimeDiagnosticReport> {
    return this.request(`${this.projectPath(projectId)}/diagnostics`, DiagnosticReportSchema);
  }

  recoveryJobs(projectId: string, cursor?: string, limit = 25): Promise<RuntimeRecoveryJobList> {
    return this.request(`${this.projectPath(projectId)}/recovery-jobs${this.query({ cursor, limit })}`, RecoveryJobListSchema);
  }

  previewRecovery(projectId: string, operation: RuntimeRecoveryOperation, parameters: Record<string, unknown>, actor: string): Promise<RuntimeRecoveryJob> {
    return this.request(`${this.projectPath(projectId)}/recovery-jobs/preview`, RecoveryJobSchema, {
      method: "POST", body: JSON.stringify({ operation, parameters, actor }),
    });
  }

  executeRecovery(projectId: string, jobId: string, actor: string, confirmationToken?: string): Promise<RuntimeRecoveryJob> {
    return this.request(`${this.projectPath(projectId)}/recovery-jobs/${encodeURIComponent(jobId)}/execute`, RecoveryJobSchema, {
      method: "POST", body: JSON.stringify({ actor, confirmation_token: confirmationToken }),
    });
  }

  cancelRecovery(projectId: string, jobId: string, actor: string): Promise<RuntimeRecoveryJob> {
    return this.request(`${this.projectPath(projectId)}/recovery-jobs/${encodeURIComponent(jobId)}/cancel`, RecoveryJobSchema, {
      method: "POST", body: JSON.stringify({ actor }),
    });
  }

  finalizedChapter(projectId: string, chapterNumber: number): Promise<ChapterArtifactResult> {
    return this.request(`/api/story-runtime/v1/projects/${encodeURIComponent(projectId)}/chapters/${chapterNumber}`, ChapterArtifactResultSchema);
  }

  createProject(input: { projectId: string; idempotencyKey: string }): Promise<ProjectCreatedResult> {
    return this.request("/api/story-runtime/v1/projects", ProjectCreatedResultSchema, {
      method: "POST", body: JSON.stringify({ request_id: randomUUID(), idempotency_key: input.idempotencyKey,
        project_id: input.projectId, schema_version: STORY_RUNTIME_SCHEMA_VERSION, authority_mode: "runtime" }),
    });
  }

  queryContext(input: QueryContextInput): Promise<RuntimeContextResult> {
    return this.request("/api/story-runtime/v1/queries/context", ContextQueryResultSchema, {
      method: "POST",
      body: JSON.stringify({
        request_id: randomUUID(),
        project_id: input.projectId,
        schema_version: STORY_RUNTIME_SCHEMA_VERSION,
        chapter_number: input.chapterNumber,
        intent: input.intent,
        entity_ids: input.entityIds ?? [],
        budget: { max_tokens: input.maxTokens, max_items: input.maxItems },
        include_retrieval_candidates: input.includeRetrievalCandidates ?? true,
      }),
    });
  }

  prepareChapter(input: { projectId: string; idempotencyKey: string; expectedRevision: number; chapterNumber: number; intent: Record<string, unknown> }): Promise<PrepareChapterResult> {
    return this.request("/api/story-runtime/v1/chapters/prepare", PrepareChapterResultSchema, {
      method: "POST", body: JSON.stringify({ request_id: randomUUID(), idempotency_key: input.idempotencyKey,
        project_id: input.projectId, schema_version: STORY_RUNTIME_SCHEMA_VERSION, expected_revision: input.expectedRevision,
        chapter_number: input.chapterNumber, intent: input.intent, base_context_revision: input.expectedRevision }),
    });
  }

  validateChapter(input: { projectId: string; idempotencyKey: string; expectedRevision: number; prepareId: string; artifacts: RuntimeChapterArtifactsInput }): Promise<ValidateChapterResult> {
    return this.request("/api/story-runtime/v1/chapters/validate", ValidateChapterResultSchema, {
      method: "POST", body: JSON.stringify({ request_id: randomUUID(), idempotency_key: input.idempotencyKey,
        project_id: input.projectId, schema_version: STORY_RUNTIME_SCHEMA_VERSION, expected_revision: input.expectedRevision,
        prepare_id: input.prepareId, artifacts: input.artifacts, validation_profile: "strict" }),
    });
  }

  commitChapter(input: { projectId: string; idempotencyKey: string; expectedRevision: number; prepareId: string; validationToken: string; artifacts: RuntimeChapterArtifactsInput }): Promise<FinalizedCommitResult> {
    return this.request("/api/story-runtime/v1/chapters/commit", FinalizedCommitResultSchema, {
      method: "POST", body: JSON.stringify({ request_id: randomUUID(), idempotency_key: input.idempotencyKey,
        project_id: input.projectId, schema_version: STORY_RUNTIME_SCHEMA_VERSION, expected_revision: input.expectedRevision,
        prepare_id: input.prepareId, validation_token: input.validationToken, artifacts: input.artifacts }),
    });
  }

  validateReviews(input: { projectId: string; idempotencyKey: string; expectedRevision: number; chapterNumber: number; body: string; artifacts: ReadonlyArray<ChapterReviewArtifact> }): Promise<ReviewValidationResult> {
    return this.request("/api/story-runtime/v1/reviews/validate", ReviewValidationResultSchema, {
      method: "POST", body: JSON.stringify({ request_id: randomUUID(), idempotency_key: input.idempotencyKey,
        project_id: input.projectId, schema_version: STORY_RUNTIME_SCHEMA_VERSION, expected_revision: input.expectedRevision,
        chapter_number: input.chapterNumber, body: input.body, artifacts: input.artifacts }),
    });
  }

  storeReviewDecision(input: { projectId: string; idempotencyKey: string; expectedRevision: number; decision: HumanReviewDecision }): Promise<HumanReviewDecision> {
    return this.request("/api/story-runtime/v1/reviews/decisions", HumanReviewDecisionSchema, {
      method: "POST", body: JSON.stringify({ request_id: randomUUID(), idempotency_key: input.idempotencyKey,
        project_id: input.projectId, schema_version: STORY_RUNTIME_SCHEMA_VERSION, expected_revision: input.expectedRevision,
        decision: input.decision }),
    });
  }

  chapterReviews(projectId: string, chapterNumber: number): Promise<ChapterReviewArtifact[]> {
    return this.request(`/api/story-runtime/v1/projects/${encodeURIComponent(projectId)}/chapters/${chapterNumber}/reviews`, zod.array(ChapterReviewArtifactSchema));
  }

  validateRevision(input: { projectId: string; idempotencyKey: string; expectedRevision: number; chapterNumber: number; originalBody: string; revisedBody: string; plan: RevisionPlan; result: RevisionResult }): Promise<RevisionResult> {
    return this.request("/api/story-runtime/v1/revisions/validate", RevisionResultSchema, {
      method: "POST", body: JSON.stringify({ request_id: randomUUID(), idempotency_key: input.idempotencyKey,
        project_id: input.projectId, schema_version: STORY_RUNTIME_SCHEMA_VERSION, expected_revision: input.expectedRevision,
        chapter_number: input.chapterNumber, original_body: input.originalBody, revised_body: input.revisedBody,
        plan: input.plan, result: input.result }),
    });
  }

  reviewStatus(projectId: string, chapterNumber: number): Promise<ReviewStatusResult> {
    return this.request(`/api/story-runtime/v1/projects/${encodeURIComponent(projectId)}/chapters/${chapterNumber}/review-status`, ReviewStatusResultSchema);
  }

  revisionDiff(projectId: string, chapterNumber: number): Promise<RevisionDiffResult> {
    return this.request(`/api/story-runtime/v1/projects/${encodeURIComponent(projectId)}/chapters/${chapterNumber}/revision-diff`, RevisionDiffResultSchema);
  }

  private projectPath(projectId: string): string {
    return `/api/story-runtime/v1/projects/${encodeURIComponent(projectId)}`;
  }

  private query(values: Readonly<Record<string, string | number | undefined>>): string {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(values)) {
      if (value !== undefined && value !== "") params.set(key, String(value));
    }
    const rendered = params.toString();
    return rendered ? `?${rendered}` : "";
  }

  private async request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      let response: Response;
      try {
        response = await this.fetchImpl(`${this.baseUrl}${path}`, {
          ...init,
          signal: controller.signal,
          headers: {
            accept: "application/json",
            ...(init?.body ? { "content-type": "application/json" } : {}),
            ...(this.apiToken ? { authorization: `Bearer ${this.apiToken}` } : {}),
            ...init?.headers,
          },
        });
      } catch (error) {
        throw new StoryRuntimeClientError(`Story Runtime is unavailable: ${String(error)}`, "unavailable", error);
      }
      if (!response.ok) {
        const text = (await response.text()).slice(0, 2_000);
        let payload: { code?: string; current_revision?: number } = {};
        try { payload = JSON.parse(text) as typeof payload; } catch { /* non-JSON error */ }
        throw new StoryRuntimeClientError(
          `Story Runtime returned HTTP ${response.status}: ${text.slice(0, 500)}`,
          "http_error",
          undefined,
          response.status,
          payload.code,
          payload.current_revision,
        );
      }
      let payload: unknown;
      try {
        payload = await response.json();
      } catch (error) {
        throw new StoryRuntimeClientError("Story Runtime returned non-JSON data", "malformed_response", error);
      }
      const parsed = schema.safeParse(payload);
      if (!parsed.success) {
        throw new StoryRuntimeClientError(
          `Story Runtime response failed schema validation: ${parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; ")}`,
          "malformed_response",
        );
      }
      return parsed.data;
    } finally {
      clearTimeout(timer);
    }
  }
}

/** Dedicated review boundary used by Studio, CLI and TUI. Runtime still never invokes an LLM. */
export class RuntimeReviewClient extends StoryRuntimeClient {}
