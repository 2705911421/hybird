# Phase 6 implementation

Date: 2026-07-12

Phase 6 integrates Story Runtime observability into InkOS Studio. It does not change Runtime authority, chapter commit semantics, review authority, or Phase 7+ behavior.

## Runtime

Migration 5 adds durable recovery jobs and audit entries. `ObservabilityService` is the only read model used by the new API. It exposes strict overview, commit, event, projection, review, migration, configuration, doctor, diagnostic, and recovery DTOs. Commit/event/recovery collections use opaque cursor pagination with a maximum page size of 100. Cursors bind to project, collection, filters, and sort position.

`observability.py` owns recursive redaction for secret-shaped keys and values, bearer strings, home/username paths, database paths, traceback fields, and chapter content fields. Event payloads are summarized by default. Payloads over 4 KiB are never embedded in the timeline response.

Recovery is preview-first and allow-listed. Jobs persist progress, result, failure, cancellation capability, and audit trail. Confirmation tokens are random, stored only as hashes, cleared on execution, and bound to a single job.

## Studio

Studio uses `StoryRuntimeClient` and strict Zod parsing through its Hono server. The browser never receives the Runtime bearer. Runtime errors map to `degraded`, `unavailable`, `version_mismatch`, `migration_required`, `database_locked`, or `recovery_required`; unexpected messages are not forwarded.

The hash-routed Runtime workbench provides Overview, Commits, Commit Detail, Events, Projections, Doctor & Recovery, Review Status, Migration Status, and Runtime Configuration Status. It reuses Studio tokens, typography, Lucide icons, tables, dialogs, and responsive layout.

Overview polls every 30 seconds, pauses while the page is hidden, and exponentially backs off to five minutes. Recovery history polls every three seconds while its view is active. Other lists load on navigation/filter/page changes only.

## CLI

The CLI exposes the same service-layer diagnostics through `overview`, `commits`, `events`, `projections`, `diagnostics`, `migration-status`, and `configuration-status`. No CLI command queries SQL directly for user output.

## Feature flags and rollback

- `STORY_RUNTIME_OBSERVABILITY_ENABLED=0` disables Runtime observability APIs.
- `STORY_RUNTIME_RECOVERY_ENABLED=0` disables recovery preview/execute/cancel.
- `INKOS_STUDIO_RUNTIME_PANEL=0` hides and blocks the Studio Runtime panel.
- `INKOS_STUDIO_RUNTIME_RECOVERY=0` disables Studio recovery actions while retaining read-only status.

UI rollback does not stop Runtime, alter authority, modify commits, restore the old Dashboard, or introduce SQLite/file reads.
