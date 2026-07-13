from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from .contracts import (ChapterReviewArtifact, HumanReviewDecision, ReviewStatusResult,
                        ReviewValidationResult, StoreReviewDecisionRequest,
                        ValidateReviewsRequest, ValidateRevisionRequest, RevisionDiffResult, RevisionResult)
from .database import Database
from .errors import ConflictError, NotFoundError, RuntimeErrorBase

MAX_ARTIFACT_BYTES = 1_000_000
FORBIDDEN_AGENT_FIELDS = {"command", "commands", "shell", "exec", "file_path", "filepath", "path", "database", "db_write", "sql", "validator_policy", "system_prompt"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def forbidden_agent_field(value) -> str | None:
    if isinstance(value, list):
        return next((found for item in value if (found := forbidden_agent_field(item))), None)
    if not isinstance(value, dict): return None
    for key, child in value.items():
        if str(key).casefold() in FORBIDDEN_AGENT_FIELDS: return str(key)
        if found := forbidden_agent_field(child): return found
    return None


def finding_fingerprint(finding) -> str:
    locations = ",".join(f"{span.start_offset}:{span.end_offset}" for span in finding.evidence_spans)
    semantic = _normalize(f"{finding.message} {finding.rationale}")[:500]
    parts = [finding.category, ",".join(sorted(map(_normalize, finding.affected_entities))),
             ",".join(sorted(map(_normalize, finding.affected_facts))), locations,
             finding.deterministic_rule_id or "", semantic]
    return _hash("\0".join(parts))


def _request_hash(request) -> str:
    return _hash(_json(request.model_dump(mode="json", exclude={"request_id", "idempotency_key"})))


class ReviewService:
    def __init__(self, database: Database): self.database = database

    def validate(self, request: ValidateReviewsRequest) -> ReviewValidationResult:
        request_hash = _request_hash(request)
        body_hash = _hash(request.body)
        stale, fingerprints = [], {}
        for artifact in request.artifacts:
            encoded = _json(artifact.model_dump(mode="json"))
            if len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES:
                raise RuntimeErrorBase("ARTIFACT_TOO_LARGE", "review artifact exceeds 1 MB")
            if forbidden := forbidden_agent_field(artifact.model_dump(mode="json")):
                raise RuntimeErrorBase("FORBIDDEN_AGENT_CAPABILITY", f"review artifact contains forbidden capability field: {forbidden}")
            if artifact.project_id != request.project_id or artifact.chapter_number != request.chapter_number:
                raise ConflictError("REVIEW_SCOPE_MISMATCH", "artifact project or chapter does not match request")
            if artifact.source_revision != request.expected_revision:
                raise ConflictError("REVISION_CONFLICT", "review artifact targets a stale revision")
            if artifact.body_sha256 != body_hash:
                raise ConflictError("BODY_HASH_MISMATCH", "review artifact body hash does not match current body")
            for finding in artifact.findings:
                fp = finding_fingerprint(finding); fingerprints[finding.finding_id] = fp
                for span in finding.evidence_spans:
                    valid = span.end_offset > span.start_offset and span.end_offset <= len(request.body)
                    valid = valid and _hash(request.body[span.start_offset:span.end_offset]) == span.quoted_hash
                    if not valid:
                        stale.append(finding.finding_id)
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            replay = conn.execute("SELECT request_hash,result_json FROM review_operations WHERE project_id=? AND operation='reviews.validate' AND idempotency_key=?", (request.project_id, request.idempotency_key)).fetchone()
            if replay:
                if replay[0] != request_hash: raise ConflictError("IDEMPOTENCY_CONFLICT", "review validation key was reused with different content")
                conn.rollback()
                return ReviewValidationResult.model_validate({**json.loads(replay[1]), "replayed": True})
            project = conn.execute("SELECT revision,authority_mode FROM projects WHERE project_id=?", (request.project_id,)).fetchone()
            if not project: raise NotFoundError("PROJECT_NOT_FOUND", "project does not exist")
            if project["revision"] != request.expected_revision: raise ConflictError("REVISION_CONFLICT", "project revision changed", current_revision=project["revision"])
            for artifact in request.artifacts:
                payload = _json(artifact.model_dump(mode="json")); payload_hash = _hash(payload)
                old = conn.execute("SELECT payload_hash FROM review_artifacts WHERE artifact_id=?", (artifact.artifact_id,)).fetchone()
                if old and old[0] != payload_hash: raise ConflictError("ARTIFACT_ID_CONFLICT", "artifact id was reused with different content")
                if not old:
                    conn.execute("INSERT INTO review_artifacts VALUES (?,?,?,?,?,?,?,?,?)", (artifact.artifact_id, request.project_id, request.chapter_number, request.expected_revision, body_hash, artifact.reviewer_kind, payload, payload_hash, _now()))
                    for finding in artifact.findings:
                        status = "stale" if finding.finding_id in stale else finding.status
                        conn.execute("INSERT INTO review_findings VALUES (?,?,?,?,?,?,?,?,?)", (request.project_id, request.chapter_number, artifact.artifact_id, finding.finding_id, fingerprints[finding.finding_id], finding.severity, int(finding.blocking), status, _json(finding.model_dump(mode="json"))))
            status = self._status_with_conn(conn, request.project_id, request.chapter_number)
            result = ReviewValidationResult(project_id=request.project_id, chapter_number=request.chapter_number, accepted_artifact_ids=[a.artifact_id for a in request.artifacts], stale_finding_ids=sorted(set(stale)), blocking_finding_ids=status.blocking_finding_ids, fingerprints=fingerprints, status=status)
            conn.execute("INSERT INTO review_operations VALUES (?,?,?,?,?,?)", (request.project_id, request.idempotency_key, "reviews.validate", request_hash, _json(result.model_dump(mode="json")), _now()))
            conn.commit()
        return result

    def decision(self, request: StoreReviewDecisionRequest) -> HumanReviewDecision:
        decision = request.decision
        if decision.project_id != request.project_id or decision.source_revision != request.expected_revision:
            raise ConflictError("DECISION_SCOPE_MISMATCH", "decision scope or revision does not match request")
        payload = _json(decision.model_dump(mode="json")); payload_hash = _hash(payload)
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            project = conn.execute("SELECT revision FROM projects WHERE project_id=?", (request.project_id,)).fetchone()
            if not project: raise NotFoundError("PROJECT_NOT_FOUND", "project does not exist")
            if project[0] != request.expected_revision: raise ConflictError("REVISION_CONFLICT", "decision targets a stale revision", current_revision=project[0])
            old = conn.execute("SELECT payload_hash,decision_json FROM human_review_decisions WHERE decision_id=? OR (project_id=? AND idempotency_key=?)", (decision.decision_id, request.project_id, request.idempotency_key)).fetchone()
            if old:
                if old[0] != payload_hash: raise ConflictError("IDEMPOTENCY_CONFLICT", "decision identity was reused with different content")
                conn.rollback(); return HumanReviewDecision.model_validate_json(old[1])
            conn.execute("INSERT INTO human_review_decisions VALUES (?,?,?,?,?,?,?,?,?)", (decision.decision_id, request.project_id, decision.chapter_number, decision.source_revision, decision.decision, payload, payload_hash, request.idempotency_key, _now()))
            for finding_id, finding_decision in decision.finding_decisions.items():
                row = conn.execute("SELECT fingerprint FROM review_findings WHERE project_id=? AND chapter_number=? AND finding_id=?", (request.project_id, decision.chapter_number, finding_id)).fetchone()
                if not row: raise NotFoundError("FINDING_NOT_FOUND", f"finding does not exist: {finding_id}")
                conn.execute(
                    "INSERT INTO review_finding_decisions VALUES (?,?,?,?,?,?,?)",
                    (decision.decision_id, request.project_id, decision.chapter_number, decision.source_revision,
                     row[0], finding_decision, _now()),
                )
            conn.commit()
        return decision

    def validate_revision(self, request: ValidateRevisionRequest):
        request_hash = _request_hash(request)
        if request.plan.project_id != request.project_id or request.result.project_id != request.project_id or request.plan.chapter_number != request.chapter_number or request.result.chapter_number != request.chapter_number:
            raise ConflictError("REVISION_SCOPE_MISMATCH", "revision artifacts do not match request scope")
        if not request.plan.requires_reaudit:
            raise RuntimeErrorBase("REAUDIT_REQUIRED", "Runtime-authority revision plans must require re-audit")
        original_hash, revised_hash = _hash(request.original_body), _hash(request.revised_body)
        if request.plan.body_sha256 != original_hash or request.result.original_body_sha256 != original_hash or request.result.revised_body_sha256 != revised_hash:
            raise ConflictError("REVISION_HASH_MISMATCH", "revision body hashes do not match supplied bodies")
        if request.plan.source_revision != request.expected_revision or request.result.source_revision != request.expected_revision:
            raise ConflictError("REVISION_CONFLICT", "revision artifacts target a stale revision")
        if original_hash == revised_hash:
            raise RuntimeErrorBase("REVISION_UNCHANGED", "revision result must change the chapter body")
        for span in request.result.changed_spans:
            if span.end_offset < span.start_offset or span.end_offset > len(request.original_body):
                raise RuntimeErrorBase("INVALID_CHANGED_SPAN", "changed span is outside the original body")
        for locked in request.plan.locked_text:
            valid = locked.end_offset > locked.start_offset and locked.end_offset <= len(request.original_body)
            valid = valid and _hash(request.original_body[locked.start_offset:locked.end_offset]) == locked.quoted_hash
            if not valid:
                raise RuntimeErrorBase("INVALID_LOCKED_TEXT", "locked text evidence is stale or invalid")
            if any(span.start_offset < locked.end_offset and locked.start_offset < span.end_offset for span in request.result.changed_spans):
                raise RuntimeErrorBase("LOCKED_TEXT_CHANGED", "revision changed user-locked text")
        resolved = set(request.result.resolved_finding_ids)
        unresolved = set(request.result.unresolved_finding_ids)
        planned = set(request.plan.finding_ids)
        if resolved & unresolved or resolved | unresolved != planned:
            raise RuntimeErrorBase("REVISION_FINDING_MISMATCH", "resolved and unresolved findings must partition the revision plan")
        payload = _json(request.result.model_dump(mode="json"))
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            replay = conn.execute("SELECT request_hash,result_json FROM review_operations WHERE project_id=? AND operation='revisions.validate' AND idempotency_key=?", (request.project_id, request.idempotency_key)).fetchone()
            if replay:
                if replay[0] != request_hash: raise ConflictError("IDEMPOTENCY_CONFLICT", "revision validation key was reused with different content")
                conn.rollback()
                return request.result.model_validate_json(replay[1])
            project = conn.execute("SELECT revision FROM projects WHERE project_id=?", (request.project_id,)).fetchone()
            if not project: raise NotFoundError("PROJECT_NOT_FOUND", "project does not exist")
            if project[0] != request.expected_revision: raise ConflictError("REVISION_CONFLICT", "project revision changed", current_revision=project[0])
            old = conn.execute("SELECT payload_hash,result_json FROM revision_results WHERE result_id=?", (request.result.result_id,)).fetchone()
            if old:
                if old[0] != _hash(payload): raise ConflictError("IDEMPOTENCY_CONFLICT", "revision result id was reused with different content")
                conn.rollback(); return request.result
            known = {row[0] for row in conn.execute("SELECT finding_id FROM review_findings WHERE project_id=? AND chapter_number=?", (request.project_id, request.chapter_number))}
            unknown = sorted(set(request.plan.finding_ids) - known)
            if unknown: raise NotFoundError("FINDING_NOT_FOUND", f"revision plan references unknown findings: {', '.join(unknown)}")
            conn.execute("INSERT INTO revision_results(result_id,project_id,chapter_number,source_revision,original_body_sha256,revised_body_sha256,requires_reaudit,result_json,payload_hash,original_body_text,revised_body_text,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (request.result.result_id, request.project_id, request.chapter_number, request.expected_revision, original_hash, revised_hash, 1, payload, _hash(payload), request.original_body, request.revised_body, _now()))
            conn.execute("UPDATE review_findings SET status='stale' WHERE project_id=? AND chapter_number=?", (request.project_id, request.chapter_number))
            conn.execute("INSERT INTO review_operations VALUES (?,?,?,?,?,?)", (request.project_id, request.idempotency_key, "revisions.validate", request_hash, payload, _now()))
            conn.commit()
        return request.result

    def artifacts(self, project_id: str, chapter_number: int) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT artifact_json FROM review_artifacts WHERE project_id=? AND chapter_number=? ORDER BY created_at", (project_id, chapter_number)).fetchall()
            project = conn.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
            effective = self._effective_finding_decisions(conn, project_id, chapter_number, project[0]) if project else {}
            fingerprints = {
                row[0]: row[1] for row in conn.execute(
                    "SELECT finding_id,fingerprint FROM review_findings WHERE project_id=? AND chapter_number=?",
                    (project_id, chapter_number),
                )
            }
        artifacts = [json.loads(row[0]) for row in rows]
        for artifact in artifacts:
            for finding in artifact["findings"]:
                action = effective.get(fingerprints.get(finding["finding_id"], ""))
                if finding["status"] != "stale" and action:
                    finding["status"] = {"accept": "accepted", "reject": "rejected", "request_changes": "open"}[action]
        return artifacts

    def revision_diff(self, project_id: str, chapter_number: int) -> RevisionDiffResult:
        with self.database.connect() as conn:
            row = conn.execute("SELECT source_revision,original_body_text,revised_body_text,original_body_sha256,revised_body_sha256,result_json FROM revision_results WHERE project_id=? AND chapter_number=? ORDER BY created_at DESC LIMIT 1", (project_id, chapter_number)).fetchone()
        if not row: raise NotFoundError("REVISION_NOT_FOUND", "no validated revision exists for this chapter")
        result = RevisionResult.model_validate_json(row[5])
        return RevisionDiffResult(project_id=project_id, chapter_number=chapter_number, source_revision=row[0], original_body=row[1], revised_body=row[2], original_body_sha256=row[3], revised_body_sha256=row[4], changed_spans=result.changed_spans)

    def status(self, project_id: str, chapter_number: int) -> ReviewStatusResult:
        with self.database.connect() as conn:
            return self._status_with_conn(conn, project_id, chapter_number)

    def _status_with_conn(self, conn, project_id: str, chapter_number: int) -> ReviewStatusResult:
        project = conn.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if not project: raise NotFoundError("PROJECT_NOT_FOUND", "project does not exist")
        revised = conn.execute("SELECT revised_body_sha256 FROM revision_results WHERE project_id=? AND chapter_number=? AND source_revision=? ORDER BY created_at DESC LIMIT 1", (project_id, chapter_number, project[0])).fetchone()
        latest_artifact = conn.execute("SELECT body_sha256 FROM review_artifacts WHERE project_id=? AND chapter_number=? AND source_revision=? ORDER BY created_at DESC LIMIT 1", (project_id, chapter_number, project[0])).fetchone()
        body_filter = revised[0] if revised else (latest_artifact[0] if latest_artifact else None)
        artifact_count = conn.execute("SELECT COUNT(*) FROM review_artifacts WHERE project_id=? AND chapter_number=? AND source_revision=? AND (? IS NULL OR body_sha256=?)", (project_id, chapter_number, project[0], body_filter, body_filter)).fetchone()[0]
        findings = conn.execute("SELECT f.finding_id,f.blocking,f.status,f.fingerprint,f.severity FROM review_findings f JOIN review_artifacts a ON a.artifact_id=f.artifact_id WHERE f.project_id=? AND f.chapter_number=? AND a.source_revision=? AND (? IS NULL OR a.body_sha256=?)", (project_id, chapter_number, project[0], body_filter, body_filter)).fetchall()
        decision = conn.execute("SELECT decision,source_revision,decision_json FROM human_review_decisions WHERE project_id=? AND chapter_number=? ORDER BY created_at DESC LIMIT 1", (project_id, chapter_number)).fetchone()
        revision = project[0]
        effective_decisions = self._effective_finding_decisions(conn, project_id, chapter_number, revision)
        global_approve = bool(
            decision and decision[0] == "approve" and decision[1] == revision
            and not json.loads(decision[2]).get("finding_decisions")
        )
        blocked_by_fingerprint: dict[str, str] = {}
        for row in findings:
            if row[1] and row[2] == "open" and effective_decisions.get(row[3]) != "accept":
                blocked_by_fingerprint.setdefault(row[3], row[0])
        blocked_ids = list(blocked_by_fingerprint.values())
        opinions: dict[str, tuple[set[int], set[str]]] = {}
        for row in findings:
            blocking_values, severity_values = opinions.setdefault(row[3], (set(), set()))
            blocking_values.add(int(row[1])); severity_values.add(str(row[4]))
        reviewer_conflict = any(len(blocking) > 1 or len(severity) > 1 for blocking, severity in opinions.values())
        if not artifact_count: state, reasons = "unreviewed", ["no validated review artifact"]
        elif not findings: state, reasons = "clear", []
        elif any(row[2] == "stale" for row in findings): state, reasons = "stale", ["one or more findings contain stale or invalid evidence"]
        elif decision and decision[1] != revision: state, reasons = "stale", ["latest human decision targets a stale revision"]
        elif decision and decision[0] == "reject": state, reasons = "rejected", ["human reviewer rejected the chapter"]
        elif decision and decision[0] == "request_changes": state, reasons = "changes_requested", ["human reviewer requested changes"]
        elif reviewer_conflict and not (decision and decision[0] == "approve" and decision[1] == revision):
            state, reasons = "blocked", ["reviewers disagree on severity or blocking status"]
        else:
            state, reasons = ("clear", []) if not blocked_ids or global_approve else ("blocked", ["unresolved blocking findings"])
        return ReviewStatusResult(project_id=project_id, chapter_number=chapter_number, revision=revision, status=state, blocking_finding_ids=blocked_ids, requires_human=bool(blocked_ids) or reviewer_conflict, reasons=reasons)

    @staticmethod
    def _effective_finding_decisions(conn, project_id: str, chapter_number: int, revision: int) -> dict[str, str]:
        rows = conn.execute(
            "SELECT fingerprint,decision FROM review_finding_decisions "
            "WHERE project_id=? AND chapter_number=? AND source_revision=? ORDER BY created_at,decision_id",
            (project_id, chapter_number, revision),
        ).fetchall()
        return {row[0]: row[1] for row in rows}
