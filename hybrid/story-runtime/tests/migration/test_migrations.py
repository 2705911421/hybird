import sqlite3

import pytest

from story_runtime.config import RuntimeConfig
from story_runtime.database import Database
from story_runtime.migrations import Migration
import story_runtime.migrations as migration_module


@pytest.mark.migration
def test_migrate_empty_database_is_repeatable(tmp_path):
    database = Database(RuntimeConfig(database_path=tmp_path / "story.db"))
    assert database.migrations.migrate() == 8
    assert database.migrations.migrate() == 8
    assert database.migrations.current_version() == 8


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
    broken = Migration(9, "broken", "CREATE TABLE must_not_survive(value TEXT); INVALID SQL;", "DROP TABLE must_not_survive;")
    monkeypatch.setattr(migration_module, "MIGRATIONS", migration_module.MIGRATIONS + (broken,))
    with pytest.raises(sqlite3.OperationalError):
        database.migrations.migrate(9)
    assert database.migrations.current_version() == 8
    with database.connect() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='must_not_survive'").fetchone() is None


@pytest.mark.migration
def test_manifest_migration_creates_verified_v7_backup_before_up(tmp_path):
    path = tmp_path / "story.db"
    database = Database(RuntimeConfig(database_path=path))
    database.migrations.migrate(target=7)
    database.migrations.migrate()
    backup = path.with_name("story.db.pre-manifest-v7.sqlite3")
    assert backup.is_file()
    conn = sqlite3.connect(backup)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 7
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='project_revisions'").fetchone() is None
    finally:
        conn.close()


@pytest.mark.migration
def test_interrupted_manifest_migration_rolls_back_and_preserves_verified_backup(tmp_path, monkeypatch):
    path = tmp_path / "story.db"
    database = Database(RuntimeConfig(database_path=path))
    database.migrations.migrate(target=7)
    original = migration_module.MIGRATIONS[-1]
    interrupted = Migration(
        original.version,
        original.name,
        original.up + "\nCREATE TABLE interruption_probe(value TEXT); INVALID SQL;",
        original.down,
    )
    monkeypatch.setattr(migration_module, "MIGRATIONS", migration_module.MIGRATIONS[:-1] + (interrupted,))

    with pytest.raises(sqlite3.OperationalError):
        database.migrations.migrate()

    assert database.migrations.current_version() == 7
    backup = path.with_name("story.db.pre-manifest-v7.sqlite3")
    assert backup.is_file()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 7
    with database.connect() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='project_revisions'").fetchone() is None
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='interruption_probe'").fetchone() is None

    monkeypatch.setattr(migration_module, "MIGRATIONS", migration_module.MIGRATIONS[:-1] + (original,))
    with pytest.raises(RuntimeError, match="backup already exists"):
        database.migrations.migrate()


@pytest.mark.migration
def test_downgrade_stops_after_first_manifest_write(tmp_path):
    database = Database(RuntimeConfig(database_path=tmp_path / "story.db"))
    database.migrations.migrate()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) "
            "VALUES ('p',0,'initialized',0,'story-runtime/v1','now','now','runtime')"
        )
        conn.execute(
            "INSERT INTO project_revisions(project_id,revision,manifest_id,previous_revision,previous_manifest_hash,"
            "transition_kind,command_id,commit_id,idempotency_key,request_hash,event_count,first_event_sequence,"
            "last_event_sequence,ordered_event_ids_json,ordered_event_hashes_json,ordered_event_ids_hash,artifact_refs_json,"
            "artifact_hashes_json,event_schema_version,reducer_version,manifest_schema_version,contract_version,"
            "provenance_class,provenance_id,actor_class,state_hash,manifest_hash,created_at) "
            "VALUES ('p',0,'m',NULL,NULL,'initialize_empty','c',NULL,'key','hash',0,NULL,NULL,'[]','[]','oh','[]','[]',"
            "'legacy-unversioned','story-reducers/not-applicable','revision-manifest/v1','story-runtime/v1','native','p','system','s','h','now')"
        )
    with pytest.raises(RuntimeError, match="downgrade is blocked"):
        database.migrations.migrate(7)
    assert database.migrations.current_version() == 8
