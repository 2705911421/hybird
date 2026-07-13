from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from . import SCHEMA_VERSION, __version__
from .chapter_commits import ChapterCommitService
from .contracts import (
    CommitDetail, CommitListResult, CommitSummary, CommitTransitionView,
    DiagnosticReport, EventTimelineItem, EventTimelineResult, ImpactStatus,
    IndexHealth, MigrationStatus, PageInfo, ProjectionListResult, ProjectionView,
    RecoveryExecuteRequest, RecoveryJob, RecoveryJobListResult, RecoveryPreviewRequest,
    ReplayProjectionsRequest, ReviewOverview, RuntimeConfigurationStatus, RuntimeOverview,
)
from .database import Database
from .errors import ConflictError, NotFoundError, RuntimeErrorBase
from .migrations import MIGRATIONS
from .outbox import OutboxWorker
from .repository import StoryRepository

_PRIVATE_KEYS = re.compile(
    r"api[_-]?key|token|authorization|bearer|secret|password|database.*path|db.*path|"
    r"chapter.*(?:body|content)|body_text|^(?:body|content|text)$|private.*content|environment|traceback",
    re.IGNORECASE,
)
_WINDOWS_HOME = re.compile(r"(?i)[A-Z]:\\Users\\[^\\\s]+")
_POSIX_HOME = re.compile(r"/(?:home|Users)/[^/\s]+")
_BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+")
_SECRET_VALUE = re.compile(r"(?i)(sk-[A-Za-z0-9_-]{8,}|(?:api[_-]?key|token|secret)\s*[=:]\s*[^\s,;]+)")
_SAFE_OPERATIONS = {"retry_outbox_item", "rebuild_lexical_index", "rebuild_vector_index"}
_CONFIRM_OPERATIONS = {
    "replay_core_projection", "abort_prepared_commit", "restore_snapshot",
    "clear_retry_queue", "resume_interrupted_migration",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _SECRET_VALUE.sub("[REDACTED]", value)
    value = _WINDOWS_HOME.sub("[HOME]", value)
    return _POSIX_HOME.sub("[HOME]", value)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _PRIVATE_KEYS.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def _fingerprint(filters: dict[str, Any]) -> str:
    raw = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _encode_cursor(kind: str, project_id: str, fingerprint: str, position: list[Any]) -> str:
    raw = json.dumps({"v": 1, "k": kind, "p": project_id, "f": fingerprint, "o": position}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None, kind: str, project_id: str, fingerprint: str) -> list[Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload != {**payload, "v": 1, "k": kind, "p": project_id, "f": fingerprint}:
            raise ValueError
        position = payload.get("o")
        if not isinstance(position, list):
            raise ValueError
        return position
    except Exception as exc:
        raise RuntimeErrorBase(
            "INVALID_CURSOR", "The page cursor is invalid or no longer matches these filters.",
            retryable=False, details={"action": "restart_pagination"},
        ) from exc


def _page_limit(limit: int) -> int:
    if limit < 1 or limit > 100:
        raise RuntimeErrorBase("INVALID_PAGE_SIZE", "Page size must be between 1 and 100.")
    return limit


class ObservabilityService:
    def __init__(self, database: Database, repository: StoryRepository):
        self.database = database
        self.repository = repository

    def overview(self, project_id: str) -> RuntimeOverview:
        project = self.repository.get_project(project_id)
        with self.database.connect() as conn:
            counts = conn.execute(
                "SELECT "
                "SUM(CASE WHEN state IN ('PREPARED','VALIDATED') THEN 1 ELSE 0 END),"
                "SUM(CASE WHEN state IN ('REJECTED','RECOVERY_REQUIRED') THEN 1 ELSE 0 END),"
                "MAX(CASE WHEN state='FINALIZED' THEN finalized_at END) "
                "FROM chapter_commits WHERE project_id=?", (project_id,),
            ).fetchone()
            recovery = int(conn.execute(
                "SELECT COUNT(*) FROM recovery_jobs WHERE project_id=? AND state IN ('previewed','running','failed','blocked')",
                (project_id,),
            ).fetchone()[0])
            index_row = conn.execute(
                "SELECT COUNT(*),MAX(chapter_number) FROM retrieval_documents WHERE project_id=?", (project_id,),
            ).fetchone()
            pending_index = int(conn.execute(
                "SELECT COUNT(*) FROM outbox WHERE project_id=? AND status IN ('pending','failed') AND topic='search.index'",
                (project_id,),
            ).fetchone()[0])
            projection = self.repository.projection_health(project_id)
            unresolved = self.repository.unresolved_incidents(project_id)
            last_backup_row = conn.execute(
                "SELECT MAX(updated_at) FROM outbox WHERE project_id=? AND topic='snapshot.create' AND status='done'",
                (project_id,),
            ).fetchone()
        active = int(counts[0] or 0)
        blocked = int(counts[1] or 0)
        runtime_state = "healthy"
        if blocked or recovery:
            runtime_state = "recovery_required"
        elif projection["status"] != "ready" or unresolved or pending_index:
            runtime_state = "degraded"
        impact = self.impact(runtime_state)
        return RuntimeOverview(
            project_id=project_id, runtime_state=runtime_state, impact=impact,
            current_revision=project["revision"], latest_chapter=project["latest_chapter"],
            project_phase=project["phase"], authority_mode=project["authority_mode"],
            active_prepares=active, blocked_commits=blocked, pending_recovery=recovery,
            projection_health=projection["status"],
            index_health=IndexHealth(
                status="degraded" if pending_index else "ready",
                lexical_documents=int(index_row[0]), vector_status="not_configured",
                last_indexed_chapter=index_row[1], pending_items=pending_index,
            ),
            last_successful_commit=counts[2], last_backup=last_backup_row[0],
            schema_version=project["schema_version"], runtime_version=__version__,
        )

    @staticmethod
    def impact(state: str) -> ImpactStatus:
        values = {
            "healthy": ("Runtime is operating normally.", False, False, True, "No action is required.", []),
            "degraded": ("A disposable projection or index is behind.", False, False, True, "Review Doctor and retry the affected projection.", []),
            "unavailable": ("Studio cannot reach Story Runtime.", True, True, True, "Check the local Runtime process and retry.", ["all_runtime_operations"]),
            "version_mismatch": ("Studio and Runtime contract versions are incompatible.", True, True, False, "Update the older component.", ["runtime_writes", "recovery_execute"]),
            "migration_required": ("The Runtime schema must be migrated.", True, True, False, "Preview and confirm migration recovery.", ["runtime_writes"]),
            "database_locked": ("Runtime storage is temporarily locked.", False, True, True, "Wait for the active transaction and retry.", ["runtime_writes", "recovery_execute"]),
            "recovery_required": ("An authoritative commit or recovery job needs attention.", False, True, False, "Open Doctor & Recovery and follow the previewed action.", ["chapter_commit"]),
        }
        happened, reads, writes, retryable, action, disabled = values[state]
        return ImpactStatus(what_happened=happened, reads_affected=reads, writes_affected=writes,
                            retryable=retryable, user_action=action, disabled_actions=disabled)

    def commits(self, project_id: str, *, cursor: str | None, limit: int, chapter: int | None,
                state: str | None, date_from: str | None, date_to: str | None) -> CommitListResult:
        self.repository.get_project(project_id)
        limit = _page_limit(limit)
        filters = {"chapter": chapter, "state": state, "date_from": date_from, "date_to": date_to}
        fp = _fingerprint(filters)
        position = _decode_cursor(cursor, "commits", project_id, fp)
        where = ["project_id=?"]
        params: list[Any] = [project_id]
        if chapter is not None:
            where.append("chapter_number=?"); params.append(chapter)
        if state:
            where.append("state=?"); params.append(state)
        if date_from:
            where.append("created_at>=?"); params.append(date_from)
        if date_to:
            where.append("created_at<=?"); params.append(date_to)
        if position:
            if len(position) != 2:
                raise RuntimeErrorBase("INVALID_CURSOR", "The page cursor is invalid.")
            where.append("(updated_at<? OR (updated_at=? AND commit_id<?))")
            params.extend([position[0], position[0], position[1]])
        with self.database.connect() as conn:
            rows = conn.execute(
                f"SELECT commit_id,chapter_number,state,request_id,resulting_revision,created_at,updated_at "
                f"FROM chapter_commits WHERE {' AND '.join(where)} ORDER BY updated_at DESC,commit_id DESC LIMIT ?",
                (*params, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [self._commit_summary(row) for row in rows]
        next_cursor = _encode_cursor("commits", project_id, fp, [rows[-1]["updated_at"], rows[-1]["commit_id"]]) if has_more else None
        return CommitListResult(items=items, page=PageInfo(limit=limit, has_more=has_more, next_cursor=next_cursor))

    def commit(self, project_id: str, commit_id: str) -> CommitDetail:
        self.repository.get_project(project_id)
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM chapter_commits WHERE project_id=? AND commit_id=?", (project_id, commit_id)).fetchone()
            if not row:
                raise NotFoundError("COMMIT_NOT_FOUND", "Commit not found.")
            transitions = conn.execute(
                "SELECT from_state,to_state,reason,resulting_revision,created_at FROM commit_transitions WHERE commit_id=? ORDER BY transition_id",
                (commit_id,),
            ).fetchall()
            artifact = conn.execute("SELECT checksum FROM chapter_artifacts WHERE commit_id=?", (commit_id,)).fetchone()
            event_count = int(conn.execute("SELECT COUNT(*) FROM story_events WHERE project_id=? AND commit_id=?", (project_id, commit_id)).fetchone()[0])
            projections = conn.execute(
                "SELECT projection_name,status,checkpoint,applied_revision,retry_count,last_error FROM projection_checkpoints WHERE project_id=? ORDER BY projection_name",
                (project_id,),
            ).fetchall()
            findings = conn.execute(
                "SELECT finding_id,severity,blocking,status FROM review_findings WHERE project_id=? AND chapter_number=? ORDER BY severity,finding_id LIMIT 100",
                (project_id, row["chapter_number"]),
            ).fetchall()
            decision = conn.execute(
                "SELECT decision_id,decision,created_at FROM human_review_decisions WHERE project_id=? AND chapter_number=? ORDER BY created_at DESC LIMIT 1",
                (project_id, row["chapter_number"]),
            ).fetchone()
        error_details = redact(json.loads(row["error_details_json"] or "{}"))
        error = None if not row["error_code"] else {"code": row["error_code"], "message": redact_text(str(error_details.get("message", "Commit did not complete."))), "retryable": row["state"] in {"RECOVERY_REQUIRED", "REJECTED"}}
        repair = "Preview commit recovery." if row["state"] == "RECOVERY_REQUIRED" else "Resolve validation findings and submit again." if row["state"] == "REJECTED" else None
        return CommitDetail(
            summary=self._commit_summary(row),
            transitions=[CommitTransitionView(**dict(item)) for item in transitions],
            artifact_checksum=artifact[0] if artifact else None, event_count=event_count,
            projection_results=[redact(dict(item)) for item in projections],
            validation_findings=[dict(item) for item in findings],
            human_decision=dict(decision) if decision else None, error=error, repair_action=repair,
        )

    @staticmethod
    def _commit_summary(row: sqlite3.Row) -> CommitSummary:
        return CommitSummary(
            commit_id=row["commit_id"], chapter_number=row["chapter_number"], state=row["state"],
            request_id=row["request_id"], idempotency_status="recorded",
            retryable=row["state"] in {"REJECTED", "RECOVERY_REQUIRED", "ABORTED"},
            resulting_revision=row["resulting_revision"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def events(self, project_id: str, *, cursor: str | None, limit: int, event_type: str | None,
               aggregate: str | None, chapter: int | None, revision: int | None, view: str) -> EventTimelineResult:
        self.repository.get_project(project_id)
        limit = _page_limit(limit)
        if view not in {"summary", "evidence"}:
            raise RuntimeErrorBase("INVALID_EVENT_VIEW", "Event view must be summary or evidence.")
        filters = {"event_type": event_type, "aggregate": aggregate, "chapter": chapter, "revision": revision, "view": view}
        fp = _fingerprint(filters)
        position = _decode_cursor(cursor, "events", project_id, fp)
        where = ["project_id=?"]
        params: list[Any] = [project_id]
        for clause, value in (("event_type=?", event_type), ("aggregate_type=?", aggregate), ("chapter_number=?", chapter), ("applied_revision=?", revision)):
            if value is not None:
                where.append(clause); params.append(value)
        if position:
            if len(position) != 1 or not isinstance(position[0], int):
                raise RuntimeErrorBase("INVALID_CURSOR", "The page cursor is invalid.")
            where.append("sequence<?"); params.append(position[0])
        with self.database.connect() as conn:
            rows = conn.execute(
                f"SELECT sequence,event_id,event_type,subject,aggregate_type,aggregate_id,chapter_number,applied_revision,payload_json,evidence_json,created_at "
                f"FROM story_events WHERE {' AND '.join(where)} ORDER BY sequence DESC LIMIT ?", (*params, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items: list[EventTimelineItem] = []
        for row in rows:
            payload_raw = row["payload_json"] or "{}"
            payload = redact(json.loads(payload_raw))
            preview = {str(k): v for k, v in list(payload.items())[:8]} if isinstance(payload, dict) else None
            summary = str(payload.get("summary") or payload.get("title") or row["subject"] or row["event_type"]) if isinstance(payload, dict) else row["event_type"]
            items.append(EventTimelineItem(
                sequence=row["sequence"], event_id=row["event_id"], event_type=row["event_type"],
                aggregate_type=row["aggregate_type"], aggregate_id=row["aggregate_id"], chapter_number=row["chapter_number"],
                revision=row["applied_revision"], summary=redact_text(summary)[:500],
                evidence=redact(json.loads(row["evidence_json"] or "[]")) if view == "evidence" else None,
                payload_preview=preview if len(payload_raw.encode("utf-8")) <= 4096 else None,
                payload_bytes=len(payload_raw.encode("utf-8")), payload_truncated=len(payload_raw.encode("utf-8")) > 4096,
                created_at=row["created_at"],
            ))
        next_cursor = _encode_cursor("events", project_id, fp, [rows[-1]["sequence"]]) if has_more else None
        return EventTimelineResult(items=items, page=PageInfo(limit=limit, has_more=has_more, next_cursor=next_cursor))

    def projections(self, project_id: str) -> ProjectionListResult:
        self.repository.get_project(project_id)
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT projection_name,checkpoint,applied_revision,state_hash,status,retry_count,last_error,updated_at FROM projection_checkpoints WHERE project_id=? ORDER BY projection_name",
                (project_id,),
            ).fetchall()
        return ProjectionListResult(items=[ProjectionView(
            projection=row["projection_name"], checkpoint=row["checkpoint"], revision=row["applied_revision"],
            hash=row["state_hash"], status=row["status"], retry_count=row["retry_count"],
            last_error=redact_text(row["last_error"]) if row["last_error"] else None,
            replay_capability="confirmation_required", updated_at=row["updated_at"],
        ) for row in rows])

    def migration(self) -> MigrationStatus:
        current = self.database.migrations.current_version()
        target = self.database.latest_schema_version
        return MigrationStatus(
            status="current" if current == target else "required", current_version=current, target_version=target,
            pending_versions=[item.version for item in MIGRATIONS if item.version > current],
            resume_capability="not_needed" if current == target else "confirmation_required",
        )

    def configuration(self) -> RuntimeConfigurationStatus:
        cfg = self.database.config
        return RuntimeConfigurationStatus(
            writes_enabled=cfg.writes_enabled, unified_review_enabled=cfg.unified_review_enabled,
            token_configured=bool(cfg.local_token), projection_output_configured=cfg.projection_root is not None,
            observability_enabled=cfg.observability_enabled, recovery_enabled=cfg.recovery_enabled,
            busy_timeout_ms=cfg.busy_timeout_ms,
        )

    def reviews(self, project_id: str) -> ReviewOverview:
        self.repository.get_project(project_id)
        with self.database.connect() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM review_artifacts WHERE project_id=?", (project_id,)).fetchone()[0])
            open_count = int(conn.execute("SELECT COUNT(*) FROM review_findings WHERE project_id=? AND status NOT IN ('resolved','dismissed')", (project_id,)).fetchone()[0])
            blocking = int(conn.execute("SELECT COUNT(*) FROM review_findings WHERE project_id=? AND blocking=1 AND status NOT IN ('resolved','dismissed')", (project_id,)).fetchone()[0])
            decision = conn.execute("SELECT decision,created_at FROM human_review_decisions WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone()
        return ReviewOverview(project_id=project_id, total_artifacts=total, open_findings=open_count,
                              blocking_findings=blocking, latest_decision=decision[0] if decision else None,
                              latest_decision_at=decision[1] if decision else None)

    def diagnostics(self, project_id: str, doctor: Any) -> DiagnosticReport:
        overview = self.overview(project_id)
        projections = self.projections(project_id).items
        with self.database.connect() as conn:
            errors = conn.execute(
                "SELECT component,state,message,retryable,repair_action,created_at FROM runtime_incidents WHERE project_id=? ORDER BY created_at DESC LIMIT 25",
                (project_id,),
            ).fetchall()
            checksums = conn.execute(
                "SELECT commit_id,chapter_number,artifact_sha256 FROM chapter_commits WHERE project_id=? AND artifact_sha256 IS NOT NULL ORDER BY updated_at DESC LIMIT 50",
                (project_id,),
            ).fetchall()
        return DiagnosticReport(
            generated_at=_now(), project_id=project_id,
            versions={"runtime": __version__, "contract": SCHEMA_VERSION, "schema": self.database.migrations.current_version()},
            non_sensitive_config=self.configuration().model_dump(mode="json"),
            commit_status={"revision": overview.current_revision, "latest_chapter": overview.latest_chapter,
                           "active_prepares": overview.active_prepares, "blocked": overview.blocked_commits},
            projection_status=projections, doctor=doctor.__class__.model_validate(redact(doctor.model_dump(mode="json"))),
            recent_errors=[redact(dict(row)) for row in errors],
            checksums=[dict(row) for row in checksums],
        )


class RecoveryService:
    def __init__(self, database: Database, repository: StoryRepository):
        self.database = database
        self.repository = repository

    def preview(self, project_id: str, request: RecoveryPreviewRequest) -> RecoveryJob:
        project = self.repository.get_project(project_id)
        operation = request.operation
        requires_confirmation = operation in _CONFIRM_OPERATIONS
        token = secrets.token_urlsafe(32) if requires_confirmation else None
        job_id = str(uuid4())
        now = _now()
        parameters = self._validate_parameters(project_id, operation, request.parameters)
        blocked_reason = None
        if operation == "restore_snapshot":
            blocked_reason = "No verified authoritative snapshot restore provider is configured."
        preview = {
            "operation": operation, "changes_authority": operation in {"abort_prepared_commit", "restore_snapshot"},
            "current_revision": project["revision"], "parameters": redact(parameters),
            "warning": "Execution requires explicit confirmation." if requires_confirmation else None,
            "blocked_reason": blocked_reason,
        }
        state = "blocked" if blocked_reason else "previewed"
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO recovery_jobs(job_id,project_id,operation,state,requires_confirmation,confirmation_hash,parameters_json,preview_json,progress,cancellable,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,0,0,?,?)",
                (job_id, project_id, operation, state, int(requires_confirmation),
                 hashlib.sha256(token.encode()).hexdigest() if token else None,
                 json.dumps(parameters, ensure_ascii=False), json.dumps(preview, ensure_ascii=False), now, now),
            )
            self._audit(conn, job_id, project_id, "preview", state, request.actor, {"operation": operation})
            conn.commit()
        return self.get(project_id, job_id, confirmation_token=token)

    def execute(self, project_id: str, job_id: str, request: RecoveryExecuteRequest) -> RecoveryJob:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM recovery_jobs WHERE project_id=? AND job_id=?", (project_id, job_id)).fetchone()
        if not row:
            raise NotFoundError("RECOVERY_JOB_NOT_FOUND", "Recovery job not found.")
        if row["state"] == "blocked":
            raise ConflictError("RECOVERY_OPERATION_BLOCKED", "This recovery operation is not available in the current configuration.")
        if row["state"] != "previewed":
            raise ConflictError("RECOVERY_JOB_NOT_EXECUTABLE", "Recovery job is no longer awaiting execution.")
        if row["requires_confirmation"]:
            supplied = hashlib.sha256((request.confirmation_token or "").encode()).hexdigest()
            if not secrets.compare_digest(supplied, row["confirmation_hash"] or ""):
                raise ConflictError("RECOVERY_CONFIRMATION_REQUIRED", "Preview confirmation is missing or invalid.")
        now = _now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            updated = conn.execute(
                "UPDATE recovery_jobs SET state='running',progress=5,confirmation_hash=NULL,updated_at=? WHERE job_id=? AND state='previewed'",
                (now, job_id),
            )
            if updated.rowcount != 1:
                conn.rollback(); raise ConflictError("RECOVERY_JOB_CONFLICT", "Recovery job state changed; refresh before retrying.", retryable=True)
            self._audit(conn, job_id, project_id, "execute", "running", request.actor, {})
            conn.commit()
        try:
            result = self._run(project_id, row["operation"], json.loads(row["parameters_json"]))
            self._finish(project_id, job_id, "completed", result=result, actor=request.actor)
        except RuntimeErrorBase as exc:
            self._finish(project_id, job_id, "failed", error=(exc.code, exc.message), actor=request.actor)
            raise
        except Exception as exc:
            self._finish(project_id, job_id, "failed", error=("RECOVERY_FAILED", redact_text(str(exc))), actor=request.actor)
            raise RuntimeErrorBase("RECOVERY_FAILED", "Recovery could not be completed. Review the redacted job result.", retryable=True) from exc
        return self.get(project_id, job_id)

    def get(self, project_id: str, job_id: str, confirmation_token: str | None = None) -> RecoveryJob:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM recovery_jobs WHERE project_id=? AND job_id=?", (project_id, job_id)).fetchone()
            if not row:
                raise NotFoundError("RECOVERY_JOB_NOT_FOUND", "Recovery job not found.")
            audit = conn.execute(
                "SELECT action,outcome,actor,details_json,created_at FROM recovery_audit WHERE job_id=? ORDER BY audit_id", (job_id,),
            ).fetchall()
        error = None if not row["error_code"] else {"code": row["error_code"], "message": redact_text(row["error_message"] or "Recovery failed.")}
        return RecoveryJob(
            job_id=row["job_id"], project_id=row["project_id"], operation=row["operation"], state=row["state"],
            requires_confirmation=bool(row["requires_confirmation"]), confirmation_token=confirmation_token,
            preview=redact(json.loads(row["preview_json"])), result=redact(json.loads(row["result_json"])) if row["result_json"] else None,
            progress=row["progress"], cancellable=bool(row["cancellable"]), error=error,
            created_at=row["created_at"], updated_at=row["updated_at"], completed_at=row["completed_at"],
            audit_trail=[{**dict(item), "details": redact(json.loads(item["details_json"]))} for item in audit],
        )

    def list(self, project_id: str, *, cursor: str | None, limit: int) -> RecoveryJobListResult:
        self.repository.get_project(project_id)
        limit = _page_limit(limit)
        fp = _fingerprint({})
        position = _decode_cursor(cursor, "recovery", project_id, fp)
        where = "project_id=?"
        params: list[Any] = [project_id]
        if position:
            if len(position) != 2:
                raise RuntimeErrorBase("INVALID_CURSOR", "The page cursor is invalid.")
            where += " AND (created_at<? OR (created_at=? AND job_id<?))"
            params.extend([position[0], position[0], position[1]])
        with self.database.connect() as conn:
            rows = conn.execute(f"SELECT job_id,created_at FROM recovery_jobs WHERE {where} ORDER BY created_at DESC,job_id DESC LIMIT ?", (*params, limit + 1)).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [self.get(project_id, row["job_id"]) for row in rows]
        next_cursor = _encode_cursor("recovery", project_id, fp, [rows[-1]["created_at"], rows[-1]["job_id"]]) if has_more else None
        return RecoveryJobListResult(items=items, page=PageInfo(limit=limit, has_more=has_more, next_cursor=next_cursor))

    def cancel(self, project_id: str, job_id: str, actor: str) -> RecoveryJob:
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT state,cancellable FROM recovery_jobs WHERE project_id=? AND job_id=?", (project_id, job_id)).fetchone()
            if not row:
                conn.rollback(); raise NotFoundError("RECOVERY_JOB_NOT_FOUND", "Recovery job not found.")
            if row["state"] != "running" or not row["cancellable"]:
                conn.rollback(); raise ConflictError("RECOVERY_NOT_CANCELLABLE", "This job cannot be cancelled safely in its current state.")
            now = _now()
            conn.execute("UPDATE recovery_jobs SET state='cancelled',updated_at=?,completed_at=? WHERE job_id=?", (now, now, job_id))
            self._audit(conn, job_id, project_id, "cancel", "cancelled", actor, {})
            conn.commit()
        return self.get(project_id, job_id)

    def _validate_parameters(self, project_id: str, operation: str, parameters: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "retry_outbox_item": {"outbox_id"}, "rebuild_lexical_index": set(), "rebuild_vector_index": set(),
            "replay_core_projection": {"projection_names"}, "abort_prepared_commit": {"commit_id"},
            "restore_snapshot": {"snapshot_id"}, "clear_retry_queue": set(), "resume_interrupted_migration": set(),
        }[operation]
        unknown = set(parameters) - allowed
        if unknown:
            raise RuntimeErrorBase("INVALID_RECOVERY_PARAMETERS", "Recovery parameters contain unsupported fields.", details={"fields": sorted(unknown)})
        result = {key: parameters[key] for key in allowed if key in parameters}
        if operation == "retry_outbox_item" and not isinstance(result.get("outbox_id"), int):
            raise RuntimeErrorBase("INVALID_RECOVERY_PARAMETERS", "outbox_id is required.")
        if operation == "abort_prepared_commit" and not isinstance(result.get("commit_id"), str):
            raise RuntimeErrorBase("INVALID_RECOVERY_PARAMETERS", "commit_id is required.")
        if operation == "replay_core_projection":
            names = result.get("projection_names")
            if not isinstance(names, list) or not names or not all(isinstance(name, str) for name in names):
                raise RuntimeErrorBase("INVALID_RECOVERY_PARAMETERS", "projection_names is required.")
        return result

    def _run(self, project_id: str, operation: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if operation == "retry_outbox_item":
            outbox_id = parameters["outbox_id"]
            with self.database.connect() as conn:
                row = conn.execute("SELECT status FROM outbox WHERE project_id=? AND outbox_id=?", (project_id, outbox_id)).fetchone()
                if not row:
                    raise NotFoundError("OUTBOX_ITEM_NOT_FOUND", "Retry item not found.")
                if row["status"] not in {"pending", "failed"}:
                    raise ConflictError("OUTBOX_ITEM_NOT_RETRYABLE", "Retry item is not pending or failed.")
            result = OutboxWorker(self.database).run(__import__("story_runtime.contracts", fromlist=["OutboxRunRequest"]).OutboxRunRequest(
                request_id=uuid4(), project_id=project_id, limit=1, retry_failed=True, admin_scope="story-runtime.outbox.run",
            ))
            return result.model_dump(mode="json")
        if operation == "rebuild_lexical_index":
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("INSERT INTO retrieval_fts(retrieval_fts) VALUES('rebuild')")
                conn.commit()
            return {"rebuilt": "lexical", "authoritative_data_changed": False}
        if operation == "rebuild_vector_index":
            return {"rebuilt": "vector", "status": "not_configured", "authoritative_data_changed": False}
        if operation == "replay_core_projection":
            project = self.repository.get_project(project_id)
            result = ChapterCommitService(self.database).replay(ReplayProjectionsRequest(
                request_id=uuid4(), idempotency_key=f"studio-replay-{uuid4()}", project_id=project_id,
                schema_version=SCHEMA_VERSION, expected_revision=project["revision"],
                projection_names=parameters["projection_names"], from_event_sequence=0,
                verify_only=False, target_revision=project["revision"],
            ))
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                placeholders = ",".join("?" for _ in parameters["projection_names"])
                conn.execute(
                    f"UPDATE runtime_incidents SET resolved_at=? WHERE project_id=? AND resolved_at IS NULL AND retryable=1 AND component IN ({placeholders})",
                    (_now(), project_id, *parameters["projection_names"]),
                )
                conn.commit()
            return result.model_dump(mode="json")
        if operation == "abort_prepared_commit":
            commit_id = parameters["commit_id"]
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT state,chapter_number,request_id,idempotency_key,expected_revision,schema_version FROM chapter_commits WHERE project_id=? AND commit_id=?", (project_id, commit_id)).fetchone()
                if not row:
                    conn.rollback(); raise NotFoundError("COMMIT_NOT_FOUND", "Prepared commit not found.")
                if row["state"] not in {"PREPARED", "VALIDATED"}:
                    conn.rollback(); raise ConflictError("COMMIT_NOT_ABORTABLE", "Only a prepared or validated commit can be aborted.")
                now = _now()
                conn.execute("UPDATE chapter_commits SET state='ABORTED',updated_at=? WHERE commit_id=?", (now, commit_id))
                conn.execute(
                    "INSERT INTO commit_transitions(commit_id,from_state,to_state,reason,request_id,idempotency_key,project_id,chapter_number,expected_revision,resulting_revision,schema_version,created_at) VALUES (?,?, 'ABORTED','studio confirmed abort',?,?,?,?,?,NULL,?,?)",
                    (commit_id, row["state"], row["request_id"], row["idempotency_key"], project_id, row["chapter_number"], row["expected_revision"], row["schema_version"], now),
                )
                conn.commit()
            return {"commit_id": commit_id, "state": "ABORTED"}
        if operation == "clear_retry_queue":
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                removed = conn.execute("DELETE FROM outbox WHERE project_id=? AND status='failed'", (project_id,)).rowcount
                conn.commit()
            return {"cleared": removed, "authoritative_data_changed": False}
        if operation == "resume_interrupted_migration":
            return {"schema_version": self.database.migrations.migrate()}
        raise ConflictError("RECOVERY_OPERATION_BLOCKED", "This recovery operation is not available.")

    def _finish(self, project_id: str, job_id: str, state: str, *, result: dict[str, Any] | None = None,
                error: tuple[str, str] | None = None, actor: str) -> None:
        now = _now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE recovery_jobs SET state=?,progress=?,result_json=?,error_code=?,error_message=?,updated_at=?,completed_at=? WHERE job_id=?",
                (state, 100, json.dumps(redact(result), ensure_ascii=False) if result is not None else None,
                 error[0] if error else None, redact_text(error[1]) if error else None, now, now, job_id),
            )
            self._audit(conn, job_id, project_id, "finish", state, actor, result or ({"error": error[0]} if error else {}))
            conn.commit()

    @staticmethod
    def _audit(conn: sqlite3.Connection, job_id: str, project_id: str, action: str, outcome: str, actor: str, details: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO recovery_audit(job_id,project_id,action,outcome,actor,details_json,created_at) VALUES (?,?,?,?,?,?,?)",
            (job_id, project_id, action, outcome, actor, json.dumps(redact(details), ensure_ascii=False), _now()),
        )
