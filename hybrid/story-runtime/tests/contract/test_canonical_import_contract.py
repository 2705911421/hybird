from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from story_runtime.contracts import CreateMigrationJobRequest, MigrationActionRequest
from story_runtime.migration_jobs import LegacyMigrationService


CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "schemas"


def test_canonical_import_schema_accepts_runtime_cir(runtime, tmp_path):
    config, database, _, _ = runtime
    source = tmp_path / "CJK-项目"
    (source / "chapters").mkdir(parents=True)
    (source / "inkos.json").write_text('{"version":"1.7.0"}', encoding="utf-8")
    (source / "chapters" / "Ch001.md").write_text("# 第一章\n正文🙂", encoding="utf-8")
    service = LegacyMigrationService(database, config)
    job = service.create(CreateMigrationJobRequest(source_path=str(source), target_project_id="schema-target"))
    job = service.scan(job.migration_job_id, MigrationActionRequest(actor="contract-test"))
    schema = json.loads((CONTRACTS / "canonical-import-v1.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(job.cir), key=lambda error: list(error.path))
    assert errors == [], [error.message for error in errors]


def test_all_phase7_schemas_are_valid_json_schema():
    for name in ("canonical-import-v1.json", "migration-job-request.json", "migration-decision-request.json", "migration-job-result.json"):
        Draft202012Validator.check_schema(json.loads((CONTRACTS / name).read_text(encoding="utf-8")))
