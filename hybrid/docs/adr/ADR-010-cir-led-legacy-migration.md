# ADR-010: CIR-led legacy migration and delayed authority cutover

- Status: accepted
- Date: 2026-07-13
- Phase: 7

## Decision

InkOS and webnovel-writer importers produce `canonical-import/v1` before any target authority write. Only Story Runtime validates and imports CIR. Studio is an API client and never reads source SQLite or target SQLite.

Migration jobs are durable state machines. Target projects remain `authority_mode=legacy` through scan, decision, dry-run, snapshot, import, and verify. `authority_mode=runtime` is written only after `COMPLETED`, successful doctor/replay verification, and the exact operator confirmation `CONFIRM_RUNTIME_CUTOVER`.

Every semantic disagreement is a conflict with source, candidates, evidence, recommendation, human decision, and resolution audit. Recommendations never act as silent winner rules. Source paths are read-only; scripts are never executed; symlinks are not followed; archives are inspected but not extracted.

## Consequences

- There is no dual authority during migration.
- Import retries use stable CIR IDs and `migration_import_ledger`.
- Verified SQLite backup snapshots, not live-file copies, protect existing targets.
- Format adapters can change without changing target tables.
- Old files remain available and are never automatically deleted or back-written.

