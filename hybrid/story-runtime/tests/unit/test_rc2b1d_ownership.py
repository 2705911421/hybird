from __future__ import annotations

import hashlib
import json
from uuid import uuid4

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
from story_runtime.revision_manifests import RevisionManifest, RevisionManifestRepository
from story_runtime.services import RuntimeServices


FORBIDDEN_MANIFEST_FIELDS = {
    "body", "body_text", "content", "full_state", "event_payload", "payload_json",
    "review_text", "entities", "facts", "timeline", "threads",
}


def _finalized_chapter(tmp_path, project_id: str = "ownership-book"):
    database = Database(RuntimeConfig(database_path=tmp_path / f"{project_id}.db"))
    database.migrations.migrate()
    service = ChapterCommitService(database)
    service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key=f"create-{project_id}-0001",
        project_id=project_id, schema_version="story-runtime/v1",
    ))
    body = "唯一正文标记：雾港钟声落在第七码头。" * 32
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
            aggregate_id="harbor-key", payload={"predicate": "harbor.key", "value": payload_marker},
            evidence=[{"artifact_id": "chapter-body", "start": 0, "end": 4}],
        )],
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
