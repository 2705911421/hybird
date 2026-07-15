from fastapi.testclient import TestClient
from story_runtime.api import create_app
from story_runtime.config import RuntimeConfig


def test_read_only_http_runtime(app, auth_headers):
    with TestClient(app) as client:
        health = client.get("/api/story-runtime/v1/health")
        assert health.status_code == 200
        assert health.json()["database"] == "ready"
        status = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/status", headers=auth_headers)
        assert status.status_code == 200
        assert status.json()["revision"] == 7
        entity = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/entities/char-lin?include_history=true", headers=auth_headers)
        assert entity.json()["entity"]["canonical_name"] == "Lin Yue"
        historical = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/entities/char-lin?at_revision=1", headers=auth_headers)
        assert historical.status_code == 409
        assert historical.json()["code"] == "HISTORY_NOT_IMPLEMENTED"
        doctor = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/doctor?deep=true", headers=auth_headers)
        assert doctor.json()["status"] == "warning"
        assert any(check["code"] == "manifest.bootstrap_required" for check in doctor.json()["checks"])


def test_context_query_and_rag_over_http(app, auth_headers):
    body = {
        "request_id": "2827cc6f-4cbb-451d-8a34-1b849a44cff5", "project_id": "lighthouse-fixture",
        "schema_version": "story-runtime/v1", "chapter_number": 4, "intent": "harbor brass key ferry",
        "entity_ids": ["char-lin"], "budget": {"max_tokens": 1024, "max_items": 20},
        "include_retrieval_candidates": True,
    }
    with TestClient(app) as client:
        response = client.post("/api/story-runtime/v1/queries/context", headers=auth_headers, json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["authoritative_facts"]
    assert payload["retrieval_candidates"]


def test_write_endpoint_is_feature_flag_closed(app, auth_headers):
    body = {
        "request_id": "a8e05ee7-84d1-4cb7-bfe8-d098e67a62a6", "idempotency_key": "write-disabled-key-0001",
        "project_id": "lighthouse-fixture", "schema_version": "story-runtime/v1", "expected_revision": 7,
        "chapter_number": 4, "intent": {}, "base_context_revision": 7,
    }
    with TestClient(app) as client:
        response = client.post("/api/story-runtime/v1/chapters/prepare", headers=auth_headers, json=body)
    assert response.status_code == 403
    assert response.json()["code"] == "WRITE_FEATURE_DISABLED"


def test_recovery_and_outbox_routes_require_operator_scope(tmp_path, auth_headers):
    app = create_app(RuntimeConfig(
        database_path=tmp_path / "operator-api.db", local_token="test-token", writes_enabled=True,
    ))
    with TestClient(app) as client:
        outbox = client.post("/api/story-runtime/v1/outbox/run", headers=auth_headers, json={
            "request_id": "2827cc6f-4cbb-451d-8a34-1b849a44cff5", "limit": 10,
            "retry_failed": True,
        })
        recovery = client.post("/api/story-runtime/v1/commits/recover", headers=auth_headers, json={
            "request_id": "2827cc6f-4cbb-451d-8a34-1b849a44cff5", "project_id": "missing",
            "commit_id": "2827cc6f-4cbb-451d-8a34-1b849a44cff6",
            "idempotency_key": "operator-recovery-key-01", "action": "abort", "reason": "test",
        })
    assert outbox.status_code == 409
    assert outbox.json()["code"] == "OPERATOR_SCOPE_REQUIRED"
    assert recovery.status_code == 409
    assert recovery.json()["code"] == "OPERATOR_SCOPE_REQUIRED"
