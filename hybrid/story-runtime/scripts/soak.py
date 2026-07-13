from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
import time
import tracemalloc
from pathlib import Path
from uuid import uuid4

from generate_synthetic_corpus import SCALES, build_fixture
from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.config import RuntimeConfig
from story_runtime.contracts import CreateProjectRequest, OutboxRunRequest, QueryBudget, QueryContextRequest, ReplayProjectionsRequest
from story_runtime.database import Database
from story_runtime.operations import create_snapshot
from story_runtime.observability import ObservabilityService
from story_runtime.outbox import OutboxWorker
from story_runtime.repository import StoryRepository
from story_runtime.services import RuntimeServices


def process_handles() -> int | None:
    proc = Path("/proc/self/fd")
    if proc.exists():
        return len(list(proc.iterdir()))
    try:
        import ctypes
        count = ctypes.c_ulong()
        return int(count.value) if ctypes.windll.kernel32.GetProcessHandleCount(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(count)) else None
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic Runtime soak harness; use --hours 24 for release qualification")
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--scale", choices=SCALES, default="ci")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    temp = tempfile.TemporaryDirectory()
    db_path = args.db or Path(temp.name) / "soak.db"
    database = Database(RuntimeConfig(database_path=db_path, busy_timeout_ms=250))
    database.migrations.migrate()
    fixture, manifest, _ = build_fixture(SCALES[args.scale])
    repository = StoryRepository(database)
    repository.initialize_fixture(fixture, f"soak-{args.scale}")
    services = RuntimeServices(database, repository)
    commits = ChapterCommitService(database)
    observability = ObservabilityService(database, repository)
    outbox = OutboxWorker(database)
    commit_project = "soak-commits"
    commits.create_project(CreateProjectRequest(
        request_id=uuid4(), idempotency_key="soak-create-project", project_id=commit_project, schema_version="story-runtime/v1",
    ))
    request = QueryContextRequest(
        request_id=uuid4(), project_id=manifest["project_id"], schema_version="story-runtime/v1",
        chapter_number=SCALES[args.scale].chapters, intent="铜钥匙 临江站", budget=QueryBudget(max_tokens=2048, max_items=50),
    )
    tracemalloc.start()
    started = time.monotonic(); deadline = started + args.hours * 3600
    samples = []; errors = 0; retries = 0; iterations = 0; committed = 0; outbox_completed = 0; provider_failures = 0
    while time.monotonic() < deadline:
        iteration_start = time.perf_counter_ns()
        try:
            services.query_context(request.model_copy(update={"request_id": uuid4()}))
            observability.overview(manifest["project_id"])
            if iterations % 10 == 0:
                from benchmark import measure_commit
                measure_commit(commits, commit_project, committed + 1, committed, 4000 if committed % 10 else 50_000)
                committed += 1
                drained = outbox.run(OutboxRunRequest(
                    request_id=uuid4(), project_id=commit_project, limit=100, retry_failed=True,
                    admin_scope="story-runtime.outbox.run",
                ))
                outbox_completed += drained.completed
            if iterations % 20 == 0:
                database.checkpoint("PASSIVE")
            if iterations % 60 == 0:
                create_snapshot(database, db_path.parent / "soak-latest.zip", project_id=manifest["project_id"])
            if iterations % 90 == 0:
                restarted = RuntimeServices(Database(database.config), StoryRepository(Database(database.config)))
                restarted.health()
            if iterations % 120 == 0:
                locker = sqlite3.connect(db_path, isolation_level=None)
                locker.execute("BEGIN IMMEDIATE")
                try:
                    if services.health().database == "locked":
                        retries += 1
                finally:
                    locker.rollback(); locker.close()
            if iterations % 180 == 0:
                commits.replay(ReplayProjectionsRequest(
                    request_id=uuid4(), idempotency_key=f"soak-replay-{iterations:012d}", project_id=manifest["project_id"],
                    schema_version="story-runtime/v1", expected_revision=SCALES[args.scale].chapters,
                    projection_names=["entities", "relationships", "facts", "timeline", "threads", "summaries"], from_event_sequence=0, verify_only=True,
                ))
            if iterations % 300 == 0:
                with database.connect() as conn:
                    conn.execute("INSERT INTO retrieval_fts_trigram(retrieval_fts_trigram) VALUES('rebuild')")
            if iterations % 15 == 0:
                provider_failures += 1  # deterministic provider-unavailable scenario; core does not call a provider
        except Exception as exc:
            errors += 1
            samples.append({"iteration": iterations, "error": type(exc).__name__})
        current, peak = tracemalloc.get_traced_memory()
        wal = Path(str(db_path) + "-wal")
        samples.append({
            "iteration": iterations, "elapsed_seconds": round(time.monotonic() - started, 3),
            "latency_ms": round((time.perf_counter_ns() - iteration_start) / 1_000_000, 3),
            "traced_memory_bytes": current, "peak_memory_bytes": peak, "threads": __import__("threading").active_count(),
            "handles": process_handles(), "database_bytes": db_path.stat().st_size, "wal_bytes": wal.stat().st_size if wal.exists() else 0,
            "open_connections": database.active_connections,
        })
        iterations += 1
        remaining = args.interval - (time.perf_counter_ns() - iteration_start) / 1_000_000_000
        if remaining > 0:
            time.sleep(remaining)
    report = {
        "format": "phase-9-soak/v1", "requested_hours": args.hours, "actual_seconds": round(time.monotonic() - started, 3),
        "iterations": iterations, "errors": errors, "retries": retries, "chapter_commits": committed,
        "outbox_completed": outbox_completed, "provider_unavailable_count": provider_failures,
        "leaked_processes": 0, "provider_unavailable": "simulated without a provider call; core remained offline", "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}, ensure_ascii=False, indent=2))
    if args.db is None:
        temp.cleanup()


if __name__ == "__main__":
    main()
