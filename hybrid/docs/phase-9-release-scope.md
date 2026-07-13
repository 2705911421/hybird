# Phase 9 release scope freeze

Status: frozen 2026-07-13. Phase 9 is stabilization only.

## Included

- InkOS Studio/CLI/TUI product shell with Story Runtime as the sole long-form authority.
- Deterministic context assembly, exact fact/entity reads, trigram lexical retrieval, optional rebuildable vector integration, chapter prepare/validate/commit, typed reviews/revisions, events, projections, outbox, doctor and legacy migration.
- SQLite WAL authority, checked migrations, online snapshot/restore, structured bounded logs, diagnostics, deterministic million-character benchmarks, short/24-hour soak harnesses, cross-platform CI and standalone Runtime packaging.
- Long novels and the already-supported InkOS non-long-form project types. Only long novels use Story Runtime authority.

## Excluded

- New domain models, another Runtime, another authority database, distributed services, Studio rewrite, real LLM/embedding/reranker as a required test, LAN Runtime exposure, cloud/NFS authority storage, collaborative multi-writer editing, and claims of universal downgrade support.
- A signed native GUI installer/notarized app bundle is not present in this repository and is a release blocker for an installer-labelled release.

## Supported platform and toolchain

- Windows 11 x64, Ubuntu 24.04 x64, macOS 14+ arm64 are the intended package targets.
- Runtime source supports CPython 3.11 through 3.13. Release binaries embed CPython 3.11.
- InkOS source/build supports Node 22 LTS and pnpm 9. End users of the standalone Runtime do not install Python or create a venv.
- Cross-platform claims remain provisional until all three clean-machine jobs have artifacts and reports.

## Authority guarantee

SQLite in Story Runtime is the only writer for chapters, facts, relationships, events, commits, reviews and core projections. InkOS requests versioned commands. Markdown, FTS/vector indexes, snapshots and exports are disposable or restorable derivatives. No fallback write is permitted when Runtime is unavailable.

## Compatibility, upgrade and rollback

- API/project contract: `story-runtime/v1`; database schema: 7; snapshot format: `hybrid-story-runtime-snapshot/v1`.
- Phase 9 reads Phase 8 schema 6 and upgrades 6 to 7 through an explicit CLI migration with a pre-migration online snapshot and report.
- Schema newer than 7 is rejected as `schema_too_new`; it is never silently downgraded.
- Project schema other than `story-runtime/v1` requires a documented importer/migration.
- Rollback means restoring the pre-migration snapshot into a new directory, validating it, then selecting that project. In-place restore is forbidden. Only migrations explicitly reviewed as reversible may be downgraded; no blanket downgrade promise is made.

## Known limits

- SQLite must be on a local disk. UNC/NFS/network-sync authority paths are unsupported and warned/blocked by launch policy.
- One Runtime process owns one SQLite authority database and may serve multiple projects in that database. Multi-host writers are unsupported.
- Maximum HTTP body defaults to 16 MiB; migration limits remain 64 MiB/file, 4 GiB total and 200,000 files.
- Vector retrieval is optional and not configured in the release baseline. Core offline operation uses exact and lexical retrieval.
- Portable packages and standalone Runtime are implemented; native signing, notarization and uninstall registration are not.
