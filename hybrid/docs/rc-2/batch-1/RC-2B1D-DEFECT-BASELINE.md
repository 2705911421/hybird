# RC-2B1D Defect Baseline

Recorded: 2026-07-18 (Asia/Shanghai)

## Candidate identity

| Item | Baseline |
| --- | --- |
| Repository | `2705911421/hybird` |
| Branch | `master` |
| HEAD | `790e06d231daa33ce3774cc065e21c059d7680d7` |
| `origin/master` | `790e06d231daa33ce3774cc065e21c059d7680d7` |
| Ahead / behind | `0 / 0` |
| Staged | empty |
| Unstaged | empty |
| Untracked | empty |
| Worktree | clean before repair |

## Executed test baseline

| Gate | Command | Result |
| --- | --- | --- |
| Runtime full | `python -m pytest -q --basetemp C:\\tmp\\rc2b1d-baseline-full -p no:cacheprovider` | PASS, 146 tests |
| Batch 1 specialized | `python -m pytest -q tests/unit/test_revision_manifests.py tests/unit/test_revision_neutrality.py tests/unit/test_chapter_commits.py tests/migration/test_migrations.py tests/integration/test_phase7_migration.py tests/integration/test_api.py tests/integration/test_cli.py --basetemp C:\\tmp\\rc2b1d-baseline-specialized -p no:cacheprovider` | PASS, 69 tests |
| Python architecture gate | `python hybrid/scripts/check_architecture.py` | PASS at the unmodified baseline; known mutation-test blind spot remains |
| TypeScript authority call graph | `npx --yes pnpm@9.15.9 --dir inkos check:chapter-authority` | PASS, 439 modules / 319 import edges / 24022 call sites |

The global pnpm 11 installation is newer than the repository lockfile. The call-graph baseline therefore used pnpm 9.15.9. A transient root `.pnpm-store` created by the first incompatible invocation was removed, and the worktree was confirmed clean before this document was added.

## Confirmed defects

1. `manifest_integrity_issues` accepts any non-empty `event_schema_version`, `reducer_version`, `manifest_schema_version`, and `contract_version`; unknown values can be paired with a recomputed self-hash and reported as a valid chain.
2. Manifest `command_id` is included in the self-hash but is not cross-checked against the real command provenance. A recomputed manifest hash therefore hides a rebound command identity.
3. Direct corruption is reported at its own revision, but later revisions are not explicitly marked `AFFECTED_BY_PRIOR_CORRUPTION`; no first-untrusted/latest-trusted/affected-range summary is emitted.
4. `check_architecture.py` excludes all of `migration_jobs.py` from the direct project-revision SQL rule. The exemption is file-wide rather than symbol-specific, so a production bypass can be inserted without failing the gate.

## Current Doctor diagnostic surface

The baseline `DoctorCheck` exposes only `code`, `status`, `message`, `repair`, `retryable`, and `requires_confirmation`. It has no structured project, revision, field, observed/supported version, verification-stop, or chain-health fields.

Existing manifest codes are the lowercase dynamic family:

- `manifest.project_missing`, `manifest.missing`, `manifest.bootstrap_required`;
- `manifest.latest_mismatch`, `manifest.lineage_start`, `manifest.revision_zero`;
- `manifest.hash.<revision>`, `manifest.previous_revision.<revision>`, `manifest.previous_hash.<revision>`;
- `manifest.compatibility.<revision>` only for empty values;
- `manifest.event_count.<revision>`, `manifest.event_membership_hash.<revision>`, `manifest.event_missing.<revision>`, `manifest.event_range.<revision>`, `manifest.event_hash.<revision>`, `manifest.event_revision.<revision>`;
- `manifest.artifact_count.<revision>`, `manifest.artifact_hash.<revision>`, `manifest.commit_link.<revision>`, `manifest.transition_missing.<revision>`;
- `manifest.chain` only when no issue is returned.

## Current manifest compatibility and integrity fields

Migration 8 persists `transition_kind`, `event_schema_version`, `reducer_version`, `manifest_schema_version`, `contract_version`, `provenance_class`, `provenance_id`, `actor_class`, `ordered_event_ids_hash`, `state_hash`, and `manifest_hash`. The current native values are:

- manifest schema: `revision-manifest/v1`;
- event compatibility: `legacy-unversioned`;
- reducer: `story-reducers/legacy-v1` or `story-reducers/not-applicable` at initialization/bootstrap;
- Runtime contract: `story-runtime/v1`;
- provenance classes constrained by schema: `native`, `verified_import`, `bootstrap_boundary`, `compensation`;
- hash algorithm: SHA-256, represented by the `sha256:` tag;
- canonicalization: normalized, sorted-key, compact UTF-8 JSON implemented by `canonical_manifest_bytes`; no persisted canonicalization-version column exists in Batch 1;
- artifact schema is owned by referenced artifact/commit records, not duplicated in the manifest; no manifest artifact-schema column exists;
- bootstrap compatibility is represented by the existing provenance/reducer/event/contract fields; no independent bootstrap-version column exists.

RC-2B1D must centralize supported values without inventing Batch 2 persistence fields.

## `migration_jobs.py` responsibility and call path

`LegacyMigrationService` owns the staged legacy-import workflow: create/list/get, discover/scan, decisions, dry-run, verified snapshot, import, verification, pause/resume, cutover, rollback, report, migration ledgers, CIR mapping, and isolated replay verification. FastAPI constructs it in `create_app`, stores it as `app.state.migration_jobs`, and exposes it through `/projects/migrate` and `/migration-jobs/*` routes.

The module is production code and is reachable from public API routes. Its isolated `_replay_cir_hash` helper mutates a temporary replay database for verification; that exact symbol is a legitimate, documented exception to native authority allocation. The baseline gate instead exempts the entire file, which is the confirmed enforcement defect.

## Verification gaps

1. Gate 11: no repeatable combined static/dynamic proof yet establishes that manifests cannot contain or reconstruct full chapter, review, story-state, projection, or event payload authority, while artifact deletion and event membership mismatches remain detectable.
2. Gate 15: existing tests cover a basic revision-7 bootstrap and first revision-8 write, but not the required reusable migration-7 fixture matrix, interruption/retry/concurrency, null event schema, partial legacy metadata, and preservation assertions as one explicit gate.

## Release-readiness issues

The same-SHA `phase9-cross-platform` failures remain Batch 12 concerns: Windows InkOS test parsing, `pip-audit`, and deterministic Studio build. RC-2B1D does not change Phase 9 workflows or attempt to remediate these failures, and does not claim repository-wide CI green or production readiness.

## Out of scope

Closed typed event catalog, complete mutation-event coverage, historical query/state service, `at_revision` behavior changes, history tables, target-revision replay redesign, TypeScript historical clients, and Studio/CLI/TUI time-travel UI remain Batch 2 or later. No independent Batch 1 regate or push is authorized by this repair task.
