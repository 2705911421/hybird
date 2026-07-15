from __future__ import annotations

from typing import Annotated, Union
import hashlib
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import RuntimeConfig
from .chapter_commits import ChapterCommitService
from .chapter_reads import ChapterReadService
from .contracts import (
    AppendEventsRequest, AppendEventsResult, TypedDiffCommandRequest, ChapterArtifactResult, CommitChapterRequest, ContextQueryResult, DoctorResult,
    CreateProjectRequest, EntityResult, ErrorResponse, ExportSnapshotRequest, FinalizedCommitResult, HealthResponse,
    MigrateProjectRequest, PrepareChapterRequest, ProjectStatusResponse,
    PrepareChapterResult, ProjectCreatedResult, QueryContextRequest, ReplayProjectionsRequest,
    ReplayProjectionsResult, ValidateChapterArtifactsRequest, ValidateChapterResult,
    CommitRecoveryRequest, CommitRecoveryResult, OutboxRunRequest, OutboxRunResult,
    ChapterReviewArtifact, HumanReviewDecision, ReviewStatusResult, ReviewValidationResult,
    StoreReviewDecisionRequest, ValidateReviewsRequest, ValidateRevisionRequest, RevisionResult, RevisionDiffResult,
    CommitDetail, CommitListResult, DiagnosticReport, EventTimelineResult, MigrationStatus,
    ProjectionListResult, RecoveryExecuteRequest, RecoveryJob, RecoveryJobListResult,
    RecoveryPreviewRequest, ReviewOverview, RuntimeConfigurationStatus, RuntimeOverview,
    CreateMigrationJobRequest, MigrationActionRequest, MigrationDecisionsRequest,
    MigrationJobListResult, MigrationJobResult,
    ChapterAggregateResult, ChapterCollectionResult, ChapterExportRequest,
    ChapterExportSnapshotResult, ChapterSearchResult,
)
from .database import Database
from .errors import ConflictError, FeatureDisabledError, NotFoundError, RuntimeErrorBase
from .repository import StoryRepository
from .services import RuntimeServices
from .outbox import OutboxWorker
from .reviews import ReviewService
from .observability import ObservabilityService, RecoveryService, redact, redact_text
from .migration_jobs import LegacyMigrationService
from .runtime_logging import configure_runtime_logging

API_PREFIX = "/api/story-runtime/v1"
WRITE_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Runtime write feature is disabled"},
    409: {"model": ErrorResponse, "description": "Revision conflict"},
    422: {"model": ErrorResponse, "description": "Contract or domain validation error"},
}
WriteRequest = Union[
    PrepareChapterRequest, ValidateChapterArtifactsRequest, CommitChapterRequest,
    AppendEventsRequest, TypedDiffCommandRequest, ReplayProjectionsRequest, MigrateProjectRequest, ExportSnapshotRequest,
    CommitRecoveryRequest, OutboxRunRequest,
    ValidateReviewsRequest, StoreReviewDecisionRequest, ValidateRevisionRequest,
]


def create_app(config: RuntimeConfig | None = None) -> FastAPI:
    config = config or RuntimeConfig.from_env()
    database = Database(config)
    database.migrations.migrate()
    repository = StoryRepository(database)
    services = RuntimeServices(database, repository)
    commits = ChapterCommitService(database, unified_review_enabled=config.unified_review_enabled)
    chapter_reads = ChapterReadService(database)
    app = FastAPI(title="Hybrid Story Runtime API", version="0.1.0", docs_url="/docs", redoc_url=None)
    app.state.config = config
    app.state.database = database
    app.state.repository = repository
    app.state.services = services
    app.state.commits = commits
    app.state.chapter_reads = chapter_reads
    app.state.outbox = OutboxWorker(database)
    app.state.reviews = ReviewService(database)
    app.state.observability = ObservabilityService(database, repository)
    app.state.recovery = RecoveryService(database, repository)
    app.state.migration_jobs = LegacyMigrationService(database, config)
    logger = configure_runtime_logging(config.log_path, config.log_max_bytes, config.log_backups)

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        started = time.perf_counter()

        def payload_too_large_response() -> JSONResponse:
            logger.warning("runtime request rejected", extra={
                "request_id": request_id, "operation": f"{request.method} <payload-rejected>",
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "result": 413, "retryability": False, "error_code": "PAYLOAD_TOO_LARGE",
            })
            return JSONResponse(
                status_code=413,
                content={"code": "PAYLOAD_TOO_LARGE", "message": "request body exceeds the configured limit", "retryable": False},
                headers={"x-request-id": request_id},
            )

        content_length = request.headers.get("content-length")
        if content_length and content_length.isdecimal() and int(content_length) > config.max_request_bytes:
            return payload_too_large_response()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            received = 0
            chunks: list[bytes] = []
            async for chunk in request.stream():
                received += len(chunk)
                if received > config.max_request_bytes:
                    return payload_too_large_response()
                chunks.append(chunk)
            request._body = b"".join(chunks)

        def log_context() -> dict[str, str | None]:
            project_id = request.path_params.get("project_id")
            route = request.scope.get("route")
            route_path = getattr(route, "path", None)
            return {
                "project_id": hashlib.sha256(project_id.encode()).hexdigest()[:12] if project_id else None,
                "commit_id": request.path_params.get("commit_id"),
                "operation": f"{request.method} {route_path or '<unmatched>'}",
            }

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            context = log_context()
            logger.info("runtime request", extra={
                "request_id": request_id, **context, "duration_ms": duration_ms,
                "result": response.status_code, "retryability": response.status_code in {409, 423, 429, 503},
            })
            response.headers["x-request-id"] = request_id
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            context = log_context()
            logger.exception("unhandled runtime request failure", extra={
                "request_id": request_id, **context, "duration_ms": duration_ms,
                "result": 500, "retryability": False, "error_code": "UNHANDLED_ERROR",
            })
            raise

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if authorization != f"Bearer {config.local_token}":
            raise HTTPException(status_code=401, detail="invalid local bearer token")

    @app.exception_handler(RuntimeErrorBase)
    async def runtime_error_handler(_request: Request, exc: RuntimeErrorBase):
        status = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 403 if isinstance(exc, FeatureDisabledError) else 503 if exc.retryable else 422
        body = ErrorResponse(code=exc.code, message=redact_text(exc.message), retryable=exc.retryable, current_revision=exc.current_revision, details=redact(exc.details))
        return JSONResponse(status_code=status, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, exc: RequestValidationError):
        body = ErrorResponse(
            code="VALIDATION_ERROR",
            message="request does not match the story-runtime/v1 contract",
            retryable=False,
            details={"errors": exc.errors()},
        )
        return JSONResponse(status_code=422, content=jsonable_encoder(body))

    @app.get(f"{API_PREFIX}/health", response_model=HealthResponse, operation_id="getHealth")
    def health() -> HealthResponse:
        return services.health()

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/status", response_model=ProjectStatusResponse, operation_id="getProjectStatus", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}})
    def project_status(project_id: str) -> ProjectStatusResponse:
        return services.project_status(project_id)

    def observability_enabled() -> None:
        if not config.observability_enabled:
            raise FeatureDisabledError("OBSERVABILITY_DISABLED", "Runtime observability is disabled by feature flag.")

    def migration_enabled() -> None:
        if not config.migration_enabled:
            raise FeatureDisabledError("MIGRATION_DISABLED", "Legacy project migration is disabled by feature flag.")

    def migration_write_enabled() -> None:
        migration_enabled()
        if not config.writes_enabled:
            raise FeatureDisabledError(
                "WRITE_FEATURE_DISABLED", "Target import operations require STORY_RUNTIME_ENABLE_WRITES=1",
                details={"feature_flag": "STORY_RUNTIME_ENABLE_WRITES", "enabled": False},
            )

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/overview", response_model=RuntimeOverview, operation_id="getRuntimeOverview", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def runtime_overview(project_id: str):
        return app.state.observability.overview(project_id)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/commits", response_model=CommitListResult, operation_id="listCommits", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def list_commits(project_id: str, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                     chapter: Annotated[int | None, Query(ge=1)] = None, state: str | None = None,
                     from_date: str | None = None, to_date: str | None = None):
        return app.state.observability.commits(project_id, cursor=cursor, limit=limit, chapter=chapter, state=state, date_from=from_date, date_to=to_date)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/commits/{{commit_id}}", response_model=CommitDetail, operation_id="getCommitDetail", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def get_commit(project_id: str, commit_id: str):
        return app.state.observability.commit(project_id, commit_id)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/events", response_model=EventTimelineResult, operation_id="listEvents", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def list_events(project_id: str, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                    event_type: str | None = None, aggregate: str | None = None,
                    chapter: Annotated[int | None, Query(ge=1)] = None,
                    revision: Annotated[int | None, Query(ge=0)] = None, view: str = "summary"):
        return app.state.observability.events(project_id, cursor=cursor, limit=limit, event_type=event_type,
                                              aggregate=aggregate, chapter=chapter, revision=revision, view=view)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/projections", response_model=ProjectionListResult, operation_id="listProjections", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def list_projections(project_id: str):
        return app.state.observability.projections(project_id)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/reviews/status", response_model=ReviewOverview, operation_id="getReviewOverview", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def review_overview(project_id: str):
        return app.state.observability.reviews(project_id)

    @app.get(f"{API_PREFIX}/migration/status", response_model=MigrationStatus, operation_id="getMigrationStatus", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def migration_status():
        return app.state.observability.migration()

    @app.post(f"{API_PREFIX}/migration-jobs", response_model=MigrationJobResult, operation_id="createLegacyMigrationJob", dependencies=[Depends(authorize), Depends(migration_enabled)], responses=WRITE_RESPONSES)
    def create_migration_job(body: CreateMigrationJobRequest):
        return app.state.migration_jobs.create(body)

    @app.get(f"{API_PREFIX}/migration-jobs", response_model=MigrationJobListResult, operation_id="listLegacyMigrationJobs", dependencies=[Depends(authorize), Depends(migration_enabled)])
    def list_migration_jobs(target_project_id: str | None = None):
        return app.state.migration_jobs.list(target_project_id)

    @app.get(f"{API_PREFIX}/migration-jobs/{{job_id}}", response_model=MigrationJobResult, operation_id="getLegacyMigrationJob", dependencies=[Depends(authorize), Depends(migration_enabled)])
    def get_migration_job(job_id: str):
        return app.state.migration_jobs.get(job_id)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/scan", response_model=MigrationJobResult, operation_id="scanLegacyMigrationSource", dependencies=[Depends(authorize), Depends(migration_enabled)], responses=WRITE_RESPONSES)
    def scan_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.scan(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/decisions", response_model=MigrationJobResult, operation_id="decideLegacyMigrationConflicts", dependencies=[Depends(authorize), Depends(migration_enabled)], responses=WRITE_RESPONSES)
    def decide_migration_job(job_id: str, body: MigrationDecisionsRequest):
        return app.state.migration_jobs.decide(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/dry-run", response_model=MigrationJobResult, operation_id="dryRunLegacyMigration", dependencies=[Depends(authorize), Depends(migration_enabled)], responses=WRITE_RESPONSES)
    def dry_run_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.dry_run(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/snapshot", response_model=MigrationJobResult, operation_id="snapshotLegacyMigrationTarget", dependencies=[Depends(authorize), Depends(migration_write_enabled)], responses=WRITE_RESPONSES)
    def snapshot_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.snapshot(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/import", response_model=MigrationJobResult, operation_id="importLegacyMigration", dependencies=[Depends(authorize), Depends(migration_write_enabled)], responses=WRITE_RESPONSES)
    def import_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.import_job(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/verify", response_model=MigrationJobResult, operation_id="verifyLegacyMigration", dependencies=[Depends(authorize), Depends(migration_write_enabled)], responses=WRITE_RESPONSES)
    def verify_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.verify(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/pause", response_model=MigrationJobResult, operation_id="pauseLegacyMigration", dependencies=[Depends(authorize), Depends(migration_enabled)], responses=WRITE_RESPONSES)
    def pause_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.pause(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/resume", response_model=MigrationJobResult, operation_id="resumeLegacyMigration", dependencies=[Depends(authorize), Depends(migration_enabled)], responses=WRITE_RESPONSES)
    def resume_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.resume(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/cutover", response_model=MigrationJobResult, operation_id="cutoverLegacyMigration", dependencies=[Depends(authorize), Depends(migration_write_enabled)], responses=WRITE_RESPONSES)
    def cutover_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.cutover(job_id, body)

    @app.post(f"{API_PREFIX}/migration-jobs/{{job_id}}/rollback", response_model=MigrationJobResult, operation_id="rollbackLegacyMigration", dependencies=[Depends(authorize), Depends(migration_write_enabled)], responses=WRITE_RESPONSES)
    def rollback_migration_job(job_id: str, body: MigrationActionRequest):
        return app.state.migration_jobs.rollback(job_id, body)

    @app.get(f"{API_PREFIX}/migration-jobs/{{job_id}}/report", operation_id="downloadLegacyMigrationReport", dependencies=[Depends(authorize), Depends(migration_enabled)])
    def migration_job_report(job_id: str):
        return app.state.migration_jobs.report(job_id)

    @app.get(f"{API_PREFIX}/configuration/status", response_model=RuntimeConfigurationStatus, operation_id="getRuntimeConfigurationStatus", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def configuration_status():
        return app.state.observability.configuration()

    @app.post(f"{API_PREFIX}/queries/context", response_model=ContextQueryResult, operation_id="queryContext", dependencies=[Depends(authorize)])
    def query_context(body: QueryContextRequest) -> ContextQueryResult:
        return services.query_context(body)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/entities/{{entity_id}}", response_model=EntityResult, operation_id="queryEntity", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def query_entity(project_id: str, entity_id: str, at_revision: Annotated[int | None, Query(ge=0)] = None, include_history: bool = False) -> EntityResult:
        if at_revision is not None:
            # RC-2B Batch 1 establishes revision existence only. It must not
            # turn the current projection into pseudo-history; Batch 2+ must
            # complete typed coverage before an exact historical read exists.
            raise ConflictError(
                "HISTORY_NOT_IMPLEMENTED",
                "exact historical state is not implemented; omit at_revision for a latest-only read",
                details={"requested_revision": at_revision, "batch": "RC-2B1"},
            )
        result = services.entity(project_id, entity_id, include_history)
        return result

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/chapters/{{chapter_number}}", response_model=ChapterArtifactResult, operation_id="getFinalizedChapter", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}})
    def finalized_chapter(project_id: str, chapter_number: int) -> ChapterArtifactResult:
        if chapter_number < 1:
            raise NotFoundError("CHAPTER_NOT_FOUND", f"finalized chapter not found: {chapter_number}")
        return commits.chapter(project_id, chapter_number)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/chapters", response_model=ChapterCollectionResult, operation_id="listFinalizedChapters", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def finalized_chapters(
        project_id: str,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        from_chapter: Annotated[int | None, Query(ge=1)] = None,
        to_chapter: Annotated[int | None, Query(ge=1)] = None,
        volume_id: str | None = None,
        finalized_only: bool = True,
    ) -> ChapterCollectionResult:
        return chapter_reads.collection(
            project_id,
            cursor=cursor,
            limit=limit,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            volume_id=volume_id,
            finalized_only=finalized_only,
        )

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/chapter-aggregate", response_model=ChapterAggregateResult, operation_id="getChapterAggregate", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}})
    def chapter_aggregate(project_id: str) -> ChapterAggregateResult:
        return chapter_reads.aggregate(project_id)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/chapter-export", response_model=ChapterExportSnapshotResult, operation_id="createChapterExportSnapshot", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def chapter_export(project_id: str, body: ChapterExportRequest) -> ChapterExportSnapshotResult:
        return chapter_reads.export_snapshot(project_id, body)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/chapter-search", response_model=ChapterSearchResult, operation_id="searchFinalizedChapters", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def chapter_search(
        project_id: str,
        q: Annotated[str, Query(min_length=1, max_length=500)],
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> ChapterSearchResult:
        return chapter_reads.search(project_id, q, cursor=cursor, limit=limit)

    def disabled(_body: WriteRequest) -> None:
        raise FeatureDisabledError(
            "WRITE_FEATURE_DISABLED",
            "Runtime write endpoints require STORY_RUNTIME_ENABLE_WRITES=1",
            details={"feature_flag": "STORY_RUNTIME_ENABLE_WRITES", "enabled": False},
        )

    @app.post(f"{API_PREFIX}/projects", response_model=ProjectCreatedResult, operation_id="createRuntimeProject", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def create_runtime_project(body: CreateProjectRequest):
        if not config.writes_enabled: disabled(body)
        return commits.create_project(body)

    @app.post(f"{API_PREFIX}/chapters/prepare", response_model=PrepareChapterResult, operation_id="prepareChapter", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def prepare_chapter(body: PrepareChapterRequest):
        if not config.writes_enabled: disabled(body)
        return commits.prepare(body)

    @app.post(f"{API_PREFIX}/chapters/validate", response_model=ValidateChapterResult, operation_id="validateChapterArtifacts", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def validate_chapter(body: ValidateChapterArtifactsRequest):
        if not config.writes_enabled: disabled(body)
        return commits.validate(body)

    @app.post(f"{API_PREFIX}/chapters/commit", response_model=FinalizedCommitResult, operation_id="commitChapter", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def commit_chapter(body: CommitChapterRequest):
        if not config.writes_enabled: disabled(body)
        return commits.commit(body)

    @app.post(f"{API_PREFIX}/events/append", response_model=AppendEventsResult, operation_id="appendEvents", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def append_events(body: AppendEventsRequest):
        if not config.writes_enabled: disabled(body)
        return commits.append_operator_events(body)

    @app.post(f"{API_PREFIX}/commands/typed-diff", response_model=AppendEventsResult, operation_id="applyTypedDiff", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def apply_typed_diff(body: TypedDiffCommandRequest):
        if not config.writes_enabled: disabled(body)
        return commits.apply_typed_diff(body)

    @app.post(f"{API_PREFIX}/projections/replay", response_model=ReplayProjectionsResult, operation_id="replayProjections", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def replay_projections(body: ReplayProjectionsRequest):
        if not config.writes_enabled: disabled(body)
        return commits.replay(body)

    @app.post(f"{API_PREFIX}/commits/recover", response_model=CommitRecoveryResult, operation_id="recoverCommit", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def recover_commit(body: CommitRecoveryRequest):
        if not config.writes_enabled: disabled(body)
        return commits.recover(body)

    @app.post(f"{API_PREFIX}/outbox/run", response_model=OutboxRunResult, operation_id="runOutbox", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def run_outbox(body: OutboxRunRequest):
        if not config.writes_enabled: disabled(body)
        return app.state.outbox.run(body)

    @app.post(f"{API_PREFIX}/reviews/validate", response_model=ReviewValidationResult, operation_id="validateReviews", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def validate_reviews(body: ValidateReviewsRequest):
        if not config.writes_enabled: disabled(body)
        return app.state.reviews.validate(body)

    @app.post(f"{API_PREFIX}/reviews/decisions", response_model=HumanReviewDecision, operation_id="storeReviewDecision", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def store_review_decision(body: StoreReviewDecisionRequest):
        if not config.writes_enabled: disabled(body)
        return app.state.reviews.decision(body)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/chapters/{{chapter_number}}/reviews", response_model=list[ChapterReviewArtifact], operation_id="getChapterReviews", dependencies=[Depends(authorize)])
    def chapter_reviews(project_id: str, chapter_number: int):
        return app.state.reviews.artifacts(project_id, chapter_number)

    @app.post(f"{API_PREFIX}/revisions/validate", response_model=RevisionResult, operation_id="validateRevision", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def validate_revision(body: ValidateRevisionRequest):
        if not config.writes_enabled: disabled(body)
        return app.state.reviews.validate_revision(body)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/chapters/{{chapter_number}}/review-status", response_model=ReviewStatusResult, operation_id="getChapterReviewStatus", dependencies=[Depends(authorize)])
    def chapter_review_status(project_id: str, chapter_number: int):
        return app.state.reviews.status(project_id, chapter_number)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/chapters/{{chapter_number}}/revision-diff", response_model=RevisionDiffResult, operation_id="getChapterRevisionDiff", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}})
    def chapter_revision_diff(project_id: str, chapter_number: int):
        return app.state.reviews.revision_diff(project_id, chapter_number)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/doctor", response_model=DoctorResult, operation_id="doctorProject", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}})
    def doctor(project_id: str, deep: bool = False) -> DoctorResult:
        return services.doctor(project_id, deep)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/diagnostics", response_model=DiagnosticReport, operation_id="downloadDiagnosticReport", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def diagnostics(project_id: str):
        return app.state.observability.diagnostics(project_id, services.doctor(project_id, False))

    def recovery_enabled() -> None:
        observability_enabled()
        if not config.recovery_enabled:
            raise FeatureDisabledError("RECOVERY_DISABLED", "Runtime recovery operations are disabled by feature flag.")

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/recovery-jobs/preview", response_model=RecoveryJob, operation_id="previewRecovery", dependencies=[Depends(authorize), Depends(recovery_enabled)], responses=WRITE_RESPONSES)
    def preview_recovery(project_id: str, body: RecoveryPreviewRequest):
        return app.state.recovery.preview(project_id, body)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/recovery-jobs", response_model=RecoveryJobListResult, operation_id="listRecoveryJobs", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def list_recovery_jobs(project_id: str, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 25):
        return app.state.recovery.list(project_id, cursor=cursor, limit=limit)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/recovery-jobs/{{job_id}}", response_model=RecoveryJob, operation_id="getRecoveryJob", dependencies=[Depends(authorize), Depends(observability_enabled)])
    def get_recovery_job(project_id: str, job_id: str):
        return app.state.recovery.get(project_id, job_id)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/recovery-jobs/{{job_id}}/execute", response_model=RecoveryJob, operation_id="executeRecovery", dependencies=[Depends(authorize), Depends(recovery_enabled)], responses=WRITE_RESPONSES)
    def execute_recovery(project_id: str, job_id: str, body: RecoveryExecuteRequest):
        return app.state.recovery.execute(project_id, job_id, body)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/recovery-jobs/{{job_id}}/cancel", response_model=RecoveryJob, operation_id="cancelRecovery", dependencies=[Depends(authorize), Depends(recovery_enabled)], responses=WRITE_RESPONSES)
    def cancel_recovery(project_id: str, job_id: str, body: RecoveryExecuteRequest):
        return app.state.recovery.cancel(project_id, job_id, body.actor)

    @app.post(f"{API_PREFIX}/projects/migrate", operation_id="migrateProject", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def migrate_disabled(body: MigrateProjectRequest): disabled(body)

    @app.post(f"{API_PREFIX}/projects/export-snapshot", operation_id="exportSnapshot", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def export_disabled(body: ExportSnapshotRequest): disabled(body)

    return app
