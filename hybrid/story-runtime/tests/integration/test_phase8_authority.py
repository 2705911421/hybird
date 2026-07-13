from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from story_runtime.api import create_app
from story_runtime.config import RuntimeConfig


def _common(project_id: str, key: str, revision: int) -> dict:
    return {
        "request_id": str(uuid4()),
        "idempotency_key": key,
        "project_id": project_id,
        "schema_version": "story-runtime/v1",
        "expected_revision": revision,
    }


def test_typed_diff_is_the_only_studio_truth_mutation_chain(tmp_path):
    config = RuntimeConfig(database_path=tmp_path / "phase8.db", local_token="phase8-token", writes_enabled=True)
    headers = {"Authorization": "Bearer phase8-token"}
    project_id = "phase8-runtime-book"
    app = create_app(config)

    event = {
        "event_type": "entity.upsert",
        "subject": "char-ada",
        "aggregate_type": "entity",
        "aggregate_id": "char-ada",
        "payload": {"entity_type": "character", "canonical_name": "Ada", "attributes": {"role": "lead"}},
        "evidence": [{"artifact_id": "studio-typed-diff", "start": 0, "end": 3}],
    }
    command = {
        **_common(project_id, "phase8-typed-diff-0001", 0),
        "actor": "studio-user",
        "reason": "user changed character role",
        "events": [event],
    }

    with TestClient(app) as client:
        created = client.post("/api/story-runtime/v1/projects", headers=headers, json={
            "request_id": str(uuid4()), "idempotency_key": "phase8-create-project-0001",
            "project_id": project_id, "schema_version": "story-runtime/v1", "authority_mode": "runtime",
        })
        assert created.status_code == 200, created.text

        first = client.post("/api/story-runtime/v1/commands/typed-diff", headers=headers, json=command)
        assert first.status_code == 200, first.text
        assert first.json()["revision"] == 1
        assert first.json()["event_count"] == 1

        replayed = client.post("/api/story-runtime/v1/commands/typed-diff", headers=headers, json={
            **command, "request_id": str(uuid4()),
        })
        assert replayed.status_code == 200, replayed.text
        assert replayed.json()["replayed"] is True
        assert replayed.json()["revision"] == 1

        entity = client.get(f"/api/story-runtime/v1/projects/{project_id}/entities/char-ada", headers=headers)
        assert entity.status_code == 200, entity.text
        assert entity.json()["entity"]["attributes"]["role"] == "lead"

        stale = client.post("/api/story-runtime/v1/commands/typed-diff", headers=headers, json={
            **command, "request_id": str(uuid4()), "idempotency_key": "phase8-stale-command-0001",
        })
        assert stale.status_code == 409
        assert stale.json()["code"] == "REVISION_CONFLICT"

        forbidden = client.post("/api/story-runtime/v1/commands/typed-diff", headers=headers, json={
            **_common(project_id, "phase8-forbidden-command-01", 1),
            "actor": "studio-user", "reason": "attempt direct SQL", "events": [{
                **event, "payload": {**event["payload"], "sql": "DELETE FROM facts"},
            }],
        })
        assert forbidden.status_code == 409
        assert forbidden.json()["code"] == "FORBIDDEN_COMMAND_CAPABILITY"
