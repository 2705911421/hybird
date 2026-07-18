from __future__ import annotations

from uuid import uuid4

import json
import pytest

from story_runtime.chapter_commits import ChapterCommitService
from story_runtime.config import RuntimeConfig
from story_runtime.contracts import CreateProjectRequest, StoryEventInput, TypedDiffCommandRequest
from story_runtime.database import Database
from story_runtime.repository import StoryRepository
from story_runtime.revision_manifests import (
    RevisionManifestRepository,
    canonical_manifest_hash,
)
from story_runtime.services import RuntimeServices


def _native_project(tmp_path, project_id: str = "doctor-integrity"):
    database = Database(RuntimeConfig(database_path=tmp_path / f"{project_id}.db"))
    database.migrations.migrate()
    ChapterCommitService(database).create_project(CreateProjectRequest(
        request_id=uuid4(),
        idempotency_key=f"create-{project_id}-0001",
        project_id=project_id,
        schema_version="story-runtime/v1",
    ))
    return database, RuntimeServices(database, StoryRepository(database))


def _rewrite_manifest(database: Database, project_id: str, revision: int, **changes) -> None:
    with database.connect() as conn:
        conn.execute("DROP TRIGGER IF EXISTS project_revisions_immutable_update")
        conn.execute("PRAGMA ignore_check_constraints=ON")
        assignments = ",".join(f"{field}=?" for field in changes)
        conn.execute(
            f"UPDATE project_revisions SET {assignments} WHERE project_id=? AND revision=?",
            (*changes.values(), project_id, revision),
        )
        row = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id=? AND revision=?",
            (project_id, revision),
        ).fetchone()
        manifest_hash = canonical_manifest_hash(
            RevisionManifestRepository.from_row(row).canonical_payload()
        )
        conn.execute(
            "UPDATE project_revisions SET manifest_hash=? WHERE project_id=? AND revision=?",
            (manifest_hash, project_id, revision),
        )


def _recompute_manifest(database: Database, project_id: str, revision: int) -> str:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM project_revisions WHERE project_id=? AND revision=?",
            (project_id, revision),
        ).fetchone()
        manifest_hash = canonical_manifest_hash(
            RevisionManifestRepository.from_row(row).canonical_payload()
        )
        conn.execute(
            "UPDATE project_revisions SET manifest_hash=? WHERE project_id=? AND revision=?",
            (manifest_hash, project_id, revision),
        )
    return manifest_hash


def _typed_diff(database: Database, project_id: str, revision: int, key: str):
    return ChapterCommitService(database).apply_typed_diff(TypedDiffCommandRequest(
        request_id=uuid4(),
        idempotency_key=key,
        project_id=project_id,
        schema_version="story-runtime/v1",
        expected_revision=revision,
        actor="doctor-test",
        reason="provenance fixture",
        events=[StoryEventInput(
            event_type="fact.upsert",
            subject="world",
            aggregate_type="fact",
            aggregate_id=f"fact-{revision + 1}",
            payload={"predicate": f"world.rule.{revision + 1}", "value": "known"},
            evidence=[],
        )],
    ))


def test_doctor_fails_closed_for_unknown_manifest_schema_even_with_recomputed_hash(tmp_path) -> None:
    database, runtime = _native_project(tmp_path)
    _rewrite_manifest(
        database,
        "doctor-integrity",
        0,
        manifest_schema_version="revision-manifest/v999",
    )

    result = runtime.doctor("doctor-integrity", deep=True)
    issue = next(check for check in result.checks if check.code == "UNKNOWN_MANIFEST_SCHEMA_VERSION")

    assert result.status == "blocked"
    assert issue.project_id == "doctor-integrity"
    assert issue.revision == 0
    assert issue.field == "manifest_schema_version"
    assert issue.observed_value == "revision-manifest/v999"
    assert issue.supported_values == ["revision-manifest/v1"]
    assert issue.severity == "critical"
    assert issue.verification_stopped is True
    assert issue.chain_health == "UNVERIFIABLE_UNKNOWN_VERSION"
    assert any(check.code == "UNKNOWN_CANONICALIZATION_VERSION" for check in result.checks)
    assert not any(check.code == "manifest.chain" and check.status == "pass" for check in result.checks)


@pytest.mark.parametrize(
    ("field", "observed", "code", "supported"),
    [
        ("event_schema_version", "events/v999", "UNKNOWN_EVENT_SCHEMA_VERSION", ["legacy-unversioned", "story-runtime/v1"]),
        (
            "reducer_version",
            "story-reducers/v999",
            "UNKNOWN_REDUCER_VERSION",
            ["story-reducers/legacy-v1", "story-reducers/not-applicable"],
        ),
    ],
)
def test_doctor_marks_unknown_event_and_reducer_versions_replay_unsafe(
    tmp_path, field: str, observed: str, code: str, supported: list[str]
) -> None:
    database, runtime = _native_project(tmp_path, f"unknown-{field}")
    _rewrite_manifest(database, f"unknown-{field}", 0, **{field: observed})

    result = runtime.doctor(f"unknown-{field}", deep=True)
    issue = next(check for check in result.checks if check.code == code)

    assert result.status == "blocked"
    assert issue.field == field
    assert issue.observed_value == observed
    assert issue.supported_values == supported
    assert issue.replay_safe is False
    assert issue.chain_health == "UNVERIFIABLE_UNKNOWN_VERSION"


def test_doctor_stops_hash_verification_for_unknown_hash_algorithm(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "unknown-hash")
    with database.connect() as conn:
        conn.execute("DROP TRIGGER project_revisions_immutable_update")
        conn.execute(
            "UPDATE project_revisions SET manifest_hash=? WHERE project_id='unknown-hash' AND revision=0",
            ("sha512:" + "a" * 128,),
        )

    result = runtime.doctor("unknown-hash", deep=True)
    issue = next(check for check in result.checks if check.code == "UNKNOWN_HASH_ALGORITHM")

    assert issue.field == "manifest_hash"
    assert issue.observed_value == "sha512"
    assert issue.supported_values == ["sha256"]
    assert issue.verification_stopped is True
    assert issue.chain_health == "UNVERIFIABLE_UNKNOWN_VERSION"
    assert not any(check.code == "manifest.hash.0" for check in result.checks)


@pytest.mark.parametrize(
    ("field", "observed", "code"),
    [
        ("contract_version", "story-runtime/v999", "UNKNOWN_COMPATIBILITY_VERSION"),
        ("transition_kind", "future-transition/v999", "UNKNOWN_COMPATIBILITY_VERSION"),
        ("provenance_class", "future-provenance/v999", "UNKNOWN_PROVENANCE_VERSION"),
    ],
)
def test_doctor_rejects_unknown_contract_transition_and_provenance_values(
    tmp_path, field: str, observed: str, code: str
) -> None:
    project_id = f"unknown-{field}"
    database, runtime = _native_project(tmp_path, project_id)
    _rewrite_manifest(database, project_id, 0, **{field: observed})

    result = runtime.doctor(project_id, deep=True)

    assert any(
        check.code == code
        and check.field == field
        and check.observed_value == observed
        and check.replay_safe is False
        for check in result.checks
    )


def test_doctor_detects_missing_command_identity_after_manifest_hash_is_recomputed(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "command-missing")
    _typed_diff(database, "command-missing", 0, "typed-command-missing-0001")
    _rewrite_manifest(database, "command-missing", 1, command_id="domain.command:does-not-exist")

    result = runtime.doctor("command-missing", deep=True)
    issue = next(check for check in result.checks if check.code == "MANIFEST_COMMAND_REFERENCE_MISSING")

    assert result.status == "blocked"
    assert issue.revision == 1
    assert issue.field == "command_id"
    assert issue.observed_value == "domain.command:does-not-exist"
    assert issue.chain_health == "CORRUPTED"
    assert not any(check.code == "manifest.hash.1" for check in result.checks)


def test_doctor_detects_cross_project_command_rebound(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "command-project-a")
    ChapterCommitService(database).create_project(CreateProjectRequest(
        request_id=uuid4(),
        idempotency_key="create-command-project-b-0001",
        project_id="command-project-b",
        schema_version="story-runtime/v1",
    ))
    _typed_diff(database, "command-project-a", 0, "typed-command-project-a-0001")
    _typed_diff(database, "command-project-b", 0, "typed-command-project-b-0001")
    other_command = RevisionManifestRepository(database).get("command-project-b", 1).command_id
    _rewrite_manifest(database, "command-project-a", 1, command_id=other_command)

    result = runtime.doctor("command-project-a", deep=True)
    codes = {check.code for check in result.checks}

    assert "COMMAND_PROJECT_MISMATCH" in codes
    assert "DUPLICATE_COMMAND_ID" in codes


def test_doctor_detects_command_resulting_revision_mismatch(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "command-revision")
    key = "typed-command-revision-0001"
    _typed_diff(database, "command-revision", 0, key)
    with database.connect() as conn:
        ledger = conn.execute(
            "SELECT result_json FROM idempotency_ledger WHERE project_id='command-revision' AND idempotency_key=?",
            (key,),
        ).fetchone()
        payload = json.loads(ledger["result_json"])
        payload["revision"] = 99
        conn.execute(
            "UPDATE idempotency_ledger SET result_json=? WHERE project_id='command-revision' AND idempotency_key=?",
            (json.dumps(payload), key),
        )

    result = runtime.doctor("command-revision", deep=True)
    issue = next(check for check in result.checks if check.code == "COMMAND_REVISION_MISMATCH")

    assert issue.revision == 1
    assert issue.field == "result_json.revision"
    assert issue.observed_value == "99"


def test_doctor_detects_same_project_command_id_rebound(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "command-rebound")
    _typed_diff(database, "command-rebound", 0, "typed-command-rebound-0001")
    _typed_diff(database, "command-rebound", 1, "typed-command-rebound-0002")
    with database.connect() as conn:
        conn.execute("DROP TRIGGER project_revisions_immutable_update")
        command1 = conn.execute(
            "SELECT command_id FROM project_revisions WHERE project_id='command-rebound' AND revision=1"
        ).fetchone()[0]
        command2 = conn.execute(
            "SELECT command_id FROM project_revisions WHERE project_id='command-rebound' AND revision=2"
        ).fetchone()[0]
        conn.execute(
            "UPDATE project_revisions SET command_id='temporary-command' "
            "WHERE project_id='command-rebound' AND revision=1"
        )
        conn.execute(
            "UPDATE project_revisions SET command_id=? WHERE project_id='command-rebound' AND revision=2",
            (command1,),
        )
        conn.execute(
            "UPDATE project_revisions SET command_id=? WHERE project_id='command-rebound' AND revision=1",
            (command2,),
        )
    hash1 = _recompute_manifest(database, "command-rebound", 1)
    with database.connect() as conn:
        conn.execute(
            "UPDATE project_revisions SET previous_manifest_hash=? "
            "WHERE project_id='command-rebound' AND revision=2",
            (hash1,),
        )
    _recompute_manifest(database, "command-rebound", 2)

    result = runtime.doctor("command-rebound", deep=True)

    assert {check.revision for check in result.checks if check.code == "COMMAND_ID_REBOUND"} == {1, 2}


def test_doctor_detects_incomplete_command_ledger_provenance(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "command-incomplete")
    key = "typed-command-incomplete-0001"
    _typed_diff(database, "command-incomplete", 0, key)
    with database.connect() as conn:
        conn.execute(
            "UPDATE idempotency_ledger SET result_json='not-json', operation='unknown-operation' "
            "WHERE project_id='command-incomplete' AND idempotency_key=?",
            (key,),
        )

    result = runtime.doctor("command-incomplete", deep=True)
    codes = {check.code for check in result.checks}

    assert "COMMAND_PROVENANCE_INCOMPLETE" in codes


def test_doctor_propagates_first_chain_corruption_to_all_later_revisions(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "chain-impact")
    for revision in range(3):
        _typed_diff(database, "chain-impact", revision, f"typed-chain-impact-{revision + 1:04d}")
    with database.connect() as conn:
        conn.execute("DROP TRIGGER project_revisions_immutable_update")
        conn.execute(
            "UPDATE project_revisions SET previous_manifest_hash=? "
            "WHERE project_id='chain-impact' AND revision=1",
            ("sha256:" + "0" * 64,),
        )

    result = runtime.doctor("chain-impact", deep=True)
    by_revision = {
        check.revision: check.chain_health
        for check in result.checks
        if check.code in {"MANIFEST_CHAIN_CORRUPTED", "MANIFEST_CHAIN_AFFECTED"}
    }
    summary = next(check for check in result.checks if check.code == "MANIFEST_CHAIN_IMPACT")

    assert by_revision == {
        1: "CORRUPTED",
        2: "AFFECTED_BY_PRIOR_CORRUPTION",
        3: "AFFECTED_BY_PRIOR_CORRUPTION",
    }
    assert summary.latest_trusted_revision == 0
    assert summary.first_untrusted_revision == 1
    assert summary.chain_impact_start == 1
    assert summary.chain_impact_end == 3
    assert summary.total_affected_revisions == 3
    assert "1..3" in summary.message


def test_doctor_reports_later_direct_corruption_without_duplicate_upstream_defect(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "chain-multiple")
    for revision in range(4):
        _typed_diff(database, "chain-multiple", revision, f"typed-chain-multiple-{revision + 1:04d}")
    with database.connect() as conn:
        conn.execute("DROP TRIGGER project_revisions_immutable_update")
        conn.execute(
            "UPDATE project_revisions SET previous_manifest_hash=? WHERE project_id='chain-multiple' AND revision=1",
            ("sha256:" + "0" * 64,),
        )
        conn.execute(
            "UPDATE project_revisions SET command_id=? WHERE project_id='chain-multiple' AND revision=4",
            ("domain.command:tampered-later",),
        )

    result = runtime.doctor("chain-multiple", deep=True)
    health = [
        (check.revision, check.chain_health)
        for check in result.checks
        if check.code in {"MANIFEST_CHAIN_CORRUPTED", "MANIFEST_CHAIN_AFFECTED"}
    ]

    assert health == [
        (1, "CORRUPTED"),
        (2, "AFFECTED_BY_PRIOR_CORRUPTION"),
        (3, "AFFECTED_BY_PRIOR_CORRUPTION"),
        (4, "CORRUPTED"),
    ]


def test_doctor_propagates_unknown_version_to_later_revisions(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "unknown-chain")
    _typed_diff(database, "unknown-chain", 0, "typed-unknown-chain-0001")
    _typed_diff(database, "unknown-chain", 1, "typed-unknown-chain-0002")
    _rewrite_manifest(database, "unknown-chain", 1, manifest_schema_version="revision-manifest/v999")
    hash1 = RevisionManifestRepository(database).get("unknown-chain", 1).manifest_hash
    _rewrite_manifest(database, "unknown-chain", 2, previous_manifest_hash=hash1)

    result = runtime.doctor("unknown-chain", deep=True)
    health = {
        check.revision: check.chain_health
        for check in result.checks
        if check.code in {"MANIFEST_CHAIN_UNVERIFIABLE", "MANIFEST_CHAIN_AFFECTED"}
    }

    assert health == {1: "UNVERIFIABLE_UNKNOWN_VERSION", 2: "AFFECTED_BY_PRIOR_CORRUPTION"}


def test_doctor_marks_missing_predecessor_without_synthesizing_history(tmp_path) -> None:
    database, runtime = _native_project(tmp_path, "missing-predecessor")
    _typed_diff(database, "missing-predecessor", 0, "typed-missing-predecessor-0001")
    _typed_diff(database, "missing-predecessor", 1, "typed-missing-predecessor-0002")
    with database.connect() as conn:
        conn.execute("DROP TRIGGER project_revisions_immutable_delete")
        conn.execute(
            "DELETE FROM project_revisions WHERE project_id='missing-predecessor' AND revision=1"
        )

    result = runtime.doctor("missing-predecessor", deep=True)

    assert any(
        check.code == "MANIFEST_CHAIN_MISSING_PREDECESSOR"
        and check.revision == 2
        and check.chain_health == "MISSING_PREDECESSOR"
        for check in result.checks
    )
    assert [item.revision for item in RevisionManifestRepository(database).list("missing-predecessor")] == [0, 2]
