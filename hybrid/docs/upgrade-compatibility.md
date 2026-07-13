# Upgrade and compatibility

| App | Runtime | API | DB | Project | Result |
|---|---|---|---:|---|---|
| 1.7.x | 0.1.x | story-runtime/v1 | 7 | story-runtime/v1 | compatible |
| 1.7.x | 0.1.x | story-runtime/v1 | 6 | story-runtime/v1 | migration_required |
| 1.7.x | older/unknown | missing v1 | any | v1 | runtime_too_old |
| older/unknown | 0.1.x | v1 | 7 | v1 | app_too_old |
| 1.7.x | 0.1.x | v1 | >7 | any | schema_too_new |
| any | any | incompatible | any | other | unsupported |

The implemented database checker emits `compatible`, `migration_required` or `schema_too_new`; the process-manager handshake rejects Runtime/schema mismatch. The broader App/Runtime statuses are the product decision matrix and still require a single combined DTO before every label is machine-emitted.

Upgrade with `story-runtime --db project.db migrate --snapshot-dir backups --report migration-report.json`. The command reads the checksum ledger, creates an online pre-migration snapshot when the version changes, uses transactional migrations where SQLite permits and writes a report. Interrupted legacy import jobs retain resume checkpoints; database migration resume beyond transaction rollback is not separately implemented.

Rollback restores the pre-migration snapshot into a new directory and runs compatibility/integrity/doctor/replay. Never delete the upgraded directory until acceptance. Down migrations are development-tested internally, but the product CLI rejects in-place downgrade because no current migration is release-declared reversible. Only a future release note and migration declaration may open a specific reversible path.
