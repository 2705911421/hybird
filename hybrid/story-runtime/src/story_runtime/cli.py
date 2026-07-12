from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .api import create_app
from .config import RuntimeConfig
from .database import Database
from .repository import StoryRepository
from .services import RuntimeServices


def _runtime(db_path: Path, timeout_ms: int = 750):
    config = RuntimeConfig(database_path=db_path.resolve(), busy_timeout_ms=timeout_ms)
    database = Database(config)
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
    init = sub.add_parser("init-fixture")
    init.add_argument("--fixture", type=Path, required=True)
    init.add_argument("--idempotency-key", default="fixture-bootstrap-v1")
    status = sub.add_parser("status")
    status.add_argument("project_id")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("project_id")
    doctor.add_argument("--deep", action="store_true")
    query = sub.add_parser("query")
    query.add_argument("project_id")
    query.add_argument("--entity")
    query.add_argument("--history", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=47831)
    args = parser.parse_args(argv)
    config, database, repository, services = _runtime(args.db)
    if args.command == "migrate":
        _print({"schema_version": database.migrations.migrate(args.target)})
    elif args.command == "init-fixture":
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        _print(repository.initialize_fixture(fixture, args.idempotency_key))
    elif args.command == "status":
        _print(services.project_status(args.project_id))
    elif args.command == "doctor":
        _print(services.doctor(args.project_id, args.deep))
    elif args.command == "query":
        if not args.entity:
            parser.error("query currently requires --entity for an exact lookup")
        _print(services.entity(args.project_id, args.entity, args.history))
    elif args.command == "serve":
        import uvicorn
        uvicorn.run(create_app(config), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
