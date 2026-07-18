from __future__ import annotations

import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest

from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.config import RuntimeConfig
from story_runtime.contracts import (
    ChapterArtifacts,
    CommitChapterRequest,
    CreateProjectRequest,
    PrepareChapterRequest,
    StoryEventInput,
    ValidateChapterArtifactsRequest,
)
from story_runtime.database import Database
from story_runtime.repository import StoryRepository
from story_runtime.revision_manifests import (
    RevisionManifest,
    RevisionManifestRepository,
    canonical_manifest_hash,
)
from story_runtime.services import RuntimeServices


FORBIDDEN_MANIFEST_FIELDS = {
    "body", "body_text", "content", "full_state", "event_payload", "payload_json",
    "review_text", "entities", "facts", "timeline", "threads",
}


def _finalized_chapter(
    tmp_path, project_id: str = "ownership-book", *, body_repeat: int = 32, event_count: int = 1
):
    database = Database(RuntimeConfig(database_path=tmp_path / f"{project_id}.db"))
    database.migrations.migrate()
    service = ChapterCommitService(database)
    service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key=f"create-{project_id}-0001",
        project_id=project_id, schema_version="story-runtime/v1",
    ))
    body = (
        "唯一正文标记：雾港钟声落在第七码头。"
        " body payload_json entities facts timeline threads \x00\x01"
    ) * body_repeat
    payload_marker = "唯一事件载荷标记：灯塔密钥已经转交"
    artifacts = ChapterArtifacts(
        chapter_number=1,
        title="雾港",
        body=body,
        body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        summary="角色抵达码头。",
        outline_fulfillment={"planned_node_ids": [], "covered_node_ids": [], "missed_node_ids": []},
        review={"passed": True, "issues": []},
        state_mutation_proposal={"source": "rc2b1d-ownership"},
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact",
            aggregate_id=f"harbor-key-{index}",
            payload={"predicate": f"harbor.key.{index}", "value": f"{payload_marker}-{index}"},
            evidence=[{"artifact_id": "chapter-body", "start": 0, "end": 4}],
        ) for index in range(event_count)],
    )
    key = f"chapter-{project_id}-0001"
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id=project_id,
        schema_version="story-runtime/v1", expected_revision=0,
        chapter_number=1, intent={}, base_context_revision=0,
    ))
    validated = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key=key, project_id=project_id,
        schema_version="story-runtime/v1", expected_revision=0,
        prepare_id=prepared.prepare_id, artifacts=artifacts,
    ))
    committed = service.commit(CommitChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id=project_id,
        schema_version="story-runtime/v1", expected_revision=0,
        prepare_id=prepared.prepare_id, validation_token=validated.validation_token,
        artifacts=artifacts,
    ))
    runtime = RuntimeServices(database, StoryRepository(database))
    return database, runtime, committed, body, payload_marker


def test_manifest_schema_and_model_reject_full_authority_payload_fields(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "schema.db"))
    database.migrations.migrate()
    with database.read() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(project_revisions)")}

    assert FORBIDDEN_MANIFEST_FIELDS.isdisjoint(columns)
    assert FORBIDDEN_MANIFEST_FIELDS.isdisjoint(RevisionManifest.__dataclass_fields__)


def test_manifest_event_and_artifact_have_single_nonoverlapping_authority(tmp_path) -> None:
    database, _, committed, body, payload_marker = _finalized_chapter(tmp_path)
    manifest = RevisionManifestRepository(database).get("ownership-book", 1)
    serialized = json.dumps(manifest.canonical_payload(), ensure_ascii=False, sort_keys=True)

    assert body not in serialized
    assert payload_marker not in serialized
    assert FORBIDDEN_MANIFEST_FIELDS.isdisjoint(manifest.canonical_payload())
    assert manifest.artifact_references == (f"chapter:{committed.commit_id}",)
    assert manifest.event_count == 1
    with database.read() as conn:
        artifact = conn.execute(
            "SELECT body_text,events_json FROM chapter_artifacts WHERE commit_id=?",
            (str(committed.commit_id),),
        ).fetchone()
        event = conn.execute(
            "SELECT payload_json FROM story_events WHERE project_id='ownership-book' AND applied_revision=1"
        ).fetchone()
    assert artifact["body_text"] == body
    assert body not in event["payload_json"]
    assert payload_marker in event["payload_json"]
    assert payload_marker in artifact["events_json"]


def test_doctor_detects_missing_artifact_that_manifest_cannot_replace(tmp_path) -> None:
    database, runtime, committed, body, _ = _finalized_chapter(tmp_path, "missing-artifact")
    with database.connect() as conn:
        conn.execute("DELETE FROM chapter_artifacts WHERE commit_id=?", (str(committed.commit_id),))

    result = runtime.doctor("missing-artifact", deep=True)

    assert any(check.code == "manifest.artifact_hash.1" for check in result.checks)
    assert body not in json.dumps(
        RevisionManifestRepository(database).get("missing-artifact", 1).canonical_payload(),
        ensure_ascii=False,
    )


def test_doctor_detects_event_membership_reference_loss(tmp_path) -> None:
    database, runtime, _, _, _ = _finalized_chapter(tmp_path, "missing-event")
    with database.connect() as conn:
        conn.execute("DELETE FROM story_events WHERE project_id='missing-event' AND applied_revision=1")

    result = runtime.doctor("missing-event", deep=True)

    assert any(check.code == "manifest.event_missing.1" for check in result.checks)


def test_doctor_rejects_unknown_referenced_artifact_schema(tmp_path) -> None:
    database, runtime, committed, _, _ = _finalized_chapter(tmp_path, "unknown-artifact")
    with database.connect() as conn:
        conn.execute(
            "UPDATE chapter_artifacts SET schema_version='chapter-artifact/v999' WHERE commit_id=?",
            (str(committed.commit_id),),
        )

    result = runtime.doctor("unknown-artifact", deep=True)
    issue = next(check for check in result.checks if check.code == "UNKNOWN_ARTIFACT_SCHEMA_VERSION")

    assert issue.revision == 1
    assert issue.field == "chapter_artifacts.schema_version"
    assert issue.observed_value == "chapter-artifact/v999"
    assert issue.replay_safe is False


def test_doctor_detects_commit_revision_provenance_mismatch(tmp_path) -> None:
    database, runtime, committed, _, _ = _finalized_chapter(tmp_path, "commit-mismatch")
    with database.connect() as conn:
        conn.execute(
            "UPDATE chapter_commits SET resulting_revision=99 WHERE commit_id=?",
            (str(committed.commit_id),),
        )

    result = runtime.doctor("commit-mismatch", deep=True)

    assert any(check.code == "COMMAND_COMMIT_MISMATCH" for check in result.checks)


def test_doctor_detects_events_rebound_to_another_command(tmp_path) -> None:
    database, runtime, _, _, _ = _finalized_chapter(tmp_path, "event-command-mismatch")
    with database.connect() as conn:
        conn.execute(
            "UPDATE story_events SET commit_id='another-command' "
            "WHERE project_id='event-command-mismatch' AND applied_revision=1"
        )

    result = runtime.doctor("event-command-mismatch", deep=True)

    assert any(check.code == "COMMAND_EVENT_RANGE_MISMATCH" for check in result.checks)


def test_doctor_detects_artifact_content_tamper_without_trusting_stored_checksum(tmp_path) -> None:
    database, runtime, committed, _, _ = _finalized_chapter(tmp_path, "tampered-artifact")
    with database.connect() as conn:
        conn.execute(
            "UPDATE chapter_artifacts SET body_text=body_text || '篡改' WHERE commit_id=?",
            (str(committed.commit_id),),
        )

    result = runtime.doctor("tampered-artifact", deep=True)

    assert any(
        check.code == "manifest.artifact_content_hash.1"
        and check.chain_health == "CORRUPTED"
        for check in result.checks
    )


def test_schema_ownership_matrix_has_one_authoritative_owner_per_payload(tmp_path) -> None:
    database = Database(RuntimeConfig(database_path=tmp_path / "ownership-matrix.db"))
    database.migrations.migrate()
    with database.read() as conn:
        columns = {
            table: {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for table in (
                "project_revisions", "chapter_artifacts", "review_artifacts", "story_events",
                "chapter_commits", "idempotency_ledger", "entities", "facts", "timeline",
                "narrative_threads",
            )
        }

    assert "body_text" in columns["chapter_artifacts"]
    assert "artifact_json" in columns["review_artifacts"]
    assert "payload_json" in columns["story_events"]
    assert {"artifact_refs_json", "artifact_hashes_json", "ordered_event_ids_json"} <= columns["project_revisions"]
    assert {"commit_id", "resulting_revision", "artifact_sha256"} <= columns["chapter_commits"]
    assert {"idempotency_key", "result_json"} <= columns["idempotency_ledger"]
    assert FORBIDDEN_MANIFEST_FIELDS.isdisjoint(columns["project_revisions"])


def test_large_cjk_multi_event_manifest_is_size_bounded_and_cannot_reconstruct_body(tmp_path) -> None:
    small_db, _, _, small_body, _ = _finalized_chapter(
        tmp_path, "ownership-small", body_repeat=1, event_count=1
    )
    large_db, _, _, large_body, _ = _finalized_chapter(
        tmp_path, "ownership-large", body_repeat=5000, event_count=8
    )
    small = RevisionManifestRepository(small_db).get("ownership-small", 1).canonical_payload()
    large = RevisionManifestRepository(large_db).get("ownership-large", 1).canonical_payload()
    small_json = json.dumps(small, ensure_ascii=False, sort_keys=True)
    large_json = json.dumps(large, ensure_ascii=False, sort_keys=True)

    assert len(large_body) > len(small_body) * 1000
    assert len(large_json) < 12_000
    assert len(large_json) - len(small_json) < 8_000  # event membership, never body growth
    assert large_body not in large_json
    assert "唯一正文标记" not in large_json
    with pytest.raises(KeyError):
        _ = large["body"]
    assert not {"entities", "facts", "timeline", "threads"} & large.keys()


def test_doctor_detects_cross_project_artifact_reference_even_after_manifest_rehash(tmp_path) -> None:
    database, runtime, first, _, _ = _finalized_chapter(tmp_path, "artifact-project-a")
    service = ChapterCommitService(database)
    service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="create-artifact-project-b-0001",
        project_id="artifact-project-b", schema_version="story-runtime/v1",
    ))
    # Reuse the second project's real commit from a separate database only as a
    # foreign identity; it must never satisfy project A's reference.
    other_db, _, other, _, _ = _finalized_chapter(tmp_path, "artifact-project-b-source")
    other_manifest = RevisionManifestRepository(other_db).get("artifact-project-b-source", 1)
    with database.connect() as conn:
        conn.execute("DROP TRIGGER project_revisions_immutable_update")
        conn.execute(
            "UPDATE project_revisions SET artifact_refs_json=?,artifact_hashes_json=? "
            "WHERE project_id='artifact-project-a' AND revision=1",
            (json.dumps([f"chapter:{other.commit_id}"]), json.dumps(list(other_manifest.artifact_hashes))),
        )
        row = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id='artifact-project-a' AND revision=1"
        ).fetchone()
        digest = canonical_manifest_hash(RevisionManifestRepository.from_row(row).canonical_payload())
        conn.execute(
            "UPDATE project_revisions SET manifest_hash=? WHERE project_id='artifact-project-a' AND revision=1",
            (digest,),
        )

    result = runtime.doctor("artifact-project-a", deep=True)

    assert any(check.code == "manifest.artifact_hash.1" for check in result.checks)
    assert str(first.commit_id) != str(other.commit_id)


def test_duplicate_artifact_identity_is_rejected_by_storage_authority(tmp_path) -> None:
    database, _, committed, _, _ = _finalized_chapter(tmp_path, "duplicate-artifact")
    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM chapter_artifacts WHERE commit_id=?", (str(committed.commit_id),)
            ).fetchone()
            columns = list(row.keys())
            conn.execute(
                f"INSERT INTO chapter_artifacts({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )


def test_doctor_detects_reordered_event_membership_after_manifest_rehash(tmp_path) -> None:
    database, runtime, _, _, _ = _finalized_chapter(
        tmp_path, "event-ordering", event_count=3
    )
    with database.connect() as conn:
        conn.execute("DROP TRIGGER project_revisions_immutable_update")
        row = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id='event-ordering' AND revision=1"
        ).fetchone()
        ids = list(reversed(json.loads(row["ordered_event_ids_json"])))
        hashes = list(reversed(json.loads(row["ordered_event_hashes_json"])))
        membership_hash = canonical_manifest_hash({
            "ordered_event_ids": ids, "ordered_event_hashes": hashes,
        })
        conn.execute(
            "UPDATE project_revisions SET ordered_event_ids_json=?,ordered_event_hashes_json=?,"
            "ordered_event_ids_hash=? WHERE project_id='event-ordering' AND revision=1",
            (json.dumps(ids), json.dumps(hashes), membership_hash),
        )
        changed = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id='event-ordering' AND revision=1"
        ).fetchone()
        digest = canonical_manifest_hash(RevisionManifestRepository.from_row(changed).canonical_payload())
        conn.execute(
            "UPDATE project_revisions SET manifest_hash=? WHERE project_id='event-ordering' AND revision=1",
            (digest,),
        )

    result = runtime.doctor("event-ordering", deep=True)

    assert any(check.code == "manifest.event_order.1" for check in result.checks)
