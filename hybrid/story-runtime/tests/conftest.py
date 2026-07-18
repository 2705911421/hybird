from __future__ import annotations

import json
from pathlib import Path

import pytest

from story_runtime.api import create_app
from story_runtime.config import RuntimeConfig
from story_runtime.database import Database
from story_runtime.repository import StoryRepository
from story_runtime.services import RuntimeServices


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_data():
    return json.loads((ROOT / "fixtures/lighthouse-project.json").read_text(encoding="utf-8"))


@pytest.fixture
def runtime(tmp_path, fixture_data):
    config = RuntimeConfig(database_path=tmp_path / "story.db", local_token="test-token", busy_timeout_ms=100)
    database = Database(config)
    database.migrations.migrate()
    repository = StoryRepository(database)
    repository.initialize_fixture(fixture_data, "test-fixture-bootstrap")
    services = RuntimeServices(database, repository)
    return config, database, repository, services


@pytest.fixture
def app(runtime):
    config, _, _, _ = runtime
    return create_app(config)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def legacy_v7_database(tmp_path):
    """Reusable current-state-only migration-7 project with imperfect legacy metadata."""

    config = RuntimeConfig(
        database_path=tmp_path / "legacy-v7.db",
        local_token="test-token",
        busy_timeout_ms=5_000,
    )
    database = Database(config)
    database.migrations.migrate(target=7)
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) "
            "VALUES ('legacy-first-write',7,'migration-verifying',3,'story-runtime/v1','old','old','runtime')"
        )
        conn.execute(
            "INSERT INTO entities(project_id,entity_id,entity_type,canonical_name,aliases_json,attributes_json,history_json) "
            "VALUES ('legacy-first-write','legacy-character','character','Legacy Character','[]','{\"kept\":true}','[]')"
        )
        conn.execute(
            "INSERT INTO facts(project_id,fact_id,subject,predicate,value_json,valid_from_revision) "
            "VALUES ('legacy-first-write','legacy-fact','world','world.legacy','true',7)"
        )
        conn.execute(
            "INSERT INTO chapter_summaries(project_id,chapter_number,title,summary,body_sha256) "
            "VALUES ('legacy-first-write',3,'Legacy Three','preserved summary',?)",
            ("a" * 64,),
        )
        conn.execute(
            "INSERT INTO chapter_commits(commit_id,project_id,chapter_number,request_id,idempotency_key,request_hash,"
            "expected_revision,resulting_revision,state,body_sha256,artifact_sha256,schema_version,created_at,updated_at,error_details_json) "
            "VALUES ('legacy-partial-commit','legacy-first-write',4,'legacy-request','legacy-partial-key-0001','legacy-hash',"
            "7,NULL,'PREPARED',NULL,NULL,'story-runtime/v1','old','old','{\"legacy_optional\":true}')"
        )
        conn.execute(
            "INSERT INTO story_events(project_id,event_id,event_type,subject,chapter_number,payload_json,evidence_json,confidence,"
            "commit_id,ordinal,aggregate_type,aggregate_id,schema_version,created_at,applied_revision) "
            "VALUES ('legacy-first-write','legacy-null-schema','legacy.fact','world',1,'{\"legacy\":true}','not-json',1.0,"
            "NULL,NULL,'project','legacy-first-write',NULL,'old',NULL)"
        )
        conn.execute(
            "INSERT INTO story_events(project_id,event_id,event_type,subject,chapter_number,payload_json,evidence_json,confidence,"
            "commit_id,ordinal,aggregate_type,aggregate_id,schema_version,created_at,applied_revision) "
            "VALUES ('legacy-first-write','legacy-unknown-schema','legacy.fact','world',2,'{\"legacy\":\"unknown\"}','[]',1.0,"
            "NULL,NULL,'project','legacy-first-write','legacy-events/v999','old',NULL)"
        )
    with database.read() as conn:
        snapshot = {
            "events": [dict(row) for row in conn.execute(
                "SELECT * FROM story_events WHERE project_id='legacy-first-write' ORDER BY event_id"
            )],
            "entity": dict(conn.execute(
                "SELECT * FROM entities WHERE project_id='legacy-first-write' AND entity_id='legacy-character'"
            ).fetchone()),
            "fact": dict(conn.execute(
                "SELECT * FROM facts WHERE project_id='legacy-first-write' AND fact_id='legacy-fact'"
            ).fetchone()),
            "partial_commit": dict(conn.execute(
                "SELECT * FROM chapter_commits WHERE commit_id='legacy-partial-commit'"
            ).fetchone()),
        }
    return config, database, snapshot
