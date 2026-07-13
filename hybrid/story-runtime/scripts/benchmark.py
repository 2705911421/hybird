from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from generate_synthetic_corpus import SCALES, build_fixture
from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.config import RuntimeConfig
from story_runtime.contracts import (
    ChapterArtifacts, CommitChapterRequest, CreateProjectRequest, PrepareChapterRequest,
    QueryBudget, QueryContextRequest, ReplayProjectionsRequest, StoryEventInput,
    ValidateChapterArtifactsRequest,
)
from story_runtime.database import Database
from story_runtime.operations import create_snapshot
from story_runtime.repository import StoryRepository
from story_runtime.services import RuntimeServices


def distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    pick = lambda fraction: ordered[min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))]
    return {"p50": round(statistics.median(ordered), 3), "p95": round(pick(.95), 3), "p99": round(pick(.99), 3), "max": round(max(ordered), 3)}


def chapter_artifacts(chapter: int, body_chars: int) -> ChapterArtifacts:
    body = (f"第{chapter}章，临江站复核铜钥匙与时间线。" * (body_chars // 20 + 1))[:body_chars]
    return ChapterArtifacts(
        chapter_number=chapter, title=f"基准章节{chapter}", body=body,
        body_sha256=hashlib.sha256(body.encode()).hexdigest(), summary="确定性提交基准。",
        outline_fulfillment={"planned_node_ids": [], "covered_node_ids": [], "missed_node_ids": []},
        review={"passed": True, "issues": []}, state_mutation_proposal={"source": "deterministic-benchmark"},
        events=[
            StoryEventInput(
                event_type="entity.upsert", subject=f"chapter-{chapter}", aggregate_type="entity",
                aggregate_id=f"chapter-{chapter}", payload={"entity_type": "chapter_marker", "canonical_name": f"章节{chapter}", "attributes": {}}, evidence=[],
            ),
            StoryEventInput(
                event_type="fact.upsert", subject=f"chapter-{chapter}", aggregate_type="fact",
                aggregate_id=f"benchmark-fact-{chapter}", payload={"predicate": "chapter.status", "value": "finalized"}, evidence=[],
            ),
        ],
    )


def measure_commit(service: ChapterCommitService, project_id: str, chapter: int, revision: int, body_chars: int) -> tuple[float, float, float]:
    key = f"benchmark-chapter-{chapter:08d}"
    artifacts = chapter_artifacts(chapter, body_chars)
    start = time.perf_counter_ns()
    prepared = service.prepare(PrepareChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id=project_id, schema_version="story-runtime/v1",
        expected_revision=revision, chapter_number=chapter, intent={}, base_context_revision=revision,
    ))
    validated = service.validate(ValidateChapterArtifactsRequest(
        request_id=uuid4(), idempotency_key=key, project_id=project_id, schema_version="story-runtime/v1",
        expected_revision=revision, prepare_id=prepared.prepare_id, artifacts=artifacts,
    ))
    commit_start = time.perf_counter_ns()
    request = CommitChapterRequest(
        request_id=uuid4(), idempotency_key=key, project_id=project_id, schema_version="story-runtime/v1",
        expected_revision=revision, prepare_id=prepared.prepare_id, validation_token=validated.validation_token, artifacts=artifacts,
    )
    service.commit(request)
    commit_ms = (time.perf_counter_ns() - commit_start) / 1_000_000
    lifecycle_ms = (time.perf_counter_ns() - start) / 1_000_000
    retry_start = time.perf_counter_ns()
    service.commit(request.model_copy(update={"request_id": uuid4()}))
    retry_ms = (time.perf_counter_ns() - retry_start) / 1_000_000
    return lifecycle_ms, commit_ms, retry_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 9 deterministic performance benchmark")
    parser.add_argument("--scale", choices=SCALES, default="million")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--commit-iterations", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--keep-db", type=Path)
    args = parser.parse_args()
    fixture, corpus_manifest, _ = build_fixture(SCALES[args.scale], args.seed)
    temp = tempfile.TemporaryDirectory()
    db_path = args.keep_db or Path(temp.name) / "story.db"
    database = Database(RuntimeConfig(database_path=db_path, writes_enabled=True))
    migrate_start = time.perf_counter_ns()
    database.migrations.migrate()
    migration_ms = (time.perf_counter_ns() - migrate_start) / 1_000_000
    repository = StoryRepository(database)
    init_start = time.perf_counter_ns()
    repository.initialize_fixture(fixture, f"synthetic-{args.scale}-{args.seed}")
    initialize_ms = (time.perf_counter_ns() - init_start) / 1_000_000
    services = RuntimeServices(database, repository)

    exact, lexical, validation, serialization = [], [], [], []
    response_bytes: list[int] = []
    compliance: list[bool] = []
    request = QueryContextRequest(
        request_id=uuid4(), project_id=corpus_manifest["project_id"], schema_version="story-runtime/v1",
        chapter_number=SCALES[args.scale].chapters, intent="铜钥匙 临江站 时间线",
        entity_ids=["char-0000"], budget=QueryBudget(max_tokens=4096, max_items=100),
    )
    for _ in range(args.iterations):
        started = time.perf_counter_ns()
        services.entity(corpus_manifest["project_id"], "char-0000", True)
        exact.append((time.perf_counter_ns() - started) / 1_000_000)
        started = time.perf_counter_ns()
        parsed = QueryContextRequest.model_validate(request.model_dump(mode="json"))
        validation.append((time.perf_counter_ns() - started) / 1_000_000)
        started = time.perf_counter_ns()
        response = services.query_context(parsed)
        lexical.append((time.perf_counter_ns() - started) / 1_000_000)
        started = time.perf_counter_ns()
        encoded = response.model_dump_json().encode()
        serialization.append((time.perf_counter_ns() - started) / 1_000_000)
        response_bytes.append(len(encoded))
        compliance.append(response.trace.budget_used <= request.budget.max_tokens and len(response.trace.selected_source_ids) <= request.budget.max_items)

    commit_service = ChapterCommitService(database)
    commit_project = "benchmark-commits"
    commit_service.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="benchmark-create-project", project_id=commit_project, schema_version="story-runtime/v1",
    ))
    normal_lifecycle, normal_transaction, retries = [], [], []
    for index in range(args.commit_iterations):
        lifecycle, transaction, retry = measure_commit(commit_service, commit_project, index + 1, index, 4000)
        normal_lifecycle.append(lifecycle); normal_transaction.append(transaction); retries.append(retry)
    large_lifecycle, large_transaction = [], []
    for offset in range(max(3, args.commit_iterations // 5)):
        chapter = args.commit_iterations + offset + 1
        revision = args.commit_iterations + offset
        lifecycle, transaction, retry = measure_commit(commit_service, commit_project, chapter, revision, 50_000)
        large_lifecycle.append(lifecycle); large_transaction.append(transaction); retries.append(retry)

    replay_start = time.perf_counter_ns()
    replay = commit_service.replay(ReplayProjectionsRequest(
        request_id=uuid4(), idempotency_key="benchmark-replay-all", project_id=corpus_manifest["project_id"],
        schema_version="story-runtime/v1", expected_revision=SCALES[args.scale].chapters,
        projection_names=["entities", "relationships", "facts", "timeline", "threads", "summaries"],
        from_event_sequence=0, verify_only=True,
    ))
    replay_ms = (time.perf_counter_ns() - replay_start) / 1_000_000
    snapshot_path = db_path.parent / "benchmark-snapshot.zip"
    snapshot_start = time.perf_counter_ns()
    snapshot = create_snapshot(database, snapshot_path, project_id=corpus_manifest["project_id"])
    snapshot_ms = (time.perf_counter_ns() - snapshot_start) / 1_000_000
    with database.connect() as conn:
        plans = {
            "facts": [row[3] for row in conn.execute("EXPLAIN QUERY PLAN SELECT * FROM facts WHERE project_id=? AND valid_to_revision IS NULL ORDER BY fact_id LIMIT 100", (corpus_manifest["project_id"],))],
            "events": [row[3] for row in conn.execute("EXPLAIN QUERY PLAN SELECT * FROM story_events WHERE project_id=? ORDER BY sequence LIMIT 100", (corpus_manifest["project_id"],))],
            "retrieval": [row[3] for row in conn.execute("EXPLAIN QUERY PLAN SELECT * FROM retrieval_documents WHERE project_id=? AND chapter_number=?", (corpus_manifest["project_id"], SCALES[args.scale].chapters))],
        }
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        outbox_pending = int(conn.execute("SELECT COUNT(*) FROM outbox WHERE project_id=? AND status='pending'", (commit_project,)).fetchone()[0])
    wal_path = Path(str(db_path) + "-wal")
    checkpoint = database.checkpoint("TRUNCATE")
    result = {
        "benchmark": "phase-9/v1", "measured_at_unix": int(time.time()), "corpus": corpus_manifest,
        "environment": {"python": __import__("platform").python_version(), "platform": __import__("platform").platform(), "sqlite": __import__("sqlite3").sqlite_version},
        "setup_ms": {"migration": round(migration_ms, 3), "initialize": round(initialize_ms, 3)},
        "context_query_ms": {"exact": distribution(exact), "lexical": distribution(lexical), "optional_vector": {"status": "not_configured", "values": None}},
        "context_response": {"max_bytes": max(response_bytes), "token_budget_compliance": all(compliance), "samples": len(compliance)},
        "chapter_commit_ms": {"normal_lifecycle": distribution(normal_lifecycle), "normal_transaction": distribution(normal_transaction), "large_lifecycle": distribution(large_lifecycle), "large_transaction": distribution(large_transaction), "response_loss_retry": distribution(retries)},
        "validation_ms": {"pydantic_query": distribution(validation), "serialization": distribution(serialization), "zod": {"status": "not_measured_by_python_harness"}},
        "recovery_ms": {"projection_replay_verify": round(replay_ms, 3), "snapshot": round(snapshot_ms, 3)},
        "replay": {"event_count": replay.event_count, "hash": replay.resulting_hash, "matched": replay.matched},
        "storage": {"database_bytes": page_count * page_size, "wal_bytes_before_truncate": wal_path.stat().st_size if wal_path.exists() else 0, "snapshot_bytes": snapshot["database"]["bytes"], "checkpoint": checkpoint, "outbox_pending": outbox_pending},
        "query_plans": plans,
        "unmeasured": ["vector retrieval", "Studio browser rendering", "Zod validation", "OS package smoke", "24-hour soak"],
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if args.keep_db is None:
        temp.cleanup()


if __name__ == "__main__":
    main()
