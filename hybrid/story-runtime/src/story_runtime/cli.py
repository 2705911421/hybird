from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .api import create_app
from .config import RuntimeConfig
from .database import Database
from .repository import StoryRepository
from .services import RuntimeServices
from .observability import ObservabilityService, RecoveryService
from .operations import compatibility, create_snapshot, restore_snapshot


def _runtime(db_path: Path, timeout_ms: int = 750, *, migrate: bool = True):
    env_config = RuntimeConfig.from_env()
    config = RuntimeConfig(
        database_path=db_path.resolve(),
        local_token=env_config.local_token,
        busy_timeout_ms=env_config.busy_timeout_ms if timeout_ms == 750 else timeout_ms,
        writes_enabled=env_config.writes_enabled,
    )
    database = Database(config)
    if migrate:
        database.migrations.migrate()
    repository = StoryRepository(database)
    return config, database, repository, RuntimeServices(database, repository)


def _print(value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="story-runtime", description="Independent local Story Runtime")
    parser.add_argument("--db", type=Path, default=Path(os.getenv("STORY_RUNTIME_DB", "./data/story.db")))
    sub = parser.add_subparsers(dest="command", required=True)
    migrate = sub.add_parser("migrate")
    migrate.add_argument("--target", type=int)
    migrate.add_argument("--snapshot-dir", type=Path, default=Path("./backups"))
    migrate.add_argument("--report", type=Path)
    init = sub.add_parser("init-fixture")
    init.add_argument("--fixture", type=Path, required=True)
    init.add_argument("--idempotency-key", default="fixture-bootstrap-v1")
    status = sub.add_parser("status")
    status.add_argument("project_id")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("project_id")
    doctor.add_argument("--deep", action="store_true")
    overview = sub.add_parser("overview")
    overview.add_argument("project_id")
    commits = sub.add_parser("commits")
    commits.add_argument("project_id")
    commits.add_argument("--cursor")
    commits.add_argument("--limit", type=int, default=25)
    commits.add_argument("--chapter", type=int)
    commits.add_argument("--state")
    events = sub.add_parser("events")
    events.add_argument("project_id")
    events.add_argument("--cursor")
    events.add_argument("--limit", type=int, default=25)
    events.add_argument("--event-type")
    events.add_argument("--chapter", type=int)
    events.add_argument("--revision", type=int)
    events.add_argument("--view", choices=("summary", "evidence"), default="summary")
    projections = sub.add_parser("projections")
    projections.add_argument("project_id")
    diagnostics = sub.add_parser("diagnostics")
    diagnostics.add_argument("project_id")
    sub.add_parser("migration-status")
    sub.add_parser("configuration-status")
    query = sub.add_parser("query")
    query.add_argument("project_id")
    query.add_argument("--entity")
    query.add_argument("--history", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=47831)
    create = sub.add_parser("create-project")
    create.add_argument("project_id")
    create.add_argument("--idempotency-key", required=True)
    outbox = sub.add_parser("run-outbox")
    outbox.add_argument("--project-id")
    outbox.add_argument("--limit", type=int, default=100)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("destination", type=Path)
    snapshot.add_argument("--project-id")
    restore = sub.add_parser("restore")
    restore.add_argument("snapshot", type=Path)
    restore.add_argument("target_dir", type=Path)
    sub.add_parser("compatibility")
    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--mode", choices=("PASSIVE", "FULL", "RESTART", "TRUNCATE"), default="PASSIVE")
    args = parser.parse_args(argv)
    config, database, repository, services = _runtime(args.db, migrate=False)
    if warning := database.filesystem_warning():
        print(f"WARNING: {warning}", file=sys.stderr)
    observability = ObservabilityService(database, repository)
    if args.command == "migrate":
        before = database.migrations.current_version()
        target = args.target if args.target is not None else database.latest_schema_version
        if target < before:
            parser.error(
                "in-place database downgrade is not supported; restore the verified pre-migration snapshot into a new directory"
            )
        snapshot_result = None
        if database.path.exists() and database.path.stat().st_size > 0 and before != target:
            stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
            snapshot_result = create_snapshot(database, args.snapshot_dir / f"pre-migration-{before}-to-{target}-{stamp}.zip")
        applied = database.migrations.migrate(args.target)
        report = {"status": "completed", "from_schema": before, "to_schema": applied, "pre_migration_snapshot": snapshot_result}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _print(report)
    elif args.command == "restore":
        _print(restore_snapshot(args.snapshot, args.target_dir))
    elif args.command == "compatibility":
        _print(compatibility(database).as_dict())
    elif args.command == "checkpoint":
        busy, log_pages, checkpointed = database.checkpoint(args.mode)
        _print({"mode": args.mode, "busy": busy, "log_pages": log_pages, "checkpointed_pages": checkpointed})
    elif args.command == "snapshot":
        _print(create_snapshot(database, args.destination, project_id=args.project_id))
    elif args.command == "init-fixture":
        database.migrations.migrate()
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        _print(repository.initialize_fixture(fixture, args.idempotency_key))
    elif args.command == "status":
        _print(services.project_status(args.project_id))
    elif args.command == "doctor":
        _print(services.doctor(args.project_id, args.deep))
    elif args.command == "overview":
        _print(observability.overview(args.project_id))
    elif args.command == "commits":
        _print(observability.commits(args.project_id, cursor=args.cursor, limit=args.limit, chapter=args.chapter,
                                     state=args.state, date_from=None, date_to=None))
    elif args.command == "events":
        _print(observability.events(args.project_id, cursor=args.cursor, limit=args.limit, event_type=args.event_type,
                                    aggregate=None, chapter=args.chapter, revision=args.revision, view=args.view))
    elif args.command == "projections":
        _print(observability.projections(args.project_id))
    elif args.command == "diagnostics":
        _print(observability.diagnostics(args.project_id, services.doctor(args.project_id, False)))
    elif args.command == "migration-status":
        _print(observability.migration())
    elif args.command == "configuration-status":
        _print(observability.configuration())
    elif args.command == "query":
        if not args.entity:
            parser.error("query currently requires --entity for an exact lookup")
        _print(services.entity(args.project_id, args.entity, args.history))
    elif args.command == "serve":
        if database.path.exists() and database.migrations.current_version() not in {0, database.latest_schema_version}:
            parser.error("database migration required; run 'story-runtime migrate' to create a snapshot and migrate")
        database.migrations.migrate()
        import uvicorn
        if args.host not in {"127.0.0.1", "::1", "localhost"}:
            parser.error("non-loopback Runtime exposure is unsupported without a separate authenticated network design")
        uvicorn.run(create_app(config), host=args.host, port=args.port)
    elif args.command == "create-project":
        from uuid import uuid4
        from .chapter_commits import ChapterCommitService
        from .contracts import CreateProjectRequest
        _print(ChapterCommitService(database).create_project(CreateProjectRequest(
            request_id=uuid4(), idempotency_key=args.idempotency_key,
            project_id=args.project_id, schema_version="story-runtime/v1",
        )))
    elif args.command == "run-outbox":
        from uuid import uuid4
        from .contracts import OutboxRunRequest
        from .outbox import OutboxWorker
        _print(OutboxWorker(database).run(OutboxRunRequest(
            request_id=uuid4(), project_id=args.project_id, limit=args.limit,
            admin_scope="story-runtime.outbox.run",
        )))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
