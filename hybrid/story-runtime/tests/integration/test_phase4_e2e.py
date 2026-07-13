from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient

from story_runtime.api import create_app
from story_runtime.config import RuntimeConfig


def common(project_id: str, key: str, revision: int) -> dict:
    return {
        "request_id": str(uuid4()), "idempotency_key": key, "project_id": project_id,
        "schema_version": "story-runtime/v1", "expected_revision": revision,
    }


def artifact(chapter: int, body: str, *, has_key: bool, resolve: bool = False) -> dict:
    evidence = [{"artifact_id": "chapter-body", "start": 0, "end": len(body)}]
    return {
        "chapter_number": chapter, "title": f"第{chapter}章", "body": body,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "summary": "林舟拾起钥匙。" if has_key else "林舟交出钥匙。",
        "outline_fulfillment": {"planned_node_ids": [], "covered_node_ids": [], "missed_node_ids": []},
        "review": {"passed": True, "issues": []}, "state_mutation_proposal": {"typed": True},
        "evidence_spans": evidence,
        "events": [
            {"event_type": "entity.upsert", "subject": "char-lin", "aggregate_type": "entity", "aggregate_id": "char-lin", "payload": {"entity_type": "character", "canonical_name": "林舟", "attributes": {"has_key": has_key}}, "evidence": evidence},
            {"event_type": "fact.upsert", "subject": "char-lin", "aggregate_type": "fact", "aggregate_id": "lin-key", "payload": {"predicate": "inventory.has_key", "value": has_key}, "evidence": evidence},
            {"event_type": "thread.resolve" if resolve else "thread.upsert", "subject": "key-thread", "aggregate_type": "narrative_thread", "aggregate_id": "key-thread", "payload": {"title": "钥匙来源", "status": "resolved" if resolve else "open", "introduced_chapter": 1, "resolved_chapter": chapter if resolve else None}, "evidence": evidence},
        ],
    }


def submit(client: TestClient, headers: dict[str, str], project_id: str, chapter: int, revision: int, artifacts: dict) -> dict:
    key = f"chapter-{chapter}-deterministic-key"
    prepared = client.post("/api/story-runtime/v1/chapters/prepare", headers=headers, json={
        **common(project_id, key, revision), "chapter_number": chapter,
        "intent": {"goal": f"chapter {chapter}"}, "base_context_revision": revision,
    })
    assert prepared.status_code == 200, prepared.text
    prepare_id = prepared.json()["prepare_id"]
    validated = client.post("/api/story-runtime/v1/chapters/validate", headers=headers, json={
        **common(project_id, key, revision), "prepare_id": prepare_id, "artifacts": artifacts,
    })
    assert validated.status_code == 200, validated.text
    assert not [issue for issue in validated.json()["issues"] if issue["severity"] == "blocking"]
    committed = client.post("/api/story-runtime/v1/chapters/commit", headers=headers, json={
        **common(project_id, key, revision), "prepare_id": prepare_id,
        "validation_token": validated.json()["validation_token"], "artifacts": artifacts,
    })
    assert committed.status_code == 200, committed.text
    return committed.json()


def test_two_chapter_restart_and_projection_replay(tmp_path):
    config = RuntimeConfig(database_path=tmp_path / "phase4-e2e.db", local_token="phase4-token", writes_enabled=True)
    headers = {"Authorization": "Bearer phase4-token"}
    project_id = "phase4-e2e-book"
    app = create_app(config)
    with TestClient(app) as client:
        created = client.post("/api/story-runtime/v1/projects", headers=headers, json={
            "request_id": str(uuid4()), "idempotency_key": "create-phase4-e2e-book", "project_id": project_id,
            "schema_version": "story-runtime/v1", "authority_mode": "runtime",
        })
        assert created.status_code == 200
        first = submit(client, headers, project_id, 1, 0, artifact(1, "第一章：林舟拾起钥匙。", has_key=True))
        second = submit(client, headers, project_id, 2, 1, artifact(2, "第二章：林舟交出钥匙。", has_key=False, resolve=True))
        assert first["resulting_revision"] == 1
        assert second["resulting_revision"] == 2

    restarted = create_app(config)
    with TestClient(restarted) as client:
        status = client.get(f"/api/story-runtime/v1/projects/{project_id}/status", headers=headers)
        assert status.json()["revision"] == 2
        assert status.json()["latest_chapter"] == 2
        entity = client.get(f"/api/story-runtime/v1/projects/{project_id}/entities/char-lin?include_history=true", headers=headers)
        assert entity.json()["entity"]["attributes"]["has_key"] is False
        replay = client.post("/api/story-runtime/v1/projections/replay", headers=headers, json={
            **common(project_id, "replay-all-projections-key", 2),
            "projection_names": ["entities", "relationships", "facts", "timeline", "threads", "summaries"],
            "from_event_sequence": 0, "to_event_sequence": None, "target_revision": 2,
            "verify_only": True, "expected_hash": second["projection_hash"],
        })
        assert replay.status_code == 200, replay.text
        assert replay.json()["matched"] is True
        assert replay.json()["resulting_hash"] == second["projection_hash"]
