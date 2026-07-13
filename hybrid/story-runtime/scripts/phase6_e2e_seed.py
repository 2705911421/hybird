from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from story_runtime.config import RuntimeConfig
from story_runtime.database import Database
from story_runtime.repository import StoryRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    database = Database(RuntimeConfig(database_path=args.db.resolve(), local_token="phase6-e2e-token", writes_enabled=True))
    database.migrations.migrate()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    StoryRepository(database).initialize_fixture(fixture, "phase6-e2e-fixture")
    now = datetime.now(timezone.utc).isoformat()
    commit_id = "77777777-7777-4777-8777-777777777777"
    with database.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE projects SET authority_mode='runtime' WHERE project_id='lighthouse-fixture'")
        conn.execute(
            "INSERT OR IGNORE INTO chapter_commits(commit_id,project_id,chapter_number,request_id,idempotency_key,request_hash,expected_revision,resulting_revision,state,body_sha256,artifact_sha256,schema_version,created_at,updated_at,finalized_at,error_details_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (commit_id, "lighthouse-fixture", 3, "phase6-e2e-request", "phase6-e2e-commit-key", "a" * 64, 6, 7,
             "FINALIZED", "b" * 64, "c" * 64, "story-runtime/v1", now, now, now, "{}"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO chapter_artifacts(commit_id,project_id,chapter_number,title,body_text,summary,outline_fulfillment_json,review_json,state_mutation_proposal_json,evidence_spans_json,events_json,schema_version,body_sha256,checksum,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (commit_id, "lighthouse-fixture", 3, "The Brass Key", "fixture body is never exposed by observability", "A key changes hands.", "{}", "{}", "{}", "[]", "[]", "story-runtime/v1", "b" * 64, "c" * 64, now),
        )
        conn.execute(
            "INSERT INTO commit_transitions(commit_id,from_state,to_state,reason,request_id,idempotency_key,project_id,chapter_number,expected_revision,resulting_revision,schema_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (commit_id, "PROJECTING", "FINALIZED", "deterministic fixture", "phase6-e2e-request", "phase6-e2e-commit-key", "lighthouse-fixture", 3, 6, 7, "story-runtime/v1", now),
        )
        conn.execute(
            "UPDATE projection_checkpoints SET status='retryable',retry_count=1,last_error='deterministic retryable fixture failure',updated_at=? WHERE project_id='lighthouse-fixture' AND projection_name='timeline'",
            (now,),
        )
        conn.execute(
            "INSERT INTO runtime_incidents(project_id,component,state,message,retryable,repair_action,created_at) VALUES (?,?,?,?,?,?,?)",
            ("lighthouse-fixture", "timeline", "degraded", "Timeline projection needs replay.", 1, "Preview and confirm projection replay.", now),
        )
        conn.commit()
    print(json.dumps({"project_id": "lighthouse-fixture", "commit_id": commit_id, "state": "degraded"}))


if __name__ == "__main__":
    main()
