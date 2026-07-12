from story_runtime.contracts import QueryBudget, QueryContextRequest


def test_context_separates_authority_from_retrieval(runtime):
    _, _, _, services = runtime
    request = QueryContextRequest(
        request_id="d7db31dc-cc22-4788-b263-5787db9505bb",
        project_id="lighthouse-fixture", schema_version="story-runtime/v1", chapter_number=4,
        intent="harbor brass key ferry", entity_ids=["char-lin"],
        budget=QueryBudget(max_tokens=1024, max_items=20),
    )
    result = services.query_context(request)
    assert result.authoritative_facts
    assert result.retrieval_candidates
    assert all(item.trust == "untrusted_content" for item in result.retrieval_candidates)
    assert result.trace.budget_used <= 1024


def test_projection_failure_is_recoverable(runtime):
    _, _, repository, services = runtime
    repository.record_projection_failure("lighthouse-fixture", "summaries", "injected deterministic failure")
    status = services.project_status("lighthouse-fixture")
    assert status.projection_health["status"] == "degraded"
    assert status.projection_health["recoverable"] == "true"
    doctor = services.doctor("lighthouse-fixture")
    assert doctor.status == "warning"
    assert any(check.repair == "replay projection" for check in doctor.checks)
