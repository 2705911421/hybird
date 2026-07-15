from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT.parent / "contracts"


def validate_schema(name: str, instance) -> None:
    schema_path = CONTRACTS / "schemas" / name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    def retrieve(uri: str) -> Resource:
        referenced = CONTRACTS / "schemas" / uri.rsplit("/", 1)[-1]
        return Resource.from_contents(json.loads(referenced.read_text(encoding="utf-8")))
    registry = Registry(retrieve=retrieve).with_resource(schema["$id"], Resource.from_contents(schema))
    Draft202012Validator(schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(instance)


@pytest.mark.contract
def test_approved_operations_are_implemented(app):
    approved = yaml.safe_load((CONTRACTS / "story-runtime.openapi.yaml").read_text(encoding="utf-8"))
    approved_operations = {op["operationId"] for path in approved["paths"].values() for method, op in path.items() if method in {"get", "post"}}
    generated = app.openapi()
    implemented = {op["operationId"] for path in generated["paths"].values() for op in path.values() if isinstance(op, dict) and "operationId" in op}
    assert approved_operations == implemented
    assert {"/api/story-runtime/v1" + path for path in approved["paths"]} == set(generated["paths"])
    rendered = json.dumps(generated, sort_keys=True)
    for private_name in ("story_events", "projection_checkpoints", "idempotency_ledger", "runtime_incidents"):
        assert private_name not in rendered


@pytest.mark.contract
def test_runtime_has_no_host_or_llm_hard_dependency():
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src/story_runtime").glob("*.py"))
    for forbidden in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", ".claude", "import openai", "import anthropic", "import inkos"):
        assert forbidden.casefold() not in source.casefold()


@pytest.mark.contract
def test_read_responses_validate_against_approved_json_schemas(app, auth_headers):
    with TestClient(app) as client:
        health = client.get("/api/story-runtime/v1/health").json()
        status = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/status", headers=auth_headers).json()
    validate_schema("health-response.json", health)
    validate_schema("project-status-response.json", status)


@pytest.mark.contract
def test_inline_read_responses_match_approved_components(app, auth_headers):
    approved = yaml.safe_load((CONTRACTS / "story-runtime.openapi.yaml").read_text(encoding="utf-8"))
    schemas = approved["components"]["schemas"]
    query = {
        "request_id": "2827cc6f-4cbb-451d-8a34-1b849a44cff5", "project_id": "lighthouse-fixture",
        "schema_version": "story-runtime/v1", "chapter_number": 4, "expected_revision": 7,
        "intent": "harbor brass key ferry",
        "budget": {"max_tokens": 1024, "max_items": 20},
    }
    with TestClient(app) as client:
        context = client.post("/api/story-runtime/v1/queries/context", headers=auth_headers, json=query).json()
        entity = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/entities/char-lin", headers=auth_headers).json()
        doctor = client.get("/api/story-runtime/v1/projects/lighthouse-fixture/doctor", headers=auth_headers).json()
    openapi_schema = {"components": {"schemas": schemas}, "$ref": "#/components/schemas/ContextQueryResult"}
    Draft202012Validator(openapi_schema).validate(context)
    Draft202012Validator(schemas["EntityResult"]).validate(entity)
    Draft202012Validator(schemas["DoctorResult"]).validate(doctor)


@pytest.mark.contract
def test_all_write_models_are_closed_and_reject_extra_fields(app, auth_headers):
    body = {
        "request_id": "a8e05ee7-84d1-4cb7-bfe8-d098e67a62a6", "idempotency_key": "write-disabled-key-0001",
        "project_id": "lighthouse-fixture", "schema_version": "story-runtime/v1", "expected_revision": 7,
        "chapter_number": 4, "intent": {}, "base_context_revision": 7, "unexpected": True
    }
    with TestClient(app) as client:
        response = client.post("/api/story-runtime/v1/chapters/prepare", headers=auth_headers, json=body)
    assert response.status_code == 422
    validate_schema("error-response.json", response.json())
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.contract
def test_every_approved_write_route_is_present_but_disabled(app, auth_headers):
    common = {
        "request_id": "a8e05ee7-84d1-4cb7-bfe8-d098e67a62a6", "idempotency_key": "write-disabled-key-0001",
        "project_id": "lighthouse-fixture", "schema_version": "story-runtime/v1", "expected_revision": 7,
    }
    artifacts = {
        "chapter_number": 4, "title": "Test", "body": "deterministic body",
        "body_sha256": hashlib.sha256(b"deterministic body").hexdigest(), "events": [], "outline_fulfillment": {},
    }
    samples = {
        "/chapters/prepare": {**common, "chapter_number": 4, "intent": {}, "base_context_revision": 7},
        "/chapters/validate": {**common, "prepare_id": "44ba8279-bf5a-4ac9-9388-c829b85e691d", "artifacts": artifacts},
        "/chapters/commit": {**common, "prepare_id": "44ba8279-bf5a-4ac9-9388-c829b85e691d", "validation_token": "deterministic-token", "artifacts": artifacts},
        "/events/append": {**common, "events": [{"event_id": "e1", "event_type": "test", "subject": "x", "payload": {}, "evidence": []}], "reason": "contract test"},
        "/projections/replay": {**common, "projection_names": ["summaries"], "from_event_sequence": 0, "verify_only": True},
        "/projects/migrate": {**common, "source_kind": "story-runtime-snapshot", "source_path": "fixture.json", "target_schema_version": "story-runtime/v1", "dry_run": True},
        "/projects/export-snapshot": {**common, "format": "json", "include_chapter_bodies": False},
    }
    with TestClient(app) as client:
        for path, body in samples.items():
            response = client.post("/api/story-runtime/v1" + path, headers=auth_headers, json=body)
            assert response.status_code == 403, (path, response.text)
            payload = response.json()
            validate_schema("error-response.json", payload)
            assert payload["code"] == "WRITE_FEATURE_DISABLED"
