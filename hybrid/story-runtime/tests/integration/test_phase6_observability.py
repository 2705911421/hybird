from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient


def _seed(database):
    now = datetime.now(timezone.utc).isoformat()
    with database.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE projects SET authority_mode='runtime' WHERE project_id='lighthouse-fixture'")
        for index in range(35):
            state = "FINALIZED" if index < 30 else "REJECTED"
            commit_id = f"00000000-0000-4000-8000-{index:012d}"
            conn.execute(
                "INSERT INTO chapter_commits(commit_id,project_id,chapter_number,request_id,idempotency_key,request_hash,expected_revision,resulting_revision,state,body_sha256,artifact_sha256,schema_version,created_at,updated_at,finalized_at,error_details_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (commit_id, "lighthouse-fixture", index + 1, f"request-{index}", f"idempotency-key-{index:04d}", "a" * 64,
                 index, index + 1 if state == "FINALIZED" else None, state, "b" * 64, "c" * 64,
                 "story-runtime/v1", now, f"2026-07-12T{index % 24:02d}:00:00+00:00", now if state == "FINALIZED" else None,
                 json.dumps({"message": "C:\\Users\\private-user\\story.db Authorization: Bearer secret-token"}) if state == "REJECTED" else "{}"),
            )
        for index in range(40):
            payload = {"summary": f"event {index}", "content": "private chapter"}
            if index == 39:
                payload["blob"] = "x" * 10_000
            conn.execute(
                "INSERT INTO story_events(project_id,event_id,event_type,subject,chapter_number,payload_json,evidence_json,confidence,aggregate_type,aggregate_id,schema_version,created_at,applied_revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("lighthouse-fixture", f"phase6-event-{index}", "FactChanged" if index % 2 else "TimelineAdvanced",
                 f"event {index}", (index % 5) + 1, json.dumps(payload), json.dumps([{"path": "C:\\Users\\private-user\\chapter.md"}]),
                 1.0, "fact", f"fact-{index}", "story-runtime/v1", now, index),
            )
        conn.execute(
            "INSERT INTO runtime_incidents(project_id,component,state,message,retryable,repair_action,created_at) VALUES (?,?,?,?,?,?,?)",
            ("lighthouse-fixture", "provider", "degraded", "api_key=sk-sensitive C:\\Users\\private-user\\story.db", 1, "retry", now),
        )
        conn.execute(
            "INSERT INTO outbox(project_id,topic,payload_json,status,retry_count,last_error,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            ("lighthouse-fixture", "search.index", json.dumps({"chapter_number": 1}), "failed", 1, "Bearer outbox-secret", now, now),
        )
        conn.commit()


def test_observability_requires_authorization(app):
    with TestClient(app) as client:
        response = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/overview")
    assert response.status_code == 401


def test_commit_pagination_filtering_and_cursor_invalidation(app, runtime, auth_headers):
    _, database, _, _ = runtime
    _seed(database)
    with TestClient(app) as client:
        first = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/commits?limit=10", headers=auth_headers)
        assert first.status_code == 200
        payload = first.json()
        assert len(payload["items"]) == 10
        assert payload["page"]["has_more"] is True
        cursor = payload["page"]["next_cursor"]
        second = client.get(f"/api/story-runtime/v1/projects/lighthouse-fixture/commits?limit=10&cursor={cursor}", headers=auth_headers)
        assert {item["commit_id"] for item in payload["items"]}.isdisjoint({item["commit_id"] for item in second.json()["items"]})
        filtered = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/commits?state=REJECTED", headers=auth_headers)
        assert all(item["state"] == "REJECTED" for item in filtered.json()["items"])
        invalidated = client.get(f"/api/story-runtime/v1/projects/lighthouse-fixture/commits?limit=10&state=FINALIZED&cursor={cursor}", headers=auth_headers)
        assert invalidated.status_code == 422
        assert invalidated.json()["code"] == "INVALID_CURSOR"


def test_event_payload_is_bounded_and_redacted(app, runtime, auth_headers):
    _, database, _, _ = runtime
    _seed(database)
    with TestClient(app) as client:
        response = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/events?limit=5&view=evidence", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    large = next(item for item in payload["items"] if item["payload_truncated"])
    assert large["payload_preview"] is None
    rendered = json.dumps(payload)
    assert "private chapter" not in rendered
    assert "private-user" not in rendered
    assert "[HOME]" in rendered


def test_overview_degraded_empty_and_configuration_do_not_leak_secrets(app, runtime, auth_headers):
    _, database, _, _ = runtime
    with TestClient(app) as client:
        empty = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/overview", headers=auth_headers)
        assert empty.status_code == 200
        assert empty.json()["active_prepares"] == 0
        _seed(database)
        overview = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/overview", headers=auth_headers)
        assert overview.json()["runtime_state"] in {"degraded", "recovery_required"}
        config = client.get("/api/story-runtime/v1/configuration/status", headers=auth_headers)
        assert config.json()["token_configured"] is True
        assert config.json()["secret_values_exposed"] is False
        assert "test-token" not in config.text
        report = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/diagnostics", headers=auth_headers)
        assert "sk-sensitive" not in report.text
        assert "private-user" not in report.text
        assert "Bearer outbox-secret" not in report.text
        for internal in ("chapter_commits", "story_events", "projection_checkpoints", "runtime_incidents"):
            assert internal not in report.text


def test_recovery_preview_confirmation_and_audit(app, runtime, auth_headers):
    _, database, _, _ = runtime
    _seed(database)
    with TestClient(app) as client:
        safe = client.post("/api/story-runtime/v1/projects/lighthouse-fixture/recovery-jobs/preview", headers=auth_headers, json={
            "operation": "rebuild_lexical_index", "parameters": {}, "actor": "test-user",
        })
        assert safe.status_code == 200
        assert safe.json()["requires_confirmation"] is False
        safe_done = client.post(f"/api/story-runtime/v1/projects/lighthouse-fixture/recovery-jobs/{safe.json()['job_id']}/execute", headers=auth_headers, json={"actor": "test-user"})
        assert safe_done.json()["state"] == "completed"

        risky = client.post("/api/story-runtime/v1/projects/lighthouse-fixture/recovery-jobs/preview", headers=auth_headers, json={
            "operation": "clear_retry_queue", "parameters": {}, "actor": "test-user",
        }).json()
        assert risky["requires_confirmation"] is True
        assert risky["confirmation_token"]
        denied = client.post(f"/api/story-runtime/v1/projects/lighthouse-fixture/recovery-jobs/{risky['job_id']}/execute", headers=auth_headers, json={"actor": "test-user"})
        assert denied.status_code == 409
        done = client.post(f"/api/story-runtime/v1/projects/lighthouse-fixture/recovery-jobs/{risky['job_id']}/execute", headers=auth_headers, json={"actor": "test-user", "confirmation_token": risky["confirmation_token"]})
        assert done.status_code == 200
        assert done.json()["state"] == "completed"
        assert [entry["action"] for entry in done.json()["audit_trail"]] == ["preview", "execute", "finish"]


def test_restore_snapshot_is_explicitly_blocked(app, auth_headers):
    with TestClient(app) as client:
        response = client.post("/api/story-runtime/v1/projects/lighthouse-fixture/recovery-jobs/preview", headers=auth_headers, json={
            "operation": "restore_snapshot", "parameters": {"snapshot_id": "missing"}, "actor": "test-user",
        })
    assert response.status_code == 200
    assert response.json()["state"] == "blocked"
    assert response.json()["requires_confirmation"] is True


def test_projection_replay_resolves_retryable_incident(app, runtime, auth_headers):
    _, database, _, _ = runtime
    _seed(database)
    with database.connect() as conn:
        conn.execute("UPDATE runtime_incidents SET component='timeline' WHERE project_id='lighthouse-fixture'")
        conn.execute("UPDATE projection_checkpoints SET status='retryable' WHERE project_id='lighthouse-fixture' AND projection_name='timeline'")
        conn.execute("UPDATE chapter_commits SET state='ABORTED' WHERE project_id='lighthouse-fixture' AND state='REJECTED'")
        conn.execute("UPDATE outbox SET status='done' WHERE project_id='lighthouse-fixture'")
    with TestClient(app) as client:
        preview = client.post("/api/story-runtime/v1/projects/lighthouse-fixture/recovery-jobs/preview", headers=auth_headers, json={
            "operation": "replay_core_projection", "parameters": {"projection_names": ["entities", "relationships", "facts", "timeline", "threads", "summaries"]}, "actor": "test-user",
        }).json()
        done = client.post(f"/api/story-runtime/v1/projects/lighthouse-fixture/recovery-jobs/{preview['job_id']}/execute", headers=auth_headers, json={"actor": "test-user", "confirmation_token": preview["confirmation_token"]})
        assert done.status_code == 200
        overview = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/overview", headers=auth_headers).json()
    assert overview["projection_health"] == "ready"
    assert overview["runtime_state"] == "healthy"
