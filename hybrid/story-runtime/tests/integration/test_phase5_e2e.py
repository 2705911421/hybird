from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient

from story_runtime.api import create_app
from story_runtime.config import RuntimeConfig


BASE = "/api/story-runtime/v1"
HEADERS = {"Authorization": "Bearer test-token"}


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_context(project_id: str, revision: int, key: str) -> dict:
    return {
        "request_id": str(uuid4()), "idempotency_key": key, "project_id": project_id,
        "schema_version": "story-runtime/v1", "expected_revision": revision,
    }


def review_artifact(project_id: str, body: str, *, blocking: bool) -> dict:
    findings = []
    if blocking:
        findings.append({
            "finding_id": "finding-blocking", "category": "continuity", "severity": "major", "blocking": True,
            "message": "Location contradicts authority", "rationale": "The transition is absent.",
            "evidence_spans": [{
                "artifact": "chapter_body", "start_offset": 0, "end_offset": 1,
                "quoted_hash": sha(body[0:1]), "locator": "chapter:1:0-1", "explanation": "Subject mention", "status": "current",
            }],
            "affected_entities": ["char-a"], "affected_facts": ["character.location"],
            "proposed_resolution": "Add the transition.", "confidence": 1, "source": "runtime_validator",
            "deterministic_rule_id": "FACT.LOCATION", "supersedes": [], "status": "open",
        })
    return {
        "artifact_id": "review-blocked" if blocking else "review-clear", "schema_version": "review-artifacts/v1",
        "project_id": project_id, "chapter_number": 1, "source_revision": 0, "body_sha256": sha(body),
        "reviewer_kind": "runtime_validator", "reviewer_version": "1", "generated_at": "2026-07-12T00:00:00Z",
        "dimensions": {"continuity": 100}, "findings": findings, "summary": "blocked" if blocking else "clear",
        "recommended_action": "human_review" if blocking else "approve", "model_metadata": {},
        "prompt_template_version": "deterministic/v1",
    }


def state_proposal(project_id: str, body: str) -> dict:
    return {
        "proposal_id": "proposal-1", "schema_version": "review-artifacts/v1", "project_id": project_id,
        "chapter_number": 1, "source_revision": 0, "body_sha256": sha(body), "entity_mutations": [],
        "relationship_mutations": [], "fact_mutations": [], "timeline_events": [], "narrative_thread_mutations": [],
        "foreshadowing_mutations": [], "evidence": [], "confidence": 1, "extraction_source": "observer",
    }


def test_typed_review_blocks_commit_until_idempotent_human_decision(tmp_path):
    app = create_app(RuntimeConfig(
        database_path=tmp_path / "phase5-e2e.db", local_token="test-token", writes_enabled=True,
        unified_review_enabled=True,
    ))
    project_id = "phase5-e2e"
    body = "甲在港口发现钥匙。"
    review = review_artifact(project_id, body, blocking=True)
    artifacts = {
        "chapter_number": 1, "title": "钥匙", "body": body, "body_sha256": sha(body), "summary": "甲发现钥匙。",
        "events": [{
            "event_type": "entity.upsert", "subject": "char-a", "aggregate_type": "entity", "aggregate_id": "char-a",
            "payload": {"entity_type": "character", "canonical_name": "甲"},
            "evidence": [{"artifact_id": "chapter-body", "start": 0, "end": 1}], "confidence": 1,
        }],
        "outline_fulfillment": {"planned_node_ids": [], "covered_node_ids": [], "missed_node_ids": []},
        "review": review, "state_mutation_proposal": state_proposal(project_id, body),
        "evidence_spans": [{"artifact_id": "chapter-body", "start": 0, "end": 1}],
    }
    with TestClient(app) as client:
        created = client.post(f"{BASE}/projects", headers=HEADERS, json={
            "request_id": str(uuid4()), "idempotency_key": "create-phase5-project", "project_id": project_id,
            "schema_version": "story-runtime/v1", "authority_mode": "runtime",
        })
        assert created.status_code == 200

        review_response = client.post(f"{BASE}/reviews/validate", headers=HEADERS, json={
            **write_context(project_id, 0, "validate-phase5-review"), "chapter_number": 1, "body": body, "artifacts": [review],
        })
        assert review_response.status_code == 200
        assert review_response.json()["status"]["status"] == "blocked"

        prepare = client.post(f"{BASE}/chapters/prepare", headers=HEADERS, json={
            **write_context(project_id, 0, "phase5-chapter-key"), "chapter_number": 1, "intent": {}, "base_context_revision": 0,
        })
        assert prepare.status_code == 200
        validate = client.post(f"{BASE}/chapters/validate", headers=HEADERS, json={
            **write_context(project_id, 0, "phase5-chapter-key"), "prepare_id": prepare.json()["prepare_id"],
            "artifacts": artifacts, "validation_profile": "strict",
        })
        assert validate.status_code == 200 and validate.json()["state"] == "VALIDATED"
        commit_payload = {
            **write_context(project_id, 0, "phase5-chapter-key"), "prepare_id": prepare.json()["prepare_id"],
            "validation_token": validate.json()["validation_token"], "artifacts": artifacts,
        }
        blocked = client.post(f"{BASE}/chapters/commit", headers=HEADERS, json=commit_payload)
        assert blocked.status_code == 409 and blocked.json()["code"] == "REVIEW_BLOCKED"

        decision_payload = {
            **write_context(project_id, 0, "phase5-human-decision"),
            "decision": {
                "decision_id": "decision-1", "schema_version": "review-artifacts/v1", "project_id": project_id,
                "chapter_number": 1, "reviewer": "editor", "decision": "approve",
                "finding_decisions": {"finding-blocking": "accept"}, "comment": "Confirmed intentional transition.",
                "timestamp": "2026-07-12T00:01:00Z", "source_revision": 0,
            },
        }
        first_decision = client.post(f"{BASE}/reviews/decisions", headers=HEADERS, json=decision_payload)
        replay_decision = client.post(f"{BASE}/reviews/decisions", headers=HEADERS, json={**decision_payload, "request_id": str(uuid4())})
        assert first_decision.status_code == replay_decision.status_code == 200
        assert first_decision.json() == replay_decision.json()

        committed = client.post(f"{BASE}/chapters/commit", headers=HEADERS, json={**commit_payload, "request_id": str(uuid4())})
        assert committed.status_code == 200
        assert committed.json()["state"] == "FINALIZED"
        assert committed.json()["resulting_revision"] == 1
