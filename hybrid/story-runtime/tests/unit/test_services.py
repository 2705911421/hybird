from story_runtime.contracts import ContextLayers, QueryBudget, QueryContextRequest
import json


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
    assert result.layers.hard_constraints
    assert result.layers.recent_narrative
    assert any(item.predicate == "timeline.current" for item in result.layers.hard_constraints)
    assert any(item.predicate == "chapter.excerpt" for item in result.layers.recent_narrative)
    assert all(item.source.id and item.updated_at and 0 <= item.confidence <= 1 for layer in (
        result.layers.hard_constraints,
        result.layers.plot_commitments,
        result.layers.relevant_memory,
        result.layers.recent_narrative,
        result.layers.style_guidance,
    ) for item in layer)


def test_conflicting_authoritative_facts_are_reported_without_resolution(runtime):
    _, database, _, services = runtime
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO facts VALUES (?,?,?,?,?,?,?)",
            ("lighthouse-fixture", "fact-ren-dead", "char-ren", "character.profile", json.dumps({"status": "dead"}), 7, None),
        )
        conn.commit()
    request = QueryContextRequest(
        request_id="744176f4-c9ab-4ac5-855f-3559218fdbda",
        project_id="lighthouse-fixture", schema_version="story-runtime/v1", chapter_number=4,
        intent="Ren character status", entity_ids=["char-ren"],
        budget=QueryBudget(max_tokens=2048, max_items=50),
    )
    result = services.query_context(request)
    assert result.conflicts
    conflict = next(item for item in result.conflicts if item.subject == "char-ren" and item.predicate == "character.profile")
    assert set(conflict.item_ids) == {"fact-character-ren", "fact-ren-dead"}
    assert "no value was selected" in conflict.message


def test_long_novel_context_is_budgeted_by_importance_not_full_database(runtime):
    _, database, _, services = runtime
    with database.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for index in range(2_000):
            conn.execute(
                "INSERT INTO facts VALUES (?,?,?,?,?,?,?)",
                ("lighthouse-fixture", f"long-fact-{index:04d}", f"archive-{index}", "memory.detail", json.dumps({"harbor": "noise", "index": index}), 7, None),
            )
        conn.commit()
    request = QueryContextRequest(
        request_id="f82b15f2-58c1-4505-9710-8424e692504d",
        project_id="lighthouse-fixture", schema_version="story-runtime/v1", chapter_number=2001,
        intent="harbor archive", budget=QueryBudget(max_tokens=1024, max_items=30),
    )
    result = services.query_context(request)
    layered = [item for name in ContextLayers.model_fields for item in getattr(result.layers, name)]
    assert len(layered) <= 30
    assert result.trace.budget_used <= 1024
    assert len(layered) < 2_000
    assert any(item.importance >= 90 for item in layered)
    assert any(item.content.startswith("Compressed reference:") for item in layered)


def test_projection_failure_is_recoverable(runtime):
    _, _, repository, services = runtime
    repository.record_projection_failure("lighthouse-fixture", "summaries", "injected deterministic failure")
    status = services.project_status("lighthouse-fixture")
    assert status.projection_health["status"] == "degraded"
    assert status.projection_health["recoverable"] == "true"
    doctor = services.doctor("lighthouse-fixture")
    assert doctor.status == "warning"
    assert any(check.repair == "replay projection" for check in doctor.checks)
