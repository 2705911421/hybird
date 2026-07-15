from __future__ import annotations

from copy import deepcopy

import pytest
from uuid import uuid4

from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.config import RuntimeConfig
from story_runtime.contracts import CreateProjectRequest, StoryEventInput, TypedDiffCommandRequest
from story_runtime.database import Database
from story_runtime.revision_manifests import (
    AuthorityWriteResult,
    ProjectRevisionAllocator,
    RevisionManifestRepository,
    RevisionTransition,
    canonical_manifest_hash,
)
from story_runtime.repository import StoryRepository
from story_runtime.services import RuntimeServices


def _manifest_payload() -> dict:
    return {
        "project_id": "book-一",
        "revision": 2,
        "previous_revision": 1,
        "previous_manifest_hash": "sha256:" + "1" * 64,
        "transition_kind": "domain_command",
        "command_id": "command-2",
        "commit_id": None,
        "idempotency_key": "typed-diff-key-0002",
        "request_hash": "sha256:" + "2" * 64,
        "event_count": 2,
        "first_event_sequence": 8,
        "last_event_sequence": 9,
        "ordered_event_ids": ["event-a", "event-b"],
        "ordered_event_hashes": ["sha256:" + "a" * 64, "sha256:" + "b" * 64],
        "artifact_references": ["chapter:2", "summary:2"],
        "artifact_hashes": ["sha256:" + "c" * 64, "sha256:" + "d" * 64],
        "event_schema_version": "legacy-unversioned",
        "reducer_version": "story-reducers/legacy-v1",
        "manifest_schema_version": "revision-manifest/v1",
        "contract_version": "story-runtime/v1",
        "provenance_class": "native",
        "provenance_id": "command:2",
        "actor_class": "human_operator",
        "created_at": "2026-07-15T10:11:12.123456Z",
        "state_hash": "sha256:" + "e" * 64,
    }


def test_canonical_manifest_hash_is_stable_and_semantically_sensitive() -> None:
    payload = _manifest_payload()
    reordered_keys = dict(reversed(list(payload.items())))
    assert canonical_manifest_hash(payload) == canonical_manifest_hash(reordered_keys)

    changed_event_order = deepcopy(payload)
    changed_event_order["ordered_event_ids"].reverse()
    assert canonical_manifest_hash(payload) != canonical_manifest_hash(changed_event_order)

    changed_artifact = deepcopy(payload)
    changed_artifact["artifact_hashes"][0] = "sha256:" + "f" * 64
    assert canonical_manifest_hash(payload) != canonical_manifest_hash(changed_artifact)

    changed_previous = deepcopy(payload)
    changed_previous["previous_manifest_hash"] = "sha256:" + "0" * 64
    assert canonical_manifest_hash(payload) != canonical_manifest_hash(changed_previous)


def test_migration_adds_an_immutable_revision_ledger(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "manifest.db"))
    assert database.migrations.migrate() == 8
    with database.connect() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(project_revisions)")}
        assert {
            "project_id", "revision", "manifest_id", "previous_revision",
            "previous_manifest_hash", "command_id", "commit_id", "event_count",
            "first_event_sequence", "last_event_sequence", "event_schema_version",
            "reducer_version", "manifest_schema_version", "contract_version",
            "artifact_refs_json", "artifact_hashes_json", "ordered_event_ids_hash",
            "manifest_hash", "created_at",
        } <= columns
        conn.execute(
            "INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) "
            "VALUES ('p',0,'initialized',0,'story-runtime/v1','now','now','runtime')"
        )
        values = (
            "p", 0, "manifest-0", None, None, "initialize_empty", "create-p", None,
            "create-project-key-0001", "sha256:" + "1" * 64, 0, None, None,
            "[]", "[]", "sha256:" + "2" * 64, "[]", "[]",
            "legacy-unversioned", "story-reducers/not-applicable",
            "revision-manifest/v1", "story-runtime/v1", "native", "project:p",
            "system", "sha256:" + "3" * 64, "sha256:" + "4" * 64, "now",
        )
        conn.execute(
            "INSERT INTO project_revisions(project_id,revision,manifest_id,previous_revision,previous_manifest_hash,"
            "transition_kind,command_id,commit_id,idempotency_key,request_hash,event_count,first_event_sequence,"
            "last_event_sequence,ordered_event_ids_json,ordered_event_hashes_json,ordered_event_ids_hash,"
            "artifact_refs_json,artifact_hashes_json,event_schema_version,reducer_version,manifest_schema_version,"
            "contract_version,provenance_class,provenance_id,actor_class,state_hash,manifest_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )
        with pytest.raises(Exception, match="immutable"):
            conn.execute("UPDATE project_revisions SET actor_class='other' WHERE project_id='p'")
        with pytest.raises(Exception, match="immutable"):
            conn.execute("DELETE FROM project_revisions WHERE project_id='p'")
        with pytest.raises(Exception):
            conn.execute("DELETE FROM projects WHERE project_id='p'")


def test_native_project_creation_atomically_creates_revision_zero_and_retries_it(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "native.db"))
    database.migrations.migrate()
    service = ChapterCommitService(database)
    request = CreateProjectRequest(
        request_id=uuid4(), idempotency_key="native-project-create-key-0001",
        project_id="native-book", schema_version="story-runtime/v1",
    )

    first = service.create_project(request)
    second = service.create_project(request.model_copy(update={"request_id": uuid4()}))
    manifests = RevisionManifestRepository(database).list("native-book")

    assert first.revision == second.revision == 0
    assert second.replayed is True
    assert len(manifests) == 1
    assert manifests[0].revision == 0
    assert manifests[0].transition_kind == "initialize_empty"
    assert manifests[0].event_count == 0
    assert manifests[0].previous_revision is None
    assert manifests[0].previous_manifest_hash is None
    assert manifests[0].provenance_id == "project:native-book"
    assert manifests[0].actor_class == "system"


def test_old_database_gets_no_fabricated_rows_and_first_write_establishes_boundary(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "old.db"))
    database.migrations.migrate(target=7)
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) "
            "VALUES ('legacy-book',7,'drafting',3,'story-runtime/v1','old','old','runtime')"
        )
        conn.execute(
            "INSERT INTO entities(project_id,entity_id,entity_type,canonical_name) "
            "VALUES ('legacy-book','e-1','character','Old State')"
        )
    database.migrations.migrate()
    assert RevisionManifestRepository(database).list("legacy-book") == []

    service = ChapterCommitService(database)
    result = service.apply_typed_diff(TypedDiffCommandRequest(
        request_id=uuid4(), idempotency_key="legacy-first-command-0001",
        project_id="legacy-book", schema_version="story-runtime/v1", expected_revision=7,
        actor="human-editor", reason="first governed write",
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact",
            aggregate_id="legacy-rule", payload={"predicate": "world.rule", "value": "kept"}, evidence=[],
        )],
    ))

    manifests = RevisionManifestRepository(database).list("legacy-book")
    assert result.revision == 8
    assert [manifest.revision for manifest in manifests] == [7, 8]
    assert manifests[0].transition_kind == "bootstrap"
    assert manifests[0].provenance_class == "bootstrap_boundary"
    assert manifests[0].previous_revision is None
    assert manifests[1].previous_manifest_hash == manifests[0].manifest_hash
    assert manifests[1].provenance_id.startswith("operator:")
    assert manifests[1].actor_class == "manual_operator"


def test_nonempty_legacy_revision_zero_uses_boundary_one_without_faking_zero(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "legacy-zero.db"))
    database.migrations.migrate()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) "
            "VALUES ('legacy-zero',0,'drafting',0,'story-runtime/v1','old','old','runtime')"
        )
        conn.execute(
            "INSERT INTO entities(project_id,entity_id,entity_type,canonical_name) "
            "VALUES ('legacy-zero','e-1','character','Existing')"
        )
    result = ChapterCommitService(database).apply_typed_diff(TypedDiffCommandRequest(
        request_id=uuid4(), idempotency_key="legacy-zero-first-command-0001",
        project_id="legacy-zero", schema_version="story-runtime/v1", expected_revision=0,
        actor="human-editor", reason="first governed write",
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact",
            aggregate_id="rule", payload={"predicate": "world.rule", "value": "known"}, evidence=[],
        )],
    ))
    assert result.revision == 2
    assert [manifest.revision for manifest in RevisionManifestRepository(database).list("legacy-zero")] == [1, 2]


def test_doctor_detects_manifest_tamper_and_chain_mismatch_without_repair(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "doctor.db"))
    database.migrations.migrate()
    service = ChapterCommitService(database)
    service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="doctor-project-create-0001",
        project_id="doctor-book", schema_version="story-runtime/v1",
    ))
    service.apply_typed_diff(TypedDiffCommandRequest(
        request_id=uuid4(), idempotency_key="doctor-command-key-0001",
        project_id="doctor-book", schema_version="story-runtime/v1", expected_revision=0,
        actor="human", reason="doctor fixture",
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact", aggregate_id="f",
            payload={"predicate": "world.rule", "value": "one"}, evidence=[],
        )],
    ))
    runtime = RuntimeServices(database, StoryRepository(database))
    assert not any(check.code.startswith("manifest.") and check.status == "fail" for check in runtime.doctor("doctor-book", deep=True).checks)

    with database.connect() as conn:
        conn.execute("DROP TRIGGER project_revisions_immutable_update")
        conn.execute(
            "UPDATE project_revisions SET previous_manifest_hash=? WHERE project_id='doctor-book' AND revision=1",
            ("sha256:" + "0" * 64,),
        )
    doctor = runtime.doctor("doctor-book", deep=True)
    assert doctor.status == "blocked"
    assert any(check.code == "manifest.previous_hash.1" and check.status == "fail" for check in doctor.checks)
    assert len(RevisionManifestRepository(database).list("doctor-book")) == 2


def test_manifest_insert_then_failed_cas_and_successful_cas_then_rollback_publish_nothing(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "rollback.db"))
    database.migrations.migrate()
    service = ChapterCommitService(database)
    service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="rollback-project-create-0001",
        project_id="rollback-book", schema_version="story-runtime/v1",
    ))
    allocator = ProjectRevisionAllocator()

    def transition(key: str) -> RevisionTransition:
        return RevisionTransition(
            project_id="rollback-book", expected_revision=0, transition_kind="domain_command",
            command_id=f"command:{key}", commit_id=None, idempotency_key=key,
            request_hash="1" * 64, artifact_references=(), provenance_class="native",
            provenance_id=f"test:{key}", actor_class="test", created_at="2026-07-15T12:00:00Z",
            pre_transition_state_hash="2" * 64,
        )

    with database.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        def sabotage_cas(_: int) -> AuthorityWriteResult:
            conn.execute("UPDATE projects SET revision=99 WHERE project_id='rollback-book'")
            return AuthorityWriteResult((), "3" * 64)

        with pytest.raises(Exception, match="manifest CAS"):
            allocator.execute(conn, transition("allocator-cas-fail-0001"), sabotage_cas)
        conn.rollback()

    assert [item.revision for item in RevisionManifestRepository(database).list("rollback-book")] == [0]
    with database.read() as conn:
        assert conn.execute("SELECT revision FROM projects WHERE project_id='rollback-book'").fetchone()[0] == 0

    with database.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        allocator.execute(
            conn, transition("allocator-outer-rollback-0001"),
            lambda _: AuthorityWriteResult((), "4" * 64),
        )
        conn.rollback()
    assert [item.revision for item in RevisionManifestRepository(database).list("rollback-book")] == [0]


def test_manifest_identity_constraints_reject_duplicate_revision_id_and_command(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "identity.db"))
    database.migrations.migrate()
    service = ChapterCommitService(database)
    service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="identity-project-create-0001",
        project_id="identity-book", schema_version="story-runtime/v1",
    ))
    with database.connect() as conn:
        original = dict(conn.execute(
            "SELECT * FROM project_revisions WHERE project_id='identity-book' AND revision=0"
        ).fetchone())
        columns = ",".join(original)
        placeholders = ",".join("?" for _ in original)

        for overrides in (
            {"manifest_id": "duplicate-revision", "command_id": "different-command-1",
             "idempotency_key": "different-key-1", "manifest_hash": "sha256:" + "a" * 64},
            {"revision": 1, "previous_revision": 0, "previous_manifest_hash": original["manifest_hash"],
             "command_id": "different-command-2", "idempotency_key": "different-key-2",
             "manifest_hash": "sha256:" + "b" * 64},
            {"revision": 1, "manifest_id": "different-manifest", "previous_revision": 0,
             "previous_manifest_hash": original["manifest_hash"], "idempotency_key": "different-key-3",
             "manifest_hash": "sha256:" + "c" * 64},
        ):
            candidate = {**original, **overrides}
            with pytest.raises(Exception):
                conn.execute(
                    f"INSERT INTO project_revisions({columns}) VALUES ({placeholders})",
                    tuple(candidate.values()),
                )


def test_doctor_detects_pointer_without_manifest_and_manifest_without_transition(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "orphan.db"))
    database.migrations.migrate()
    service = ChapterCommitService(database)
    service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="orphan-project-create-0001",
        project_id="orphan-book", schema_version="story-runtime/v1",
    ))
    runtime = RuntimeServices(database, StoryRepository(database))

    with database.connect() as conn:
        conn.execute("UPDATE projects SET revision=1 WHERE project_id='orphan-book'")
    pointer_doctor = runtime.doctor("orphan-book", deep=True)
    assert any(check.code == "manifest.latest_mismatch" and check.status == "fail" for check in pointer_doctor.checks)

    with database.connect() as conn:
        conn.execute("UPDATE projects SET revision=0 WHERE project_id='orphan-book'")
        conn.execute(
            "DELETE FROM idempotency_ledger WHERE project_id='orphan-book' AND idempotency_key='orphan-project-create-0001'"
        )
    transition_doctor = runtime.doctor("orphan-book", deep=True)
    assert any(check.code == "manifest.transition_missing.0" and check.status == "fail" for check in transition_doctor.checks)
