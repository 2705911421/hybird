from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from uuid import UUID, uuid5

from . import SCHEMA_VERSION
from .contracts import (
    AppendEventsRequest,
    AppendEventsResult,
    TypedDiffCommandRequest,
    ChapterArtifacts,
    ChapterArtifactResult,
    CommitChapterRequest,
    CreateProjectRequest,
    FinalizedCommitResult,
    PrepareChapterRequest,
    PrepareChapterResult,
    ProjectCreatedResult,
    ReplayProjectionsRequest,
    ReplayProjectionsResult,
    StoryEventInput,
    ValidateChapterArtifactsRequest,
    ValidateChapterResult,
    ValidationIssue,
    ChapterReviewArtifact,
    StateMutationProposal,
    CommitRecoveryRequest,
    CommitRecoveryResult,
)
from .database import Database
from .errors import ConflictError, DatabaseUnavailableError, NotFoundError, RuntimeErrorBase
from .reviews import forbidden_agent_field


_NAMESPACE = UUID("6bc66f5d-3127-4ac8-9d51-e8ec2b520904")
_CORE_PROJECTIONS = {
    "entities": "entities",
    "relationships": "relationships",
    "facts": "facts",
    "timeline": "timeline",
    "threads": "narrative_threads",
    "summaries": "chapter_summaries",
}
_ALLOWED_TRANSITIONS = {
    None: {"PREPARED"},
    "PREPARED": {"VALIDATED", "REJECTED", "ABORTED"},
    "VALIDATED": {"PERSISTING", "ABORTED", "RECOVERY_REQUIRED"},
    "PERSISTING": {"COMMITTED", "RECOVERY_REQUIRED"},
    "COMMITTED": {"PROJECTING", "RECOVERY_REQUIRED"},
    "PROJECTING": {"FINALIZED", "RECOVERY_REQUIRED"},
    "RECOVERY_REQUIRED": {"PERSISTING", "ABORTED"},
    "REJECTED": set(),
    "ABORTED": set(),
    "FINALIZED": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _artifact_payload(artifacts: ChapterArtifacts) -> dict[str, Any]:
    return artifacts.model_dump(mode="json", exclude_none=True)


class ChapterCommitService:
    def __init__(self, database: Database, fault_injector: Callable[[str], None] | None = None, unified_review_enabled: bool = False):
        self.database = database
        self.fault_injector = fault_injector
        self.unified_review_enabled = unified_review_enabled

    def create_project(self, request: CreateProjectRequest) -> ProjectCreatedResult:
        request_hash = _hash(request.model_dump(mode="json", exclude={"request_id"}))
        now = _now()
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                previous = conn.execute(
                    "SELECT request_hash,result_json FROM idempotency_ledger WHERE project_id=? AND idempotency_key=?",
                    (request.project_id, request.idempotency_key),
                ).fetchone()
                if previous:
                    if previous["request_hash"] != request_hash:
                        raise ConflictError("IDEMPOTENCY_CONFLICT", "idempotency key was used with a different project payload")
                    conn.rollback()
                    return ProjectCreatedResult(**{**json.loads(previous["result_json"]), "replayed": True})
                existing = conn.execute("SELECT authority_mode,revision FROM projects WHERE project_id=?", (request.project_id,)).fetchone()
                if existing:
                    raise ConflictError("PROJECT_EXISTS", f"project already exists: {request.project_id}", current_revision=existing["revision"])
                conn.execute(
                    "INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) VALUES (?,0,'initialized',0,?,?,?,'runtime')",
                    (request.project_id, SCHEMA_VERSION, now, now),
                )
                result = ProjectCreatedResult(project_id=request.project_id, authority_mode="runtime", revision=0)
                conn.execute(
                    "INSERT INTO idempotency_ledger(project_id,idempotency_key,operation,result_json,created_at,request_hash,status_code) VALUES (?,?,'project.create',?,?,?,201)",
                    (request.project_id, request.idempotency_key, _json(result.model_dump(mode="json")), now, request_hash),
                )
                conn.commit()
                return result
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)

    def chapter(self, project_id: str, chapter_number: int) -> ChapterArtifactResult:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT c.project_id,c.chapter_number,c.resulting_revision,c.commit_id,a.title,a.body_text,a.summary,c.body_sha256,c.artifact_sha256,c.finalized_at FROM chapter_commits c JOIN chapter_artifacts a USING(commit_id) WHERE c.project_id=? AND c.chapter_number=? AND c.state='FINALIZED'",
                (project_id, chapter_number),
            ).fetchone()
        if not row:
            raise NotFoundError("CHAPTER_NOT_FOUND", f"finalized chapter not found: {chapter_number}")
        return ChapterArtifactResult(
            project_id=row["project_id"], chapter_number=row["chapter_number"], revision=row["resulting_revision"],
            commit_id=row["commit_id"], title=row["title"], body=row["body_text"], summary=row["summary"],
            body_sha256=row["body_sha256"], artifact_sha256=row["artifact_sha256"], finalized_at=row["finalized_at"],
        )

    def prepare(self, request: PrepareChapterRequest) -> PrepareChapterResult:
        request_payload = request.model_dump(mode="json", exclude={"request_id", "expires_in_seconds"})
        request_hash = _hash(request_payload)
        commit_id = str(uuid5(_NAMESPACE, f"{request.project_id}\0{request.idempotency_key}"))
        now = _now()
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT * FROM chapter_commits WHERE project_id=? AND idempotency_key=?",
                    (request.project_id, request.idempotency_key),
                ).fetchone()
                if existing:
                    if existing["request_hash"] != request_hash:
                        raise ConflictError("IDEMPOTENCY_CONFLICT", "idempotency key was used with a different prepare payload", current_revision=self._project_revision(conn, request.project_id))
                    conn.rollback()
                    return self._prepare_result(existing, replayed=True)
                project = self._runtime_project(conn, request.project_id)
                self._check_revision(project, request.expected_revision)
                if request.base_context_revision != request.expected_revision:
                    raise ConflictError("BASE_CONTEXT_CONFLICT", "base context revision does not match expected revision", current_revision=project["revision"])
                expected_chapter = int(project["latest_chapter"]) + 1
                if request.chapter_number != expected_chapter:
                    raise ConflictError("CHAPTER_SEQUENCE_CONFLICT", f"next chapter must be {expected_chapter}", current_revision=project["revision"])
                conn.execute(
                    "INSERT INTO chapter_commits(commit_id,project_id,chapter_number,request_id,idempotency_key,request_hash,expected_revision,state,schema_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'PREPARED',?,?,?)",
                    (commit_id, request.project_id, request.chapter_number, str(request.request_id), request.idempotency_key, request_hash, request.expected_revision, SCHEMA_VERSION, now, now),
                )
                self._transition(conn, commit_id, None, "PREPARED", "prepare accepted", now)
                result = self._prepare_result(conn.execute("SELECT * FROM chapter_commits WHERE commit_id=?", (commit_id,)).fetchone())
                conn.execute(
                    "INSERT INTO idempotency_ledger(project_id,idempotency_key,operation,result_json,created_at,request_hash,status_code) VALUES (?,?,'chapter.lifecycle',?,?,?,200)",
                    (request.project_id, request.idempotency_key, _json(result.model_dump(mode="json")), now, request_hash),
                )
                conn.commit()
                self._inject("prepare.after_commit")
                return result
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)

    def validate(self, request: ValidateChapterArtifactsRequest) -> ValidateChapterResult:
        artifact_payload = _artifact_payload(request.artifacts)
        artifact_hash = _hash(artifact_payload)
        issues = self._validate_artifacts(request.artifacts, request.project_id, request.expected_revision)
        now = _now()
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                commit = self._commit_for_request(conn, request.project_id, str(request.prepare_id), request.idempotency_key)
                self._check_revision(self._runtime_project(conn, request.project_id), request.expected_revision)
                if commit["chapter_number"] != request.artifacts.chapter_number:
                    raise ConflictError("CHAPTER_MISMATCH", "artifact chapter does not match prepared chapter")
                if commit["state"] == "VALIDATED":
                    if commit["artifact_sha256"] != artifact_hash:
                        raise ConflictError("ARTIFACT_CONFLICT", "validated commit was replayed with different artifacts")
                    conn.rollback()
                    return self._validation_result(commit, [], replayed=True)
                if commit["state"] == "FINALIZED":
                    if commit["artifact_sha256"] != artifact_hash:
                        raise ConflictError("ARTIFACT_CONFLICT", "finalized commit was replayed with different artifacts")
                    conn.rollback()
                    return self._validation_result(commit, [], replayed=True)
                if commit["state"] != "PREPARED":
                    raise ConflictError("ILLEGAL_COMMIT_STATE", f"cannot validate commit in {commit['state']} state")
                issues.extend(self._validate_authority_conflicts(conn, request.project_id, request.artifacts))
                if any(issue.severity == "blocking" for issue in issues):
                    self._transition(conn, commit["commit_id"], "PREPARED", "REJECTED", "blocking validation issues", now)
                    conn.execute(
                        "UPDATE chapter_commits SET state='REJECTED',body_sha256=?,artifact_sha256=?,error_code='VALIDATION_BLOCKED',error_details_json=?,updated_at=? WHERE commit_id=?",
                        (request.artifacts.body_sha256, artifact_hash, _json([issue.model_dump(mode="json") for issue in issues]), now, commit["commit_id"]),
                    )
                    conn.commit()
                    rejected = conn.execute("SELECT * FROM chapter_commits WHERE commit_id=?", (commit["commit_id"],)).fetchone()
                    return self._validation_result(rejected, issues)
                validation_token = hashlib.sha256(f"{commit['commit_id']}\0{artifact_hash}\0{SCHEMA_VERSION}".encode()).hexdigest()
                self._store_artifact(conn, commit, request.artifacts, artifact_hash, now)
                self._inject("validate.after_artifact")
                self._transition(conn, commit["commit_id"], "PREPARED", "VALIDATED", "artifact validation passed", now)
                conn.execute(
                    "UPDATE chapter_commits SET state='VALIDATED',body_sha256=?,artifact_sha256=?,validation_token=?,updated_at=?,error_code=NULL,error_details_json='{}' WHERE commit_id=?",
                    (request.artifacts.body_sha256, artifact_hash, validation_token, now, commit["commit_id"]),
                )
                conn.commit()
                self._inject("validate.after_commit")
                validated = conn.execute("SELECT * FROM chapter_commits WHERE commit_id=?", (commit["commit_id"],)).fetchone()
                return self._validation_result(validated, issues)
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)

    def commit(self, request: CommitChapterRequest) -> FinalizedCommitResult:
        artifact_hash = _hash(_artifact_payload(request.artifacts))
        now = _now()
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._inject("commit.after_begin")
                commit = self._commit_for_request(conn, request.project_id, str(request.prepare_id), request.idempotency_key)
                if commit["state"] == "FINALIZED":
                    if commit["artifact_sha256"] != artifact_hash:
                        raise ConflictError("ARTIFACT_CONFLICT", "finalized commit was replayed with different artifacts")
                    result = self._finalized_result(conn, commit, replayed=True)
                    conn.rollback()
                    return result
                if commit["state"] not in {"VALIDATED", "RECOVERY_REQUIRED"}:
                    raise ConflictError("ILLEGAL_COMMIT_STATE", f"cannot commit from {commit['state']} state")
                if commit["validation_token"] != request.validation_token or commit["artifact_sha256"] != artifact_hash:
                    raise ConflictError("VALIDATION_TOKEN_CONFLICT", "validation token or artifact checksum does not match")
                project = self._runtime_project(conn, request.project_id)
                self._check_revision(project, request.expected_revision)
                if self.unified_review_enabled:
                    self._check_review_gate(conn, request.project_id, request.artifacts.chapter_number, request.expected_revision, request.artifacts.body_sha256)
                resulting_revision = request.expected_revision + 1
                commit = self._set_state(conn, commit, "PERSISTING", "commit transaction started", now)
                events = self._append_commit_events(conn, commit, request.artifacts.events, resulting_revision, now)
                commit = self._set_state(conn, commit, "COMMITTED", "artifact and events persisted", now, resulting_revision)
                commit = self._set_state(conn, commit, "PROJECTING", "core projection reducers started", now, resulting_revision)
                for event in events:
                    self._inject("commit.reducer")
                    self._apply_event(conn, request.project_id, event, resulting_revision)
                conn.execute(
                    "INSERT INTO chapter_summaries(project_id,chapter_number,title,summary,body_sha256) VALUES (?,?,?,?,?) ON CONFLICT(project_id,chapter_number) DO UPDATE SET title=excluded.title,summary=excluded.summary,body_sha256=excluded.body_sha256",
                    (request.project_id, request.artifacts.chapter_number, request.artifacts.title, request.artifacts.summary, request.artifacts.body_sha256),
                )
                conn.execute(
                    "UPDATE projects SET revision=?,latest_chapter=?,phase='drafting',updated_at=?,runtime_finalized_at=COALESCE(runtime_finalized_at,?) WHERE project_id=? AND revision=?",
                    (resulting_revision, request.artifacts.chapter_number, now, now, request.project_id, request.expected_revision),
                )
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ConflictError("REVISION_CONFLICT", "project revision changed during commit", current_revision=self._project_revision(conn, request.project_id))
                projection_hash = self._update_checkpoints(conn, request.project_id, resulting_revision, now)
                self._inject("commit.before_finalize")
                self._transition(conn, commit["commit_id"], "PROJECTING", "FINALIZED", "core projections and revision finalized", now, resulting_revision)
                conn.execute(
                    "UPDATE chapter_commits SET state='FINALIZED',resulting_revision=?,updated_at=?,finalized_at=?,error_code=NULL,error_details_json='{}' WHERE commit_id=?",
                    (resulting_revision, now, now, commit["commit_id"]),
                )
                for topic in ("markdown.export", "search.index", "snapshot.create"):
                    conn.execute(
                        "INSERT INTO outbox(project_id,commit_id,topic,payload_json,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                        (request.project_id, commit["commit_id"], topic, _json({"chapter_number": request.artifacts.chapter_number, "revision": resulting_revision}), now, now),
                    )
                self._inject("commit.after_outbox")
                finalized = conn.execute("SELECT * FROM chapter_commits WHERE commit_id=?", (commit["commit_id"],)).fetchone()
                result = self._finalized_result(conn, finalized, projection_hash=projection_hash)
                conn.execute(
                    "UPDATE idempotency_ledger SET result_json=?,status_code=200 WHERE project_id=? AND idempotency_key=?",
                    (_json(result.model_dump(mode="json")), request.project_id, request.idempotency_key),
                )
                conn.commit()
                self._inject("commit.after_commit")
                return result
        except sqlite3.IntegrityError as exc:
            raise ConflictError("COMMIT_CONFLICT", "chapter or event was already finalized", details={"database": str(exc)}) from exc
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)

    def _check_review_gate(self, conn, project_id: str, chapter_number: int, revision: int, body_sha256: str) -> None:
        artifacts = conn.execute(
            "SELECT COUNT(*) FROM review_artifacts WHERE project_id=? AND chapter_number=? AND source_revision=? AND body_sha256=?",
            (project_id, chapter_number, revision, body_sha256),
        ).fetchone()[0]
        if not artifacts:
            raise ConflictError("REVIEW_REQUIRED", "no validated review artifact exists for the current body and revision")
        stale = conn.execute(
            "SELECT COUNT(*) FROM review_findings f JOIN review_artifacts a ON a.artifact_id=f.artifact_id WHERE f.project_id=? AND f.chapter_number=? AND a.source_revision=? AND a.body_sha256=? AND f.status='stale'",
            (project_id, chapter_number, revision, body_sha256),
        ).fetchone()[0]
        if stale:
            raise ConflictError("REVIEW_STALE", "stale or invalid review evidence prevents commit", details={"stale_count": stale})
        disagreement = conn.execute(
            "SELECT COUNT(*) FROM (SELECT f.fingerprint FROM review_findings f JOIN review_artifacts a ON a.artifact_id=f.artifact_id WHERE f.project_id=? AND f.chapter_number=? AND a.source_revision=? AND a.body_sha256=? GROUP BY f.fingerprint HAVING COUNT(DISTINCT f.severity)>1 OR COUNT(DISTINCT f.blocking)>1)",
            (project_id, chapter_number, revision, body_sha256),
        ).fetchone()[0]
        blocked = conn.execute(
            "SELECT DISTINCT f.fingerprint FROM review_findings f JOIN review_artifacts a ON a.artifact_id=f.artifact_id WHERE f.project_id=? AND f.chapter_number=? AND a.source_revision=? AND a.body_sha256=? AND f.blocking=1 AND f.status='open'",
            (project_id, chapter_number, revision, body_sha256),
        ).fetchall()
        decision = conn.execute(
            "SELECT decision,decision_json FROM human_review_decisions WHERE project_id=? AND chapter_number=? AND source_revision=? ORDER BY created_at DESC LIMIT 1",
            (project_id, chapter_number, revision),
        ).fetchone()
        if decision and decision[0] in {"reject", "request_changes"}:
            raise ConflictError("REVIEW_BLOCKED", f"human review decision is {decision[0]}")
        accepted = {
            row[0] for row in conn.execute(
                "SELECT fingerprint FROM ("
                "SELECT fingerprint,decision,ROW_NUMBER() OVER (PARTITION BY fingerprint ORDER BY created_at DESC,decision_id DESC) AS rank "
                "FROM review_finding_decisions WHERE project_id=? AND chapter_number=? AND source_revision=?"
                ") WHERE rank=1 AND decision='accept'",
                (project_id, chapter_number, revision),
            )
        }
        blocked = [row for row in blocked if row[0] not in accepted]
        human_reviewed = bool(decision and decision[0] == "approve")
        global_approve = bool(human_reviewed and not json.loads(decision[1]).get("finding_decisions"))
        if disagreement and not human_reviewed:
            raise ConflictError("REVIEWER_CONFLICT", "reviewer disagreement requires a human decision", details={"conflict_count": disagreement})
        if blocked and not global_approve:
            raise ConflictError("REVIEW_BLOCKED", "unresolved blocking review findings prevent commit", details={"blocking_count": len(blocked)})

    def replay(self, request: ReplayProjectionsRequest) -> ReplayProjectionsResult:
        unknown = sorted(set(request.projection_names) - set(_CORE_PROJECTIONS))
        if unknown:
            raise RuntimeErrorBase("UNKNOWN_PROJECTION", f"unknown projections: {', '.join(unknown)}")
        job_id = str(uuid5(_NAMESPACE, f"replay\0{request.project_id}\0{request.idempotency_key}"))
        now = _now()
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                project = self._runtime_project(conn, request.project_id)
                self._check_revision(project, request.expected_revision)
                previous = conn.execute("SELECT * FROM replay_jobs WHERE replay_job_id=?", (job_id,)).fetchone()
                if previous and previous["state"] in {"FINALIZED", "MISMATCH"}:
                    conn.rollback()
                    return self._replay_result(previous)
                if not previous:
                    conn.execute(
                        "INSERT INTO replay_jobs VALUES (?,?,?,?,?,?,?,?,?,NULL,'RUNNING','{}',?,NULL)",
                        (job_id, request.project_id, str(request.request_id), _json(request.projection_names), request.from_event_sequence, request.to_event_sequence, request.target_revision, int(request.verify_only), request.expected_hash, now),
                    )
                conn.execute("SAVEPOINT projection_replay")
                self._clear_projections(conn, request.project_id, request.projection_names)
                params: list[Any] = [request.project_id, request.from_event_sequence]
                where = "project_id=? AND sequence>=?"
                if request.to_event_sequence is not None:
                    where += " AND sequence<=?"
                    params.append(request.to_event_sequence)
                if request.target_revision is not None:
                    where += " AND applied_revision<=?"
                    params.append(request.target_revision)
                rows = conn.execute(f"SELECT * FROM story_events WHERE {where} ORDER BY sequence", params).fetchall()
                for row in rows:
                    if self._projection_for_aggregate(row["aggregate_type"]) in request.projection_names:
                        self._apply_event(conn, request.project_id, dict(row), row["applied_revision"] or project["revision"])
                if "summaries" in request.projection_names:
                    conn.execute(
                        "INSERT INTO chapter_summaries(project_id,chapter_number,title,summary,body_sha256) SELECT a.project_id,a.chapter_number,a.title,a.summary,a.body_sha256 FROM chapter_artifacts a JOIN chapter_commits c USING(commit_id) WHERE a.project_id=? AND c.state='FINALIZED'",
                        (request.project_id,),
                    )
                resulting_hash = self.projection_hash(conn, request.project_id, request.projection_names)
                matched = request.expected_hash is None or request.expected_hash == resulting_hash
                if request.verify_only:
                    conn.execute("ROLLBACK TO projection_replay")
                conn.execute("RELEASE projection_replay")
                if not request.verify_only:
                    self._update_checkpoints(conn, request.project_id, int(project["revision"]), _now())
                state = "FINALIZED" if matched else "MISMATCH"
                completed = _now()
                conn.execute(
                    "UPDATE replay_jobs SET resulting_hash=?,state=?,details_json=?,completed_at=? WHERE replay_job_id=?",
                    (resulting_hash, state, _json({"event_count": len(rows), "matched": matched}), completed, job_id),
                )
                conn.commit()
                return ReplayProjectionsResult(
                    replay_job_id=job_id, project_id=request.project_id, state=state,
                    verify_only=request.verify_only, projection_names=request.projection_names,
                    resulting_hash=resulting_hash, expected_hash=request.expected_hash,
                    matched=matched, event_count=len(rows),
                )
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)

    def append_operator_events(self, request: AppendEventsRequest) -> AppendEventsResult:
        if request.admin_scope != "story-runtime.events.append":
            raise ConflictError("OPERATOR_SCOPE_REQUIRED", "direct event append requires operator scope")
        request_hash = _hash(request.model_dump(mode="json", exclude={"request_id"}))
        now = _now()
        try:
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                previous = conn.execute(
                    "SELECT request_hash,result_json FROM idempotency_ledger WHERE project_id=? AND idempotency_key=?",
                    (request.project_id, request.idempotency_key),
                ).fetchone()
                if previous:
                    if previous["request_hash"] != request_hash:
                        raise ConflictError("IDEMPOTENCY_CONFLICT", "idempotency key was used with different operator events")
                    conn.rollback()
                    return AppendEventsResult(**{**json.loads(previous["result_json"]), "replayed": True})
                project = self._runtime_project(conn, request.project_id)
                self._check_revision(project, request.expected_revision)
                revision = request.expected_revision + 1
                stored: list[dict[str, Any]] = []
                commit_id = f"operator:{uuid5(_NAMESPACE, request.idempotency_key)}"
                for ordinal, event in enumerate(request.events):
                    raw = event.model_dump(mode="json", exclude={"event_id"}, exclude_none=True)
                    event_id = hashlib.sha256(f"{request.project_id}\0{commit_id}\0{ordinal}\0{_json(raw)}".encode()).hexdigest()
                    aggregate_id = event.aggregate_id or event.subject
                    chapter = int(event.payload.get("chapter_number", project["latest_chapter"]))
                    conn.execute(
                        "INSERT INTO story_events(project_id,event_id,event_type,subject,chapter_number,payload_json,evidence_json,confidence,commit_id,ordinal,aggregate_type,aggregate_id,schema_version,created_at,applied_revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (request.project_id, event_id, event.event_type, event.subject, chapter, _json(event.payload), _json(event.evidence), event.confidence, commit_id, ordinal, event.aggregate_type, aggregate_id, SCHEMA_VERSION, now, revision),
                    )
                    stored_event = {**raw, "event_id": event_id, "aggregate_id": aggregate_id, "chapter_number": chapter}
                    stored.append(stored_event)
                    self._apply_event(conn, request.project_id, stored_event, revision)
                conn.execute("UPDATE projects SET revision=?,updated_at=? WHERE project_id=? AND revision=?", (revision, now, request.project_id, request.expected_revision))
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ConflictError("REVISION_CONFLICT", "project revision changed during operator append", current_revision=self._project_revision(conn, request.project_id))
                projection_hash = self._update_checkpoints(conn, request.project_id, revision, now)
                result = AppendEventsResult(request_id=request.request_id, project_id=request.project_id, revision=revision, event_count=len(stored), projection_hash=projection_hash)
                conn.execute(
                    "INSERT INTO idempotency_ledger(project_id,idempotency_key,operation,result_json,created_at,request_hash,status_code) VALUES (?,?,'events.append',?,?,?,200)",
                    (request.project_id, request.idempotency_key, _json(result.model_dump(mode="json")), now, request_hash),
                )
                conn.execute(
                    "INSERT INTO outbox(project_id,commit_id,topic,payload_json,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (request.project_id, commit_id, "search.index", _json({"revision": revision}), now, now),
                )
                conn.commit()
                return result
        except sqlite3.OperationalError as exc:
            self._raise_operational(exc)

    def apply_typed_diff(self, request: TypedDiffCommandRequest) -> AppendEventsResult:
        """Validate and atomically apply a user-authored domain diff."""
        operator_request = AppendEventsRequest(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            project_id=request.project_id,
            schema_version=request.schema_version,
            expected_revision=request.expected_revision,
            events=request.events,
            reason=f"{request.actor}: {request.reason}",
            admin_scope="story-runtime.events.append",
        )
        with self.database.connect() as conn:
            replay = conn.execute(
                "SELECT 1 FROM idempotency_ledger WHERE project_id=? AND idempotency_key=?",
                (request.project_id, request.idempotency_key),
            ).fetchone()
        if replay:
            return self.append_operator_events(operator_request)
        allowed = {
            "entity.upsert": "entity",
            "relationship.upsert": "relationship",
            "fact.upsert": "fact",
            "timeline.upsert": "timeline",
            "thread.upsert": "narrative_thread",
            "thread.resolve": "narrative_thread",
            "thread.defer": "narrative_thread",
        }
        if forbidden := forbidden_agent_field(request.model_dump(mode="json")):
            raise ConflictError("FORBIDDEN_COMMAND_CAPABILITY", f"typed diff contains forbidden capability field: {forbidden}")
        for event in request.events:
            expected_aggregate = allowed.get(event.event_type)
            if expected_aggregate is None or event.aggregate_type != expected_aggregate:
                raise ConflictError("TYPED_DIFF_EVENT_INVALID", f"unsupported typed diff event: {event.event_type}/{event.aggregate_type}")
        with self.database.connect() as conn:
            project = self._runtime_project(conn, request.project_id)
            self._check_revision(project, request.expected_revision)
            probe = ChapterArtifacts(
                chapter_number=max(1, int(project["latest_chapter"]) or 1),
                title="typed-diff",
                body="",
                body_sha256=hashlib.sha256(b"").hexdigest(),
                events=request.events,
                outline_fulfillment={},
                summary="typed-diff",
                review={},
                state_mutation_proposal={},
                evidence_spans=[],
            )
            issues = self._validate_authority_conflicts(conn, request.project_id, probe)
        blocking = [issue for issue in issues if issue.severity == "blocking"]
        if blocking:
            raise ConflictError(
                "TYPED_DIFF_VALIDATION_FAILED",
                "typed diff conflicts with current authority",
                current_revision=request.expected_revision,
                details={"issues": [issue.model_dump(mode="json") for issue in blocking]},
            )
        return self.append_operator_events(operator_request)

    def recover(self, request: CommitRecoveryRequest) -> CommitRecoveryResult:
        if request.admin_scope != "story-runtime.commits.recover":
            raise ConflictError("OPERATOR_SCOPE_REQUIRED", "commit recovery requires operator scope")
        now = _now()
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            commit = self._commit_for_request(conn, request.project_id, str(request.commit_id), request.idempotency_key)
            if commit["state"] == "FINALIZED":
                conn.rollback()
                return CommitRecoveryResult(
                    request_id=request.request_id, project_id=request.project_id, commit_id=request.commit_id,
                    state="FINALIZED", resulting_revision=commit["resulting_revision"],
                    repair_action="none; commit was already finalized", replayed=True,
                )
            if request.action == "abort":
                if commit["state"] not in {"PREPARED", "VALIDATED", "RECOVERY_REQUIRED"}:
                    raise ConflictError("RECOVERY_REQUIRED", f"move {commit['state']} to recovery before aborting")
                self._transition(conn, commit["commit_id"], commit["state"], "ABORTED", request.reason, now)
                conn.execute("UPDATE chapter_commits SET state='ABORTED',updated_at=?,error_code='OPERATOR_ABORTED' WHERE commit_id=?", (now, commit["commit_id"]))
                conn.commit()
                return CommitRecoveryResult(
                    request_id=request.request_id, project_id=request.project_id, commit_id=request.commit_id,
                    state="ABORTED", repair_action="no retry; prepare a new commit with a new idempotency key",
                )
            if commit["state"] not in {"VALIDATED", "PERSISTING", "COMMITTED", "PROJECTING", "RECOVERY_REQUIRED"}:
                raise ConflictError("ILLEGAL_COMMIT_STATE", f"cannot recover commit in {commit['state']} state")
            if commit["state"] != "RECOVERY_REQUIRED":
                self._transition(conn, commit["commit_id"], commit["state"], "RECOVERY_REQUIRED", request.reason, now)
            conn.execute("DELETE FROM story_events WHERE commit_id=?", (commit["commit_id"],))
            self._rebuild_finalized_projections(conn, request.project_id)
            conn.execute(
                "UPDATE chapter_commits SET state='RECOVERY_REQUIRED',resulting_revision=NULL,updated_at=?,error_code='RECOVERY_RETRY',error_details_json=? WHERE commit_id=?",
                (now, _json({"reason": request.reason}), commit["commit_id"]),
            )
            conn.commit()
        artifacts = self._load_artifact(request.commit_id)
        finalized = self.commit(CommitChapterRequest(
            request_id=request.request_id, idempotency_key=request.idempotency_key,
            project_id=request.project_id, schema_version=SCHEMA_VERSION,
            expected_revision=commit["expected_revision"], prepare_id=request.commit_id,
            validation_token=commit["validation_token"], artifacts=artifacts,
        ))
        return CommitRecoveryResult(
            request_id=request.request_id, project_id=request.project_id, commit_id=request.commit_id,
            state="FINALIZED", resulting_revision=finalized.resulting_revision,
            repair_action="recovered from the stored validated artifact",
        )

    def projection_hash(self, conn: sqlite3.Connection, project_id: str, names: Iterable[str] | None = None) -> str:
        selected = sorted(names or _CORE_PROJECTIONS)
        payload: dict[str, Any] = {}
        for name in selected:
            table = _CORE_PROJECTIONS[name]
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            order = ",".join(columns)
            rows = conn.execute(f"SELECT * FROM {table} WHERE project_id=? ORDER BY {order}", (project_id,)).fetchall()
            payload[name] = [dict(row) for row in rows]
        return _hash(payload)

    def _validate_artifacts(self, artifacts: ChapterArtifacts, project_id: str | None = None, expected_revision: int | None = None) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        actual_body_hash = hashlib.sha256(artifacts.body.encode("utf-8")).hexdigest()
        if actual_body_hash != artifacts.body_sha256:
            issues.append(ValidationIssue(severity="blocking", code="BODY_HASH_MISMATCH", message="body_sha256 does not match UTF-8 chapter body"))
        if not artifacts.summary.strip():
            issues.append(ValidationIssue(severity="blocking", code="SUMMARY_REQUIRED", message="chapter summary is required"))
        seen_ids: set[str] = set()
        for ordinal, event in enumerate(artifacts.events):
            if event.event_id and event.event_id in seen_ids:
                issues.append(ValidationIssue(severity="blocking", code="DUPLICATE_EVENT_ID", message="event_id is duplicated in the artifact", event_ordinal=ordinal))
            if event.event_id:
                seen_ids.add(event.event_id)
            aggregate_id = event.aggregate_id or event.subject
            if not aggregate_id:
                issues.append(ValidationIssue(severity="blocking", code="AGGREGATE_ID_REQUIRED", message="event aggregate_id or subject is required", event_ordinal=ordinal))
            for evidence in event.evidence:
                start, end = evidence.get("start"), evidence.get("end")
                if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start or end > len(artifacts.body):
                    issues.append(ValidationIssue(severity="blocking", code="INVALID_EVIDENCE_SPAN", message="evidence span must reference the chapter body", event_ordinal=ordinal))
        if not artifacts.events:
            issues.append(ValidationIssue(severity="informational", code="NO_STATE_EVENTS", message="chapter has no proposed story-state mutations"))
        if self.unified_review_enabled:
            try:
                review = ChapterReviewArtifact.model_validate(artifacts.review)
                if project_id is not None and review.project_id != project_id:
                    issues.append(ValidationIssue(severity="blocking", code="REVIEW_SCOPE_MISMATCH", message="review project does not match the commit"))
                if review.chapter_number != artifacts.chapter_number:
                    issues.append(ValidationIssue(severity="blocking", code="REVIEW_SCOPE_MISMATCH", message="review chapter does not match the commit"))
                if expected_revision is not None and review.source_revision != expected_revision:
                    issues.append(ValidationIssue(severity="blocking", code="REVIEW_REVISION_MISMATCH", message="review targets a stale revision"))
                if review.body_sha256 != artifacts.body_sha256:
                    issues.append(ValidationIssue(severity="blocking", code="REVIEW_BODY_MISMATCH", message="review targets a different chapter body"))
            except Exception:
                issues.append(ValidationIssue(severity="blocking", code="TYPED_REVIEW_REQUIRED", message="Runtime-authority commit requires review-artifacts/v1"))
            try:
                proposal = StateMutationProposal.model_validate(artifacts.state_mutation_proposal)
                if forbidden := forbidden_agent_field(proposal.model_dump(mode="json")):
                    issues.append(ValidationIssue(severity="blocking", code="FORBIDDEN_AGENT_CAPABILITY", message=f"state proposal contains forbidden capability field: {forbidden}"))
                if project_id is not None and proposal.project_id != project_id:
                    issues.append(ValidationIssue(severity="blocking", code="PROPOSAL_SCOPE_MISMATCH", message="state proposal project does not match the commit"))
                if proposal.chapter_number != artifacts.chapter_number or proposal.body_sha256 != artifacts.body_sha256:
                    issues.append(ValidationIssue(severity="blocking", code="PROPOSAL_SCOPE_MISMATCH", message="state proposal chapter or body does not match the commit"))
                if expected_revision is not None and proposal.source_revision != expected_revision:
                    issues.append(ValidationIssue(severity="blocking", code="PROPOSAL_REVISION_MISMATCH", message="state proposal targets a stale revision"))
                for evidence in proposal.evidence:
                    valid = evidence.end_offset > evidence.start_offset and evidence.end_offset <= len(artifacts.body)
                    quoted_hash = hashlib.sha256(
                        artifacts.body[evidence.start_offset:evidence.end_offset].encode("utf-8")
                    ).hexdigest()
                    valid = valid and quoted_hash == evidence.quoted_hash
                    if not valid:
                        issues.append(ValidationIssue(severity="blocking", code="PROPOSAL_EVIDENCE_INVALID", message="state proposal evidence must hash a valid chapter-body span"))
                    elif evidence.status == "stale":
                        issues.append(ValidationIssue(severity="blocking", code="PROPOSAL_EVIDENCE_STALE", message="state proposal evidence must be current or remapped"))
            except Exception:
                issues.append(ValidationIssue(severity="blocking", code="TYPED_STATE_PROPOSAL_REQUIRED", message="Runtime-authority commit requires a typed StateMutationProposal"))
        return issues

    def _validate_authority_conflicts(self, conn: sqlite3.Connection, project_id: str, artifacts: ChapterArtifacts) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        proposed_entities = {event.aggregate_id or event.subject for event in artifacts.events if event.aggregate_type == "entity"}
        known_entities = {row[0] for row in conn.execute("SELECT entity_id FROM entities WHERE project_id=?", (project_id,))} | proposed_entities
        latest_timeline = conn.execute("SELECT sequence_key FROM timeline WHERE project_id=? ORDER BY sequence_key DESC LIMIT 1", (project_id,)).fetchone()

        for ordinal, event in enumerate(artifacts.events):
            payload = event.payload
            if event.aggregate_type == "relationship":
                for field in ("source_entity_id", "target_entity_id"):
                    entity_id = payload.get(field)
                    if not isinstance(entity_id, str) or entity_id not in known_entities:
                        issues.append(ValidationIssue(severity="blocking", code="UNKNOWN_RELATIONSHIP_ENTITY", message=f"relationship references unknown {field}", event_ordinal=ordinal))

            if event.aggregate_type == "fact":
                predicate = str(payload.get("predicate", event.event_type))
                current = conn.execute(
                    "SELECT value_json FROM facts WHERE project_id=? AND subject=? AND predicate=? AND valid_to_revision IS NULL ORDER BY valid_from_revision DESC LIMIT 1",
                    (project_id, event.subject, predicate),
                ).fetchone()
                current_value = json.loads(current[0]) if current else None
                next_value = payload.get("value")
                if event.subject not in known_entities and event.subject not in {"project", "world", "timeline", "narrative"}:
                    issues.append(ValidationIssue(severity="blocking", code="UNKNOWN_FACT_ENTITY", message="fact mutation references an unknown entity", event_ordinal=ordinal))
                if "expected_previous_value" in payload and current_value != payload["expected_previous_value"]:
                    issues.append(ValidationIssue(severity="blocking", code="FACT_CAS_CONFLICT", message="fact expected_previous_value does not match authority", event_ordinal=ordinal))
                normalized = predicate.casefold()
                if normalized.endswith("status") and str(current_value).casefold() in {"dead", "deceased", "死亡", "已死亡"} and str(next_value).casefold() not in {"dead", "deceased", "死亡", "已死亡"} and not payload.get("revival_explanation"):
                    issues.append(ValidationIssue(severity="blocking", code="UNEXPLAINED_REVIVAL", message="a dead character cannot become active without a revival explanation", event_ordinal=ordinal))
                if normalized.endswith("location") and current is not None and current_value != next_value and not payload.get("transition_reason"):
                    issues.append(ValidationIssue(severity="blocking", code="LOCATION_TRANSITION_UNEXPLAINED", message="location change requires a transition reason", event_ordinal=ordinal))
                if normalized.startswith("world.rule") and current is not None and current_value != next_value and not payload.get("human_decision_id"):
                    issues.append(ValidationIssue(severity="blocking", code="WORLD_RULE_CONFLICT", message="world-rule change requires a human decision", event_ordinal=ordinal))
                for field in ("quantity", "balance", "remaining"):
                    if isinstance(payload.get(field), (int, float)) and payload[field] < 0:
                        issues.append(ValidationIssue(severity="blocking", code="NEGATIVE_RESOURCE", message=f"resource {field} cannot be negative", event_ordinal=ordinal))
                if isinstance(payload.get("resource_delta"), (int, float)) and isinstance(current_value, (int, float)) and current_value + payload["resource_delta"] < 0:
                    issues.append(ValidationIssue(severity="blocking", code="NEGATIVE_RESOURCE", message="resource delta would make authority negative", event_ordinal=ordinal))

            if event.aggregate_type == "timeline":
                sequence_key = str(payload.get("sequence_key", ""))
                if latest_timeline and sequence_key and sequence_key < str(latest_timeline[0]) and not payload.get("allows_reorder"):
                    issues.append(ValidationIssue(severity="blocking", code="TIMELINE_REVERSED", message="timeline mutation precedes the current authority position", event_ordinal=ordinal))

            if event.aggregate_type == "narrative_thread" and payload.get("major") is True and payload.get("status") in {"deleted", "abandoned", "resolved"} and not payload.get("human_decision_id"):
                issues.append(ValidationIssue(severity="blocking", code="MAJOR_FORESHADOWING_REQUIRES_HUMAN", message="major foreshadowing changes require a human decision", event_ordinal=ordinal))
        return issues

    def _store_artifact(self, conn: sqlite3.Connection, commit: sqlite3.Row, artifacts: ChapterArtifacts, checksum: str, now: str) -> None:
        conn.execute(
            "INSERT INTO chapter_artifacts(commit_id,project_id,chapter_number,title,body_text,summary,outline_fulfillment_json,review_json,state_mutation_proposal_json,evidence_spans_json,events_json,schema_version,body_sha256,checksum,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (commit["commit_id"], commit["project_id"], artifacts.chapter_number, artifacts.title, artifacts.body, artifacts.summary,
             _json(artifacts.outline_fulfillment), _json(artifacts.review or {}), _json(artifacts.state_mutation_proposal),
             _json(artifacts.evidence_spans), _json([event.model_dump(mode="json", exclude_none=True) for event in artifacts.events]),
             SCHEMA_VERSION, artifacts.body_sha256, checksum, now),
        )

    def _append_commit_events(self, conn: sqlite3.Connection, commit: sqlite3.Row, events: list[StoryEventInput], revision: int, now: str) -> list[dict[str, Any]]:
        stored: list[dict[str, Any]] = []
        for ordinal, event in enumerate(events):
            if ordinal > 0:
                self._inject("commit.events_midpoint")
            raw = event.model_dump(mode="json", exclude={"event_id"}, exclude_none=True)
            event_id = hashlib.sha256(f"{commit['project_id']}\0{commit['commit_id']}\0{ordinal}\0{_json(raw)}".encode()).hexdigest()
            aggregate_id = event.aggregate_id or event.subject
            conn.execute(
                "INSERT INTO story_events(project_id,event_id,event_type,subject,chapter_number,payload_json,evidence_json,confidence,commit_id,ordinal,aggregate_type,aggregate_id,schema_version,created_at,applied_revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (commit["project_id"], event_id, event.event_type, event.subject, commit["chapter_number"], _json(event.payload), _json(event.evidence), event.confidence,
                 commit["commit_id"], ordinal, event.aggregate_type, aggregate_id, SCHEMA_VERSION, now, revision),
            )
            stored.append({**raw, "event_id": event_id, "aggregate_id": aggregate_id, "ordinal": ordinal, "sequence": conn.execute("SELECT last_insert_rowid()").fetchone()[0]})
        return stored

    def _load_artifact(self, commit_id: UUID) -> ChapterArtifacts:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM chapter_artifacts WHERE commit_id=?", (str(commit_id),)).fetchone()
        if row is None:
            raise ConflictError("ARTIFACT_NOT_RECOVERABLE", "validated artifact is missing")
        return ChapterArtifacts(
            chapter_number=row["chapter_number"], title=row["title"], body=row["body_text"],
            summary=row["summary"], body_sha256=row["body_sha256"],
            events=json.loads(row["events_json"]),
            outline_fulfillment=json.loads(row["outline_fulfillment_json"]),
            review=json.loads(row["review_json"]),
            state_mutation_proposal=json.loads(row["state_mutation_proposal_json"]),
            evidence_spans=json.loads(row["evidence_spans_json"]),
        )

    def _rebuild_finalized_projections(self, conn: sqlite3.Connection, project_id: str) -> None:
        self._clear_projections(conn, project_id, _CORE_PROJECTIONS)
        rows = conn.execute(
            "SELECT e.* FROM story_events e JOIN chapter_commits c ON c.commit_id=e.commit_id "
            "WHERE e.project_id=? AND c.state='FINALIZED' ORDER BY e.sequence", (project_id,),
        ).fetchall()
        for row in rows:
            self._apply_event(conn, project_id, dict(row), row["applied_revision"] or 0)
        conn.execute(
            "INSERT INTO chapter_summaries(project_id,chapter_number,title,summary,body_sha256) "
            "SELECT a.project_id,a.chapter_number,a.title,a.summary,a.body_sha256 FROM chapter_artifacts a "
            "JOIN chapter_commits c USING(commit_id) WHERE a.project_id=? AND c.state='FINALIZED'",
            (project_id,),
        )

    def _apply_event(self, conn: sqlite3.Connection, project_id: str, event: dict[str, Any], revision: int) -> None:
        aggregate_type = event.get("aggregate_type") or "fact"
        aggregate_id = event.get("aggregate_id") or event.get("subject")
        payload = event.get("payload")
        if payload is None:
            payload = json.loads(event["payload_json"])
        event_id = event.get("event_id")
        chapter = event.get("chapter_number") or payload.get("chapter_number") or 0
        if aggregate_type == "entity":
            conn.execute(
                "INSERT INTO entities(project_id,entity_id,entity_type,canonical_name,aliases_json,attributes_json,history_json) VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id,entity_id) DO UPDATE SET entity_type=excluded.entity_type,canonical_name=excluded.canonical_name,aliases_json=excluded.aliases_json,attributes_json=excluded.attributes_json,history_json=json_insert(entities.history_json,'$[#]',json(?))",
                (project_id, aggregate_id, payload.get("entity_type", "character"), payload.get("canonical_name", aggregate_id), _json(payload.get("aliases", [])), _json(payload.get("attributes", {})), _json([{"revision": revision, "event_id": event_id}]), _json({"revision": revision, "event_id": event_id})),
            )
        elif aggregate_type == "relationship":
            conn.execute(
                "INSERT INTO relationships(project_id,relationship_id,source_entity_id,target_entity_id,relationship_type,attributes_json) VALUES (?,?,?,?,?,?) ON CONFLICT(project_id,relationship_id) DO UPDATE SET source_entity_id=excluded.source_entity_id,target_entity_id=excluded.target_entity_id,relationship_type=excluded.relationship_type,attributes_json=excluded.attributes_json",
                (project_id, aggregate_id, payload["source_entity_id"], payload["target_entity_id"], payload.get("relationship_type", "related"), _json(payload.get("attributes", {}))),
            )
        elif aggregate_type == "timeline":
            conn.execute(
                "INSERT INTO timeline(project_id,timeline_id,sequence_key,title,event_id,details_json) VALUES (?,?,?,?,?,?) ON CONFLICT(project_id,timeline_id) DO UPDATE SET sequence_key=excluded.sequence_key,title=excluded.title,event_id=excluded.event_id,details_json=excluded.details_json",
                (project_id, aggregate_id, str(payload.get("sequence_key", f"chapter-{chapter:06d}")), payload.get("title", aggregate_id), event_id, _json(payload.get("details", payload))),
            )
        elif aggregate_type == "narrative_thread":
            conn.execute(
                "INSERT INTO narrative_threads(project_id,thread_id,title,status,introduced_chapter,resolved_chapter,details_json) VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id,thread_id) DO UPDATE SET title=excluded.title,status=excluded.status,resolved_chapter=excluded.resolved_chapter,details_json=excluded.details_json",
                (project_id, aggregate_id, payload.get("title", aggregate_id), payload.get("status", "open"), payload.get("introduced_chapter", chapter), payload.get("resolved_chapter"), _json(payload.get("details", {}))),
            )
        elif aggregate_type == "fact":
            predicate = payload.get("predicate", event.get("event_type", "fact.updated"))
            subject = event.get("subject") or aggregate_id
            conn.execute(
                "UPDATE facts SET valid_to_revision=? WHERE project_id=? AND subject=? AND predicate=? AND valid_to_revision IS NULL",
                (revision, project_id, subject, predicate),
            )
            conn.execute(
                "INSERT INTO facts(project_id,fact_id,subject,predicate,value_json,valid_from_revision,valid_to_revision) VALUES (?,?,?,?,?,?,NULL)",
                (project_id, f"fact:{event_id}", subject, predicate, _json(payload.get("value", payload)), revision),
            )

    def _clear_projections(self, conn: sqlite3.Connection, project_id: str, names: Iterable[str]) -> None:
        for name in names:
            conn.execute(f"DELETE FROM {_CORE_PROJECTIONS[name]} WHERE project_id=?", (project_id,))

    def _projection_for_aggregate(self, aggregate_type: str | None) -> str:
        return {"entity": "entities", "relationship": "relationships", "fact": "facts", "timeline": "timeline", "narrative_thread": "threads"}.get(aggregate_type or "fact", "facts")

    def _update_checkpoints(self, conn: sqlite3.Connection, project_id: str, revision: int, now: str) -> str:
        event_offset = int(conn.execute("SELECT COALESCE(MAX(sequence),0) FROM story_events WHERE project_id=?", (project_id,)).fetchone()[0])
        for name in _CORE_PROJECTIONS:
            state_hash = self.projection_hash(conn, project_id, [name])
            conn.execute(
                "INSERT INTO projection_checkpoints(project_id,projection_name,status,checkpoint,retry_count,last_error,updated_at,applied_revision,event_offset,state_hash) VALUES (?,?,'ready',?,0,NULL,?,?,?,?) ON CONFLICT(project_id,projection_name) DO UPDATE SET status='ready',checkpoint=excluded.checkpoint,last_error=NULL,updated_at=excluded.updated_at,applied_revision=excluded.applied_revision,event_offset=excluded.event_offset,state_hash=excluded.state_hash",
                (project_id, name, revision, now, revision, event_offset, state_hash),
            )
        return self.projection_hash(conn, project_id)

    def _runtime_project(self, conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if not row:
            raise NotFoundError("PROJECT_NOT_FOUND", f"project not found: {project_id}")
        if row["authority_mode"] != "runtime":
            raise ConflictError("PROJECT_NOT_RUNTIME_AUTHORITY", "project is not configured for Runtime authority", current_revision=row["revision"])
        return row

    def _project_revision(self, conn: sqlite3.Connection, project_id: str) -> int:
        row = conn.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
        return int(row[0]) if row else 0

    def _check_revision(self, project: sqlite3.Row, expected: int) -> None:
        if int(project["revision"]) != expected:
            raise ConflictError("REVISION_CONFLICT", f"expected revision {expected}, current revision is {project['revision']}", current_revision=project["revision"], retryable=True)

    def _commit_for_request(self, conn: sqlite3.Connection, project_id: str, commit_id: str, key: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM chapter_commits WHERE commit_id=? AND project_id=? AND idempotency_key=?", (commit_id, project_id, key)).fetchone()
        if not row:
            raise NotFoundError("COMMIT_NOT_FOUND", "prepared commit was not found")
        return row

    def _transition(self, conn: sqlite3.Connection, commit_id: str, from_state: str | None, to_state: str, reason: str, now: str, resulting_revision: int | None = None) -> None:
        if to_state not in _ALLOWED_TRANSITIONS.get(from_state, set()):
            raise ConflictError("ILLEGAL_STATE_TRANSITION", f"illegal commit transition {from_state or 'NONE'} -> {to_state}")
        commit = conn.execute("SELECT * FROM chapter_commits WHERE commit_id=?", (commit_id,)).fetchone()
        conn.execute(
            "INSERT INTO commit_transitions(commit_id,from_state,to_state,reason,request_id,idempotency_key,project_id,chapter_number,expected_revision,resulting_revision,schema_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (commit_id, from_state, to_state, reason, commit["request_id"], commit["idempotency_key"], commit["project_id"], commit["chapter_number"], commit["expected_revision"], resulting_revision, commit["schema_version"], now),
        )

    def _set_state(self, conn: sqlite3.Connection, commit: sqlite3.Row, state: str, reason: str, now: str, resulting_revision: int | None = None) -> sqlite3.Row:
        self._transition(conn, commit["commit_id"], commit["state"], state, reason, now, resulting_revision)
        conn.execute("UPDATE chapter_commits SET state=?,resulting_revision=COALESCE(?,resulting_revision),updated_at=? WHERE commit_id=?", (state, resulting_revision, now, commit["commit_id"]))
        return conn.execute("SELECT * FROM chapter_commits WHERE commit_id=?", (commit["commit_id"],)).fetchone()

    def _prepare_result(self, commit: sqlite3.Row, replayed: bool = False) -> PrepareChapterResult:
        return PrepareChapterResult(commit_id=commit["commit_id"], prepare_id=commit["commit_id"], project_id=commit["project_id"], chapter_number=commit["chapter_number"], state=commit["state"], current_revision=commit["expected_revision"], expected_revision=commit["expected_revision"], replayed=replayed)

    def _validation_result(self, commit: sqlite3.Row, issues: list[ValidationIssue], replayed: bool = False) -> ValidateChapterResult:
        return ValidateChapterResult(commit_id=commit["commit_id"], project_id=commit["project_id"], chapter_number=commit["chapter_number"], state=commit["state"], artifact_sha256=commit["artifact_sha256"] or "0" * 64, validation_token=commit["validation_token"], issues=issues, replayed=replayed)

    def _finalized_result(self, conn: sqlite3.Connection, commit: sqlite3.Row, replayed: bool = False, projection_hash: str | None = None) -> FinalizedCommitResult:
        event_count = int(conn.execute("SELECT COUNT(*) FROM story_events WHERE commit_id=?", (commit["commit_id"],)).fetchone()[0])
        return FinalizedCommitResult(commit_id=commit["commit_id"], project_id=commit["project_id"], chapter_number=commit["chapter_number"], state="FINALIZED", expected_revision=commit["expected_revision"], resulting_revision=commit["resulting_revision"], body_sha256=commit["body_sha256"], artifact_sha256=commit["artifact_sha256"], event_count=event_count, projection_hash=projection_hash or self.projection_hash(conn, commit["project_id"]), finalized_at=commit["finalized_at"], replayed=replayed)

    def _replay_result(self, job: sqlite3.Row) -> ReplayProjectionsResult:
        details = json.loads(job["details_json"])
        return ReplayProjectionsResult(replay_job_id=job["replay_job_id"], project_id=job["project_id"], state=job["state"], verify_only=bool(job["verify_only"]), projection_names=json.loads(job["projection_names_json"]), resulting_hash=job["resulting_hash"], expected_hash=job["expected_hash"], matched=bool(details.get("matched")), event_count=int(details.get("event_count", 0)))

    def _raise_operational(self, exc: sqlite3.OperationalError) -> None:
        if "locked" in str(exc).lower():
            raise DatabaseUnavailableError("DATABASE_LOCKED", "SQLite is locked; retry the same request", retryable=True, details={"repair": "retry same idempotency key"}) from exc
        raise exc

    def _inject(self, point: str) -> None:
        if self.fault_injector:
            self.fault_injector(point)
