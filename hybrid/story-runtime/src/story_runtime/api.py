from __future__ import annotations

from typing import Annotated, Union

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import RuntimeConfig
from .contracts import (
    AppendEventsRequest, CommitChapterRequest, ContextQueryResult, DoctorResult,
    EntityResult, ErrorResponse, ExportSnapshotRequest, HealthResponse,
    MigrateProjectRequest, PrepareChapterRequest, ProjectStatusResponse,
    QueryContextRequest, ReplayProjectionsRequest, ValidateChapterArtifactsRequest,
)
from .database import Database
from .errors import FeatureDisabledError, NotFoundError, RuntimeErrorBase
from .repository import StoryRepository
from .services import RuntimeServices

API_PREFIX = "/api/story-runtime/v1"
WRITE_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Phase 1 write feature is disabled"},
    409: {"model": ErrorResponse, "description": "Revision conflict"},
    422: {"model": ErrorResponse, "description": "Contract or domain validation error"},
}
WriteRequest = Union[
    PrepareChapterRequest, ValidateChapterArtifactsRequest, CommitChapterRequest,
    AppendEventsRequest, ReplayProjectionsRequest, MigrateProjectRequest, ExportSnapshotRequest,
]


def create_app(config: RuntimeConfig | None = None) -> FastAPI:
    config = config or RuntimeConfig.from_env()
    database = Database(config)
    database.migrations.migrate()
    repository = StoryRepository(database)
    services = RuntimeServices(database, repository)
    app = FastAPI(title="Hybrid Story Runtime API", version="0.1.0", docs_url="/docs", redoc_url=None)
    app.state.config = config
    app.state.database = database
    app.state.repository = repository
    app.state.services = services

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if authorization != f"Bearer {config.local_token}":
            raise HTTPException(status_code=401, detail="invalid local bearer token")

    @app.exception_handler(RuntimeErrorBase)
    async def runtime_error_handler(_request: Request, exc: RuntimeErrorBase):
        status = 404 if isinstance(exc, NotFoundError) else 403 if isinstance(exc, FeatureDisabledError) else 503 if exc.retryable else 422
        body = ErrorResponse(code=exc.code, message=exc.message, retryable=exc.retryable, current_revision=exc.current_revision, details=exc.details)
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

    @app.post(f"{API_PREFIX}/queries/context", response_model=ContextQueryResult, operation_id="queryContext", dependencies=[Depends(authorize)])
    def query_context(body: QueryContextRequest) -> ContextQueryResult:
        return services.query_context(body)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/entities/{{entity_id}}", response_model=EntityResult, operation_id="queryEntity", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}})
    def query_entity(project_id: str, entity_id: str, at_revision: Annotated[int | None, Query(ge=0)] = None, include_history: bool = False) -> EntityResult:
        result = services.entity(project_id, entity_id, include_history)
        if at_revision is not None and at_revision > result.revision:
            raise NotFoundError("REVISION_NOT_FOUND", f"revision {at_revision} does not exist")
        return result

    def disabled(_body: WriteRequest) -> None:
        raise FeatureDisabledError(
            "WRITE_FEATURE_DISABLED",
            "Phase 1 write endpoints are disabled",
            details={"feature_flag": "STORY_RUNTIME_ENABLE_WRITES", "enabled": False},
        )

    @app.post(f"{API_PREFIX}/chapters/prepare", operation_id="prepareChapter", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def prepare_disabled(body: PrepareChapterRequest): disabled(body)

    @app.post(f"{API_PREFIX}/chapters/validate", operation_id="validateChapterArtifacts", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def validate_disabled(body: ValidateChapterArtifactsRequest): disabled(body)

    @app.post(f"{API_PREFIX}/chapters/commit", operation_id="commitChapter", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def commit_disabled(body: CommitChapterRequest): disabled(body)

    @app.post(f"{API_PREFIX}/events/append", operation_id="appendEvents", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def events_disabled(body: AppendEventsRequest): disabled(body)

    @app.post(f"{API_PREFIX}/projections/replay", operation_id="replayProjections", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def replay_disabled(body: ReplayProjectionsRequest): disabled(body)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/doctor", response_model=DoctorResult, operation_id="doctorProject", dependencies=[Depends(authorize)], responses={404: {"model": ErrorResponse}})
    def doctor(project_id: str, deep: bool = False) -> DoctorResult:
        return services.doctor(project_id, deep)

    @app.post(f"{API_PREFIX}/projects/migrate", operation_id="migrateProject", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def migrate_disabled(body: MigrateProjectRequest): disabled(body)

    @app.post(f"{API_PREFIX}/projects/export-snapshot", operation_id="exportSnapshot", dependencies=[Depends(authorize)], responses=WRITE_RESPONSES)
    def export_disabled(body: ExportSnapshotRequest): disabled(body)

    return app
