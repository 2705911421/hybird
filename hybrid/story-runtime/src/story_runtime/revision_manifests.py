"""Immutable project revision manifests (ADR-RC2-001/002/003).

A manifest is the authoritative proof that one project revision exists and the
integrity/provenance index for its atomic transition.  It deliberately stores
only event membership and artifact references/hashes: events remain the
authoritative expression of individual domain changes, while artifacts remain
the authority for large immutable payloads such as chapter bodies and reviews.
A manifest is never a story-state projection, snapshot, diff, cache, complete
event payload, or replacement artifact; an event or artifact alone never proves
that a revision exists.  Batch 2 will close and version the event catalog.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid5

from .database import Database
from .errors import ConflictError
from .revision_compatibility import KNOWN_REVISION_COMPATIBILITY, supported_values


MANIFEST_SCHEMA_VERSION = "revision-manifest/v1"
EVENT_SCHEMA_VERSION = "legacy-unversioned"
REDUCER_VERSION = "story-reducers/legacy-v1"
CONTRACT_VERSION = "story-runtime/v1"
_MANIFEST_NAMESPACE = UUID("6f816d60-7f6b-5bd6-bac4-95e4dc6edb14")
_COMMAND_NAMESPACE = UUID("6bc66f5d-3127-4ac8-9d51-e8ec2b520904")


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {unicodedata.normalize("NFC", str(key)): _normalize(item) for key, item in value.items()}
    return value


def canonical_manifest_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize the frozen logical manifest contract as canonical UTF-8 JSON.

    Manifest IDs, stored hashes and physical SQLite identifiers are deliberately
    absent from the input contract. Ordered arrays remain ordered; object key
    order is irrelevant. See ADR-RC2-001 and REVISION-MANIFEST-SPEC.md.
    """

    return json.dumps(
        _normalize(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_manifest_hash(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_manifest_bytes(payload)).hexdigest()


def _tagged_hash(value: str) -> str:
    return value if ":" in value else f"sha256:{value}"


def _utc_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def expected_command_id(manifest: "RevisionManifest") -> str | None:
    """Derive command identity from the real Batch 1 persistence model."""

    if manifest.transition_kind == "initialize_empty":
        return f"project.create:{uuid5(_COMMAND_NAMESPACE, manifest.project_id)}"
    if manifest.transition_kind == "domain_command":
        return f"domain.command:{uuid5(_COMMAND_NAMESPACE, manifest.project_id + chr(0) + manifest.idempotency_key)}"
    if manifest.transition_kind in {"chapter_finalize", "chapter_replace"} and manifest.commit_id:
        return f"chapter.finalize:{manifest.commit_id}"
    if manifest.transition_kind == "bootstrap":
        return f"history.bootstrap:{manifest.project_id}"
    return None


@dataclass(frozen=True)
class RevisionManifest:
    project_id: str
    revision: int
    manifest_id: str
    previous_revision: int | None
    previous_manifest_hash: str | None
    transition_kind: str
    command_id: str
    commit_id: str | None
    idempotency_key: str
    request_hash: str
    event_count: int
    first_event_sequence: int | None
    last_event_sequence: int | None
    ordered_event_ids: tuple[str, ...]
    ordered_event_hashes: tuple[str, ...]
    ordered_event_ids_hash: str
    artifact_references: tuple[str, ...]
    artifact_hashes: tuple[str, ...]
    event_schema_version: str
    reducer_version: str
    manifest_schema_version: str
    contract_version: str
    provenance_class: str
    provenance_id: str
    actor_class: str
    state_hash: str
    manifest_hash: str
    created_at: str

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "revision": self.revision,
            "previous_revision": self.previous_revision,
            "previous_manifest_hash": self.previous_manifest_hash,
            "transition_kind": self.transition_kind,
            "command_id": self.command_id,
            "commit_id": self.commit_id,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "event_count": self.event_count,
            "first_event_sequence": self.first_event_sequence,
            "last_event_sequence": self.last_event_sequence,
            "ordered_event_ids": list(self.ordered_event_ids),
            "ordered_event_hashes": list(self.ordered_event_hashes),
            "artifact_references": list(self.artifact_references),
            "artifact_hashes": list(self.artifact_hashes),
            "event_schema_version": self.event_schema_version,
            "reducer_version": self.reducer_version,
            "manifest_schema_version": self.manifest_schema_version,
            "contract_version": self.contract_version,
            "provenance_class": self.provenance_class,
            "provenance_id": self.provenance_id,
            "actor_class": self.actor_class,
            "created_at": self.created_at,
            "state_hash": self.state_hash,
        }

    @property
    def hash_valid(self) -> bool:
        return canonical_manifest_hash(self.canonical_payload()) == self.manifest_hash


class RevisionManifestRepository:
    """Read-only application interface for the immutable revision ledger.

    Manifest creation is intentionally private to ProjectRevisionAllocator and
    native initialization. Events own domain changes; artifacts own large bytes.
    This repository never reconstructs story state from a manifest.
    """

    def __init__(self, database: Database):
        self.database = database

    def get(self, project_id: str, revision: int) -> RevisionManifest | None:
        with self.database.read() as conn:
            row = conn.execute(
                "SELECT * FROM project_revisions WHERE project_id=? AND revision=?",
                (project_id, revision),
            ).fetchone()
        return self.from_row(row) if row else None

    def latest(self, project_id: str) -> RevisionManifest | None:
        with self.database.read() as conn:
            row = conn.execute(
                "SELECT * FROM project_revisions WHERE project_id=? ORDER BY revision DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return self.from_row(row) if row else None

    def list(self, project_id: str) -> list[RevisionManifest]:
        with self.database.read() as conn:
            rows = conn.execute(
                "SELECT * FROM project_revisions WHERE project_id=? ORDER BY revision",
                (project_id,),
            ).fetchall()
        return [self.from_row(row) for row in rows]

    @staticmethod
    def from_row(row: Any) -> RevisionManifest:
        return RevisionManifest(
            project_id=row["project_id"], revision=int(row["revision"]), manifest_id=row["manifest_id"],
            previous_revision=row["previous_revision"], previous_manifest_hash=row["previous_manifest_hash"],
            transition_kind=row["transition_kind"], command_id=row["command_id"], commit_id=row["commit_id"],
            idempotency_key=row["idempotency_key"], request_hash=row["request_hash"], event_count=int(row["event_count"]),
            first_event_sequence=row["first_event_sequence"], last_event_sequence=row["last_event_sequence"],
            ordered_event_ids=tuple(json.loads(row["ordered_event_ids_json"])),
            ordered_event_hashes=tuple(json.loads(row["ordered_event_hashes_json"])),
            ordered_event_ids_hash=row["ordered_event_ids_hash"],
            artifact_references=tuple(json.loads(row["artifact_refs_json"])),
            artifact_hashes=tuple(json.loads(row["artifact_hashes_json"])),
            event_schema_version=row["event_schema_version"], reducer_version=row["reducer_version"],
            manifest_schema_version=row["manifest_schema_version"], contract_version=row["contract_version"],
            provenance_class=row["provenance_class"], provenance_id=row["provenance_id"],
            actor_class=row["actor_class"], state_hash=row["state_hash"], manifest_hash=row["manifest_hash"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class RevisionTransition:
    project_id: str
    expected_revision: int
    transition_kind: str
    command_id: str
    commit_id: str | None
    idempotency_key: str
    request_hash: str
    artifact_references: tuple[tuple[str, str], ...]
    provenance_class: str
    provenance_id: str
    actor_class: str
    created_at: str
    pre_transition_state_hash: str
    event_schema_version: str = EVENT_SCHEMA_VERSION
    reducer_version: str = REDUCER_VERSION


@dataclass(frozen=True)
class AuthorityWriteResult:
    event_ids: tuple[str, ...]
    state_hash: str


@dataclass(frozen=True)
class RevisionTransitionResult:
    revision: int
    manifest: RevisionManifest
    replayed: bool = False


@dataclass(frozen=True)
class ManifestIntegrityIssue:
    code: str
    message: str
    revision: int | None = None
    field: str | None = None
    observed_value: str | None = None
    supported_values: tuple[str, ...] = ()
    severity: str = "error"
    verification_stopped: bool = False
    replay_safe: bool | None = None
    chain_health: str | None = None
    chain_impact_start: int | None = None
    chain_impact_end: int | None = None
    latest_trusted_revision: int | None = None
    first_untrusted_revision: int | None = None
    total_affected_revisions: int | None = None

    def __iter__(self):
        # Preserve the original two-value iteration used by project status.
        yield self.code
        yield self.message


class ProjectRevisionAllocator:
    """The sole interface for finalizing a post-initialization story revision.

    Callers supply one authority-write callback. This module hides bootstrap
    compatibility, next-revision allocation, event/artifact membership,
    canonical hashing, immutable manifest insertion and the project CAS. The
    caller owns the outer ``BEGIN IMMEDIATE`` transaction and final commit.
    """

    def execute(
        self,
        conn: Any,
        transition: RevisionTransition,
        write_authority: Callable[[int], AuthorityWriteResult],
    ) -> RevisionTransitionResult:
        previous = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id=? AND idempotency_key=?",
            (transition.project_id, transition.idempotency_key),
        ).fetchone()
        if previous:
            manifest = RevisionManifestRepository.from_row(previous)
            if manifest.request_hash != _tagged_hash(transition.request_hash):
                raise ConflictError("IDEMPOTENCY_CONFLICT", "idempotency key was used with a different authority payload")
            return RevisionTransitionResult(manifest.revision, manifest, replayed=True)

        project = conn.execute(
            "SELECT * FROM projects WHERE project_id=?", (transition.project_id,)
        ).fetchone()
        if project is None:
            raise ConflictError("PROJECT_NOT_FOUND", f"project not found: {transition.project_id}")
        if int(project["revision"]) != transition.expected_revision:
            raise ConflictError(
                "REVISION_CONFLICT",
                f"expected revision {transition.expected_revision}, current revision is {project['revision']}",
                current_revision=project["revision"], retryable=True,
            )

        current_revision = self._ensure_lineage(conn, transition, int(project["revision"]))
        revision = current_revision + 1
        authority = write_authority(revision)
        events = self._load_events(conn, transition.project_id, authority.event_ids)
        previous_manifest = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id=? AND revision=?",
            (transition.project_id, current_revision),
        ).fetchone()
        if previous_manifest is None:
            raise ConflictError("MANIFEST_CHAIN_BROKEN", "current project revision has no manifest")
        manifest = self._insert_manifest(
            conn,
            project_id=transition.project_id,
            revision=revision,
            previous_revision=current_revision,
            previous_manifest_hash=previous_manifest["manifest_hash"],
            transition_kind=transition.transition_kind,
            command_id=transition.command_id,
            commit_id=transition.commit_id,
            idempotency_key=transition.idempotency_key,
            request_hash=transition.request_hash,
            events=events,
            artifact_references=transition.artifact_references,
            event_schema_version=transition.event_schema_version,
            reducer_version=transition.reducer_version,
            provenance_class=transition.provenance_class,
            provenance_id=transition.provenance_id,
            actor_class=transition.actor_class,
            state_hash=authority.state_hash,
            created_at=transition.created_at,
        )
        conn.execute(
            "UPDATE projects SET revision=?,updated_at=?,manifest_backfill_required=0,manifest_writer_version=? "
            "WHERE project_id=? AND revision=?",
            (revision, _utc_timestamp(transition.created_at), MANIFEST_SCHEMA_VERSION,
             transition.project_id, current_revision),
        )
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            raise ConflictError("REVISION_CONFLICT", "project revision changed during manifest CAS", retryable=True)
        return RevisionTransitionResult(revision, manifest)

    def establish_bootstrap(
        self, conn: Any, *, project_id: str, expected_revision: int, state_hash: str,
        provenance_id: str, created_at: str, actor_class: str = "migration_operator",
    ) -> RevisionManifest:
        row = conn.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise ConflictError("PROJECT_NOT_FOUND", f"project not found: {project_id}")
        if int(row["revision"]) != expected_revision:
            raise ConflictError("REVISION_CONFLICT", "bootstrap expected revision is stale", current_revision=row["revision"])
        transition = RevisionTransition(
            project_id=project_id, expected_revision=expected_revision, transition_kind="bootstrap",
            command_id=f"history.bootstrap:{project_id}", commit_id=None,
            idempotency_key=f"history.bootstrap:{project_id}", request_hash=state_hash,
            artifact_references=(), provenance_class="bootstrap_boundary", provenance_id=provenance_id,
            actor_class=actor_class, created_at=created_at, pre_transition_state_hash=state_hash,
            reducer_version="story-reducers/not-applicable",
        )
        revision = self._ensure_lineage(conn, transition, expected_revision)
        manifest = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id=? AND revision=?", (project_id, revision)
        ).fetchone()
        return RevisionManifestRepository.from_row(manifest)

    def _ensure_lineage(self, conn: Any, transition: RevisionTransition, current_revision: int) -> int:
        current = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id=? AND revision=?",
            (transition.project_id, current_revision),
        ).fetchone()
        if current:
            return current_revision
        any_manifest = conn.execute(
            "SELECT 1 FROM project_revisions WHERE project_id=? LIMIT 1", (transition.project_id,)
        ).fetchone()
        if any_manifest:
            raise ConflictError("MANIFEST_CHAIN_BROKEN", "latest project revision is missing its manifest")

        boundary_revision = current_revision
        if current_revision == 0 and self._has_current_state(conn, transition.project_id):
            conn.execute(
                "UPDATE projects SET revision=1,updated_at=? WHERE project_id=? AND revision=0",
                (_utc_timestamp(transition.created_at), transition.project_id),
            )
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise ConflictError("REVISION_CONFLICT", "project changed while establishing bootstrap boundary")
            boundary_revision = 1
        self._insert_manifest(
            conn,
            project_id=transition.project_id,
            revision=boundary_revision,
            previous_revision=None,
            previous_manifest_hash=None,
            transition_kind="bootstrap",
            command_id=f"history.bootstrap:{transition.project_id}",
            commit_id=None,
            idempotency_key=f"history.bootstrap:{transition.project_id}",
            request_hash=transition.pre_transition_state_hash,
            events=[], artifact_references=self._bootstrap_artifact_refs(conn, transition.project_id),
            event_schema_version=EVENT_SCHEMA_VERSION,
            reducer_version="story-reducers/not-applicable",
            provenance_class="bootstrap_boundary",
            provenance_id=transition.provenance_id,
            actor_class=transition.actor_class,
            state_hash=transition.pre_transition_state_hash,
            created_at=transition.created_at,
        )
        conn.execute(
            "UPDATE projects SET history_completeness='bootstrap_boundary',history_available_from_revision=?,"
            "manifest_backfill_required=0,manifest_writer_version=? WHERE project_id=?",
            (boundary_revision, MANIFEST_SCHEMA_VERSION, transition.project_id),
        )
        return boundary_revision

    @staticmethod
    def _has_current_state(conn: Any, project_id: str) -> bool:
        for table in ("entities", "relationships", "story_events", "timeline", "narrative_threads",
                      "chapter_summaries", "facts", "chapter_commits"):
            if conn.execute(f"SELECT 1 FROM {table} WHERE project_id=? LIMIT 1", (project_id,)).fetchone():
                return True
        return False

    @staticmethod
    def _bootstrap_artifact_refs(conn: Any, project_id: str) -> tuple[tuple[str, str], ...]:
        rows = conn.execute(
            "SELECT c.commit_id,c.artifact_sha256 FROM chapter_commits c "
            "JOIN chapter_artifacts a USING(commit_id) WHERE c.project_id=? AND c.state='FINALIZED' "
            "ORDER BY c.chapter_number,c.commit_id",
            (project_id,),
        ).fetchall()
        return tuple((f"chapter:{row['commit_id']}", row["artifact_sha256"]) for row in rows)

    @staticmethod
    def _load_events(conn: Any, project_id: str, event_ids: tuple[str, ...]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for event_id in event_ids:
            row = conn.execute(
                "SELECT * FROM story_events WHERE project_id=? AND event_id=?", (project_id, event_id)
            ).fetchone()
            if row is None:
                raise ConflictError("MANIFEST_EVENT_MISSING", f"manifest event is missing: {event_id}")
            events.append(dict(row))
        return events

    def _insert_manifest(
        self, conn: Any, *, project_id: str, revision: int, previous_revision: int | None,
        previous_manifest_hash: str | None, transition_kind: str, command_id: str,
        commit_id: str | None, idempotency_key: str, request_hash: str,
        events: list[dict[str, Any]], artifact_references: tuple[tuple[str, str], ...],
        event_schema_version: str, reducer_version: str, provenance_class: str,
        provenance_id: str, actor_class: str, state_hash: str, created_at: str,
    ) -> RevisionManifest:
        event_ids = [event["event_id"] for event in events]
        event_hashes = [self._event_hash(event) for event in events]
        sequences = [int(event["sequence"]) for event in events]
        artifacts = sorted(artifact_references, key=lambda item: (item[0], item[1]))
        refs = [item[0] for item in artifacts]
        hashes = [_tagged_hash(item[1]) for item in artifacts]
        timestamp = _utc_timestamp(created_at)
        payload = {
            "project_id": project_id, "revision": revision, "previous_revision": previous_revision,
            "previous_manifest_hash": previous_manifest_hash, "transition_kind": transition_kind,
            "command_id": command_id, "commit_id": commit_id, "idempotency_key": idempotency_key,
            "request_hash": _tagged_hash(request_hash), "event_count": len(events),
            "first_event_sequence": min(sequences) if sequences else None,
            "last_event_sequence": max(sequences) if sequences else None,
            "ordered_event_ids": event_ids, "ordered_event_hashes": event_hashes,
            "artifact_references": refs, "artifact_hashes": hashes,
            "event_schema_version": event_schema_version, "reducer_version": reducer_version,
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
            "provenance_class": provenance_class, "provenance_id": provenance_id,
            "actor_class": actor_class, "created_at": timestamp, "state_hash": _tagged_hash(state_hash),
        }
        manifest_hash = canonical_manifest_hash(payload)
        manifest_id = str(uuid5(_MANIFEST_NAMESPACE, f"{project_id}\0{revision}\0{manifest_hash}"))
        ordered_hash = canonical_manifest_hash({
            "ordered_event_ids": event_ids, "ordered_event_hashes": event_hashes,
        })
        conn.execute(
            "INSERT INTO project_revisions(project_id,revision,manifest_id,previous_revision,previous_manifest_hash,"
            "transition_kind,command_id,commit_id,idempotency_key,request_hash,event_count,first_event_sequence,"
            "last_event_sequence,ordered_event_ids_json,ordered_event_hashes_json,ordered_event_ids_hash,"
            "artifact_refs_json,artifact_hashes_json,event_schema_version,reducer_version,manifest_schema_version,"
            "contract_version,provenance_class,provenance_id,actor_class,state_hash,manifest_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, revision, manifest_id, previous_revision, previous_manifest_hash, transition_kind,
             command_id, commit_id, idempotency_key, _tagged_hash(request_hash), len(events),
             min(sequences) if sequences else None, max(sequences) if sequences else None,
             _json(event_ids), _json(event_hashes), ordered_hash, _json(refs), _json(hashes),
             event_schema_version, reducer_version, MANIFEST_SCHEMA_VERSION, CONTRACT_VERSION,
             provenance_class, provenance_id, actor_class, _tagged_hash(state_hash), manifest_hash, timestamp),
        )
        row = conn.execute("SELECT * FROM project_revisions WHERE manifest_id=?", (manifest_id,)).fetchone()
        return RevisionManifestRepository.from_row(row)

    @staticmethod
    def _event_hash(event: dict[str, Any]) -> str:
        logical = {
            key: event.get(key) for key in (
                "event_id", "project_id", "event_type", "subject", "chapter_number", "payload_json",
                "evidence_json", "confidence", "commit_id", "ordinal", "aggregate_type", "aggregate_id",
                "schema_version", "created_at", "applied_revision",
            )
        }
        return canonical_manifest_hash(logical)


def create_initial_manifest(
    conn: Any, *, project_id: str, command_id: str, idempotency_key: str,
    request_hash: str, created_at: str,
) -> RevisionManifest:
    timestamp = _utc_timestamp(created_at)
    ordered_hash = canonical_manifest_hash({"ordered_event_ids": [], "ordered_event_hashes": []})
    state_hash = canonical_manifest_hash({"authority_state": "empty_initialized", "project_id": project_id})
    payload = {
        "project_id": project_id, "revision": 0, "previous_revision": None,
        "previous_manifest_hash": None, "transition_kind": "initialize_empty",
        "command_id": command_id, "commit_id": None, "idempotency_key": idempotency_key,
        "request_hash": _tagged_hash(request_hash), "event_count": 0,
        "first_event_sequence": None, "last_event_sequence": None,
        "ordered_event_ids": [], "ordered_event_hashes": [],
        "artifact_references": [], "artifact_hashes": [],
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "reducer_version": "story-reducers/not-applicable",
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "provenance_class": "native", "provenance_id": f"project:{project_id}",
        "actor_class": "system", "created_at": timestamp, "state_hash": state_hash,
    }
    manifest_hash = canonical_manifest_hash(payload)
    manifest_id = str(uuid5(_MANIFEST_NAMESPACE, f"{project_id}\0{0}\0{manifest_hash}"))
    conn.execute(
        "INSERT INTO project_revisions(project_id,revision,manifest_id,previous_revision,previous_manifest_hash,"
        "transition_kind,command_id,commit_id,idempotency_key,request_hash,event_count,first_event_sequence,"
        "last_event_sequence,ordered_event_ids_json,ordered_event_hashes_json,ordered_event_ids_hash,"
        "artifact_refs_json,artifact_hashes_json,event_schema_version,reducer_version,manifest_schema_version,"
        "contract_version,provenance_class,provenance_id,actor_class,state_hash,manifest_hash,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, 0, manifest_id, None, None, "initialize_empty", command_id, None,
         idempotency_key, _tagged_hash(request_hash), 0, None, None, "[]", "[]", ordered_hash,
         "[]", "[]", EVENT_SCHEMA_VERSION, "story-reducers/not-applicable", MANIFEST_SCHEMA_VERSION,
         CONTRACT_VERSION, "native", f"project:{project_id}", "system", state_hash, manifest_hash, timestamp),
    )
    row = conn.execute("SELECT * FROM project_revisions WHERE manifest_id=?", (manifest_id,)).fetchone()
    return RevisionManifestRepository.from_row(row)


def manifest_integrity_issues(conn: Any, project_id: str) -> list[ManifestIntegrityIssue]:
    """Diagnose ledger integrity without synthesizing or repairing authority."""

    project = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if project is None:
        return [ManifestIntegrityIssue("manifest.project_missing", "project does not exist")]
    rows = conn.execute(
        "SELECT * FROM project_revisions WHERE project_id=? ORDER BY revision", (project_id,)
    ).fetchall()
    if not rows:
        severity = "missing" if project["authority_mode"] == "runtime" else "bootstrap_required"
        return [ManifestIntegrityIssue(f"manifest.{severity}", "project has no finalized revision manifest")]

    issues: list[ManifestIntegrityIssue] = []
    manifests = [RevisionManifestRepository.from_row(row) for row in rows]
    latest = manifests[-1]
    if latest.revision != int(project["revision"]):
        issues.append(ManifestIntegrityIssue("manifest.latest_mismatch", "project revision differs from latest manifest", latest.revision))
    first = manifests[0]
    if first.revision != 0 and first.provenance_class != "bootstrap_boundary":
        issues.append(ManifestIntegrityIssue("manifest.lineage_start", "non-zero lineage start is not a bootstrap boundary", first.revision))
    if first.revision == 0 and first.transition_kind not in {"initialize_empty", "bootstrap"}:
        issues.append(ManifestIntegrityIssue("manifest.revision_zero", "revision zero has an invalid transition kind", first.revision))

    allocator = ProjectRevisionAllocator()
    previous: RevisionManifest | None = None
    for manifest in manifests:
        compatibility_values = {
            "manifest_schema_version": manifest.manifest_schema_version,
            "event_schema_version": manifest.event_schema_version,
            "reducer_version": manifest.reducer_version,
            "contract_version": manifest.contract_version,
            "provenance_class": manifest.provenance_class,
            "transition_kind": manifest.transition_kind,
        }
        verification_stopped = False
        for field, observed in compatibility_values.items():
            policy = KNOWN_REVISION_COMPATIBILITY[field]
            if observed in policy.supported_values:
                continue
            verification_stopped = verification_stopped or policy.stops_integrity_verification
            issues.append(ManifestIntegrityIssue(
                code=policy.diagnostic_code,
                message=(f"unknown {field} value {observed!r}; integrity or replay compatibility "
                         "cannot be assumed and no automatic rewrite is permitted"),
                revision=manifest.revision,
                field=field,
                observed_value=observed,
                supported_values=tuple(supported_values(field)),
                severity="critical" if policy.stops_integrity_verification else "error",
                verification_stopped=policy.stops_integrity_verification,
                replay_safe=False if policy.replay_safety_relevant else None,
                chain_health="UNVERIFIABLE_UNKNOWN_VERSION",
            ))
            if field == "manifest_schema_version":
                canonical_policy = KNOWN_REVISION_COMPATIBILITY["canonicalization_version"]
                issues.append(ManifestIntegrityIssue(
                    code=canonical_policy.diagnostic_code,
                    message=("canonical serialization cannot be selected for unknown manifest schema "
                             f"{observed!r}"),
                    revision=manifest.revision,
                    field="canonicalization_version",
                    observed_value=f"unverifiable-for:{observed}",
                    supported_values=tuple(supported_values("canonicalization_version")),
                    severity="critical",
                    verification_stopped=True,
                    chain_health="UNVERIFIABLE_UNKNOWN_VERSION",
                ))

        hash_values: list[tuple[str, str]] = [
            ("manifest_hash", manifest.manifest_hash),
            ("request_hash", manifest.request_hash),
            ("ordered_event_ids_hash", manifest.ordered_event_ids_hash),
            ("state_hash", manifest.state_hash),
        ]
        if manifest.previous_manifest_hash:
            hash_values.append(("previous_manifest_hash", manifest.previous_manifest_hash))
        hash_values.extend(
            (f"ordered_event_hashes[{index}]", value)
            for index, value in enumerate(manifest.ordered_event_hashes)
        )
        hash_values.extend(
            (f"artifact_hashes[{index}]", value)
            for index, value in enumerate(manifest.artifact_hashes)
        )
        hash_policy = KNOWN_REVISION_COMPATIBILITY["hash_algorithm"]
        for field, value in hash_values:
            observed = value.split(":", 1)[0] if ":" in value else "untagged"
            if observed in hash_policy.supported_values:
                continue
            verification_stopped = True
            issues.append(ManifestIntegrityIssue(
                code=hash_policy.diagnostic_code,
                message=f"unknown hash algorithm {observed!r} in {field}; hash verification stopped",
                revision=manifest.revision,
                field=field,
                observed_value=observed,
                supported_values=tuple(supported_values("hash_algorithm")),
                severity="critical",
                verification_stopped=True,
                chain_health="UNVERIFIABLE_UNKNOWN_VERSION",
            ))

        if not verification_stopped and not manifest.hash_valid:
            issues.append(ManifestIntegrityIssue(f"manifest.hash.{manifest.revision}", "canonical manifest hash mismatch", manifest.revision, chain_health="CORRUPTED"))
        if previous is not None:
            if manifest.previous_revision != previous.revision:
                issues.append(ManifestIntegrityIssue(f"manifest.previous_revision.{manifest.revision}", "manifest revision chain is not contiguous", manifest.revision, chain_health="MISSING_PREDECESSOR"))
            if manifest.previous_manifest_hash != previous.manifest_hash:
                issues.append(ManifestIntegrityIssue(f"manifest.previous_hash.{manifest.revision}", "previous manifest hash mismatch", manifest.revision, chain_health="CORRUPTED"))
        if not all((manifest.event_schema_version, manifest.reducer_version,
                    manifest.manifest_schema_version, manifest.contract_version)):
            issues.append(ManifestIntegrityIssue(f"manifest.compatibility.{manifest.revision}", "manifest compatibility version is empty", manifest.revision, chain_health="UNVERIFIABLE_UNKNOWN_VERSION"))
        if manifest.event_count != len(manifest.ordered_event_ids) or manifest.event_count != len(manifest.ordered_event_hashes):
            issues.append(ManifestIntegrityIssue(f"manifest.event_count.{manifest.revision}", "event count does not match ordered membership", manifest.revision, chain_health="CORRUPTED"))
        ordered_hash = canonical_manifest_hash({
            "ordered_event_ids": list(manifest.ordered_event_ids),
            "ordered_event_hashes": list(manifest.ordered_event_hashes),
        })
        if not verification_stopped and ordered_hash != manifest.ordered_event_ids_hash:
            issues.append(ManifestIntegrityIssue(f"manifest.event_membership_hash.{manifest.revision}", "ordered event membership hash mismatch", manifest.revision, chain_health="CORRUPTED"))
        try:
            loaded = allocator._load_events(conn, project_id, manifest.ordered_event_ids) if manifest.ordered_event_ids else []
        except ConflictError:
            loaded = []
            issues.append(ManifestIntegrityIssue(f"manifest.event_missing.{manifest.revision}", "manifest references a missing event", manifest.revision, chain_health="CORRUPTED"))
        if loaded:
            sequences = [int(event["sequence"]) for event in loaded]
            if min(sequences) != manifest.first_event_sequence or max(sequences) != manifest.last_event_sequence:
                issues.append(ManifestIntegrityIssue(f"manifest.event_range.{manifest.revision}", "event acceleration range does not match membership", manifest.revision, chain_health="CORRUPTED"))
            if not verification_stopped:
                actual_hashes = tuple(allocator._event_hash(event) for event in loaded)
                if actual_hashes != manifest.ordered_event_hashes:
                    issues.append(ManifestIntegrityIssue(f"manifest.event_hash.{manifest.revision}", "event envelope hash mismatch", manifest.revision, chain_health="CORRUPTED"))
            if any(event["applied_revision"] != manifest.revision for event in loaded):
                issues.append(ManifestIntegrityIssue(f"manifest.event_revision.{manifest.revision}", "event revision does not match manifest", manifest.revision, chain_health="CORRUPTED"))
        if len(manifest.artifact_references) != len(manifest.artifact_hashes):
            issues.append(ManifestIntegrityIssue(f"manifest.artifact_count.{manifest.revision}", "artifact references and hashes are misaligned", manifest.revision, chain_health="CORRUPTED"))
        for reference, digest in zip(manifest.artifact_references, manifest.artifact_hashes):
            if reference.startswith("chapter:"):
                commit_id = reference.removeprefix("chapter:")
                artifact = conn.execute(
                    "SELECT c.artifact_sha256,c.resulting_revision,c.state,a.schema_version FROM chapter_commits c "
                    "JOIN chapter_artifacts a USING(commit_id) WHERE c.project_id=? AND c.commit_id=?",
                    (project_id, commit_id),
                ).fetchone()
                if artifact is None:
                    issues.append(ManifestIntegrityIssue(f"manifest.artifact_hash.{manifest.revision}", "chapter artifact is missing or hash-mismatched", manifest.revision, chain_health="CORRUPTED"))
                else:
                    if not verification_stopped and _tagged_hash(artifact["artifact_sha256"]) != digest:
                        issues.append(ManifestIntegrityIssue(f"manifest.artifact_hash.{manifest.revision}", "chapter artifact is missing or hash-mismatched", manifest.revision, chain_health="CORRUPTED"))
                    artifact_policy = KNOWN_REVISION_COMPATIBILITY["artifact_schema_version"]
                    if artifact["schema_version"] not in artifact_policy.supported_values:
                        issues.append(ManifestIntegrityIssue(
                            artifact_policy.diagnostic_code,
                            "referenced artifact uses an unknown schema and cannot be safely interpreted",
                            manifest.revision,
                            field="chapter_artifacts.schema_version",
                            observed_value=artifact["schema_version"],
                            supported_values=tuple(supported_values("artifact_schema_version")),
                            severity="error",
                            replay_safe=False,
                            chain_health="UNVERIFIABLE_UNKNOWN_VERSION",
                        ))
                    if artifact["state"] != "FINALIZED" or (
                        manifest.transition_kind in {"chapter_finalize", "chapter_replace"}
                        and int(artifact["resulting_revision"]) != manifest.revision
                    ):
                        issues.append(ManifestIntegrityIssue(f"manifest.commit_link.{manifest.revision}", "chapter commit is not finalized at manifest revision", manifest.revision, chain_health="CORRUPTED"))

        expected_command = expected_command_id(manifest)
        other_bindings = conn.execute(
            "SELECT project_id,revision FROM project_revisions WHERE command_id=? "
            "AND NOT (project_id=? AND revision=?)",
            (manifest.command_id, project_id, manifest.revision),
        ).fetchall()
        expected_bindings: list[tuple[str, int]] = []
        if expected_command is not None and manifest.command_id != expected_command:
            for candidate_row in conn.execute(
                "SELECT * FROM project_revisions WHERE NOT (project_id=? AND revision=?)",
                (project_id, manifest.revision),
            ):
                candidate = RevisionManifestRepository.from_row(candidate_row)
                if expected_command_id(candidate) == manifest.command_id:
                    expected_bindings.append((candidate.project_id, candidate.revision))
        if other_bindings:
            issues.append(ManifestIntegrityIssue(
                "DUPLICATE_COMMAND_ID",
                "command identity is bound to more than one immutable authority transition",
                manifest.revision,
                field="command_id",
                observed_value=manifest.command_id,
                severity="critical",
                chain_health="CORRUPTED",
            ))
        if expected_command is not None and manifest.command_id != expected_command:
            cross_project = (
                any(row["project_id"] != project_id for row in other_bindings)
                or any(bound_project != project_id for bound_project, _ in expected_bindings)
            )
            same_project = (
                any(row["project_id"] == project_id for row in other_bindings)
                or any(bound_project == project_id for bound_project, _ in expected_bindings)
            )
            code = (
                "COMMAND_PROJECT_MISMATCH" if cross_project
                else "COMMAND_ID_REBOUND" if same_project
                else "MANIFEST_COMMAND_REFERENCE_MISSING"
            )
            issues.append(ManifestIntegrityIssue(
                code,
                f"manifest command identity does not match the real {manifest.transition_kind} command",
                manifest.revision,
                field="command_id",
                observed_value=manifest.command_id,
                supported_values=(expected_command,),
                severity="critical",
                chain_health="CORRUPTED",
            ))

        ledger = None
        if manifest.transition_kind != "bootstrap":
            ledger = conn.execute(
                "SELECT project_id,idempotency_key,operation,result_json,request_hash "
                "FROM idempotency_ledger WHERE project_id=? AND idempotency_key=?",
                (project_id, manifest.idempotency_key),
            ).fetchone()
            if ledger is None:
                issues.append(ManifestIntegrityIssue(
                    "MANIFEST_COMMAND_REFERENCE_MISSING",
                    "manifest has no command/idempotency ledger record",
                    manifest.revision,
                    field="idempotency_key",
                    observed_value=manifest.idempotency_key,
                    severity="critical",
                    chain_health="CORRUPTED",
                ))
            else:
                try:
                    command_result = json.loads(ledger["result_json"])
                except (TypeError, json.JSONDecodeError):
                    command_result = None
                if not isinstance(command_result, dict):
                    issues.append(ManifestIntegrityIssue(
                        "COMMAND_PROVENANCE_INCOMPLETE",
                        "command ledger result is unavailable or malformed",
                        manifest.revision,
                        field="result_json",
                        observed_value=str(ledger["result_json"]),
                        severity="critical",
                        chain_health="CORRUPTED",
                    ))
                else:
                    resulting_revision = command_result.get(
                        "revision", command_result.get("resulting_revision")
                    )
                    if resulting_revision != manifest.revision:
                        issues.append(ManifestIntegrityIssue(
                            "COMMAND_REVISION_MISMATCH",
                            "command ledger resulting revision differs from its manifest",
                            manifest.revision,
                            field="result_json.revision",
                            observed_value=str(resulting_revision),
                            supported_values=(str(manifest.revision),),
                            severity="critical",
                            chain_health="CORRUPTED",
                        ))
                if (
                    manifest.transition_kind in {"initialize_empty", "domain_command"}
                    and ledger["request_hash"]
                    and _tagged_hash(ledger["request_hash"]) != manifest.request_hash
                ):
                    issues.append(ManifestIntegrityIssue(
                        "MANIFEST_COMMAND_REFERENCE_MISMATCH",
                        "manifest request hash differs from the command ledger",
                        manifest.revision,
                        field="request_hash",
                        observed_value=manifest.request_hash,
                        supported_values=(_tagged_hash(ledger["request_hash"]),),
                        severity="critical",
                        chain_health="CORRUPTED",
                    ))
                expected_operation = {
                    "initialize_empty": "project.create",
                    "domain_command": "events.append",
                    "chapter_finalize": "chapter.lifecycle",
                    "chapter_replace": "chapter.lifecycle",
                }.get(manifest.transition_kind)
                if expected_operation and ledger["operation"] != expected_operation:
                    issues.append(ManifestIntegrityIssue(
                        "COMMAND_PROVENANCE_INCOMPLETE",
                        "command ledger operation does not match manifest transition kind",
                        manifest.revision,
                        field="idempotency_ledger.operation",
                        observed_value=ledger["operation"],
                        supported_values=(expected_operation,),
                        severity="critical",
                        chain_health="CORRUPTED",
                    ))

        if manifest.transition_kind in {"chapter_finalize", "chapter_replace"}:
            commit = conn.execute(
                "SELECT commit_id,project_id,idempotency_key,resulting_revision,state "
                "FROM chapter_commits WHERE commit_id=?",
                (manifest.commit_id,),
            ).fetchone()
            if commit is None:
                issues.append(ManifestIntegrityIssue(
                    "MANIFEST_COMMAND_REFERENCE_MISSING",
                    "manifest chapter command references a missing commit",
                    manifest.revision,
                    field="commit_id",
                    observed_value=str(manifest.commit_id),
                    severity="critical",
                    chain_health="CORRUPTED",
                ))
            else:
                if commit["project_id"] != project_id:
                    issues.append(ManifestIntegrityIssue(
                        "COMMAND_PROJECT_MISMATCH",
                        "chapter commit belongs to another project",
                        manifest.revision,
                        field="chapter_commits.project_id",
                        observed_value=commit["project_id"],
                        supported_values=(project_id,),
                        severity="critical",
                        chain_health="CORRUPTED",
                    ))
                if (
                    commit["idempotency_key"] != manifest.idempotency_key
                    or commit["resulting_revision"] != manifest.revision
                    or commit["state"] != "FINALIZED"
                ):
                    issues.append(ManifestIntegrityIssue(
                        "COMMAND_COMMIT_MISMATCH",
                        "chapter commit provenance differs from its manifest command",
                        manifest.revision,
                        field="chapter_commits.resulting_revision",
                        observed_value=str(commit["resulting_revision"]),
                        supported_values=(str(manifest.revision),),
                        severity="critical",
                        chain_health="CORRUPTED",
                    ))

        if loaded:
            expected_event_command = (
                manifest.commit_id
                if manifest.transition_kind in {"chapter_finalize", "chapter_replace"}
                else manifest.provenance_id if manifest.transition_kind == "domain_command" else None
            )
            if expected_event_command and any(event["commit_id"] != expected_event_command for event in loaded):
                issues.append(ManifestIntegrityIssue(
                    "COMMAND_EVENT_RANGE_MISMATCH",
                    "one or more manifest events belong to another command/commit",
                    manifest.revision,
                    field="story_events.commit_id",
                    observed_value=",".join(sorted({str(event["commit_id"]) for event in loaded})),
                    supported_values=(expected_event_command,),
                    severity="critical",
                    chain_health="CORRUPTED",
                ))
        if manifest.transition_kind in {"initialize_empty", "domain_command"}:
            command = conn.execute(
                "SELECT 1 FROM idempotency_ledger WHERE project_id=? AND idempotency_key=?",
                (project_id, manifest.idempotency_key),
            ).fetchone()
            if command is None:
                issues.append(ManifestIntegrityIssue(f"manifest.transition_missing.{manifest.revision}", "manifest has no corresponding committed command transition", manifest.revision, chain_health="CORRUPTED"))
        elif manifest.transition_kind in {"chapter_finalize", "chapter_replace"}:
            commit = conn.execute(
                "SELECT 1 FROM chapter_commits WHERE project_id=? AND commit_id=? AND state='FINALIZED'",
                (project_id, manifest.commit_id),
            ).fetchone()
            if commit is None:
                issues.append(ManifestIntegrityIssue(f"manifest.transition_missing.{manifest.revision}", "manifest has no corresponding finalized chapter transition", manifest.revision, chain_health="CORRUPTED"))
        previous = manifest

    event_policy = KNOWN_REVISION_COMPATIBILITY["event_schema_version"]
    legacy_boundary_revision = manifests[0].revision if manifests else int(project["revision"])
    for event in conn.execute(
        "SELECT event_id,schema_version,applied_revision FROM story_events "
        "WHERE project_id=? AND schema_version IS NOT NULL ORDER BY sequence",
        (project_id,),
    ):
        if event["schema_version"] in event_policy.supported_values:
            continue
        issues.append(ManifestIntegrityIssue(
            event_policy.diagnostic_code,
            f"event {event['event_id']} uses an unknown schema; historical replay is unsafe",
            int(event["applied_revision"]) if event["applied_revision"] is not None else legacy_boundary_revision,
            field="story_events.schema_version",
            observed_value=event["schema_version"],
            supported_values=tuple(supported_values("event_schema_version")),
            severity="error",
            replay_safe=False,
        ))

    direct_health: dict[int, str] = {}
    priority = {
        "CORRUPTED": 1,
        "UNVERIFIABLE_UNKNOWN_VERSION": 2,
        "MISSING_PREDECESSOR": 3,
    }
    for issue in issues:
        if issue.revision is None or issue.chain_health not in priority:
            continue
        current = direct_health.get(issue.revision)
        if current is None or priority[issue.chain_health] > priority[current]:
            direct_health[issue.revision] = issue.chain_health
    if direct_health:
        first_untrusted = min(direct_health)
        latest_trusted = next(
            (manifest.revision for manifest in reversed(manifests) if manifest.revision < first_untrusted),
            None,
        )
        affected = [manifest for manifest in manifests if manifest.revision >= first_untrusted]
        for manifest in affected:
            health = direct_health.get(manifest.revision, "AFFECTED_BY_PRIOR_CORRUPTION")
            code = {
                "CORRUPTED": "MANIFEST_CHAIN_CORRUPTED",
                "UNVERIFIABLE_UNKNOWN_VERSION": "MANIFEST_CHAIN_UNVERIFIABLE",
                "MISSING_PREDECESSOR": "MANIFEST_CHAIN_MISSING_PREDECESSOR",
                "AFFECTED_BY_PRIOR_CORRUPTION": "MANIFEST_CHAIN_AFFECTED",
            }[health]
            message = (
                f"revision {manifest.revision} is directly {health.lower()}"
                if manifest.revision in direct_health
                else (f"revision {manifest.revision} is affected by prior corruption at "
                      f"revision {first_untrusted}")
            )
            issues.append(ManifestIntegrityIssue(
                code,
                message,
                manifest.revision,
                severity="critical" if manifest.revision in direct_health else "error",
                chain_health=health,
            ))
        impact_end = affected[-1].revision
        issues.append(ManifestIntegrityIssue(
            "MANIFEST_CHAIN_IMPACT",
            f"manifest trust chain is untrusted for revisions {first_untrusted}..{impact_end}; "
            "restore exact immutable authority from a verified backup and do not synthesize history",
            first_untrusted,
            severity="critical",
            chain_health=direct_health[first_untrusted],
            chain_impact_start=first_untrusted,
            chain_impact_end=impact_end,
            latest_trusted_revision=latest_trusted,
            first_untrusted_revision=first_untrusted,
            total_affected_revisions=len(affected),
        ))
    return issues
