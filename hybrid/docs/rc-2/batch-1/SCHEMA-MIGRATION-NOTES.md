# Schema Migration Notes

Migration: 8, `immutable_project_revision_manifests`
Direction: additive over schema 7

Before applying migration 8 to a file database, the migration engine creates `DATABASE.pre-manifest-v7.sqlite3`, performs SQLite online backup, verifies `PRAGMA integrity_check=ok`, and verifies schema version 7. An existing backup path fails closed for operator inspection rather than being overwritten. If migration 8 is interrupted after the backup but before commit, schema changes roll back atomically, the verified schema-7 backup remains, and a retry intentionally stops until an operator inspects and archives/removes that backup.

The migration retains all old tables/events/revisions, adds project history/manifest handshake columns, creates the immutable ledger/indexes/triggers, and creates no project manifest rows. Existing projects default to `manifest_backfill_required=1` and `history_completeness=unavailable`.

Before any manifest exists, SQL downgrade of migration 8 is mechanically possible for controlled development databases. Once any manifest exists, the migration engine blocks downgrade. Operational rollback after that stop point is: stop writes, preserve the whole database, and restore a verified pre-cutover/full backup with a compatible Runtime. Dropping manifests or reusing numbers is prohibited.

Schema version 8 is the mixed-version handshake. Runtime startup always migrates/checks the database; an older schema-7 Runtime sees a newer schema and refuses startup instead of silently writing without manifests. The compatibility window therefore permits old readers only through a deliberately compatible read-only deployment, not old writers.
