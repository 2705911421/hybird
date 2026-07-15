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


MANIFEST_SCHEMA_VERSION = "revision-manifest/v1"
EVENT_SCHEMA_VERSION = "legacy-unversioned"
REDUCER_VERSION = "story-reducers/legacy-v1"
CONTRACT_VERSION = "story-runtime/v1"
_MANIFEST_NAMESPACE = UUID("6f816d60-7f6b-5bd6-bac4-95e4dc6edb14")


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


def manifest_integrity_issues(conn: Any, project_id: str) -> list[tuple[str, str]]:
    """Diagnose ledger integrity without synthesizing or repairing authority."""

    project = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if project is None:
        return [("manifest.project_missing", "project does not exist")]
    rows = conn.execute(
        "SELECT * FROM project_revisions WHERE project_id=? ORDER BY revision", (project_id,)
    ).fetchall()
    if not rows:
        severity = "missing" if project["authority_mode"] == "runtime" else "bootstrap_required"
        return [(f"manifest.{severity}", "project has no finalized revision manifest")]

    issues: list[tuple[str, str]] = []
    manifests = [RevisionManifestRepository.from_row(row) for row in rows]
    latest = manifests[-1]
    if latest.revision != int(project["revision"]):
        issues.append(("manifest.latest_mismatch", "project revision differs from latest manifest"))
    first = manifests[0]
    if first.revision != 0 and first.provenance_class != "bootstrap_boundary":
        issues.append(("manifest.lineage_start", "non-zero lineage start is not a bootstrap boundary"))
    if first.revision == 0 and first.transition_kind not in {"initialize_empty", "bootstrap"}:
        issues.append(("manifest.revision_zero", "revision zero has an invalid transition kind"))

    allocator = ProjectRevisionAllocator()
    previous: RevisionManifest | None = None
    for manifest in manifests:
        if not manifest.hash_valid:
            issues.append((f"manifest.hash.{manifest.revision}", "canonical manifest hash mismatch"))
        if previous is not None:
            if manifest.previous_revision != previous.revision:
                issues.append((f"manifest.previous_revision.{manifest.revision}", "manifest revision chain is not contiguous"))
            if manifest.previous_manifest_hash != previous.manifest_hash:
                issues.append((f"manifest.previous_hash.{manifest.revision}", "previous manifest hash mismatch"))
        if not all((manifest.event_schema_version, manifest.reducer_version,
                    manifest.manifest_schema_version, manifest.contract_version)):
            issues.append((f"manifest.compatibility.{manifest.revision}", "manifest compatibility version is empty"))
        if manifest.event_count != len(manifest.ordered_event_ids) or manifest.event_count != len(manifest.ordered_event_hashes):
            issues.append((f"manifest.event_count.{manifest.revision}", "event count does not match ordered membership"))
        ordered_hash = canonical_manifest_hash({
            "ordered_event_ids": list(manifest.ordered_event_ids),
            "ordered_event_hashes": list(manifest.ordered_event_hashes),
        })
        if ordered_hash != manifest.ordered_event_ids_hash:
            issues.append((f"manifest.event_membership_hash.{manifest.revision}", "ordered event membership hash mismatch"))
        try:
            loaded = allocator._load_events(conn, project_id, manifest.ordered_event_ids) if manifest.ordered_event_ids else []
        except ConflictError:
            loaded = []
            issues.append((f"manifest.event_missing.{manifest.revision}", "manifest references a missing event"))
        if loaded:
            sequences = [int(event["sequence"]) for event in loaded]
            if min(sequences) != manifest.first_event_sequence or max(sequences) != manifest.last_event_sequence:
                issues.append((f"manifest.event_range.{manifest.revision}", "event acceleration range does not match membership"))
            actual_hashes = tuple(allocator._event_hash(event) for event in loaded)
            if actual_hashes != manifest.ordered_event_hashes:
                issues.append((f"manifest.event_hash.{manifest.revision}", "event envelope hash mismatch"))
            if any(event["applied_revision"] != manifest.revision for event in loaded):
                issues.append((f"manifest.event_revision.{manifest.revision}", "event revision does not match manifest"))
        if len(manifest.artifact_references) != len(manifest.artifact_hashes):
            issues.append((f"manifest.artifact_count.{manifest.revision}", "artifact references and hashes are misaligned"))
        for reference, digest in zip(manifest.artifact_references, manifest.artifact_hashes):
            if reference.startswith("chapter:"):
                commit_id = reference.removeprefix("chapter:")
                artifact = conn.execute(
                    "SELECT c.artifact_sha256,c.resulting_revision,c.state FROM chapter_commits c "
                    "JOIN chapter_artifacts a USING(commit_id) WHERE c.project_id=? AND c.commit_id=?",
                    (project_id, commit_id),
                ).fetchone()
                if artifact is None or _tagged_hash(artifact["artifact_sha256"]) != digest:
                    issues.append((f"manifest.artifact_hash.{manifest.revision}", "chapter artifact is missing or hash-mismatched"))
                elif artifact["state"] != "FINALIZED" or (
                    manifest.transition_kind in {"chapter_finalize", "chapter_replace"}
                    and int(artifact["resulting_revision"]) != manifest.revision
                ):
                    issues.append((f"manifest.commit_link.{manifest.revision}", "chapter commit is not finalized at manifest revision"))
        if manifest.transition_kind in {"initialize_empty", "domain_command"}:
            command = conn.execute(
                "SELECT 1 FROM idempotency_ledger WHERE project_id=? AND idempotency_key=?",
                (project_id, manifest.idempotency_key),
            ).fetchone()
            if command is None:
                issues.append((f"manifest.transition_missing.{manifest.revision}", "manifest has no corresponding committed command transition"))
        elif manifest.transition_kind in {"chapter_finalize", "chapter_replace"}:
            commit = conn.execute(
                "SELECT 1 FROM chapter_commits WHERE project_id=? AND commit_id=? AND state='FINALIZED'",
                (project_id, manifest.commit_id),
            ).fetchone()
            if commit is None:
                issues.append((f"manifest.transition_missing.{manifest.revision}", "manifest has no corresponding finalized chapter transition"))
        previous = manifest
    return issues
