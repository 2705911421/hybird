from __future__ import annotations

import inspect

import pytest

from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.chapter_reads import ChapterReadService
from story_runtime.migration_jobs import LegacyMigrationService
from story_runtime.observability import ObservabilityService, RecoveryService
from story_runtime.operations import create_snapshot
from story_runtime.outbox import OutboxWorker
from story_runtime.reviews import ReviewService
from story_runtime.services import RuntimeServices


@pytest.mark.parametrize(("operation", "entry"), [
    ("prepare", ChapterCommitService.prepare),
    ("validate", ChapterCommitService.validate),
    ("review artifact validation", ReviewService.validate),
    ("human review decision", ReviewService.decision),
    ("revision-result validation", ReviewService.validate_revision),
    ("replay verify/projection repair", ChapterCommitService.replay),
    ("snapshot", create_snapshot),
    ("export", ChapterReadService.export_snapshot),
    ("index/read search", ChapterReadService.search),
    ("outbox", OutboxWorker.run),
    ("doctor", RuntimeServices.doctor),
    ("recovery audit/preview", RecoveryService.preview),
    ("recovery execution", RecoveryService.execute),
    ("migration scan", LegacyMigrationService.scan),
    ("migration dry-run", LegacyMigrationService.dry_run),
    ("UI/operator read", ObservabilityService.overview),
    ("future historical read boundary", RuntimeServices.entity),
])
def test_excluded_operation_has_no_revision_allocator_or_direct_pointer_write(operation, entry) -> None:
    source = inspect.getsource(entry)
    assert "revision_allocator" not in source, operation
    assert "ProjectRevisionAllocator" not in source, operation
    assert "UPDATE projects SET revision" not in source, operation
    assert "expected_revision + 1" not in source, operation
