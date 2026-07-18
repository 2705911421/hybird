from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3
from uuid import uuid4

import pytest

from fastapi.testclient import TestClient

from story_runtime.api import create_app
from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.contracts import (
    ChapterArtifacts,
    CommitChapterRequest,
    PrepareChapterRequest,
    StoryEventInput,
    TypedDiffCommandRequest,
    ValidateChapterArtifactsRequest,
)
from story_runtime.errors import ConflictError, DatabaseUnavailableError
from story_runtime.repository import StoryRepository
from story_runtime.revision_manifests import ProjectRevisionAllocator, RevisionManifestRepository
from story_runtime.services import RuntimeServices


def _request(
    key: str, *, expected_revision: int = 7, value: object = True
) -> TypedDiffCommandRequest:
    return TypedDiffCommandRequest(
        request_id=uuid4(), idempotency_key=key,
        project_id="legacy-first-write", schema_version="story-runtime/v1",
        expected_revision=expected_revision, actor="legacy-cutover", reason="first native authority write",
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact",
            aggregate_id=f"native-{key}",
            payload={"predicate": f"world.native.{key}", "value": value}, evidence=[],
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


@pytest.mark.parametrize(
    "family",
    [
        "L1_plain_current_state", "L2_null_event_metadata", "L3_partial_commits",
        "L4_imported_project", "L5_migration7_database", "L6_migration8_no_write",
        "L7_existing_boundary", "L12_malformed_optional_metadata",
        "L13_unknown_compatibility", "L14_legacy_revision_zero", "L15_large_revision",
    ],
)
def test_legacy_fixture_families_preserve_history_boundary_semantics(
    legacy_v7_database, family: str
) -> None:
    _, database, snapshot = legacy_v7_database
    expected_revision = 7
    if family == "L14_legacy_revision_zero":
        with database.connect() as conn:
            conn.execute("UPDATE projects SET revision=0 WHERE project_id='legacy-first-write'")
        expected_revision = 0
    elif family == "L15_large_revision":
        with database.connect() as conn:
            conn.execute("UPDATE projects SET revision=9999 WHERE project_id='legacy-first-write'")
        expected_revision = 9999
    elif family == "L4_imported_project":
        with database.connect() as conn:
            conn.execute(
                "INSERT INTO migration_jobs(job_id,source_type,source_path,source_path_fingerprint,"
                "source_checksum_manifest_json,target_project_id,mapping_version,cir_version,current_stage,"
                "progress,created_at,updated_at) VALUES "
                "('legacy-import-proof','inkos','legacy/book','fingerprint','[]','legacy-first-write',"
                "'mapping/v1','cir/v1','COMPLETED',100,'old','old')"
            )

    assert database.migrations.migrate() == 8
    assert RevisionManifestRepository(database).list("legacy-first-write") == []
    if family == "L2_null_event_metadata":
        with database.read() as conn:
            row = conn.execute(
                "SELECT schema_version,applied_revision FROM story_events "
                "WHERE event_id='legacy-null-schema'"
            ).fetchone()
            assert row["schema_version"] is None and row["applied_revision"] is None
    if family == "L3_partial_commits":
        with database.read() as conn:
            assert conn.execute(
                "SELECT state FROM chapter_commits WHERE commit_id='legacy-partial-commit'"
            ).fetchone()[0] == "PREPARED"
    if family == "L7_existing_boundary":
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            state_hash = ChapterCommitService(database).projection_hash(conn, "legacy-first-write")
            boundary = ProjectRevisionAllocator().establish_bootstrap(
                conn, project_id="legacy-first-write", expected_revision=7,
                state_hash=state_hash, provenance_id="verified-legacy-cutover",
                created_at="2026-07-18T00:00:00+00:00",
            )
            conn.commit()
        assert boundary.revision == 7

    result = ChapterCommitService(database).apply_typed_diff(
        _request(f"legacy-family-{family}-0001", expected_revision=expected_revision)
    )
    manifests = RevisionManifestRepository(database).list("legacy-first-write")
    if expected_revision == 0:
        assert [item.revision for item in manifests] == [1, 2]
        assert result.revision == 2
    else:
        assert [item.revision for item in manifests] == [expected_revision, expected_revision + 1]
        assert result.revision == expected_revision + 1
    assert manifests[0].provenance_class == "bootstrap_boundary"
    assert manifests[0].previous_revision is None
    assert manifests[0].previous_manifest_hash is None
    assert manifests[1].previous_manifest_hash == manifests[0].manifest_hash
    assert not any(item.revision < manifests[0].revision for item in manifests)
    _assert_legacy_rows_unchanged(database, snapshot)
    doctor = RuntimeServices(database, StoryRepository(database)).doctor("legacy-first-write", deep=True)
    assert not any(check.chain_health == "MISSING_REVISION" for check in doctor.checks)


@pytest.mark.parametrize(
    ("name", "trigger_sql"),
    [
        (
            "boundary_before_insert",
            "CREATE TRIGGER fail_point BEFORE INSERT ON project_revisions "
            "WHEN NEW.provenance_class='bootstrap_boundary' BEGIN SELECT RAISE(ABORT,'boundary before'); END",
        ),
        (
            "boundary_after_insert",
            "CREATE TRIGGER fail_point AFTER INSERT ON project_revisions "
            "WHEN NEW.provenance_class='bootstrap_boundary' BEGIN SELECT RAISE(ABORT,'boundary after'); END",
        ),
        (
            "native_event_after_insert",
            "CREATE TRIGGER fail_point AFTER INSERT ON story_events "
            "WHEN NEW.applied_revision=8 BEGIN SELECT RAISE(ABORT,'event after'); END",
        ),
        (
            "native_manifest_after_insert",
            "CREATE TRIGGER fail_point AFTER INSERT ON project_revisions "
            "WHEN NEW.revision=8 BEGIN SELECT RAISE(ABORT,'manifest after'); END",
        ),
        (
            "project_cas_before_update",
            "CREATE TRIGGER fail_point BEFORE UPDATE OF revision ON projects "
            "WHEN NEW.revision=8 BEGIN SELECT RAISE(ABORT,'cas before'); END",
        ),
        (
            "ledger_before_insert",
            "CREATE TRIGGER fail_point BEFORE INSERT ON idempotency_ledger "
            "WHEN NEW.operation='events.append' BEGIN SELECT RAISE(ABORT,'ledger before'); END",
        ),
    ],
)
def test_first_native_write_failure_points_roll_back_and_survive_reopen(
    legacy_v7_database, name: str, trigger_sql: str
) -> None:
    config, database, snapshot = legacy_v7_database
    database.migrations.migrate()
    with database.connect() as conn:
        conn.execute(trigger_sql)

    with pytest.raises(sqlite3.DatabaseError):
        ChapterCommitService(database).apply_typed_diff(_request(f"failure-{name}-0001"))

    reopened = type(database)(config)
    with reopened.read() as conn:
        assert conn.execute(
            "SELECT revision FROM projects WHERE project_id='legacy-first-write'"
        ).fetchone()[0] == 7
        assert conn.execute(
            "SELECT COUNT(*) FROM project_revisions WHERE project_id='legacy-first-write'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM story_events WHERE project_id='legacy-first-write' "
            "AND applied_revision IS NOT NULL"
        ).fetchone()[0] == 0
    _assert_legacy_rows_unchanged(reopened, snapshot)

    with reopened.connect() as conn:
        conn.execute("DROP TRIGGER fail_point")
    retried = ChapterCommitService(reopened).apply_typed_diff(_request(f"failure-{name}-0001"))
    assert retried.revision == 8
    assert [item.revision for item in RevisionManifestRepository(reopened).list("legacy-first-write")] == [7, 8]


def test_response_loss_retry_and_idempotency_conflict_do_not_create_revision9(legacy_v7_database) -> None:
    _, database, _ = legacy_v7_database
    database.migrations.migrate()
    request = _request("legacy-response-loss-0001")
    first = ChapterCommitService(database).apply_typed_diff(request)
    replay = ChapterCommitService(database).apply_typed_diff(
        request.model_copy(update={"request_id": uuid4()})
    )
    assert first.revision == replay.revision == 8
    assert replay.replayed is True

    with pytest.raises(ConflictError) as conflict:
        ChapterCommitService(database).apply_typed_diff(
            _request("legacy-response-loss-0001", value="different")
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    assert [item.revision for item in RevisionManifestRepository(database).list("legacy-first-write")] == [7, 8]


def test_same_key_concurrency_is_one_revision_and_idempotent(legacy_v7_database) -> None:
    _, database, _ = legacy_v7_database
    database.migrations.migrate()
    request = _request("legacy-same-key-concurrent-0001")

    def execute():
        try:
            result = ChapterCommitService(database).apply_typed_diff(
                request.model_copy(update={"request_id": uuid4()})
            )
            return ("ok", result.revision, result.replayed)
        except ConflictError as exc:
            return (exc.code, exc.current_revision, False)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(), range(2)))

    assert all(result[0] == "ok" and result[1] == 8 for result in results)
    assert sorted(result[2] for result in results) == [False, True]
    assert [item.revision for item in RevisionManifestRepository(database).list("legacy-first-write")] == [7, 8]


def test_chapter_finalize_vs_typed_diff_first_write_has_one_winner(legacy_v7_database) -> None:
    _, database, _ = legacy_v7_database
    database.migrations.migrate()
    service = ChapterCommitService(database)
    key = "legacy-chapter-first-write-0001"
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id="legacy-first-write",
        schema_version="story-runtime/v1", expected_revision=7,
        chapter_number=4, intent={}, base_context_revision=7,
    ))
    body = "旧项目首次原生章节写入"
    artifacts = ChapterArtifacts(
        chapter_number=4, title="Native Four", body=body,
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        summary="native", outline_fulfillment={"planned_node_ids": [], "covered_node_ids": [], "missed_node_ids": []},
        review={"passed": True}, state_mutation_proposal={},
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact",
            aggregate_id="chapter-first", payload={"predicate": "world.chapter.first", "value": True},
            evidence=[],
        )],
    )
    validated = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key=key, project_id="legacy-first-write",
        schema_version="story-runtime/v1", expected_revision=7,
        prepare_id=prepared.prepare_id, artifacts=artifacts,
    ))
    chapter_request = CommitChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id="legacy-first-write",
        schema_version="story-runtime/v1", expected_revision=7,
        prepare_id=prepared.prepare_id, validation_token=validated.validation_token,
        artifacts=artifacts,
    )

    def chapter():
        try:
            return ("ok", ChapterCommitService(database).commit(chapter_request).resulting_revision)
        except ConflictError as exc:
            return (exc.code, exc.current_revision)

    def diff():
        try:
            return ("ok", ChapterCommitService(database).apply_typed_diff(
                _request("legacy-racing-diff-0001")
            ).revision)
        except ConflictError as exc:
            return (exc.code, exc.current_revision)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(chapter), pool.submit(diff)]
        results = [future.result() for future in futures]

    assert sum(status == "ok" for status, _ in results) == 1
    assert sorted(revision for status, revision in results if status == "ok") == [8]
    assert [item.revision for item in RevisionManifestRepository(database).list("legacy-first-write")] == [7, 8]


def test_sqlite_lock_is_revision_neutral_and_retry_creates_only_r8(legacy_v7_database) -> None:
    _, database, _ = legacy_v7_database
    database.migrations.migrate()
    with database.connect() as lock:
        lock.execute("BEGIN IMMEDIATE")
        with pytest.raises(DatabaseUnavailableError) as blocked:
            ChapterCommitService(database).apply_typed_diff(_request("legacy-lock-retry-0001"))
        assert blocked.value.code == "DATABASE_LOCKED"
        lock.rollback()

    result = ChapterCommitService(database).apply_typed_diff(_request("legacy-lock-retry-0001"))
    assert result.revision == 8
    assert [item.revision for item in RevisionManifestRepository(database).list("legacy-first-write")] == [7, 8]


def test_doctor_reports_missing_first_native_after_valid_boundary(legacy_v7_database) -> None:
    _, database, _ = legacy_v7_database
    database.migrations.migrate()
    with database.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        state_hash = ChapterCommitService(database).projection_hash(conn, "legacy-first-write")
        ProjectRevisionAllocator().establish_bootstrap(
            conn, project_id="legacy-first-write", expected_revision=7,
            state_hash=state_hash, provenance_id="verified-legacy-cutover",
            created_at="2026-07-18T00:00:00+00:00",
        )
        conn.execute("UPDATE projects SET revision=8 WHERE project_id='legacy-first-write'")
        conn.commit()

    doctor = RuntimeServices(database, StoryRepository(database)).doctor("legacy-first-write", deep=True)
    summary = next(check for check in doctor.checks if check.code == "MANIFEST_CHAIN_IMPACT")

    assert summary.first_missing_revision == 8
    assert summary.latest_trusted_revision == 7
    assert summary.first_untrusted_revision == 8
    assert not any(
        check.revision is not None
        and check.revision < 7
        and check.chain_health == "MISSING_REVISION"
        for check in doctor.checks
    )
