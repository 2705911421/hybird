import sqlite3

import pytest

from story_runtime.config import RuntimeConfig
from story_runtime.database import Database
from story_runtime.migrations import Migration
import story_runtime.migrations as migration_module


@pytest.mark.migration
def test_migrate_empty_database_is_repeatable(tmp_path):
    database = Database(RuntimeConfig(database_path=tmp_path / "story.db"))
    assert database.migrations.migrate() == 2
    assert database.migrations.migrate() == 2
    assert database.migrations.current_version() == 2


@pytest.mark.migration
def test_migration_up_down_smoke(tmp_path):
    database = Database(RuntimeConfig(database_path=tmp_path / "story.db"))
    database.migrations.migrate()
    assert database.migrations.migrate(1) == 1
    with database.connect() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT * FROM retrieval_documents")
    assert database.migrations.migrate(2) == 2


@pytest.mark.migration
def test_failed_migration_rolls_back_atomically(tmp_path, monkeypatch):
    database = Database(RuntimeConfig(database_path=tmp_path / "story.db"))
    database.migrations.migrate()
    broken = Migration(3, "broken", "CREATE TABLE must_not_survive(value TEXT); INVALID SQL;", "DROP TABLE must_not_survive;")
    monkeypatch.setattr(migration_module, "MIGRATIONS", migration_module.MIGRATIONS + (broken,))
    with pytest.raises(sqlite3.OperationalError):
        database.migrations.migrate(3)
    assert database.migrations.current_version() == 2
    with database.connect() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='must_not_survive'").fetchone() is None
