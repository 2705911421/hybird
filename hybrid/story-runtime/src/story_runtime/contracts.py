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
    status: Literal["pass", "warn", "fail"]
    message: str
    repair: str | None


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
    event_id: str
    event_type: str
    subject: str
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
    review: dict[str, Any] | None = None
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


class ReplayProjectionsRequest(CommonWriteContext):
    projection_names: list[str] = Field(min_length=1)
    from_event_sequence: int = Field(ge=0)
    to_event_sequence: int | None = Field(default=None, ge=0)
    verify_only: bool


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
