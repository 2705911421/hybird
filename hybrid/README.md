# Hybrid workspace

The product boundary is InkOS as the TypeScript product shell and Story Runtime as the Python long-form authority service.

Current state: Phase 8 complete; Phase 9 not started.

- Runtime owns long-form chapters, facts, events, commits, projections, review artifacts, migration and replay.
- InkOS owns product/session settings, LLM generation, exports and separately scoped non-long-form features.
- Markdown, FTS/vector indexes and readable snapshots are rebuildable projections or importer inputs.
- Legacy projects are read/export/backup/migrate-only.

Start with [final data ownership](docs/final-data-ownership.md), [Phase 8 implementation](docs/phase-8-implementation.md), [architecture gates](docs/architecture-gates.md), and the [migration guide](docs/legacy-project-migration-guide.md).
