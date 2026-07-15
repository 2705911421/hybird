from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest

from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.config import RuntimeConfig
from story_runtime.contracts import (
    AppendEventsRequest,
    ChapterArtifacts,
    CommitChapterRequest,
    CreateProjectRequest,
    PrepareChapterRequest,
    ReplayProjectionsRequest,
    StoryEventInput,
    TypedDiffCommandRequest,
    ValidateChapterArtifactsRequest,
)
from story_runtime.database import Database
from story_runtime.errors import ConflictError
from story_runtime.errors import DatabaseUnavailableError
from story_runtime.repository import StoryRepository
from story_runtime.services import RuntimeServices
from story_runtime.revision_manifests import RevisionManifestRepository


def runtime_service(tmp_path):
    database = Database(RuntimeConfig(database_path=tmp_path / "phase4.db", writes_enabled=True))
    database.migrations.migrate()
    return database, ChapterCommitService(database)


def create_project(service: ChapterCommitService, project_id: str = "runtime-book"):
    return service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="create-runtime-book-0001",
        project_id=project_id, schema_version="story-runtime/v1",
    ))


def artifacts(chapter: int = 1, body: str = "第一章正文。林舟拾起钥匙。") -> ChapterArtifacts:
    return ChapterArtifacts(
        chapter_number=chapter,
        title=f"第{chapter}章",
        body=body,
        body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        summary="林舟拾起钥匙。",
        outline_fulfillment={"planned_node_ids": [], "covered_node_ids": [], "missed_node_ids": []},
        review={"passed": True, "issues": []},
        state_mutation_proposal={"source": "deterministic-test"},
        events=[StoryEventInput(
            event_type="fact.upsert", subject="char-lin", aggregate_type="fact",
            aggregate_id="char-lin-has-key", payload={"predicate": "inventory.has_key", "value": True},
            evidence=[{"artifact_id": "chapter-body", "start": 0, "end": 4}],
        ), StoryEventInput(
            event_type="entity.upsert", subject="char-lin", aggregate_type="entity",
            aggregate_id="char-lin", payload={"entity_type": "character", "canonical_name": "林舟", "attributes": {"has_key": True}},
            evidence=[{"artifact_id": "chapter-body", "start": 0, "end": 4}],
        ), StoryEventInput(
            event_type="thread.upsert", subject="key-thread", aggregate_type="narrative_thread",
            aggregate_id="key-thread", payload={"title": "钥匙来源", "status": "open", "introduced_chapter": chapter},
            evidence=[{"artifact_id": "chapter-body", "start": 0, "end": 4}],
        )],
    )


def lifecycle(service: ChapterCommitService, chapter_artifacts: ChapterArtifacts, *, revision: int = 0, key: str = "chapter-commit-key-0001"):
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=revision,
        chapter_number=chapter_artifacts.chapter_number, intent={}, base_context_revision=revision,
    ))
    validated = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=revision,
        prepare_id=prepared.prepare_id, artifacts=chapter_artifacts,
    ))
    committed = service.commit(CommitChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=revision,
        prepare_id=prepared.prepare_id, validation_token=validated.validation_token,
        artifacts=chapter_artifacts,
    ))
    return prepared, validated, committed


def test_state_machine_finalizes_atomically_and_retries_response_loss(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    chapter = artifacts()
    prepared, validated, committed = lifecycle(service, chapter)
    assert prepared.state == "PREPARED"
    assert validated.state == "VALIDATED"
    assert committed.state == "FINALIZED"
    assert committed.resulting_revision == 1
    assert committed.event_count == 3
    manifest = RevisionManifestRepository(database).get("runtime-book", 1)
    assert manifest is not None
    assert manifest.transition_kind == "chapter_finalize"
    assert manifest.commit_id == str(committed.commit_id)
    assert manifest.event_count == 3
    assert manifest.artifact_references == (f"chapter:{committed.commit_id}",)
    assert manifest.artifact_hashes == (f"sha256:{committed.artifact_sha256}",)
    assert manifest.hash_valid is True

    replayed = service.commit(CommitChapterRequest(
        request_id=uuid4(), idempotency_key="chapter-commit-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0,
        prepare_id=prepared.prepare_id, validation_token=validated.validation_token,
        artifacts=chapter,
    ))
    assert replayed.replayed is True
    assert replayed.commit_id == committed.commit_id
    with database.connect() as conn:
        assert conn.execute("SELECT revision FROM projects WHERE project_id='runtime-book'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM story_events WHERE project_id='runtime-book'").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM project_revisions WHERE project_id='runtime-book'").fetchone()[0] == 2
        states = [row[0] for row in conn.execute("SELECT to_state FROM commit_transitions WHERE commit_id=? ORDER BY transition_id", (str(committed.commit_id),))]
        assert states == ["PREPARED", "VALIDATED", "PERSISTING", "COMMITTED", "PROJECTING", "FINALIZED"]


def test_zero_event_chapter_gets_one_compatibility_manifest_and_one_revision(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    no_events = artifacts().model_copy(update={"events": []})
    _, _, committed = lifecycle(service, no_events)
    manifest = RevisionManifestRepository(database).get("runtime-book", 1)

    assert committed.resulting_revision == 1
    assert manifest is not None
    assert manifest.event_count == 0
    assert manifest.first_event_sequence is None
    assert manifest.event_schema_version == "legacy-unversioned"


def test_same_key_different_prepare_payload_conflicts(tmp_path):
    _, service = runtime_service(tmp_path)
    create_project(service)
    request = PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="chapter-commit-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1,
        intent={"goal": "one"}, base_context_revision=0,
    )
    first = service.prepare(request)
    assert service.prepare(request.model_copy(update={"request_id": uuid4()})).commit_id == first.commit_id
    with pytest.raises(ConflictError, match="different prepare payload"):
        service.prepare(request.model_copy(update={"request_id": uuid4(), "intent": {"goal": "two"}}))


def test_revision_conflict_and_blocking_validation(tmp_path):
    _, service = runtime_service(tmp_path)
    create_project(service)
    with pytest.raises(ConflictError, match="expected revision"):
        service.prepare(PrepareChapterRequest(
            request_id=uuid4(), idempotency_key="chapter-commit-key-0001", project_id="runtime-book",
            schema_version="story-runtime/v1", expected_revision=1, chapter_number=1,
            intent={}, base_context_revision=1,
        ))
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="chapter-commit-key-0002", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1,
        intent={}, base_context_revision=0,
    ))
    bad = artifacts().model_copy(update={"body_sha256": "0" * 64})
    result = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key="chapter-commit-key-0002", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id,
        artifacts=bad,
    ))
    assert result.state == "REJECTED"
    assert any(issue.code == "BODY_HASH_MISMATCH" for issue in result.issues)


def test_unified_review_requires_typed_review_and_inert_state_proposal(tmp_path):
    database = Database(RuntimeConfig(database_path=tmp_path / "typed.db", writes_enabled=True, unified_review_enabled=True))
    database.migrations.migrate()
    service = ChapterCommitService(database, unified_review_enabled=True)
    legacy = artifacts()
    issues = service._validate_artifacts(legacy, "runtime-book", 0)
    assert {issue.code for issue in issues} >= {"TYPED_REVIEW_REQUIRED", "TYPED_STATE_PROPOSAL_REQUIRED"}

    body = legacy.body
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    typed = legacy.model_copy(update={
        "review": {
            "artifact_id": "review-a", "schema_version": "review-artifacts/v1", "project_id": "runtime-book",
            "chapter_number": 1, "source_revision": 0, "body_sha256": body_hash,
            "reviewer_kind": "runtime_validator", "reviewer_version": "1", "generated_at": datetime.now(timezone.utc),
            "dimensions": {}, "findings": [], "summary": "clear", "recommended_action": "approve",
            "model_metadata": {}, "prompt_template_version": "deterministic/v1",
        },
        "state_mutation_proposal": {
            "proposal_id": "proposal-a", "schema_version": "review-artifacts/v1", "project_id": "runtime-book",
            "chapter_number": 1, "source_revision": 0, "body_sha256": body_hash,
            "entity_mutations": [], "relationship_mutations": [], "fact_mutations": [], "timeline_events": [],
            "narrative_thread_mutations": [], "foreshadowing_mutations": [], "evidence": [],
            "confidence": 1, "extraction_source": "observer",
        },
    })
    assert not [issue for issue in service._validate_artifacts(typed, "runtime-book", 0) if issue.severity == "blocking"]
    dangerous = typed.model_copy(update={"state_mutation_proposal": {
        **typed.state_mutation_proposal,
        "fact_mutations": [{"operation": "update", "target_id": "fact-a", "value": {"validator_policy": "ignore"}}],
    }})
    assert "FORBIDDEN_AGENT_CAPABILITY" in {issue.code for issue in service._validate_artifacts(dangerous, "runtime-book", 0)}

    invalid_evidence = typed.model_copy(update={"state_mutation_proposal": {
        **typed.state_mutation_proposal,
        "evidence": [{
            "artifact": "chapter_body", "start_offset": 0, "end_offset": 1,
            "quoted_hash": "0" * 64, "locator": "chapter:1:0-1",
            "explanation": "invalid hash", "status": "current",
        }],
    }})
    assert "PROPOSAL_EVIDENCE_INVALID" in {issue.code for issue in service._validate_artifacts(invalid_evidence, "runtime-book", 0)}

    stale_evidence = typed.model_copy(update={"state_mutation_proposal": {
        **typed.state_mutation_proposal,
        "evidence": [{
            "artifact": "chapter_body", "start_offset": 0, "end_offset": 1,
            "quoted_hash": hashlib.sha256(body[0:1].encode("utf-8")).hexdigest(),
            "locator": "chapter:1:0-1", "explanation": "old extraction", "status": "stale",
        }],
    }})
    assert "PROPOSAL_EVIDENCE_STALE" in {issue.code for issue in service._validate_artifacts(stale_evidence, "runtime-book", 0)}


def test_sqlite_authority_domain_conflicts_are_deterministic(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    with database.connect() as conn:
        conn.execute("INSERT INTO entities VALUES ('runtime-book','char-a','character','A','[]','{}','[]')")
        conn.executemany("INSERT INTO facts VALUES ('runtime-book',?,?,?,?,0,NULL)", [
            ("status-a", "char-a", "character.status", '"dead"'),
            ("location-a", "char-a", "character.location", '"old-port"'),
            ("rule-a", "world", "world.rule.magic", '"forbidden"'),
            ("resource-a", "char-a", "resource.coins", "1"),
        ])
        conn.execute("INSERT INTO timeline VALUES ('runtime-book','time-a','010','Current',NULL,'{}')")
        conn.commit()
        chapter = artifacts().model_copy(update={"events": [
            StoryEventInput(event_type="relationship.upsert", subject="rel-a", aggregate_type="relationship", aggregate_id="rel-a", payload={"source_entity_id": "char-a", "target_entity_id": "missing"}, evidence=[]),
            StoryEventInput(event_type="fact.upsert", subject="char-a", aggregate_type="fact", aggregate_id="status-a", payload={"predicate": "character.status", "value": "alive"}, evidence=[]),
            StoryEventInput(event_type="fact.upsert", subject="char-a", aggregate_type="fact", aggregate_id="location-a", payload={"predicate": "character.location", "value": "new-port"}, evidence=[]),
            StoryEventInput(event_type="fact.upsert", subject="world", aggregate_type="fact", aggregate_id="rule-a", payload={"predicate": "world.rule.magic", "value": "allowed"}, evidence=[]),
            StoryEventInput(event_type="fact.upsert", subject="char-a", aggregate_type="fact", aggregate_id="resource-a", payload={"predicate": "resource.coins", "value": -1, "quantity": -1}, evidence=[]),
            StoryEventInput(event_type="timeline.upsert", subject="time-b", aggregate_type="timeline", aggregate_id="time-b", payload={"sequence_key": "001", "title": "Past"}, evidence=[]),
            StoryEventInput(event_type="thread.resolve", subject="hook-a", aggregate_type="narrative_thread", aggregate_id="hook-a", payload={"status": "resolved", "major": True}, evidence=[]),
        ]})
        codes = {issue.code for issue in service._validate_authority_conflicts(conn, "runtime-book", chapter)}
    assert codes >= {
        "UNKNOWN_RELATIONSHIP_ENTITY", "UNEXPLAINED_REVIVAL", "LOCATION_TRANSITION_UNEXPLAINED",
        "WORLD_RULE_CONFLICT", "NEGATIVE_RESOURCE", "TIMELINE_REVERSED", "MAJOR_FORESHADOWING_REQUIRES_HUMAN",
    }


def test_projection_replay_hash_is_deterministic(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    _, _, committed = lifecycle(service, artifacts())
    replay = service.replay(ReplayProjectionsRequest(
        request_id=uuid4(), idempotency_key="replay-projection-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=1,
        projection_names=["entities", "facts", "threads", "summaries"],
        from_event_sequence=0, verify_only=True,
    ))
    assert replay.matched is True
    with database.connect() as conn:
        subset_hash = service.projection_hash(conn, "runtime-book", ["entities", "facts", "threads", "summaries"])
    assert replay.resulting_hash == subset_hash
    assert committed.projection_hash


def test_projection_failure_rolls_back_the_entire_commit(tmp_path, monkeypatch):
    database, service = runtime_service(tmp_path)
    create_project(service)
    chapter = artifacts()
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="chapter-commit-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1, intent={}, base_context_revision=0,
    ))
    validated = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key="chapter-commit-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id, artifacts=chapter,
    ))
    monkeypatch.setattr(service, "_apply_event", lambda *_args: (_ for _ in ()).throw(RuntimeError("injected reducer failure")))
    with pytest.raises(RuntimeError, match="injected reducer failure"):
        service.commit(CommitChapterRequest(
            request_id=uuid4(), idempotency_key="chapter-commit-key-0001", project_id="runtime-book",
            schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id,
            validation_token=validated.validation_token, artifacts=chapter,
        ))
    with database.connect() as conn:
        assert conn.execute("SELECT state FROM chapter_commits WHERE commit_id=?", (str(prepared.commit_id),)).fetchone()[0] == "VALIDATED"
        assert conn.execute("SELECT revision FROM projects WHERE project_id='runtime-book'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM story_events WHERE project_id='runtime-book'").fetchone()[0] == 0


def test_large_cjk_chapter_body_round_trips(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    body = "潮声压过码头。" * 20_000
    chapter = artifacts(body=body)
    _, _, committed = lifecycle(service, chapter)
    with database.connect() as conn:
        stored = conn.execute("SELECT body_text FROM chapter_artifacts WHERE commit_id=?", (str(committed.commit_id),)).fetchone()[0]
    assert stored == body
    assert hashlib.sha256(stored.encode("utf-8")).hexdigest() == chapter.body_sha256


def test_concurrent_same_chapter_commit_has_one_winner(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    requests = []
    for index in range(2):
        key = f"concurrent-chapter-key-{index:04d}"
        chapter = artifacts(body=f"并发候选正文 {index}")
        prepared = service.prepare(PrepareChapterRequest(
            request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
            schema_version="story-runtime/v1", expected_revision=0, chapter_number=1, intent={"candidate": index}, base_context_revision=0,
        ))
        validated = service.validate(ValidateChapterArtifactsRequest(
            request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
            schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id, artifacts=chapter,
        ))
        requests.append(CommitChapterRequest(
            request_id=uuid4(), idempotency_key=key, project_id="runtime-book",
            schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id,
            validation_token=validated.validation_token, artifacts=chapter,
        ))

    def attempt(request):
        try:
            return service.commit(request).state
        except ConflictError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, requests))
    assert outcomes.count("FINALIZED") == 1
    assert any(outcome in {"REVISION_CONFLICT", "COMMIT_CONFLICT"} for outcome in outcomes)
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chapter_commits WHERE project_id='runtime-book' AND state='FINALIZED'").fetchone()[0] == 1
        assert conn.execute("SELECT revision FROM projects WHERE project_id='runtime-book'").fetchone()[0] == 1


def test_prepare_and_validate_survive_restart(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    chapter = artifacts()
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="restart-chapter-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1, intent={}, base_context_revision=0,
    ))
    validated = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key="restart-chapter-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id, artifacts=chapter,
    ))
    restarted = ChapterCommitService(Database(RuntimeConfig(database_path=database.path, writes_enabled=True)))
    result = restarted.commit(CommitChapterRequest(
        request_id=uuid4(), idempotency_key="restart-chapter-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id,
        validation_token=validated.validation_token, artifacts=chapter,
    ))
    assert result.state == "FINALIZED"


def test_operator_append_requires_scope_and_is_idempotent(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    request = AppendEventsRequest(
        request_id=uuid4(), idempotency_key="operator-append-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, reason="controlled import",
        admin_scope=None, events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact", aggregate_id="world-rule",
            payload={"predicate": "world.rule", "value": "doors close at dusk", "chapter_number": 0},
            evidence=[{"artifact_id": "operator-import", "start": 0, "end": 1}],
        )],
    )
    with pytest.raises(ConflictError, match="operator scope"):
        service.append_operator_events(request)
    scoped = request.model_copy(update={"admin_scope": "story-runtime.events.append"})
    first = service.append_operator_events(scoped)
    second = service.append_operator_events(scoped.model_copy(update={"request_id": uuid4()}))
    assert first.revision == 1
    assert second.replayed is True
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM story_events WHERE project_id='runtime-book'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM project_revisions WHERE project_id='runtime-book'").fetchone()[0] == 2
    manifest = RevisionManifestRepository(database).get("runtime-book", 1)
    assert manifest is not None
    assert manifest.transition_kind == "domain_command"
    assert manifest.event_count == 1


def test_typed_diff_uses_one_manifest_for_multiple_mutations_and_retries(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    request = TypedDiffCommandRequest(
        request_id=uuid4(), idempotency_key="typed-diff-command-key-0001",
        project_id="runtime-book", schema_version="story-runtime/v1", expected_revision=0,
        actor="human-editor", reason="manual canonical correction",
        events=[
            StoryEventInput(
                event_type="fact.upsert", subject="world", aggregate_type="fact",
                aggregate_id="rule-light", payload={"predicate": "world.light", "value": "dim"}, evidence=[],
            ),
            StoryEventInput(
                event_type="timeline.upsert", subject="timeline", aggregate_type="timeline",
                aggregate_id="t-1", payload={"sequence_key": "001", "title": "Dusk"}, evidence=[],
            ),
        ],
    )
    first = service.apply_typed_diff(request)
    retry = service.apply_typed_diff(request.model_copy(update={"request_id": uuid4()}))

    assert first.revision == 1
    assert retry.replayed is True
    manifest = RevisionManifestRepository(database).get("runtime-book", 1)
    assert manifest is not None
    assert manifest.transition_kind == "domain_command"
    assert manifest.event_count == 2
    assert len(RevisionManifestRepository(database).list("runtime-book")) == 2
    with pytest.raises(ConflictError, match="different operator events"):
        service.apply_typed_diff(request.model_copy(update={
            "request_id": uuid4(), "reason": "changed retry payload",
        }))
    assert len(RevisionManifestRepository(database).list("runtime-book")) == 2


def test_chapter_and_typed_diff_with_same_expected_revision_have_one_manifest_winner(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    chapter = artifacts()
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="mixed-chapter-command-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1,
        intent={}, base_context_revision=0,
    ))
    validated = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key="mixed-chapter-command-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0,
        prepare_id=prepared.prepare_id, artifacts=chapter,
    ))
    chapter_request = CommitChapterRequest(
        request_id=uuid4(), idempotency_key="mixed-chapter-command-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, prepare_id=prepared.prepare_id,
        validation_token=validated.validation_token, artifacts=chapter,
    )
    diff_request = TypedDiffCommandRequest(
        request_id=uuid4(), idempotency_key="mixed-typed-command-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, actor="human", reason="concurrent edit",
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact", aggregate_id="mixed-fact",
            payload={"predicate": "world.concurrent", "value": True}, evidence=[],
        )],
    )

    def run(call):
        try:
            return call()
        except ConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, [
            lambda: service.commit(chapter_request),
            lambda: service.apply_typed_diff(diff_request),
        ]))

    assert sum(not isinstance(outcome, ConflictError) for outcome in outcomes) == 1
    manifests = RevisionManifestRepository(database).list("runtime-book")
    assert [manifest.revision for manifest in manifests] == [0, 1]
    with database.read() as conn:
        assert conn.execute("SELECT revision FROM projects WHERE project_id='runtime-book'").fetchone()[0] == 1


def test_sqlite_lock_returns_retryable_error(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    blocker = database.connect()
    conn = blocker.__enter__()
    conn.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(DatabaseUnavailableError) as raised:
            service.prepare(PrepareChapterRequest(
                request_id=uuid4(), idempotency_key="locked-prepare-key-0001", project_id="runtime-book",
                schema_version="story-runtime/v1", expected_revision=0, chapter_number=1, intent={}, base_context_revision=0,
            ))
        assert raised.value.retryable is True
        assert raised.value.code == "DATABASE_LOCKED"
    finally:
        conn.rollback()
        blocker.__exit__(None, None, None)


def test_locked_authority_command_consumes_no_manifest_or_revision_and_retries_cleanly(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    request = TypedDiffCommandRequest(
        request_id=uuid4(), idempotency_key="locked-authority-command-0001",
        project_id="runtime-book", schema_version="story-runtime/v1", expected_revision=0,
        actor="human", reason="locked writer retry",
        events=[StoryEventInput(
            event_type="fact.upsert", subject="world", aggregate_type="fact", aggregate_id="lock-fact",
            payload={"predicate": "world.lock", "value": "released"}, evidence=[],
        )],
    )
    blocker = database.connect()
    conn = blocker.__enter__()
    conn.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(DatabaseUnavailableError):
            service.apply_typed_diff(request)
    finally:
        conn.rollback()
        blocker.__exit__(None, None, None)

    assert [manifest.revision for manifest in RevisionManifestRepository(database).list("runtime-book")] == [0]
    assert service.apply_typed_diff(request.model_copy(update={"request_id": uuid4()})).revision == 1
    assert [manifest.revision for manifest in RevisionManifestRepository(database).list("runtime-book")] == [0, 1]


def test_doctor_distinguishes_pending_commit_and_outbox(tmp_path):
    database, service = runtime_service(tmp_path)
    create_project(service)
    service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key="doctor-prepare-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=0, chapter_number=1, intent={}, base_context_revision=0,
    ))
    doctor = RuntimeServices(database, StoryRepository(database)).doctor("runtime-book", deep=True)
    assert doctor.status == "warning"
    assert any(check.code.startswith("commit.") and "resume" in (check.repair or "") for check in doctor.checks)


def test_replay_expected_hash_mismatch_is_reported(tmp_path):
    _, service = runtime_service(tmp_path)
    create_project(service)
    lifecycle(service, artifacts())
    result = service.replay(ReplayProjectionsRequest(
        request_id=uuid4(), idempotency_key="replay-mismatch-key-0001", project_id="runtime-book",
        schema_version="story-runtime/v1", expected_revision=1,
        projection_names=["facts"], from_event_sequence=0, verify_only=True,
        expected_hash="0" * 64,
    ))
    assert result.state == "MISMATCH"
    assert result.matched is False
