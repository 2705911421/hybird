from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from story_runtime.api import create_app
from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.contracts import StoryEventInput, TypedDiffCommandRequest
from story_runtime.errors import ConflictError
from story_runtime.repository import StoryRepository
from story_runtime.revision_manifests import RevisionManifestRepository
from story_runtime.services import RuntimeServices


def _request(key: str) -> TypedDiffCommandRequest:
    return TypedDiffCommandRequest(
        request_id=uuid4(), idempotency_key=key,
        project_id="legacy-first-write", schema_version="story-runtime/v1",
        expected_revision=7, actor="legacy-cutover", reason="first native authority write",
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact",
            aggregate_id=f"native-{key}",
            payload={"predicate": f"world.native.{key}", "value": True}, evidence=[],
        )],
    )


def _assert_legacy_rows_unchanged(database, snapshot) -> None:
    with database.read() as conn:
        assert [dict(row) for row in conn.execute(
            "SELECT * FROM story_events WHERE project_id='legacy-first-write' AND applied_revision IS NULL ORDER BY event_id"
        )] == snapshot["events"]
        assert dict(conn.execute(
            "SELECT * FROM entities WHERE project_id='legacy-first-write' AND entity_id='legacy-character'"
        ).fetchone()) == snapshot["entity"]
        assert dict(conn.execute(
            "SELECT * FROM facts WHERE project_id='legacy-first-write' AND fact_id='legacy-fact'"
        ).fetchone()) == snapshot["fact"]
        assert dict(conn.execute(
            "SELECT * FROM chapter_commits WHERE commit_id='legacy-partial-commit'"
        ).fetchone()) == snapshot["partial_commit"]


def test_migration7_first_write_creates_only_boundary7_and_native8_and_retries(legacy_v7_database) -> None:
    config, database, snapshot = legacy_v7_database
    assert database.migrations.migrate() == 8
    assert RevisionManifestRepository(database).list("legacy-first-write") == []

    service = ChapterCommitService(database)
    request = _request("legacy-first-native-0001")
    first = service.apply_typed_diff(request)
    replay = service.apply_typed_diff(request.model_copy(update={"request_id": uuid4()}))
    manifests = RevisionManifestRepository(database).list("legacy-first-write")

    assert first.revision == replay.revision == 8
    assert replay.replayed is True
    assert [item.revision for item in manifests] == [7, 8]
    assert manifests[0].transition_kind == "bootstrap"
    assert manifests[0].provenance_class == "bootstrap_boundary"
    assert manifests[0].event_count == 0
    assert manifests[0].previous_revision is None
    assert manifests[1].previous_manifest_hash == manifests[0].manifest_hash
    assert not any(item.revision < 7 for item in manifests)
    _assert_legacy_rows_unchanged(database, snapshot)

    with TestClient(create_app(config)) as client:
        response = client.get(
            "/api/story-runtime/v1/projects/legacy-first-write/entities/legacy-character?at_revision=6",
            headers={"Authorization": "Bearer test-token"},
        )
    assert response.status_code == 409
    assert response.json()["code"] == "HISTORY_NOT_IMPLEMENTED"


def test_interrupted_first_write_rolls_back_boundary_and_retry_stays_at_revision8(legacy_v7_database) -> None:
    _, database, snapshot = legacy_v7_database
    database.migrations.migrate()
    with database.connect() as conn:
        conn.executescript(
            "CREATE TRIGGER fail_first_native_ledger BEFORE INSERT ON idempotency_ledger "
            "WHEN NEW.operation='events.append' BEGIN SELECT RAISE(ABORT,'injected ledger failure'); END;"
        )
    request = _request("legacy-interrupted-0001")

    try:
        ChapterCommitService(database).apply_typed_diff(request)
        raise AssertionError("fault injection did not abort the first write")
    except sqlite3.IntegrityError as exc:
        assert "injected ledger failure" in str(exc)

    with database.read() as conn:
        assert conn.execute(
            "SELECT revision FROM projects WHERE project_id='legacy-first-write'"
        ).fetchone()[0] == 7
        assert conn.execute(
            "SELECT COUNT(*) FROM project_revisions WHERE project_id='legacy-first-write'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM story_events WHERE project_id='legacy-first-write' AND applied_revision IS NOT NULL"
        ).fetchone()[0] == 0
    _assert_legacy_rows_unchanged(database, snapshot)

    with database.connect() as conn:
        conn.execute("DROP TRIGGER fail_first_native_ledger")
    result = ChapterCommitService(database).apply_typed_diff(request.model_copy(update={"request_id": uuid4()}))

    assert result.revision == 8
    assert [item.revision for item in RevisionManifestRepository(database).list("legacy-first-write")] == [7, 8]


def test_concurrent_first_writes_create_one_boundary_and_one_revision8(legacy_v7_database) -> None:
    _, database, _ = legacy_v7_database
    database.migrations.migrate()

    def execute(key: str):
        try:
            return ("ok", ChapterCommitService(database).apply_typed_diff(_request(key)).revision)
        except ConflictError as exc:
            return (exc.code, exc.current_revision)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, ["legacy-concurrent-a-0001", "legacy-concurrent-b-0001"]))

    assert sorted(status for status, _ in results) == ["REVISION_CONFLICT", "ok"]
    assert [item.revision for item in RevisionManifestRepository(database).list("legacy-first-write")] == [7, 8]
    with database.read() as conn:
        assert conn.execute(
            "SELECT revision FROM projects WHERE project_id='legacy-first-write'"
        ).fetchone()[0] == 8


def test_doctor_reports_unknown_old_event_compatibility_without_rewriting_it(legacy_v7_database) -> None:
    _, database, snapshot = legacy_v7_database
    database.migrations.migrate()
    ChapterCommitService(database).apply_typed_diff(_request("legacy-doctor-native-0001"))

    result = RuntimeServices(database, StoryRepository(database)).doctor("legacy-first-write", deep=True)
    issue = next(check for check in result.checks if check.code == "UNKNOWN_EVENT_SCHEMA_VERSION")

    assert issue.field == "story_events.schema_version"
    assert issue.observed_value == "legacy-events/v999"
    assert issue.replay_safe is False
    _assert_legacy_rows_unchanged(database, snapshot)
