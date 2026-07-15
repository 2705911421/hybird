# RC-2B Batch 1 Pre-Commit Inventory

Captured: 2026-07-15 (Asia/Shanghai)
Repository root: `C:\Users\27059\Documents\hybrid-workspace`
Branch: `master`
HEAD: `cefed3baffacea6fce715b856cc89bdfeaabc521`
Baseline: `cefed3baffacea6fce715b856cc89bdfeaabc521` (HEAD equals baseline)
Upstream: `origin/master`, ahead 0 / behind 0 at capture time

## Git state at inventory capture

- Staged changes: none (`git diff --cached --stat` was empty).
- Tracked working-tree changes: 12 files, 535 insertions and 60 deletions before closeout corrections.
- Untracked files: RC-1 audit documents, RC-2 audit/decision/Batch 1 documents, the manifest implementation, and two Batch 1 unit-test modules.
- Submodules: none (`git submodule status` returned no entries).

`git status --short --untracked-files=all` at capture:

```text
 M hybrid/contracts/story-runtime.openapi.yaml
 M hybrid/scripts/check_architecture.py
 M hybrid/story-runtime/src/story_runtime/api.py
 M hybrid/story-runtime/src/story_runtime/chapter_commits.py
 M hybrid/story-runtime/src/story_runtime/migration_jobs.py
 M hybrid/story-runtime/src/story_runtime/migrations.py
 M hybrid/story-runtime/src/story_runtime/services.py
 M hybrid/story-runtime/tests/integration/test_api.py
 M hybrid/story-runtime/tests/integration/test_cli.py
 M hybrid/story-runtime/tests/integration/test_phase7_migration.py
 M hybrid/story-runtime/tests/migration/test_migrations.py
 M hybrid/story-runtime/tests/unit/test_chapter_commits.py
?? hybrid/docs/rc-1/RC-1-FINAL-GATE-BASELINE.md
?? hybrid/docs/rc-1/RC-1-FINAL-GATE-REPORT.md
?? hybrid/docs/rc-1/RC-1-FINDING-REVALIDATION.md
?? hybrid/docs/rc-1/architecture-classification/ARCHITECTURE-CLASSIFICATION-REVIEW.md
?? hybrid/docs/rc-1/architecture-classification/AUDIT-CALLGRAPH.md
?? hybrid/docs/rc-1/architecture-classification/BASELINE.md
?? hybrid/docs/rc-1/architecture-classification/CLASSIFICATION-CRITERIA.md
?? hybrid/docs/rc-2/AT-REVISION-AUDIT.md
?? hybrid/docs/rc-2/EVENT-COVERAGE-MATRIX.md
?? hybrid/docs/rc-2/HISTORICAL-DATA-MODEL-AUDIT.md
?? hybrid/docs/rc-2/HISTORICAL-QUERY-API-DRAFT.md
?? hybrid/docs/rc-2/RC-2-IMPLEMENTATION-PLAN.md
?? hybrid/docs/rc-2/RC-2A-AUDIT-REPORT.md
?? hybrid/docs/rc-2/RC-2A-BASELINE.md
?? hybrid/docs/rc-2/architecture-decisions/*
?? hybrid/docs/rc-2/batch-1/*
?? hybrid/story-runtime/src/story_runtime/revision_manifests.py
?? hybrid/story-runtime/tests/unit/test_revision_manifests.py
?? hybrid/story-runtime/tests/unit/test_revision_neutrality.py
```

Baseline tracked diff stat at capture:

```text
12 files changed, 535 insertions(+), 60 deletions(-)
```

Untracked files are not represented in that Git diff statistic. The final staged statistic is recorded in the implementation report after selective staging.

## Classification of every changed path

| Classification | Paths | Disposition |
|---|---|---|
| Batch 1 production code | `hybrid/story-runtime/src/story_runtime/api.py`; `chapter_commits.py`; `migration_jobs.py`; `services.py`; `revision_manifests.py` | Candidate commit |
| Batch 1 migration | `hybrid/story-runtime/src/story_runtime/migrations.py` | Candidate commit |
| Batch 1 tests | `hybrid/story-runtime/tests/integration/test_api.py`; `test_cli.py`; `test_phase7_migration.py`; `tests/migration/test_migrations.py`; `tests/unit/test_chapter_commits.py`; `test_revision_manifests.py`; `test_revision_neutrality.py` | Candidate commit |
| Batch 1 architecture gate | `hybrid/scripts/check_architecture.py` | Candidate commit |
| Generated contract | `hybrid/contracts/story-runtime.openapi.yaml` | Candidate commit; only fail-closed `at_revision` description and 409 response changed |
| Batch 1 documentation | `hybrid/docs/rc-2/AT-REVISION-AUDIT.md`; `EVENT-COVERAGE-MATRIX.md`; `HISTORICAL-DATA-MODEL-AUDIT.md`; `HISTORICAL-QUERY-API-DRAFT.md`; `RC-2-IMPLEMENTATION-PLAN.md`; `RC-2A-AUDIT-REPORT.md`; `RC-2A-BASELINE.md` | Candidate commit as pre-implementation audit provenance; design only |
| Batch 1 documentation | `hybrid/docs/rc-2/architecture-decisions/ADR-RC2-001-PROJECT-REVISION-SEMANTICS.md`; `ADR-RC2-002-LIMITED-HISTORY-BOUNDARY.md`; `ADR-RC2-003-HYBRID-HISTORICAL-ARCHITECTURE.md`; `ADR-RC2-004-EVENT-CATALOG-AND-COVERAGE.md`; `ADR-RC2-005-REPLAY-AND-REPAIR-BOUNDARY.md`; `ADR-RC2-006-BATCH-ORDER-AND-GATES.md`; `ADR-RC2-007-LEGACY-HISTORY-COMPATIBILITY.md`; `COMPATIBILITY-FAILURE-POLICY.md`; `HISTORY-AVAILABILITY-CONTRACT.md`; `RC-2-DATA-OWNERSHIP-MATRIX.md`; `RC-2A5-APPROVAL-GATE.md`; `RC-2A5-ARCHITECTURE-APPROVAL-REPORT.md`; `RC-2A5-BASELINE.md`; `REVISION-MANIFEST-SPEC.md` | Candidate commit as frozen approval input and provenance; contains no implementation |
| Batch 1 documentation | `hybrid/docs/rc-2/batch-1/BOOTSTRAP-BOUNDARY-IMPLEMENTATION.md`; `COMPATIBILITY-NOTES.md`; `DOCTOR-NOTES.md`; `MANIFEST-HASH-SPEC.md`; `RC-2B1-IMPLEMENTATION-REPORT.md`; `RC-2B1-PRECOMMIT-INVENTORY.md`; `RC-2B1-PREIMPLEMENTATION-AUDIT.md`; `RC-2B1-TEST-REPORT.md`; `REVISION-ALLOCATOR-SPEC.md`; `REVISION-MANIFEST-IMPLEMENTATION.md`; `SCHEMA-MIGRATION-NOTES.md` | Candidate commit |
| Unrelated | all seven untracked files under `hybrid/docs/rc-1/` listed above | Preserve in working tree; never stage in Batch 1 |
| Build/cache/temp | root `.pytest_cache/` and ignored per-test child directories under `.test-tmp-*` (tracked `*current` sentinels/fixtures are retained); Runtime `.pytest_cache/`, `.phase6-e2e.db`, `build/`, `dist/`, `__pycache__/`; InkOS package `dist/`, Studio `.playwright-cli/` and `test-results/`; `output/rc1-ui/`; `output/rc1-verification/__pycache__/` and live DB/WAL/SHM | Delete before clean test run; regenerated outputs re-cleaned before staging |
| Build/dependency cache | Runtime `.venv/`; InkOS `node_modules/` and package-local `node_modules/` | Ignored and retained to run reproducible local tests; never staged |
| Unrelated ignored local state | `inkos/.npmrc`; `inkos/test-project/`; ignored `webnovel-writer/` tree | Preserve; never stage; `.npmrc` treated as possible local secret |
| Uncertain | none after path/content tracing | No unresolved item may be staged |

## Scope-contamination review

Searches covered the Runtime source/tests/contracts/gates for the closed event catalog, typed domain-event v1, mandatory `chapter.finalized`, historical tables/API, replay redesign, historical snapshots, TypeScript clients, Studio/CLI/TUI time travel, and later-batch feature flags.

- No Batch 2 event catalog, mandatory event, append-only event redesign, or typed v1 domain payload implementation exists in the candidate code.
- No historical state table, reducer, snapshot chain, TypeScript history client, or Studio/CLI/TUI time-travel implementation exists.
- `at_revision` was not implemented as history. It was changed to fail closed with `409 HISTORY_NOT_IMPLEMENTED`, preventing the previous current-state pseudo-history behavior.
- Existing snapshot/export/replay code predates the baseline and was not redefined by this batch.
- The RC-2 plan, audits, API draft and event matrix are design/approval provenance only and explicitly defer implementation.

Scope result: no substantive Batch 2 implementation and no unsafe contamination requiring a split.

## Authority-responsibility review

`project_revisions` stores revision identity, predecessor/hash, command/commit/idempotency identities, ordered event IDs and envelope hashes, artifact references/hashes, compatibility/provenance metadata, resulting-state hash and timestamp. It stores no chapter body, review body, complete event payload, complete story state, projection, reducer output, or snapshot. Events continue to express domain changes (with incomplete coverage explicitly deferred to Batch 2), and chapter artifacts continue to own chapter bytes and large payloads.

Closeout review found and corrected one Batch 1 provenance defect: native post-initialization transitions had discarded the caller-supplied provenance/actor and mislabeled them as bootstrap compatibility. Tests now assert native command provenance, and doctor now detects a manifest with no committed command/chapter transition.

## Final selective staging

Only the 47 candidate paths classified above were staged: 3,677 insertions and 60 deletions. The seven untracked RC-1 documents remained unstaged. No database, WAL/SHM, log, coverage, build/dist output, cache, local `.npmrc`, dependency tree or secret-pattern match was present in the staged set.
