# RC-2B1D Test Report

Execution date: 2026-07-18, Windows 10 build 26200, Python 3.11.15 / SQLite 3.53.1, Node 24.16.0, pnpm 9.15.9.

## Runtime and defect suites

| Suite | Result |
| --- | --- |
| Runtime full: `python -m pytest -q --basetemp C:\\tmp\\rc2b1d-precommit-full -p no:cacheprovider` | PASS, 182 tests |
| RC-2B1D + Batch 1 specialized matrix | PASS, 105 tests after final Doctor category cases |
| RC-2B1D dedicated files (Doctor, ownership, architecture, legacy first-write) | PASS, 36 tests |
| Python architecture gate | PASS |
| `git diff --check` | PASS; Windows line-ending notices only |

The Runtime full suite covers doctor, allocator/CAS, manifests, hash chain, migration, bootstrap, chapter finalize, typed diff, idempotency, concurrency, recovery/replay and existing revision-neutral operations. Dedicated RC-2B1D tests add unknown compatibility, provenance rebinding after self-hash recomputation, downstream chain impact, architecture mutations, ownership and migration-7 first-write fault/concurrency cases.

## InkOS regressions

| Suite | Result |
| --- | --- |
| Core full | PASS, 173 files / 1572 tests |
| Studio full | PASS, 58 files / 503 tests |
| CLI/TUI full Vitest | PASS, exit 0; direct full Vitest run completed in 193.1s |
| RC-1 Chromium | PASS, 13/13 in 178.5s |
| TypeScript authority call graph | PASS, 439 modules / 319 import edges / 24022 call sites |
| full workspace typecheck | PASS |
| full workspace build | PASS |

The CLI package `test` lifecycle first exceeded the 240-second tool window because it combines prebuild and the long test run. The same complete CLI/TUI Vitest suite then passed directly, and prebuild/build plus full workspace build passed separately. This is recorded as an execution-window observation, not a hidden test pass.

## CI and Release Readiness context

No CI exists for the unpushed working tree. The fixed baseline SHA retains these previously independently verified same-SHA runs:

- RC-1 Gate run `29416156927`: SUCCESS;
- authority-gates run `29416156658`: SUCCESS;
- phase9-cross-platform run `29416156656`: FAILURE.

RC-2B1D does not change Phase 9 workflow or fix its Windows InkOS, `pip-audit`, or deterministic Studio clean-build failures. Those remain Batch 12 / Release Readiness blockers. This report does not claim the repository is CI green or production-ready.
