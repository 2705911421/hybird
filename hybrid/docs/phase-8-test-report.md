# Phase 8 test report

Date: 2026-07-13
Status: **PASS**
Scope: Phase 8 only; Phase 9 was not started.

## Destructive-change prerequisite

Phase 7 passed an actual private long-form project migration exercise before Phase 8 deletion began. The source was read-only and redacted in evidence; disposable Runtime databases proved dry-run, migration, validation, replay, export, cutover, Runtime rollback and pre-migration restore. See `phase-7-actual-project-acceptance.md`.

## Final automated verification

| Suite or gate | Result |
|---|---:|
| Story Runtime `pytest` | 96 passed |
| Story Runtime `pip check` | passed |
| Story Runtime `compileall` | passed |
| InkOS Core Vitest | 170 files, 1,543 tests passed |
| InkOS Studio Vitest | 58 files, 497 tests passed |
| InkOS CLI Vitest | 38 files, 205 tests passed |
| TypeScript tests total | 266 files, 2,245 tests passed |
| Combined automated tests | 2,341 passed |
| InkOS production build | passed |
| InkOS workspace typecheck | passed |
| Phase 8 architecture gate | 10 authority rules plus duplicate-Dashboard isolation passed |
| Git whitespace/error check | passed |

The CLI package-publish test timeout was increased after Windows `npm pack` exceeded its former 30-second test budget. The command itself succeeded; the full CLI suite was rerun serially and passed. A Studio daemon timing failure seen only during a concurrent stress run was likewise followed by a clean complete Studio run.

## Required behavior coverage

| Area | Evidence/result |
|---|---|
| New book, write, revise, commit, query | Runtime-only initialization and chapter persistence tests passed; legacy writer calls fail closed. |
| Review artifacts | Runtime review/status tests passed; duplicate Studio approve/reject writers are 410 tombstones. |
| Studio, CLI, TUI | Full package suites passed; all long-form status and command paths require Runtime. |
| Export and readable snapshots | Phase 7 actual-project export/snapshot digests verified; exports remain non-authoritative. |
| Restore, migration, doctor, replay | Actual-project exercise and Runtime integration suite passed. |
| Typed entity/world/relation/thread edits | Studio proxy and Runtime typed-diff integration tests passed, including expected revision, transaction/event/projection and idempotent retry. |
| Agent permissions | 138 permission/prompt boundary tests passed; authority mutators are absent and Runtime data, databases and migration snapshots are path-denied. |
| Legacy project | Read/export/dry-run/backup remain available; legacy write paths return explicit read-only/migration guidance. |
| Non-long-form | Play, Short Fiction and Interactive Film regression tests passed; separate ownership is documented in ADR-011. |
| Configuration migration | Real temporary BOM-prefixed config migrated to Runtime-only mode, created a backup and emitted explicit warnings. |

## Static and inventory checks

- Knip unused-file/export/dependency analysis and Vulture high-confidence Python analysis were run.
- Phase 8 authority dead code was deleted incrementally: legacy chapter persistence, bootstrap, chapter-import source, hook arbiter, duplicate tests and dead Studio foundation UI.
- Route, test, feature-flag and config inventories were captured during cleanup. Studio mutation routes that must remain understandable are explicit 410 tombstones, not writers.
- Knip findings with unresolved dynamic UI/provider/build reachability are marked `unknown` in the removal audit and were not deleted.
- Direct SQLite/data-path access, Markdown bootstrap, duplicate commit/review/dashboard, Runtime LLM imports, missing write metadata, missing migration provenance and authority-marked FTS/vector indexes are CI failures.

## Rollback readiness

The release boundary retains the previous application and Runtime packages, pre-migration snapshot, schema compatibility statement and legacy reader/migration tooling. Rollback restores a package/snapshot boundary; it does not re-enable dual-write in this version.

## Conclusion

Phase 8's completion definition is met: Story Runtime is the sole long-form authority writer, all architecture gates are in CI, legacy projects have a safe read/migrate/export exit, non-long-form ownership is explicit, provenance/licenses remain, and no hidden fallback or second long-form write chain remains.
