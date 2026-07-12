from story_runtime.contracts import QueryBudget, QueryContextRequest


def test_fixture_initialization_is_idempotent(runtime, fixture_data):
    _, _, repository, _ = runtime
    result = repository.initialize_fixture(fixture_data, "test-fixture-bootstrap")
    assert result["replayed"] is True
    assert repository.counts("lighthouse-fixture") == {
        "characters": 2, "relationships": 1, "events": 2,
        "timeline": 2, "narrative_threads": 1, "chapter_summaries": 3,
    }


def test_exact_entity_query(runtime):
    _, _, _, services = runtime
    result = services.entity("lighthouse-fixture", "char-lin", include_history=True)
    assert result.entity.canonical_name == "Lin Yue"
    assert result.entity.attributes["role"] == "lighthouse keeper"
    assert result.entity.history[0]["revision"] == 3


def test_all_required_story_views_are_authoritative_facts(runtime):
    _, _, repository, _ = runtime
    facts = repository.query_facts("lighthouse-fixture", "", [], 100)
    predicates = {fact.predicate for fact in facts}
    assert {
        "character.profile", "relationship.siblings", "event.beacon_failed",
        "timeline.sequence", "narrative_thread.open", "chapter.summary",
    } <= predicates


def test_deterministic_rag_query(runtime):
    _, _, repository, _ = runtime
    first = repository.rag_search("lighthouse-fixture", "harbor brass key", 5)
    second = repository.rag_search("lighthouse-fixture", "harbor brass key", 5)
    assert first == second
    assert first[0].trust == "untrusted_content"
    assert "brass key" in first[0].text
