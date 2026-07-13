from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.config import RuntimeConfig
from story_runtime.contracts import (
    CommitChapterRequest, CommitRecoveryRequest, CreateProjectRequest, OutboxRunRequest,
    PrepareChapterRequest, ValidateChapterArtifactsRequest,
)
from story_runtime.database import Database
from story_runtime.errors import ConflictError, DatabaseUnavailableError
from story_runtime.outbox import OutboxWorker
from story_runtime.repository import StoryRepository
from story_runtime.services import RuntimeServices

from tests.unit.test_chapter_commits import artifacts


def setup_runtime(tmp_path):
    config = RuntimeConfig(
        database_path=tmp_path / "failure-matrix.db", writes_enabled=True,
        projection_root=tmp_path / "projections",
    )
    database = Database(config)
    database.migrations.migrate()
    service = ChapterCommitService(database)
    service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="failure-project-create-01",
        project_id="runtime-book", schema_version="story-runtime/v1",
    ))
    return database, service


def prepare_validate(service, key="failure-chapter-key-0001"):
    chapter = artifacts()
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1,
        intent={}, base_context_revision=0,
    ))
    validated = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0,
        prepare_id=prepared.prepare_id, artifacts=chapter,
    ))
    return chapter, prepared, validated


def commit_request(chapter, prepared, validated, key="failure-chapter-key-0001"):
    return CommitChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0,
        prepare_id=prepared.prepare_id, validation_token=validated.validation_token,
        artifacts=chapter,
    )


@pytest.mark.parametrize("point", [
    "commit.after_begin", "commit.events_midpoint", "commit.reducer",
    "commit.before_finalize", "commit.after_outbox",
])
def test_transaction_faults_have_no_unknown_half_commit(tmp_path, point):
    database, service = setup_runtime(tmp_path)
    chapter, prepared, validated = prepare_validate(service)

    def fail(name):
        if name == point:
            raise RuntimeError(f"injected:{point}")

    with pytest.raises(RuntimeError, match="injected"):
        ChapterCommitService(database, fail).commit(commit_request(chapter, prepared, validated))
    with database.connect() as conn:
        row = conn.execute("SELECT state,resulting_revision FROM chapter_commits WHERE commit_id=?", (str(prepared.commit_id),)).fetchone()
        assert tuple(row) == ("VALIDATED", None)
        assert conn.execute("SELECT COUNT(*) FROM story_events WHERE commit_id=?", (str(prepared.commit_id),)).fetchone()[0] == 0
        assert conn.execute("SELECT revision FROM projects WHERE project_id='runtime-book'").fetchone()[0] == 0
    result = service.commit(commit_request(chapter, prepared, validated))
    assert result.state == "FINALIZED"


def test_prepare_validate_exit_and_runtime_restart_are_resumable(tmp_path):
    database, _ = setup_runtime(tmp_path)
    seen = {"prepare.after_commit", "validate.after_commit"}

    def fail(name):
        if name in seen:
            seen.remove(name)
            raise RuntimeError(name)

    service = ChapterCommitService(database, fail)
    request = PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="failure-chapter-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1, intent={}, base_context_revision=0,
    )
    with pytest.raises(RuntimeError, match="prepare.after_commit"):
        service.prepare(request)
    prepared = ChapterCommitService(database).prepare(request.model_copy(update={"request_id": uuid4()}))
    validate = ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key=request.idempotency_key, project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id, artifacts=artifacts(),
    )
    with pytest.raises(RuntimeError, match="validate.after_commit"):
        service.validate(validate)
    restarted = ChapterCommitService(Database(database.config))
    validated = restarted.validate(validate.model_copy(update={"request_id": uuid4()}))
    assert validated.replayed is True
    assert restarted.commit(commit_request(artifacts(), prepared, validated)).state == "FINALIZED"


def test_body_artifact_stage_failure_rolls_back_and_retries(tmp_path):
    database, service = setup_runtime(tmp_path)
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="artifact-stage-key-00001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1,
        intent={}, base_context_revision=0,
    ))
    request = ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key="artifact-stage-key-00001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0,
        prepare_id=prepared.prepare_id, artifacts=artifacts(),
    )

    def fail(name):
        if name == "validate.after_artifact":
            raise RuntimeError("body staged then process exited")

    with pytest.raises(RuntimeError, match="body staged"):
        ChapterCommitService(database, fail).validate(request)
    with database.connect() as conn:
        assert conn.execute("SELECT state FROM chapter_commits WHERE commit_id=?", (str(prepared.commit_id),)).fetchone()[0] == "PREPARED"
        assert conn.execute("SELECT COUNT(*) FROM chapter_artifacts WHERE commit_id=?", (str(prepared.commit_id),)).fetchone()[0] == 0
    assert service.validate(request.model_copy(update={"request_id": uuid4()})).state == "VALIDATED"


def test_response_loss_inkos_exit_and_pending_outbox_are_safe(tmp_path):
    database, service = setup_runtime(tmp_path)
    chapter, prepared, validated = prepare_validate(service)

    def lose_response(name):
        if name == "commit.after_commit":
            raise ConnectionError("response lost")

    with pytest.raises(ConnectionError, match="response lost"):
        ChapterCommitService(database, lose_response).commit(commit_request(chapter, prepared, validated))
    replayed = service.commit(commit_request(chapter, prepared, validated))
    assert replayed.replayed is True
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM story_events").fetchone()[0] == 3


def test_outbox_failure_windows_lock_and_retry(tmp_path):
    database, service = setup_runtime(tmp_path)
    chapter, prepared, validated = prepare_validate(service)
    service.commit(commit_request(chapter, prepared, validated))

    def occupied(name):
        if name == "outbox.before_replace":
            raise PermissionError("Windows file is occupied")

    first = OutboxWorker(database, occupied).run(OutboxRunRequest(
        request_id=uuid4(), project_id="runtime-book", limit=3,
        admin_scope="story-runtime.outbox.run",
    ))
    assert first.failed >= 1
    repaired = OutboxWorker(database).run(OutboxRunRequest(
        request_id=uuid4(), project_id="runtime-book", limit=10,
        admin_scope="story-runtime.outbox.run",
    ))
    with database.connect() as conn:
        remaining = [tuple(row) for row in conn.execute("SELECT topic,status,last_error FROM outbox WHERE status!='done'")]
    assert repaired.pending == 0, remaining
    assert (tmp_path / "projections/runtime-book/chapters/0001.md").read_text(encoding="utf-8").startswith("<!-- non-authoritative")


def test_operator_abort_and_recover(tmp_path):
    database, service = setup_runtime(tmp_path)
    chapter, prepared, validated = prepare_validate(service)
    with database.connect() as conn:
        conn.execute("UPDATE chapter_commits SET state='PROJECTING' WHERE commit_id=?", (str(prepared.commit_id),))
    recovered = service.recover(CommitRecoveryRequest(
        request_id=uuid4(), project_id="runtime-book", commit_id=prepared.commit_id,
        idempotency_key="failure-chapter-key-0001", action="recover", reason="injected crash",
        admin_scope="story-runtime.commits.recover",
    ))
    assert recovered.state == "FINALIZED"
    assert service.recover(CommitRecoveryRequest(
        request_id=uuid4(), project_id="runtime-book", commit_id=prepared.commit_id,
        idempotency_key="failure-chapter-key-0001", action="recover", reason="retry",
        admin_scope="story-runtime.commits.recover",
    )).replayed is True

    database2, service2 = setup_runtime(tmp_path / "abort")
    prepared2 = service2.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="abort-chapter-key-00001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1, intent={}, base_context_revision=0,
    ))
    aborted = service2.recover(CommitRecoveryRequest(
        request_id=uuid4(), project_id="runtime-book", commit_id=prepared2.commit_id,
        idempotency_key="abort-chapter-key-00001", action="abort", reason="operator cancelled",
        admin_scope="story-runtime.commits.recover",
    ))
    assert aborted.state == "ABORTED"


def test_concurrency_same_and_different_chapters_and_sqlite_lock(tmp_path):
    database, service = setup_runtime(tmp_path)
    chapter, prepared, validated = prepare_validate(service)
    request = commit_request(chapter, prepared, validated)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.commit(request), range(2)))
    assert {result.resulting_revision for result in results} == {1}
    assert sum(result.replayed for result in results) == 1

    blocker = database.connect()
    conn = blocker.__enter__()
    try:
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(DatabaseUnavailableError):
            service.prepare(PrepareChapterRequest(
                request_id=uuid4(), idempotency_key="locked-chapter-key-0001", project_id="runtime-book",
                schema_version="story-runtime/v1", expected_revision=1, chapter_number=2, intent={}, base_context_revision=1,
            ))
    finally:
        conn.rollback()
        blocker.__exit__(None, None, None)

    doctor = RuntimeServices(database, StoryRepository(database)).doctor("runtime-book", deep=True)
    assert doctor.status in {"ok", "warning"}
