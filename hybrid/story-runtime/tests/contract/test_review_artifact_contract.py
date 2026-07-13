import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from story_runtime.contracts import (
    ChapterReviewArtifact, HumanReviewDecision, RevisionPlan, RevisionResult, StateMutationProposal,
)


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "contracts/schemas/review-artifacts.json").read_text(encoding="utf-8"))
FIXTURE = json.loads((ROOT / "contracts/fixtures/review-artifacts-v1.json").read_text(encoding="utf-8"))
CASES = {
    "chapter_review": ChapterReviewArtifact,
    "state_proposal": StateMutationProposal,
    "revision_plan": RevisionPlan,
    "revision_result": RevisionResult,
    "human_decision": HumanReviewDecision,
}


@pytest.mark.contract
@pytest.mark.parametrize(("name", "model"), CASES.items())
def test_cross_language_review_fixtures_match_json_schema_and_pydantic(name, model):
    payload = FIXTURE[name]
    Draft202012Validator(SCHEMA).validate(payload)
    assert model.model_validate(payload).schema_version == "review-artifacts/v1"


@pytest.mark.contract
def test_review_contract_rejects_unknown_missing_invalid_enum_and_version():
    base = FIXTURE["chapter_review"]
    for changed in (
        {**base, "unknown": True},
        {key: value for key, value in base.items() if key != "artifact_id"},
        {**base, "recommended_action": "silently_commit"},
        {**base, "schema_version": "review-artifacts/v999"},
    ):
        with pytest.raises(ValidationError):
            ChapterReviewArtifact.model_validate(changed)
