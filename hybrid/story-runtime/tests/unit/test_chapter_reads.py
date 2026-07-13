from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest

from story_runtime.chapter_reads import ChapterReadService
from story_runtime.config import RuntimeConfig
from story_runtime.contracts import ChapterExportRequest
from story_runtime.database import Database
from story_runtime.errors import ConflictError, DatabaseUnavailableError


NOW = "2026-07-13T00:00:00+00:00"


def seeded_runtime(tmp_path):
    database = Database(RuntimeConfig(database_path=tmp_path / "chapter-reads.db", writes_enabled=True))
    database.migrations.migrate()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO projects(project_id,revision,phase,latest_chapter,schema_version,created_at,updated_at,authority_mode) VALUES ('runtime-book',7,'writing',3,'story-runtime/v1',?,?,'runtime')",
            (NOW, NOW),
        )
        for number, body, volume in ((1, "第一章。海港。", "v1"), (2, "第二章。钥匙。", "v1"), (3, "第三章。灯塔。", "v2")):
            commit_id = str(uuid4())
            body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            artifact_hash = hashlib.sha256(f"artifact-{number}".encode()).hexdigest()
            conn.execute(
                "INSERT INTO chapter_commits(commit_id,project_id,chapter_number,request_id,idempotency_key,request_hash,expected_revision,resulting_revision,state,body_sha256,artifact_sha256,schema_version,created_at,updated_at,finalized_at,error_details_json) VALUES (?,?,?,?,?,?,?,?,'FINALIZED',?,?,?,?,?,?, '{}')",
                (commit_id, "runtime-book", number, str(uuid4()), f"key-{number}", "hash", number - 1, number, body_hash, artifact_hash, "story-runtime/v1", NOW, NOW, NOW),
            )
            conn.execute(
                "INSERT INTO chapter_artifacts(commit_id,project_id,chapter_number,title,body_text,summary,outline_fulfillment_json,review_json,state_mutation_proposal_json,evidence_spans_json,events_json,schema_version,body_sha256,checksum,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (commit_id, "runtime-book", number, f"第{number}章", body, f"摘要{number}", f'{{"volume_id":"{volume}"}}', "{}", "{}", "[]", "[]", "story-runtime/v1", body_hash, artifact_hash, NOW),
            )
    return database, ChapterReadService(database)


def test_collection_paginates_at_fixed_revision_and_filters(tmp_path):
    database, service = seeded_runtime(tmp_path)
    first = service.collection("runtime-book", cursor=None, limit=2, from_chapter=None, to_chapter=None, volume_id=None, finalized_only=True)
    assert first.revision == 7
    assert first.total_count == 3
    assert first.latest_chapter == 3
    assert [item.chapter_number for item in first.items] == [1, 2]
    assert first.page.has_more is True

    second = service.collection("runtime-book", cursor=first.page.next_cursor, limit=2, from_chapter=None, to_chapter=None, volume_id=None, finalized_only=True)
    assert [item.chapter_number for item in second.items] == [3]
    assert second.page.has_more is False

    volume = service.collection("runtime-book", cursor=None, limit=10, from_chapter=2, to_chapter=3, volume_id="v1", finalized_only=True)
    assert [item.chapter_number for item in volume.items] == [2]

    with database.connect() as conn:
        conn.execute("UPDATE projects SET revision=8 WHERE project_id='runtime-book'")
    with pytest.raises(ConflictError, match="revision changed"):
        service.collection("runtime-book", cursor=first.page.next_cursor, limit=2, from_chapter=None, to_chapter=None, volume_id=None, finalized_only=True)


def test_aggregate_export_and_search_are_runtime_body_backed(tmp_path):
    _, service = seeded_runtime(tmp_path)
    aggregate = service.aggregate("runtime-book")
    assert aggregate.chapter_count == 3
    assert aggregate.latest_chapter == 3
    assert aggregate.total_characters == sum(map(len, ("第一章。海港。", "第二章。钥匙。", "第三章。灯塔。")))
    assert [(volume.volume_id, volume.chapter_count) for volume in aggregate.volumes] == [("v1", 2), ("v2", 1)]

    snapshot = service.export_snapshot("runtime-book", ChapterExportRequest(expected_revision=7))
    assert snapshot.revision == 7
    assert snapshot.chapter_count == 3
    assert [chapter.body for chapter in snapshot.chapters] == ["第一章。海港。", "第二章。钥匙。", "第三章。灯塔。"]
    assert len(snapshot.collection_sha256) == 64

    result = service.search("runtime-book", "钥匙", cursor=None, limit=10)
    assert result.revision == result.index_revision == 7
    assert result.stale is False
    assert [hit.chapter_number for hit in result.items] == [2]
    assert result.items[0].body == "第二章。钥匙。"


def test_export_rejects_revision_and_checksum_mismatch(tmp_path):
    database, service = seeded_runtime(tmp_path)
    with pytest.raises(ConflictError, match="does not match"):
        service.export_snapshot("runtime-book", ChapterExportRequest(expected_revision=6))
    with database.connect() as conn:
        conn.execute("UPDATE chapter_artifacts SET body_text='tampered' WHERE project_id='runtime-book' AND chapter_number=2")
    with pytest.raises(DatabaseUnavailableError, match="checksum"):
        service.export_snapshot("runtime-book", ChapterExportRequest(expected_revision=7))


def test_non_finalized_collection_is_rejected(tmp_path):
    _, service = seeded_runtime(tmp_path)
    with pytest.raises(ConflictError, match="only expose finalized"):
        service.collection("runtime-book", cursor=None, limit=10, from_chapter=None, to_chapter=None, volume_id=None, finalized_only=False)
