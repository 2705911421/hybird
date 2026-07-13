from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from . import SCHEMA_VERSION


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorResponse(StrictModel):
    code: str
    message: str
    retryable: bool
    current_revision: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded", "unavailable"]
    runtime_version: str
    schema_versions: list[str]
    database: Literal["ready", "locked", "migration_required", "unavailable"]


class ProjectStatusResponse(StrictModel):
    project_id: str
    revision: int = Field(ge=0)
    phase: str
    latest_chapter: int = Field(ge=0)
    projection_health: dict[str, Any]
    schema_version: str
    active_prepare_ids: list[str] = Field(default_factory=list)
    authority_mode: Literal["legacy", "runtime"] = "legacy"


RuntimeState = Literal[
    "healthy", "degraded", "unavailable", "version_mismatch",
    "migration_required", "database_locked", "recovery_required",
]


class PageInfo(StrictModel):
    limit: int = Field(ge=1, le=100)
    has_more: bool
    next_cursor: str | None = None


class ImpactStatus(StrictModel):
    what_happened: str
    reads_affected: bool
    writes_affected: bool
    retryable: bool
    user_action: str
    disabled_actions: list[str] = Field(default_factory=list)


class IndexHealth(StrictModel):
    status: Literal["ready", "degraded", "unavailable", "rebuilding"]
    lexical_documents: int = Field(ge=0)
    vector_status: Literal["ready", "not_configured", "degraded", "rebuilding"]
    last_indexed_chapter: int | None = Field(default=None, ge=0)
    pending_items: int = Field(ge=0)


class RuntimeOverview(StrictModel):
    project_id: str
    runtime_state: RuntimeState
    impact: ImpactStatus
    current_revision: int = Field(ge=0)
    latest_chapter: int = Field(ge=0)
    project_phase: str
    authority_mode: Literal["legacy", "runtime"]
    active_prepares: int = Field(ge=0)
    blocked_commits: int = Field(ge=0)
    pending_recovery: int = Field(ge=0)
    projection_health: Literal["ready", "degraded"]
    index_health: IndexHealth
    last_successful_commit: datetime | None = None
    last_backup: datetime | None = None
    schema_version: str
    runtime_version: str


class CommitSummary(StrictModel):
    commit_id: str
    chapter_number: int = Field(ge=1)
    state: str
    request_id: str
    idempotency_status: Literal["recorded", "replayed", "unknown"]
    retryable: bool
    resulting_revision: int | None = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime


class CommitListResult(StrictModel):
    items: list[CommitSummary]
    page: PageInfo


class CommitTransitionView(StrictModel):
    from_state: str | None
    to_state: str
    reason: str
    resulting_revision: int | None = Field(default=None, ge=0)
    created_at: datetime


class CommitDetail(StrictModel):
    summary: CommitSummary
    transitions: list[CommitTransitionView]
    artifact_checksum: str | None
    event_count: int = Field(ge=0)
    projection_results: list[dict[str, Any]]
    validation_findings: list[dict[str, Any]]
    human_decision: dict[str, Any] | None
    error: dict[str, Any] | None
    repair_action: str | None


class EventTimelineItem(StrictModel):
    sequence: int = Field(ge=1)
    event_id: str
    event_type: str
    aggregate_type: str | None
    aggregate_id: str | None
    chapter_number: int | None = Field(default=None, ge=1)
    revision: int | None = Field(default=None, ge=0)
    summary: str
    evidence: list[dict[str, Any]] | None = None
    payload_preview: dict[str, Any] | None = None
    payload_bytes: int = Field(ge=0)
    payload_truncated: bool
    created_at: datetime | None


class EventTimelineResult(StrictModel):
    items: list[EventTimelineItem]
    page: PageInfo


class ProjectionView(StrictModel):
    projection: str
    checkpoint: int = Field(ge=0)
    revision: int = Field(ge=0)
    hash: str | None
    status: str
    retry_count: int = Field(ge=0)
    last_error: str | None
    replay_capability: Literal["direct", "confirmation_required", "blocked"]
    updated_at: datetime


class ProjectionListResult(StrictModel):
    items: list[ProjectionView]


class MigrationStatus(StrictModel):
    status: Literal["current", "required", "in_progress", "interrupted", "blocked"]
    current_version: int = Field(ge=0)
    target_version: int = Field(ge=0)
    pending_versions: list[int]
    resume_capability: Literal["not_needed", "confirmation_required", "blocked"]


class RuntimeConfigurationStatus(StrictModel):
    writes_enabled: bool
    unified_review_enabled: bool
    token_configured: bool
    projection_output_configured: bool
    observability_enabled: bool
    recovery_enabled: bool
    busy_timeout_ms: int = Field(ge=1)
    secret_values_exposed: Literal[False] = False


RecoveryOperation = Literal[
    "retry_outbox_item", "rebuild_lexical_index", "rebuild_vector_index",
    "replay_core_projection", "abort_prepared_commit", "restore_snapshot",
    "clear_retry_queue", "resume_interrupted_migration",
]


class RecoveryPreviewRequest(StrictModel):
    operation: RecoveryOperation
    parameters: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(min_length=1, max_length=100)


class RecoveryExecuteRequest(StrictModel):
    confirmation_token: str | None = Field(default=None, min_length=20, max_length=200)
    actor: str = Field(min_length=1, max_length=100)


class RecoveryJob(StrictModel):
    job_id: str
    project_id: str
    operation: RecoveryOperation
    state: Literal["previewed", "running", "completed", "failed", "cancelled", "blocked"]
    requires_confirmation: bool
    confirmation_token: str | None = None
    preview: dict[str, Any]
    result: dict[str, Any] | None
    progress: int = Field(ge=0, le=100)
    cancellable: bool
    error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)


class RecoveryJobListResult(StrictModel):
    items: list[RecoveryJob]
    page: PageInfo


class DiagnosticReport(StrictModel):
    generated_at: datetime
    project_id: str
    versions: dict[str, Any]
    non_sensitive_config: dict[str, Any]
    commit_status: dict[str, Any]
    projection_status: list[ProjectionView]
    doctor: "DoctorResult"
    recent_errors: list[dict[str, Any]]
    checksums: list[dict[str, Any]]


class ReviewOverview(StrictModel):
    project_id: str
    total_artifacts: int = Field(ge=0)
    open_findings: int = Field(ge=0)
    blocking_findings: int = Field(ge=0)
    latest_decision: str | None
    latest_decision_at: datetime | None


class QueryBudget(StrictModel):
    max_tokens: int = Field(ge=256, le=100_000)
    max_items: int = Field(ge=1, le=500)


class QueryContextRequest(StrictModel):
    request_id: UUID
    project_id: str = Field(min_length=1, max_length=128)
    schema_version: Literal[SCHEMA_VERSION]
    chapter_number: int = Field(ge=1)
    intent: str = Field(min_length=1, max_length=10_000)
    entity_ids: list[str] = Field(default_factory=list)
    budget: QueryBudget
    include_retrieval_candidates: bool = True


class AuthoritativeFact(StrictModel):
    fact_id: str
    subject: str
    predicate: str
    value: Any
    valid_from_revision: int = Field(ge=0)
    valid_to_revision: int | None = Field(default=None, ge=0)
    source: str
    confidence: float = Field(ge=0, le=1)
    updated_at: datetime


class RetrievalCandidate(StrictModel):
    source_id: str
    text: str
    score: float
    trust: Literal["untrusted_content"] = "untrusted_content"
    updated_at: datetime


ContextLayerName = Literal[
    "hard_constraints",
    "plot_commitments",
    "relevant_memory",
    "recent_narrative",
    "style_guidance",
]


class ContextItemSource(StrictModel):
    kind: Literal["structured_query", "rag", "chapter_summary", "request_intent"]
    id: str


class ContextItem(StrictModel):
    item_id: str
    layer: ContextLayerName
    content: str
    source: ContextItemSource
    confidence: float = Field(ge=0, le=1)
    updated_at: datetime
    importance: int = Field(ge=0, le=100)
    trust: Literal["trusted", "untrusted_content"]
    subject: str | None = None
    predicate: str | None = None


class ContextLayers(StrictModel):
    hard_constraints: list[ContextItem] = Field(default_factory=list)
    plot_commitments: list[ContextItem] = Field(default_factory=list)
    relevant_memory: list[ContextItem] = Field(default_factory=list)
    recent_narrative: list[ContextItem] = Field(default_factory=list)
    style_guidance: list[ContextItem] = Field(default_factory=list)


class ContextConflict(StrictModel):
    conflict_id: str
    subject: str
    predicate: str
    item_ids: list[str] = Field(min_length=2)
    values: list[Any] = Field(min_length=2)
    message: str


class QueryTrace(StrictModel):
    budget_used: int = Field(ge=0)
    selected_source_ids: list[str]


class ContextQueryResult(StrictModel):
    request_id: UUID
    project_id: str
    revision: int = Field(ge=0)
    authoritative_facts: list[AuthoritativeFact]
    retrieval_candidates: list[RetrievalCandidate]
    untrusted_materials: list[dict[str, Any]]
    layers: ContextLayers
    conflicts: list[ContextConflict]
    trace: QueryTrace


class EntityView(StrictModel):
    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, Any]
    history: list[dict[str, Any]] = Field(default_factory=list)


class EntityResult(StrictModel):
    project_id: str
    revision: int = Field(ge=0)
    entity: EntityView


class DoctorCheck(StrictModel):
    code: str
    status: Literal["pass", "warning", "fail", "blocked"]
    message: str
    repair: str | None
    retryable: bool = False
    requires_confirmation: bool = False


class DoctorResult(StrictModel):
    project_id: str
    revision: int = Field(ge=0)
    status: Literal["ok", "warning", "blocked"]
    checks: list[DoctorCheck]


class CommonWriteContext(StrictModel):
    request_id: UUID
    idempotency_key: str = Field(min_length=16, max_length=200)
    project_id: str = Field(min_length=1, max_length=128)
    schema_version: Literal[SCHEMA_VERSION]
    expected_revision: int = Field(ge=0)


class StoryEventInput(StrictModel):
    event_id: str | None = None
    event_type: str
    subject: str
    aggregate_type: Literal["entity", "relationship", "fact", "timeline", "narrative_thread", "project"] = "fact"
    aggregate_id: str | None = None
    payload: dict[str, Any]
    evidence: list[dict[str, Any]]
    confidence: float = Field(default=1.0, ge=0, le=1)


class ChapterArtifacts(StrictModel):
    chapter_number: int = Field(ge=1)
    title: str
    body: str
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    events: list[StoryEventInput]
    outline_fulfillment: dict[str, Any]
    summary: str = ""
    review: dict[str, Any] | None = None
    state_mutation_proposal: dict[str, Any] = Field(default_factory=dict)
    evidence_spans: list[dict[str, Any]] = Field(default_factory=list)
    agent_trace_id: str | None = None


class PrepareChapterRequest(CommonWriteContext):
    chapter_number: int = Field(ge=1)
    intent: dict[str, Any]
    base_context_revision: int = Field(ge=0)
    expires_in_seconds: int = Field(default=3600, ge=60, le=86_400)


class ValidateChapterArtifactsRequest(CommonWriteContext):
    prepare_id: UUID
    artifacts: ChapterArtifacts
    validation_profile: str = "strict"


class CommitChapterRequest(CommonWriteContext):
    prepare_id: UUID
    validation_token: str = Field(min_length=16, max_length=500)
    artifacts: ChapterArtifacts


class AppendEventsRequest(CommonWriteContext):
    events: list[StoryEventInput] = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=500)
    admin_scope: Literal["story-runtime.events.append"] | None = None


class TypedDiffCommandRequest(CommonWriteContext):
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
    events: list[StoryEventInput] = Field(min_length=1, max_length=100)


class ReplayProjectionsRequest(CommonWriteContext):
    projection_names: list[str] = Field(min_length=1)
    from_event_sequence: int = Field(ge=0)
    to_event_sequence: int | None = Field(default=None, ge=0)
    verify_only: bool
    target_revision: int | None = Field(default=None, ge=0)
    expected_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CreateProjectRequest(StrictModel):
    request_id: UUID
    idempotency_key: str = Field(min_length=16, max_length=200)
    project_id: str = Field(min_length=1, max_length=128)
    schema_version: Literal[SCHEMA_VERSION]
    authority_mode: Literal["runtime"] = "runtime"


class ProjectCreatedResult(StrictModel):
    project_id: str
    authority_mode: Literal["runtime"]
    revision: int = Field(ge=0)
    replayed: bool = False


CommitState = Literal[
    "PREPARED", "VALIDATED", "PERSISTING", "COMMITTED", "PROJECTING", "FINALIZED",
    "REJECTED", "ABORTED", "RECOVERY_REQUIRED",
]


class PrepareChapterResult(StrictModel):
    commit_id: UUID
    prepare_id: UUID
    project_id: str
    chapter_number: int
    state: CommitState
    current_revision: int
    expected_revision: int
    required_artifact_schema: str = "chapter-artifacts.json"
    replayed: bool = False


class ValidationIssue(StrictModel):
    severity: Literal["blocking", "warning", "informational"]
    code: str
    message: str
    event_ordinal: int | None = None


class ValidateChapterResult(StrictModel):
    commit_id: UUID
    project_id: str
    chapter_number: int
    state: CommitState
    artifact_sha256: str
    validation_token: str | None = None
    issues: list[ValidationIssue]
    replayed: bool = False


class FinalizedCommitResult(StrictModel):
    commit_id: UUID
    project_id: str
    chapter_number: int
    state: Literal["FINALIZED"]
    expected_revision: int
    resulting_revision: int
    body_sha256: str
    artifact_sha256: str
    event_count: int
    projection_hash: str
    finalized_at: datetime
    replayed: bool = False


class ChapterArtifactResult(StrictModel):
    project_id: str
    chapter_number: int = Field(ge=1)
    revision: int = Field(ge=1)
    commit_id: UUID
    title: str
    body: str
    summary: str
    body_sha256: str
    artifact_sha256: str
    finalized_at: datetime


class ReplayProjectionsResult(StrictModel):
    replay_job_id: UUID
    project_id: str
    state: Literal["FINALIZED", "MISMATCH"]
    verify_only: bool
    projection_names: list[str]
    resulting_hash: str
    expected_hash: str | None = None
    matched: bool
    event_count: int


class AppendEventsResult(StrictModel):
    request_id: UUID
    project_id: str
    status: Literal["completed"] = "completed"
    revision: int = Field(ge=0)
    event_count: int = Field(ge=1)
    projection_hash: str
    replayed: bool = False


class CommitRecoveryRequest(StrictModel):
    request_id: UUID
    project_id: str = Field(min_length=1, max_length=128)
    commit_id: UUID
    idempotency_key: str = Field(min_length=16, max_length=200)
    action: Literal["recover", "abort"]
    reason: str = Field(min_length=1, max_length=500)
    admin_scope: Literal["story-runtime.commits.recover"] | None = None


class CommitRecoveryResult(StrictModel):
    request_id: UUID
    project_id: str
    commit_id: UUID
    state: CommitState
    resulting_revision: int | None = None
    repair_action: str
    replayed: bool = False


class OutboxRunRequest(StrictModel):
    request_id: UUID
    project_id: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=100, ge=1, le=1000)
    retry_failed: bool = True
    admin_scope: Literal["story-runtime.outbox.run"] | None = None


class OutboxRunResult(StrictModel):
    request_id: UUID
    claimed: int
    completed: int
    failed: int
    pending: int


class MigrateProjectRequest(CommonWriteContext):
    source_kind: Literal["inkos-1.7", "webnovel-writer-6.2", "story-runtime-snapshot"]
    source_path: str = Field(min_length=1)
    target_schema_version: Literal[SCHEMA_VERSION]
    dry_run: bool
    resume_job_id: UUID | None = None


class ExportSnapshotRequest(CommonWriteContext):
    format: Literal["json", "markdown-bundle"]
    include_chapter_bodies: bool
    revision: int | None = Field(default=None, ge=0)


MigrationStage = Literal[
    "DISCOVERED", "SCANNED", "MAPPED", "VALIDATED", "AWAITING_DECISIONS", "READY",
    "IMPORTING", "VERIFYING", "COMPLETED", "PAUSED", "FAILED", "ROLLED_BACK", "QUARANTINED",
]


class CreateMigrationJobRequest(StrictModel):
    source_path: str = Field(min_length=1, max_length=4096)
    target_project_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    source_type: Literal["auto", "inkos", "webnovel-writer"] = "auto"
    mapping_version: str = Field(default="phase7-map-v1", min_length=1, max_length=64)
    create_new_version: bool = False


class MigrationDecision(StrictModel):
    conflict_id: str = Field(min_length=1, max_length=200)
    decision: Literal["choose_candidate", "merge", "ignore", "quarantine"]
    candidate_id: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=2000)


class MigrationDecisionsRequest(StrictModel):
    decisions: list[MigrationDecision]


class MigrationActionRequest(StrictModel):
    actor: str = Field(default="local-operator", min_length=1, max_length=200)
    confirmation: str | None = Field(default=None, max_length=200)


class MigrationJobResult(StrictModel):
    migration_job_id: str
    source_type: Literal["inkos", "webnovel-writer", "hybrid", "unknown"]
    source_path_fingerprint: str
    target_project_id: str
    mapping_version: str
    cir_version: str
    current_stage: MigrationStage
    progress: int = Field(ge=0, le=100)
    warnings: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    decisions: dict[str, Any]
    checkpoints: list[dict[str, Any]]
    audit_log: list[dict[str, Any]]
    discovery: dict[str, Any]
    source_checksum_manifest: list[dict[str, Any]]
    target_snapshot: dict[str, Any] | None = None
    cir: dict[str, Any] | None = None
    dry_run: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    cutover_confirmed: bool = False
    reused: bool = False


class MigrationJobListResult(StrictModel):
    items: list[MigrationJobResult]


REVIEW_SCHEMA_VERSION = "review-artifacts/v1"


class EvidenceSpan(StrictModel):
    artifact: Literal["chapter_body"]
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    quoted_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    locator: str = Field(min_length=1, max_length=500)
    explanation: str = Field(max_length=2000)
    status: Literal["current", "stale", "remapped"]


class ReviewFinding(StrictModel):
    finding_id: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=100)
    severity: Literal["info", "minor", "major", "critical"]
    blocking: bool
    message: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(max_length=8000)
    evidence_spans: list[EvidenceSpan] = Field(max_length=100)
    affected_entities: list[str] = Field(max_length=100)
    affected_facts: list[str] = Field(max_length=100)
    proposed_resolution: str | None = Field(default=None, max_length=8000)
    confidence: float = Field(ge=0, le=1)
    source: Literal["runtime_validator", "llm_reviewer", "human", "legacy_adapter"]
    deterministic_rule_id: str | None = Field(default=None, max_length=128)
    supersedes: list[str] = Field(max_length=100)
    status: Literal["open", "accepted", "rejected", "resolved", "superseded", "stale"]


class ChapterReviewArtifact(StrictModel):
    artifact_id: str = Field(min_length=1, max_length=128)
    schema_version: Literal["review-artifacts/v1"]
    project_id: str = Field(min_length=1, max_length=128)
    chapter_number: int = Field(ge=1)
    source_revision: int = Field(ge=0)
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_kind: Literal["auditor", "continuity_auditor", "state_validator", "reviewer", "runtime_validator", "human", "legacy_adapter"]
    reviewer_version: str = Field(min_length=1, max_length=100)
    generated_at: datetime
    dimensions: dict[str, float]
    findings: list[ReviewFinding] = Field(max_length=1000)
    summary: str = Field(max_length=16000)
    recommended_action: Literal["approve", "revise", "human_review", "reject"]
    model_metadata: dict[str, str | int | float | bool | None]
    prompt_template_version: str = Field(min_length=1, max_length=100)


class ArtifactMutation(StrictModel):
    operation: Literal["create", "update", "delete", "resolve", "reopen"]
    target_id: str = Field(min_length=1, max_length=128)
    value: dict[str, Any]


class StateMutationProposal(StrictModel):
    proposal_id: str = Field(min_length=1, max_length=128)
    schema_version: Literal["review-artifacts/v1"]
    project_id: str
    chapter_number: int = Field(ge=1)
    source_revision: int = Field(ge=0)
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entity_mutations: list[ArtifactMutation]
    relationship_mutations: list[ArtifactMutation]
    fact_mutations: list[ArtifactMutation]
    timeline_events: list[ArtifactMutation]
    narrative_thread_mutations: list[ArtifactMutation]
    foreshadowing_mutations: list[ArtifactMutation]
    evidence: list[EvidenceSpan]
    confidence: float = Field(ge=0, le=1)
    extraction_source: Literal["observer", "reflector", "chapter_analyzer", "legacy_adapter"]


class RevisionPlan(StrictModel):
    plan_id: str
    schema_version: Literal["review-artifacts/v1"]
    project_id: str
    chapter_number: int = Field(ge=1)
    source_revision: int = Field(ge=0)
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    finding_ids: list[str]
    allowed_scopes: list[str]
    forbidden_hard_facts: list[str]
    locked_text: list[EvidenceSpan]
    target_outcomes: list[str]
    requires_reaudit: bool


class ChangedSpan(StrictModel):
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    replacement_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class RevisionResult(StrictModel):
    result_id: str
    schema_version: Literal["review-artifacts/v1"]
    project_id: str
    chapter_number: int = Field(ge=1)
    source_revision: int = Field(ge=0)
    original_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revised_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolved_finding_ids: list[str]
    unresolved_finding_ids: list[str]
    newly_introduced_risks: list[str]
    changed_spans: list[ChangedSpan]
    revision_rationale: str = Field(max_length=16000)


class HumanReviewDecision(StrictModel):
    decision_id: str
    schema_version: Literal["review-artifacts/v1"]
    project_id: str
    chapter_number: int = Field(ge=1)
    reviewer: str
    decision: Literal["approve", "reject", "request_changes"]
    finding_decisions: dict[str, Literal["accept", "reject", "request_changes"]]
    comment: str = Field(max_length=16000)
    timestamp: datetime
    source_revision: int = Field(ge=0)


class ValidateReviewsRequest(CommonWriteContext):
    chapter_number: int = Field(ge=1)
    body: str = Field(max_length=2_000_000)
    artifacts: list[ChapterReviewArtifact] = Field(min_length=1, max_length=50)


class StoreReviewDecisionRequest(CommonWriteContext):
    decision: HumanReviewDecision


class ValidateRevisionRequest(CommonWriteContext):
    chapter_number: int = Field(ge=1)
    original_body: str = Field(max_length=2_000_000)
    revised_body: str = Field(max_length=2_000_000)
    plan: RevisionPlan
    result: RevisionResult


class ReviewStatusResult(StrictModel):
    project_id: str
    chapter_number: int
    revision: int
    status: Literal["clear", "blocked", "changes_requested", "rejected", "stale", "unreviewed"]
    blocking_finding_ids: list[str]
    requires_human: bool
    reasons: list[str]


class ReviewValidationResult(StrictModel):
    project_id: str
    chapter_number: int
    accepted_artifact_ids: list[str]
    stale_finding_ids: list[str]
    blocking_finding_ids: list[str]
    fingerprints: dict[str, str]
    status: ReviewStatusResult
    replayed: bool = False


class RevisionDiffResult(StrictModel):
    project_id: str
    chapter_number: int = Field(ge=1)
    source_revision: int = Field(ge=0)
    original_body: str
    revised_body: str
    original_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revised_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed_spans: list[ChangedSpan]
