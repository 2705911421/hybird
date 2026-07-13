import { z } from "zod";

export const STORY_RUNTIME_SCHEMA_VERSION = "story-runtime/v1" as const;

export const StoryRuntimeModeSchema = z.enum(["legacy", "story-runtime", "shadow"]);
export type StoryRuntimeMode = z.infer<typeof StoryRuntimeModeSchema>;

export const StoryRuntimeConfigSchema = z.object({
  mode: StoryRuntimeModeSchema.default("legacy"),
  baseUrl: z.string().url().default("http://127.0.0.1:47831"),
  apiTokenEnv: z.string().min(1).optional(),
  timeoutMs: z.number().int().min(100).max(60_000).default(3_000),
  maxContextTokens: z.number().int().min(256).max(100_000).default(16_000),
  maxItems: z.number().int().min(1).max(500).default(100),
  fallbackOnUnavailable: z.boolean().default(true),
}).strict().default({ mode: "legacy" });

export type StoryRuntimeConfig = z.infer<typeof StoryRuntimeConfigSchema>;

export const HealthResponseSchema = z.object({
  status: z.enum(["ok", "degraded", "unavailable"]),
  runtime_version: z.string(),
  schema_versions: z.array(z.string()),
  database: z.enum(["ready", "locked", "migration_required", "unavailable"]),
}).strict();

export const ProjectStatusResponseSchema = z.object({
  project_id: z.string(),
  revision: z.number().int().nonnegative(),
  phase: z.string(),
  latest_chapter: z.number().int().nonnegative(),
  projection_health: z.record(z.unknown()),
  schema_version: z.string(),
  active_prepare_ids: z.array(z.string()),
  authority_mode: z.enum(["legacy", "runtime"]),
}).strict();

export const RuntimeStateSchema = z.enum([
  "healthy", "degraded", "unavailable", "version_mismatch",
  "migration_required", "database_locked", "recovery_required",
]);

export const PageInfoSchema = z.object({
  limit: z.number().int().min(1).max(100), has_more: z.boolean(), next_cursor: z.string().nullable(),
}).strict();

export const ImpactStatusSchema = z.object({
  what_happened: z.string(), reads_affected: z.boolean(), writes_affected: z.boolean(),
  retryable: z.boolean(), user_action: z.string(), disabled_actions: z.array(z.string()),
}).strict();

export const IndexHealthSchema = z.object({
  status: z.enum(["ready", "degraded", "unavailable", "rebuilding"]),
  lexical_documents: z.number().int().nonnegative(),
  vector_status: z.enum(["ready", "not_configured", "degraded", "rebuilding"]),
  last_indexed_chapter: z.number().int().nonnegative().nullable(), pending_items: z.number().int().nonnegative(),
}).strict();

export const RuntimeOverviewSchema = z.object({
  project_id: z.string(), runtime_state: RuntimeStateSchema, impact: ImpactStatusSchema,
  current_revision: z.number().int().nonnegative(), latest_chapter: z.number().int().nonnegative(),
  project_phase: z.string(), authority_mode: z.enum(["legacy", "runtime"]),
  active_prepares: z.number().int().nonnegative(), blocked_commits: z.number().int().nonnegative(),
  pending_recovery: z.number().int().nonnegative(), projection_health: z.enum(["ready", "degraded"]),
  index_health: IndexHealthSchema, last_successful_commit: z.string().datetime({ offset: true }).nullable(),
  last_backup: z.string().datetime({ offset: true }).nullable(), schema_version: z.string(), runtime_version: z.string(),
}).strict();

export const CommitSummarySchema = z.object({
  commit_id: z.string(), chapter_number: z.number().int().positive(), state: z.string(), request_id: z.string(),
  idempotency_status: z.enum(["recorded", "replayed", "unknown"]), retryable: z.boolean(),
  resulting_revision: z.number().int().nonnegative().nullable(),
  created_at: z.string().datetime({ offset: true }), updated_at: z.string().datetime({ offset: true }),
}).strict();

export const CommitListSchema = z.object({ items: z.array(CommitSummarySchema), page: PageInfoSchema }).strict();
export const CommitDetailSchema = z.object({
  summary: CommitSummarySchema,
  transitions: z.array(z.object({ from_state: z.string().nullable(), to_state: z.string(), reason: z.string(), resulting_revision: z.number().int().nonnegative().nullable(), created_at: z.string().datetime({ offset: true }) }).strict()),
  artifact_checksum: z.string().nullable(), event_count: z.number().int().nonnegative(),
  projection_results: z.array(z.record(z.unknown())), validation_findings: z.array(z.record(z.unknown())),
  human_decision: z.record(z.unknown()).nullable(), error: z.record(z.unknown()).nullable(), repair_action: z.string().nullable(),
}).strict();

export const EventTimelineSchema = z.object({
  items: z.array(z.object({
    sequence: z.number().int().positive(), event_id: z.string(), event_type: z.string(),
    aggregate_type: z.string().nullable(), aggregate_id: z.string().nullable(),
    chapter_number: z.number().int().positive().nullable(), revision: z.number().int().nonnegative().nullable(),
    summary: z.string(), evidence: z.array(z.record(z.unknown())).nullable(),
    payload_preview: z.record(z.unknown()).nullable(), payload_bytes: z.number().int().nonnegative(),
    payload_truncated: z.boolean(), created_at: z.string().datetime({ offset: true }).nullable(),
  }).strict()), page: PageInfoSchema,
}).strict();

export const ProjectionSchema = z.object({
  projection: z.string(), checkpoint: z.number().int().nonnegative(), revision: z.number().int().nonnegative(),
  hash: z.string().nullable(), status: z.string(), retry_count: z.number().int().nonnegative(),
  last_error: z.string().nullable(), replay_capability: z.enum(["direct", "confirmation_required", "blocked"]),
  updated_at: z.string().datetime({ offset: true }),
}).strict();
export const ProjectionListSchema = z.object({ items: z.array(ProjectionSchema) }).strict();

export const DoctorSchema = z.object({
  project_id: z.string(), revision: z.number().int().nonnegative(), status: z.enum(["ok", "warning", "blocked"]),
  checks: z.array(z.object({ code: z.string(), status: z.enum(["pass", "warning", "fail", "blocked"]),
    message: z.string(), repair: z.string().nullable(), retryable: z.boolean(), requires_confirmation: z.boolean() }).strict()),
}).strict();

export const MigrationStatusSchema = z.object({
  status: z.enum(["current", "required", "in_progress", "interrupted", "blocked"]),
  current_version: z.number().int().nonnegative(), target_version: z.number().int().nonnegative(),
  pending_versions: z.array(z.number().int().nonnegative()), resume_capability: z.enum(["not_needed", "confirmation_required", "blocked"]),
}).strict();
export const RuntimeConfigurationStatusSchema = z.object({
  writes_enabled: z.boolean(), unified_review_enabled: z.boolean(), token_configured: z.boolean(),
  projection_output_configured: z.boolean(), observability_enabled: z.boolean(), recovery_enabled: z.boolean(),
  busy_timeout_ms: z.number().int().positive(), secret_values_exposed: z.literal(false),
}).strict();
export const ReviewOverviewSchema = z.object({
  project_id: z.string(), total_artifacts: z.number().int().nonnegative(), open_findings: z.number().int().nonnegative(),
  blocking_findings: z.number().int().nonnegative(), latest_decision: z.string().nullable(),
  latest_decision_at: z.string().datetime({ offset: true }).nullable(),
}).strict();

export const RecoveryOperationSchema = z.enum([
  "retry_outbox_item", "rebuild_lexical_index", "rebuild_vector_index", "replay_core_projection",
  "abort_prepared_commit", "restore_snapshot", "clear_retry_queue", "resume_interrupted_migration",
]);
export const RecoveryJobSchema: z.ZodTypeAny = z.object({
  job_id: z.string(), project_id: z.string(), operation: RecoveryOperationSchema,
  state: z.enum(["previewed", "running", "completed", "failed", "cancelled", "blocked"]),
  requires_confirmation: z.boolean(), confirmation_token: z.string().nullable(), preview: z.record(z.unknown()),
  result: z.record(z.unknown()).nullable(), progress: z.number().int().min(0).max(100), cancellable: z.boolean(),
  error: z.record(z.unknown()).nullable(), created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }), completed_at: z.string().datetime({ offset: true }).nullable(),
  audit_trail: z.array(z.record(z.unknown())),
}).strict();
export const RecoveryJobListSchema = z.object({ items: z.array(RecoveryJobSchema), page: PageInfoSchema }).strict();
export const DiagnosticReportSchema = z.object({
  generated_at: z.string().datetime({ offset: true }), project_id: z.string(), versions: z.record(z.unknown()),
  non_sensitive_config: z.record(z.unknown()), commit_status: z.record(z.unknown()),
  projection_status: z.array(ProjectionSchema), doctor: DoctorSchema,
  recent_errors: z.array(z.record(z.unknown())), checksums: z.array(z.record(z.unknown())),
}).strict();

export const CommitStateSchema = z.enum([
  "PREPARED", "VALIDATED", "PERSISTING", "COMMITTED", "PROJECTING", "FINALIZED",
  "REJECTED", "ABORTED", "RECOVERY_REQUIRED",
]);

export const ProjectCreatedResultSchema = z.object({
  project_id: z.string(), authority_mode: z.literal("runtime"),
  revision: z.number().int().nonnegative(), replayed: z.boolean(),
}).strict();

export const PrepareChapterResultSchema = z.object({
  commit_id: z.string().uuid(), prepare_id: z.string().uuid(), project_id: z.string(),
  chapter_number: z.number().int().positive(), state: CommitStateSchema,
  current_revision: z.number().int().nonnegative(), expected_revision: z.number().int().nonnegative(),
  required_artifact_schema: z.string(), replayed: z.boolean(),
}).strict();

export const ValidationIssueSchema = z.object({
  severity: z.enum(["blocking", "warning", "informational"]), code: z.string(),
  message: z.string(), event_ordinal: z.number().int().nonnegative().nullable(),
}).strict();

export const ValidateChapterResultSchema = z.object({
  commit_id: z.string().uuid(), project_id: z.string(), chapter_number: z.number().int().positive(),
  state: CommitStateSchema, artifact_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  validation_token: z.string().nullable(), issues: z.array(ValidationIssueSchema), replayed: z.boolean(),
}).strict();

export const FinalizedCommitResultSchema = z.object({
  commit_id: z.string().uuid(), project_id: z.string(), chapter_number: z.number().int().positive(),
  state: z.literal("FINALIZED"), expected_revision: z.number().int().nonnegative(),
  resulting_revision: z.number().int().positive(), body_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  artifact_sha256: z.string().regex(/^[a-f0-9]{64}$/), event_count: z.number().int().nonnegative(),
  projection_hash: z.string().regex(/^[a-f0-9]{64}$/), finalized_at: z.string().datetime({ offset: true }),
  replayed: z.boolean(),
}).strict();

export const ChapterArtifactResultSchema = z.object({
  project_id: z.string(), chapter_number: z.number().int().positive(), revision: z.number().int().positive(),
  commit_id: z.string().uuid(), title: z.string(), body: z.string(), summary: z.string(),
  body_sha256: z.string().regex(/^[a-f0-9]{64}$/), artifact_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  finalized_at: z.string().datetime({ offset: true }),
}).strict();

export const ContextLayerNameSchema = z.enum([
  "hard_constraints",
  "plot_commitments",
  "relevant_memory",
  "recent_narrative",
  "style_guidance",
]);
export type ContextLayerName = z.infer<typeof ContextLayerNameSchema>;

export const ContextItemSchema = z.object({
  item_id: z.string().min(1),
  layer: ContextLayerNameSchema,
  content: z.string(),
  source: z.object({
    kind: z.enum(["structured_query", "rag", "chapter_summary", "request_intent"]),
    id: z.string().min(1),
  }).strict(),
  confidence: z.number().min(0).max(1),
  updated_at: z.string().datetime({ offset: true }),
  importance: z.number().int().min(0).max(100),
  trust: z.enum(["trusted", "untrusted_content"]),
  subject: z.string().nullable(),
  predicate: z.string().nullable(),
}).strict();

export const ContextLayersSchema = z.object({
  hard_constraints: z.array(ContextItemSchema),
  plot_commitments: z.array(ContextItemSchema),
  relevant_memory: z.array(ContextItemSchema),
  recent_narrative: z.array(ContextItemSchema),
  style_guidance: z.array(ContextItemSchema),
}).strict();

export const ContextConflictSchema = z.object({
  conflict_id: z.string(),
  subject: z.string(),
  predicate: z.string(),
  item_ids: z.array(z.string()).min(2),
  values: z.array(z.unknown()).min(2),
  message: z.string(),
}).strict();

export const ContextQueryResultSchema = z.object({
  request_id: z.string().uuid(),
  project_id: z.string(),
  revision: z.number().int().nonnegative(),
  authoritative_facts: z.array(z.unknown()),
  retrieval_candidates: z.array(z.unknown()),
  untrusted_materials: z.array(z.record(z.unknown())),
  layers: ContextLayersSchema,
  conflicts: z.array(ContextConflictSchema),
  trace: z.object({
    budget_used: z.number().int().nonnegative(),
    selected_source_ids: z.array(z.string()),
  }).strict(),
}).strict();

export const LegacyMigrationStageSchema = z.enum([
  "DISCOVERED", "SCANNED", "MAPPED", "VALIDATED", "AWAITING_DECISIONS", "READY",
  "IMPORTING", "VERIFYING", "COMPLETED", "PAUSED", "FAILED", "ROLLED_BACK", "QUARANTINED",
]);
const MigrationConflictSchema = z.object({
  conflict_id: z.string(), type: z.string(), severity: z.string(), blocking: z.boolean(),
  sources: z.array(z.record(z.unknown())), candidates: z.array(z.record(z.unknown())),
  evidence: z.record(z.unknown()), recommended_decision: z.string(),
  user_decision: z.record(z.unknown()).nullable(), resolution_audit: z.array(z.record(z.unknown())),
}).strict();
export const LegacyMigrationJobSchema = z.object({
  migration_job_id: z.string().uuid(), source_type: z.enum(["inkos", "webnovel-writer", "hybrid", "unknown"]),
  source_path_fingerprint: z.string().regex(/^[a-f0-9]{64}$/), target_project_id: z.string(),
  mapping_version: z.string(), cir_version: z.literal("canonical-import/v1"), current_stage: LegacyMigrationStageSchema,
  progress: z.number().int().min(0).max(100), warnings: z.array(z.record(z.unknown())),
  conflicts: z.array(MigrationConflictSchema), decisions: z.record(z.unknown()), checkpoints: z.array(z.record(z.unknown())),
  audit_log: z.array(z.record(z.unknown())), discovery: z.record(z.unknown()), source_checksum_manifest: z.array(z.record(z.unknown())),
  target_snapshot: z.record(z.unknown()).nullable(), cir: z.record(z.unknown()).nullable(), dry_run: z.record(z.unknown()).nullable(),
  verification: z.record(z.unknown()).nullable(), cutover_confirmed: z.boolean(), reused: z.boolean(),
}).strict();
export const LegacyMigrationJobListSchema = z.object({ items: z.array(LegacyMigrationJobSchema) }).strict();

export type RuntimeHealth = z.infer<typeof HealthResponseSchema>;
export type RuntimeProjectStatus = z.infer<typeof ProjectStatusResponseSchema>;
export type RuntimeOverview = z.infer<typeof RuntimeOverviewSchema>;
export type RuntimeCommitList = z.infer<typeof CommitListSchema>;
export type RuntimeCommitDetail = z.infer<typeof CommitDetailSchema>;
export type RuntimeEventTimeline = z.infer<typeof EventTimelineSchema>;
export type RuntimeProjectionList = z.infer<typeof ProjectionListSchema>;
export type RuntimeDoctor = z.infer<typeof DoctorSchema>;
export type RuntimeMigrationStatus = z.infer<typeof MigrationStatusSchema>;
export type RuntimeConfigurationStatus = z.infer<typeof RuntimeConfigurationStatusSchema>;
export type RuntimeReviewOverview = z.infer<typeof ReviewOverviewSchema>;
export type RuntimeRecoveryJob = z.infer<typeof RecoveryJobSchema>;
export type RuntimeRecoveryJobList = z.infer<typeof RecoveryJobListSchema>;
export type RuntimeDiagnosticReport = z.infer<typeof DiagnosticReportSchema>;
export type RuntimeRecoveryOperation = z.infer<typeof RecoveryOperationSchema>;
export type RuntimeContextResult = z.infer<typeof ContextQueryResultSchema>;
export type RuntimeContextItem = z.infer<typeof ContextItemSchema>;
export type RuntimeContextConflict = z.infer<typeof ContextConflictSchema>;
export type PrepareChapterResult = z.infer<typeof PrepareChapterResultSchema>;
export type ValidateChapterResult = z.infer<typeof ValidateChapterResultSchema>;
export type FinalizedCommitResult = z.infer<typeof FinalizedCommitResultSchema>;
export type ProjectCreatedResult = z.infer<typeof ProjectCreatedResultSchema>;
export type ChapterArtifactResult = z.infer<typeof ChapterArtifactResultSchema>;
export type LegacyMigrationJob = z.infer<typeof LegacyMigrationJobSchema>;
export type LegacyMigrationJobList = z.infer<typeof LegacyMigrationJobListSchema>;
