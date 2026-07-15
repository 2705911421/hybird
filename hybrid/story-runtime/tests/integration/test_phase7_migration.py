from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def _write_source(root: Path, *, truth_conflict: bool = False) -> dict[str, int]:
    (root / "story" / "state").mkdir(parents=True)
    (root / "chapters").mkdir()
    (root / "inkos.json").write_text(json.dumps({"version": "1.7.0"}), encoding="utf-8")
    (root / "story" / "state" / "characters.json").write_text(
        json.dumps([{"id": "lin", "name": "林澈", "aliases": ["阿澈"], "status": "active"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "story" / "state" / "hooks.json").write_text(
        json.dumps([{"id": "h1", "title": "灯塔信号", "status": "active", "introduced_chapter": 1}], ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "chapters" / "Ch001.md").write_text("# 第一章 灯塔\n\n潮水漫过旧台阶。🌊", encoding="utf-8")
    (root / "chapters" / "Ch002.md").write_text("# 第二章 回声\n\n林澈听见回声。", encoding="utf-8")
    if truth_conflict:
        (root / "story" / "current_state.md").write_text("# Current state\n林澈已经离开。", encoding="utf-8")
    return {str(path.relative_to(root)): path.stat().st_mtime_ns for path in root.rglob("*") if path.is_file()}


def _create(client: TestClient, headers: dict[str, str], source: Path, target: str = "migrated-cjk") -> dict:
    response = client.post("/api/story-runtime/v1/migration-jobs", headers=headers, json={
        "source_path": str(source), "target_project_id": target, "source_type": "auto",
        "mapping_version": "phase7-map-v1", "create_new_version": False,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _post(client: TestClient, headers: dict[str, str], job_id: str, action: str, payload: dict | None = None):
    response = client.post(f"/api/story-runtime/v1/migration-jobs/{job_id}/{action}", headers=headers, json=payload or {"actor": "pytest", "confirmation": None})
    assert response.status_code == 200, response.text
    return response.json()


def _write_enabled_app(app):
    from story_runtime.api import create_app
    config = app.state.config.__class__(
        database_path=app.state.config.database_path, local_token="test-token", busy_timeout_ms=100,
        writes_enabled=True, migration_enabled=True,
    )
    return create_app(config)


def test_inkos_cir_dry_run_import_verify_cutover_is_idempotent(app, auth_headers, tmp_path):
    source = tmp_path / "旧项目📚"
    mtimes = _write_source(source)
    write_app = _write_enabled_app(app)
    with TestClient(write_app) as client:
        job = _create(client, auth_headers, source)
        reused = _create(client, auth_headers, source)
        assert reused["migration_job_id"] == job["migration_job_id"]
        assert reused["reused"] is True

        job = _post(client, auth_headers, job["migration_job_id"], "scan")
        assert job["current_stage"] == "READY"
        assert job["cir"]["cir_version"] == "canonical-import/v1"
        assert len(job["cir"]["chapters"]) == 2
        assert all(item["sha256"] for item in job["source_checksum_manifest"] if item["type"] != "symlink")

        job = _post(client, auth_headers, job["migration_job_id"], "dry-run")
        assert job["dry_run"]["add"]["chapters"] == 2
        assert job["dry_run"]["blocking_conflicts"] == []
        job = _post(client, auth_headers, job["migration_job_id"], "snapshot")
        assert job["target_snapshot"]["verified"] is True
        job = _post(client, auth_headers, job["migration_job_id"], "import")
        assert job["current_stage"] == "VERIFYING"
        job = _post(client, auth_headers, job["migration_job_id"], "import")
        assert job["current_stage"] == "VERIFYING"
        with write_app.state.database.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM chapter_commits WHERE project_id='migrated-cjk'").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM entities WHERE project_id='migrated-cjk'").fetchone()[0] == 1
            assert conn.execute("SELECT revision FROM projects WHERE project_id='migrated-cjk'").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM project_revisions WHERE project_id='migrated-cjk'").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM story_events WHERE project_id='migrated-cjk' AND applied_revision IS NOT NULL").fetchone()[0] == 0
        # Retry is ledger-idempotent and does not create duplicate authority rows.
        job = _post(client, auth_headers, job["migration_job_id"], "verify")
        assert job["current_stage"] == "COMPLETED"
        assert job["verification"]["chapter_body_coverage"] == 1.0
        assert job["verification"]["chapter_checksum_coverage"] == 1.0
        assert job["verification"]["replay_hash"] == job["verification"]["projection_hash"]
        status = client.get("/api/story-runtime/v1/projects/migrated-cjk/status", headers=auth_headers).json()
        assert status["authority_mode"] == "legacy"

        rejected = client.post(f"/api/story-runtime/v1/migration-jobs/{job['migration_job_id']}/cutover", headers=auth_headers, json={"actor": "pytest", "confirmation": "yes"})
        assert rejected.status_code == 409
        job = _post(client, auth_headers, job["migration_job_id"], "cutover", {"actor": "pytest", "confirmation": "CONFIRM_RUNTIME_CUTOVER"})
        assert job["cutover_confirmed"] is True
        status = client.get("/api/story-runtime/v1/projects/migrated-cjk/status", headers=auth_headers).json()
        assert status["authority_mode"] == "runtime"
        with write_app.state.database.connect() as conn:
            boundary = conn.execute("SELECT * FROM project_revisions WHERE project_id='migrated-cjk'").fetchall()
            assert len(boundary) == 1
            assert boundary[0]["revision"] == 1
            assert boundary[0]["transition_kind"] == "bootstrap"
            assert boundary[0]["provenance_class"] == "bootstrap_boundary"
            assert boundary[0]["previous_revision"] is None

    assert mtimes == {str(path.relative_to(source)): path.stat().st_mtime_ns for path in source.rglob("*") if path.is_file()}
    assert not any(path.name.startswith("migration") for path in source.rglob("*"))


def test_semantic_conflict_waits_for_human_decision(app, auth_headers, tmp_path):
    source = tmp_path / "conflict"
    _write_source(source, truth_conflict=True)
    with TestClient(app) as client:
        job = _create(client, auth_headers, source, "conflict-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
        assert job["current_stage"] == "AWAITING_DECISIONS"
        conflict = next(item for item in job["conflicts"] if item["type"] == "conflicting_fact")
        blocked = client.post(f"/api/story-runtime/v1/migration-jobs/{job['migration_job_id']}/snapshot", headers=auth_headers, json={"actor": "pytest"})
        assert blocked.status_code in {403, 409}
        response = client.post(f"/api/story-runtime/v1/migration-jobs/{job['migration_job_id']}/decisions", headers=auth_headers, json={"decisions": [{
            "conflict_id": conflict["conflict_id"], "decision": "choose_candidate", "candidate_id": "markdown-truth", "note": "operator reviewed both sources",
        }]})
        assert response.status_code == 200, response.text
        assert response.json()["current_stage"] == "READY"
        assert response.json()["decisions"][conflict["conflict_id"]]["actor"] == "local-operator"
        preview = _post(client, auth_headers, job["migration_job_id"], "dry-run")
        assert preview["dry_run"]["add"]["entities"] == 0
        assert preview["dry_run"]["add"]["documents"] >= 1


def test_corrupt_json_is_quarantined_and_source_hash_is_reported(app, auth_headers, tmp_path):
    source = tmp_path / "broken"
    _write_source(source)
    broken = source / "story" / "state" / "broken.json"
    broken.write_bytes(b'{"not": valid}')
    expected = hashlib.sha256(broken.read_bytes()).hexdigest()
    with TestClient(app) as client:
        job = _create(client, auth_headers, source, "broken-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
    assert job["current_stage"] == "AWAITING_DECISIONS"
    item = next(item for item in job["source_checksum_manifest"] if item["path"].endswith("broken.json"))
    assert item["sha256"] == expected
    assert item["parse_status"] == "error"
    assert any(conflict["type"] == "corrupted_source" for conflict in job["conflicts"])


def test_symlink_is_never_followed(app, auth_headers, tmp_path):
    source = tmp_path / "symlink-source"
    _write_source(source)
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret": true}', encoding="utf-8")
    link = source / "story" / "state" / "escape.json"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        return
    with TestClient(app) as client:
        job = _create(client, auth_headers, source, "symlink-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
    manifest = next(item for item in job["source_checksum_manifest"] if item["path"].endswith("escape.json"))
    assert manifest["type"] == "symlink"
    assert manifest["parse_status"] == "rejected"
    assert manifest["sha256"] is None


def test_webnovel_json_sqlite_disagreement_is_not_silently_resolved(app, auth_headers, tmp_path):
    source = tmp_path / "webnovel"
    (source / ".webnovel").mkdir(parents=True)
    (source / "events").mkdir()
    (source / "chapters").mkdir()
    (source / ".webnovel" / "state.json").write_text(json.dumps({"version": "6.2", "revision": 1}), encoding="utf-8")
    (source / "events" / "events.json").write_text(json.dumps([{"event_id": "e1", "event_type": "fact.set", "subject": "project"}]), encoding="utf-8")
    (source / "chapters" / "chapter-1.md").write_text("# Chapter 1\nBody", encoding="utf-8")
    conn = sqlite3.connect(source / "index.db")
    try:
        conn.execute("CREATE TABLE events(event_id TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO events VALUES (?)", [("e1",), ("e2",)])
        conn.commit()
    finally:
        conn.close()
    with TestClient(app) as client:
        job = _create(client, auth_headers, source, "webnovel-target")
        assert job["source_type"] == "webnovel-writer"
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
    assert job["current_stage"] == "AWAITING_DECISIONS"
    conflict = next(item for item in job["conflicts"] if item["conflict_id"].startswith("conflicting_fact:") and "webnovel" in json.dumps(item))
    assert {candidate["candidate_id"] for candidate in conflict["candidates"]} == {"webnovel-json", "webnovel-index-db"}
    vector_docs = [item for item in job["cir"]["documents"] if item["document_type"] == "vector_metadata"]
    assert vector_docs == []


def test_pause_resume_keeps_stage_and_decisions(app, auth_headers, tmp_path):
    source = tmp_path / "pause-source"
    _write_source(source, truth_conflict=True)
    with TestClient(app) as client:
        job = _create(client, auth_headers, source, "pause-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
        conflict = next(item for item in job["conflicts"] if item["type"] == "conflicting_fact")
        response = client.post(f"/api/story-runtime/v1/migration-jobs/{job['migration_job_id']}/decisions", headers=auth_headers, json={"decisions": [{"conflict_id": conflict["conflict_id"], "decision": "quarantine", "note": "keep unresolved source outside authority"}]})
        assert response.status_code == 200
        job = _post(client, auth_headers, job["migration_job_id"], "pause")
        assert job["current_stage"] == "PAUSED"
        job = _post(client, auth_headers, job["migration_job_id"], "resume")
        assert job["current_stage"] == "READY"
        assert job["decisions"][conflict["conflict_id"]]["decision"] == "quarantine"


def test_verified_snapshot_restores_existing_target_before_cutover(app, auth_headers, tmp_path):
    source = tmp_path / "rollback-source"
    _write_source(source)
    for chapter in (source / "chapters").glob("*.md"):
        chapter.unlink()
    write_app = _write_enabled_app(app)
    with write_app.state.database.connect() as conn:
        before = dict(conn.execute("SELECT revision,latest_chapter,authority_mode FROM projects WHERE project_id='lighthouse-fixture'").fetchone())
        before_entities = conn.execute("SELECT COUNT(*) FROM entities WHERE project_id='lighthouse-fixture'").fetchone()[0]
    with TestClient(write_app) as client:
        job = _create(client, auth_headers, source, "lighthouse-fixture")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
        job = _post(client, auth_headers, job["migration_job_id"], "snapshot")
        assert job["target_snapshot"]["kind"] == "sqlite-backup"
        job = _post(client, auth_headers, job["migration_job_id"], "import")
        job = _post(client, auth_headers, job["migration_job_id"], "rollback")
        assert job["current_stage"] == "ROLLED_BACK"
    with write_app.state.database.connect() as conn:
        after = dict(conn.execute("SELECT revision,latest_chapter,authority_mode FROM projects WHERE project_id='lighthouse-fixture'").fetchone())
        after_entities = conn.execute("SELECT COUNT(*) FROM entities WHERE project_id='lighthouse-fixture'").fetchone()[0]
    assert after == before
    assert after_entities == before_entities


def test_selected_chapter_candidate_controls_imported_body(app, auth_headers, tmp_path):
    source = tmp_path / "chapter-choice"
    _write_source(source)
    alternate = "# Alternate\n\nSelected body"
    alternate_path = source / "chapters" / "chapter-1.txt"
    alternate_path.write_text(alternate, encoding="utf-8")
    expected = hashlib.sha256(alternate_path.read_bytes().decode("utf-8").strip().encode("utf-8")).hexdigest()
    write_app = _write_enabled_app(app)
    with TestClient(write_app) as client:
        job = _create(client, auth_headers, source, "chapter-choice-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
        conflict = next(item for item in job["conflicts"] if item["type"] == "chapter_body_mismatch")
        candidate = next(item["candidate_id"] for item in conflict["candidates"] if item["value"] == expected)
        response = client.post(f"/api/story-runtime/v1/migration-jobs/{job['migration_job_id']}/decisions", headers=auth_headers, json={"decisions": [{"conflict_id": conflict["conflict_id"], "decision": "choose_candidate", "candidate_id": candidate}]})
        assert response.status_code == 200, response.text
        job = _post(client, auth_headers, job["migration_job_id"], "snapshot")
        job = _post(client, auth_headers, job["migration_job_id"], "import")
        chapter = client.get("/api/story-runtime/v1/projects/chapter-choice-target/chapters/1", headers=auth_headers)
        assert chapter.status_code == 200, chapter.text
        assert chapter.json()["body_sha256"] == expected


def test_import_interrupt_resumes_from_batch_checkpoint_without_duplicates(app, auth_headers, tmp_path, monkeypatch):
    source = tmp_path / "checkpoint-source"
    (source / "chapters").mkdir(parents=True)
    (source / "inkos.json").write_text('{"version":"1.7.0"}', encoding="utf-8")
    for number in range(1, 102):
        (source / "chapters" / f"Ch{number:04d}.md").write_text(f"# Chapter {number}\n\nBody {number}", encoding="utf-8")
    write_app = _write_enabled_app(app)
    service = write_app.state.migration_jobs
    original = service._append_checkpoint
    interrupted = False

    def pause_after_first(job_id: str, checkpoint: dict):
        nonlocal interrupted
        original(job_id, checkpoint)
        if not interrupted:
            interrupted = True
            with service.database.connect() as conn:
                conn.execute("UPDATE migration_jobs SET current_stage='PAUSED',resume_stage='IMPORTING' WHERE job_id=?", (job_id,))

    monkeypatch.setattr(service, "_append_checkpoint", pause_after_first)
    with TestClient(write_app) as client:
        job = _create(client, auth_headers, source, "checkpoint-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
        job = _post(client, auth_headers, job["migration_job_id"], "snapshot")
        job = _post(client, auth_headers, job["migration_job_id"], "import")
        assert job["current_stage"] == "PAUSED"
        first_count = sum(1 for checkpoint in job["checkpoints"] if checkpoint.get("stage") == "IMPORTING")
        assert first_count == 1
        monkeypatch.setattr(service, "_append_checkpoint", original)
        job = _post(client, auth_headers, job["migration_job_id"], "resume")
        assert job["current_stage"] == "IMPORTING"
        job = _post(client, auth_headers, job["migration_job_id"], "import")
        assert job["current_stage"] == "VERIFYING"
    with service.database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chapter_commits WHERE project_id='checkpoint-target'").fetchone()[0] == 101
        assert conn.execute("SELECT COUNT(*) FROM migration_import_ledger WHERE job_id=? AND item_kind='chapters'", (job["migration_job_id"],)).fetchone()[0] == 101


def test_verify_detects_projection_drift_with_independent_replay(app, auth_headers, tmp_path):
    source = tmp_path / "replay-drift"
    _write_source(source)
    write_app = _write_enabled_app(app)
    with TestClient(write_app) as client:
        job = _create(client, auth_headers, source, "replay-drift-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
        job = _post(client, auth_headers, job["migration_job_id"], "snapshot")
        job = _post(client, auth_headers, job["migration_job_id"], "import")
        with write_app.state.database.connect() as conn:
            conn.execute("UPDATE entities SET attributes_json='{}' WHERE project_id='replay-drift-target'")
        job = _post(client, auth_headers, job["migration_job_id"], "verify")
    assert job["current_stage"] == "FAILED"
    assert job["verification"]["replay_matched"] is False
    assert job["verification"]["replay_hash"] != job["verification"]["projection_hash"]


def test_source_checksum_drift_blocks_import_without_target_writes(app, auth_headers, tmp_path):
    source = tmp_path / "source-drift"
    _write_source(source)
    write_app = _write_enabled_app(app)
    with TestClient(write_app) as client:
        job = _create(client, auth_headers, source, "source-drift-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
        job = _post(client, auth_headers, job["migration_job_id"], "snapshot")
        (source / "chapters" / "Ch001.md").write_text("changed after scan", encoding="utf-8")
        response = client.post(f"/api/story-runtime/v1/migration-jobs/{job['migration_job_id']}/import", headers=auth_headers, json={"actor": "pytest"})
        assert response.status_code == 409
        assert response.json()["code"] == "SOURCE_CHANGED_AFTER_SCAN"
    with write_app.state.database.connect() as conn:
        assert conn.execute("SELECT 1 FROM projects WHERE project_id='source-drift-target'").fetchone() is None


def test_zip_slip_entry_is_reported_without_extraction(app, auth_headers, tmp_path):
    source = tmp_path / "zip-source"
    source.mkdir()
    (source / "inkos.json").write_text('{"version":"1.7.0"}', encoding="utf-8")
    with zipfile.ZipFile(source / "legacy.zip", "w") as archive:
        archive.writestr("../outside.json", '{"escape":true}')
    with TestClient(app) as client:
        job = _create(client, auth_headers, source, "zip-target")
        job = _post(client, auth_headers, job["migration_job_id"], "scan")
    archive_item = next(item for item in job["source_checksum_manifest"] if item["path"] == "legacy.zip")
    assert archive_item["parse_status"] == "error"
    assert job["current_stage"] == "AWAITING_DECISIONS"
    assert not (tmp_path / "outside.json").exists()
