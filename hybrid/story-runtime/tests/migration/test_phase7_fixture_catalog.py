from __future__ import annotations

import importlib.util
import time
from pathlib import Path

from story_runtime.contracts import CreateMigrationJobRequest, MigrationActionRequest
from story_runtime.migration_jobs import LegacyMigrationService


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "generate_phase7_fixtures.py"


def _builder():
    spec = importlib.util.spec_from_file_location("phase7_fixtures", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.build


def test_fixture_catalog_covers_phase7_attack_and_scale_cases(tmp_path):
    catalog = _builder()(tmp_path / "fixtures")
    expected = {
        "inkos-small", "inkos-large", "inkos-truth-conflict", "chapter-gap", "CJK-文件名-📚",
        "corrupt-json", "corrupt-sqlite", "alias-collision", "multi-volume", "windows-long-path",
        "webnovel-mismatch", "zip-slip", "million-char-synthetic", "symlink-attack",
    }
    assert expected <= set(catalog)


def test_million_character_fixture_scans_with_bounded_memory_contract(runtime, tmp_path):
    root = tmp_path / "fixtures"
    _builder()(root)
    config, database, _, _ = runtime
    service = LegacyMigrationService(database, config)
    job = service.create(CreateMigrationJobRequest(source_path=str(root / "million-char-synthetic"), target_project_id="million-target"))
    started = time.perf_counter()
    result = service.scan(job.migration_job_id, MigrationActionRequest(actor="performance-test"))
    elapsed = time.perf_counter() - started
    assert len(result.cir["chapters"]) == 100
    assert sum(item["size"] for item in result.source_checksum_manifest) >= 1_000_000
    assert elapsed < 15.0
