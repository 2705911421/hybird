from __future__ import annotations

import json
import io
import logging
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from story_runtime.api import create_app
from story_runtime.config import RuntimeConfig
from story_runtime.database import Database
from story_runtime.operations import compatibility, create_snapshot, restore_snapshot
from story_runtime.runtime_logging import JsonFormatter


def test_online_snapshot_restores_only_to_a_new_directory(runtime, tmp_path):
    config, database, _, _ = runtime
    snapshot = tmp_path / "backup.zip"
    manifest = create_snapshot(database, snapshot, project_id="lighthouse-fixture")
    assert manifest["project_revision"] == 7
    assert len(manifest["projection_hash"]) == 64
    assert manifest["indexes_rebuild_required"] is True
    restored = restore_snapshot(snapshot, tmp_path / "restored")
    assert restored["integrity"] == "ok"
    assert restored["projection_hash"] == manifest["projection_hash"]
    assert restored["doctor"]["project_id"] == "lighthouse-fixture"
    restored_db = Database(RuntimeConfig(database_path=Path(restored["target_database"])))
    with restored_db.connect() as conn:
        assert conn.execute("SELECT revision FROM projects WHERE project_id='lighthouse-fixture'").fetchone()[0] == 7
    with pytest.raises(FileExistsError):
        restore_snapshot(snapshot, tmp_path / "restored")


def test_restore_rejects_unexpected_archive_entries(runtime, tmp_path):
    _, database, _, _ = runtime
    valid = tmp_path / "valid.zip"
    create_snapshot(database, valid)
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(valid) as source, zipfile.ZipFile(bad, "w") as target:
        for name in source.namelist():
            target.writestr(name, source.read(name))
        target.writestr("../outside.txt", "blocked")
    with pytest.raises(ValueError, match="unexpected"):
        restore_snapshot(bad, tmp_path / "bad-restore")
    assert not (tmp_path / "outside.txt").exists()


def test_compatibility_reports_schema_too_new_without_downgrading(tmp_path):
    database = Database(RuntimeConfig(database_path=tmp_path / "future.db"))
    database.migrations.migrate()
    with database.connect() as conn:
        conn.execute("INSERT INTO schema_migrations VALUES (999,'future','checksum','2026-01-01T00:00:00Z')")
    assert compatibility(database).status == "schema_too_new"
    with pytest.raises(RuntimeError, match="newer"):
        database.migrations.migrate()


def test_database_pragmas_checkpoint_and_network_warning(tmp_path, monkeypatch):
    database = Database(RuntimeConfig(database_path=tmp_path / "story.db", wal_autocheckpoint_pages=17))
    database.migrations.migrate()
    with database.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 17
    assert len(database.checkpoint("PASSIVE")) == 3
    monkeypatch.setenv("STORY_RUNTIME_ASSUME_NETWORK_FS", "1")
    assert "unsupported" in database.filesystem_warning()


def test_structured_log_redacts_secrets():
    record = logging.LogRecord("story_runtime", logging.INFO, __file__, 1, "Bearer abc API_KEY=secret", (), None)
    record.request_id = "request-1"
    payload = json.loads(JsonFormatter().format(record))
    assert "secret" not in payload["message"]
    assert "Bearer abc" not in payload["message"]
    assert payload["request_id"] == "request-1"
    assert payload["version"]
    assert payload["schema_version"] == "story-runtime/v1"


def test_http_rejects_oversized_payload_before_validation(tmp_path):
    config = RuntimeConfig(database_path=tmp_path / "api.db", local_token="token", max_request_bytes=16)
    with TestClient(create_app(config)) as client:
        response = client.post(
            "/api/story-runtime/v1/queries/context", headers={"Authorization": "Bearer token"}, json={"oversized": "x" * 100},
        )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
    assert response.headers["x-request-id"]


def test_http_counts_body_bytes_when_content_length_is_false(tmp_path):
    config = RuntimeConfig(database_path=tmp_path / "api.db", local_token="token", max_request_bytes=16)
    with TestClient(create_app(config)) as client:
        response = client.post(
            "/api/story-runtime/v1/queries/context",
            headers={"Authorization": "Bearer token", "Content-Length": "1"},
            content=b"x" * 100,
        )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_request_log_uses_route_template_and_fingerprints_project(runtime):
    config, _, _, _ = runtime
    config = replace(config, local_token="token")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("story_runtime")
    logger.addHandler(handler)
    try:
        with TestClient(create_app(config)) as client:
            response = client.get(
                "/api/story-runtime/v1/projects/lighthouse-fixture/status",
                headers={"Authorization": "Bearer token"},
            )
        assert response.status_code == 200
    finally:
        logger.removeHandler(handler)
        handler.close()

    payload = json.loads(stream.getvalue().splitlines()[-1])
    assert payload["operation"] == "GET /api/story-runtime/v1/projects/{project_id}/status"
    assert payload["project_id"] == "f700d3a52d02"
    assert "lighthouse-fixture" not in stream.getvalue()
