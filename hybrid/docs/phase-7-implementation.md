# Phase 7 implementation

Date: 2026-07-13

Phase 7 migrates legacy InkOS and optional webnovel-writer projects into Story Runtime while keeping the source read-only and delaying authority cutover until explicit confirmation. It does not implement Phase 8 or Phase 9.

## Job architecture

Migration 6 adds `migration_jobs`, `migration_import_ledger`, and `migration_source_provenance`. Jobs follow:

`DISCOVERED → SCANNED → MAPPED → VALIDATED → AWAITING_DECISIONS → READY → IMPORTING → VERIFYING → COMPLETED`

`PAUSED`, `FAILED`, `ROLLED_BACK`, and `QUARANTINED` are durable exceptional states. Job identity is source fingerprint + mapping version + target project. Stable CIR IDs and the ledger make retries idempotent.

## Source protection

The scanner uses non-following directory iteration, byte reads, and SQLite `mode=ro&immutable=1`. It never imports Python/JS, executes hooks, extracts ZIP files, writes the source, or changes source mtime. Symlinks are rejected; escaping links become blocking `corrupted_source` conflicts. ZIP entries are checked for absolute paths, `..`, expanded size and per-entry size without extraction. Paths are normalized with `resolve`; per-file, total-byte and file-count limits are configurable.

The manifest records relative path, kind, byte size, SHA-256, encoding, parse state and original mtime. UTF-8/UTF-8-BOM/UTF-16 are accepted; other encoding failures are reported.

## Import, verify and cutover

Dry-run reports additions, merges, ignored/quarantined conflicts, estimated revision/events/entities, unmapped fields, risks and target bytes. An existing target is protected by `sqlite3_backup`; integrity and SHA-256 are verified. A new target uses an explicit empty-target checkpoint.

Import occurs in Runtime-owned batches of 100 CIR items. Each batch commits its ledger entries and checkpoint together; a pause or process interruption resumes by skipping the stable IDs already present in the ledger. The verified pre-import snapshot remains the rollback boundary for a partially imported target. The target remains `legacy`.

Verification rechecks the live source manifest, reports body/checksum coverage, entity/relationship/hook/summary coverage, fact/timeline counts, unmapped/quarantined counts and deep doctor output, then independently replays the effective CIR into a temporary Runtime database seeded from the target snapshot. Cutover is blocked unless that replay hash equals the live target projection hash. Chapter body coverage below 100% also blocks completion.

Cutover requires `COMPLETED` plus exact `CONFIRM_RUNTIME_CUTOVER`. Only then is `projects.authority_mode` changed to `runtime`. Pre-cutover rollback restores the target snapshot or removes the new trial project. Source files are never deleted and new Runtime chapters are never silently back-written.

## API and Studio

OpenAPI 0.7 adds create/list/get, scan, decisions, dry-run, snapshot, import, verify, pause/resume, cutover, rollback and report endpoints under `/migration-jobs`. Snapshot/import/verify/cutover/rollback require Runtime writes to be enabled.

Studio’s migration wizard performs the 15 requested steps through `StoryRuntimeClient`. The browser and Studio server never query SQLite. Conflicts are handled individually; progress, checksums, dry-run, coverage, rollback, confirmation and report download are visible.
