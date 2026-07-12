import sqlite3

from story_runtime.config import RuntimeConfig
from story_runtime.database import Database
from story_runtime.repository import StoryRepository
from story_runtime.services import RuntimeServices


def test_runtime_restart_preserves_state(runtime):
    config, _, _, _ = runtime
    restarted_database = Database(config)
    restarted = RuntimeServices(restarted_database, StoryRepository(restarted_database))
    assert restarted.entity("lighthouse-fixture", "char-ren").entity.attributes["status"] == "missing"
    assert restarted.project_status("lighthouse-fixture").revision == 7


def test_sqlite_lock_reports_recoverable_health(runtime):
    config, database, _, services = runtime
    locker = sqlite3.connect(database.path, isolation_level=None)
    locker.execute("BEGIN EXCLUSIVE")
    try:
        health = services.health()
        assert health.status == "degraded"
        assert health.database == "locked"
    finally:
        locker.rollback()
        locker.close()
    assert services.health().database == "ready"
