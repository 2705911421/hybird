# Phase 8 implementation

Date: 2026-07-13  
Status: implemented; Phase 9 not started

## Authority contraction

- Deleted the legacy chapter persistence implementation and selection port.
- Removed Writer chapter/Truth save methods and long-form `MemoryDB` synchronization.
- Replaced legacy draft, revision, state repair, Markdown resync and chapter import entry points with fail-closed migration/Runtime guidance.
- Removed automatic Markdown bootstrap from state loading and memory retrieval; structured state absence is explicit.
- Deleted the bootstrap module itself; migration source parsing remains isolated in the explicit importer.
- Removed long-form Agent Truth/chapter/import/generic file mutators from both registry and implementation.
- Rewrote long-form Agent prompts and edit sessions so they can emit only typed proposals, review artifacts and Runtime command requests; path checks deny Runtime databases, authority roots and migration snapshots in code.
- Removed deterministic interaction file writers; UI actions now fail closed instead of editing legacy files.
- Removed legacy/shadow context provider, shadow diff, Runtime-unavailable fallback and dead Markdown context composer.
- New books require Runtime authority; Runtime project creation is part of book initialization.
- Fan-fiction and spinoff initialization use the same Runtime project chain while retaining source provenance.
- Draft audit output is ephemeral proposal data; post-chapter hooks no longer promote a second authority write.

## Studio and Runtime command path

Studio direct Truth/chapter/repair/resync/rewrite/review/import routes are HTTP 410 compatibility tombstones. User edits to characters, world, relationships, facts, timeline and threads use:

`typed diff -> Runtime validation -> expected revision -> transaction -> event -> projection`

The new Runtime `/commands/typed-diff` contract carries request ID, idempotency key, project ID, schema version and expected revision, plus actor, reason and typed events. It rejects direct SQL/path capabilities, stale revisions and unsupported event/aggregate pairs; retries are idempotent.

Studio's generic artifact writer is restricted to non-long-form output roots. Direct foundation controls were removed, chat file edits cannot target `books/**`, and no raw Runtime database download route exists.

## Legacy exit and configuration

- Old projects remain readable/exportable and can use the Phase 7 migration wizard.
- Runtime status reports legacy/shadow as read-only with deprecation guidance.
- Default configuration is `story-runtime` with fail-closed fallback.
- `pnpm migrate:phase8-config -- <project>` creates a backup and reports every migration; old keys are never silently ignored.
- The migrator accepts UTF-8 JSON with or without BOM, rewrites retired authority/fallback keys and preserves a timestamped backup.
- CLI doctor/status/review/TUI no longer advertise `memory.db` or file-authority fallback semantics.

## CI and cleanup

Root CI runs architecture gates, Runtime dependency/compile/tests and InkOS install/typecheck/build/tests. The architecture script enforces ten authority rules plus duplicate Dashboard/plugin isolation, including Agent prompt/path capabilities.

Knip and Vulture were run. Phase 8-relevant dead paths were removed. Unrelated UI/provider exports and dependencies reported by Knip were not deleted because dynamic reachability is unresolved and therefore classified `unknown`.

Upstream history and licenses are retained. No Phase 9 work was performed.
