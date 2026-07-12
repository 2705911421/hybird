from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from story_runtime.config import RuntimeConfig
from story_runtime.contracts import QueryBudget, QueryContextRequest
from story_runtime.database import Database
from story_runtime.repository import StoryRepository
from story_runtime.services import RuntimeServices


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[min(len(values) - 1, int(len(values) * fraction))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(RuntimeConfig(database_path=Path(tmp) / "story.db"))
        db.migrations.migrate()
        repo = StoryRepository(db)
        fixture = json.loads((root / "fixtures/lighthouse-project.json").read_text(encoding="utf-8"))
        repo.initialize_fixture(fixture, "benchmark-fixture-v1")
        services = RuntimeServices(db, repo)
        exact, rag = [], []
        for _ in range(args.iterations):
            start = time.perf_counter_ns()
            services.entity("lighthouse-fixture", "char-lin", True)
            exact.append((time.perf_counter_ns() - start) / 1_000_000)
            request = QueryContextRequest(request_id=uuid4(), project_id="lighthouse-fixture", schema_version="story-runtime/v1", chapter_number=4, intent="harbor brass key ferry", budget=QueryBudget(max_tokens=1024, max_items=20))
            start = time.perf_counter_ns()
            services.query_context(request)
            rag.append((time.perf_counter_ns() - start) / 1_000_000)
        result = {
            "fixture": "lighthouse-project", "iterations": args.iterations,
            "exact_query_ms": {"median": round(statistics.median(exact), 3), "p95": round(percentile(exact, .95), 3)},
            "context_rag_query_ms": {"median": round(statistics.median(rag), 3), "p95": round(percentile(rag, .95), 3)},
        }
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
