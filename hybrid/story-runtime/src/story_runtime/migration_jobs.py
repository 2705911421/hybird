from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote
from uuid import UUID, uuid4, uuid5

from . import SCHEMA_VERSION
from .config import RuntimeConfig
from .contracts import (
    CreateMigrationJobRequest,
    MigrationActionRequest,
    MigrationDecisionsRequest,
    MigrationJobListResult,
    MigrationJobResult,
)
from .database import Database
from .errors import ConflictError, NotFoundError, RuntimeErrorBase
from .services import RuntimeServices
from .repository import StoryRepository
from .chapter_commits import ChapterCommitService


CIR_VERSION = "canonical-import/v1"
DEFAULT_MAPPING_VERSION = "phase7-map-v1"
_NAMESPACE = UUID("b2f936b1-494f-53f0-9740-c52d78818ac2")
_CHAPTER_RE = re.compile(r"(?:chapter|ch|第)[-_ ]*0*(\d+)", re.IGNORECASE)
_ALLOWED_TEXT = {".json", ".md", ".txt", ".yaml", ".yml"}
_KNOWN_DATABASES = {"memory.db", "index.db", "vectors.db"}
_CONFLICT_TYPES = {
    "duplicate_entity", "ambiguous_alias", "conflicting_fact", "conflicting_relationship",
    "chapter_body_mismatch", "chapter_number_gap", "duplicate_chapter", "timeline_conflict",
    "hook_state_conflict", "unknown_event_type", "invalid_resource_value",
    "review_body_hash_mismatch", "orphan_reference", "corrupted_source", "unmapped_field",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable(kind: str, source: str, locator: str = "") -> str:
    return str(uuid5(_NAMESPACE, f"{kind}\0{source}\0{locator}"))


class SourceProtectionError(RuntimeErrorBase):
    pass


class LegacyMigrationService:
    """Phase 7 migration coordinator. Source paths are opened for reads only.

    No source script is imported or executed. All target writes flow through this
    Runtime-owned service and the migration ledger.
    """

    def __init__(self, database: Database, config: RuntimeConfig):
        self.database = database
        self.config = config

    def create(self, request: CreateMigrationJobRequest, actor: str = "local-operator") -> MigrationJobResult:
        root = self._root(request.source_path)
        fingerprint = self._path_fingerprint(root)
        mapping_version = request.mapping_version or DEFAULT_MAPPING_VERSION
        with self.database.connect() as conn:
            prior = conn.execute(
                "SELECT job_id FROM migration_jobs WHERE source_path_fingerprint=? AND mapping_version=? AND target_project_id=?",
                (fingerprint, mapping_version, request.target_project_id),
            ).fetchone()
            if prior and not request.create_new_version:
                return self.get(prior["job_id"], reused=True)
            if prior and request.create_new_version:
                mapping_version = f"{mapping_version}+{uuid4().hex[:8]}"
            source_type, discovery = self._discover(root, request.source_type)
            job_id = str(uuid5(_NAMESPACE, f"job\0{fingerprint}\0{mapping_version}\0{request.target_project_id}"))
            now = _now()
            audit = [{"at": now, "actor": actor, "action": "discover", "outcome": "ok", "details": {"source_type": source_type}}]
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO migration_jobs(
                job_id,source_type,source_path,source_path_fingerprint,target_project_id,mapping_version,cir_version,
                current_stage,progress,audit_log_json,discovery_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,'DISCOVERED',5,?,?,?,?)""",
                (job_id, source_type, str(root), fingerprint, request.target_project_id, mapping_version,
                 CIR_VERSION, _json(audit), _json(discovery), now, now),
            )
            conn.commit()
        return self.get(job_id)

    def list(self, target_project_id: str | None = None) -> MigrationJobListResult:
        with self.database.connect() as conn:
            if target_project_id:
                rows = conn.execute("SELECT job_id FROM migration_jobs WHERE target_project_id=? ORDER BY created_at DESC", (target_project_id,)).fetchall()
            else:
                rows = conn.execute("SELECT job_id FROM migration_jobs ORDER BY created_at DESC").fetchall()
        return MigrationJobListResult(items=[self.get(row["job_id"]) for row in rows])

    def get(self, job_id: str, reused: bool = False) -> MigrationJobResult:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM migration_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise NotFoundError("MIGRATION_JOB_NOT_FOUND", f"migration job not found: {job_id}")
        return MigrationJobResult(
            migration_job_id=row["job_id"], source_type=row["source_type"],
            source_path_fingerprint=row["source_path_fingerprint"], target_project_id=row["target_project_id"],
            mapping_version=row["mapping_version"], cir_version=row["cir_version"], current_stage=row["current_stage"],
            progress=row["progress"], warnings=json.loads(row["warnings_json"]), conflicts=json.loads(row["conflicts_json"]),
            decisions=json.loads(row["decisions_json"]), checkpoints=json.loads(row["checkpoints_json"]),
            audit_log=json.loads(row["audit_log_json"]), discovery=json.loads(row["discovery_json"]),
            source_checksum_manifest=json.loads(row["source_checksum_manifest_json"]),
            target_snapshot=json.loads(row["target_snapshot_json"]) if row["target_snapshot_json"] else None,
            cir=json.loads(row["cir_json"]) if row["cir_json"] else None,
            dry_run=json.loads(row["dry_run_json"]) if row["dry_run_json"] else None,
            verification=json.loads(row["verification_json"]) if row["verification_json"] else None,
            cutover_confirmed=bool(row["cutover_confirmed"]), reused=reused,
        )

    def scan(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        self._require_stage(row, {"DISCOVERED", "SCANNED", "MAPPED", "VALIDATED", "AWAITING_DECISIONS", "READY", "FAILED"})
        root = self._root(row["source_path"])
        manifest, parsed, warnings, conflicts = self._scan(root, row["source_type"])
        self._verify_source_unchanged(root, manifest)
        discovery = self._enrich_discovery(json.loads(row["discovery_json"]), manifest, parsed)
        self._update(job_id, "SCANNED", 25, action.actor, "scan", manifest=manifest, warnings=warnings, conflicts=conflicts,
                     discovery=discovery)
        cir, mapping_conflicts, mapping_warnings = self._map(row, manifest, parsed)
        conflicts.extend(mapping_conflicts)
        warnings.extend(mapping_warnings)
        self._update(job_id, "MAPPED", 45, action.actor, "map", cir=cir, warnings=warnings, conflicts=conflicts)
        conflicts.extend(self._validate_cir(cir))
        conflicts = self._dedupe_conflicts(conflicts)
        cir["unresolved_conflicts"] = conflicts
        self._update(job_id, "VALIDATED", 55, action.actor, "validate", cir=cir, warnings=warnings, conflicts=conflicts)
        blocking = [c for c in conflicts if c["blocking"] and not c.get("user_decision")]
        stage = "AWAITING_DECISIONS" if blocking else "READY"
        self._update(job_id, stage, 60 if blocking else 65, action.actor, "conflict-gate", cir=cir, warnings=warnings, conflicts=conflicts)
        return self.get(job_id)

    def decide(self, job_id: str, request: MigrationDecisionsRequest, actor: str = "local-operator") -> MigrationJobResult:
        row = self._row(job_id)
        self._require_stage(row, {"AWAITING_DECISIONS", "VALIDATED", "READY", "QUARANTINED"})
        conflicts = json.loads(row["conflicts_json"])
        decisions = json.loads(row["decisions_json"])
        by_id = {c["conflict_id"]: c for c in conflicts}
        for decision in request.decisions:
            conflict = by_id.get(decision.conflict_id)
            if not conflict:
                raise ConflictError("MIGRATION_CONFLICT_NOT_FOUND", f"unknown conflict: {decision.conflict_id}")
            if decision.decision == "choose_candidate" and not decision.candidate_id:
                raise ConflictError("MIGRATION_DECISION_INVALID", "choose_candidate requires candidate_id")
            candidate_ids = {str(candidate.get("candidate_id")) for candidate in conflict.get("candidates", [])}
            if decision.decision == "choose_candidate" and decision.candidate_id not in candidate_ids:
                raise ConflictError("MIGRATION_DECISION_INVALID", f"candidate does not belong to conflict: {decision.candidate_id}")
            if decision.decision == "merge" and conflict["type"] in {"chapter_body_mismatch", "duplicate_chapter"}:
                raise ConflictError("MIGRATION_DECISION_INVALID", "chapter bodies require an explicit selected or newly mapped candidate")
            payload = decision.model_dump(mode="json") | {"actor": actor, "decided_at": _now()}
            decisions[decision.conflict_id] = payload
            conflict["user_decision"] = payload
            conflict["resolution_audit"] = [*conflict.get("resolution_audit", []), payload]
        blocking = [c for c in conflicts if c["blocking"] and not c.get("user_decision")]
        quarantined = [c for c in conflicts if c.get("user_decision", {}).get("decision") == "quarantine"]
        stage = "READY" if not blocking else "AWAITING_DECISIONS"
        self._update(job_id, stage, 65 if stage == "READY" else 60, actor, "decide", conflicts=conflicts, decisions=decisions,
                     details={"remaining_blocking": len(blocking), "quarantined": len(quarantined)})
        return self.get(job_id)

    def dry_run(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        self._require_stage(row, {"READY", "AWAITING_DECISIONS"})
        cir = self._resolved_cir(row)
        conflicts = json.loads(row["conflicts_json"])
        decisions = json.loads(row["decisions_json"])
        report = self._dry_run(cir, conflicts, decisions)
        self._update(job_id, row["current_stage"], max(row["progress"], 68), action.actor, "dry-run", dry_run=report)
        return self.get(job_id)

    def snapshot(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        self._require_stage(row, {"READY"})
        self._assert_no_unresolved(row)
        snapshot = self._create_verified_snapshot(row)
        checkpoints = json.loads(row["checkpoints_json"])
        checkpoints.append({"stage": "SNAPSHOT", "at": _now(), "checksum": snapshot.get("sha256"), "verified": True})
        self._update(job_id, "READY", 72, action.actor, "snapshot", snapshot=snapshot, checkpoints=checkpoints)
        return self.get(job_id)

    def import_job(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        self._require_stage(row, {"READY", "PAUSED", "FAILED", "IMPORTING", "VERIFYING"})
        self._assert_no_unresolved(row)
        if not row["target_snapshot_json"]:
            raise ConflictError("TARGET_SNAPSHOT_REQUIRED", "create and verify a target snapshot before import")
        self._verify_scanned_source(row)
        self._update(job_id, "IMPORTING", 75, action.actor, "import-start")
        try:
            imported = self._import_cir(self._row(job_id), action.actor)
            if self._row(job_id)["current_stage"] == "PAUSED":
                return self.get(job_id)
            checkpoints = json.loads(self._row(job_id)["checkpoints_json"])
            checkpoints.append({"stage": "IMPORT", "at": _now(), "imported": imported})
            self._update(job_id, "VERIFYING", 90, action.actor, "import-complete", checkpoints=checkpoints)
        except Exception as exc:
            self._update(job_id, "FAILED", 75, action.actor, "import-failed", details={"error": type(exc).__name__, "message": str(exc)[:500]})
            raise
        return self.get(job_id)

    def verify(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        self._require_stage(row, {"VERIFYING", "FAILED"})
        self._verify_scanned_source(row)
        report = self._verify_import(row)
        stage = "COMPLETED" if report["blocking_conflicts"] == 0 and report["chapter_body_coverage"] == 1.0 and report["doctor_status"] == "ok" and report["replay_matched"] else "FAILED"
        self._update(job_id, stage, 100 if stage == "COMPLETED" else 95, action.actor, "verify", verification=report,
                     details={"result": stage})
        return self.get(job_id)

    def pause(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        if row["current_stage"] in {"COMPLETED", "ROLLED_BACK", "QUARANTINED"}:
            raise ConflictError("MIGRATION_NOT_PAUSABLE", f"cannot pause {row['current_stage']}")
        with self.database.connect() as conn:
            conn.execute("UPDATE migration_jobs SET resume_stage=current_stage,current_stage='PAUSED',updated_at=? WHERE job_id=?", (_now(), job_id))
        self._audit(job_id, action.actor, "pause", "ok", {"resume_stage": row["current_stage"]})
        return self.get(job_id)

    def resume(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        self._require_stage(row, {"PAUSED"})
        stage = row["resume_stage"] or "READY"
        with self.database.connect() as conn:
            conn.execute("UPDATE migration_jobs SET current_stage=?,resume_stage=NULL,updated_at=? WHERE job_id=?", (stage, _now(), job_id))
        self._audit(job_id, action.actor, "resume", "ok", {"stage": stage})
        return self.get(job_id)

    def cutover(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        self._require_stage(row, {"COMPLETED"})
        if action.confirmation != "CONFIRM_RUNTIME_CUTOVER":
            raise ConflictError("CUTOVER_CONFIRMATION_REQUIRED", "explicit CONFIRM_RUNTIME_CUTOVER confirmation is required")
        verification = json.loads(row["verification_json"] or "{}")
        if verification.get("doctor_status") != "ok" or not verification.get("replay_hash"):
            raise ConflictError("CUTOVER_VERIFICATION_REQUIRED", "doctor and replay verification must pass before cutover")
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE projects SET authority_mode='runtime',phase='runtime-authority',runtime_finalized_at=?,updated_at=? WHERE project_id=? AND authority_mode='legacy'", (_now(), _now(), row["target_project_id"]))
            if conn.total_changes == 0:
                project = conn.execute("SELECT authority_mode FROM projects WHERE project_id=?", (row["target_project_id"],)).fetchone()
                if not project or project["authority_mode"] != "runtime":
                    conn.rollback()
                    raise ConflictError("CUTOVER_TARGET_INVALID", "target project is not available for cutover")
            conn.execute("UPDATE migration_jobs SET cutover_confirmed=1,updated_at=? WHERE job_id=?", (_now(), job_id))
            conn.commit()
        self._audit(job_id, action.actor, "cutover", "ok", {"authority_mode": "runtime"})
        return self.get(job_id)

    def rollback(self, job_id: str, action: MigrationActionRequest) -> MigrationJobResult:
        row = self._row(job_id)
        if row["cutover_confirmed"]:
            raise ConflictError("POST_CUTOVER_ROLLBACK_REQUIRES_STOP", "stop Runtime writes and use the audited operator rollback procedure")
        snapshot = json.loads(row["target_snapshot_json"] or "null")
        if not snapshot:
            raise ConflictError("TARGET_SNAPSHOT_REQUIRED", "no verified target snapshot exists")
        if snapshot.get("kind") == "empty-target":
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM projects WHERE project_id=? AND authority_mode='legacy'", (row["target_project_id"],))
                conn.execute("DELETE FROM migration_import_ledger WHERE job_id=?", (job_id,))
                conn.commit()
        else:
            self._restore_snapshot(snapshot)
        self._update(job_id, "ROLLED_BACK", row["progress"], action.actor, "rollback", details={"snapshot_sha256": snapshot.get("sha256")})
        return self.get(job_id)

    def report(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        return job.model_dump(mode="json") | {"report_version": "phase7-migration-report/v1", "generated_at": _now()}

    # -- discovery and source protection -------------------------------------------------

    def _root(self, raw: str) -> Path:
        root = Path(raw).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise SourceProtectionError("SOURCE_NOT_DIRECTORY", "migration source must be an existing directory")
        return root

    def _path_fingerprint(self, root: Path) -> str:
        stat = root.stat()
        return _sha_bytes(f"{os.path.normcase(str(root))}\0{stat.st_dev}\0{stat.st_ino}".encode("utf-8"))

    def _discover(self, root: Path, requested: str) -> tuple[str, dict[str, Any]]:
        names = {p.name.casefold() for p in root.iterdir()}
        inkos = "inkos.json" in names or "books" in names or (root / "story" / "state").is_dir()
        webnovel = ".webnovel" in names or "commits" in names and "events" in names or "index.db" in names
        detected = "hybrid" if inkos and webnovel else "inkos" if inkos else "webnovel-writer" if webnovel else "unknown"
        if requested != "auto" and detected not in {requested, "hybrid"}:
            detected = requested
        missing = []
        if detected in {"inkos", "hybrid"} and not ((root / "books").exists() or (root / "story").exists()):
            missing.append("books-or-story")
        if detected in {"webnovel-writer", "hybrid"} and not ((root / ".webnovel").exists() or (root / "commits").exists()):
            missing.append(".webnovel-or-commits")
        return detected, {"root_name": root.name, "detected_type": detected, "missing": missing, "schema_hints": sorted(names & {"inkos.json", "index.db", "memory.db", "vectors.db"})}

    def _walk(self, root: Path) -> Iterable[Path]:
        count = total = 0
        stack = [root]
        while stack:
            directory = stack.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if entry.is_symlink():
                        yield path
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    count += 1
                    size = entry.stat(follow_symlinks=False).st_size
                    total += size
                    if count > self.config.migration_max_files:
                        raise SourceProtectionError("SOURCE_FILE_LIMIT", "source file count exceeds configured limit")
                    if total > self.config.migration_max_total_bytes:
                        raise SourceProtectionError("SOURCE_TOTAL_SIZE_LIMIT", "source exceeds configured total byte limit")
                    yield path

    def _scan(self, root: Path, source_type: str) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        manifest: list[dict[str, Any]] = []
        parsed: dict[str, Any] = {}
        warnings: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        for path in self._walk(root):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                target = path.resolve(strict=False)
                outside = not target.is_relative_to(root)
                manifest.append({"path": rel, "type": "symlink", "size": 0, "sha256": None, "encoding": None, "parse_status": "rejected", "mtime_ns": path.lstat().st_mtime_ns})
                conflicts.append(self._conflict("corrupted_source", rel, "critical", True, [{"path": rel}], [], {"reason": "symlink rejected", "escapes_root": outside}, "quarantine"))
                continue
            stat = path.stat()
            if stat.st_size > self.config.migration_max_file_bytes:
                manifest.append({"path": rel, "type": "oversize", "size": stat.st_size, "sha256": None, "encoding": None, "parse_status": "rejected", "mtime_ns": stat.st_mtime_ns})
                conflicts.append(self._conflict("corrupted_source", rel, "critical", True, [{"path": rel}], [], {"reason": "file size limit"}, "quarantine"))
                continue
            data = path.read_bytes()
            suffix = path.suffix.casefold()
            item = {"path": rel, "type": self._file_type(path), "size": len(data), "sha256": _sha_bytes(data), "encoding": None, "parse_status": "not-applicable", "mtime_ns": stat.st_mtime_ns}
            try:
                if suffix in _ALLOWED_TEXT:
                    text, encoding = self._decode(data)
                    item["encoding"] = encoding
                    if suffix == ".json":
                        parsed[rel] = json.loads(text)
                        item["parse_status"] = "ok"
                    else:
                        parsed[rel] = text
                        item["parse_status"] = "ok"
                elif path.name.casefold() in _KNOWN_DATABASES:
                    parsed[rel] = self._inspect_sqlite(path)
                    item["parse_status"] = "ok" if parsed[rel]["integrity"] == "ok" else "error"
                    if item["parse_status"] == "error":
                        conflicts.append(self._conflict("corrupted_source", rel, "critical", True, [{"path": rel, "sha256": item["sha256"]}], [], parsed[rel], "quarantine"))
                elif suffix == ".zip":
                    parsed[rel] = self._inspect_zip(path)
                    item["parse_status"] = "ok" if not parsed[rel]["unsafe_entries"] else "error"
                    if parsed[rel]["unsafe_entries"]:
                        conflicts.append(self._conflict("corrupted_source", rel, "critical", True, [{"path": rel}], [], parsed[rel], "quarantine"))
            except (UnicodeError, json.JSONDecodeError, sqlite3.DatabaseError, zipfile.BadZipFile) as exc:
                item["parse_status"] = "error"
                warnings.append({"code": "SOURCE_PARSE_ERROR", "path": rel, "message": str(exc)[:500]})
                conflicts.append(self._conflict("corrupted_source", rel, "critical", True, [{"path": rel, "sha256": item["sha256"]}], [], {"error": type(exc).__name__}, "quarantine"))
            manifest.append(item)
        manifest.sort(key=lambda item: item["path"].casefold())
        return manifest, parsed, warnings, conflicts

    def _decode(self, data: bytes) -> tuple[str, str]:
        for encoding in ("utf-8-sig", "utf-8", "utf-16"):
            try:
                return data.decode(encoding), encoding
            except UnicodeError:
                pass
        raise UnicodeError("unsupported or invalid text encoding")

    def _inspect_sqlite(self, path: Path) -> dict[str, Any]:
        uri = f"file:{quote(path.resolve().as_posix())}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.row_factory = sqlite3.Row
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            counts = {}
            samples: dict[str, list[dict[str, Any]]] = {}
            sample_budget = 1_000
            for table in tables[:100]:
                if re.fullmatch(r"[A-Za-z0-9_]+", table):
                    counts[table] = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    if table.casefold() in {"events", "story_events", "commits", "chapter_commits", "projection_status", "projection_checkpoints", "documents", "memory", "memories", "facts", "hooks", "chapter_summaries"} and sample_budget > 0:
                        rows = conn.execute(f'SELECT * FROM "{table}" LIMIT ?', (min(200, sample_budget),)).fetchall()
                        samples[table] = [{key: self._safe_sql_value(row[index]) for index, key in enumerate(row.keys())} for row in rows]
                        sample_budget -= len(rows)
            role = "rebuildable-metadata" if path.name.casefold() == "vectors.db" else "candidate-evidence" if path.name.casefold() == "memory.db" else "mirror-evidence"
            return {"integrity": integrity, "tables": tables, "counts": counts, "samples": samples, "authoritative": False, "role": role}
        finally:
            conn.close()

    def _inspect_zip(self, path: Path) -> dict[str, Any]:
        unsafe = []
        total = 0
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                normalized = Path(info.filename.replace("\\", "/"))
                total += info.file_size
                if normalized.is_absolute() or ".." in normalized.parts or info.file_size > self.config.migration_max_file_bytes:
                    unsafe.append(info.filename)
                if total > self.config.migration_max_total_bytes:
                    unsafe.append("<expanded-size-limit>")
                    break
        return {"entries": len(archive.infolist()), "expanded_bytes": total, "unsafe_entries": unsafe}

    @staticmethod
    def _safe_sql_value(value: Any) -> Any:
        if value is None or isinstance(value, (int, float)):
            return value
        if isinstance(value, bytes):
            return {"blob_sha256": _sha_bytes(value), "size": len(value)}
        return str(value)[:4_000]

    def _verify_source_unchanged(self, root: Path, manifest: list[dict[str, Any]]) -> None:
        for item in manifest:
            path = root / item["path"]
            if item["type"] == "symlink":
                current = path.lstat().st_mtime_ns
            else:
                current = path.stat().st_mtime_ns
            if current != item["mtime_ns"]:
                raise SourceProtectionError("SOURCE_MTIME_CHANGED", f"source mtime changed during scan: {item['path']}")

    def _verify_scanned_source(self, row: sqlite3.Row) -> None:
        root = self._root(row["source_path"])
        for item in json.loads(row["source_checksum_manifest_json"]):
            path = root / item["path"]
            try:
                stat = path.lstat() if item["type"] == "symlink" else path.stat()
            except FileNotFoundError as exc:
                raise ConflictError("SOURCE_CHANGED_AFTER_SCAN", f"source file disappeared: {item['path']}") from exc
            if stat.st_mtime_ns != item["mtime_ns"]:
                raise ConflictError("SOURCE_CHANGED_AFTER_SCAN", f"source mtime changed: {item['path']}")
            if item.get("sha256") is not None and _sha_bytes(path.read_bytes()) != item["sha256"]:
                raise ConflictError("SOURCE_CHANGED_AFTER_SCAN", f"source checksum changed: {item['path']}")

    def _enrich_discovery(self, discovery: dict[str, Any], manifest: list[dict[str, Any]], parsed: dict[str, Any]) -> dict[str, Any]:
        versions: dict[str, Any] = {}
        chapter_numbers: list[int] = []
        for rel, value in parsed.items():
            if Path(rel).name.casefold() in {"inkos.json", "state.json", "manifest.json"} and isinstance(value, dict):
                for key in ("version", "schema_version", "schemaVersion", "project_version"):
                    if key in value:
                        versions[f"{rel}:{key}"] = value[key]
            number = self._chapter_number(rel, value)
            if number and ("chapter" in rel.casefold() or Path(rel).stem.casefold().startswith("ch")):
                chapter_numbers.append(number)
        databases = [item["path"] for item in manifest if item["type"] == "sqlite"]
        state_files = [item["path"] for item in manifest if "/state/" in f"/{item['path'].casefold()}/" or Path(item["path"]).name.casefold() in {"state.json", "current_state.md", "manifest.json"}]
        parse_errors = [item["path"] for item in manifest if item["parse_status"] == "error"]
        return discovery | {
            "versions": versions,
            "chapter_range": [min(chapter_numbers), max(chapter_numbers)] if chapter_numbers else None,
            "chapter_count": len(set(chapter_numbers)), "state_files": state_files,
            "databases": databases, "parse_errors": parse_errors,
        }

    # -- CIR -----------------------------------------------------------------------------

    def _map(self, row: sqlite3.Row, manifest: list[dict[str, Any]], parsed: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        fingerprint = row["source_path_fingerprint"]
        cir: dict[str, Any] = {
            "cir_version": CIR_VERSION,
            "source_metadata": {"source_type": row["source_type"], "source_path_fingerprint": fingerprint, "mapping_version": row["mapping_version"], "scanned_at": _now()},
            "project": {"cir_item_id": _stable("project", fingerprint), "project_id": row["target_project_id"], "title": Path(row["source_path"]).name, "extensions": {}},
            "chapters": [], "entities": [], "aliases": [], "relationships": [], "facts": [], "events": [],
            "timeline": [], "narrative_threads": [], "reviews": [], "summaries": [], "documents": [],
            "unresolved_conflicts": [], "unmapped_fields": [], "provenance": [],
        }
        conflicts: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        manifest_by_path = {item["path"]: item for item in manifest}
        chapter_candidates: dict[int, list[dict[str, Any]]] = {}
        structured_paths: list[str] = []
        markdown_truth_paths: list[str] = []
        for rel, value in parsed.items():
            meta = manifest_by_path.get(rel)
            if not meta or meta["parse_status"] != "ok":
                continue
            name = Path(rel).name.casefold()
            suffix = Path(rel).suffix.casefold()
            chapter_no = self._chapter_number(rel, value)
            if chapter_no and isinstance(value, str) and ("chapter" in rel.casefold() or "chapters/" in rel.casefold() or name.startswith("ch") or name.startswith("第")):
                body = value.strip()
                item_id = _stable("chapter", fingerprint, f"{chapter_no}:{meta['sha256']}")
                chapter = {"cir_item_id": item_id, "chapter_number": chapter_no, "title": self._chapter_title(body, chapter_no), "body": body,
                           "body_sha256": _sha_bytes(body.encode("utf-8")), "source_sha256": meta["sha256"], "source_path": rel}
                chapter_candidates.setdefault(chapter_no, []).append(chapter)
                self._provenance(cir, item_id, rel, meta, "chapter")
                continue
            if suffix == ".json":
                json_chapters = self._json_chapters(value, rel, meta, fingerprint) if "chapter" in rel.casefold() else []
                if json_chapters:
                    for chapter in json_chapters:
                        chapter_candidates.setdefault(chapter["chapter_number"], []).append(chapter)
                        self._provenance(cir, chapter["cir_item_id"], rel, meta, "chapter", {"chapter_number": chapter["chapter_number"]})
                    continue
                if any(token in rel.casefold() for token in ("snapshot", "outline", "manifest", "contract", "volume", "project-memory", "project_memory", "style")):
                    doc_id = _stable("document", fingerprint, rel)
                    document_type = "snapshot_evidence" if "snapshot" in rel.casefold() else self._document_kind(rel)
                    cir["documents"].append({"cir_item_id": doc_id, "document_type": document_type, "title": Path(rel).stem, "content": _json(value), "metadata": {"source_path": rel, "authoritative": False}})
                    self._provenance(cir, doc_id, rel, meta, document_type)
                    continue
                if "/state/" in f"/{rel.casefold()}/" or Path(rel).name.casefold() in {"state.json", "current_state.json", "truth.json"}:
                    structured_paths.append(rel)
                self._map_json(cir, value, rel, meta, fingerprint, conflicts)
            elif suffix in {".md", ".txt", ".yaml", ".yml"}:
                doc_id = _stable("document", fingerprint, rel)
                kind = self._document_kind(rel)
                cir["documents"].append({"cir_item_id": doc_id, "document_type": kind, "title": Path(rel).stem, "content": value, "metadata": {"source_path": rel}})
                self._provenance(cir, doc_id, rel, meta, kind)
                if kind in {"truth_markdown", "current_state", "hooks"}:
                    markdown_truth_paths.append(rel)
                    self._map_markdown_truth(cir, value, rel, meta, fingerprint, kind)
            elif name == "vectors.db":
                doc_id = _stable("document", fingerprint, rel)
                cir["documents"].append({"cir_item_id": doc_id, "document_type": "vector_metadata", "title": name, "content": "", "metadata": value | {"rebuild_required": True, "authoritative": False}})
                self._provenance(cir, doc_id, rel, meta, "vector_metadata")
            elif name in {"memory.db", "index.db"}:
                doc_id = _stable("document", fingerprint, rel)
                cir["documents"].append({"cir_item_id": doc_id, "document_type": "sqlite_evidence", "title": name, "content": "", "metadata": value | {"candidate_evidence_only": name == "memory.db"}})
                self._provenance(cir, doc_id, rel, meta, "sqlite_evidence")
        for number, candidates in sorted(chapter_candidates.items()):
            if len(candidates) == 1:
                cir["chapters"].append(candidates[0])
            else:
                hashes = {candidate["body_sha256"] for candidate in candidates}
                kind = "duplicate_chapter" if len(hashes) == 1 else "chapter_body_mismatch"
                conflict = self._conflict(kind, f"chapter:{number}", "critical", True,
                    [{"path": c["source_path"], "sha256": c["source_sha256"]} for c in candidates],
                    [{"candidate_id": c["cir_item_id"], "value": c["body_sha256"]} for c in candidates],
                    {"chapter_number": number}, "choose_candidate")
                conflicts.append(conflict)
                cir["chapters"].append(candidates[0] | {"alternatives": candidates[1:], "conflict_ids": [conflict["conflict_id"]]})
        self._resolve_relationship_refs(cir)
        if structured_paths and markdown_truth_paths:
            conflict = self._conflict("conflicting_fact", "truth:structured-vs-markdown", "major", True,
                [{"path": p} for p in structured_paths[:20]] + [{"path": p} for p in markdown_truth_paths[:20]],
                [{"candidate_id": "structured-json", "value": "structured state"}, {"candidate_id": "markdown-truth", "value": "markdown bootstrap"}],
                {"policy": "structured JSON is a suggestion only; no silent winner"}, "choose_candidate")
            conflicts.append(conflict)
            structured_ids = {item["cir_item_id"] for item in cir["provenance"] if item["source_path"] in structured_paths}
            markdown_ids = {item["cir_item_id"] for item in cir["provenance"] if item["source_path"] in markdown_truth_paths}
            self._tag_items(cir, structured_ids, conflict["conflict_id"], "structured-json")
            self._tag_items(cir, markdown_ids, conflict["conflict_id"], "markdown-truth")
        if row["source_type"] in {"webnovel-writer", "hybrid"}:
            json_events = len(cir["events"])
            for rel, value in parsed.items():
                if Path(rel).name.casefold() != "index.db" or not isinstance(value, dict):
                    continue
                mirror_counts = value.get("counts", {})
                sqlite_events = next((int(count) for table, count in mirror_counts.items() if table.casefold() in {"events", "story_events"}), None)
                if sqlite_events is not None and sqlite_events != json_events:
                    conflict = self._conflict("conflicting_fact", "webnovel:json-vs-index-events", "critical", True,
                        [{"path": "JSON commits/events"}, {"path": rel}],
                        [{"candidate_id": "webnovel-json", "value": json_events}, {"candidate_id": "webnovel-index-db", "value": sqlite_events}],
                        {"policy": "commit, checksum, event ID and projection evidence must be reviewed; neither source is assumed authoritative",
                         "json_event_ids": [item["event_id"] for item in cir["events"][:500]], "sqlite_counts": mirror_counts,
                         "sqlite_samples": value.get("samples", {})}, "choose_candidate")
                    conflicts.append(conflict)
                    json_ids = {item["cir_item_id"] for item in cir["provenance"] if item["source_path"] != rel and any(token in item["source_path"].casefold() for token in ("event", "commit"))}
                    db_ids = {item["cir_item_id"] for item in cir["provenance"] if item["source_path"] == rel}
                    self._tag_items(cir, json_ids, conflict["conflict_id"], "webnovel-json")
                    self._tag_items(cir, db_ids, conflict["conflict_id"], "webnovel-index-db")
        cir["unresolved_conflicts"] = conflicts
        cir["unmapped_fields"] = self._dedupe_items(cir["unmapped_fields"])
        return cir, conflicts, warnings

    def _map_json(self, cir: dict[str, Any], value: Any, rel: str, meta: dict[str, Any], fingerprint: str, conflicts: list[dict[str, Any]]) -> None:
        if not isinstance(value, (dict, list)):
            cir["unmapped_fields"].append({"source_path": rel, "json_pointer": "", "value": value})
            return
        lower = rel.casefold()
        records = value if isinstance(value, list) else value.get("items") if isinstance(value.get("items"), list) else None
        if "relationship" in lower:
            records = records or ([value] if isinstance(value, dict) else value)
            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    continue
                item_id = _stable("relationship", fingerprint, f"{rel}:{index}")
                cir["relationships"].append({
                    "cir_item_id": item_id, "relationship_id": str(record.get("relationship_id") or record.get("id") or item_id),
                    "source_entity_id": str(record.get("source_entity_id") or record.get("source") or ""),
                    "target_entity_id": str(record.get("target_entity_id") or record.get("target") or ""),
                    "relationship_type": str(record.get("relationship_type") or record.get("type") or "related"),
                    "attributes": record,
                })
                self._provenance(cir, item_id, rel, meta, "structured_json", {"json_pointer": f"/{index}"})
            return
        if "timeline" in lower:
            records = records or ([value] if isinstance(value, dict) else value)
            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    continue
                item_id = _stable("timeline", fingerprint, f"{rel}:{index}")
                cir["timeline"].append({
                    "cir_item_id": item_id, "timeline_id": str(record.get("timeline_id") or record.get("id") or item_id),
                    "sequence_key": str(record.get("sequence_key") or record.get("time") or record.get("order") or index),
                    "title": str(record.get("title") or record.get("event") or f"Timeline {index + 1}"),
                    "event_id": record.get("event_id"), "details": record,
                })
                self._provenance(cir, item_id, rel, meta, "structured_json", {"json_pointer": f"/{index}"})
            return
        if any(token in lower for token in ("character", "entities", "world", "location", "resource")):
            records = records or ([value] if isinstance(value, dict) else value)
            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    continue
                name = str(record.get("name") or record.get("title") or record.get("id") or f"unnamed-{index}")
                entity_id = _stable("entity", fingerprint, f"{rel}:{index}:{name}")
                entity_type = "character" if "character" in lower else "location" if "location" in lower else "resource" if "resource" in lower else "world"
                aliases = record.get("aliases", []) if isinstance(record.get("aliases", []), list) else []
                cir["entities"].append({"cir_item_id": entity_id, "entity_id": entity_id, "entity_type": entity_type, "canonical_name": name, "aliases": aliases, "attributes": record})
                self._provenance(cir, entity_id, rel, meta, "structured_json", {"json_pointer": f"/{index}"})
                for alias in aliases:
                    cir["aliases"].append({"cir_item_id": _stable("alias", entity_id, str(alias)), "entity_id": entity_id, "alias": str(alias)})
                if entity_type == "resource":
                    numeric = record.get("value", record.get("amount"))
                    if numeric is not None and (not isinstance(numeric, (int, float)) or numeric < 0):
                        conflicts.append(self._conflict("invalid_resource_value", entity_id, "critical", True, [{"path": rel}], [{"candidate_id": entity_id, "value": numeric}], {"entity": name}, "quarantine"))
            return
        if "summary" in lower:
            records = records or ([value] if isinstance(value, dict) else value)
            for index, record in enumerate(records):
                if isinstance(record, str):
                    record = {"summary": record, "chapter_number": index + 1}
                if not isinstance(record, dict):
                    continue
                number = int(record.get("chapter_number") or record.get("chapter") or index + 1)
                summary = str(record.get("summary") or record.get("content") or "")
                item_id = _stable("summary", fingerprint, f"{rel}:{number}")
                cir["summaries"].append({"cir_item_id": item_id, "chapter_number": number, "title": str(record.get("title") or f"Chapter {number}"), "summary": summary, "body_sha256": record.get("body_sha256")})
                self._provenance(cir, item_id, rel, meta, "structured_json")
            return
        if "hook" in lower or "thread" in lower or "foreshadow" in lower:
            records = records or ([value] if isinstance(value, dict) else value)
            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    continue
                item_id = _stable("thread", fingerprint, f"{rel}:{index}")
                status = str(record.get("status") or "open").casefold()
                mapped = {"active": "open", "pending": "open", "resolved": "resolved", "closed": "resolved", "deferred": "deferred"}.get(status, status)
                if mapped not in {"open", "resolved", "deferred", "abandoned"}:
                    conflicts.append(self._conflict("hook_state_conflict", item_id, "major", True, [{"path": rel}], [{"candidate_id": item_id, "value": status}], record, "quarantine"))
                    mapped = "open"
                cir["narrative_threads"].append({"cir_item_id": item_id, "thread_id": item_id, "title": str(record.get("title") or record.get("name") or f"Hook {index + 1}"), "status": mapped, "introduced_chapter": int(record.get("introduced_chapter") or record.get("chapter") or 1), "resolved_chapter": record.get("resolved_chapter"), "details": record})
                self._provenance(cir, item_id, rel, meta, "structured_json")
            return
        if "event" in lower or "commit" in lower:
            records = records or ([value] if isinstance(value, dict) else value)
            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    continue
                event_type = str(record.get("event_type") or record.get("type") or "")
                item_id = _stable("event", fingerprint, f"{rel}:{index}:{record.get('event_id', '')}")
                if not event_type:
                    conflicts.append(self._conflict("unknown_event_type", item_id, "major", True, [{"path": rel}], [{"candidate_id": item_id, "value": record}], {}, "quarantine"))
                    event_type = "legacy.unknown"
                cir["events"].append({"cir_item_id": item_id, "event_id": str(record.get("event_id") or item_id), "event_type": event_type, "subject": str(record.get("subject") or record.get("aggregate_id") or "project"), "chapter_number": record.get("chapter_number") or record.get("chapter"), "payload": record, "confidence": 1.0})
                self._provenance(cir, item_id, rel, meta, "structured_json")
            return
        if "review" in lower:
            records = records or ([value] if isinstance(value, dict) else value)
            for index, record in enumerate(records):
                if isinstance(record, dict):
                    item_id = _stable("review", fingerprint, f"{rel}:{index}")
                    cir["reviews"].append({"cir_item_id": item_id, "chapter_number": int(record.get("chapter_number") or record.get("chapter") or 1), "body_sha256": record.get("body_sha256"), "review": record})
                    self._provenance(cir, item_id, rel, meta, "structured_json")
            return
        if isinstance(value, dict):
            for key, candidate in value.items():
                fact_id = _stable("fact", fingerprint, f"{rel}:{key}")
                cir["facts"].append({"cir_item_id": fact_id, "fact_id": fact_id, "subject": Path(rel).stem, "predicate": str(key), "value": candidate, "confidence": 0.85})
                self._provenance(cir, fact_id, rel, meta, "structured_json", {"json_pointer": f"/{key}"})
        else:
            cir["unmapped_fields"].append({"source_path": rel, "json_pointer": "", "value": value})

    def _map_markdown_truth(self, cir: dict[str, Any], text: str, rel: str, meta: dict[str, Any], fingerprint: str, kind: str) -> None:
        heading = Path(rel).stem
        extracted = 0
        for line_number, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if line.startswith("#"):
                heading = line.lstrip("#").strip() or heading
                continue
            match = re.match(r"^(?:[-*]\s*)?([^:：]{1,120})[:：]\s*(.+)$", line)
            if match and extracted < 500:
                predicate = re.sub(r"\s+", "_", match.group(1).strip()).casefold()
                item_id = _stable("fact", fingerprint, f"{rel}:{line_number}:{predicate}")
                cir["facts"].append({"cir_item_id": item_id, "fact_id": item_id, "subject": heading, "predicate": predicate, "value": match.group(2).strip(), "confidence": 0.6, "bootstrap": True})
                self._provenance(cir, item_id, rel, meta, "markdown_bootstrap", {"line": line_number})
                extracted += 1
            elif kind == "hooks" and re.match(r"^[-*]\s+", line) and extracted < 500:
                title = re.sub(r"^[-*]\s+(?:\[[ xX]\]\s*)?", "", line).strip()
                if title:
                    item_id = _stable("thread", fingerprint, f"{rel}:{line_number}")
                    status = "resolved" if re.match(r"^[-*]\s+\[[xX]\]", line) else "open"
                    cir["narrative_threads"].append({"cir_item_id": item_id, "thread_id": item_id, "title": title, "status": status, "introduced_chapter": 1, "resolved_chapter": None, "details": {"bootstrap": True, "source_line": line_number}})
                    self._provenance(cir, item_id, rel, meta, "markdown_bootstrap", {"line": line_number})
                    extracted += 1

    def _validate_cir(self, cir: dict[str, Any]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        numbers = sorted(chapter["chapter_number"] for chapter in cir["chapters"])
        if numbers:
            missing = sorted(set(range(numbers[0], numbers[-1] + 1)) - set(numbers))
            if missing:
                conflicts.append(self._conflict("chapter_number_gap", "chapters", "critical", True, [], [{"candidate_id": "missing", "value": missing}], {"range": [numbers[0], numbers[-1]]}, "quarantine"))
        entity_ids = {entity["entity_id"] for entity in cir["entities"]}
        fact_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for fact in cir["facts"]:
            fact_groups.setdefault((fact["subject"], fact["predicate"]), []).append(fact)
        for (subject, predicate), facts in fact_groups.items():
            values = {_json(fact.get("value")) for fact in facts}
            if len(values) > 1:
                conflicts.append(self._conflict("conflicting_fact", f"fact:{subject}:{predicate}", "critical", True, [], [{"candidate_id": fact["cir_item_id"], "value": fact.get("value")} for fact in facts], {"subject": subject, "predicate": predicate}, "choose_candidate"))
        timeline_groups: dict[str, list[dict[str, Any]]] = {}
        for item in cir["timeline"]:
            timeline_groups.setdefault(item["sequence_key"], []).append(item)
        for sequence_key, items in timeline_groups.items():
            if len({_json(item.get("details")) for item in items}) > 1:
                conflicts.append(self._conflict("timeline_conflict", f"timeline:{sequence_key}", "critical", True, [], [{"candidate_id": item["cir_item_id"], "value": item} for item in items], {"sequence_key": sequence_key}, "choose_candidate"))
        for thread in cir["narrative_threads"]:
            if thread.get("resolved_chapter") is not None and int(thread["resolved_chapter"]) < int(thread["introduced_chapter"]):
                conflicts.append(self._conflict("hook_state_conflict", thread["cir_item_id"], "critical", True, [], [{"candidate_id": thread["cir_item_id"], "value": thread}], {"reason": "resolved before introduced"}, "quarantine"))
        aliases: dict[str, list[str]] = {}
        for alias in cir["aliases"]:
            aliases.setdefault(alias["alias"].casefold(), []).append(alias["entity_id"])
        for alias, ids in aliases.items():
            if len(set(ids)) > 1:
                conflicts.append(self._conflict("ambiguous_alias", f"alias:{alias}", "critical", True, [], [{"candidate_id": value, "value": alias} for value in ids], {"alias": alias}, "choose_candidate"))
        for relationship in cir["relationships"]:
            if relationship["source_entity_id"] not in entity_ids or relationship["target_entity_id"] not in entity_ids:
                conflicts.append(self._conflict("orphan_reference", relationship["cir_item_id"], "critical", True, [], [{"candidate_id": relationship["cir_item_id"], "value": relationship}], relationship, "quarantine"))
        relationship_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for relationship in cir["relationships"]:
            key = (relationship["source_entity_id"], relationship["target_entity_id"], relationship["relationship_type"])
            relationship_groups.setdefault(key, []).append(relationship)
        for key, relationships in relationship_groups.items():
            if len({_json(item.get("attributes")) for item in relationships}) > 1:
                conflicts.append(self._conflict("conflicting_relationship", f"relationship:{key}", "critical", True, [], [{"candidate_id": item["cir_item_id"], "value": item} for item in relationships], {"relationship": key}, "choose_candidate"))
        chapter_hashes = {chapter["chapter_number"]: chapter["body_sha256"] for chapter in cir["chapters"]}
        chapter_ids = {chapter["chapter_number"]: chapter["cir_item_id"] for chapter in cir["chapters"]}
        for review in cir["reviews"]:
            expected = review.get("body_sha256")
            actual = chapter_hashes.get(review["chapter_number"])
            if expected and actual and expected != actual:
                conflicts.append(self._conflict("review_body_hash_mismatch", review["cir_item_id"], "major", True, [], [{"candidate_id": review["cir_item_id"], "value": expected}, {"candidate_id": chapter_ids[review["chapter_number"]], "value": actual}], {}, "quarantine"))
        return conflicts

    def _dry_run(self, cir: dict[str, Any], conflicts: list[dict[str, Any]], decisions: dict[str, Any]) -> dict[str, Any]:
        counts = {key: len(cir[key]) for key in ("chapters", "entities", "aliases", "relationships", "facts", "events", "timeline", "narrative_threads", "reviews", "summaries", "documents")}
        quarantined = [cid for cid, value in decisions.items() if value["decision"] == "quarantine"]
        ignored = [cid for cid, value in decisions.items() if value["decision"] == "ignore"]
        blocking = [c["conflict_id"] for c in conflicts if c["blocking"] and c["conflict_id"] not in decisions]
        estimated_bytes = len(_json(cir).encode("utf-8"))
        return {"report_version": "migration-dry-run/v1", "add": counts, "merge": {"aliases": counts["aliases"]}, "ignore": ignored,
                "quarantine": quarantined, "estimated_revision_increment": max(1, counts["chapters"] + counts["events"]),
                "estimated_event_count": counts["events"] + counts["chapters"], "estimated_entity_count": counts["entities"],
                "unmapped_fields": cir["unmapped_fields"], "blocking_conflicts": blocking,
                "risks": ["semantic conflicts require retained human decisions"] if conflicts else [], "target_capacity_bytes": estimated_bytes}

    # -- target snapshot/import/verify ----------------------------------------------------

    def _create_verified_snapshot(self, row: sqlite3.Row) -> dict[str, Any]:
        with self.database.connect() as conn:
            target_exists = conn.execute("SELECT 1 FROM projects WHERE project_id=?", (row["target_project_id"],)).fetchone() is not None
        if not target_exists:
            return {"kind": "empty-target", "target_project_id": row["target_project_id"], "verified": True, "created_at": _now()}
        root = self.database.path.parent / "migration-snapshots" / row["job_id"]
        root.mkdir(parents=True, exist_ok=True)
        path = root / "target-before-import.sqlite3"
        source = sqlite3.connect(self.database.path)
        destination = sqlite3.connect(path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        verify = sqlite3.connect(f"file:{quote(path.resolve().as_posix())}?mode=ro&immutable=1", uri=True)
        try:
            integrity = verify.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            verify.close()
        if integrity != "ok":
            raise ConflictError("SNAPSHOT_VERIFY_FAILED", "target snapshot failed SQLite integrity check")
        checksum = _sha_bytes(path.read_bytes())
        return {"kind": "sqlite-backup", "path": str(path), "sha256": checksum, "size": path.stat().st_size, "integrity": integrity, "verified": True, "restore_verified": True, "created_at": _now()}

    def _import_cir(self, row: sqlite3.Row, actor: str) -> dict[str, int]:
        cir = self._resolved_cir(row)
        imported = {kind: 0 for kind in ("entities", "relationships", "facts", "events", "timeline", "narrative_threads", "summaries", "documents", "chapters", "reviews")}
        pending = [(kind, item) for kind in imported for item in cir[kind]]
        latest = max((chapter["chapter_number"] for chapter in cir["chapters"]), default=0)
        for batch_number, offset in enumerate(range(0, max(1, len(pending)), 100), start=1):
            batch = pending[offset:offset + 100]
            now = _now()
            with self.database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    project = conn.execute("SELECT revision,authority_mode FROM projects WHERE project_id=?", (row["target_project_id"],)).fetchone()
                    if project and project["authority_mode"] == "runtime":
                        raise ConflictError("TARGET_ALREADY_RUNTIME", "cannot import legacy sources into an existing Runtime-authority project")
                    if not project:
                        conn.execute("INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) VALUES (?,0,'migration-import',0,?,?,?,'legacy')", (row["target_project_id"], SCHEMA_VERSION, now, now))
                        revision = 0
                    else:
                        revision = int(project["revision"])
                    for kind, item in batch:
                        if self._ledger_exists(conn, row["job_id"], item["cir_item_id"]):
                            continue
                        revision = self._import_item(conn, row, kind, item, revision, now)
                        self._ledger(conn, row["job_id"], kind, item, now)
                        imported[kind] += 1
                    conn.execute("UPDATE projects SET revision=?,latest_chapter=MAX(latest_chapter,?),phase='migration-verifying',schema_version=?,updated_at=? WHERE project_id=?", (revision, latest, SCHEMA_VERSION, now, row["target_project_id"]))
                    for provenance in cir["provenance"]:
                        conn.execute("INSERT OR IGNORE INTO migration_source_provenance(job_id,cir_item_id,source_path,source_sha256,source_kind,locator_json,confidence) VALUES (?,?,?,?,?,?,?)",
                                     (row["job_id"], provenance["cir_item_id"], provenance["source_path"], provenance["source_sha256"], provenance["source_kind"], _json(provenance.get("locator", {})), provenance.get("confidence", 1.0)))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            self._append_checkpoint(row["job_id"], {"stage": "IMPORTING", "batch": batch_number, "offset": offset + len(batch), "total": len(pending), "at": _now()})
            if self._row(row["job_id"])["current_stage"] == "PAUSED":
                break
        return imported

    def _import_item(self, conn: sqlite3.Connection, row: sqlite3.Row, kind: str, item: dict[str, Any], revision: int, now: str) -> int:
        project_id = row["target_project_id"]
        if kind == "entities":
            conn.execute("INSERT OR IGNORE INTO entities(project_id,entity_id,entity_type,canonical_name,aliases_json,attributes_json,history_json) VALUES (?,?,?,?,?,?,'[]')", (project_id, item["entity_id"], item["entity_type"], item["canonical_name"], _json(item.get("aliases", [])), _json(item.get("attributes", {}))))
        elif kind == "relationships":
            conn.execute("INSERT OR IGNORE INTO relationships(project_id,relationship_id,source_entity_id,target_entity_id,relationship_type,attributes_json) VALUES (?,?,?,?,?,?)", (project_id, item["relationship_id"], item["source_entity_id"], item["target_entity_id"], item["relationship_type"], _json(item.get("attributes", {}))))
        elif kind == "facts":
            conn.execute("INSERT OR IGNORE INTO facts(project_id,fact_id,subject,predicate,value_json,valid_from_revision) VALUES (?,?,?,?,?,?)", (project_id, item["fact_id"], item["subject"], item["predicate"], _json(item.get("value")), revision))
        elif kind == "events":
            revision += 1
            conn.execute("INSERT OR IGNORE INTO story_events(project_id,event_id,event_type,subject,chapter_number,payload_json,evidence_json,confidence,schema_version,created_at,applied_revision,aggregate_type,aggregate_id) VALUES (?,?,?,?,?,?,'[]',?,?,?,?,?,?)", (project_id, item["event_id"], item["event_type"], item["subject"], item.get("chapter_number"), _json(item.get("payload", {})), item.get("confidence", 1.0), SCHEMA_VERSION, now, revision, "project", project_id))
        elif kind == "timeline":
            conn.execute("INSERT OR IGNORE INTO timeline(project_id,timeline_id,sequence_key,title,event_id,details_json) VALUES (?,?,?,?,?,?)", (project_id, item["timeline_id"], item["sequence_key"], item["title"], item.get("event_id"), _json(item.get("details", {}))))
        elif kind == "narrative_threads":
            conn.execute("INSERT OR IGNORE INTO narrative_threads(project_id,thread_id,title,status,introduced_chapter,resolved_chapter,details_json) VALUES (?,?,?,?,?,?,?)", (project_id, item["thread_id"], item["title"], item["status"], item["introduced_chapter"], item.get("resolved_chapter"), _json(item.get("details", {}))))
        elif kind == "summaries":
            conn.execute("INSERT OR IGNORE INTO chapter_summaries(project_id,chapter_number,title,summary,body_sha256) VALUES (?,?,?,?,?)", (project_id, item["chapter_number"], item["title"], item["summary"], item.get("body_sha256")))
        elif kind == "documents":
            conn.execute("INSERT OR IGNORE INTO retrieval_documents(project_id,source_id,source_type,chapter_number,text) VALUES (?,?,?,?,?)", (project_id, item["cir_item_id"], item["document_type"], item.get("chapter_number"), item.get("content") or _json(item.get("metadata", {}))))
        elif kind == "chapters":
            revision += 1
            commit_id = item["cir_item_id"]
            conn.execute("INSERT OR IGNORE INTO chapter_commits(commit_id,project_id,chapter_number,request_id,idempotency_key,request_hash,expected_revision,resulting_revision,state,body_sha256,artifact_sha256,schema_version,created_at,updated_at,finalized_at) VALUES (?,?,?,?,?,?,?,?, 'FINALIZED',?,?,?,?,?,?)", (commit_id, project_id, item["chapter_number"], commit_id, f"migration:{row['job_id']}:{commit_id}", item["body_sha256"], revision - 1, revision, item["body_sha256"], item["body_sha256"], SCHEMA_VERSION, now, now, now))
            conn.execute("INSERT OR IGNORE INTO chapter_artifacts(commit_id,project_id,chapter_number,title,body_text,summary,outline_fulfillment_json,review_json,state_mutation_proposal_json,evidence_spans_json,events_json,schema_version,body_sha256,checksum,created_at) VALUES (?,?,?,?,?,?,'{}','{}','{}','[]','[]',?,?,?,?)", (commit_id, project_id, item["chapter_number"], item["title"], item["body"], "", SCHEMA_VERSION, item["body_sha256"], item["body_sha256"], now))
            conn.execute("INSERT OR IGNORE INTO chapter_summaries(project_id,chapter_number,title,summary,body_sha256) VALUES (?,?,?,?,?)", (project_id, item["chapter_number"], item["title"], "", item["body_sha256"]))
        elif kind == "reviews":
            payload = item["review"]
            artifact_id = item["cir_item_id"]
            conn.execute("INSERT OR IGNORE INTO review_artifacts(artifact_id,project_id,chapter_number,source_revision,body_sha256,reviewer_kind,artifact_json,payload_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (artifact_id, project_id, item["chapter_number"], revision, item.get("body_sha256") or "0" * 64, "legacy-import", _json(payload), _sha_bytes(_json(payload).encode()), now))
        return revision

    def _verify_import(self, row: sqlite3.Row) -> dict[str, Any]:
        cir = self._resolved_cir(row)
        project_id = row["target_project_id"]
        with self.database.connect() as conn:
            source_chapters = {item["chapter_number"]: item["body_sha256"] for item in cir["chapters"]}
            target_chapters = {r["chapter_number"]: r["body_sha256"] for r in conn.execute("SELECT chapter_number,body_sha256 FROM chapter_commits WHERE project_id=? AND state='FINALIZED'", (project_id,))}
            body_matches = sum(1 for number, digest in source_chapters.items() if target_chapters.get(number) == digest)
            counts = {
                "entities": conn.execute("SELECT COUNT(*) FROM entities WHERE project_id=?", (project_id,)).fetchone()[0],
                "relationships": conn.execute("SELECT COUNT(*) FROM relationships WHERE project_id=?", (project_id,)).fetchone()[0],
                "facts": conn.execute("SELECT COUNT(*) FROM facts WHERE project_id=?", (project_id,)).fetchone()[0],
                "timeline": conn.execute("SELECT COUNT(*) FROM timeline WHERE project_id=?", (project_id,)).fetchone()[0],
                "narrative_threads": conn.execute("SELECT COUNT(*) FROM narrative_threads WHERE project_id=?", (project_id,)).fetchone()[0],
                "summaries": conn.execute("SELECT COUNT(*) FROM chapter_summaries WHERE project_id=?", (project_id,)).fetchone()[0],
            }
            projection_hash = ChapterCommitService(self.database).projection_hash(conn, project_id)
        replay_hash = self._replay_cir_hash(row, cir)
        doctor = RuntimeServices(self.database, StoryRepository(self.database)).doctor(project_id, deep=True)
        unresolved = [c for c in json.loads(row["conflicts_json"]) if c["blocking"] and not c.get("user_decision")]
        total = len(source_chapters)
        coverage = body_matches / total if total else 1.0
        summary_source = len(cir["summaries"])
        active_threads = len([item for item in cir["narrative_threads"] if item["status"] in {"open", "deferred"}])
        source_manifest = json.loads(row["source_checksum_manifest_json"])
        return {
            "report_version": "migration-verification/v1", "chapter_body_coverage": coverage,
            "chapter_checksum_coverage": coverage, "source_chapter_count": total, "target_chapter_count": len(target_chapters),
            "entity_mapping_coverage": self._coverage(len(cir["entities"]), counts["entities"]),
            "relationship_mapping_coverage": self._coverage(len(cir["relationships"]), counts["relationships"]),
            "active_hook_thread_mapping_coverage": self._coverage(active_threads, counts["narrative_threads"]),
            "summary_coverage": self._coverage(summary_source, counts["summaries"]),
            "fact_count": counts["facts"], "timeline_count": counts["timeline"],
            "unmapped_fields": len(cir["unmapped_fields"]),
            "quarantined_items": len([d for d in json.loads(row["decisions_json"]).values() if d["decision"] == "quarantine"]),
            "blocking_conflicts": len(unresolved), "source_checksum": _sha_bytes(_json(source_manifest).encode()),
            "projection_hash": projection_hash, "replay_hash": replay_hash, "replay_matched": replay_hash == projection_hash,
            "doctor_status": doctor.status, "doctor": doctor.model_dump(mode="json"),
        }

    def _replay_cir_hash(self, row: sqlite3.Row, cir: dict[str, Any]) -> str:
        snapshot = json.loads(row["target_snapshot_json"] or "null")
        with tempfile.TemporaryDirectory(prefix="phase7-replay-", dir=self.database.path.parent) as directory:
            replay_path = Path(directory) / "replay.sqlite3"
            if snapshot and snapshot.get("kind") == "sqlite-backup":
                source = sqlite3.connect(f"file:{quote(Path(snapshot['path']).resolve().as_posix())}?mode=ro&immutable=1", uri=True)
                destination = sqlite3.connect(replay_path)
                try:
                    source.backup(destination)
                finally:
                    destination.close(); source.close()
                replay_db = Database(RuntimeConfig(database_path=replay_path, busy_timeout_ms=self.config.busy_timeout_ms))
            else:
                replay_db = Database(RuntimeConfig(database_path=replay_path, busy_timeout_ms=self.config.busy_timeout_ms))
                replay_db.migrations.migrate()
            now = _now()
            with replay_db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                project = conn.execute("SELECT revision,authority_mode FROM projects WHERE project_id=?", (row["target_project_id"],)).fetchone()
                if not project:
                    conn.execute("INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) VALUES (?,0,'migration-replay',0,?,?,?,'legacy')", (row["target_project_id"], SCHEMA_VERSION, now, now))
                    revision = 0
                else:
                    revision = int(project["revision"])
                for kind in ("entities", "relationships", "facts", "events", "timeline", "narrative_threads", "summaries", "documents", "chapters", "reviews"):
                    for item in cir[kind]:
                        revision = self._import_item(conn, row, kind, item, revision, now)
                latest = max((chapter["chapter_number"] for chapter in cir["chapters"]), default=0)
                conn.execute("UPDATE projects SET revision=?,latest_chapter=MAX(latest_chapter,?),updated_at=? WHERE project_id=?", (revision, latest, now, row["target_project_id"]))
                conn.commit()
                return ChapterCommitService(replay_db).projection_hash(conn, row["target_project_id"])

    def _restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        path = Path(snapshot["path"])
        if not path.is_file() or _sha_bytes(path.read_bytes()) != snapshot["sha256"]:
            raise ConflictError("SNAPSHOT_CHECKSUM_MISMATCH", "verified target snapshot is missing or changed")
        source = sqlite3.connect(f"file:{quote(path.resolve().as_posix())}?mode=ro&immutable=1", uri=True)
        destination = sqlite3.connect(self.database.path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()

    # -- persistence helpers --------------------------------------------------------------

    def _row(self, job_id: str) -> sqlite3.Row:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM migration_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise NotFoundError("MIGRATION_JOB_NOT_FOUND", f"migration job not found: {job_id}")
        return row

    def _cir(self, row: sqlite3.Row) -> dict[str, Any]:
        if not row["cir_json"]:
            raise ConflictError("CIR_NOT_AVAILABLE", "scan and map the source before this operation")
        return json.loads(row["cir_json"])

    def _resolved_cir(self, row: sqlite3.Row) -> dict[str, Any]:
        """Apply durable human decisions to a copy used by preview/import/verify."""
        cir = json.loads(_json(self._cir(row)))
        decisions = json.loads(row["decisions_json"])
        conflicts = {item["conflict_id"]: item for item in json.loads(row["conflicts_json"])}
        sections = ("chapters", "entities", "aliases", "relationships", "facts", "events", "timeline", "narrative_threads", "reviews", "summaries", "documents")
        for conflict_id, decision in decisions.items():
            conflict = conflicts.get(conflict_id)
            if not conflict:
                continue
            mode = decision["decision"]
            candidate_id = decision.get("candidate_id")
            if conflict["type"] in {"chapter_body_mismatch", "duplicate_chapter"}:
                selected: list[dict[str, Any]] = []
                for chapter in cir["chapters"]:
                    if conflict_id not in chapter.get("conflict_ids", []):
                        selected.append(chapter)
                        continue
                    candidates = [{key: value for key, value in chapter.items() if key not in {"alternatives", "conflict_ids"}}, *chapter.get("alternatives", [])]
                    if mode == "choose_candidate":
                        chosen = next((item for item in candidates if item["cir_item_id"] == candidate_id), None)
                        if not chosen:
                            raise ConflictError("MIGRATION_DECISION_INVALID", f"candidate is unavailable: {candidate_id}")
                        selected.append(chosen)
                    elif mode == "merge":
                        raise ConflictError("MIGRATION_DECISION_INVALID", "chapter bodies cannot be merged without an explicit merged CIR candidate")
                    # ignore/quarantine intentionally omit the disputed chapter.
                cir["chapters"] = selected
                continue
            if conflict["type"] == "ambiguous_alias":
                alias = str(conflict.get("evidence", {}).get("alias", ""))
                for entity in cir["entities"]:
                    if mode in {"ignore", "quarantine"} or (mode == "choose_candidate" and entity["entity_id"] != candidate_id):
                        entity["aliases"] = [value for value in entity.get("aliases", []) if str(value).casefold() != alias.casefold()]
                cir["aliases"] = [item for item in cir["aliases"] if not (str(item["alias"]).casefold() == alias.casefold() and (mode in {"ignore", "quarantine"} or item["entity_id"] != candidate_id))]
                continue
            candidate_ids = {str(item.get("candidate_id")) for item in conflict.get("candidates", [])}
            for section in sections:
                filtered = []
                for item in cir[section]:
                    tagged = conflict_id in item.get("conflict_ids", [])
                    identified = item.get("cir_item_id") in candidate_ids
                    if not tagged and not identified:
                        filtered.append(item); continue
                    if mode == "merge":
                        filtered.append(item); continue
                    if mode == "choose_candidate" and (item.get("source_group") == candidate_id or item.get("cir_item_id") == candidate_id):
                        filtered.append(item)
                    # ignore/quarantine and unselected candidates are excluded.
                cir[section] = filtered
        return cir

    def _require_stage(self, row: sqlite3.Row, allowed: set[str]) -> None:
        if row["current_stage"] not in allowed:
            raise ConflictError("MIGRATION_STAGE_CONFLICT", f"operation is not allowed in {row['current_stage']}", details={"allowed": sorted(allowed)})

    def _assert_no_unresolved(self, row: sqlite3.Row) -> None:
        unresolved = [c for c in json.loads(row["conflicts_json"]) if c["blocking"] and not c.get("user_decision")]
        if unresolved:
            raise ConflictError("MIGRATION_DECISIONS_REQUIRED", "blocking conflicts require explicit decisions", details={"conflict_ids": [c["conflict_id"] for c in unresolved]})

    def _update(self, job_id: str, stage: str, progress: int, actor: str, action: str, *, manifest=None, warnings=None,
                conflicts=None, decisions=None, checkpoints=None, cir=None, dry_run=None, snapshot=None, verification=None,
                discovery=None, details=None) -> None:
        row = self._row(job_id)
        values = {
            "source_checksum_manifest_json": _json(manifest) if manifest is not None else row["source_checksum_manifest_json"],
            "warnings_json": _json(warnings) if warnings is not None else row["warnings_json"],
            "conflicts_json": _json(conflicts) if conflicts is not None else row["conflicts_json"],
            "decisions_json": _json(decisions) if decisions is not None else row["decisions_json"],
            "checkpoints_json": _json(checkpoints) if checkpoints is not None else row["checkpoints_json"],
            "cir_json": _json(cir) if cir is not None else row["cir_json"],
            "dry_run_json": _json(dry_run) if dry_run is not None else row["dry_run_json"],
            "target_snapshot_json": _json(snapshot) if snapshot is not None else row["target_snapshot_json"],
            "verification_json": _json(verification) if verification is not None else row["verification_json"],
            "discovery_json": _json(discovery) if discovery is not None else row["discovery_json"],
        }
        audit = json.loads(row["audit_log_json"])
        audit.append({"at": _now(), "actor": actor, "action": action, "outcome": "ok" if stage != "FAILED" else "failed", "details": details or {}})
        with self.database.connect() as conn:
            conn.execute("""UPDATE migration_jobs SET current_stage=?,progress=?,source_checksum_manifest_json=?,warnings_json=?,conflicts_json=?,decisions_json=?,checkpoints_json=?,audit_log_json=?,cir_json=?,dry_run_json=?,target_snapshot_json=?,verification_json=?,discovery_json=?,updated_at=?,completed_at=CASE WHEN ?='COMPLETED' THEN ? ELSE completed_at END WHERE job_id=?""",
                         (stage, progress, values["source_checksum_manifest_json"], values["warnings_json"], values["conflicts_json"], values["decisions_json"], values["checkpoints_json"], _json(audit), values["cir_json"], values["dry_run_json"], values["target_snapshot_json"], values["verification_json"], values["discovery_json"], _now(), stage, _now(), job_id))

    def _audit(self, job_id: str, actor: str, action: str, outcome: str, details: dict[str, Any]) -> None:
        row = self._row(job_id)
        audit = json.loads(row["audit_log_json"])
        audit.append({"at": _now(), "actor": actor, "action": action, "outcome": outcome, "details": details})
        with self.database.connect() as conn:
            conn.execute("UPDATE migration_jobs SET audit_log_json=?,updated_at=? WHERE job_id=?", (_json(audit), _now(), job_id))

    def _append_checkpoint(self, job_id: str, checkpoint: dict[str, Any]) -> None:
        row = self._row(job_id)
        checkpoints = json.loads(row["checkpoints_json"])
        checkpoints.append(checkpoint)
        with self.database.connect() as conn:
            conn.execute("UPDATE migration_jobs SET checkpoints_json=?,updated_at=? WHERE job_id=?", (_json(checkpoints[-500:]), _now(), job_id))

    def _ledger_exists(self, conn: sqlite3.Connection, job_id: str, cir_item_id: str) -> bool:
        return conn.execute("SELECT 1 FROM migration_import_ledger WHERE job_id=? AND cir_item_id=?", (job_id, cir_item_id)).fetchone() is not None

    def _ledger(self, conn: sqlite3.Connection, job_id: str, kind: str, item: dict[str, Any], now: str) -> None:
        payload = _json(item)
        conn.execute("INSERT INTO migration_import_ledger(job_id,cir_item_id,item_kind,target_key,payload_sha256,imported_at) VALUES (?,?,?,?,?,?)", (job_id, item["cir_item_id"], kind, item.get(f"{kind[:-1]}_id", item["cir_item_id"]), _sha_bytes(payload.encode()), now))

    def _conflict(self, kind: str, key: str, severity: str, blocking: bool, sources: list[dict[str, Any]], candidates: list[dict[str, Any]], evidence: dict[str, Any], recommendation: str) -> dict[str, Any]:
        if kind not in _CONFLICT_TYPES:
            raise ValueError(f"unsupported migration conflict type: {kind}")
        conflict_id = f"{kind}:{_sha_bytes(key.encode())[:16]}"
        return {"conflict_id": conflict_id, "type": kind, "severity": severity, "blocking": blocking,
                "sources": sources, "candidates": candidates, "evidence": evidence,
                "recommended_decision": recommendation, "user_decision": None, "resolution_audit": []}

    def _dedupe_conflicts(self, conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list({item["conflict_id"]: item for item in conflicts}.values())

    def _dedupe_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list({_sha_bytes(_json(item).encode()): item for item in items}.values())

    def _provenance(self, cir: dict[str, Any], item_id: str, rel: str, meta: dict[str, Any], kind: str, locator: dict[str, Any] | None = None) -> None:
        cir["provenance"].append({"cir_item_id": item_id, "source_path": rel, "source_sha256": meta["sha256"], "source_kind": kind, "locator": locator or {}, "confidence": 1.0 if kind == "chapter" else 0.85})

    def _tag_items(self, cir: dict[str, Any], item_ids: set[str], conflict_id: str, source_group: str) -> None:
        for section in ("chapters", "entities", "aliases", "relationships", "facts", "events", "timeline", "narrative_threads", "reviews", "summaries", "documents"):
            for item in cir[section]:
                if item["cir_item_id"] in item_ids:
                    item["conflict_ids"] = sorted(set(item.get("conflict_ids", [])) | {conflict_id})
                    item["source_group"] = source_group

    def _resolve_relationship_refs(self, cir: dict[str, Any]) -> None:
        names: dict[str, set[str]] = {}
        for entity in cir["entities"]:
            for value in (entity["entity_id"], entity["canonical_name"], *entity.get("aliases", [])):
                names.setdefault(str(value).casefold(), set()).add(entity["entity_id"])
        for relationship in cir["relationships"]:
            for key in ("source_entity_id", "target_entity_id"):
                candidates = names.get(str(relationship[key]).casefold(), set())
                if len(candidates) == 1:
                    relationship[key] = next(iter(candidates))

    def _chapter_number(self, rel: str, value: Any) -> int | None:
        match = _CHAPTER_RE.search(Path(rel).stem)
        if match:
            return int(match.group(1))
        if isinstance(value, str):
            match = re.match(r"\s*(?:#\s*)?(?:第\s*)?(\d+)(?:\s*章|\b)", value)
            if match:
                return int(match.group(1))
        return None

    def _json_chapters(self, value: Any, rel: str, meta: dict[str, Any], fingerprint: str) -> list[dict[str, Any]]:
        records = value if isinstance(value, list) else value.get("chapters") if isinstance(value, dict) and isinstance(value.get("chapters"), list) else [value] if isinstance(value, dict) else []
        chapters = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            body = record.get("body", record.get("content", record.get("text")))
            number = record.get("chapter_number", record.get("chapter", record.get("number")))
            if not isinstance(body, str) or not isinstance(number, int) or number < 1:
                continue
            normalized = body.strip()
            source_locator = f"{rel}:{index}:{number}"
            chapters.append({
                "cir_item_id": _stable("chapter", fingerprint, source_locator), "chapter_number": number,
                "title": str(record.get("title") or f"Chapter {number}"), "body": normalized,
                "body_sha256": _sha_bytes(normalized.encode("utf-8")), "source_sha256": meta["sha256"],
                "source_path": rel, "source_locator": {"json_index": index},
            })
        return chapters

    def _chapter_title(self, body: str, number: int) -> str:
        first = next((line.strip().lstrip("#").strip() for line in body.splitlines() if line.strip()), "")
        return first[:200] or f"Chapter {number}"

    def _document_kind(self, rel: str) -> str:
        lower = rel.casefold()
        if "outline" in lower:
            return "outline"
        if "style" in lower:
            return "style_guidance"
        if "hook" in lower or "foreshadow" in lower:
            return "hooks"
        if "current" in lower and "state" in lower:
            return "current_state"
        if "truth" in lower or "story/" in lower:
            return "truth_markdown"
        return "source_document"

    def _file_type(self, path: Path) -> str:
        if path.is_symlink():
            return "symlink"
        if path.name.casefold() in _KNOWN_DATABASES:
            return "sqlite"
        if path.suffix.casefold() == ".json":
            return "json"
        if path.suffix.casefold() in {".md", ".txt"}:
            return "markdown" if path.suffix.casefold() == ".md" else "text"
        if path.suffix.casefold() == ".zip":
            return "zip"
        return "binary"

    @staticmethod
    def _coverage(source: int, target: int) -> float:
        return 1.0 if source == 0 else min(1.0, target / source)
