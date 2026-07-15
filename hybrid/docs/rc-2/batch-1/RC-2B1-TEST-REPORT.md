# RC-2B Batch 1 Test Report

Date: 2026-07-15
Baseline: `cefed3baffacea6fce715b856cc89bdfeaabc521`
Execution environment: Windows 10 build 26200, PowerShell, Python 3.11.15, SQLite 3.53.1, pytest 9.1.1, Node 24.16.0, pnpm 9.12.0

All commands below were executed after the initial ignored cache/test-output cleanup. Exit codes, counts and durations are from this closeout run, not earlier reports.

## Final passing runs

| Scope | Command | Exit | Tests / skipped | Wall duration | Result |
|---|---|---:|---:|---:|---|
| Runtime full | `cd hybrid/story-runtime; python -m pytest -q` | 0 | 146 passed / 0 skipped | 40.4s | PASS |
| Batch 1 explicit specialized matrix | `cd hybrid/story-runtime; python -m pytest -q tests/unit/test_revision_manifests.py tests/unit/test_revision_neutrality.py tests/unit/test_chapter_commits.py tests/migration/test_migrations.py tests/integration/test_phase7_migration.py tests/integration/test_api.py tests/integration/test_cli.py` | 0 | 69 passed / 0 skipped | 19.9s | PASS |
| Python compilation and environment | `python -m compileall -q src tests scripts; python -m pip check` | 0 | N/A | 3.4s | PASS; no broken requirements |
| Architecture + patch hygiene | `python hybrid/scripts/check_architecture.py; git diff --check` | 0 | N/A | 1.5s | PASS; line-ending warnings only |
| Authority call graph | `cd inkos; pnpm check:chapter-authority` | 0 | 439 modules / 319 edges / 24022 call sites | 4.5s | PASS |
| InkOS Core | `cd inkos; pnpm --filter @actalk/inkos-core test` | 0 | 173 files / 1572 passed / 0 skipped | 65.7s | PASS |
| InkOS CLI/TUI final run | `cd inkos; pnpm --filter @actalk/inkos test` | 0 | 40 files / 219 passed / 0 skipped | 169.4s | PASS |
| InkOS Studio | `cd inkos; pnpm --filter @actalk/inkos-studio test` | 0 | 58 files / 503 passed / 0 skipped | 79.0s | PASS |
| TypeScript workspace | `cd inkos; pnpm typecheck` | 0 | N/A | 62.3s | PASS |
| Workspace build | `cd inkos; pnpm build` | 0 | N/A | 76.4s | PASS; existing chunk-size warning only |
| RC-1 failed-target rerun | `cd inkos/packages/studio; pnpm exec playwright test --config playwright.rc1.config.ts --grep "fault timeout fails closed and recovers"` | 0 | 1 passed / 0 skipped | 36.5s | PASS |
| RC-1 Chromium final full rerun | `cd inkos; pnpm --filter @actalk/inkos-studio test:e2e:rc1` | 0 | 13 passed / 0 skipped | 161.1s | PASS |

## Non-passing/incomplete attempts retained

These attempts are intentionally recorded and were not hidden or excluded:

- The first CLI/TUI command was externally terminated by the command runner at 184 seconds (exit 124) before Vitest returned a result. The identical command was rerun with a sufficient ceiling and passed 40 files / 219 tests. No product or test code changed between these attempts.
- The first RC-1 Chromium full run completed 12/13 with one failure: `fault timeout fails closed and recovers` did not restore `runtime-count` within 30 seconds after retry. The unchanged failed target then passed 1/1, and the unchanged complete suite passed 13/13. No Studio code, E2E assertion, timeout, retry count or test selection was modified. This is retained as a harness/timing stability observation, not counted as a hidden pass.

## Batch 1 coverage mapping

- Fresh database, schema-7 upgrade, native Runtime project, legacy/bootstrap project, existing chapter commits and legacy `schema_version=NULL` events are covered by the full and specialized suites.
- Migration repeat, atomic failure rollback, verified pre-manifest backup, interruption behavior and downgrade stop are covered. An interrupted migration preserves schema 7 and its verified backup; a retry fails closed until the operator inspects/removes or archives that backup.
- Manifest UPDATE/DELETE, duplicate revision, duplicate manifest ID, duplicate command identity, project-pointer/manifest mismatch, missing command transition, predecessor hash mismatch, event envelope/reference tamper and chapter artifact mismatch are covered by database constraints and doctor tests.
- Native revision 0, legacy revision-0 boundary handling, one allocator/CAS, idempotent retries, competing commands, response loss, outer rollback, lock/retry, chapter finalize, typed diff, recovery/replay neutrality and fail-closed `at_revision` are covered.

## Known limits and unverified environments

- Linux and macOS were not executed against this unpushed local candidate. They remain NOT VERIFIED; this report makes no cross-platform claim.
- Batch 1 does not provide complete event sourcing, full event coverage, historical reducers or historical state queries.
- The initial Chromium timeout-recovery fluctuation is a known test-harness timing observation even though the unchanged target and final full run passed.
