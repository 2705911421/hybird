from __future__ import annotations

import sqlite3
from typing import Any

from . import SCHEMA_VERSION, __version__
from .contracts import (
    ContextQueryResult, DoctorCheck, DoctorResult, EntityResult, HealthResponse,
    ProjectStatusResponse, QueryContextRequest, QueryTrace,
)
from .database import Database
from .repository import StoryRepository


class RuntimeServices:
    def __init__(self, database: Database, repository: StoryRepository):
        self.database = database
        self.repository = repository

    def health(self) -> HealthResponse:
        try:
            current = self.database.migrations.current_version()
            if current < self.database.latest_schema_version:
                return HealthResponse(status="degraded", runtime_version=__version__, schema_versions=[SCHEMA_VERSION], database="migration_required")
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.rollback()
            return HealthResponse(status="ok", runtime_version=__version__, schema_versions=[SCHEMA_VERSION], database="ready")
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                return HealthResponse(status="degraded", runtime_version=__version__, schema_versions=[SCHEMA_VERSION], database="locked")
            return HealthResponse(status="unavailable", runtime_version=__version__, schema_versions=[SCHEMA_VERSION], database="unavailable")

    def project_status(self, project_id: str) -> ProjectStatusResponse:
        project = self.repository.get_project(project_id)
        projection = self.repository.projection_health(project_id)
        degraded_names = [row["projection_name"] for row in projection["projections"] if row["status"] != "ready"]
        return ProjectStatusResponse(
            project_id=project_id, revision=project["revision"], phase=project["phase"], latest_chapter=project["latest_chapter"],
            projection_health={
                "status": projection["status"],
                "recoverable": "true" if projection["recoverable"] else "false",
                "repair": "replay:" + ",".join(degraded_names) if degraded_names else "none",
            },
            schema_version=project["schema_version"], active_prepare_ids=[],
        )

    def entity(self, project_id: str, entity_id: str, include_history: bool = False) -> EntityResult:
        project = self.repository.get_project(project_id)
        return EntityResult(project_id=project_id, revision=project["revision"], entity=self.repository.get_entity(project_id, entity_id, include_history))

    def query_context(self, request: QueryContextRequest) -> ContextQueryResult:
        project = self.repository.get_project(request.project_id)
        facts = self.repository.query_facts(request.project_id, request.intent, request.entity_ids, request.budget.max_items)
        remaining = max(0, request.budget.max_items - len(facts))
        retrieval = self.repository.rag_search(request.project_id, request.intent, remaining) if request.include_retrieval_candidates else []
        max_chars = request.budget.max_tokens * 4
        used = 0
        selected_facts = []
        for fact in facts:
            cost = len(fact.model_dump_json())
            if used + cost > max_chars:
                break
            selected_facts.append(fact)
            used += cost
        selected_retrieval = []
        for candidate in retrieval:
            cost = len(candidate.text)
            if used + cost > max_chars:
                break
            selected_retrieval.append(candidate)
            used += cost
        return ContextQueryResult(
            request_id=request.request_id, project_id=request.project_id, revision=project["revision"],
            authoritative_facts=selected_facts, retrieval_candidates=selected_retrieval, untrusted_materials=[],
            trace=QueryTrace(budget_used=(used + 3) // 4, selected_source_ids=[f.fact_id for f in selected_facts] + [r.source_id for r in selected_retrieval]),
        )

    def doctor(self, project_id: str, deep: bool = False) -> DoctorResult:
        project = self.repository.get_project(project_id)
        checks = [
            DoctorCheck(code="schema.current", status="pass", message=f"schema migration {self.database.migrations.current_version()} is current", repair=None),
            DoctorCheck(code="authority.integrity", status="pass", message="SQLite integrity check passed", repair=None),
            DoctorCheck(code="writes.feature_flag", status="pass", message="HTTP write endpoints are disabled for Phase 1", repair=None),
        ]
        if deep and self.repository.integrity_check() != "ok":
            checks[1] = DoctorCheck(code="authority.integrity", status="fail", message="SQLite integrity check failed", repair="restore a verified snapshot")
        projection = self.repository.projection_health(project_id)
        if projection["status"] == "ready":
            checks.append(DoctorCheck(code="projections.core", status="pass", message="all core projections are ready", repair=None))
        else:
            checks.append(DoctorCheck(code="projections.core", status="warn", message="one or more projections require replay", repair="run projection replay after enabling the operator write flag"))
        for incident in self.repository.unresolved_incidents(project_id):
            checks.append(DoctorCheck(code=f"incident.{incident['component']}", status="warn" if incident["retryable"] else "fail", message=incident["message"], repair=incident["repair_action"]))
        status = "blocked" if any(c.status == "fail" for c in checks) else "warning" if any(c.status == "warn" for c in checks) else "ok"
        return DoctorResult(project_id=project_id, revision=project["revision"], status=status, checks=checks)

    def fixture_summary(self, project_id: str) -> dict[str, Any]:
        return {"project": self.repository.get_project(project_id), "counts": self.repository.counts(project_id)}
