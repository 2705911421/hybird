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
