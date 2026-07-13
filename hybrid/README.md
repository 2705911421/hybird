# Hybrid workspace

The product boundary is InkOS as the TypeScript product shell and Story Runtime as the Python long-form authority service.

Current state: Phase 8 complete; Phase 9 stabilization implemented in part and release-blocked pending cross-platform, 24-hour, packaging and disaster-recovery evidence.

- Runtime owns long-form chapters, facts, events, commits, projections, review artifacts, migration and replay.
- InkOS owns product/session settings, LLM generation, exports and separately scoped non-long-form features.
- Markdown, FTS/vector indexes and readable snapshots are rebuildable projections or importer inputs.
- Legacy projects are read/export/backup/migrate-only.
- Phase 9 adds deterministic scale/soak tooling, SQLite operations, snapshot/restore, bounded logs, Runtime lifecycle and release workflows; it is not declared complete.

Start with [final data ownership](docs/final-data-ownership.md), [Phase 8 implementation](docs/phase-8-implementation.md), [architecture gates](docs/architecture-gates.md), and the [migration guide](docs/legacy-project-migration-guide.md).
